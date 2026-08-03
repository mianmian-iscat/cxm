"""
quality_scorer.py — 五维评估与上线评级 (Gap 2.6)

评估子系统。职责：
- 五维评分（0-100 分制）
- A/B/C/D 上线评级
- 生成质量报告

使用方式：
    from core.quality_scorer import QualityScorer
    scorer = QualityScorer()
    report = scorer.score(metrics_report, assertion_summary, evidence_summary)
    # report.rating = "A" / "B" / "C" / "D"
"""

from dataclasses import dataclass, field
from typing import  Dict, Optional

@dataclass
class QualityReport:
    """质量评估报告"""
    dimensions: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    rating: str = "D"
    rating_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "dimensions": self.dimensions,
            "weights": self.weights,
            "totalScore": round(self.total_score, 2),
            "rating": self.rating,
            "ratingReason": self.rating_reason,
        }

# 六维权重
_WEIGHTS = {
    "correctness": 0.25,   # 功能正确性
    "business_value": 0.25, # 业务价值性
    "stability": 0.20,     # 执行稳定性
    "performance": 0.10,   # 性能效率
    "extensibility": 0.10, # 可扩展性
    "knowledge_completeness": 0.10,  # 知识完整性
}

# 人工基线耗时（毫秒），用于计算提效比
_MANUAL_BASELINE_MS = {
    "f88_material": 300000,     # 5 分钟
    "xiaoer_product": 240000,   # 4 分钟
    "qianniu_material": 180000, # 3 分钟
    "default": 200000,          # 默认 3.3 分钟
}

