"""
budget_guard.py — Token 预算守卫 (Gap 2.2)

主Agent控制面子系统。职责：
- 追踪各组件 Token 消耗
- 超限时返回降级建议（Plan 模式）
- 生成 Token 分布报告

使用方式：
    from core.budget_guard import BudgetGuard
    guard = BudgetGuard(limit=1_000_000)
    guard.record_usage("llm_plan", 50000)
    status = guard.check_budget()
    if status["degraded"]:
        # 降级为 Plan 模式
"""

from dataclasses import dataclass
from typing import  Dict, List

@dataclass
class BudgetStatus:
    """预算状态"""
    used: int
    limit: int
    remaining: int
    degraded: bool
    usage_pct: float
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "used": self.used, "limit": self.limit,
            "remaining": self.remaining, "degraded": self.degraded,
            "usagePct": round(self.usage_pct, 4),
            "suggestion": self.suggestion,
        }

class BudgetGuard:
    """
    Token 预算守卫。
    追踪各组件消耗，超限时建议降级。
    """

    def __init__(self, limit: int = 1_000_000):
        """
        Args:
            limit: Token 预算上限（默认 1M）
        """
        self._limit = limit
        self._usage: Dict[str, int] = {}  # component -> tokens
        self._history: List[dict] = []

    def record_usage(self, component: str, tokens: int):
        """
        记录某组件的 Token 消耗。

        Args:
            component: 组件名（如 "llm_plan", "step_click", "assert"）
            tokens: Token 数量
        """
        self._usage[component] = self._usage.get(component, 0) + tokens
        self._history.append({"component": component, "tokens": tokens})

    def check_budget(self) -> BudgetStatus:
        """
        检查当前预算状态。

        Returns:
            BudgetStatus
        """
        total = sum(self._usage.values())
        remaining = max(0, self._limit - total)
        pct = total / self._limit if self._limit > 0 else 0
        degraded = total >= self._limit

        suggestion = ""
        if degraded:
            suggestion = "Token 预算已耗尽，建议降级为 Plan 模式（只规划不执行）"
        elif pct > 0.8:
            suggestion = f"Token 已使用 {pct:.0%}，建议精简输出"
        elif pct > 0.5:
            suggestion = f"Token 已使用 {pct:.0%}"

        return BudgetStatus(
            used=total, limit=self._limit,
            remaining=remaining, degraded=degraded,
            usage_pct=pct, suggestion=suggestion,
        )

    def get_report(self) -> dict:
        """
        生成 Token 分布报告。

        Returns:
            {total, limit, by_component, top_consumers}
        """
        total = sum(self._usage.values())
        # 按消耗排序
        sorted_components = sorted(self._usage.items(), key=lambda x: x[1], reverse=True)

        return {
            "total": total,
            "limit": self._limit,
            "remaining": max(0, self._limit - total),
            "usage_pct": round(total / self._limit, 4) if self._limit > 0 else 0,
            "by_component": dict(sorted_components),
            "top_consumers": [
                {"component": c, "tokens": t, "pct": round(t / total, 4) if total > 0 else 0}
                for c, t in sorted_components[:5]
            ],
        }

    def estimate_remaining_steps(self, avg_tokens_per_step: int = 5000) -> int:
        """
        估算剩余 Token 可执行的步骤数。

        Args:
            avg_tokens_per_step: 每步平均 Token 消耗

        Returns:
            预计可执行步骤数
        """
        status = self.check_budget()
        if avg_tokens_per_step <= 0:
            return 0
        return max(0, status.remaining // avg_tokens_per_step)
