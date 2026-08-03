"""test_circuit_breaker.py — 熔断器单元测试 (Gap 2.4)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerInitial(unittest.TestCase):

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertFalse(cb.should_break())
        self.assertEqual(cb.failure_count, 0)
        self.assertEqual(cb.failure_rate, 0.0)

    def test_pass_keeps_closed(self):
        cb = CircuitBreaker()
        cb.record_result("pass")
        cb.record_result("pass")
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertFalse(cb.should_break())


class TestConsecutiveFailureTrigger(unittest.TestCase):

    def test_three_consecutive_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_result("fail")
        cb.record_result("fail")
        self.assertFalse(cb.should_break())
        cb.record_result("fail")
        self.assertTrue(cb.should_break())
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_error_counts_as_failure(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_result("error")
        cb.record_result("fail")
        cb.record_result("error")
        self.assertTrue(cb.should_break())

    def test_pass_resets_consecutive(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_result("fail")
        cb.record_result("fail")
        cb.record_result("pass")
        cb.record_result("fail")
        self.assertFalse(cb.should_break())
        self.assertEqual(cb._consecutive_failures, 1)


class TestFailureRateTrigger(unittest.TestCase):

    def test_high_failure_rate_triggers(self):
        cb = CircuitBreaker(failure_threshold=10, failure_rate_threshold=0.4, window_size=10)
        # 5 failures in 10 steps = 50% > 40%
        for _ in range(5):
            cb.record_result("pass")
        for _ in range(5):
            cb.record_result("fail")
        self.assertTrue(cb.should_break())

    def test_low_failure_rate_no_trigger(self):
        cb = CircuitBreaker(failure_threshold=10, failure_rate_threshold=0.4, window_size=10)
        # 3 failures in 10 steps = 30% < 40%
        for _ in range(7):
            cb.record_result("pass")
        for _ in range(3):
            cb.record_result("fail")
        self.assertFalse(cb.should_break())

    def test_skip_not_failure(self):
        cb = CircuitBreaker(failure_threshold=10, failure_rate_threshold=0.4, window_size=10)
        for _ in range(5):
            cb.record_result("pass")
        for _ in range(3):
            cb.record_result("skip")
        for _ in range(2):
            cb.record_result("fail")
        # 2 failures in 10 = 20%
        self.assertFalse(cb.should_break())


class TestHalfOpen(unittest.TestCase):

    def test_try_half_open_from_open(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_result("fail")
        cb.record_result("fail")
        cb.record_result("fail")
        cb.should_break()  # triggers OPEN
        result = cb.try_half_open()
        self.assertTrue(result)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_half_open_pass_returns_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_result("fail")
        cb.record_result("fail")
        cb.record_result("fail")
        cb.should_break()
        cb.try_half_open()
        cb.record_result("pass")
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_fail_returns_open(self):
        cb = CircuitBreaker(failure_threshold=3, half_open_max=1)
        cb.record_result("fail")
        cb.record_result("fail")
        cb.record_result("fail")
        cb.should_break()
        cb.try_half_open()
        cb.record_result("fail")
        self.assertEqual(cb.state, CircuitState.OPEN)


class TestReset(unittest.TestCase):

    def test_reset(self):
        cb = CircuitBreaker()
        cb.record_result("fail")
        cb.record_result("fail")
        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failure_count, 0)
        self.assertEqual(cb._consecutive_failures, 0)


class TestReport(unittest.TestCase):

    def test_get_report(self):
        cb = CircuitBreaker()
        cb.record_result("pass")
        cb.record_result("fail")
        cb.record_result("pass")
        report = cb.get_report()
        self.assertEqual(report["state"], "closed")
        self.assertEqual(report["total_results"], 3)
        self.assertEqual(report["failure_count"], 1)
        # failure_rate = 1/3 since window has only 3 results
        self.assertAlmostEqual(report["failure_rate"], 1 / 3, places=2)


if __name__ == "__main__":
    unittest.main()