class QualityScorer:
    """
    五维评估与上线评级。
    """

    def __init__(self, manual_baseline_ms: int = 0, business_type: str = "default"):
        """
        Args:
            manual_baseline_ms: 人工执行基线耗时（ms），0 时按 business_type 自动选取
            business_type: 业务类型
        """
        self._business_type = business_type
        if manual_baseline_ms > 0:
            self._baseline_ms = manual_baseline_ms
        else:
            self._baseline_ms = _MANUAL_BASELINE_MS.get(business_type, _MANUAL_BASELINE_MS["default"])

    def score(
        self,
        metrics_report,
        assertion_summary: Optional[dict] = None,
        evidence_summary: Optional[dict] = None,
        step_results: Optional[list] = None,
        completeness_report=None,
    ) -> QualityReport:
        """
        计算六维评分和上线评级。

        Args:
            metrics_report: MetricsReport 实例或 dict
            assertion_summary: assertion.to_summary() 的输出
            evidence_summary: evidence.to_summary_dict() 的输出
            step_results: output["steps"] 列表
            completeness_report: CompletenessReport 实例或 dict

        Returns:
            QualityReport
        """
        report = QualityReport(weights=dict(_WEIGHTS))

        # 提取数据
        core = self._extract_core(metrics_report)
        assertion = assertion_summary or {}
        evidence = evidence_summary or {}
        steps = step_results or []

        # 1. 功能正确性 (25%)
        report.dimensions["correctness"] = self._score_correctness(core, assertion, steps)

        # 2. 业务价值性 (25%)
        report.dimensions["business_value"] = self._score_business_value(core, evidence)

        # 3. 执行稳定性 (20%)
        report.dimensions["stability"] = self._score_stability(core, evidence)

        # 4. 性能效率 (10%)
        report.dimensions["performance"] = self._score_performance(core)

        # 5. 可扩展性 (10%)
        report.dimensions["extensibility"] = self._score_extensibility(core, evidence)

        # 6. 知识完整性 (10%)
        report.dimensions["knowledge_completeness"] = self._score_knowledge_completeness(
            completeness_report
        )

        # 加权总分
        report.total_score = sum(
            report.dimensions[dim] * _WEIGHTS[dim] for dim in _WEIGHTS
        )

        # 评级
        report.rating, report.rating_reason = self._compute_rating(report)

        return report

    # ── 维度评分 ──

    def _score_correctness(self, core: dict, assertion: dict, steps: list) -> float:
        """功能正确性：assertion pass rate + step success rate"""
        # assertion pass rate
        total_assertions = assertion.get("total", 0)
        passed_assertions = assertion.get("passed", 0)
        assertion_rate = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 80

        # step success rate
        total_steps = len(steps)
        passed_steps = sum(1 for s in steps if s.get("status") == "pass")
        step_rate = (passed_steps / total_steps * 100) if total_steps > 0 else 80

        # 综合
        return min(100, assertion_rate * 0.5 + step_rate * 0.5)

    def _score_business_value(self, core: dict, evidence: dict) -> float:
        """业务价值性：提效比 + 证据完整度"""
        # 提效比
        ai_duration = core.get("avg_duration_ms", 0)
        if ai_duration > 0 and self._baseline_ms > 0:
            efficiency = min(100, (self._baseline_ms / ai_duration) * 50)
        else:
            efficiency = 60

        # 证据完整度
        ev_count = evidence.get("evidenceCount", 0)
        ev_validated = evidence.get("validatedCount", 0)
        evidence_score = (ev_validated / ev_count * 50) if ev_count > 0 else 40

        return min(100, efficiency + evidence_score)

    def _score_stability(self, core: dict, evidence: dict) -> float:
        """执行稳定性：false_positive_rate 反转 + 无熔断"""
        fpr = core.get("false_positive_rate", 0)
        stability = (1 - fpr) * 80

        # 错误率
        ev_errors = evidence.get("errorCount", 0)
        ev_total = evidence.get("evidenceCount", 0)
        if ev_total > 0:
            error_rate = ev_errors / ev_total
            stability += (1 - error_rate) * 20
        else:
            stability += 20

        return min(100, stability)

    def _score_performance(self, core: dict) -> float:
        """性能效率：avg_duration 与基线对比"""
        duration = core.get("avg_duration_ms", 0)
        if duration <= 0:
            return 70
        # 60s 以内满分，120s 以上 50 分
        if duration <= 60000:
            return 100
        elif duration <= 120000:
            return 100 - (duration - 60000) / 60000 * 50
        else:
            return max(30, 50 - (duration - 120000) / 60000 * 20)

    def _score_extensibility(self, core: dict, evidence: dict) -> float:
        """可扩展性：工具覆盖率 + 证据链完整度"""
        # 基础分
        score = 60

        # 有 evidence 加分
        if evidence.get("evidenceCount", 0) > 0:
            score += 20

        # 有 validated 加分
        if evidence.get("validatedCount", 0) > 0:
            score += 10

        # 有 LLM 调用加分
        if core.get("cost_per_task", 0) > 0:
            score += 10

        return min(100, score)

    def _score_knowledge_completeness(self, completeness_report) -> float:
        """
        知识完整性：覆盖率 + 缺口严重度惩罚。

        Args:
            completeness_report: CompletenessReport 实例或 dict
        """
        if completeness_report is None:
            return 70  # 未提供报告时给基线分

        # 支持 dict 和对象两种形式
        if isinstance(completeness_report, dict):
            coverage = completeness_report.get("coverage_pct", 0)
            gaps = completeness_report.get("gaps", [])
        else:
            coverage = completeness_report.coverage_pct
            gaps = completeness_report.gaps

        # 基础分 = 覆盖率直接映射
        score = coverage

        # high 级缺口每个扣 15 分
        high_count = sum(
            1 for g in gaps
            if (g.get("severity") if isinstance(g, dict) else g.severity) == "high"
        )
        score -= high_count * 15

        # medium 级缺口每个扣 5 分
        medium_count = sum(
            1 for g in gaps
            if (g.get("severity") if isinstance(g, dict) else g.severity) == "medium"
        )
        score -= medium_count * 5

        return max(0, min(100, score))

    # ── 评级 ──

    def _compute_rating(self, report: QualityReport) -> tuple:
        """A/B/C/D 评级"""
        correctness = report.dimensions.get("correctness", 0)
        total = report.total_score

        if all(v >= 80 for v in report.dimensions.values()):
            return ("A", "全部维度 >= 80，直接上线")

        if correctness >= 80 and total >= 70:
            return ("B", f"功能正确性 {correctness:.0f} >= 80 且总分 {total:.0f} >= 70，灰度上线")

        if correctness >= 60:
            return ("C", f"功能正确性 {correctness:.0f} >= 60，限场景上线")

        return ("D", f"功能正确性 {correctness:.0f} < 60，拒绝上线")

    # ── 工具 ──

    def _extract_core(self, metrics_report) -> dict:
        """从 MetricsReport 或 dict 提取核心指标"""
        if isinstance(metrics_report, dict):
            core = metrics_report.get("core_metrics", metrics_report)
            return {
                "task_success_rate": core.get("task_success_rate", 0),
                "avg_duration_ms": core.get("avg_task_duration_ms", core.get("avg_duration_ms", 0)),
                "cost_per_task": core.get("cost_per_task", 0),
                "false_positive_rate": core.get("false_positive_rate", 0),
            }
        # MetricsReport 实例
        try:
            cm = metrics_report.core_metrics
            return {
                "task_success_rate": cm.task_success_rate,
                "avg_duration_ms": cm.avg_task_duration_ms,
                "cost_per_task": cm.cost_per_task,
                "false_positive_rate": cm.false_positive_rate,
            }
        except AttributeError:
            return {}
