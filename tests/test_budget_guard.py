"""test_budget_guard.py — Token 预算守卫单元测试 (Gap 2.2)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.budget_guard import BudgetGuard, BudgetStatus


class TestBudgetGuard(unittest.TestCase):

    def test_initial_state(self):
        guard = BudgetGuard(limit=100000)
        status = guard.check_budget()
        self.assertEqual(status.used, 0)
        self.assertEqual(status.remaining, 100000)
        self.assertFalse(status.degraded)

    def test_record_usage(self):
        guard = BudgetGuard(limit=100000)
        guard.record_usage("llm_plan", 50000)
        status = guard.check_budget()
        self.assertEqual(status.used, 50000)
        self.assertEqual(status.remaining, 50000)
        self.assertFalse(status.degraded)

    def test_multiple_components(self):
        guard = BudgetGuard(limit=100000)
        guard.record_usage("llm_plan", 30000)
        guard.record_usage("step_click", 20000)
        guard.record_usage("assert", 10000)
        status = guard.check_budget()
        self.assertEqual(status.used, 60000)

    def test_accumulate_same_component(self):
        guard = BudgetGuard(limit=100000)
        guard.record_usage("llm_plan", 30000)
        guard.record_usage("llm_plan", 20000)
        status = guard.check_budget()
        self.assertEqual(status.used, 50000)

    def test_degraded_on_exhaustion(self):
        guard = BudgetGuard(limit=100)
        guard.record_usage("llm_plan", 150)
        status = guard.check_budget()
        self.assertTrue(status.degraded)
        self.assertEqual(status.remaining, 0)
        self.assertIn("降级", status.suggestion)

    def test_warning_at_80_percent(self):
        guard = BudgetGuard(limit=100)
        guard.record_usage("step", 85)
        status = guard.check_budget()
        self.assertFalse(status.degraded)
        self.assertIn("85%", status.suggestion)


class TestBudgetReport(unittest.TestCase):

    def test_get_report(self):
        guard = BudgetGuard(limit=100000)
        guard.record_usage("llm_plan", 50000)
        guard.record_usage("step_click", 20000)
        report = guard.get_report()
        self.assertEqual(report["total"], 70000)
        self.assertEqual(report["limit"], 100000)
        self.assertEqual(len(report["by_component"]), 2)
        self.assertEqual(report["top_consumers"][0]["component"], "llm_plan")

    def test_empty_report(self):
        guard = BudgetGuard(limit=100000)
        report = guard.get_report()
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["top_consumers"], [])


class TestEstimate(unittest.TestCase):

    def test_estimate_remaining_steps(self):
        guard = BudgetGuard(limit=100000)
        guard.record_usage("step", 50000)
        remaining = guard.estimate_remaining_steps(avg_tokens_per_step=5000)
        self.assertEqual(remaining, 10)

    def test_estimate_zero_avg(self):
        guard = BudgetGuard(limit=100000)
        remaining = guard.estimate_remaining_steps(avg_tokens_per_step=0)
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
