"""
test_checkpoint_manager.py — CheckpointManager 单元测试

测试断点续跑的核心逻辑，不依赖浏览器/CDP。
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.checkpoint_manager import CheckpointManager


def make_step_result(index: int, status: str = "pass") -> dict:
    return {
        "index": index,
        "type": "click",
        "description": f"step {index}",
        "status": status,
        "duration": 100,
    }


class TestCheckpointTrigger(unittest.TestCase):
    """track_step：触发时机判断"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_trigger_by_step_count(self):
        """满 segmentSize 步时触发"""
        cm = CheckpointManager("run-1", self.tmp, total_steps=20, segment_size=3)
        results = [cm.track_step(make_step_result(i)) for i in range(3)]
        # 前两步不触发，第三步触发
        self.assertFalse(results[0])
        self.assertFalse(results[1])
        self.assertTrue(results[2])

    def test_trigger_by_size(self):
        """输出体积超限时触发"""
        cm = CheckpointManager(
            "run-2", self.tmp, total_steps=20,
            segment_size=100,          # 步数限制设很大
            output_size_limit_kb=1,    # 体积限制 1KB
        )
        # 生成一个大 step_result（> 1KB）
        big_result = make_step_result(0)
        big_result["description"] = "x" * 2000  # ~2KB
        triggered = cm.track_step(big_result)
        self.assertTrue(triggered)

    def test_reset_counter(self):
        """reset 后计数器清零，重新累积"""
        cm = CheckpointManager("run-3", self.tmp, total_steps=20, segment_size=2)
        cm.track_step(make_step_result(0))
        triggered = cm.track_step(make_step_result(1))
        self.assertTrue(triggered)

        cm.reset_seg_counter()  # 重置
        r0 = cm.track_step(make_step_result(2))
        self.assertFalse(r0)   # 重置后第一步不触发


class TestCheckpointSaveLoad(unittest.TestCase):
    """save_segment / load_state / get_resume_context"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _make_cm(self, run_id="run-test", total=20):
        return CheckpointManager(run_id, self.tmp, total_steps=total, segment_size=5)

    def test_save_and_load_state(self):
        """保存一段后，state.json 内容正确"""
        cm = self._make_cm()
        steps = [make_step_result(i) for i in range(5)]
        cm.save_segment(
            seg_index=0,
            step_range=(0, 4),
            steps_results=steps,
            captured_apis={"myApi": {"responseBody": {"ok": True}}},
            last_page_url="https://example.com/page1",
            seg_status="pass",
        )

        state = cm.load_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["lastCompletedStep"], 4)
        self.assertEqual(state["lastPageUrl"], "https://example.com/page1")
        self.assertEqual(len(state["segments"]), 1)
        self.assertEqual(state["segments"][0]["status"], "pass")
        self.assertIn("myApi", state["capturedApis"])

    def test_resume_context_after_one_segment(self):
        """一段完成后，resume context 返回正确的续跑起点"""
        cm = self._make_cm()
        cm.save_segment(
            seg_index=0,
            step_range=(0, 7),
            steps_results=[make_step_result(i) for i in range(8)],
            captured_apis={"api1": {"responseBody": {"data": 42}}},
            last_page_url="https://example.com/step8",
            seg_status="pass",
        )

        ctx = cm.get_resume_context()
        self.assertEqual(ctx["nextStepIndex"], 8)
        self.assertEqual(ctx["currentSegIndex"], 1)
        self.assertIn("api1", ctx["capturedApis"])
        self.assertEqual(ctx["lastPageUrl"], "https://example.com/step8")

    def test_resume_context_merges_multiple_segments(self):
        """多段的 capturedApis 合并，后段覆盖前段"""
        cm = self._make_cm()
        cm.save_segment(0, (0, 4), [make_step_result(i) for i in range(5)],
                        {"api1": {"responseBody": "v1"}}, "url1", "pass")
        cm.save_segment(1, (5, 9), [make_step_result(i) for i in range(5, 10)],
                        {"api1": {"responseBody": "v2"}, "api2": {"responseBody": "ok"}},
                        "url2", "pass")

        ctx = cm.get_resume_context()
        self.assertEqual(ctx["nextStepIndex"], 10)
        self.assertEqual(ctx["currentSegIndex"], 2)
        # api1 被后段覆盖
        self.assertEqual(ctx["capturedApis"]["api1"]["responseBody"], "v2")
        self.assertIn("api2", ctx["capturedApis"])

    def test_save_final_state(self):
        """最终状态写入正确"""
        cm = self._make_cm(total=5)
        cm.save_segment(0, (0, 4), [make_step_result(i) for i in range(5)],
                        {}, "url", "pass")
        cm.save_final_state("pass")
        state = cm.load_state()
        self.assertEqual(state["status"], "pass")
        self.assertIn("finishedAt", state)

    def test_error_segment_does_not_advance_lastCompleted(self):
        """出错段不更新 lastCompletedStep"""
        cm = self._make_cm()
        cm.save_segment(
            seg_index=0,
            step_range=(0, 3),
            steps_results=[make_step_result(i) for i in range(4)],
            captured_apis={},
            last_page_url="url",
            seg_status="error",
        )
        state = cm.load_state()
        # error 段不应该把 lastCompletedStep 推进到 3
        self.assertEqual(state["lastCompletedStep"], -1)

    def test_load_nonexistent_state(self):
        """不存在 state.json 时返回 None"""
        cm = self._make_cm("no-state-run")
        self.assertIsNone(cm.load_state())

    def test_load_segment(self):
        """load_segment 返回正确的段数据"""
        cm = self._make_cm()
        steps = [make_step_result(i) for i in range(3)]
        cm.save_segment(0, (0, 2), steps, {"k": "v"}, "url", "pass")
        seg = cm.load_segment(0)
        self.assertIsNotNone(seg)
        self.assertEqual(seg["segId"], "seg-000")
        self.assertEqual(seg["stepRange"], [0, 2])

    def test_load_missing_segment(self):
        """不存在的段返回 None"""
        cm = self._make_cm()
        self.assertIsNone(cm.load_segment(99))


if __name__ == "__main__":
    unittest.main(verbosity=2)
