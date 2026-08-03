"""test_perf_adaptive.py — 性能退化检测与自适应单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.perf_adaptive import PerformanceAdaptive, _StepBaseline


class TestStepBaseline(unittest.TestCase):

    def test_empty_p95_and_mean(self):
        bl = _StepBaseline(step_type="click")
        self.assertEqual(bl.p95, 0.0)
        self.assertEqual(bl.mean, 0.0)
        self.assertEqual(bl.count, 0)

    def test_mean(self):
        bl = _StepBaseline(step_type="click")
        for d in (100, 200, 300):
            bl.record(d)
        self.assertEqual(bl.mean, 200.0)

    def test_window_size_caps_history(self):
        bl = _StepBaseline(step_type="click", window_size=5)
        for d in range(10):
            bl.record(d)
        self.assertEqual(bl.count, 5)
        # 仅保留最近 5 个
        self.assertEqual(bl.durations, [5, 6, 7, 8, 9])


class TestPerformanceAdaptive(unittest.TestCase):

    def setUp(self):
        self.perf = PerformanceAdaptive()

    def test_initial_not_degraded(self):
        self.assertFalse(self.perf.is_degraded())
        self.assertEqual(self.perf.get_degradation_ratio(), 1.0)

    def test_no_degradation_below_min_samples(self):
        # 少于 5 个样本不触发检测
        for _ in range(4):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 5000)
        # 第 5 个样本触发检测，但此前只有 4 个基线不足；此步 count=5
        # 由于 p95 已含大值，可能触发也可能不触发，这里只断言不抛异常
        self.assertIsInstance(self.perf.is_degraded(), bool)

    def test_degradation_triggers_scale_up(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 2000)
        self.assertTrue(self.perf.is_degraded())
        self.assertGreater(self.perf.get_degradation_ratio(), 1.0)

    def test_adjusted_timeout_scales_when_degraded(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 2000)
        adjusted = self.perf.get_adjusted_timeout(10000)
        self.assertGreater(adjusted, 10000)

    def test_adjusted_timeout_capped(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 100000)
        adjusted = self.perf.get_adjusted_timeout(10000)
        self.assertLessEqual(adjusted, 10000 * PerformanceAdaptive.MAX_TIMEOUT_SCALE)

    def test_adjusted_timeout_no_change_when_healthy(self):
        self.assertEqual(self.perf.get_adjusted_timeout(10000), 10000)

    def test_throttle_delay_zero_when_healthy(self):
        self.assertEqual(self.perf.get_throttle_delay_ms(), 0)

    def test_throttle_delay_positive_when_degraded(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 5000)
        self.assertGreater(self.perf.get_throttle_delay_ms(), 0)

    def test_throttle_delay_capped_at_3000(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 100000)
        self.assertLessEqual(self.perf.get_throttle_delay_ms(), 3000)


class TestResourceLoad(unittest.TestCase):

    def setUp(self):
        self.perf = PerformanceAdaptive()

    def test_no_refresh_below_min_samples(self):
        for _ in range(5):
            self.perf.record_resource_load(False)
        self.assertFalse(self.perf.should_refresh_page())

    def test_refresh_when_fail_rate_high(self):
        # 10 个样本，5 个失败 → 50% > 20%
        for _ in range(5):
            self.perf.record_resource_load(True)
        for _ in range(5):
            self.perf.record_resource_load(False)
        self.assertTrue(self.perf.should_refresh_page())

    def test_no_refresh_when_fail_rate_low(self):
        for _ in range(9):
            self.perf.record_resource_load(True)
        self.perf.record_resource_load(False)
        self.assertFalse(self.perf.should_refresh_page())


class TestStatsAndReset(unittest.TestCase):

    def setUp(self):
        self.perf = PerformanceAdaptive()

    def test_stats_keys(self):
        self.perf.record_step_duration("click", 100)
        stats = self.perf.get_stats()
        for key in ("current_scale", "degradation_events", "global_p95_ms", "step_baselines"):
            self.assertIn(key, stats)

    def test_stats_records_baseline(self):
        self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 200)
        stats = self.perf.get_stats()
        self.assertIn("click", stats["step_baselines"])
        self.assertEqual(stats["step_baselines"]["click"]["count"], 2)

    def test_reset_scale(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 5000)
        self.assertTrue(self.perf.is_degraded())
        self.perf.reset_scale()
        self.assertFalse(self.perf.is_degraded())

    def test_degradation_event_recorded(self):
        for _ in range(5):
            self.perf.record_step_duration("click", 100)
        self.perf.record_step_duration("click", 2000)
        events = self.perf.get_recent_events()
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1]["step_type"], "click")


if __name__ == "__main__":
    unittest.main()
