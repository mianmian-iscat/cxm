"""test_data_healing.py — 数据自愈引擎单元测试"""

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.data_healing import (
    DataHealingEngine,
    DataHealingAction,
    DataHealingResult,
    DataFreshnessSpec,
)


async def _noop_sleep(*args, **kwargs):
    return None


class _FakeCDP:
    """可配置返回值的 CDP 桩"""

    def __init__(self, eval_return=True):
        self._eval_return = eval_return
        self.calls = []

    async def evaluate(self, js):
        self.calls.append(js)
        if callable(self._eval_return):
            return self._eval_return(js)
        return self._eval_return


def _run(coro):
    # 独立事件循环 + 结束后恢复全新循环，避免污染其他测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestIsSessionExpired(unittest.TestCase):

    def test_detects_session_keywords(self):
        for msg in ("session expired", "登录态失效", "401 unauthorized", "token invalid"):
            self.assertTrue(DataHealingEngine._is_session_expired(msg))

    def test_non_session_error(self):
        self.assertFalse(DataHealingEngine._is_session_expired("element not found"))

    def test_empty(self):
        self.assertFalse(DataHealingEngine._is_session_expired(""))


class TestHealDataInvalid(unittest.TestCase):

    def setUp(self):
        self._patcher = mock.patch("core.data_healing.asyncio.sleep", new=_noop_sleep)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_fallback_data_success(self):
        cdp = _FakeCDP(eval_return=True)
        engine = DataHealingEngine(cdp=cdp)
        input_data = {
            "data_fallback": {
                "field_path": "seller.id",
                "alternatives": ["A123", "B456"],
            }
        }
        result = _run(engine.heal_data_invalid({"error": "data invalid"}, input_data))
        self.assertEqual(result.action, DataHealingAction.FALLBACK_DATA)
        self.assertTrue(result.success)
        self.assertEqual(engine.get_stats()["fallback_switches"], 1)

    def test_fallback_no_alternatives(self):
        cdp = _FakeCDP(eval_return=True)
        engine = DataHealingEngine(cdp=cdp)
        input_data = {"data_fallback": {"field_path": "x", "alternatives": []}}
        # 无备选 → 继续兜底刷新（有 cdp → FRESHNESS_REFRESH 成功）
        result = _run(engine.heal_data_invalid({"error": "bad"}, input_data))
        self.assertEqual(result.action, DataHealingAction.FRESHNESS_REFRESH)

    def test_api_reset_success(self):
        cdp = _FakeCDP(eval_return={"ok": True, "status": 200, "data": {"reset": 1}})
        engine = DataHealingEngine(cdp=cdp)
        input_data = {"data_reset": {"url": "https://x.com/reset", "method": "POST"}}
        result = _run(engine.heal_data_invalid({"error": "bad"}, input_data))
        self.assertEqual(result.action, DataHealingAction.API_RESET)
        self.assertTrue(result.success)
        self.assertEqual(engine.get_stats()["api_resets_success"], 1)

    def test_api_reset_failure(self):
        cdp = _FakeCDP(eval_return={"ok": False, "status": 500})
        engine = DataHealingEngine(cdp=cdp)
        input_data = {"data_reset": {"url": "https://x.com/reset"}}
        result = _run(engine.heal_data_invalid({"error": "bad"}, input_data))
        self.assertEqual(result.action, DataHealingAction.API_RESET)
        self.assertFalse(result.success)

    def test_page_refresh_fallback_no_cdp(self):
        engine = DataHealingEngine(cdp=None)
        result = _run(engine.heal_data_invalid({"error": "bad"}, {}))
        self.assertEqual(result.action, DataHealingAction.NONE)
        self.assertIn("无 CDP", result.message)

    def test_page_refresh_fallback_with_cdp(self):
        cdp = _FakeCDP(eval_return=True)
        engine = DataHealingEngine(cdp=cdp)
        result = _run(engine.heal_data_invalid({"error": "bad"}, {}))
        self.assertEqual(result.action, DataHealingAction.FRESHNESS_REFRESH)
        self.assertTrue(result.success)

    def test_duration_ms_populated(self):
        cdp = _FakeCDP(eval_return=True)
        engine = DataHealingEngine(cdp=cdp)
        result = _run(engine.heal_data_invalid({"error": "bad"}, {}))
        self.assertGreaterEqual(result.duration_ms, 0)


class TestFreshnessCheck(unittest.TestCase):

    def setUp(self):
        self._patcher = mock.patch("core.data_healing.asyncio.sleep", new=_noop_sleep)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_skip_when_no_check_api(self):
        engine = DataHealingEngine(cdp=_FakeCDP())
        results = _run(engine.check_data_freshness([{"field_path": "x"}]))
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(engine.get_stats()["freshness_checks"], 1)

    def test_no_cdp_skips(self):
        engine = DataHealingEngine(cdp=None)
        results = _run(engine.check_data_freshness([{"field_path": "x", "check_api": "http://a"}]))
        self.assertTrue(results[0].success)

    def test_api_unreachable_fails(self):
        cdp = _FakeCDP(eval_return={"ok": False, "error": "network"})
        engine = DataHealingEngine(cdp=cdp)
        results = _run(engine.check_data_freshness(
            [{"field_path": "seller", "check_api": "https://x.com/check"}]
        ))
        self.assertFalse(results[0].success)
        self.assertEqual(engine.get_stats()["freshness_failures"], 1)

    def test_api_ok_passes(self):
        cdp = _FakeCDP(eval_return={"ok": True, "data": {"valid": True}, "status": 200})
        engine = DataHealingEngine(cdp=cdp)
        results = _run(engine.check_data_freshness(
            [{"field_path": "seller", "check_api": "https://x.com/check"}]
        ))
        self.assertTrue(results[0].success)

    def test_multiple_specs(self):
        cdp = _FakeCDP(eval_return={"ok": True, "data": {}, "status": 200})
        engine = DataHealingEngine(cdp=cdp)
        results = _run(engine.check_data_freshness([
            {"field_path": "a"},
            {"field_path": "b"},
        ]))
        self.assertEqual(len(results), 2)


class TestDataFreshnessSpec(unittest.TestCase):

    def test_defaults(self):
        spec = DataFreshnessSpec(field_path="x")
        self.assertEqual(spec.check_api, "")
        self.assertEqual(spec.fallback_values, [])


class TestRefreshCookies(unittest.TestCase):

    def setUp(self):
        self._patcher = mock.patch("core.data_healing.asyncio.sleep", new=_noop_sleep)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_no_cdp(self):
        engine = DataHealingEngine(cdp=None)
        result = _run(engine._refresh_cookies())
        self.assertEqual(result.action, DataHealingAction.COOKIE_REFRESH)
        self.assertFalse(result.success)
        self.assertIn("无 CDP", result.message)


if __name__ == "__main__":
    unittest.main()
