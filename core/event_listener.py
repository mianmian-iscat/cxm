"""
event_listener.py — CDP 事件监听器

负责：
- 监听 Network 请求/响应事件，维护请求状态机
- 监听 Console 日志（Runtime.consoleAPICalled）
- 监听 DOM 变更（MutationObserver 注入）
- 提供 wait_for_request() / wait_for_console() 等异步等待工具
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CapturedRequest:
    request_id: str
    method: str
    url: str
    request_body: Any = None       # dict（JSON）或 str
    status: Optional[int] = None
    response_body: Any = None      # dict（JSON）或 str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.end_time:
            return int((self.end_time - self.start_time) * 1000)
        return None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "duration": self.duration_ms,
            "requestBody": self.request_body,
            "responseBody": self.response_body,
        }


@dataclass
class ConsoleEntry:
    level: str          # log / warn / error / info
    text: str
    timestamp: float = field(default_factory=time.time)


class EventListener:
    """
    CDP 事件监听器。
    依赖 CDPClient，在其基础上维护业务层的事件状态。
    """

    def __init__(self, cdp_client, url_filter: str = None):
        self._client = cdp_client
        self._url_filter = url_filter
        self._requests: Dict[str, CapturedRequest] = {}   # request_id -> CapturedRequest
        self._console_logs: List[ConsoleEntry] = []
        self._request_waiters: List[tuple] = []           # (pattern, Future)
        self._dom_change_callbacks: List[Callable] = []

    def start(self):
        """注册所有 CDP 事件监听"""
        self._client.on("Network.requestWillBeSent", self._on_request)
        self._client.on("Network.responseReceived", self._on_response)
        self._client.on("Network.loadingFinished", self._on_loading_finished)
        self._client.on("Network.loadingFailed", self._on_loading_failed)
        self._client.on("Runtime.consoleAPICalled", self._on_console)

    def stop(self):
        """取消所有监听"""
        self._client.off("Network.requestWillBeSent", self._on_request)
        self._client.off("Network.responseReceived", self._on_response)
        self._client.off("Network.loadingFinished", self._on_loading_finished)
        self._client.off("Network.loadingFailed", self._on_loading_failed)
        self._client.off("Runtime.consoleAPICalled", self._on_console)

    # ── 网络事件处理 ──

    def _on_request(self, params: dict):
        req = params.get("request", {})
        url = req.get("url", "")
        if self._url_filter and self._url_filter not in url:
            return
        request_id = params["requestId"]
        body = req.get("postData")
        self._requests[request_id] = CapturedRequest(
            request_id=request_id,
            method=req.get("method", "GET"),
            url=url,
            request_body=self._try_parse_json(body),
        )

    def _on_response(self, params: dict):
        req = self._requests.get(params["requestId"])
        if req:
            req.status = params.get("response", {}).get("status")

    async def _on_loading_finished(self, params: dict):
        request_id = params["requestId"]
        req = self._requests.get(request_id)
        if not req:
            return
        req.end_time = time.time()

        # 获取响应体
        try:
            body = await self._client.get_response_body(request_id)
            req.response_body = self._try_parse_json(body)
        except Exception:
            req.response_body = None

        # 通知等待者
        self._notify_waiters(req)

    def _on_loading_failed(self, params: dict):
        req = self._requests.get(params["requestId"])
        if req:
            req.end_time = time.time()
            req.status = -1

    # ── Console 日志 ──

    def _on_console(self, params: dict):
        level = params.get("type", "log")
        args = params.get("args", [])
        text = " ".join(
            str(a.get("value", a.get("description", ""))) for a in args
        )
        self._console_logs.append(ConsoleEntry(level=level, text=text))

    # ── 等待工具 ──

    async def wait_for_request(self, url_pattern: str, timeout: float = 10.0) -> CapturedRequest:
        """等待匹配 url_pattern 的请求完成（含响应体）"""
        # 先检查已有完成的请求
        for req in self._requests.values():
            if url_pattern in req.url and req.end_time is not None:
                return req

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._request_waiters.append((url_pattern, fut))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"等待接口超时（{timeout}s）: {url_pattern}")
        finally:
            self._request_waiters = [(p, f) for p, f in self._request_waiters if f is not fut]

    def _notify_waiters(self, req: CapturedRequest):
        for pattern, fut in self._request_waiters:
            if pattern in req.url and not fut.done():
                fut.set_result(req)

    # ── 查询接口 ──

    def get_requests(self) -> List[CapturedRequest]:
        """返回所有已完成的请求"""
        return [r for r in self._requests.values() if r.end_time is not None]

    def get_console_logs(self, level: str = None) -> List[ConsoleEntry]:
        if level:
            return [e for e in self._console_logs if e.level == level]
        return list(self._console_logs)

    def get_errors(self) -> List[ConsoleEntry]:
        return self.get_console_logs("error")

    # ── 工具 ──

    @staticmethod
    def _try_parse_json(text: str) -> Any:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return text
