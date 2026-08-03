"""
data_healing.py — 数据自愈引擎 (维度6 + 维度3)

实装 SANDBOX_RESET + 数据新鲜度检测：
- 测试数据失效时通过 API 重置环境数据
- Cookie/Session 自动刷新
- data_fallback 声明式备选数据源
- 数据新鲜度预检（执行前验证数据有效性）

使用方式：
    from core.data_healing import DataHealingEngine
    engine = DataHealingEngine(cdp=cdp)
    result = await engine.heal_data_invalid(context)
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict


class DataHealingAction(Enum):
    NONE = "none"
    API_RESET = "api_reset"             # 通过 API 重置数据
    COOKIE_REFRESH = "cookie_refresh"   # Cookie/Session 刷新
    FALLBACK_DATA = "fallback_data"     # 切换到备选数据
    FRESHNESS_REFRESH = "freshness_refresh"  # 数据新鲜度刷新


@dataclass
class DataHealingResult:
    action: DataHealingAction = DataHealingAction.NONE
    success: bool = False
    message: str = ""
    duration_ms: int = 0
    new_data: dict = field(default_factory=dict)


@dataclass
class DataFreshnessSpec:
    """数据新鲜度声明（在 input JSON 中定义）"""
    field_path: str         # 数据字段路径（如 "seller_id"）
    check_api: str = ""     # 验证 API URL
    check_condition: str = ""  # 验证条件（JS 表达式）
    refresh_api: str = ""   # 刷新 API URL
    fallback_values: list = field(default_factory=list)  # 备选值列表


class DataHealingEngine:
    """
    数据自愈引擎：当测试数据失效时自动恢复。

    核心能力：
    1. 通过 API 调用重置测试环境数据
    2. Cookie/Session 自动重新注入
    3. data_fallback 声明式备选数据源切换
    4. 执行前数据新鲜度预检
    """

    def __init__(self, cdp=None, capture_manager=None):
        self._cdp = cdp
        self._capture = capture_manager
        self._stats = {
            "api_resets": 0,
            "api_resets_success": 0,
            "cookie_refreshes": 0,
            "fallback_switches": 0,
            "freshness_checks": 0,
            "freshness_failures": 0,
        }

    # ── SANDBOX_RESET 实装 ──

    async def heal_data_invalid(
        self,
        context: dict,
        input_data: dict = None,
    ) -> DataHealingResult:
        """
        处理 DATA_INVALID 类错误的自愈入口。

        策略链：
        1. data_fallback → 切换到备选数据
        2. cookie_refresh → 刷新 Cookie/Session
        3. api_reset → 通过 API 重置数据

        Args:
            context: 错误上下文（包含 error, step, selector 等）
            input_data: 原始 input JSON（可能包含 data_fallback 配置）

        Returns:
            DataHealingResult
        """
        start = time.time()
        input_data = input_data or {}

        # 策略1: data_fallback
        fallback = input_data.get("data_fallback")
        if fallback:
            result = await self._try_fallback_data(fallback, context)
            if result.success:
                result.duration_ms = int((time.time() - start) * 1000)
                return result

        # 策略2: Cookie 刷新
        if self._is_session_expired(context.get("error", "")):
            result = await self._refresh_cookies()
            if result.success:
                result.duration_ms = int((time.time() - start) * 1000)
                return result

        # 策略3: API 重置
        reset_config = input_data.get("data_reset")
        if reset_config:
            result = await self._api_reset_data(reset_config)
            result.duration_ms = int((time.time() - start) * 1000)
            return result

        # 通用策略：刷新页面让数据重新加载
        result = await self._page_refresh_recovery()
        result.duration_ms = int((time.time() - start) * 1000)
        return result

    # ── 数据新鲜度检测 ──

    async def check_data_freshness(
        self,
        freshness_specs: List[dict],
        input_data: dict = None,
    ) -> List[DataHealingResult]:
        """
        执行前数据新鲜度预检。

        Args:
            freshness_specs: data_freshness 声明列表
            input_data: 原始 input JSON

        Returns:
            每个声明的检测结果列表
        """
        results = []
        for spec_def in freshness_specs:
            spec = DataFreshnessSpec(
                field_path=spec_def.get("field_path", ""),
                check_api=spec_def.get("check_api", ""),
                check_condition=spec_def.get("check_condition", ""),
                refresh_api=spec_def.get("refresh_api", ""),
                fallback_values=spec_def.get("fallback_values", []),
            )
            self._stats["freshness_checks"] += 1
            result = await self._check_single_freshness(spec, input_data or {})
            if not result.success:
                self._stats["freshness_failures"] += 1
            results.append(result)
        return results

    # ── 策略实现 ──

    async def _try_fallback_data(self, fallback_config: dict, context: dict) -> DataHealingResult:
        """切换到备选数据源"""
        field_path = fallback_config.get("field_path", "")
        alternatives = fallback_config.get("alternatives", [])

        if not alternatives:
            return DataHealingResult(
                action=DataHealingAction.FALLBACK_DATA,
                message="无备选数据可切换",
            )

        # 尝试每个备选值
        for alt in alternatives:
            try:
                # 在页面中注入备选数据
                if self._cdp and field_path:
                    # 通过 JS 修改页面上的数据引用
                    inject_js = f"""(() => {{
                        // 尝试在表单中找到对应字段并填入备选值
                        const inputs = document.querySelectorAll('input, select, textarea');
                        for (const el of inputs) {{
                            if (el.name && el.name.includes({json.dumps(field_path.split('.')[-1])})) {{
                                const nativeSetter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                nativeSetter.call(el, {json.dumps(str(alt))});
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        return false;
                    }})()"""
                    success = await self._cdp.evaluate(inject_js)
                    if success:
                        self._stats["fallback_switches"] += 1
                        return DataHealingResult(
                            action=DataHealingAction.FALLBACK_DATA,
                            success=True,
                            message=f"已切换到备选数据: {field_path} = {alt}",
                            new_data={field_path: alt},
                        )
            except Exception:
                continue

        return DataHealingResult(
            action=DataHealingAction.FALLBACK_DATA,
            success=False,
            message=f"所有备选数据均不可用: {field_path}",
        )

    async def _refresh_cookies(self) -> DataHealingResult:
        """刷新 Cookie/Session"""
        if not self._cdp:
            return DataHealingResult(
                action=DataHealingAction.COOKIE_REFRESH,
                message="无 CDP 实例，无法刷新 Cookie",
            )

        try:
            # 通过 SSO warmup 恢复 session
            from core.browser_setup import ensure_alibaba_sso
            login_status = await self._cdp.check_login()
            target_url = login_status.get("currentUrl", "")
            await ensure_alibaba_sso(self._cdp, target_url, "")
            await asyncio.sleep(2)

            # 验证
            status2 = await self._cdp.check_login()
            if not status2.get("isLoginPage", False):
                self._stats["cookie_refreshes"] += 1
                return DataHealingResult(
                    action=DataHealingAction.COOKIE_REFRESH,
                    success=True,
                    message="Cookie/Session 已刷新",
                )
            return DataHealingResult(
                action=DataHealingAction.COOKIE_REFRESH,
                success=False,
                message="Cookie 刷新后仍在登录页",
            )
        except Exception as e:
            return DataHealingResult(
                action=DataHealingAction.COOKIE_REFRESH,
                success=False,
                message=f"Cookie 刷新异常: {e}",
            )

    async def _api_reset_data(self, reset_config: dict) -> DataHealingResult:
        """通过 API 重置测试数据"""
        reset_url = reset_config.get("url", "")
        reset_method = reset_config.get("method", "POST")
        reset_body = reset_config.get("body", {})

        if not reset_url or not self._cdp:
            return DataHealingResult(
                action=DataHealingAction.API_RESET,
                message="缺少重置 API 配置或 CDP 实例",
            )

        try:
            self._stats["api_resets"] += 1
            fetch_js = f"""
            (async () => {{
                try {{
                    const resp = await fetch({json.dumps(reset_url)}, {{
                        method: {json.dumps(reset_method)},
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: {json.dumps(json.dumps(reset_body))},
                        credentials: 'include',
                    }});
                    const data = await resp.json();
                    return {{ ok: resp.ok, status: resp.status, data: data }};
                }} catch (e) {{
                    return {{ ok: false, error: e.message }};
                }}
            }})()
            """
            result = await asyncio.wait_for(
                self._cdp.evaluate(fetch_js), timeout=15
            )
            if result and result.get("ok"):
                self._stats["api_resets_success"] += 1
                return DataHealingResult(
                    action=DataHealingAction.API_RESET,
                    success=True,
                    message=f"数据已重置: {reset_url[:60]}",
                    new_data=result.get("data", {}),
                )
            return DataHealingResult(
                action=DataHealingAction.API_RESET,
                success=False,
                message=f"数据重置 API 失败: status={result.get('status', '?')}",
            )
        except Exception as e:
            return DataHealingResult(
                action=DataHealingAction.API_RESET,
                success=False,
                message=f"数据重置异常: {e}",
            )

    async def _page_refresh_recovery(self) -> DataHealingResult:
        """通用兜底：刷新页面让数据重新加载"""
        if not self._cdp:
            return DataHealingResult(
                action=DataHealingAction.NONE,
                message="无 CDP 实例，无法刷新页面",
            )
        try:
            await self._cdp.evaluate("window.location.reload(true)")
            await asyncio.sleep(3)
            return DataHealingResult(
                action=DataHealingAction.FRESHNESS_REFRESH,
                success=True,
                message="页面已刷新，数据重新加载",
            )
        except Exception as e:
            return DataHealingResult(
                action=DataHealingAction.FRESHNESS_REFRESH,
                success=False,
                message=f"页面刷新失败: {e}",
            )

    async def _check_single_freshness(self, spec: DataFreshnessSpec, input_data: dict) -> DataHealingResult:
        """检查单个数据字段的新鲜度"""
        if not spec.check_api or not self._cdp:
            # 无检查 API 时直接视为通过
            return DataHealingResult(
                action=DataHealingAction.FRESHNESS_REFRESH,
                success=True,
                message=f"跳过新鲜度检查（无 check_api）: {spec.field_path}",
            )

        try:
            check_js = f"""
            (async () => {{
                try {{
                    const resp = await fetch({json.dumps(spec.check_api)}, {{ credentials: 'include' }});
                    const data = await resp.json();
                    return {{ ok: true, data: data, status: resp.status }};
                }} catch (e) {{
                    return {{ ok: false, error: e.message }};
                }}
            }})()
            """
            result = await asyncio.wait_for(
                self._cdp.evaluate(check_js), timeout=10
            )
            if not result or not result.get("ok"):
                return DataHealingResult(
                    action=DataHealingAction.FRESHNESS_REFRESH,
                    success=False,
                    message=f"数据新鲜度检查失败: {spec.field_path} → API 不可达",
                )

            # 评估检查条件
            data = result.get("data", {})
            if spec.check_condition:
                # 简单的 JS 条件评估
                eval_js = f"({spec.check_condition})({json.dumps(data)})"
                try:
                    valid = await self._cdp.evaluate(eval_js)
                    if not valid:
                        return DataHealingResult(
                            action=DataHealingAction.FRESHNESS_REFRESH,
                            success=False,
                            message=f"数据已失效: {spec.field_path} 不满足条件 '{spec.check_condition}'",
                        )
                except Exception:
                    pass  # 条件评估失败时视为通过

            return DataHealingResult(
                action=DataHealingAction.FRESHNESS_REFRESH,
                success=True,
                message=f"数据新鲜度正常: {spec.field_path}",
            )
        except Exception as e:
            return DataHealingResult(
                action=DataHealingAction.FRESHNESS_REFRESH,
                success=False,
                message=f"新鲜度检查异常: {e}",
            )

    # ── 辅助 ──

    @staticmethod
    def _is_session_expired(error_msg: str) -> bool:
        session_keywords = [
            "session", "expired", "cookie", "登录态", "登录过期",
            "token", "unauthorized", "401",
        ]
        err_lower = error_msg.lower()
        return any(kw.lower() in err_lower for kw in session_keywords)

    def get_stats(self) -> dict:
        return dict(self._stats)
