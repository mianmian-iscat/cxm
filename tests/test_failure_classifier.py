"""test_failure_classifier.py — 失败分类器与分级放行单元测试 (Gap 2.4)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.failure_classifier import FailureClassifier, FailureReport


class TestFailureClassifierPass(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_pass_step(self):
        report = self.fc.classify({"status": "pass", "type": "click", "id": "step0"})
        self.assertEqual(report.severity, "NONE")
        self.assertEqual(report.action, "none")
        self.assertEqual(report.category, "pass")

    def test_skip_step(self):
        report = self.fc.classify({"status": "skip", "type": "click", "id": "step0"})
        self.assertEqual(report.action, "skip")


class TestP0Blocking(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_login_required(self):
        report = self.fc.classify({"status": "error", "type": "navigate", "error": "login_required", "id": "s0"})
        self.assertEqual(report.severity, "P0")
        self.assertEqual(report.action, "block")

    def test_sso_error(self):
        report = self.fc.classify({"status": "error", "type": "navigate", "error": "SSO authentication failed", "id": "s0"})
        self.assertEqual(report.severity, "P0")

    def test_forbidden_403(self):
        report = self.fc.classify({"status": "error", "type": "navigate", "error": "HTTP 403 forbidden", "id": "s0"})
        self.assertEqual(report.severity, "P0")

    def test_unauthorized_401(self):
        report = self.fc.classify({"status": "error", "type": "click", "error": "401 unauthorized", "id": "s0"})
        self.assertEqual(report.severity, "P0")


class TestP1Warning(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_selector_failure(self):
        report = self.fc.classify({"status": "error", "type": "click", "error": "querySelector returned null", "id": "s1"})
        self.assertEqual(report.severity, "P1")
        self.assertEqual(report.action, "warn")

    def test_timeout_error(self):
        report = self.fc.classify({"status": "error", "type": "navigate", "error": "TimeoutError: 30s", "id": "s1"})
        self.assertEqual(report.severity, "P1")

    def test_assert_failure(self):
        report = self.fc.classify({"status": "fail", "type": "assert", "error": "assertion failed", "id": "s1"})
        self.assertEqual(report.severity, "P1")
        self.assertEqual(report.category, "real_bug")


class TestP2Skip(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_network_idle(self):
        report = self.fc.classify({"status": "error", "type": "wait", "error": "network idle exceeded", "id": "s2"})
        self.assertEqual(report.severity, "P2")
        self.assertEqual(report.action, "skip")

    def test_intermittent(self):
        report = self.fc.classify({"status": "error", "type": "click", "error": "intermittent connection issue", "id": "s2"})
        self.assertEqual(report.severity, "P2")

    def test_unknown_defaults_p2(self):
        report = self.fc.classify({"status": "error", "type": "click", "error": "weird error xyz", "id": "s2"})
        self.assertEqual(report.severity, "P2")


class TestReleaseDecision(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_no_p0_not_blocked(self):
        reports = [
            FailureReport(step_id="s0", step_type="click", category="pass", severity="NONE", action="none"),
            FailureReport(step_id="s1", step_type="click", category="script_issue", severity="P1", action="warn"),
        ]
        decision = self.fc.get_release_decision(reports)
        self.assertFalse(decision["blocked"])
        self.assertEqual(decision["p1_count"], 1)

    def test_p0_blocks(self):
        reports = [
            FailureReport(step_id="s0", step_type="navigate", category="env_failure", severity="P0", action="block"),
        ]
        decision = self.fc.get_release_decision(reports)
        self.assertTrue(decision["blocked"])
        self.assertEqual(decision["p0_count"], 1)

    def test_all_pass(self):
        reports = [
            FailureReport(step_id="s0", step_type="click", category="pass", severity="NONE", action="none"),
        ]
        decision = self.fc.get_release_decision(reports)
        self.assertFalse(decision["blocked"])
        self.assertEqual(decision["suggestion"], "全部通过")

    def test_p2_skipped_count(self):
        reports = [
            FailureReport(step_id="s0", step_type="wait", category="env_failure", severity="P2", action="skip"),
            FailureReport(step_id="s1", step_type="click", category="unknown", severity="P2", action="skip"),
        ]
        decision = self.fc.get_release_decision(reports)
        self.assertEqual(decision["p2_count"], 2)


class TestCategorization(unittest.TestCase):

    def setUp(self):
        self.fc = FailureClassifier()

    def test_env_failure_category(self):
        cat = self.fc._categorize("TimeoutError: exceeded", "click")
        self.assertEqual(cat, "env_failure")

    def test_script_issue_category(self):
        cat = self.fc._categorize("querySelector returned null", "click")
        self.assertEqual(cat, "script_issue")

    def test_assert_real_bug(self):
        cat = self.fc._categorize("assertion failed", "assert")
        self.assertEqual(cat, "real_bug")


if __name__ == "__main__":
    unittest.main()
