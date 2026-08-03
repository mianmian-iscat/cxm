"""
network_healing.py — 网络层自愈引擎 (维度4)

对 API 请求/响应级别的异常进行自动检测与恢复：
- 5xx 状态码自动重试（指数退避）
- API 响应体结构异常检测与适配
- 慢请求检测与自适应降速
- mockNetwork 自动降级
- 网络断线重连后请求重放

使用方式：
    from core.network_healing import NetworkHealingEngine
    engine = NetworkHealingEngine()
    result = await engine.handle_api_failure(entry, cdp)
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class NetworkHealingAction(Enum):
    NONE = "none"
    RETRY_5XX = "retry_5xx"
    RESPONSE_ADAPT = "response_adapt"
    SLOW_REQUEST_THROTTLE = "slow_request_throttle"
    MOCK_FALLBACK = "mock_fallback"
    REPLAY_REQUEST = "replay_request"


@dataclass
class NetworkHealingResult:
    action: NetworkHealingAction = NetworkHealingAction.NONE
    success: bool = False
    message: str = ""
    duration_ms: int = 0
    retry_count: int = 0
    adapted_response: dict = field(default_factory=dict)


@dataclass
class _ApiBaseline:
    """API 性能基线（滑动窗口）"""
    url_pattern: str
    durations: list = field(default_factory=list)
    window_size: int = 20

    def record(self, duration_ms: int):
        self.durations.append(duration_ms)
        if len(self.durations) > self.window_size:
            self.durations = self.durations[-self.window_size:]

    @property
    def p95(self) -> float:
        if not self.durations:
            return 0.0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def mean(self) -> float:
        if not self.durations:
            return 0.0
        return sum(self.durations) / len(self.durations)


class NetworkHealingEngine:
    """
    网络层自愈引擎：监控 API 请求/响应异常并自动恢复。

    核心能力：
    1. 5xx 自动重试（指数退避 3s/10s/30s）
    2. API 响应体结构变化检测与适配
    3. 慢请求 P95 检测 + 自适应降速
    4. 被测接口不可用时自动 mockNetwork 降级
    """

    # 5xx 重试退避序列（秒）
    _RETRY_BACKOFF = [3, 10, 30]
    # 慢请求倍数阈值（P95 > baseline * 此倍数时触发降速）
    _SLOW_RATIO_THRESHOLD = 2.5
    # mock 降级最大次数
    _MAX_MOCK_FALLBACK = 3

    def __init__(self):
        self._baselines: dict[str, _ApiBaseline] = {}
        self._stats = {
            "retries_5xx": 0,
            "retries_5xx_success": 0,
            "response_adapts": 0,
            "slow_throttles": 0,
            "mock_fallbacks": 0,
            "replay_success": 0,
        }
        self._mock_count = 0
        self._consecutive_5xx: dict[str, int] = {}

    # ── 主入口 ──

    async def handle_api_failure(
        self,
        api_entry: dict,
        cdp=None,
        capture_manager=None,
    ) -> NetworkHealingResult:
        """
        处理 API 级别的失败，按策略链尝试恢复。

        Args:
            api_entry: CaptureManager 中的 API entry
            cdp: CDPClient 实例（用于重放请求）
            capture_manager: CaptureManager 实例（用于检查状态）

        Returns:
            NetworkHealingResult
        """
        start = time.time()
        url = api_entry.get("url", "")
        status = api_entry.get("status")
        url_key = self._normalize_url(url)

        # 记录基线
        duration = api_entry.get("duration", 0)
        if duration > 0:
            self._record_baseline(url_key, duration)

        # 策略1: 5xx 自动重试
        if status and 500 <= status < 600:
            result = await self._retry_5xx(url, status, cdp, capture_manager)
            result.duration_ms = int((time.time() - start) * 1000)
            return result

        # 策略2: 慢请求检测 + 自适应降速
        if duration > 0:
            throttle_result = self._check_slow_request(url_key, duration)
            if throttle_result.action != NetworkHealingAction.NONE:
                throttle_result.duration_ms = int((time.time() - start) * 1000)
                return throttle_result

        # 策略3: 响应体结构异常
        if api_entry.get("responseBody") is not None:
            adapt_result = self._check_response_anomaly(url_key, api_entry)
            if adapt_result.action != NetworkHealingAction.NONE:
                adapt_result.duration_ms = int((time.time() - start) * 1000)
                return adapt_result

        return NetworkHealingResult(
            message=f"API 失败无可用自愈策略: {url[:80]} status={status}"
        )

    async def handle_network_disconnect(self, cdp, failed_url: str = "") -> NetworkHealingResult:
        """
        网络断线后的请求重放。

        在 CDP 重连成功后调用，尝试重放最近失败的请求。
        """
        start = time.time()
        if not cdp or not failed_url:
            return NetworkHealingResult(message="无法重放: 缺少 CDP 或 URL")

        try:
            # 通过页面刷新重放（而非直接发 HTTP 请求）
            await cdp.evaluate("window.location.reload()")
            await asyncio.sleep(3)

            self._stats["replay_success"] += 1
            return NetworkHealingResult(
                action=NetworkHealingAction.REPLAY_REQUEST,
                success=True,
                message=f"网络重连后页面刷新成功: {failed_url[:60]}",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NetworkHealingResult(
                action=NetworkHealingAction.REPLAY_REQUEST,
                success=False,
                message=f"请求重放失败: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    def get_throttle_delay_ms(self) -> int:
        """
        获取当前建议的步骤间降速延迟（毫秒）。
        当检测到慢请求时，后续步骤应增加等待时间。
        """
        if self._stats["slow_throttles"] > 0:
            # 每次降速增加 1s，最多 5s
            return min(self._stats["slow_throttles"] * 1000, 5000)
        return 0

    def get_stats(self) -> dict:
        return dict(self._stats)

    # ── 5xx 重试 ──

    async def _retry_5xx(
        self, url: str, status: int, cdp, capture_manager
    ) -> NetworkHealingResult:
        """5xx 状态码自动重试（指数退避）"""
        url_key = self._normalize_url(url)
        consecutive = self._consecutive_5xx.get(url_key, 0) + 1
        self._consecutive_5xx[url_key] = consecutive

        self._stats["retries_5xx"] += 1

        # 连续 5xx 超过 3 次 → 降级为 mock
        if consecutive > 3:
            return await self._mock_fallback(url, cdp)

        # 指数退避重试
        for attempt, backoff_sec in enumerate(self._RETRY_BACKOFF[:consecutive]):
            try:
                await asyncio.sleep(backoff_sec)

                # 通过页面 reload 触发请求重试
                if cdp:
                    await cdp.evaluate("window.location.reload()")
                    await asyncio.sleep(2)

                    # 检查 capture_manager 中是否有新的成功请求
                    if capture_manager:
                        new_entry = capture_manager.get_api_entry(url_key)
                        if new_entry and new_entry.get("status") and new_entry["status"] < 500:
                            self._stats["retries_5xx_success"] += 1
                            self._consecutive_5xx[url_key] = 0
                            return NetworkHealingResult(
                                action=NetworkHealingAction.RETRY_5XX,
                                success=True,
                                message=f"5xx 重试成功 (attempt {attempt+1}): {url[:60]}",
                                retry_count=attempt + 1,
                            )
            except Exception:
                continue

        return NetworkHealingResult(
            action=NetworkHealingAction.RETRY_5XX,
            success=False,
            message=f"5xx 重试全部失败: {url[:60]} status={status}",
            retry_count=len(self._RETRY_BACKOFF),
        )

    # ── mock 降级 ──

    async def _mock_fallback(self, url: str, cdp) -> NetworkHealingResult:
        """被测接口不可用时，自动启用 mockNetwork 降级"""
        self._mock_count += 1
        if self._mock_count > self._MAX_MOCK_FALLBACK:
            return NetworkHealingResult(
                action=NetworkHealingAction.MOCK_FALLBACK,
                success=False,
                message="mock 降级次数超限，需要人工介入",
            )

        try:
            if cdp:
                # 通过 CDP mockNetwork 拦截失败接口
                await cdp._send_cmd("mockNetwork", {
                    "mode": "intercept",
                    "urlPattern": self._normalize_url(url),
                    "mockStatus": 200,
                    "mockBody": json.dumps({"data": [], "success": True, "message": "mock fallback"}),
                })
                self._stats["mock_fallbacks"] += 1
                return NetworkHealingResult(
                    action=NetworkHealingAction.MOCK_FALLBACK,
                    success=True,
                    message=f"接口 mock 降级: {url[:60]}",
                )
        except Exception as e:
            return NetworkHealingResult(
                action=NetworkHealingAction.MOCK_FALLBACK,
                success=False,
                message=f"mock 降级失败: {e}",
            )

        return NetworkHealingResult(
            action=NetworkHealingAction.MOCK_FALLBACK,
            success=False,
            message="无 CDP 实例，无法 mock",
        )

    # ── 慢请求检测 ──

    def _check_slow_request(self, url_key: str, duration_ms: int) -> NetworkHealingResult:
        """检测慢请求并触发降速"""
        baseline = self._baselines.get(url_key)
        if not baseline or len(baseline.durations) < 5:
            return NetworkHealingResult()

        p95 = baseline.p95
        if p95 > 0 and duration_ms > p95 * self._SLOW_RATIO_THRESHOLD:
            self._stats["slow_throttles"] += 1
            return NetworkHealingResult(
                action=NetworkHealingAction.SLOW_REQUEST_THROTTLE,
                success=True,
                message=f"慢请求检测: {duration_ms}ms > P95({p95:.0f}ms)*{self._SLOW_RATIO_THRESHOLD}",
            )

        return NetworkHealingResult()

    # ── 响应体异常 ──

    def _check_response_anomaly(self, url_key: str, entry: dict) -> NetworkHealingResult:
        """检测 API 响应体结构异常"""
        body = entry.get("responseBody")
        if body is None:
            return NetworkHealingResult()

        # 检测常见异常模式
        anomalies = []

        # HTML 错误页（非 JSON API 应返回的数据）
        if isinstance(body, str) and ("<html" in body.lower() or "<!doctype" in body.lower()):
            anomalies.append("返回 HTML 错误页而非 JSON")

        # JSON 中包含 error/errorCode 字段
        if isinstance(body, dict):
            if body.get("error") or body.get("errorCode") or body.get("code", 0) not in (0, 200, "0", "200", "SUCCESS"):
                anomalies.append(f"JSON 错误码: {body.get('errorCode', body.get('code', ''))}")

        # 空数据（某些 API 不应返回空）
        if isinstance(body, dict) and body.get("data") == [] and body.get("total", 1) > 0:
            anomalies.append("data 为空但 total > 0")

        if anomalies:
            self._stats["response_adapts"] += 1
            return NetworkHealingResult(
                action=NetworkHealingAction.RESPONSE_ADAPT,
                success=False,  # 标记但不自动修复，让上层决策
                message=f"响应体异常: {'; '.join(anomalies)}",
                adapted_response={"anomalies": anomalies, "url": entry.get("url", "")},
            )

        return NetworkHealingResult()

    # ── 辅助 ──

    def _record_baseline(self, url_key: str, duration_ms: int):
        if url_key not in self._baselines:
            self._baselines[url_key] = _ApiBaseline(url_pattern=url_key)
        self._baselines[url_key].record(duration_ms)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """提取 URL 路径部分作为 key（去除域名和查询参数）"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.path or url[:80]
        except Exception:
            return url[:80]
