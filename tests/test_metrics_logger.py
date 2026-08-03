"""
test_metrics_logger.py — MetricsLogger 单元测试

验证：
- MetricLogEntry 序列化（to_dict 过滤 None 值）
- MetricsLogger 三种写入方法（log_step / log_llm_call / log_error）
- flush 写入 metrics.json + JSON-Lines metrics.log
- infer_error_code 错误码推断
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics_logger import MetricsLogger, MetricLogEntry, ErrorCode
from core.log_level import LogLevel, passes_filter, validate_level, get_min_level_from_env


class TestMetricLogEntry(unittest.TestCase):
    """MetricLogEntry 序列化测试"""

    def test_to_dict_filters_none(self):
        entry = MetricLogEntry(
            task_id="run-001",
            business_type="f88_material",
            step="click",
            action="点击搜索",
            result="success",
            duration_ms=320,
        )
        d = entry.to_dict()
        self.assertIn("task_id", d)
        self.assertIn("step", d)
        self.assertNotIn("token_used", d)
        self.assertNotIn("confidence", d)
        self.assertNotIn("error_code", d)
        self.assertNotIn("screenshot_path", d)
        self.assertNotIn("is_false_positive", d)

    def test_to_dict_keeps_explicit_values(self):
        entry = MetricLogEntry(
            task_id="run-001",
            business_type="original_protection",
            step="llm_plan",
            action="生成计划",
            result="success",
            duration_ms=1500,
            token_used=500,
            confidence=0.92,
        )
        d = entry.to_dict()
        self.assertEqual(d["token_used"], 500)
        self.assertEqual(d["confidence"], 0.92)


class TestMetricsLogger(unittest.TestCase):
    """MetricsLogger 写入方法测试"""

    def setUp(self):
        self.logger = MetricsLogger(task_id="test-001", business_type="f88_material")

    def test_log_step(self):
        entry = self.logger.log_step(
            step="click",
            action="点击搜索按钮",
            result="success",
            duration_ms=320,
        )
        self.assertEqual(entry.step, "click")
        self.assertEqual(entry.result, "success")
        self.assertEqual(entry.duration_ms, 320)
        self.assertIsNone(entry.token_used)
        self.assertEqual(len(self.logger.entries), 1)

    def test_log_step_with_error(self):
        entry = self.logger.log_step(
            step="fill",
            action="填写表单",
            result="failed",
            duration_ms=100,
            error_code=ErrorCode.ELEMENT_NOT_FOUND,
        )
        self.assertEqual(entry.result, "failed")
        self.assertEqual(entry.error_code, "ELEMENT_NOT_FOUND")

    def test_log_llm_call(self):
        entry = self.logger.log_llm_call(
            step="llm_plan",
            action="生成操作计划",
            token_used=500,
            confidence=0.92,
            result="success",
            duration_ms=1500,
        )
        self.assertEqual(entry.token_used, 500)
        self.assertEqual(entry.confidence, 0.92)
        self.assertEqual(entry.step, "llm_plan")

    def test_log_error(self):
        entry = self.logger.log_error(
            step="navigate",
            action="导航到目标页",
            error_code=ErrorCode.TIMEOUT,
            duration_ms=30000,
        )
        self.assertEqual(entry.result, "failed")
        self.assertEqual(entry.error_code, "TIMEOUT")

    def test_multiple_entries(self):
        self.logger.log_step("click", "点击", "success", 100)
        self.logger.log_step("fill", "填写", "success", 200)
        self.logger.log_step("assert", "断言", "failed", 50)
        self.assertEqual(len(self.logger.entries), 3)

    def test_get_failed_entries(self):
        self.logger.log_step("click", "点击", "success", 100)
        self.logger.log_step("fill", "填写", "failed", 200)
        self.logger.log_error("navigate", "导航", "TIMEOUT", 300)
        failed = self.logger.get_failed_entries()
        self.assertEqual(len(failed), 2)

    def test_get_llm_entries(self):
        self.logger.log_step("click", "点击", "success", 100)
        self.logger.log_llm_call("llm_plan", "计划", 500, 0.9)
        self.logger.log_llm_call("llm_assert", "断言", 300, 0.85)
        llm = self.logger.get_llm_entries()
        self.assertEqual(len(llm), 2)

    def test_get_total_duration_ms(self):
        self.logger.log_step("click", "a", "success", 100)
        self.logger.log_step("fill", "b", "success", 200)
        self.assertEqual(self.logger.get_total_duration_ms(), 300)

    def test_get_total_token_used(self):
        self.logger.log_step("click", "a", "success", 100)
        self.logger.log_llm_call("llm_plan", "b", 500, 0.9)
        self.logger.log_llm_call("llm_heal", "c", 300, 0.7)
        self.assertEqual(self.logger.get_total_token_used(), 800)


class TestMetricsLoggerFlush(unittest.TestCase):
    """flush 持久化测试"""

    def test_flush_writes_metrics_json_and_log(self):
        logger = MetricsLogger(task_id="flush-test", business_type="smoke")
        logger.log_step("click", "点击搜索", "success", 320)
        logger.log_step("assert", "验证结果", "success", 50)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = os.path.join(tmpdir, "run-001")
            os.makedirs(run_dir)

            metrics_path = logger.flush(run_dir)

            # metrics.json 存在且可解析
            self.assertTrue(os.path.isfile(metrics_path))
            with open(metrics_path) as f:
                data = json.load(f)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["step"], "click")
            self.assertEqual(data[1]["step"], "assert")

            # metrics.log 存在且为 JSON-Lines
            log_path = os.path.join(tmpdir, "metrics.log")
            self.assertTrue(os.path.isfile(log_path))
            with open(log_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)
            line0 = json.loads(lines[0])
            self.assertEqual(line0["task_id"], "flush-test")


class TestInferErrorCode(unittest.TestCase):
    """错误码推断测试"""

    def test_timeout(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("等待接口超时（10s）: /api/search"),
            ErrorCode.TIMEOUT,
        )

    def test_element_not_found(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("找不到文本为 '搜索' 的可点击元素"),
            ErrorCode.ELEMENT_NOT_FOUND,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("find error"),
            ErrorCode.ELEMENT_NOT_FOUND,
        )

    def test_navigation_error(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("NavigationError: net::ERR_CONNECTION_REFUSED"),
            ErrorCode.NAVIGATION_ERROR,
        )

    def test_assert_failed(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("assert: 页面不包含 '共' "),
            ErrorCode.ASSERT_FAILED,
        )

    def test_login_required(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("login_required: BUC SSO"),
            ErrorCode.LOGIN_REQUIRED,
        )

    def test_compliance_blocked(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("合规拦截：不允许删除商家数据"),
            ErrorCode.COMPLIANCE_BLOCKED,
        )

    def test_unknown(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("some random error"),
            ErrorCode.UNKNOWN,
        )

    def test_empty(self):
        self.assertEqual(
            MetricsLogger.infer_error_code(""),
            ErrorCode.UNKNOWN,
        )

    # ── 环境限制类错误码推断测试 ──

    def test_fullscreen_blocked(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("requestFullscreen requires user gesture"),
            ErrorCode.FULLSCREEN_BLOCKED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("全屏模式受限"),
            ErrorCode.FULLSCREEN_BLOCKED,
        )

    def test_drag_not_supported(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("拖拽操作失败：trim handle 未响应"),
            ErrorCode.DRAG_NOT_SUPPORTED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("drag operation failed"),
            ErrorCode.DRAG_NOT_SUPPORTED,
        )

    def test_keyboard_event_failed(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("Space键播放未触发"),
            ErrorCode.KEYBOARD_EVENT_FAILED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("keyboard event not dispatched"),
            ErrorCode.KEYBOARD_EVENT_FAILED,
        )

    def test_play_observation_limited(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("播放头位置无法观察"),
            ErrorCode.PLAY_OBSERVATION_LIMITED,
        )

    def test_zoom_not_triggered(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("缩放操作未触发"),
            ErrorCode.ZOOM_NOT_TRIGGERED,
        )

    def test_focus_required(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("setFocus: 元素无法获得焦点"),
            ErrorCode.FOCUS_REQUIRED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("快捷键响应失败，编辑器未获得焦点"),
            ErrorCode.FOCUS_REQUIRED,
        )

    def test_shortcut_conflict(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("Ctrl+Z shortcut conflict"),
            ErrorCode.SHORTCUT_CONFLICT,
        )

    def test_panel_transition_failed(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("面板过渡状态未观察到"),
            ErrorCode.PANEL_TRANSITION_FAILED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("loading transition blocked"),
            ErrorCode.PANEL_TRANSITION_FAILED,
        )

    def test_exception_sim_failed(self):
        self.assertEqual(
            MetricsLogger.infer_error_code("断网模拟失败"),
            ErrorCode.EXCEPTION_SIM_FAILED,
        )
        self.assertEqual(
            MetricsLogger.infer_error_code("mock response setup failed"),
            ErrorCode.EXCEPTION_SIM_FAILED,
        )


class TestLogLevel(unittest.TestCase):
    """日志级别模块测试"""

    def test_passes_filter_debug_below_info(self):
        self.assertFalse(passes_filter("DEBUG", "INFO"))

    def test_passes_filter_info_meets_info(self):
        self.assertTrue(passes_filter("INFO", "INFO"))

    def test_passes_filter_error_above_warning(self):
        self.assertTrue(passes_filter("ERROR", "WARNING"))

    def test_passes_filter_warning_below_error(self):
        self.assertFalse(passes_filter("WARNING", "ERROR"))

    def test_validate_level_valid(self):
        self.assertEqual(validate_level("DEBUG"), "DEBUG")
        self.assertEqual(validate_level("ERROR"), "ERROR")

    def test_validate_level_invalid_fallback_info(self):
        self.assertEqual(validate_level("INVALID"), "INFO")
        self.assertEqual(validate_level(""), "INFO")

    def test_get_min_level_from_env_default(self):
        # 默认未设置环境变量时返回 INFO
        os.environ.pop("WEB_AUTO_LOG_LEVEL", None)
        self.assertEqual(get_min_level_from_env(), "INFO")

    def test_get_min_level_from_env_override(self):
        os.environ["WEB_AUTO_LOG_LEVEL"] = "DEBUG"
        try:
            self.assertEqual(get_min_level_from_env(), "DEBUG")
        finally:
            os.environ.pop("WEB_AUTO_LOG_LEVEL", None)


class TestMetricsLoggerLevel(unittest.TestCase):
    """MetricsLogger 日志分级测试"""

    def setUp(self):
        self.logger = MetricsLogger(task_id="level-test", business_type="smoke", min_level="INFO")

    def test_log_step_default_level_info(self):
        entry = self.logger.log_step("click", "点击", "success", 100)
        self.assertEqual(entry.level, "INFO")

    def test_log_llm_call_default_level_info(self):
        entry = self.logger.log_llm_call("llm_plan", "计划", 100, 0.9)
        self.assertEqual(entry.level, "INFO")

    def test_log_error_default_level_error(self):
        entry = self.logger.log_error("navigate", "导航", "TIMEOUT", 5000)
        self.assertEqual(entry.level, "ERROR")

    def test_log_debug(self):
        entry = self.logger.log_debug("evaluate", "获取DOM信息")
        self.assertEqual(entry.level, "DEBUG")
        self.assertEqual(entry.step, "evaluate")

    def test_log_info(self):
        entry = self.logger.log_info("navigate", "导航到首页")
        self.assertEqual(entry.level, "INFO")

    def test_log_warning(self):
        entry = self.logger.log_warning(
            "click", "点击后页面未响应",
            result="failed",
            error_code=ErrorCode.TIMEOUT,
        )
        self.assertEqual(entry.level, "WARNING")
        self.assertEqual(entry.error_code, "TIMEOUT")

    def test_min_level_constructor(self):
        logger = MetricsLogger(task_id="x", min_level="WARNING")
        self.assertEqual(logger.min_level, "WARNING")

    def test_min_level_constructor_invalid_fallback(self):
        logger = MetricsLogger(task_id="x", min_level="INVALID")
        self.assertEqual(logger.min_level, "INFO")

    def test_flush_filters_debug_from_global_log(self):
        """DEBUG 条目不应写入全局 metrics.log，但写入 metrics.json"""
        logger = MetricsLogger(task_id="filter-test", business_type="smoke", min_level="INFO")
        logger.log_debug("evaluate", "DOM检查")
        logger.log_step("click", "点击按钮", "success", 100)
        logger.log_warning("fill", "填写失败降级", result="failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = os.path.join(tmpdir, "run-001")
            os.makedirs(run_dir)
            logger.flush(run_dir)

            # metrics.json 含全部 3 条
            with open(os.path.join(run_dir, "metrics.json")) as f:
                data = json.load(f)
            self.assertEqual(len(data), 3)

            # metrics.log 只含 INFO + WARNING（过滤掉 DEBUG）
            log_path = os.path.join(tmpdir, "metrics.log")
            with open(log_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)
            levels = [json.loads(line)["level"] for line in lines]
            self.assertNotIn("DEBUG", levels)
            self.assertIn("INFO", levels)
            self.assertIn("WARNING", levels)

    def test_flush_debug_level_writes_all_to_global(self):
        """min_level=DEBUG 时全部写入全局日志"""
        logger = MetricsLogger(task_id="debug-all", business_type="smoke", min_level="DEBUG")
        logger.log_debug("evaluate", "DOM检查")
        logger.log_step("click", "点击", "success", 100)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = os.path.join(tmpdir, "run-001")
            os.makedirs(run_dir)
            logger.flush(run_dir)

            log_path = os.path.join(tmpdir, "metrics.log")
            with open(log_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)

    def test_to_dict_includes_level(self):
        entry = MetricLogEntry(
            task_id="run-001",
            business_type="smoke",
            step="click",
            action="点击",
            result="success",
            duration_ms=100,
            level="WARNING",
        )
        d = entry.to_dict()
        self.assertIn("level", d)
        self.assertEqual(d["level"], "WARNING")


if __name__ == "__main__":
    unittest.main()
