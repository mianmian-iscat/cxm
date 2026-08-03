"""test_output_formatter.py — 输出初始化与摘要打印单元测试"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.output_formatter import init_output, print_verbose


def _capture(output, mode):
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_verbose(output, mode)
    return buf.getvalue()


class TestInitOutput(unittest.TestCase):

    def setUp(self):
        self.input_data = {"id": "TC-001", "name": "登录用例"}
        self.output = init_output(self.input_data, "run-123")

    def test_copies_id_and_name(self):
        self.assertEqual(self.output["id"], "TC-001")
        self.assertEqual(self.output["name"], "登录用例")

    def test_default_status_is_pass(self):
        self.assertEqual(self.output["status"], "pass")

    def test_run_id_stored_in_artifacts(self):
        self.assertEqual(self.output["artifacts"]["runId"], "run-123")

    def test_start_time_is_iso_utc(self):
        self.assertTrue(self.output["startTime"].endswith("Z"))

    def test_empty_collections_initialized(self):
        self.assertEqual(self.output["steps"], [])
        self.assertEqual(self.output["screenshots"], [])
        self.assertEqual(self.output["capture"]["requests"], [])
        self.assertEqual(self.output["duration"], 0)

    def test_missing_required_key_raises(self):
        with self.assertRaises(KeyError):
            init_output({"id": "only-id"}, "run-1")


class TestPrintVerbose(unittest.TestCase):

    def _base_output(self, **overrides):
        out = {
            "id": "TC-001",
            "status": "pass",
            "duration": 2500,
            "steps": [{"status": "pass"}, {"status": "pass"}],
            "screenshots": [],
            "capture": {"requests": []},
            "artifacts": {},
        }
        out.update(overrides)
        return out

    def test_full_mode_prints_nothing(self):
        self.assertEqual(_capture(self._base_output(), "full"), "")

    def test_minimal_mode_single_line(self):
        text = _capture(self._base_output(), "minimal")
        self.assertIn("TC-001", text)
        self.assertIn("pass", text)
        self.assertEqual(text.count("\n"), 1)

    def test_minimal_pass_icon(self):
        self.assertIn("✅", _capture(self._base_output(status="pass"), "minimal"))

    def test_minimal_fail_icon(self):
        self.assertIn("❌", _capture(self._base_output(status="fail"), "minimal"))

    def test_minimal_checkpoint_icon(self):
        text = _capture(self._base_output(status="checkpoint_saved"), "minimal")
        self.assertIn("⏳", text)

    def test_summary_includes_step_ratio(self):
        text = _capture(self._base_output(), "summary")
        self.assertIn("2/2 通过", text)

    def test_summary_partial_steps(self):
        out = self._base_output(steps=[{"status": "pass"}, {"status": "fail"}])
        self.assertIn("1/2 通过", _capture(out, "summary"))

    def test_summary_duration_formatted_seconds(self):
        text = _capture(self._base_output(duration=2500), "summary")
        self.assertIn("2.5s", text)

    def test_summary_shows_error_block(self):
        out = self._base_output(
            status="fail",
            error={"stepIndex": 3, "message": "元素未找到"},
        )
        text = _capture(out, "summary")
        self.assertIn("step 3", text)
        self.assertIn("元素未找到", text)

    def test_summary_shows_screenshots_with_dir(self):
        out = self._base_output(
            screenshots=["a.png", "b.png"],
            artifacts={"runDir": "/tmp/run"},
        )
        text = _capture(out, "summary")
        self.assertIn("2 张", text)
        self.assertIn("/tmp/run/screenshots/", text)

    def test_summary_shows_capture_requests(self):
        out = self._base_output(
            capture={"requests": [{"url": "x"}], "summary": {"totalRequests": 5}},
        )
        text = _capture(out, "summary")
        self.assertIn("5 个请求", text)

    def test_summary_checkpoint_resume_hint(self):
        out = self._base_output(
            status="checkpoint_saved",
            checkpoint={"completedSteps": 2, "totalSteps": 5, "runId": "run-9"},
        )
        text = _capture(out, "summary")
        self.assertIn("Checkpoint", text)
        self.assertIn("2/5", text)
        self.assertIn("run-9", text)


if __name__ == "__main__":
    unittest.main()
