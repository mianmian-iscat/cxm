"""
preflight_check.py — 执行前环境预检 (维度1)

在步骤执行之前检测环境问题，实现"预防优于治疗"：
- 网络可达性检测（DNS + HTTP 连通）
- 登录态有效性验证（提前 check_login）
- 页面加载性能基线采集
- 关键 API 预热

使用方式：
    from core.preflight_check import PreflightChecker
    checker = PreflightChecker(cdp=cdp)
    report = await checker.run(target_url="https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list")
    if not report.all_passed:
        # 处理预检失败
        for issue in report.issues:
            print(f"[preflight] {issue.check}: {issue.message}")
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PreflightIssue:
    check: str
    severity: str     # "block" | "warn" | "info"
    message: str
    auto_recovered: bool = False
    duration_ms: int = 0


@dataclass
class PreflightReport:
    checks_run: int = 0
    issues: List[PreflightIssue] = field(default_factory=list)
    total_duration_ms: int = 0
    performance_baseline: dict = field(default_factory=dict)

    @property
    def all_passed(self) -> bool:
        return not any(i.severity == "block" for i in self.issues)

    @property
    def warnings(self) -> List[PreflightIssue]:
        return [i for i in self.issues if i.severity == "warn"]

    @property
    def blockers(self) -> List[PreflightIssue]:
        return [i for i in self.issues if i.severity == "block"]

    def to_dict(self) -> dict:
        return {
            "checks_run": self.checks_run,
            "all_passed": self.all_passed,
            "blockers": [{"check": i.check, "message": i.message} for i in self.blockers],
            "warnings": [{"check": i.check, "message": i.message} for i in self.warnings],
            "total_duration_ms": self.total_duration_ms,
            "performance_baseline": self.performance_baseline,
        }


class PreflightChecker:
    """
    执行前环境预检引擎。

    在 impl.py CONNECT 阶段之后、STEPS 阶段之前调用，
    检测并尝试自动修复环境问题，避免步骤执行时才发现问题。
    """

    def __init__(self, cdp=None):
        self._cdp = cdp

    async def run(
        self,
        target_url: str = "",
        expected_login: bool = True,
        warmup_apis: List[str] = None,
    ) -> PreflightReport:
        """
        运行全部预检。

        Args:
            target_url: 目标页面 URL（用于网络检测 + 登录验证）
            expected_login: 是否需要登录态
            warmup_apis: 需要预热的 API URL pattern 列表

        Returns:
            PreflightReport
        """
        start = time.time()
        report = PreflightReport()

        # 检查 1：CDP 连接存活
        cdp_issue = await self._check_cdp_alive()
        report.checks_run += 1
        if cdp_issue:
            report.issues.append(cdp_issue)
            if cdp_issue.severity == "block":
                report.total_duration_ms = int((time.time() - start) * 1000)
                return report

        # 检查 2：登录态验证
        if expected_login and self._cdp:
            login_issue = await self._check_login_state()
            report.checks_run += 1
            if login_issue:
                report.issues.append(login_issue)

        # 检查 3：网络可达性（导航到目标页）
        if target_url and self._cdp:
            nav_issue = await self._check_network_reachability(target_url)
            report.checks_run += 1
            if nav_issue:
                report.issues.append(nav_issue)

            # 检查 4：页面加载性能基线
            perf_baseline = await self._measure_page_performance()
            report.checks_run += 1
            report.performance_baseline = perf_baseline

        # 检查 5：关键 API 预热
        if warmup_apis and self._cdp:
            api_issues = await self._warmup_apis(warmup_apis)
            report.checks_run += len(warmup_apis)
            report.issues.extend(api_issues)

        report.total_duration_ms = int((time.time() - start) * 1000)
        return report

    # ── 检查项 ──

    async def _check_cdp_alive(self) -> Optional[PreflightIssue]:
        """检测 CDP 桥接进程是否存活"""
        start = time.time()
        try:
            result = await asyncio.wait_for(
                self._cdp.evaluate("1 + 1"), timeout=5
            )
            duration = int((time.time() - start) * 1000)
            if result != 2:
                return PreflightIssue(
                    check="cdp_alive",
                    severity="warn",
                    message=f"CDP evaluate 返回异常值: {result}",
                    duration_ms=duration,
                )
            return None  # 正常
        except asyncio.TimeoutError:
            return PreflightIssue(
                check="cdp_alive",
                severity="block",
                message="CDP 响应超时（5s），桥接进程可能已死",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return PreflightIssue(
                check="cdp_alive",
                severity="block",
                message=f"CDP 连接异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _check_login_state(self) -> Optional[PreflightIssue]:
        """验证登录态是否有效"""
        start = time.time()
        try:
            login_status = await self._cdp.check_login()
            duration = int((time.time() - start) * 1000)
            if login_status.get("isLoginPage", False):
                # 在登录页 → 尝试自动恢复
                recovered = await self._try_auto_login_recover()
                if recovered:
                    return PreflightIssue(
                        check="login_state",
                        severity="warn",
                        message="登录态过期，已自动 SSO warmup 恢复",
                        auto_recovered=True,
                        duration_ms=int((time.time() - start) * 1000),
                    )
                return PreflightIssue(
                    check="login_state",
                    severity="block",
                    message=f"登录态过期且自动恢复失败，当前URL: {login_status.get('currentUrl', 'unknown')}",
                    duration_ms=int((time.time() - start) * 1000),
                )
            return None  # 登录正常
        except Exception as e:
            return PreflightIssue(
                check="login_state",
                severity="warn",
                message=f"登录态检测异常（非阻断）: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _check_network_reachability(self, target_url: str) -> Optional[PreflightIssue]:
        """检测目标 URL 是否可达"""
        start = time.time()
        try:
            # 使用 JS fetch 做轻量连通性检测
            check_js = f"""
            (async () => {{
                try {{
                    const resp = await fetch({repr(target_url)}, {{
                        method: 'HEAD',
                        redirect: 'follow',
                        credentials: 'include',
                    }});
                    return {{ ok: resp.ok, status: resp.status, redirected: resp.redirected }};
                }} catch (e) {{
                    return {{ ok: false, error: e.message }};
                }}
            }})()
            """
            result = await asyncio.wait_for(
                self._cdp.evaluate(check_js), timeout=15
            )
            duration = int((time.time() - start) * 1000)

            if not result or not result.get("ok"):
                error = result.get("error", f"status={result.get('status', '?')}") if result else "null response"
                return PreflightIssue(
                    check="network_reachability",
                    severity="block",
                    message=f"目标页面不可达: {target_url[:80]} ({error})",
                    duration_ms=duration,
                )

            if duration > 10000:
                return PreflightIssue(
                    check="network_reachability",
                    severity="warn",
                    message=f"目标页面响应慢: {duration}ms > 10s",
                    duration_ms=duration,
                )
            return None
        except asyncio.TimeoutError:
            return PreflightIssue(
                check="network_reachability",
                severity="block",
                message=f"目标页面连通性检测超时（15s）: {target_url[:60]}",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return PreflightIssue(
                check="network_reachability",
                severity="warn",
                message=f"网络检测异常（非阻断）: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _measure_page_performance(self) -> dict:
        """采集当前页面加载性能基线"""
        try:
            perf_js = """(() => {
                const perf = performance.getEntriesByType('navigation')[0];
                if (!perf) return null;
                return {
                    domContentLoaded: Math.round(perf.domContentLoadedEventEnd),
                    loadComplete: Math.round(perf.loadEventEnd),
                    ttfb: Math.round(perf.responseStart - perf.requestStart),
                    domInteractive: Math.round(perf.domInteractive),
                    resourceCount: performance.getEntriesByType('resource').length,
                    failedResources: performance.getEntriesByType('resource').filter(
                        r => r.transferSize === 0 && r.decodedBodySize === 0 && r.responseStatus !== 304
                    ).length,
                };
            })()"""
            result = await self._cdp.evaluate(perf_js)
            if result:
                return result
        except Exception:
            pass
        return {}

    async def _warmup_apis(self, api_patterns: List[str]) -> List[PreflightIssue]:
        """预热关键 API（触发请求并检查响应状态）"""
        issues = []
        for pattern in api_patterns:
            start = time.time()
            try:
                check_js = f"""
                (async () => {{
                    try {{
                        const resp = await fetch({repr(pattern)}, {{ credentials: 'include' }});
                        return {{ ok: resp.ok, status: resp.status }};
                    }} catch (e) {{
                        return {{ ok: false, error: e.message }};
                    }}
                }})()
                """
                result = await asyncio.wait_for(
                    self._cdp.evaluate(check_js), timeout=10
                )
                duration = int((time.time() - start) * 1000)
                if result and not result.get("ok"):
                    issues.append(PreflightIssue(
                        check=f"api_warmup:{pattern[:40]}",
                        severity="warn",
                        message=f"API 预热失败: {pattern[:60]} status={result.get('status', '?')}",
                        duration_ms=duration,
                    ))
            except Exception as e:
                issues.append(PreflightIssue(
                    check=f"api_warmup:{pattern[:40]}",
                    severity="warn",
                    message=f"API 预热异常: {e}",
                    duration_ms=int((time.time() - start) * 1000),
                ))
        return issues

    async def _try_auto_login_recover(self) -> bool:
        """尝试自动恢复登录态"""
        try:
            from core.browser_setup import ensure_alibaba_sso
            login_status = await self._cdp.check_login()
            target_url = login_status.get("currentUrl", "")
            await ensure_alibaba_sso(self._cdp, target_url, "")
            await asyncio.sleep(2)
            # 验证
            status2 = await self._cdp.check_login()
            return not status2.get("isLoginPage", False)
        except Exception:
            return False
