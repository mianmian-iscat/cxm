"""
test_core.py — core 组件单元测试

测试对象：
- normalize_input.py：输入校验逻辑
- score_eval.py：评分逻辑
- artifact_manager.py：产物目录创建和写入

运行：
    python -m pytest tests/test_core.py -v
    # 或
    python tests/test_core.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.normalize_input import normalize
from scripts.score_eval import score
from core.artifact_manager import ArtifactManager


class TestNormalizeInput(unittest.TestCase):

    def _base_input(self):
        return {
            "id": "test-001",
            "name": "测试用例",
            "context": {"urlPattern": "example.com"},
            "steps": [
                {"type": "click", "text": "搜索"}
            ]
        }

    def test_valid_input_passes(self):
        result = normalize(self._base_input())
        self.assertEqual(result["id"], "test-001")

    def test_missing_id_raises(self):
        data = self._base_input()
        del data["id"]
        with self.assertRaises(ValueError):
            normalize(data)

    def test_missing_steps_raises(self):
        data = self._base_input()
        del data["steps"]
        with self.assertRaises(ValueError):
            normalize(data)

    def test_invalid_id_format_raises(self):
        data = self._base_input()
        data["id"] = "test 001 /"
        with self.assertRaises(ValueError):
            normalize(data)

    def test_too_many_steps_raises(self):
        data = self._base_input()
        data["steps"] = [{"type": "wait", "ms": 100}] * 51
        with self.assertRaises(ValueError):
            normalize(data)

    def test_click_without_text_or_selector_raises(self):
        data = self._base_input()
        data["steps"] = [{"type": "click"}]
        with self.assertRaises(ValueError):
            normalize(data)

    def test_wait_out_of_range_raises(self):
        data = self._base_input()
        data["steps"] = [{"type": "wait", "ms": 99999}]
        with self.assertRaises(ValueError):
            normalize(data)

    def test_defaults_are_set(self):
        result = normalize(self._base_input())
        self.assertEqual(result["context"]["waitAfterLoad"], 2000)
        self.assertTrue(result["capture"]["enabled"])
        self.assertFalse(result["screenshot"]["onEachStep"])
        self.assertTrue(result["screenshot"]["onError"])

    def test_sensitive_fields_redacted(self):
        data = self._base_input()
        data["context"]["token"] = "super-secret-123"
        result = normalize(data)
        self.assertEqual(result["context"]["token"], "***REDACTED***")


class TestScoreEval(unittest.TestCase):

    def _pass_output(self):
        return {
            "id": "test-001",
            "name": "测试",
            "status": "pass",
            "startTime": "2026-01-01T00:00:00Z",
            "duration": 5000,
            "steps": [
                {"index": 0, "type": "click", "status": "pass", "duration": 500},
                {"index": 1, "type": "assert", "status": "pass", "duration": 10,
                 "assertResult": {"expected": "SKC", "actual": "(包含)", "pass": True}},
            ],
            "screenshots": [{"stepIndex": 0, "label": "step0", "path": "/tmp/a.png"}],
            "capture": {
                "requests": [
                    {"method": "POST", "url": "/api/test", "status": 200, "duration": 100,
                     "requestBody": {}, "responseBody": {"code": "OK"}}
                ]
            },
        }

    def test_perfect_output_scores_high(self):
        result = score(self._pass_output())
        self.assertGreaterEqual(result["overall_score"], 80)
        self.assertTrue(result["passed"])

    def test_error_output_fails(self):
        output = self._pass_output()
        output["status"] = "error"
        output["error"] = {"stepIndex": 0, "message": "元素不存在"}
        result = score(output)
        self.assertFalse(result["passed"])

    def test_assert_fail_reduces_score(self):
        output = self._pass_output()
        output["status"] = "fail"
        output["steps"][1]["status"] = "fail"
        output["steps"][1]["assertResult"]["pass"] = False
        result = score(output)
        self.assertLess(result["dimensions"]["assert_pass_rate"], 1.0)

    def test_no_steps_flags_issue(self):
        output = self._pass_output()
        output["steps"] = []
        result = score(output)
        self.assertIn("无任何步骤执行记录", result["issues"])


class TestArtifactManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = ArtifactManager("test-run-001", base_dir=self.tmpdir)

    def test_run_dir_created(self):
        self.assertTrue(os.path.isdir(self.mgr.run_dir))

    def test_screenshots_dir_created(self):
        self.assertTrue(os.path.isdir(self.mgr.screenshots_dir))

    def test_save_output(self):
        self.mgr.save_output({"status": "pass"})
        path = self.mgr.path("output.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["status"], "pass")

    def test_save_screenshot(self):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = self.mgr.save_screenshot(png_bytes, "step0-click")
        self.assertTrue(os.path.exists(path))

    def test_finalize_creates_manifest(self):
        self.mgr.finalize()
        manifest_path = self.mgr.path("manifest.json")
        self.assertTrue(os.path.exists(manifest_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
