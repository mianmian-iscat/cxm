"""test_network_healing.py — 网络层自愈引擎单元测试"""

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.network_healing import (
    NetworkHealingEngine,
    NetworkHealingAction,
    NetworkHealingResult,
    _ApiBaseline,
)


async def _noop_sleep(*args, **kwargs):
    return None


class _FakeCDP:
    def __init__(self):
        self.evaluated = []
        self.sent = []

    async def evaluate(self, script):
        self.evaluated.append(script)

    async def _send_cmd(self, cmd, params):
        self.sent.append((cmd, params))


class _FakeCapture:
    def __init__(self, entry=None):
        self._entry = entry

    def get_api_entry(self, url_key):
        return self._entry


def _run(coro):
    # 使用独立事件循环并在结束后恢复一个全新的循环，
    # 避免污染依赖 asyncio.get_event_loop() 的其他测试（如 test_cdp_client）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestApiBaseline(unittest.TestCase):

    def test_empty_p95_mean(self):
        bl = _ApiBaseline(url_pattern="/api")
        self.assertEqual(bl.p95, 0.0)
        self.assertEqual(bl.mean, 0.0)

    def test_window_cap(self):
        bl = _ApiBaseline(url_pattern="/api", window_size=3)
        for d in (1, 2, 3, 4, 5):
            bl.record(d)
        self.assertEqual(bl.durations, [3, 4, 5])

    def test_mean(self):
        bl = _ApiBaseline(url_pattern="/api")
        for d in (100, 200):
            bl.record(d)
        self.assertEqual(bl.mean, 150.0)


class TestNormalizeUrl(unittest.TestCase):

    def test_extracts_path(self):
        self.assertEqual(
            NetworkHealingEngine._normalize_url("https://x.com/api/list?a=1"), "/api/list"
        )

    def test_no_path_returns_prefix(self):
        # 无 path 时回退到 url 前缀
        result = NetworkHealingEngine._normalize_url("notaurl")
        self.assertTrue(result)


class TestSlowRequest(unittest.TestCase):

    def setUp(self):
        self.engine = NetworkHealingEngine()

    def test_no_throttle_below_min_samples(self):
        for _ in range(4):
            self.engine._record_baseline("/api", 100)
        result = self.engine._check_slow_request("/api", 10000)
        self.assertEqual(result.action, NetworkHealingAction.NONE)

    def test_throttle_when_slow(self):
        for _ in range(5):
            self.engine._record_baseline("/api", 100)
        result = self.engine._check_slow_request("/api", 10000)
        self.assertEqual(result.action, NetworkHealingAction.SLOW_REQUEST_THROTTLE)
        self.assertTrue(result.success)

    def test_no_throttle_when_normal(self):
        for _ in range(5):
            self.engine._record_baseline("/api", 100)
        result = self.engine._check_slow_request("/api", 120)
        self.assertEqual(result.action, NetworkHealingAction.NONE)


class TestResponseAnomaly(unittest.TestCase):

    def setUp(self):
        self.engine = NetworkHealingEngine()

    def test_html_error_page(self):
        result = self.engine._check_response_anomaly(
            "/api", {"responseBody": "<html><body>500</body></html>", "url": "x"}
        )
        self.assertEqual(result.action, NetworkHealingAction.RESPONSE_ADAPT)
        self.assertIn("HTML", result.message)

    def test_json_error_code(self):
        result = self.engine._check_response_anomaly(
            "/api", {"responseBody": {"errorCode": "E001"}, "url": "x"}
        )
        self.assertEqual(result.action, NetworkHealingAction.RESPONSE_ADAPT)

    def test_empty_data_but_total_positive(self):
        result = self.engine._check_response_anomaly(
            "/api", {"responseBody": {"data": [], "total": 5, "code": 0}, "url": "x"}
        )
        self.assertEqual(result.action, NetworkHealingAction.RESPONSE_ADAPT)
        self.assertIn("data 为空", result.message)

    def test_healthy_response_no_action(self):
        result = self.engine._check_response_anomaly(
            "/api", {"responseBody": {"data": [1, 2], "code": 0}, "url": "x"}
        )
        self.assertEqual(result.action, NetworkHealingAction.NONE)

    def test_none_body_no_action(self):
        result = self.engine._check_response_anomaly("/api", {"responseBody": None})
        self.assertEqual(result.action, NetworkHealingAction.NONE)


class TestThrottleDelay(unittest.TestCase):

    def test_zero_when_no_throttles(self):
        self.assertEqual(NetworkHealingEngine().get_throttle_delay_ms(), 0)

    def test_scaled_and_capped(self):
        engine = NetworkHealingEngine()
        engine._stats["slow_throttles"] = 10
        self.assertEqual(engine.get_throttle_delay_ms(), 5000)


class TestHandleApiFailure(unittest.TestCase):

    def setUp(self):
        self.engine = NetworkHealingEngine()
        self._patcher = mock.patch(
            "core.network_healing.asyncio.sleep", new=_noop_sleep
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_no_strategy_for_healthy(self):
        entry = {"url": "https://x.com/api", "status": 200}
        result = _run(self.engine.handle_api_failure(entry))
        self.assertEqual(result.action, NetworkHealingAction.NONE)

    def test_5xx_retry_success(self):
        entry = {"url": "https://x.com/api", "status": 503}
        cdp = _FakeCDP()
        capture = _FakeCapture(entry={"status": 200})
        result = _run(self.engine.handle_api_failure(entry, cdp=cdp, capture_manager=capture))
        self.assertEqual(result.action, NetworkHealingAction.RETRY_5XX)
        self.assertTrue(result.success)
        self.assertEqual(self.engine.get_stats()["retries_5xx_success"], 1)

    def test_5xx_retry_failure_without_recovery(self):
        entry = {"url": "https://x.com/api", "status": 500}
        cdp = _FakeCDP()
        capture = _FakeCapture(entry={"status": 500})
        result = _run(self.engine.handle_api_failure(entry, cdp=cdp, capture_manager=capture))
        self.assertEqual(result.action, NetworkHealingAction.RETRY_5XX)
        self.assertFalse(result.success)

    def test_5xx_mock_fallback_after_consecutive(self):
        entry = {"url": "https://x.com/api", "status": 500}
        cdp = _FakeCDP()
        capture = _FakeCapture(entry={"status": 500})
        # 连续 4 次 5xx → 第 4 次触发 mock 降级
        for _ in range(4):
            result = _run(
                self.engine.handle_api_failure(entry, cdp=cdp, capture_manager=capture)
            )
        self.assertEqual(result.action, NetworkHealingAction.MOCK_FALLBACK)
        self.assertTrue(result.success)


class TestHandleNetworkDisconnect(unittest.TestCase):

    def setUp(self):
        self.engine = NetworkHealingEngine()
        self._patcher = mock.patch(
            "core.network_healing.asyncio.sleep", new=_noop_sleep
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_missing_cdp_or_url(self):
        result = _run(self.engine.handle_network_disconnect(None, ""))
        self.assertFalse(result.success)
        self.assertIn("无法重放", result.message)

    def test_replay_success(self):
        cdp = _FakeCDP()
        result = _run(self.engine.handle_network_disconnect(cdp, "https://x.com/api"))
        self.assertEqual(result.action, NetworkHealingAction.REPLAY_REQUEST)
        self.assertTrue(result.success)
        self.assertEqual(self.engine.get_stats()["replay_success"], 1)


if __name__ == "__main__":
    unittest.main()
