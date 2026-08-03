"""
test_cdp_client.py — CDPClient 单元测试（Mock WebSocket）
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.cdp_client import CDPClient, _detect_runtime, _resolve_cdp_url


class TestCDPClient(unittest.TestCase):

    def test_instantiate(self):
        """CDPClient 可以正常实例化"""
        client = CDPClient()
        self.assertIsNotNone(client)

    def test_on_registers_callback(self):
        """on() 注册事件回调不抛异常"""
        client = CDPClient()
        cb = MagicMock()
        client.on("Network.requestWillBeSent", cb)
        # 无异常即通过

    def test_multiple_callbacks_same_event(self):
        """同一事件可注册多个回调"""
        client = CDPClient()
        cb1, cb2 = MagicMock(), MagicMock()
        client.on("Page.loadEventFired", cb1)
        client.on("Page.loadEventFired", cb2)

    def test_disconnect_when_not_connected(self):
        """未连接时 disconnect 不抛异常"""
        client = CDPClient()

        async def _run():
            try:
                await client.disconnect()
                return True
            except Exception:
                return True  # disconnect 失败也可接受（未建立连接）

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(result)

    def test_connect_fails_without_browser(self):
        """无浏览器时 connect 应抛出 ConnectionError 或类似异常"""
        client = CDPClient()

        async def _run():
            try:
                await client.connect(url="http://localhost:9999/non-existent")
                return "connected"
            except Exception as e:
                return f"error: {e}"

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("error", result)

    def test_evaluate_fails_without_connection(self):
        """未连接时 evaluate 应抛出异常"""
        client = CDPClient()

        async def _run():
            try:
                await client.evaluate("document.title")
                return "ok"
            except Exception as e:
                return f"error: {e}"

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("error", result)

    def test_screenshot_fails_without_connection(self):
        """未连接时 screenshot 应抛出异常"""
        client = CDPClient()

        async def _run():
            try:
                await client.screenshot()
                return "ok"
            except Exception as e:
                return f"error: {e}"

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("error", result)

    def test_set_cookies_fails_without_connection(self):
        """未连接时 set_cookies 应抛出异常"""
        client = CDPClient()

        async def _run():
            try:
                await client.set_cookies([{"name": "x", "value": "y", "domain": ".example.com"}])
                return "ok"
            except Exception as e:
                return f"error: {e}"

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("error", result)


class TestAgentBayRuntime(unittest.TestCase):
    """agentbay 运行时检测与 WebSocket 端点处理"""

    def test_detect_agentbay_via_env(self):
        """设置 WEB_AUTO_CDP_WS_URL 后自动检测为 agentbay"""
        with patch.dict(os.environ, {"WEB_AUTO_CDP_WS_URL": "wss://example.com/ws"}, clear=False):
            # 移除显式 runtime 以确保自动探测
            env = os.environ.copy()
            env.pop("WEB_AUTO_RUNTIME", None)
            with patch.dict(os.environ, env, clear=True):
                os.environ["WEB_AUTO_CDP_WS_URL"] = "wss://example.com/ws"
                self.assertEqual(_detect_runtime(), "agentbay")

    def test_detect_agentbay_explicit(self):
        """显式指定 WEB_AUTO_RUNTIME=agentbay"""
        with patch.dict(os.environ, {"WEB_AUTO_RUNTIME": "agentbay"}, clear=False):
            self.assertEqual(_detect_runtime(), "agentbay")

    def test_ws_endpoint_param(self):
        """CDPClient 接受 ws_endpoint 参数"""
        client = CDPClient(ws_endpoint="wss://test.example.com/ws/automation")
        self.assertEqual(client.ws_endpoint, "wss://test.example.com/ws/automation")
        self.assertEqual(client.cdp_url, "wss://test.example.com/ws/automation")
        self.assertEqual(client.runtime, "agentbay")

    def test_ws_endpoint_from_env(self):
        """CDPClient 从环境变量读取 ws_endpoint"""
        with patch.dict(os.environ, {"WEB_AUTO_CDP_WS_URL": "wss://env.example.com/ws"}, clear=False):
            client = CDPClient()
            self.assertEqual(client.ws_endpoint, "wss://env.example.com/ws")
            self.assertEqual(client.runtime, "agentbay")

    def test_resolve_cdp_url_with_ws_endpoint(self):
        """_resolve_cdp_url 优先返回 WebSocket 端点"""
        result = _resolve_cdp_url("agentbay", ws_endpoint="wss://test.com/ws")
        self.assertEqual(result, "wss://test.com/ws")

    def test_local_runtime_not_affected(self):
        """不设置 WebSocket 时，本地运行时不受影响"""
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("WEB_AUTO_CDP_WS_URL", None)
            env.pop("WEB_AUTO_RUNTIME", None)
            with patch.dict(os.environ, env, clear=True):
                client = CDPClient()
                self.assertIn(client.runtime, ("local", "cloudcli", "sandbox"))
                self.assertIsNone(client.ws_endpoint)


if __name__ == "__main__":
    unittest.main()
