"""test_healing_analytics.py — 自愈效果度量与反馈闭环单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.healing_analytics import HealingAnalytics, HealingHealthReport, _StrategyStats


class TestStrategyStats(unittest.TestCase):

    def test_success_rate_no_attempts(self):
        s = _StrategyStats(strategy="x")
        self.assertEqual(s.success_rate, 0.0)

    def test_success_rate(self):
        s = _StrategyStats(strategy="x", attempts=4, successes=3)
        self.assertEqual(s.success_rate, 0.75)

    def test_avg_duration(self):
        s = _StrategyStats(strategy="x", attempts=2, total_duration_ms=1000)
        self.assertEqual(s.avg_duration_ms, 500.0)

    def test_to_dict_keys(self):
        d = _StrategyStats(strategy="x", attempts=1, successes=1).to_dict()
        for key in ("strategy", "attempts", "successes", "success_rate", "avg_duration_ms"):
            self.assertIn(key, d)


class TestRecordHeal(unittest.TestCase):

    def setUp(self):
        self.a = HealingAnalytics()

    def test_record_creates_strategy(self):
        self.a.record_heal("cdp_relocate", success=True, duration_ms=1000, error_type="selector_issue")
        stats = self.a.get_stats()
        self.assertEqual(stats["total_heals"], 1)
        self.assertEqual(stats["total_success"], 1)
        self.assertEqual(stats["strategy_count"], 1)

    def test_failure_recorded(self):
        self.a.record_heal("x", success=False, duration_ms=500)
        stats = self.a.get_stats()
        self.assertEqual(stats["total_heals"], 1)
        self.assertEqual(stats["total_success"], 0)

    def test_multiple_strategies(self):
        self.a.record_heal("a", success=True)
        self.a.record_heal("b", success=False)
        self.assertEqual(self.a.get_stats()["strategy_count"], 2)


class TestGenerateReport(unittest.TestCase):

    def setUp(self):
        self.a = HealingAnalytics()

    def test_empty_report(self):
        report = self.a.generate_report()
        self.assertIsInstance(report, HealingHealthReport)
        self.assertEqual(report.total_heals, 0)
        self.assertEqual(report.overall_success_rate, 0.0)

    def test_overall_success_rate(self):
        self.a.record_heal("a", success=True)
        self.a.record_heal("a", success=True)
        self.a.record_heal("a", success=False)
        report = self.a.generate_report()
        self.assertEqual(report.total_heals, 3)
        self.assertAlmostEqual(report.overall_success_rate, 2 / 3, places=3)

    def test_degraded_strategy_detected(self):
        # 5 次尝试仅 1 次成功 → 20% < 30% 退化阈值
        for i in range(5):
            self.a.record_heal("weak", success=(i == 0), error_type="selector_issue")
        report = self.a.generate_report()
        self.assertIn("weak", report.degraded_strategies)

    def test_no_degraded_below_min_sample(self):
        # 少于 MIN_SAMPLE_SIZE 不判退化
        self.a.record_heal("weak", success=False)
        report = self.a.generate_report()
        self.assertNotIn("weak", report.degraded_strategies)

    def test_roi_computed_when_saved(self):
        self.a.record_heal("a", success=True, duration_ms=1000)
        report = self.a.generate_report()
        self.assertGreater(report.roi_score, 0)

    def test_top_error_types_sorted(self):
        for _ in range(3):
            self.a.record_heal("a", success=True, error_type="selector_issue")
        self.a.record_heal("b", success=True, error_type="timeout_issue")
        report = self.a.generate_report()
        self.assertEqual(report.top_error_types[0]["error_type"], "selector_issue")
        self.assertEqual(report.top_error_types[0]["count"], 3)

    def test_report_to_dict(self):
        self.a.record_heal("a", success=True, duration_ms=100)
        d = self.a.generate_report().to_dict()
        for key in ("total_heals", "overall_success_rate", "roi_score", "recommendations"):
            self.assertIn(key, d)

    def test_recommendation_for_excellent_strategy(self):
        for _ in range(5):
            self.a.record_heal("great", success=True)
        report = self.a.generate_report()
        self.assertTrue(any("表现优秀" in r for r in report.recommendations))


class TestPrioritySuggestions(unittest.TestCase):

    def setUp(self):
        self.a = HealingAnalytics()

    def test_keep_below_min_sample(self):
        self.a.record_heal("x", success=True)
        self.assertEqual(self.a.get_strategy_priority_suggestions()["x"], "keep")

    def test_raise_for_high_success(self):
        for _ in range(5):
            self.a.record_heal("good", success=True)
        self.assertEqual(self.a.get_strategy_priority_suggestions()["good"], "raise")

    def test_lower_for_low_success(self):
        for i in range(5):
            self.a.record_heal("bad", success=(i == 0))
        self.assertEqual(self.a.get_strategy_priority_suggestions()["bad"], "lower")

    def test_keep_for_mid_success(self):
        # 5 次 3 成功 = 60%，介于 0.3~0.8
        for i in range(5):
            self.a.record_heal("mid", success=(i < 3))
        self.assertEqual(self.a.get_strategy_priority_suggestions()["mid"], "keep")


if __name__ == "__main__":
    unittest.main()
