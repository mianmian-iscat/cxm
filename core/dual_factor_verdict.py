"""
dual_factor_verdict.py — 双因子失败裁决引擎（全托管闭环 D 核心）

来源：服饰质量全托管数字人架构方案 §3.4
设计目标：单一裁决误报率 >15%，双因子可压到 <5%。

裁决流程：
    步骤 1 规则层：FailureClassifier 基于 diff/状态码/关键字 → 初判（Bug/脚本/数据/环境）
    步骤 2 LLM 层：传入 PRD 片段 + 失败证据 + 规则初判 → 二次确认，附带置信度
    裁决：规则与 LLM 一致 → 直接落地；不一致 → 偏保守，标记 NEED_HUMAN_REVIEW

与分级放行联动：
    P0（核心主链路/资金/用户敏感数据）→ 阻断 + 自动建 Bug
    P1（重要功能/性能基线）          → 警告 + 建议人工复测
    P2（次要分支/兼容性/UI微调）     → 自动跳过 + 计入跳过率指标

使用方式：
    from core.dual_factor_verdict import DualFactorVerdictEngine, VerdictResult

    engine = DualFactorVerdictEngine(llm_config={...})
    verdict = engine.verdict(step_result, evidence_entry, prd_context="...")
    # verdict.final_category  — 最终分类
    # verdict.action          — block / warn / skip / review
    # verdict.needs_human     — 是否需要人工复核
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List

from core.failure_classifier import FailureClassifier, FailureReport, FailureCategory
from core.llm_judge import create_llm_judge, JudgmentResult, load_llm_config_from_yaml


# ── 类别映射：FailureCategory ↔ LLM 类别 ──
# llm_judge 使用 true_bug，failure_classifier 使用 real_bug，需归一化
_RULE_TO_LLM = {
    FailureCategory.REAL_BUG: "true_bug",
    FailureCategory.SCRIPT_ISSUE: "script_issue",
    FailureCategory.DATA_INVALID: "data_invalid",
    FailureCategory.ENV_FAILURE: "env_failure",
    FailureCategory.UNKNOWN: "unknown",
}

_LLM_TO_RULE = {v: k for k, v in _RULE_TO_LLM.items()}


@dataclass
class VerdictResult:
    """双因子裁决结果"""
    step_id: str = ""
    # 规则层
    rule_category: str = "unknown"
    rule_severity: str = "P2"
    # LLM 层
    llm_category: str = "unknown"
    llm_confidence: float = 0.0
    llm_reasoning: str = ""
    # 最终裁决
    agreed: bool = False
    final_category: str = "unknown"
    final_severity: str = "P2"
    action: str = "skip"              # block / warn / skip / review
    needs_human: bool = False
    verdict_source: str = ""          # dual_agree / conservative_fallback / rule_only
    suggestion: str = ""
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "rule_category": self.rule_category,
            "rule_severity": self.rule_severity,
            "llm_category": self.llm_category,
            "llm_confidence": round(self.llm_confidence, 3),
            "llm_reasoning": self.llm_reasoning,
            "agreed": self.agreed,
            "final_category": self.final_category,
            "final_severity": self.final_severity,
            "action": self.action,
            "needs_human": self.needs_human,
            "verdict_source": self.verdict_source,
            "suggestion": self.suggestion,
            "latency_ms": self.latency_ms,
        }


# ── 分级放行策略（ADR-D1：P0 阻断 / P1 警告 / P2 跳过）──

_RELEASE_POLICY = {
    "P0": {"action": "block", "desc": "阻断 + @责任人 + 自动建 Aone Bug"},
    "P1": {"action": "warn", "desc": "警告 + 报告标注 + 建议人工复测"},
    "P2": {"action": "skip", "desc": "自动跳过 + 计入跳过率指标"},
}

# 需人工复核时的保守处置：severity 不降级，action 升级为 review
_REVIEW_ACTION = "review"


class DualFactorVerdictEngine:
    """
    双因子失败裁决引擎。

    协调 FailureClassifier（规则层）与 LLM Judge（LLM 层），
    输出一致性裁决结果，不一致时偏保守标记需人工复核。
    """

    def __init__(
        self,
        llm_config: Optional[dict] = None,
        confidence_threshold: float = 0.5,
        base_dir: str = "",
    ):
        """
        Args:
            llm_config: LLM 裁决配置（None 时尝试从 self_healing_rules.yaml 加载）
            confidence_threshold: LLM 置信度低于此值时视为"LLM 不确定"，走保守路径
            base_dir: web-automation 根目录（用于加载 yaml 配置）
        """
        self._classifier = FailureClassifier()
        self._confidence_threshold = confidence_threshold

        # 初始化 LLM 裁决器
        if llm_config is None and base_dir:
            llm_config = load_llm_config_from_yaml(base_dir)
        self._judge_fn = create_llm_judge(llm_config) if llm_config else None

        # 统计
        self._stats = {
            "total": 0, "agreed": 0, "disagreed": 0,
            "human_review": 0, "rule_only": 0,
        }

    def verdict(
        self,
        step_result: dict,
        evidence_entry: Optional[dict] = None,
        prd_context: str = "",
    ) -> VerdictResult:
        """
        对单步失败执行双因子裁决。

        Args:
            step_result: 步骤执行结果 dict（含 status/error/type/id）
            evidence_entry: 对应 evidence 条目（可选，增强 LLM 上下文）
            prd_context: PRD 片段（可选，帮助 LLM 判断是否为真实 Bug）

        Returns:
            VerdictResult 双因子裁决结果
        """
        start = time.time()
        self._stats["total"] += 1

        step_id = step_result.get("id", f"step{step_result.get('index', '?')}")

        # ── 步骤 1：规则层初判 ──
        rule_report: FailureReport = self._classifier.classify(step_result, evidence_entry)
        rule_category = rule_report.category
        rule_severity = rule_report.severity

        # 通过/跳过的步骤无需 LLM 二次确认
        if rule_category == FailureCategory.PASS:
            return VerdictResult(
                step_id=step_id,
                rule_category="pass", rule_severity="NONE",
                final_category="pass", final_severity="NONE",
                action="none", agreed=True,
                verdict_source="rule_pass",
                latency_ms=int((time.time() - start) * 1000),
            )

        # ── 步骤 2：LLM 层二次确认 ──
        llm_result = self._llm_confirm(step_result, evidence_entry, prd_context, rule_report)

        # ── 裁决：一致性判断 ──
        result = self._reconcile(
            step_id, rule_report, llm_result,
        )
        result.latency_ms = int((time.time() - start) * 1000)
        return result

    def verdict_batch(
        self,
        step_results: List[dict],
        evidence_entries: Optional[List[dict]] = None,
        prd_context: str = "",
    ) -> List[VerdictResult]:
        """批量裁决"""
        evidence_entries = evidence_entries or [None] * len(step_results)
        return [
            self.verdict(sr, ev, prd_context)
            for sr, ev in zip(step_results, evidence_entries)
        ]

    def release_decision(self, verdicts: List[VerdictResult]) -> dict:
        """
        基于双因子裁决结果的分级放行决策。

        Returns:
            {
                blocked: bool,           — P0 是否阻断
                release_level: str,      — A/B/C/D 评级
                p0_blocked: [...],       — 阻断项
                p1_warnings: [...],      — 警告项
                p2_skipped: [...],       — 跳过项
                human_reviews: [...],    — 需人工复核项
                skip_rate: float,        — 跳过率
                suggestion: str,
            }
        """
        p0 = [v for v in verdicts if v.final_severity == "P0" and v.action == "block"]
        p1 = [v for v in verdicts if v.final_severity == "P1" and v.action in ("warn", "review")]
        p2 = [v for v in verdicts if v.final_severity == "P2" and v.action == "skip"]
        reviews = [v for v in verdicts if v.needs_human]

        total = len(verdicts) or 1
        skip_rate = len(p2) / total

        # 上线评级（对齐全托管方案 §8）
        if p0:
            release_level = "D"  # 功能不达标，拒绝上线
        elif reviews:
            release_level = "C"  # 存在待人工确认项，限场景上线
        elif p1:
            release_level = "B"  # 功能+稳定达标，灰度上线
        else:
            release_level = "A"  # 全部达标，直接上线

        blocked = len(p0) > 0
        if blocked:
            suggestion = f"P0 阻断: {p0[0].suggestion}"
        elif reviews:
            suggestion = f"{len(reviews)} 项双因子不一致，需人工复核后放行"
        elif p1:
            suggestion = f"{len(p1)} 个 P1 警告，建议复测"
        elif p2:
            suggestion = f"{len(p2)} 个 P2 已跳过（跳过率 {skip_rate:.0%}）"
        else:
            suggestion = "全部通过"

        return {
            "blocked": blocked,
            "release_level": release_level,
            "p0_blocked": [v.to_dict() for v in p0],
            "p1_warnings": [v.to_dict() for v in p1],
            "p2_skipped": [v.to_dict() for v in p2],
            "human_reviews": [v.to_dict() for v in reviews],
            "skip_rate": round(skip_rate, 3),
            "suggestion": suggestion,
        }

    def get_stats(self) -> dict:
        """裁决统计：一致率是误报率的核心度量"""
        total = self._stats["total"] or 1
        return {
            **self._stats,
            "agreement_rate": round(self._stats["agreed"] / total, 3),
        }

    # ── 内部方法 ──

    def _llm_confirm(
        self,
        step_result: dict,
        evidence_entry: Optional[dict],
        prd_context: str,
        rule_report: FailureReport,
    ) -> Optional[JudgmentResult]:
        """LLM 层二次确认"""
        if not self._judge_fn:
            return None

        error_info = {
            "message": step_result.get("error", ""),
            "step_type": step_result.get("type", "unknown"),
            "selector": step_result.get("selector", ""),
            "page_url": step_result.get("url", ""),
            # 增强上下文：规则初判 + PRD 片段 + 证据
            "rule_initial_verdict": rule_report.category.value
                if isinstance(rule_report.category, FailureCategory) else str(rule_report.category),
            "rule_severity": rule_report.severity,
            "prd_context": prd_context[:500] if prd_context else "",
            "evidence_snapshot": str(evidence_entry)[:300] if evidence_entry else "",
        }

        try:
            return self._judge_fn(error_info)
        except Exception:
            return None

    def _reconcile(
        self,
        step_id: str,
        rule_report: FailureReport,
        llm_result: Optional[JudgmentResult],
    ) -> VerdictResult:
        """
        一致性裁决核心逻辑：
        - 规则与 LLM 一致 → 直接落地
        - 不一致 → 主 Agent 兜底（默认偏保守，标记需人工复核）
        - LLM 不可用/不确定 → 降级为 rule_only 模式
        """
        rule_cat = rule_report.category
        rule_cat_str = rule_cat.value if isinstance(rule_cat, FailureCategory) else str(rule_cat)
        severity = rule_report.severity
        policy = _RELEASE_POLICY.get(severity, _RELEASE_POLICY["P2"])

        # LLM 不可用 → 降级为纯规则模式
        if llm_result is None:
            self._stats["rule_only"] += 1
            return VerdictResult(
                step_id=step_id,
                rule_category=rule_cat_str, rule_severity=severity,
                llm_category="unavailable", llm_confidence=0.0,
                agreed=False,
                final_category=rule_cat_str, final_severity=severity,
                action=policy["action"],
                needs_human=False,
                verdict_source="rule_only",
                suggestion=f"[规则层单因子] {rule_report.suggestion}",
            )

        # 类别归一化比对
        llm_cat = llm_result.category
        rule_as_llm = _RULE_TO_LLM.get(rule_cat, "unknown")
        agreed = (rule_as_llm == llm_cat)

        # LLM 置信度过低视为不确定
        llm_uncertain = llm_result.confidence < self._confidence_threshold

        if agreed and not llm_uncertain:
            # ── 双因子一致：直接落地 ──
            self._stats["agreed"] += 1
            return VerdictResult(
                step_id=step_id,
                rule_category=rule_cat_str, rule_severity=severity,
                llm_category=llm_cat, llm_confidence=llm_result.confidence,
                llm_reasoning=llm_result.reasoning,
                agreed=True,
                final_category=rule_cat_str, final_severity=severity,
                action=policy["action"],
                needs_human=False,
                verdict_source="dual_agree",
                suggestion=rule_report.suggestion,
            )

        # ── 不一致或 LLM 不确定：偏保守，标记需人工复核 ──
        self._stats["disagreed"] += 1
        self._stats["human_review"] += 1

        # 保守策略：severity 不降级，action 升级为 review
        # 但如果 LLM 高置信度判定为更轻类别，记录建议供人工参考
        llm_as_rule = _LLM_TO_RULE.get(llm_cat, FailureCategory.UNKNOWN)
        downgrade_hint = ""
        if not agreed and llm_result.confidence >= 0.8:
            llm_severity = self._severity_for_category(llm_as_rule)
            if _severity_rank(llm_severity) < _severity_rank(severity):
                downgrade_hint = (
                    f"（LLM 高置信度建议降级为 {llm_severity}: {llm_result.reasoning[:60]}）"
                )

        return VerdictResult(
            step_id=step_id,
            rule_category=rule_cat_str, rule_severity=severity,
            llm_category=llm_cat, llm_confidence=llm_result.confidence,
            llm_reasoning=llm_result.reasoning,
            agreed=False,
            final_category=rule_cat_str, final_severity=severity,
            action=_REVIEW_ACTION,
            needs_human=True,
            verdict_source="conservative_fallback",
            suggestion=(
                f"双因子不一致 [规则={rule_cat_str}, LLM={llm_cat}"
                f"@{llm_result.confidence:.2f}]，需人工复核{downgrade_hint}"
            ),
        )

    @staticmethod
    def _severity_for_category(category: FailureCategory) -> str:
        """类别 → 默认 severity 映射"""
        mapping = {
            FailureCategory.ENV_FAILURE: "P0",
            FailureCategory.REAL_BUG: "P1",
            FailureCategory.SCRIPT_ISSUE: "P1",
            FailureCategory.DATA_INVALID: "P1",
            FailureCategory.UNKNOWN: "P2",
        }
        return mapping.get(category, "P2")


def _severity_rank(severity: str) -> int:
    """severity 排序权重（数字越小越严重）"""
    return {"P0": 0, "P1": 1, "P2": 2, "NONE": 3}.get(severity, 2)
