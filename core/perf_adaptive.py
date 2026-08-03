"""
perf_adaptive.py — 性能退化检测与自适应 (维度8)

跟踪执行耗时并在性能退化时自动调整策略：
- 滑动窗口 P95 耗时追踪
- 性能退化时自动放大 timeout
- 资源加载失败率监控
- 步骤间自适应降速

使用方式：
    from core.perf_adaptive import PerformanceAdaptive
    perf = PerformanceAdaptive()
    perf.record_step_duration("click", 2500)
    adjusted_timeout = perf.get_adjusted_timeout(base_timeout_ms=10000)
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class _StepBaseline:
    """单步骤类型性能基线"""
    step_type: str
    durations: list = field(default_factory=list)
    window_size: int = 20

    def record(self, duration_ms: int):
        self.durations.append(duration_ms)
        if len(self.durations) > self.window_size:
            self.durations = self.durations[-self.window_size:]

    @property
    def p95(self) -> float:
        if not self.durations:
            return 0.0
        s = sorted(self.durations)
        return s[int(len(s) * 0.95) - 1] if s else 0.0

    @property
    def mean(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 0.0

    @property
    def count(self) -> int:
        return len(self.durations)


class PerformanceAdaptive:
    """
    性能退化检测与自适应调速引擎。

    核心能力：
    1. 每步耗时追踪 → 滑动窗口 P95
    2. P95 超过基线 2x 时触发 timeout 自动放大
    3. 资源加载失败率过高时触发页面刷新建议
    4. 全局执行速度自适应降速
    """

    # 退化倍数阈值（当前 P95 / 历史 P95）
    DEGRADATION_RATIO = 2.0
    # timeout 放大倍数
    TIMEOUT_SCALE_FACTOR = 2.0
    # 最大 timeout 放大倍数
    MAX_TIMEOUT_SCALE = 4.0
    # 资源失败率阈值（超过此值触发刷新建议）
    RESOURCE_FAIL_RATE_THRESHOLD = 0.2

    def __init__(self):
        self._step_baselines: Dict[str, _StepBaseline] = {}
        self._global_durations: List[int] = []
        self._resource_stats = {"total": 0, "failed": 0}
        self._degradation_events: list = []
        self._current_scale = 1.0

    # ── 记录 ──

    def record_step_duration(self, step_type: str, duration_ms: int):
        """记录一步执行耗时"""
        if step_type not in self._step_baselines:
            self._step_baselines[step_type] = _StepBaseline(step_type=step_type)
        self._step_baselines[step_type].record(duration_ms)
        self._global_durations.append(duration_ms)

        # 实时检测退化
        self._check_degradation(step_type, duration_ms)

    def record_resource_load(self, success: bool):
        """记录一次资源加载（图片/JS/CSS）"""
        self._resource_stats["total"] += 1
        if not success:
            self._resource_stats["failed"] += 1

    # ── 查询 ──

    def get_adjusted_timeout(self, base_timeout_ms: int, step_type: str = "") -> int:
        """
        获取自适应调整后的 timeout（毫秒）。

        当检测到性能退化时，自动放大 timeout。

        Args:
            base_timeout_ms: 原始 timeout
            step_type: 步骤类型（可选，用于按类型调整）

        Returns:
            调整后的 timeout（毫秒）
        """
        scale = self._current_scale

        # 按步骤类型微调
        if step_type and step_type in self._step_baselines:
            baseline = self._step_baselines[step_type]
            if baseline.count >= 5:
                # 如果该类型最近耗时明显增大，额外放大
                recent = baseline.durations[-3:] if len(baseline.durations) >= 3 else baseline.durations
                recent_mean = sum(recent) / len(recent) if recent else 0
                if recent_mean > baseline.mean * 1.5:
                    scale = min(scale * 1.5, self.MAX_TIMEOUT_SCALE)

        return int(base_timeout_ms * min(scale, self.MAX_TIMEOUT_SCALE))

    def should_refresh_page(self) -> bool:
        """
        判断是否需要建议页面刷新（资源加载失败率过高时）。
        """
        total = self._resource_stats["total"]
        if total < 10:
            return False
        fail_rate = self._resource_stats["failed"] / total
        return fail_rate > self.RESOURCE_FAIL_RATE_THRESHOLD

    def get_throttle_delay_ms(self) -> int:
        """
        获取建议的步骤间降速延迟（毫秒）。
        退化时增加步骤间等待，给浏览器恢复时间。
        """
        if self._current_scale <= 1.0:
            return 0
        # 每 0.5x 退化增加 500ms 延迟
        extra_scale = self._current_scale - 1.0
        return min(int(extra_scale * 1000), 3000)

    def is_degraded(self) -> bool:
        """当前是否处于性能退化状态"""
        return self._current_scale > 1.0

    def get_degradation_ratio(self) -> float:
        """当前退化倍数"""
        return self._current_scale

    # ── 报告 ──

    def get_stats(self) -> dict:
        baselines = {}
        for stype, bl in self._step_baselines.items():
            baselines[stype] = {
                "count": bl.count,
                "mean_ms": round(bl.mean, 1),
                "p95_ms": round(bl.p95, 1),
            }

        global_p95 = 0.0
        if self._global_durations:
            s = sorted(self._global_durations)
            global_p95 = s[int(len(s) * 0.95) - 1] if s else 0.0

        return {
            "current_scale": round(self._current_scale, 2),
            "degradation_events": len(self._degradation_events),
            "global_p95_ms": round(global_p95, 1),
            "step_baselines": baselines,
            "resource_fail_rate": (
                round(self._resource_stats["failed"] / max(self._resource_stats["total"], 1), 3)
            ),
            "recent_events": self._degradation_events[-5:],
        }

    def get_recent_events(self, limit: int = 10) -> list:
        return self._degradation_events[-limit:]

    # ── 内部 ──

    def _check_degradation(self, step_type: str, duration_ms: int):
        """检测单步是否触发性能退化"""
        baseline = self._step_baselines.get(step_type)
        if not baseline or baseline.count < 5:
            return

        p95 = baseline.p95
        if p95 <= 0:
            return

        # 当前耗时是否超过 P95 的 DEGRADATION_RATIO 倍
        if duration_ms > p95 * self.DEGRADATION_RATIO:
            # 计算新的缩放因子
            ratio = duration_ms / p95
            new_scale = min(1.0 + (ratio - 1.0) * 0.5, self.MAX_TIMEOUT_SCALE)
            if new_scale > self._current_scale:
                old_scale = self._current_scale
                self._current_scale = new_scale
                self._degradation_events.append({
                    "step_type": step_type,
                    "duration_ms": duration_ms,
                    "p95_ms": round(p95, 1),
                    "ratio": round(ratio, 2),
                    "old_scale": round(old_scale, 2),
                    "new_scale": round(new_scale, 2),
                    "timestamp": time.time(),
                })

        # 全局窗口检测：最近 5 步均值 vs 全局 P95
        if len(self._global_durations) >= 10:
            recent_5 = self._global_durations[-5:]
            recent_mean = sum(recent_5) / len(recent_5)
            global_sorted = sorted(self._global_durations[:-5])
            if global_sorted:
                global_p95 = global_sorted[int(len(global_sorted) * 0.95) - 1]
                if global_p95 > 0 and recent_mean > global_p95 * self.DEGRADATION_RATIO:
                    self._current_scale = min(self._current_scale * 1.2, self.MAX_TIMEOUT_SCALE)

    def reset_scale(self):
        """重置缩放因子（例如页面刷新后）"""
        self._current_scale = 1.0
        self._resource_stats = {"total": 0, "failed": 0}
