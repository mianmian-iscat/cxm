"""test_evaluation.py — 五维评估与上线评级单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.evaluation import (
    EvaluationEngine, DimensionScore, LaunchRating, RatingLevel,
    EvaluationReport,
)


class TestDimensionScore(unittest.TestCase):

    def test_create_score(self):
        score = DimensionScore(name="功能正确性", weight=0.3, value=85.0)
        self.assertEqual(score.weighted_value, 25.5)

    def test_zero_weight(self):
        score = DimensionScore(name="test", weight=0.0, value=100.0)
        self.assertEqual(score.weighted_value, 0.0)


class TestEvaluationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = EvaluationEngine()

    def test_evaluate_all_dimensions(self):
        metrics = {
            "pass_rate": 0.95,
            "assertion_coverage": 0.88,
            "efficiency_ratio": 3.5,
            "coverage_domain": 0.7,
            "delivery_hours": 8,
            "retry_rate": 0.05,
            "self_heal_rate": 0.6,
            "fluctuation_rate": 0.02,
            "avg_duration_ms": 2000,
            "p95_duration_ms": 5000,
            "module_reuse_rate": 0.6,
            "config_ratio": 0.8,
        }
        report = self.engine.evaluate(metrics)
        self.assertEqual(len(report.dimensions), 5)
        self.assertGreater(report.total_score, 0)

    def test_evaluate_partial_metrics(self):
        metrics = {"pass_rate": 0.9, "avg_duration_ms": 3000}
        report = self.engine.evaluate(metrics)
        self.assertIsNotNone(report)

    def test_radar_data(self):
        metrics = {"pass_rate": 0.9}
        report = self.engine.evaluate(metrics)
        radar = report.to_radar_data()
        self.assertIn("dimensions", radar)
        self.assertEqual(len(radar["dimensions"]), 5)


class TestLaunchRating(unittest.TestCase):

    def test_rating_a(self):
        report = EvaluationReport(
            dimensions=[
                DimensionScore("功能正确性", 0.3, 95),
                DimensionScore("业务价值性", 0.3, 90),
                DimensionScore("执行稳定性", 0.2, 88),
                DimensionScore("性能效率", 0.1, 85),
                DimensionScore("可扩展性", 0.1, 80),
            ],
            total_score=90.5,
        )
        rating = LaunchRating.from_report(report)
        self.assertEqual(rating.level, RatingLevel.A)

    def test_rating_b(self):
        report = EvaluationReport(
            dimensions=[
                DimensionScore("功能正确性", 0.3, 80),
                DimensionScore("业务价值性", 0.3, 75),
                DimensionScore("执行稳定性", 0.2, 70),
                DimensionScore("性能效率", 0.1, 65),
                DimensionScore("可扩展性", 0.1, 60),
            ],
            total_score=74.0,
        )
        rating = LaunchRating.from_report(report)
        self.assertEqual(rating.level, RatingLevel.B)

    def test_rating_c(self):
        report = EvaluationReport(
            dimensions=[
                DimensionScore("功能正确性", 0.3, 60),
                DimensionScore("业务价值性", 0.3, 55),
                DimensionScore("执行稳定性", 0.2, 50),
                DimensionScore("性能效率", 0.1, 45),
                DimensionScore("可扩展性", 0.1, 40),
            ],
            total_score=54.0,
        )
        rating = LaunchRating.from_report(report)
        self.assertEqual(rating.level, RatingLevel.C)

    def test_rating_d(self):
        report = EvaluationReport(
            dimensions=[],
            total_score=30.0,
        )
        rating = LaunchRating.from_report(report)
        self.assertEqual(rating.level, RatingLevel.D)

    def test_rating_to_dict(self):
        report = EvaluationReport(dimensions=[], total_score=95.0)
        rating = LaunchRating.from_report(report)
        d = rating.to_dict()
        self.assertIn("level", d)
        self.assertIn("score", d)


if __name__ == "__main__":
    unittest.main()
