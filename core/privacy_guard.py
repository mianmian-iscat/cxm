"""
privacy_guard.py — 安全红线与隐私隔离

差距 2.5 补齐。职责：
- 安全红线引擎: 从 soul.md 或代码加载红线规则
- 红线检查: 群聊/个人数据隔离、MEMORY.md [PUBLIC] 标签、上传前脱敏、跨 workspace 确认
- 脱敏过滤器: PrivacyFilter 管道，支持链式脱敏规则
- 红线违规记录与告警

使用方式:
    from core.privacy_guard import PrivacyGuard, PrivacyFilter, MaskRule
    guard = PrivacyGuard()
    result = guard.sanitize("手机13812345678")
    violations = guard.check_all({"context": "group"})
"""

import re
import time
from dataclasses import dataclass, field
from typing import  Callable, Dict, List, Optional

# ── 数据模型 ──

@dataclass
class MaskRule:
    """脱敏规则"""
    name: str
    pattern: str
    replacement: Callable[[re.Match], str]
    description: str = ""

    def apply(self, text: str) -> str:
        """应用脱敏规则"""
        return re.sub(self.pattern, self.replacement, text)

    @classmethod
    def phone(cls) -> "MaskRule":
        """手机号脱敏: 13812345678 -> 138****5678"""
        def _mask(m: re.Match) -> str:
            num = m.group(0)
            return num[:3] + "****" + num[-4:]
        return cls(
            name="phone",
            pattern=r"1[3-9]\d{9}",
            replacement=_mask,
            description="手机号脱敏",
        )

    @classmethod
    def id_card(cls) -> "MaskRule":
        """身份证脱敏: 330102199001011234 -> 3301***********234"""
        def _mask(m: re.Match) -> str:
            num = m.group(0)
            return num[:4] + "*" * (len(num) - 7) + num[-3:]
        return cls(
            name="id_card",
            pattern=r"\d{17}[\dXx]|\d{15}",
            replacement=_mask,
            description="身份证号脱敏",
        )

    @classmethod
    def email(cls) -> "MaskRule":
        """邮箱脱敏: test@example.com -> ***@example.com"""
        def _mask(m: re.Match) -> str:
            email = m.group(0)
            at_idx = email.index("@")
            return "***" + email[at_idx:]
        return cls(
            name="email",
            pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            replacement=_mask,
            description="邮箱脱敏",
        )

    @classmethod
    def token(cls) -> "MaskRule":
        """Token/JWT 脱敏"""
        def _mask(m: re.Match) -> str:
            tok = m.group(0)
            if len(tok) > 8:
                return tok[:4] + "****" + tok[-4:]
            return "****"
        return cls(
            name="token",
            pattern=r"eyJ[A-Za-z0-9_-]+\.?[A-Za-z0-9_.-]*",
            replacement=_mask,
            description="JWT Token 脱敏",
        )

    @classmethod
    def bank_card(cls) -> "MaskRule":
        """银行卡号脱敏"""
        def _mask(m: re.Match) -> str:
            num = m.group(0)
            return num[:4] + " **** **** " + num[-4:]
        return cls(
            name="bank_card",
            pattern=r"\d{16,19}",
            replacement=_mask,
            description="银行卡号脱敏",
        )

# ── 脱敏过滤器 ──

