"""
circuit_breaker.py — 熔断器 (Gap 2.4)

智能自愈子系统。职责：
- 三态状态机：CLOSED / OPEN / HALF_OPEN
- 连续失败或失败率超阈值时触发熔断
- 支持试探恢复

使用方式：
    from core.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=3, failure_rate_threshold=0.4)
    cb.record_result("pass")
    if cb.should_break():
        # 熔断，停止执行
"""

from enum import Enum
from typing import List

class CircuitState(Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 试探恢复

class CircuitBreaker:
    """
    熔断器。
    触发条件：连续 N 个 fail/error 或最近 M 步失败率 > 阈值。
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        failure_rate_threshold: float = 0.4,
        window_size: int = 10,
        half_open_max: int = 1,
    ):
        """
        Args:
            failure_threshold: 连续失败次数阈值
            failure_rate_threshold: 失败率阈值（0-1）
            window_size: 滑动窗口大小（计算失败率）
            half_open_max: HALF_OPEN 状态下允许的最大试探次数
        """
        self._state = CircuitState.CLOSED
        self._failure_threshold = failure_threshold
        self._failure_rate_threshold = failure_rate_threshold
        self._window_size = window_size
        self._half_open_max = half_open_max
        self._results: List[str] = []  # "pass" / "fail" / "error" / "skip"
        self._consecutive_failures = 0
        self._half_open_attempts = 0
        self._last_trigger_reason = ""

    # ── 记录 ──

    def record_result(self, status: str) -> CircuitState:
        """
        记录一步结果，更新状态机。

        Args:
            status: "pass" / "fail" / "error" / "skip"

        Returns:
            当前 CircuitState
        """
        self._results.append(status)

        if status in ("fail", "error"):
            self._consecutive_failures += 1
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_attempts += 1
                if self._half_open_attempts >= self._half_open_max:
                    self._state = CircuitState.OPEN
                    self._last_trigger_reason = "HALF_OPEN 试探失败"
        else:
            self._consecutive_failures = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._half_open_attempts = 0

        return self._state

    # ── 判断 ──

    def should_break(self) -> bool:
        """
        判断是否应触发熔断。

        Returns:
            True 表示应停止执行
        """
        if self._state == CircuitState.OPEN:
            return True

        # 连续失败检查
        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._last_trigger_reason = f"连续失败 {self._consecutive_failures} 次"
            return True

        # 失败率检查（滑动窗口）
        if len(self._results) >= self._window_size:
            window = self._results[-self._window_size:]
            failures = sum(1 for r in window if r in ("fail", "error"))
            rate = failures / len(window)
            if rate > self._failure_rate_threshold:
                self._state = CircuitState.OPEN
                self._last_trigger_reason = f"失败率 {rate:.0%} > {self._failure_rate_threshold:.0%}"
                return True

        return False

    def try_half_open(self) -> bool:
        """
        尝试从 OPEN 进入 HALF_OPEN（外部调用，如等待一段时间后）。

        Returns:
            是否成功进入 HALF_OPEN
        """
        if self._state == CircuitState.OPEN:
            self._state = CircuitState.HALF_OPEN
            self._half_open_attempts = 0
            return True
        return False

    def reset(self):
        """重置为 CLOSED 状态"""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._half_open_attempts = 0
        self._results.clear()
        self._last_trigger_reason = ""

    # ── 查询 ──

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self._results if r in ("fail", "error"))

    @property
    def failure_rate(self) -> float:
        if not self._results:
            return 0.0
        window = self._results[-self._window_size:]
        return sum(1 for r in window if r in ("fail", "error")) / len(window)

    def get_report(self) -> dict:
        """生成报告"""
        return {
            "state": self._state.value,
            "total_results": len(self._results),
            "failure_count": self.failure_count,
            "failure_rate": round(self.failure_rate, 4),
            "consecutive_failures": self._consecutive_failures,
            "last_trigger_reason": self._last_trigger_reason,
        }
