"""test_orchestrator.py — 主Agent控制面框架单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.orchestrator import (
    Orchestrator, ComplexityLevel, BudgetController,
    SubAgent, AgentRegistry,
)
from core.circuit_breaker import CircuitBreaker


class TestComplexityJudge(unittest.TestCase):

    def setUp(self):
        self.orch = Orchestrator()

    def test_simple_complexity(self):
        level = self.orch.judge_complexity({"steps": 1, "tools": 1})
        self.assertEqual(level, ComplexityLevel.SIMPLE)

    def test_medium_complexity(self):
        level = self.orch.judge_complexity({"steps": 5, "tools": 3})
        self.assertEqual(level, ComplexityLevel.MEDIUM)

    def test_complex_complexity(self):
        level = self.orch.judge_complexity({"steps": 15, "tools": 8, "conditions": 5})
        self.assertEqual(level, ComplexityLevel.COMPLEX)

    def test_default_is_simple(self):
        level = self.orch.judge_complexity({})
        self.assertEqual(level, ComplexityLevel.SIMPLE)


class TestBudgetController(unittest.TestCase):

    def test_within_budget(self):
        bc = BudgetController(max_tokens=1000000)
        bc.consume(500000)
        self.assertTrue(bc.within_budget)
        self.assertEqual(bc.used_tokens, 500000)

    def test_exceed_budget(self):
        bc = BudgetController(max_tokens=100)
        bc.consume(200)
        self.assertFalse(bc.within_budget)

    def test_remaining(self):
        bc = BudgetController(max_tokens=1000)
        bc.consume(300)
        self.assertEqual(bc.remaining, 700)

    def test_reset(self):
        bc = BudgetController(max_tokens=1000)
        bc.consume(500)
        bc.reset()
        self.assertEqual(bc.used_tokens, 0)


class TestCircuitBreaker(unittest.TestCase):

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, failure_rate_threshold=0.4)
        self.assertFalse(cb.should_break())

    def test_opens_after_consecutive_failures(self):
        cb = CircuitBreaker(failure_threshold=3, failure_rate_threshold=1.0)
        for _ in range(3):
            cb.record_result("fail")
        self.assertTrue(cb.should_break())

    def test_opens_on_failure_rate(self):
        cb = CircuitBreaker(failure_threshold=100, failure_rate_threshold=0.4, window_size=7)
        for _ in range(3):
            cb.record_result("pass")
        for _ in range(4):
            cb.record_result("fail")
        # 4 failures out of 7 = 57% > 40%
        self.assertTrue(cb.should_break())

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_result("fail")
        cb.reset()
        self.assertFalse(cb.should_break())


class TestAgentRegistry(unittest.TestCase):

    def test_register_and_get(self):
        registry = AgentRegistry()

        class DummyAgent(SubAgent):
            name = "dummy"
            def execute(self, task):
                return {"status": "ok"}

        registry.register(DummyAgent())
        agent = registry.get("dummy")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.execute({})["status"], "ok")

    def test_get_nonexistent(self):
        registry = AgentRegistry()
        self.assertIsNone(registry.get("nope"))

    def test_list_agents(self):
        registry = AgentRegistry()

        class A(SubAgent):
            name = "a"
            def execute(self, task):
                return {}

        class B(SubAgent):
            name = "b"
            def execute(self, task):
                return {}

        registry.register(A())
        registry.register(B())
        names = registry.list_agents()
        self.assertEqual(sorted(names), ["a", "b"])


class TestConcurrencyControl(unittest.TestCase):

    def test_acquire_release(self):
        orch = Orchestrator(max_concurrency=2)
        self.assertTrue(orch.acquire_slot())
        self.assertTrue(orch.acquire_slot())
        self.assertFalse(orch.acquire_slot())  # full
        orch.release_slot()
        self.assertTrue(orch.acquire_slot())

    def test_queue_tracking(self):
        orch = Orchestrator(max_concurrency=1)
        orch.acquire_slot()
        self.assertEqual(orch.active_count, 1)
        self.assertEqual(orch.queued_count, 0)


if __name__ == "__main__":
    unittest.main()
