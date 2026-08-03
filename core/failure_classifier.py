"""
failure_classifier.py — 失败分类器与分级放行 (Gap 2.4)

智能自愈子系统。职责：
- 对步骤失败进行根因分类
- P0/P1/P2 三级放行决策
- 生成放行决策报告

使用方式：
    from core.failure_classifier import FailureClassifier
    fc = FailureClassifier()
    report = fc.classify(step_result, evidence_entry)
    decision = fc.get_release_decision(all_reports)
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union


class FailureCategory(str, Enum):
    """失败根因分类标准枚举

    所有字符串别名（real_bug / script_issue / data_invalid / env_failure / pass /
    unknown 以及历史拼写错误如 'realBug' / 'script-issue'）必须通过
    FailureCategory.resolve() 归一化到本枚举，禁止在下游直接用裸字符串比较。
    """

    REAL_BUG = "real_bug"
    SCRIPT_ISSUE = "script_issue"
    DATA_INVALID = "data_invalid"
    ENV_FAILURE = "env_failure"
    PASS = "pass"
    UNKNOWN = "unknown"

    def __new__(cls, value: str):
        # 让枚举值同时成为字符串实例，保留 'env_failure' == FailureCategory.ENV_FAILURE 语义
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj


# ── 别名归一化表（小写 → 规范值）──
# 必须放在类外，否则会被 str,Enum 元类当成枚举成员
_FAILURE_CATEGORY_ALIASES = {
    # canonical
    "real_bug": "real_bug",
    "script_issue": "script_issue",
    "data_invalid": "data_invalid",
    "env_failure": "env_failure",
    "pass": "pass",
    "unknown": "unknown",
    # 历史别名
    "realbug": "real_bug",
    "real-bug": "real_bug",
    "real bug": "real_bug",
    "scriptissue": "script_issue",
    "script-issue": "script_issue",
    "script issue": "script_issue",
    "datainvalid": "data_invalid",
    "data-invalid": "data_invalid",
    "data invalid": "data_invalid",
    "envfailure": "env_failure",
    "env-failure": "env_failure",
    "env failure": "env_failure",
    "environment_failure": "env_failure",
    "ok": "pass",
    "success": "pass",
}


@staticmethod
def _failure_category_resolve(raw: Union[str, "FailureCategory", None]) -> "FailureCategory":
    """将任意别名/枚举/None 归一化为标准枚举；未知别名回退到 UNKNOWN。

    Examples:
        FailureCategory.resolve("realBug")        -> REAL_BUG
        FailureCategory.resolve("script-issue")   -> SCRIPT_ISSUE
        FailureCategory.resolve(FailureCategory.PASS) -> PASS
        FailureCategory.resolve(None)             -> UNKNOWN
    """
    if raw is None:
        return FailureCategory.UNKNOWN
    if isinstance(raw, FailureCategory):
        return raw
    key = str(raw).strip().lower()
    canonical = _FAILURE_CATEGORY_ALIASES.get(key)
    if canonical is None:
        return FailureCategory.UNKNOWN
    return FailureCategory(canonical)


# 作为类方法对外暴露（用赋值而非 @classmethod，避免被枚举元类拦截）
FailureCategory.resolve = _failure_category_resolve


@dataclass
class FailureReport:
    """单步失败分类报告"""
    step_id: str
    step_type: str
    category: Union[FailureCategory, str]   # 对外兼容字符串；构造时优先传枚举
    severity: str          # "P0" / "P1" / "P2" / "NONE"
    action: str            # "block" / "warn" / "skip" / "none"
    suggestion: str = ""
    error_message: str = ""

    def __post_init__(self):
        # 强制归一化：保证外部传入的字符串别名也能转为标准枚举
        if not isinstance(self.category, FailureCategory):
            self.category = FailureCategory.resolve(self.category)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id, "step_type": self.step_type,
            "category": self.category.value if isinstance(self.category, FailureCategory) else str(self.category),
            "severity": self.severity,
            "action": self.action, "suggestion": self.suggestion,
        }

# ── P0 阻断关键词 ──

_P0_PATTERNS = [
    r"login.*required", r"登录", r"SSO", r"BUC",
    r"安全拦截", r"compliance", r"forbidden", r"403",
    r"unauthorized", r"401", r"permission denied",
    r"login_required", r"loginType",
]

# ── P1 警告关键词 ──

_P1_PATTERNS = [
    r"find error", r"querySelector", r"offsetParent",
    r"找不到", r"未找到", r"selector",
    r"TimeoutError", r"timeout", r"超时",
    r"ECONNREFUSED", r"ECONNRESET",
    r"stale element", r"element.*not found",
]

# ── P2 跳过关键词 ──

_P2_PATTERNS = [
    r"network.*idle", r"intermittent",
    r"偶发", r"non-critical",
]

class FailureClassifier:
    """
    失败分类器：对步骤执行结果进行 P0/P1/P2 分级。
    """

    def classify(self, step_result: dict, evidence_entry: Optional[dict] = None) -> FailureReport:
        """
        对单步结果进行分类。

        Args:
            step_result: 步骤执行结果 dict
            evidence_entry: 对应 evidence 条目（可选）

        Returns:
            FailureReport
        """
        status = step_result.get("status", "pass")
        step_id = step_result.get("id", f"step{step_result.get('index', '?')}")
        step_type = step_result.get("type", "unknown")
        error_msg = step_result.get("error", "")

        # 通过的步骤
        if status == "pass":
            return FailureReport(
                step_id=step_id, step_type=step_type,
                category=FailureCategory.PASS, severity="NONE", action="none",
            )

        # 跳过的步骤
        if status == "skip":
            return FailureReport(
                step_id=step_id, step_type=step_type,
                category=FailureCategory.PASS, severity="NONE", action="skip",
                suggestion="步骤已跳过",
            )

        # 失败的步骤 — 分级判断
        severity, action, suggestion = self._assess(error_msg, step_type)

        # 分类
        category = self._categorize(error_msg, step_type)

        return FailureReport(
            step_id=step_id, step_type=step_type,
            category=category, severity=severity, action=action,
            suggestion=suggestion, error_message=error_msg,
        )

    def get_release_decision(self, reports: List[FailureReport]) -> dict:
        """
        汇总所有失败报告，生成放行决策。

        Returns:
            {blocked: bool, p0_count, p1_warnings, p2_skipped, suggestion}
        """
        p0 = [r for r in reports if r.severity == "P0"]
        p1 = [r for r in reports if r.severity == "P1"]
        p2 = [r for r in reports if r.severity == "P2"]

        return {
            "blocked": len(p0) > 0,
            "p0_count": len(p0),
            "p1_count": len(p1),
            "p2_count": len(p2),
            "p1_warnings": [r.to_dict() for r in p1],
            "p2_skipped": [r.to_dict() for r in p2],
            "suggestion": self._overall_suggestion(p0, p1, p2),
        }

    # ── 内部方法 ──

    def _assess(self, error_msg: str, step_type: str) -> tuple:
        """返回 (severity, action, suggestion)"""
        error_lower = error_msg.lower()

        # P0 检查
        for pat in _P0_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return ("P0", "block", f"登录态/安全问题，需人工处理: {error_msg[:60]}")

        # P1 检查
        for pat in _P1_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return ("P1", "warn", f"建议复测: {error_msg[:60]}")

        # P2 检查
        for pat in _P2_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return ("P2", "skip", "偶发问题，已跳过并计入指标")

        # assert 失败默认 P1
        if step_type == "assert":
            return ("P1", "warn", "断言失败，建议检查业务逻辑")

        # 默认 P2
        return ("P2", "skip", f"未分类失败: {error_msg[:40]}")

    def _categorize(self, error_msg: str, step_type: str) -> FailureCategory:
        """根因分类（统一返回 FailureCategory 枚举）"""
        if any(re.search(p, error_msg, re.I) for p in _P0_PATTERNS):
            return FailureCategory.ENV_FAILURE
        if any(re.search(p, error_msg, re.I) for p in [r"find error", r"querySelector", r"offsetParent", r"selector"]):
            return FailureCategory.SCRIPT_ISSUE
        if any(re.search(p, error_msg, re.I) for p in [r"TimeoutError", r"ECONNREFUSED", r"timeout"]):
            return FailureCategory.ENV_FAILURE
        if step_type == "assert":
            return FailureCategory.REAL_BUG
        return FailureCategory.UNKNOWN

    @staticmethod
    def _overall_suggestion(p0: list, p1: list, p2: list) -> str:
        if p0:
            return f"P0 阻断: {p0[0].suggestion}"
        if p1:
            return f"{len(p1)} 个 P1 警告，建议复测"
        if p2:
            return f"{len(p2)} 个 P2 已跳过"
        return "全部通过"
