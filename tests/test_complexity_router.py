"""test_complexity_router.py — 复杂度路由器单元测试 (Gap 2.2)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.complexity_router import ComplexityRouter, ComplexityLevel


class TestComplexityRouter(unittest.TestCase):

    def setUp(self):
        self.router = ComplexityRouter()

    def test_simple_no_steps(self):
        result = self.router.route({})
        self.assertEqual(result["level"], "simple")
        self.assertEqual(result["suggested_mode"], "direct")
        self.assertFalse(result["parallel_hint"])

    def test_simple_few_steps(self):
        steps = [{"type": "click"} for _ in range(5)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "simple")
        self.assertEqual(result["suggested_mode"], "direct")

    def test_medium_many_steps(self):
        steps = [{"type": "click"} for _ in range(20)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "medium")

    def test_medium_with_pipeline(self):
        result = self.router.route({"steps": [{"type": "click"}], "pipeline": {"stages": []}})
        self.assertEqual(result["level"], "medium")
        self.assertEqual(result["suggested_mode"], "pipeline")

    def test_medium_with_realtime_asserts(self):
        steps = [{"type": "click", "realtime_asserts": [{"assert": "visible"}]}]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "medium")

    def test_complex_over_30_steps(self):
        steps = [{"type": "click"} for _ in range(35)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "complex")
        self.assertEqual(result["suggested_mode"], "multi_agent")
        self.assertTrue(result["parallel_hint"])

    def test_complex_pipeline_llm_multipage(self):
        steps = [
            {"type": "navigate"}, {"type": "navigate"},
        ] + [{"type": "click"} for _ in range(5)]
        result = self.router.route({
            "steps": steps,
            "pipeline": {"stages": []},
            "llm": {"calls": [{"step": "plan"}]},
        })
        self.assertEqual(result["level"], "complex")

    def test_step_count_in_result(self):
        steps = [{"type": "click"} for _ in range(7)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["step_count"], 7)

    def test_exactly_10_steps_is_simple(self):
        steps = [{"type": "click"} for _ in range(10)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "simple")

    def test_exactly_11_steps_is_medium(self):
        steps = [{"type": "click"} for _ in range(11)]
        result = self.router.route({"steps": steps})
        self.assertEqual(result["level"], "medium")


if __name__ == "__main__":
    unittest.main()
