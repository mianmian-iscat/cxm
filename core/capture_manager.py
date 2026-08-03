"""
capture_manager.py — 网络抓包管理器

从 impl.py 抽取的网络层逻辑：
- 启动 Network domain 监听（request/response/finished）
- 存储抓包数据（capture_map）
- waitForAPI 等待机制
- 异步 body fetch + 大小限制
- 最终抓包结果整理

使用方式:
    from core.capture_manager import CaptureManager
    capture = CaptureManager(cdp, max_response_size_kb=50)
    await capture.start(url_filter="mtop")
    entry = await capture.wait_for_api("mtop/order/list", timeout_sec=10)
    requests = capture.get_captured_requests()
"""

import asyncio
import json
import time
from typing import Optional


class CaptureManager:
    """
    网络抓包管理器：封装 CDP Network 事件监听与数据存储。
    """

    def __init__(self, cdp, max_response_size_kb: int = 50):
        self._cdp = cdp
        self._max_response_size_kb = max_response_size_kb
        self._capture_map: dict = {}  # requestId -> 请求数据
        self._api_waiters: list = []  # (urlPattern, Future)
        self._body_tasks: list = []
        self._last_api_entry: Optional[dict] = None
        self._enabled = False

    @property
    def last_api_entry(self) -> Optional[dict]:
        """最近一次 waitForAPI 命中的 entry。"""
        return self._last_api_entry

    @last_api_entry.setter
    def last_api_entry(self, value):
        self._last_api_entry = value

    @property
    def capture_map(self) -> dict:
        return self._capture_map

    async def start(self, url_filter: str = "", capture_body: bool = True):
        """启动网络抓包监听。"""
        self._enabled = True
        self._capture_body = capture_body
        await self._cdp._send_cmd("enableNetwork", {"urlFilter": url_filter})

        def _on_request(params):
            req_id = params.get("requestId")
            if not req_id:
                return
            req = params.get("request", {})
            self._capture_map[req_id] = {
                "method": req.get("method", "GET"),
                "url": req.get("url", ""),
                "requestBody": _try_json(req.get("postData")),
                "status": None,
                "responseBody": None,
                "duration": 0,
                "_start": time.time(),
            }

        def _on_response(params):
            req_id = params.get("requestId")
            if req_id and req_id in self._capture_map:
                self._capture_map[req_id]["status"] = \
                    params.get("response", {}).get("status")

        def _on_finished(params):
            req_id = params.get("requestId")
            if req_id and req_id in self._capture_map:
                entry = self._capture_map[req_id]
                entry["duration"] = int((time.time() - entry["_start"]) * 1000)
                if self._capture_body:
                    cached = params.get("_cachedBody")
                    if cached is not None:
                        if self._max_response_size_kb > 0:
                            cached_str = json.dumps(cached) if not isinstance(cached, str) else cached
                            if len(cached_str) > self._max_response_size_kb * 1024:
                                entry["responseBodyTruncated"] = True
                                entry["responseBodySizeKb"] = round(len(cached_str) / 1024, 1)
                                cached = _try_json(cached_str[:self._max_response_size_kb * 1024])
                        entry["responseBody"] = _try_json(cached)
                        self._notify_waiters(entry)
                    else:
                        t = asyncio.create_task(
                            self._fetch_body_and_notify(req_id, entry)
                        )
                        self._body_tasks.append(t)
                else:
                    self._notify_waiters(entry)

        self._cdp.on("Network.requestWillBeSent", _on_request)
        self._cdp.on("Network.responseReceived", _on_response)
        self._cdp.on("Network.loadingFinished", _on_finished)

    async def wait_for_api(self, url_pattern: str, timeout_sec: float) -> dict:
        """等待特定接口完成（含响应体）。"""
        # 先检查已完成的请求
        for entry in self._capture_map.values():
            if url_pattern in entry.get("url", "") and entry.get("status") is not None:
                self._last_api_entry = entry
                return entry

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._api_waiters.append((url_pattern, fut))
        try:
            entry = await asyncio.wait_for(fut, timeout=timeout_sec)
            self._last_api_entry = entry
            return entry
        except asyncio.TimeoutError:
            raise TimeoutError(f"等待接口超时（{timeout_sec}s）: {url_pattern}")
        finally:
            self._api_waiters[:] = [(p, f) for p, f in self._api_waiters if f is not fut]

    async def flush_pending_bodies(self, timeout: float = 5.0):
        """等待所有 body fetch 任务完成。"""
        if self._body_tasks:
            pending = [t for t in self._body_tasks if not t.done()]
            if pending:
                await asyncio.wait(pending, timeout=timeout)

    def get_captured_requests(self) -> list:
        """整理抓包结果，供输出和 artifacts 使用。"""
        requests_out = []
        for entry in self._capture_map.values():
            if entry.get("status") is not None:
                req_rec = {
                    "method": entry["method"],
                    "url": entry["url"],
                    "status": entry["status"],
                    "duration": entry["duration"],
                    "requestBody": entry["requestBody"],
                    "responseBody": entry["responseBody"],
                }
                if entry.get("responseBodyTruncated"):
                    req_rec["responseBodyTruncated"] = True
                    req_rec["responseBodySizeKb"] = entry.get("responseBodySizeKb")
                requests_out.append(req_rec)
        return requests_out

    def get_api_entry(self, url_pattern: str) -> Optional[dict]:
        """按 URL 模式获取已抓到的 API entry（用于 checkpoint 恢复）。"""
        for entry in self._capture_map.values():
            if url_pattern in entry.get("url", "") and entry.get("status") is not None:
                return entry
        return None

    def get_all_api_entries(self, url_pattern: str = "") -> list:
        """
        获取所有匹配的 API entry（按时间顺序，最早 → 最晚）。

        用于 assertAPI 的 captureAll=true 场景：需要拿到同一接口的全部响应
        （例如轮询接口被调用 N 次，或同 pattern 多接口并行触发）。

        Args:
            url_pattern: URL 关键词过滤；空字符串表示返回全部已完成的 entry。

        Returns:
            匹配的 entry 列表，每个 entry 包含 url/method/status/duration/
            requestBody/responseBody/responseBodyTruncated 等字段。
        """
        out = []
        for entry in self._capture_map.values():
            if entry.get("status") is None:
                # 尚未收到响应，跳过
                continue
            if url_pattern and url_pattern not in entry.get("url", ""):
                continue
            out.append(entry)
        # 按 _start 时间戳升序
        out.sort(key=lambda e: e.get("_start", 0))
        return out

    # ── 内部 ──

    def _notify_waiters(self, entry: dict):
        """通知所有匹配的 waitForAPI 等待者。"""
        url = entry.get("url", "")
        for pattern, fut in list(self._api_waiters):
            if pattern in url and not fut.done():
                fut.set_result(entry)

    async def _fetch_body_and_notify(self, req_id: str, entry: dict):
        """异步获取响应体后通知等待者。"""
        try:
            body = await self._cdp.get_response_body(req_id)
            if self._max_response_size_kb > 0 and body:
                if len(body) > self._max_response_size_kb * 1024:
                    entry["responseBodyTruncated"] = True
                    entry["responseBodySizeKb"] = round(len(body) / 1024, 1)
                    body = body[:self._max_response_size_kb * 1024]
            entry["responseBody"] = _try_json(body)
        except Exception:
            entry["responseBody"] = None
        self._notify_waiters(entry)


def _try_json(text):
    """尝试解析 JSON，失败返回原文。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text
