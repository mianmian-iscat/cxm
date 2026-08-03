"""test_capture_manager.py — 网络抓包管理器单元测试"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capture_manager import CaptureManager, _try_json


class _FakeCDP:
    """记录事件处理器并支持手动触发的 CDP 桩"""

    def __init__(self, body=""):
        self.handlers = {}
        self.sent = []
        self._body = body

    def on(self, event, cb):
        self.handlers[event] = cb

    async def _send_cmd(self, cmd, params):
        self.sent.append((cmd, params))

    async def get_response_body(self, req_id):
        return self._body

    def fire(self, event, params):
        self.handlers[event](params)


def _run(coro):
    # 独立事件循环 + 结束后恢复全新循环，避免污染其他测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestTryJson(unittest.TestCase):

    def test_valid_json(self):
        self.assertEqual(_try_json('{"a": 1}'), {"a": 1})

    def test_invalid_json_returns_raw(self):
        self.assertEqual(_try_json("not json"), "not json")

    def test_empty_returns_none(self):
        self.assertIsNone(_try_json(""))
        self.assertIsNone(_try_json(None))


class TestStartAndCapture(unittest.TestCase):

    def _make(self, **kw):
        cdp = _FakeCDP(**kw)
        cap = CaptureManager(cdp)
        return cdp, cap

    def _full_cycle(self, cdp, cap, req_id="r1", url="https://x.com/mtop/list",
                    status=200, cached_body='{"ok":true}'):
        cdp.fire("Network.requestWillBeSent",
                 {"requestId": req_id, "request": {"method": "GET", "url": url}})
        cdp.fire("Network.responseReceived",
                 {"requestId": req_id, "response": {"status": status}})
        cdp.fire("Network.loadingFinished",
                 {"requestId": req_id, "_cachedBody": cached_body})

    def test_start_enables_network_and_registers_handlers(self):
        cdp, cap = self._make()
        _run(cap.start(url_filter="mtop"))
        self.assertIn("Network.requestWillBeSent", cdp.handlers)
        self.assertEqual(cdp.sent[0][0], "enableNetwork")

    def test_full_request_cycle_captured(self):
        cdp, cap = self._make()
        _run(cap.start())
        self._full_cycle(cdp, cap)
        reqs = cap.get_captured_requests()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["status"], 200)
        self.assertEqual(reqs[0]["responseBody"], {"ok": True})

    def test_pending_request_excluded_from_output(self):
        cdp, cap = self._make()
        _run(cap.start())
        # 只有 request，没有 response → status 为 None，不计入输出
        cdp.fire("Network.requestWillBeSent",
                 {"requestId": "r1", "request": {"method": "GET", "url": "https://x/y"}})
        self.assertEqual(cap.get_captured_requests(), [])

    def test_get_api_entry_match(self):
        cdp, cap = self._make()
        _run(cap.start())
        self._full_cycle(cdp, cap, url="https://x.com/mtop/order/list")
        entry = cap.get_api_entry("mtop/order")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], 200)

    def test_get_api_entry_no_match(self):
        cdp, cap = self._make()
        _run(cap.start())
        self._full_cycle(cdp, cap)
        self.assertIsNone(cap.get_api_entry("nonexistent"))

    def test_response_body_truncation(self):
        cdp, cap = _FakeCDP(), None
        cap = CaptureManager(cdp, max_response_size_kb=1)
        _run(cap.start())
        big = "x" * 3000  # > 1KB
        self._full_cycle(cdp, cap, cached_body=big)
        reqs = cap.get_captured_requests()
        self.assertTrue(reqs[0].get("responseBodyTruncated"))

    def test_last_api_entry_property(self):
        cdp, cap = self._make()
        cap.last_api_entry = {"url": "x"}
        self.assertEqual(cap.last_api_entry["url"], "x")


class TestWaitForApi(unittest.TestCase):

    def test_returns_already_completed(self):
        cdp = _FakeCDP()
        cap = CaptureManager(cdp)

        async def scenario():
            await cap.start()
            cdp.fire("Network.requestWillBeSent",
                     {"requestId": "r1", "request": {"method": "GET", "url": "https://x/mtop/list"}})
            cdp.fire("Network.responseReceived",
                     {"requestId": "r1", "response": {"status": 200}})
            cdp.fire("Network.loadingFinished",
                     {"requestId": "r1", "_cachedBody": '{"ok":1}'})
            return await cap.wait_for_api("mtop/list", timeout_sec=1)

        entry = _run(scenario())
        self.assertEqual(entry["status"], 200)
        self.assertEqual(cap.last_api_entry, entry)

    def test_timeout_raises(self):
        cdp = _FakeCDP()
        cap = CaptureManager(cdp)

        async def scenario():
            await cap.start()
            return await cap.wait_for_api("never", timeout_sec=0.05)

        with self.assertRaises(TimeoutError):
            _run(scenario())

    def test_waiter_notified_on_finish(self):
        cdp = _FakeCDP()
        cap = CaptureManager(cdp)

        async def scenario():
            await cap.start()
            task = asyncio.create_task(cap.wait_for_api("mtop/list", timeout_sec=2))
            await asyncio.sleep(0)  # 让 waiter 注册
            cdp.fire("Network.requestWillBeSent",
                     {"requestId": "r1", "request": {"method": "GET", "url": "https://x/mtop/list"}})
            cdp.fire("Network.responseReceived",
                     {"requestId": "r1", "response": {"status": 201}})
            cdp.fire("Network.loadingFinished",
                     {"requestId": "r1", "_cachedBody": '{"created":1}'})
            return await task

        entry = _run(scenario())
        self.assertEqual(entry["status"], 201)


class TestGetAllApiEntries(unittest.TestCase):
    """capture_manager.get_all_api_entries 单元测试"""

    def setUp(self):
        self.cdp = _FakeCDP()
        self.cap = CaptureManager(self.cdp)
        # 手动注入 3 个已完成的 entry
        self.cap._capture_map = {
            "r1": {
                "requestId": "r1", "method": "GET",
                "url": "https://x/api/afd/review/task/main/list",
                "status": 200, "duration": 120,
                "requestBody": None, "responseBody": {"success": True, "data": []},
                "_start": 1000.0,
            },
            "r2": {
                "requestId": "r2", "method": "POST",
                "url": "https://x/api/afd/review/task/main/list",
                "status": 200, "duration": 80,
                "requestBody": None, "responseBody": {"success": True, "data": [1]},
                "_start": 1005.0,
            },
            "r3": {
                "requestId": "r3", "method": "GET",
                "url": "https://x/api/workflow2/link/run",
                "status": 500, "duration": 300,
                "requestBody": None, "responseBody": {"success": False},
                "_start": 1002.0,
            },
        }

    def test_empty_pattern_returns_all(self):
        result = self.cap.get_all_api_entries("")
        self.assertEqual(len(result), 3)
        # 按 _start 升序
        self.assertEqual([e["requestId"] for e in result], ["r1", "r3", "r2"])

    def test_pattern_filters(self):
        result = self.cap.get_all_api_entries("main/list")
        self.assertEqual(len(result), 2)
        self.assertEqual([e["requestId"] for e in result], ["r1", "r2"])

    def test_pattern_no_match(self):
        result = self.cap.get_all_api_entries("no_such_api")
        self.assertEqual(result, [])

    def test_skips_pending_entries(self):
        # 注入一个尚未收到响应的 entry
        self.cap._capture_map["r4"] = {
            "requestId": "r4", "method": "GET",
            "url": "https://x/api/foo",
            "status": None, "duration": 0,
            "_start": 999.0,
        }
        result = self.cap.get_all_api_entries("")
        self.assertEqual(len(result), 3)
        self.assertNotIn("r4", [e["requestId"] for e in result])

    def test_time_ordering(self):
        # 乱序注入
        self.cap._capture_map = {
            "a": {"requestId": "a", "url": "https://x/a", "status": 200, "_start": 3},
            "b": {"requestId": "b", "url": "https://x/b", "status": 200, "_start": 1},
            "c": {"requestId": "c", "url": "https://x/c", "status": 200, "_start": 2},
        }
        result = self.cap.get_all_api_entries("")
        self.assertEqual([e["requestId"] for e in result], ["b", "c", "a"])


if __name__ == "__main__":
    unittest.main()
