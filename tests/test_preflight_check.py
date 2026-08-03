"""test_preflight_check.py — 执行前环境预检单元测试"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.preflight_check import PreflightChecker, PreflightReport, PreflightIssue


class _FakeCDP:
    """按 JS 内容路由返回值的 CDP 桩"""

    def __init__(self, alive=2, login=None, fetch_result=None, perf=None):
        self.alive = alive
        self.login = login if login is not None else {"isLoginPage": False}
        self.fetch_result = fetch_result if fetch_result is not None else {"ok": True, "status": 200}
        self.perf = perf

    async def evaluate(self, js):
        if "1 + 1" in js:
            return self.alive
        if "getEntriesByType('navigation')" in js:
            return self.perf
        if "fetch(" in js:
            return self.fetch_result
        return None

    async def check_login(self):
        return self.login


def _run(coro):
    # 独立事件循环 + 结束后恢复全新循环，避免污染其他测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestPreflightReport(unittest.TestCase):

    def test_all_passed_when_no_blockers(self):
        report = PreflightReport(issues=[PreflightIssue("x", "warn", "m")])
        self.assertTrue(report.all_passed)

    def test_not_passed_with_blocker(self):
        report = PreflightReport(issues=[PreflightIssue("x", "block", "m")])
        self.assertFalse(report.all_passed)

    def test_warnings_and_blockers_filtered(self):
        report = PreflightReport(issues=[
            PreflightIssue("a", "warn", "w"),
            PreflightIssue("b", "block", "b"),
            PreflightIssue("c", "info", "i"),
        ])
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(len(report.blockers), 1)

    def test_to_dict_keys(self):
        d = PreflightReport().to_dict()
        for key in ("checks_run", "all_passed", "blockers", "warnings", "performance_baseline"):
            self.assertIn(key, d)


class TestRun(unittest.TestCase):

    def test_cdp_none_returns_blocker(self):
        checker = PreflightChecker(cdp=None)
        report = _run(checker.run())
        self.assertFalse(report.all_passed)
        self.assertEqual(report.checks_run, 1)
        self.assertTrue(any(i.check == "cdp_alive" for i in report.blockers))

    def test_healthy_minimal_passes(self):
        checker = PreflightChecker(cdp=_FakeCDP())
        report = _run(checker.run(expected_login=False))
        self.assertTrue(report.all_passed)
        self.assertEqual(report.checks_run, 1)

    def test_cdp_wrong_value_is_warn_not_block(self):
        checker = PreflightChecker(cdp=_FakeCDP(alive=3))
        report = _run(checker.run(expected_login=False))
        self.assertTrue(report.all_passed)  # warn 不阻断
        self.assertTrue(any(i.check == "cdp_alive" and i.severity == "warn"
                            for i in report.issues))

    def test_login_ok_no_issue(self):
        checker = PreflightChecker(cdp=_FakeCDP(login={"isLoginPage": False}))
        report = _run(checker.run(expected_login=True))
        self.assertFalse(any(i.check == "login_state" for i in report.issues))

    def test_network_reachable_passes(self):
        checker = PreflightChecker(cdp=_FakeCDP(perf={"loadComplete": 1200}))
        report = _run(checker.run(target_url="https://x.com/list", expected_login=False))
        self.assertTrue(report.all_passed)
        self.assertEqual(report.performance_baseline, {"loadComplete": 1200})

    def test_network_unreachable_blocks(self):
        checker = PreflightChecker(cdp=_FakeCDP(fetch_result={"ok": False, "status": 502}))
        report = _run(checker.run(target_url="https://x.com/list", expected_login=False))
        self.assertFalse(report.all_passed)
        self.assertTrue(any(i.check == "network_reachability" for i in report.blockers))

    def test_warmup_api_failure_is_warn(self):
        checker = PreflightChecker(cdp=_FakeCDP(fetch_result={"ok": False, "status": 500}))
        report = _run(checker.run(expected_login=False, warmup_apis=["/api/list"]))
        self.assertTrue(report.all_passed)  # warmup 失败仅告警
        self.assertTrue(any(i.check.startswith("api_warmup") for i in report.warnings))

    def test_total_duration_populated(self):
        checker = PreflightChecker(cdp=_FakeCDP())
        report = _run(checker.run(expected_login=False))
        self.assertGreaterEqual(report.total_duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
