"""
healing_analytics.py — 自愈效果度量与反馈闭环 (维度12)

按维度统计自愈效果，生成健康报告，反馈到配置优化：
- 每种策略的成功率、平均修复时间
- 自愈 ROI 评估
- 自愈健康报告
- 自动调整策略优先级建议

使用方式：
    from core.healing_analytics import HealingAnalytics
    analytics = HealingAnalytics()
    analytics.record_heal(strategy="cdp_relocate", success=True, duration_ms=1500, error_type="selector_issue")
    report = analytics.generate_report()
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict


@dataclass
class _StrategyStats:
    """单策略统计"""
    strategy: str
    attempts: int = 0
    successes: int = 0
    total_duration_ms: int = 0
    error_types: dict = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.attempts, 1)

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.attempts, 1)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "error_types": dict(self.error_types),
        }


@dataclass
class HealingHealthReport:
    """自愈健康报告"""
    total_heals: int = 0
    total_success: int = 0
    overall_success_rate: float = 0.0
    strategy_stats: List[dict] = field(default_factory=list)
    top_error_types: List[dict] = field(default_factory=list)
    roi_score: float = 0.0        # 自愈 ROI（节省时间 / 消耗时间）
    recommendations: List[str] = field(default_factory=list)
    degraded_strategies: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_heals": self.total_heals,
            "total_success": self.total_success,
            "overall_success_rate": round(self.overall_success_rate, 3),
            "strategy_stats": self.strategy_stats,
            "top_error_types": self.top_error_types,
            "roi_score": round(self.roi_score, 2),
            "recommendations": self.recommendations,
            "degraded_strategies": self.degraded_strategies,
        }


class HealingAnalytics:
    """
    自愈效果度量引擎。

    核心能力：
    1. 按策略维度统计成功率、平均修复时间
    2. 自愈 ROI 评估（节省的人工时间 / 自愈计算时间）
    3. 定期生成健康报告 + 策略调整建议
    4. 检测策略退化（成功率持续下降）
    """

    # 人工修复基线时间（秒），用于计算 ROI
    MANUAL_FIX_BASELINE_SEC = 300  # 5 分钟
    # 策略退化阈值（成功率低于此值视为退化）
    DEGRADED_RATE_THRESHOLD = 0.3
    # 最小样本量（低于此值不做退化判断）
    MIN_SAMPLE_SIZE = 5

    def __init__(self):
        self._strategy_stats: Dict[str, _StrategyStats] = {}
        self._error_type_counts: Dict[str, int] = defaultdict(int)
        self._total_heal_time_ms = 0
        self._total_saved_heals = 0

    def record_heal(
        self,
        strategy: str,
        success: bool,
        duration_ms: int = 0,
        error_type: str = "",
    ):
        """
        记录一次自愈操作。

        Args:
            strategy: 策略名称（如 cdp_relocate, knowledge_fix 等）
            success: 是否成功
            duration_ms: 耗时（毫秒）
            error_type: 错误类型
        """
        if strategy not in self._strategy_stats:
            self._strategy_stats[strategy] = _StrategyStats(strategy=strategy)

        stats = self._strategy_stats[strategy]
        stats.attempts += 1
        if success:
            stats.successes += 1
            self._total_saved_heals += 1
        stats.total_duration_ms += duration_ms

        if error_type:
            stats.error_types[error_type] += 1
            self._error_type_counts[error_type] += 1

        self._total_heal_time_ms += duration_ms

    def generate_report(self) -> HealingHealthReport:
        """生成自愈健康报告"""
        report = HealingHealthReport()

        # 总体统计
        total_attempts = sum(s.attempts for s in self._strategy_stats.values())
        total_successes = sum(s.successes for s in self._strategy_stats.values())
        report.total_heals = total_attempts
        report.total_success = total_successes
        report.overall_success_rate = total_successes / max(total_attempts, 1)

        # 各策略统计
        report.strategy_stats = sorted(
            [s.to_dict() for s in self._strategy_stats.values()],
            key=lambda x: x["attempts"],
            reverse=True,
        )

        # Top 错误类型
        sorted_errors = sorted(
            self._error_type_counts.items(), key=lambda x: x[1], reverse=True
        )
        report.top_error_types = [
            {"error_type": et, "count": cnt}
            for et, cnt in sorted_errors[:10]
        ]

        # ROI 计算
        if self._total_heal_time_ms > 0 and self._total_saved_heals > 0:
            saved_seconds = self._total_saved_heals * self.MANUAL_FIX_BASELINE_SEC
            consumed_seconds = self._total_heal_time_ms / 1000
            report.roi_score = saved_seconds / max(consumed_seconds, 1)

        # 退化检测
        for stats in self._strategy_stats.values():
            if (stats.attempts >= self.MIN_SAMPLE_SIZE
                    and stats.success_rate < self.DEGRADED_RATE_THRESHOLD):
                report.degraded_strategies.append(stats.strategy)

        # 生成建议
        report.recommendations = self._generate_recommendations(report)

        return report

    def get_strategy_priority_suggestions(self) -> Dict[str, str]:
        """
        基于历史数据生成策略优先级调整建议。
        返回 {策略名: "raise"|"lower"|"keep"}
        """
        suggestions = {}
        for name, stats in self._strategy_stats.items():
            if stats.attempts < self.MIN_SAMPLE_SIZE:
                suggestions[name] = "keep"
            elif stats.success_rate > 0.8:
                suggestions[name] = "raise"
            elif stats.success_rate < 0.3:
                suggestions[name] = "lower"
            else:
                suggestions[name] = "keep"
        return suggestions

    def get_stats(self) -> dict:
        """简要统计，供 self_healing.py get_full_stats() 调用"""
        total_attempts = sum(s.attempts for s in self._strategy_stats.values())
        total_successes = sum(s.successes for s in self._strategy_stats.values())
        return {
            "total_heals": total_attempts,
            "total_success": total_successes,
            "success_rate": round(total_successes / max(total_attempts, 1), 3),
            "strategy_count": len(self._strategy_stats),
            "degraded": [
                s.strategy for s in self._strategy_stats.values()
                if s.attempts >= self.MIN_SAMPLE_SIZE and s.success_rate < self.DEGRADED_RATE_THRESHOLD
            ],
        }

    # ── 内部 ──

    def _generate_recommendations(self, report: HealingHealthReport) -> List[str]:
        """基于报告数据生成优化建议"""
        recs = []

        # 整体成功率低
        if report.total_heals > 10 and report.overall_success_rate < 0.5:
            recs.append(
                f"整体自愈成功率偏低 ({report.overall_success_rate:.0%})，"
                f"建议增加知识库覆盖或调整策略参数"
            )

        # 退化策略
        for strategy in report.degraded_strategies:
            stats = self._strategy_stats.get(strategy)
            if stats:
                recs.append(
                    f"策略 '{strategy}' 退化 (成功率 {stats.success_rate:.0%})，"
                    f"建议降低优先级或检查策略逻辑"
                )

        # ROI 低
        if report.roi_score > 0 and report.roi_score < 2:
            recs.append(
                f"自愈 ROI 偏低 ({report.roi_score:.1f}x)，"
                f"建议减少低效策略的尝试次数"
            )

        # 高成功率策略应提升优先级
        for stats in self._strategy_stats.values():
            if stats.attempts >= 5 and stats.success_rate > 0.8:
                recs.append(
                    f"策略 '{stats.strategy}' 表现优秀 "
                    f"(成功率 {stats.success_rate:.0%}, {stats.attempts} 次)，"
                    f"建议提升优先级"
                )

        # 高频错误类型无对应策略
        for et, cnt in sorted(self._error_type_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            has_strategy = any(
                et in s.error_types for s in self._strategy_stats.values()
            )
            if not has_strategy and cnt >= 3:
                recs.append(
                    f"高频错误类型 '{et}' ({cnt} 次) 无有效策略覆盖，"
                    f"建议新增针对性自愈策略"
                )

        return recs
