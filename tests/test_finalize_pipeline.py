"""
test_finalize_pipeline.py — FinalizePipeline 单元测试

覆盖：
1. Pipeline YAML 加载（存在/缺失）
2. _compact_output 压缩逻辑
3. _parse_time ISO 时间解析
4. 工具方法（stop_recording / flush_capture / disconnect）
5. run() 收尾流程（正常/部分失败不阻断）
"""
import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.finalize_pipeline import FinalizePipeline, _parse_time, _compact_output


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_finalizer(pipeline_exists=True):
    """创建 FinalizePipeline mock 实例"""
    cdp = AsyncMock()
    cdp.disconnect = AsyncMock()

    recorder = MagicMock()
    recorder.stop = AsyncMock(return_value="/tmp/rec.mp4")

    capture = MagicMock()
    capture.flush_pending_bodies = AsyncMock(return_value=None)
    capture.get_captured_requests = MagicMock(return_value=[])

    artifacts = MagicMock()
    artifacts.finalize = MagicMock(return_value={"path": "/tmp/artifacts"})
    artifacts.save_screenshot = MagicMock(return_value="/tmp/shot.png")

    metrics_logger = MagicMock()
    metrics_logger.flush = MagicMock()
    metrics_logger.log_run = MagicMock()

    assertion = MagicMock()
    assertion.run_all_assertions = MagicMock(return_value=MagicMock(passed=True))

    evidence = MagicMock()
    evidence.persist = MagicMock(return_value="/tmp/evidence.json")

    eval_engine = MagicMock()
    eval_engine.evaluate = MagicMock(return_value=MagicMock(
        total_score=85.0,
        rating=MagicMock(level=MagicMock(value="A")),
    ))

    privacy_guard = MagicMock()
    privacy_guard.sanitize = MagicMock(side_effect=lambda x: x)

    quality_scorer = MagicMock()
    quality_scorer.score = MagicMock(return_value={"score": 90, "grade": "A"})

    badcase_collector = MagicMock()
    badcase_collector.collect = MagicMock(return_value=[])

    budget_guard = MagicMock()
    budget_guard.check_budget = MagicMock(return_value=MagicMock(degraded=False))

    circuit_breaker = MagicMock()
    circuit_breaker.should_break = MagicMock(return_value=False)

    failure_classifier = MagicMock()

    kbase = MagicMock()
    kbase.update_from_result = MagicMock()

    orchestrator = MagicMock()

    hook_registry = MagicMock()
    hook_registry.fire = MagicMock()

    input_data = {"steps": [{"type": "click"}], "scene": "f88-test"}

    with patch("core.finalize_pipeline.PipelineEngine") as MockPE:
        if pipeline_exists:
            mock_engine = MagicMock()
            mock_engine.register_tool = MagicMock()
            mock_engine.execute = AsyncMock(return_value={"status": "completed"})
            MockPE.from_yaml = MagicMock(return_value=mock_engine)
        else:
            MockPE.from_yaml = MagicMock(side_effect=FileNotFoundError)

        finalizer = FinalizePipeline(
            cdp=cdp,
            recorder=recorder,
            capture_manager=capture,
            artifacts=artifacts,
            metrics_logger=metrics_logger,
            assertion=assertion,
            evidence=evidence,
            eval_engine=eval_engine,
            privacy_guard=privacy_guard,
            quality_scorer=quality_scorer,
            badcase_collector=badcase_collector,
            budget_guard=budget_guard,
            circuit_breaker=circuit_breaker,
            failure_classifier=failure_classifier,
            kbase=kbase,
            orchestrator=orchestrator,
            hook_registry=hook_registry,
            input_data=input_data,
            run_id="test-run-001",
            business_type="f88_material",
            complexity_result={"level": "simple"},
            complexity_level="simple",
        )

    return finalizer


