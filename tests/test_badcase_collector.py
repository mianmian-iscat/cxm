"""test_badcase_collector.py — BadCase 自动采集单元测试 (Gap 2.3)"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.badcase_collector import BadCaseCollector, BadCase


class TestBadCaseCollector(unittest.TestCase):

    def setUp(self):
        self.collector = BadCaseCollector()

    def test_collect_no_errors(self):
        output = {"steps": [{"status": "pass", "type": "click"}], "artifacts": {}}
        badcases = self.collector.collect(output, {})
        self.assertEqual(len(badcases), 0)

    def test_collect_error_step(self):
        output = {
            "steps": [
                {"status": "error", "type": "click", "error": "TimeoutError: exceeded 30s", "description": "click button"},
            ],
            "artifacts": {"runId": "run1"},
        }
        badcases = self.collector.collect(output, {})
        self.assertEqual(len(badcases), 1)
        self.assertEqual(badcases[0].root_cause_category, "env_failure")
        self.assertEqual(badcases[0].step_type, "click")

    def test_collect_fail_step_assert(self):
        output = {
            "steps": [
                {"status": "fail", "type": "assert", "error": "Expected true but got false", "description": "assert check"},
            ],
            "artifacts": {"runId": "run1"},
        }
        badcases = self.collector.collect(output, {})
        self.assertEqual(len(badcases), 1)
        self.assertEqual(badcases[0].root_cause_category, "real_bug")

    def test_collect_skip_pass_steps(self):
        output = {
            "steps": [
                {"status": "pass", "type": "click"},
                {"status": "skip", "type": "click"},
                {"status": "error", "type": "navigate", "error": "ECONNREFUSED"},
            ],
            "artifacts": {},
        }
        badcases = self.collector.collect(output, {})
        self.assertEqual(len(badcases), 1)


class TestErrorClassification(unittest.TestCase):

    def setUp(self):
        self.collector = BadCaseCollector()

    def test_env_failure_timeout(self):
        cat = self.collector._classify_error({"error": "TimeoutError: 30s", "status": "error", "type": "click"}, {})
        self.assertEqual(cat, "env_failure")

    def test_env_failure_econnrefused(self):
        cat = self.collector._classify_error({"error": "ECONNREFUSED 127.0.0.1:8080", "status": "error", "type": "navigate"}, {})
        self.assertEqual(cat, "env_failure")

    def test_script_issue_selector(self):
        cat = self.collector._classify_error({"error": "querySelector returned null", "status": "error", "type": "click"}, {})
        self.assertEqual(cat, "script_issue")

    def test_script_issue_offsetparent(self):
        cat = self.collector._classify_error({"error": "offsetParent is null", "status": "error", "type": "click"}, {})
        self.assertEqual(cat, "script_issue")

    def test_data_invalid(self):
        cat = self.collector._classify_error({"error": "data is invalid", "status": "error", "type": "fill"}, {})
        self.assertEqual(cat, "data_invalid")

    def test_real_bug_assert(self):
        cat = self.collector._classify_error({"error": "assert failed", "status": "fail", "type": "assert"}, {})
        self.assertEqual(cat, "real_bug")

    def test_unknown(self):
        cat = self.collector._classify_error({"error": "something weird happened", "status": "error", "type": "click"}, {})
        self.assertEqual(cat, "unknown")


class TestSaveToPatterns(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.collector = BadCaseCollector()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_creates_file(self):
        bc = BadCase(
            id="bc_run1_click_timeout",
            title="click: TimeoutError",
            error_pattern="TimeoutError: exceeded 30s",
            step_type="click",
            error_message="TimeoutError: exceeded 30s",
            root_cause_category="env_failure",
            severity="P2",
        )
        self.collector.save_to_patterns([bc], self.tmpdir)
        files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        self.assertGreater(len(files), 0)

    def test_save_deduplication(self):
        bc1 = BadCase(id="bc1", title="T1", error_pattern="TimeoutError: exceeded 30s", step_type="click",
                      error_message="TimeoutError: exceeded 30s", root_cause_category="env_failure", severity="P2",
                      created_at="2024-01-01")
        bc2 = BadCase(id="bc2", title="T2", error_pattern="TimeoutError: exceeded 30s", step_type="click",
                      error_message="TimeoutError: exceeded 30s", root_cause_category="env_failure", severity="P2",
                      created_at="2024-01-02")
        self.collector.save_to_patterns([bc1], self.tmpdir)
        self.collector.save_to_patterns([bc2], self.tmpdir)
        files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        # Should be deduplicated to 1 file
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.tmpdir, files[0])) as f:
            data = json.load(f)
        self.assertEqual(data["hit_count"], 2)


if __name__ == "__main__":
    unittest.main()
