"""test_quality_scorer.py — 五维评估与上线评级单元测试 (Gap 2.6)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quality_scorer import QualityScorer, QualityReport


class TestQualityScorerCorrectness(unittest.TestCase):

    def setUp(self):
        self.scorer = QualityScorer()

    def test_all_pass_high_correctness(self):
        steps = [{"status": "pass"} for _ in range(10)]
        assertion = {"total": 10, "passed": 10}
        report = self.scorer.score({}, assertion, {}, steps)
        self.assertGreaterEqual(report.dimensions["correctness"], 90)

    def test_half_pass_correctness(self):
        steps = [{"status": "pass"} for _ in range(5)] + [{"status": "fail"} for _ in range(5)]
        assertion = {"total": 10, "passed": 5}
        report = self.scorer.score({}, assertion, {}, steps)
        self.assertGreater(report.dimensions["correctness"], 40)
        self.assertLess(report.dimensions["correctness"], 60)

    def test_no_assertions_defaults_80(self):
        report = self.scorer.score({}, {}, {}, [])
        self.assertEqual(report.dimensions["correctness"], 80.0)


class TestQualityScorerBusinessValue(unittest.TestCase):

    def setUp(self):
        self.scorer = QualityScorer(manual_baseline_ms=200000)

    def test_fast_execution_high_value(self):
        metrics = {"core_metrics": {"avg_duration_ms": 50000}}
        evidence = {"evidenceCount": 10, "validatedCount": 8}
        report = self.scorer.score(metrics, {}, evidence, [])
        self.assertGreater(report.dimensions["business_value"], 70)

    def test_no_evidence_lower_value(self):
        metrics = {"core_metrics": {"avg_duration_ms": 50000}}
        report = self.scorer.score(metrics, {}, {}, [])
        # efficiency high but evidence_score low
        self.assertGreater(report.dimensions["business_value"], 50)


class TestQualityScorerStability(unittest.TestCase):

    def setUp(self):
        self.scorer = QualityScorer()

    def test_no_errors_high_stability(self):
        metrics = {"core_metrics": {"false_positive_rate": 0.0}}
        evidence = {"evidenceCount": 10, "errorCount": 0}
        report = self.scorer.score(metrics, {}, evidence, [])
        self.assertGreaterEqual(report.dimensions["stability"], 90)

    def test_high_false_positive_low_stability(self):
        metrics = {"core_metrics": {"false_positive_rate": 0.5}}
        evidence = {"evidenceCount": 10, "errorCount": 5}
        report = self.scorer.score(metrics, {}, evidence, [])
        self.assertLess(report.dimensions["stability"], 60)


class TestQualityScorerPerformance(unittest.TestCase):

    def setUp(self):
        self.scorer = QualityScorer()

    def test_fast_performance(self):
        metrics = {"core_metrics": {"avg_duration_ms": 30000}}
        report = self.scorer.score(metrics, {}, {}, [])
        self.assertEqual(report.dimensions["performance"], 100)

    def test_slow_performance(self):
        metrics = {"core_metrics": {"avg_duration_ms": 180000}}
        report = self.scorer.score(metrics, {}, {}, [])
        self.assertLess(report.dimensions["performance"], 50)


class TestRating(unittest.TestCase):

    def setUp(self):
        self.scorer = QualityScorer()

    def test_rating_A(self):
        # All dimensions >= 80
        steps = [{"status": "pass"} for _ in range(10)]
        assertion = {"total": 10, "passed": 10}
        metrics = {"core_metrics": {"avg_duration_ms": 30000, "false_positive_rate": 0.0}}
        evidence = {"evidenceCount": 10, "validatedCount": 9, "errorCount": 0}
        from core.knowledge_base import CompletenessReport
        completeness = CompletenessReport(
            total_topics=5, covered_topics=5, coverage_pct=100.0
        )
        report = self.scorer.score(metrics, assertion, evidence, steps, completeness_report=completeness)
        self.assertEqual(report.rating, "A")

    def test_rating_D(self):
        # correctness < 60
        steps = [{"status": "fail"} for _ in range(8)] + [{"status": "pass"} for _ in range(2)]
        assertion = {"total": 10, "passed": 2}
        report = self.scorer.score({}, assertion, {}, steps)
        self.assertEqual(report.rating, "D")


class TestQualityReport(unittest.TestCase):

    def test_to_dict(self):
        report = QualityReport(
            dimensions={"correctness": 85.0, "business_value": 70.0, "stability": 90.0, "performance": 80.0, "extensibility": 75.0},
            weights={"correctness": 0.3, "business_value": 0.3, "stability": 0.2, "performance": 0.1, "extensibility": 0.1},
            total_score=81.0,
            rating="B",
            rating_reason="test reason",
        )
        d = report.to_dict()
        self.assertEqual(d["totalScore"], 81.0)
        self.assertEqual(d["rating"], "B")
        self.assertEqual(d["ratingReason"], "test reason")
        self.assertIn("correctness", d["dimensions"])


if __name__ == "__main__":
    unittest.main()
