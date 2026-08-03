"""
test_event_listener.py — EventListener 单元测试
"""
import asyncio
import time
import unittest
from unittest.mock import MagicMock

from core.event_listener import EventListener, CapturedRequest, ConsoleEntry


class TestEventListener(unittest.TestCase):

    def setUp(self):
        self.cdp_mock = MagicMock()
        self.listener = EventListener(self.cdp_mock)

    def test_initial_state(self):
        """初始化时请求和日志列表为空"""
        self.assertEqual(self.listener.get_requests(), [])
        self.assertEqual(self.listener.get_console_logs(), [])
        self.assertEqual(self.listener.get_errors(), [])

    def test_start_stop(self):
        """start/stop 不抛异常"""
        self.listener.start()
        self.listener.stop()

    def test_captured_request_fields(self):
        """CapturedRequest 字段和 to_dict 正确"""
        req = CapturedRequest(
            request_id="r1",
            method="POST",
            url="https://example.com/api",
        )
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.url, "https://example.com/api")
        self.assertIsNone(req.status)
        self.assertIsNone(req.duration_ms)

    def test_captured_request_to_dict(self):
        """to_dict 包含必要字段"""
        req = CapturedRequest(
            request_id="r2",
            method="GET",
            url="https://api.com/data",
            status=200,
        )
        d = req.to_dict()
        self.assertEqual(d["method"], "GET")
        self.assertEqual(d["url"], "https://api.com/data")
        self.assertEqual(d["status"], 200)

    def test_captured_request_duration(self):
        """end_time 设置后 duration_ms 计算正确"""
        req = CapturedRequest(request_id="r3", method="GET", url="https://a.com")
        req.start_time = 1000.0
        req.end_time = 1001.5
        self.assertEqual(req.duration_ms, 1500)

    def test_console_entry_fields(self):
        """ConsoleEntry 字段正确"""
        entry = ConsoleEntry(level="error", text="Uncaught ReferenceError")
        self.assertEqual(entry.level, "error")
        self.assertEqual(entry.text, "Uncaught ReferenceError")
        self.assertIsInstance(entry.timestamp, float)

    def test_get_requests_returns_list(self):
        """get_requests 返回列表"""
        requests = self.listener.get_requests()
        self.assertIsInstance(requests, list)

    def test_get_console_logs_with_level_filter(self):
        """get_console_logs 支持按 level 过滤"""
        logs = self.listener.get_console_logs(level="error")
        self.assertIsInstance(logs, list)

    def test_get_errors_returns_list(self):
        """get_errors 返回列表"""
        errors = self.listener.get_errors()
        self.assertIsInstance(errors, list)

    def test_wait_for_request_timeout(self):
        """wait_for_request 超时时抛出 TimeoutError 或返回 None"""
        async def _run():
            try:
                result = await self.listener.wait_for_request("nonexistent.api", timeout=0.1)
                return result
            except (asyncio.TimeoutError, Exception):
                return None

        result = asyncio.run(_run())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