class TestParseTime(unittest.TestCase):
    """_parse_time ISO 时间解析"""

    def test_valid_iso(self):
        t = _parse_time("2026-07-07T12:00:00")
        self.assertIsInstance(t, float)
        self.assertGreater(t, 0)

    def test_with_timezone(self):
        t = _parse_time("2026-07-07T12:00:00+08:00")
        self.assertIsInstance(t, float)

    def test_with_z_suffix(self):
        t = _parse_time("2026-07-07T12:00:00Z")
        self.assertIsInstance(t, float)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            _parse_time("not-a-time")


class TestCompactOutput(unittest.TestCase):
    """_compact_output 压缩逻辑"""

    def test_pass_steps_stripped_to_essentials(self):
        output = {"steps": [{"type": "click", "status": "pass", "extra_field": "remove_me", "index": 0}], "status": "pass"}
        _compact_output(output, max_response_size_kb=50)
        step = output["steps"][0]
        self.assertNotIn("extra_field", step)
        self.assertIn("type", step)

    def test_capture_trimmed_over_20(self):
        requests = [{"url": f"http://api/{i}", "responseBodyTruncated": True} for i in range(25)]
        output = {"capture": {"requests": requests}}
        _compact_output(output, max_response_size_kb=50)
        self.assertEqual(len(output["capture"]["requests"]), 20)
        self.assertIn("summary", output["capture"])

    def test_empty_output_adds_context_optimization(self):
        output = {}
        _compact_output(output, max_response_size_kb=50)
        self.assertIn("_contextOptimization", output)


class TestFinalizePipelineInit(unittest.TestCase):
    """FinalizePipeline 初始化"""

    def test_pipeline_loaded_when_yaml_exists(self):
        finalizer = _make_finalizer(pipeline_exists=True)
        self.assertIsNotNone(finalizer._pipeline)

    def test_pipeline_none_when_yaml_missing(self):
        # Patch os.path.exists to return False
        with patch("core.finalize_pipeline.os.path.exists", return_value=False):
            finalizer = _make_finalizer(pipeline_exists=False)
        self.assertIsNone(finalizer._pipeline)


class TestFinalizePipelineTools(unittest.TestCase):
    """工具方法"""

    def test_stop_recording(self):
        finalizer = _make_finalizer()
        finalizer._output = {"artifacts": {}, "capture": {}}
        result = _run(finalizer._tool_stop_recording({}))
        finalizer._recorder.stop.assert_called_once()
        self.assertEqual(result, {"stopped": True})
        self.assertEqual(finalizer._output["artifacts"]["videoPath"], "/tmp/rec.mp4")

    def test_flush_capture(self):
        finalizer = _make_finalizer()
        finalizer._output = {"artifacts": {}, "capture": {}}
        result = _run(finalizer._tool_flush_capture({}))
        finalizer._capture.flush_pending_bodies.assert_called_once()
        self.assertEqual(result, {"flushed": True})

    def test_disconnect(self):
        finalizer = _make_finalizer()
        _run(finalizer._tool_disconnect({}))
        finalizer._cdp.disconnect.assert_called_once()


class TestFinalizePipelineRun(unittest.TestCase):
    """run() 收尾流程"""

    def test_run_with_pipeline(self):
        finalizer = _make_finalizer(pipeline_exists=True)
        output = {"status": "pass", "steps": [], "screenshots": []}
        with patch.object(finalizer, '_write_reports'):
            _run(finalizer.run(output))
        # Pipeline engine execute should have been called
        finalizer._pipeline.execute.assert_called_once()

    def test_run_without_pipeline_falls_back(self):
        finalizer = _make_finalizer(pipeline_exists=True)
        finalizer._pipeline = None  # 模拟 YAML 缺失
        output = {"status": "pass", "steps": [], "screenshots": []}
        # Mock _run_sequential to verify fallback path is taken
        finalizer._run_sequential = AsyncMock()
        _run(finalizer.run(output))
        finalizer._run_sequential.assert_called_once_with(output, None)


if __name__ == "__main__":
    unittest.main()