class PrivacyFilter:
    """
    链式脱敏过滤器。

    支持添加多条 MaskRule，依次应用。
    """

    def __init__(self):
        self._rules: List[MaskRule] = []

    def add_rule(self, rule: MaskRule):
        """添加脱敏规则"""
        self._rules.append(rule)

    def add_default_rules(self):
        """添加所有默认脱敏规则"""
        self._rules.extend([
            MaskRule.phone(),
            MaskRule.id_card(),
            MaskRule.email(),
            MaskRule.token(),
            MaskRule.bank_card(),
        ])

    def apply(self, text: str) -> str:
        """对文本应用所有脱敏规则"""
        if not text:
            return text
        result = text
        for rule in self._rules:
            result = rule.apply(result)
        return result

    def apply_dict(self, data: dict) -> dict:
        """对字典所有字符串值应用脱敏"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.apply(value)
            elif isinstance(value, dict):
                result[key] = self.apply_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.apply(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def get_rules(self) -> List[str]:
        """获取已注册的规则名称"""
        return [r.name for r in self._rules]

# ── 红线检查 ──

@dataclass
class RedlineViolation:
    """红线违规记录"""
    rule_id: str
    description: str
    context: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    severity: str = "CRITICAL"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "context": self.context,
            "timestamp": self.timestamp,
            "severity": self.severity,
        }

@dataclass
class RedlineCheckResult:
    """红线检查结果"""
    passed: bool = True
    violations: List[RedlineViolation] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    def add_violation(self, violation: RedlineViolation):
        self.violations.append(violation)
        self.passed = False

class RedlineChecker:
    """
    安全红线检查器。

    支持注册多条红线规则，对操作上下文进行合规检查。
    """

    def __init__(self):
        self._redlines: Dict[str, dict] = {}

    def add_redline(self, rule_id: str, description: str, checker: Optional[Callable] = None):
        """注册红线规则"""
        self._redlines[rule_id] = {
            "description": description,
            "checker": checker or self._default_checker(rule_id),
        }

    def list_redlines(self) -> List[dict]:
        """列出所有红线规则"""
        return [
            {"rule_id": rid, "description": info["description"]}
            for rid, info in self._redlines.items()
        ]

    def check(self, rule_id: str, ctx: dict) -> RedlineCheckResult:
        """检查单条红线"""
        result = RedlineCheckResult()
        rule = self._redlines.get(rule_id)
        if not rule:
            return result

        checker = rule["checker"]
        try:
            violation = checker(ctx)
            if violation:
                result.add_violation(RedlineViolation(
                    rule_id=rule_id,
                    description=rule["description"],
                    context=ctx,
                ))
        except Exception:
            pass

        return result

    def check_all(self, ctx: dict) -> List[RedlineViolation]:
        """检查所有红线"""
        violations = []
        for rule_id in self._redlines:
            result = self.check(rule_id, ctx)
            violations.extend(result.violations)
        return violations

    def _default_checker(self, rule_id: str) -> Callable:
        """默认检查器（基于 rule_id 的内置逻辑）"""
        def _check(ctx: dict) -> bool:
            """返回 True 表示违规"""
            if rule_id == "no_personal_data_in_group":
                # 群聊场景禁止读取个人敏感字段
                return ctx.get("context") == "group" and ctx.get("has_personal", False)

            elif rule_id == "public_only_memory":
                # MEMORY.md 仅可读取 [PUBLIC] 标签条目
                return ctx.get("memory_tag") and ctx["memory_tag"] != "PUBLIC"

            elif rule_id == "sanitize_before_upload":
                # BadCase 上传前必须脱敏
                content = ctx.get("content", "")
                if isinstance(content, str):
                    # 检查是否包含未脱敏的敏感信息
                    if re.search(r"1[3-9]\d{9}", content):
                        return True
                    if re.search(r"\d{17}[\dXx]", content):
                        return True
                return False

            elif rule_id == "cross_workspace_confirm":
                # 跨 workspace 数据访问需二次确认
                return ctx.get("cross_workspace", False) and not ctx.get("confirmed", False)

            return False
        return _check

# ── 统一安全守卫 ──

class PrivacyGuard:
    """
    统一安全守卫。

    整合 PrivacyFilter（脱敏）+ RedlineChecker（红线检查）。
    """

    def __init__(self):
        self._filter = PrivacyFilter()
        self._filter.add_default_rules()
        self._checker = RedlineChecker()
        self._violation_log: List[RedlineViolation] = []

        # 注册默认红线
        self._register_default_redlines()

    def _register_default_redlines(self):
        """注册默认安全红线"""
        self._checker.add_redline(
            "no_personal_data_in_group",
            "群聊场景禁止读取个人敏感字段",
        )
        self._checker.add_redline(
            "public_only_memory",
            "MEMORY.md仅可读取[PUBLIC]标签",
        )
        self._checker.add_redline(
            "sanitize_before_upload",
            "BadCase上传前必须脱敏",
        )
        self._checker.add_redline(
            "cross_workspace_confirm",
            "跨workspace数据访问需二次确认",
        )

    def sanitize(self, text: str) -> str:
        """对文本执行全量脱敏"""
        return self._filter.apply(text)

    def sanitize_dict(self, data: dict) -> dict:
        """对字典执行全量脱敏"""
        return self._filter.apply_dict(data)

    def add_redline(self, rule_id: str, description: str, checker: Optional[Callable] = None):
        """添加自定义红线"""
        self._checker.add_redline(rule_id, description, checker)

    def check_all(self, ctx: dict) -> List[RedlineViolation]:
        """检查所有红线，记录违规"""
        violations = self._checker.check_all(ctx)
        self._violation_log.extend(violations)
        return violations

    def get_violation_log(self) -> List[dict]:
        """获取违规日志"""
        return [v.to_dict() for v in self._violation_log]

    def get_filter(self) -> PrivacyFilter:
        """获取内部过滤器"""
        return self._filter

    def get_checker(self) -> RedlineChecker:
        """获取内部检查器"""
        return self._checker
