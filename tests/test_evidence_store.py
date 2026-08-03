"""
tests/test_evidence_store.py — Evidence Store 证据链子系统单元测试
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.evidence_store import EvidenceStore, EvidenceEntry


class TestEvidenceEntry(unittest.TestCase):

    def test_to_dict_basic(self):
        entry = EvidenceEntry(
            step_id="step0",
            tool="click",
            input={"text": "搜索"},
            output={"clicked": True},
            timestamp="2026-01-01T00:00:00+00:00",
            duration_ms=320,
        )
        d = entry.to_dict()
        self.assertEqual(d["step_id"], "step0")
        self.assertEqual(d["tool"], "click")
        self.assertEqual(d["duration_ms"], 320)
        self.assertTrue(d["schema_validated"])
        self.assertNotIn("error", d)

    def test_to_dict_with_error(self):
        entry = EvidenceEntry(
            step_id="step1",
            tool="fill",
            input={},
            output=None,
            timestamp="2026-01-01T00:00:00+00:00",
            duration_ms=100,
            error="selector not found",
        )
        d = entry.to_dict()
        self.assertEqual(d["error"], "selector not found")

    def test_serialize_bytes(self):
        result = EvidenceEntry._serialize(b"\x00\x01\x02")
        self.assertIn("bytes", result)

    def test_serialize_dict(self):
        result = EvidenceEntry._serialize({"a": 1})
        self.assertEqual(result, {"a": 1})

    def test_serialize_none(self):
        self.assertIsNone(EvidenceEntry._serialize(None))


class TestEvidenceStore(unittest.TestCase):

    def setUp(self):
        self.store = EvidenceStore(trace_id="test-run-001", pipeline="test-pipeline")

    def test_initial_state(self):
        self.assertEqual(self.store.evidence_count, 0)
        self.assertEqual(self.store.total_duration_ms, 0)
        self.assertEqual(self.store.validated_count, 0)
        self.assertEqual(self.store.error_count, 0)

    def test_record_step(self):
        self.store.record_step("step0", "click", {"text": "搜索"}, {"clicked": True}, 320, True)
        self.assertEqual(self.store.evidence_count, 1)
        self.assertEqual(self.store.total_duration_ms, 320)

    def test_record_multiple_steps(self):
        self.store.record_step("s0", "click", {}, {}, 100, True)
        self.store.record_step("s1", "fill", {}, {}, 200, True)
        self.store.record_step("s2", "wait", {}, {}, 300, False, error="timeout")
        self.assertEqual(self.store.evidence_count, 3)
        self.assertEqual(self.store.total_duration_ms, 600)
        self.assertEqual(self.store.validated_count, 2)
        self.assertEqual(self.store.error_count, 1)

    def test_set_conclusion(self):
        self.store.set_conclusion("所有步骤执行成功")
        trace = self.store.to_trace()
        self.assertEqual(trace["conclusion"], "所有步骤执行成功")

    def test_get_steps(self):
        self.store.record_step("s0", "click", {"a": 1}, {"ok": True}, 100)
        steps = self.store.get_steps()
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["step_id"], "s0")

    def test_to_trace(self):
        self.store.record_step("s0", "click", {}, {}, 100, True)
        self.store.record_step("s1", "fill", {}, {}, 200, True)
        self.store.set_conclusion("测试通过")

        trace = self.store.to_trace()
        self.assertEqual(trace["trace_id"], "test-run-001")
        self.assertEqual(trace["pipeline"], "test-pipeline")
        self.assertEqual(trace["evidence_count"], 2)
        self.assertEqual(trace["total_duration_ms"], 300)
        self.assertEqual(trace["validated_count"], 2)
        self.assertEqual(trace["error_count"], 0)
        self.assertEqual(trace["conclusion"], "测试通过")
        self.assertEqual(len(trace["steps"]), 2)
        self.assertIn("started_at", trace)

    def test_to_trace_json_serializable(self):
        self.store.record_step("s0", "click", {"text": "搜索"}, [1, 2, 3], 100)
        trace = self.store.to_trace()
        # 应该可以正常序列化
        json_str = json.dumps(trace, ensure_ascii=False)
        self.assertIsInstance(json_str, str)

    def test_save(self):
        self.store.record_step("s0", "click", {}, {}, 100)
        self.store.set_conclusion("完成")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = self.store.save(tmp_dir)
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith("evidence.json"))

            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["trace_id"], "test-run-001")
            self.assertEqual(data["evidence_count"], 1)

    def test_to_summary_dict(self):
        self.store.record_step("s0", "click", {}, {}, 100)
        self.store.record_step("s1", "fill", {}, {}, 200, False, error="err")
        self.store.set_conclusion("OK")

        summary = self.store.to_summary_dict()
        self.assertEqual(summary["traceId"], "test-run-001")
        self.assertEqual(summary["evidenceCount"], 2)
        self.assertEqual(summary["validatedCount"], 1)
        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["totalDurationMs"], 300)
        self.assertEqual(summary["conclusion"], "OK")


class TestEvidenceStoreEdgeCases(unittest.TestCase):

    def test_empty_conclusion(self):
        store = EvidenceStore(trace_id="t1")
        trace = store.to_trace()
        self.assertEqual(trace["conclusion"], "")

    def test_summary_empty_conclusion(self):
        store = EvidenceStore(trace_id="t2")
        summary = store.to_summary_dict()
        self.assertEqual(summary["conclusion"], "")


if __name__ == "__main__":
    unittest.main()
