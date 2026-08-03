"""
test_step_executor.py — StepExecutor 单元测试

覆盖：
1. 参数校验失败
2. 正常步骤执行（Happy Path）
3. 自愈成功（KNOWLEDGE_FIX + 重试成功）
4. 自愈失败（知识库未命中）
5. 熔断触发
6. 失败分级（P0 block / P2 skip）
7. 预算警告
"""
import asyncio
import sys
import types
import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from core.step_executor import StepExecutor, StepExecResult
from core.self_healing import HealingAction, HealingResult
from core.failure_classifier import FailureReport


# ── Mock Helpers ──────────────────────────────────────────────────────────────


def _make_executor(**overrides) -> StepExecutor:
    """创建一个注入了全部 mock 依赖的 StepExecutor。"""
    cdp = AsyncMock()
    cdp.screenshot = AsyncMock(return_value=b"\x89PNG")
    cdp.evaluate = AsyncMock(return_value="ok")

    registry = MagicMock()
    registry.validate_params = MagicMock(return_value={"valid": True, "error": None})

    variable_store = MagicMock()
    variable_store.resolve_params = MagicMock(side_effect=lambda s: s)
    variable_store.bind_step_output = MagicMock()

    assertion = MagicMock()
    assertion.run_realtime_asserts = MagicMock()

    evidence = MagicMock()
    evidence.record_step = MagicMock()
    evidence.get_latest_entry = MagicMock(return_value=None)

    self_healing = MagicMock()
    # 默认：不触发自愈
    self_healing.heal = MagicMock(return_value=HealingResult(
        action=HealingAction.NONE, attempted=False, message="无解法",
    ))

    failure_classifier = MagicMock()
    failure_classifier.classify = MagicMock(return_value=FailureReport(
        step_id="step0",
        step_type="click",
        category="unknown",
        severity="P2",
        action="continue",
        suggestion="",
    ))

    circuit_breaker = MagicMock()
    circuit_breaker.record_result = MagicMock()
    circuit_breaker.should_break = MagicMock(return_value=False)

    budget_guard = MagicMock()
    budget_guard.record_usage = MagicMock()
    budget_guard.check_budget = MagicMock(return_value=MagicMock(degraded=False, suggestion=""))

    hook_registry = MagicMock()
    hook_registry.fire = MagicMock()

    metrics_logger = MagicMock()
    metrics_logger.log_step = MagicMock()

    artifacts = MagicMock()
    artifacts.save_screenshot = MagicMock(return_value="/tmp/shot.png")

    capture_manager = None

    executor = StepExecutor(
        cdp=cdp,
        registry=registry,
        variable_store=variable_store,
        assertion=assertion,
        evidence=evidence,
        self_healing=self_healing,
        failure_classifier=failure_classifier,
        circuit_breaker=circuit_breaker,
        budget_guard=budget_guard,
        hook_registry=hook_registry,
        metrics_logger=metrics_logger,
        artifacts=artifacts,
        screenshot_cfg={"onError": False},
        screenshot_external=False,
        capture_manager=capture_manager,
        checkpoint_manager=None,
    )
    # 允许测试覆盖任意属性
    for k, v in overrides.items():
        setattr(executor, k, v)
    return executor


def _make_output():
    return {"status": "running", "steps": [], "screenshots": []}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestStepExecutorParamValidation(unittest.TestCase):
    """参数校验失败场景"""

    def test_invalid_params_returns_error_without_break(self):
        executor = _make_executor()
        executor._registry.validate_params = MagicMock(
            return_value={"valid": False, "error": ["missing required field: selector"]}
        )
        step = {"type": "click", "description": "点击按钮"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "error")
        self.assertIn("selector", result.step_result["error"])
        self.assertEqual(output["status"], "error")


class TestStepExecutorHappyPath(unittest.TestCase):
    """正常步骤执行"""

    def test_click_step_pass(self):
        executor = _make_executor()
        # _dispatch 返回空 dict（无额外字段）
        executor._dispatch = AsyncMock(return_value={})

        step = {"type": "click", "selector": ".btn", "description": "点击"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "pass")
        self.assertEqual(len(output["steps"]), 1)

    def test_wait_step_pass(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})

        step = {"type": "wait", "ms": 100, "description": "等待"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))
        self.assertEqual(result.step_result["status"], "pass")

    def test_screenshot_step_pass(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})

        step = {"type": "screenshot", "name": "after-load", "description": "截图"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))
        self.assertEqual(result.step_result["status"], "pass")


class TestStepExecutorSelfHealing(unittest.TestCase):
    """自愈场景"""

    def test_heal_knowledge_fix_success(self):
        """知识库命中 → 执行 fix_code → 重试成功"""
        executor = _make_executor()

        # 让 _dispatch 抛异常（模拟元素未找到）
        executor._dispatch = AsyncMock(side_effect=RuntimeError("element not found"))

        # 让 heal 返回 KNOWLEDGE_FIX
        fix_code = "await page.waitForSelector('.btn', {visible:true});"
        heal_result = HealingResult(
            action=HealingAction.KNOWLEDGE_FIX,
            attempted=True,
            success=True,
            message="知识库命中: waitForSelector",
            fix_code=fix_code,
            knowledge_source="references/boundary_cases.md",
        )
        executor._healing.heal = MagicMock(return_value=heal_result)

        # 让 _retry_healed_step 成功（不抛异常）
        executor._retry_healed_step = AsyncMock()

        step = {"type": "click", "selector": ".btn", "description": "点击"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        # 自愈成功，should_break = False
        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "pass")
        self.assertTrue(result.step_result.get("healed"))
        # fix_code 被调用（_wait_for_page_ready 也会调 evaluate，所以检查包含 fix_code 的调用）
        eval_calls = [str(c) for c in executor._cdp.evaluate.call_args_list]
        self.assertTrue(any(fix_code in c for c in eval_calls),
                        f"fix_code not found in evaluate calls: {eval_calls}")
        # retry 被调用
        executor._retry_healed_step.assert_called_once()

    def test_heal_retry_success(self):
        """环境抖动 → 等待后重试成功"""
        executor = _make_executor()

        call_count = {"n": 0}

        async def flaky_dispatch(*args):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("timeout")
            return {}

        executor._dispatch = AsyncMock(side_effect=flaky_dispatch)

        heal_result = HealingResult(
            action=HealingAction.RETRY, attempted=True, success=True,
            message="环境抖动重试",
        )
        executor._healing.heal = MagicMock(return_value=heal_result)
        executor._retry_healed_step = AsyncMock()

        step = {"type": "wait", "ms": 100}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))
        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "pass")

    def test_heal_fails_no_match(self):
        """自愈失败 → should_break = True"""
        executor = _make_executor()
        executor._dispatch = AsyncMock(side_effect=RuntimeError("unknown error"))
        # heal 返回 NONE
        executor._healing.heal = MagicMock(return_value=HealingResult(
            action=HealingAction.NONE, attempted=False, message="无解法",
        ))
        # 所有策略方法也失败（包括 scroll_click、smart_retry 等）
        executor._retry_healed_step = AsyncMock(side_effect=RuntimeError("retry failed"))
        executor._wait_for_page_ready = AsyncMock()

        step = {"type": "click", "selector": ".unknown"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertTrue(result.should_break)
        self.assertEqual(result.break_reason, "step_error")
        self.assertEqual(result.step_result["status"], "error")


class TestStepExecutorCircuitBreaker(unittest.TestCase):
    """熔断场景"""

    def test_circuit_breaker_triggers(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})
        executor._circuit_breaker.should_break = MagicMock(return_value=True)

        step = {"type": "wait", "ms": 10}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertTrue(result.should_break)
        self.assertEqual(result.break_reason, "circuit_broken")
        self.assertEqual(output["status"], "circuit_broken")


class TestStepExecutorFailureGrade(unittest.TestCase):
    """失败分级"""

    def test_p0_block(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})
        executor._failure_classifier.classify = MagicMock(return_value=FailureReport(
            step_id="step0",
            step_type="assert",
            category="real_bug",
            severity="P0",
            action="block",
            suggestion="核心功能回归，P0 阻断",
        ))

        step = {"type": "assert", "target": "pageContainsText", "text": "OK"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertTrue(result.should_break)
        self.assertEqual(result.break_reason, "blocked")
        self.assertEqual(output["status"], "blocked")

    def test_p2_skip(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})
        executor._failure_classifier.classify = MagicMock(return_value=FailureReport(
            step_id="step0",
            step_type="assert",
            category="script_issue",
            severity="P2",
            action="skip",
            suggestion="非关键 UI 展示问题",
        ))

        step = {"type": "assert", "target": "pageContainsText", "text": "logo"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "skip")


class TestStepExecutorBudgetGuard(unittest.TestCase):
    """预算追踪"""

    def test_budget_warning(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(return_value={})
        executor._budget_guard.check_budget = MagicMock(
            return_value=MagicMock(degraded=True, suggestion="Token 用量接近上限，建议分批")
        )

        step = {"type": "wait", "ms": 10}
        output = _make_output()

        _run(executor.execute_step(0, step, output))

        self.assertEqual(output["budgetWarning"], "Token 用量接近上限，建议分批")


class TestStepExecutorHooks(unittest.TestCase):
    """Hook 触发"""

    def test_on_failure_hook_fired(self):
        executor = _make_executor()
        executor._dispatch = AsyncMock(side_effect=RuntimeError("element not found"))
        executor._healing.heal = MagicMock(return_value=HealingResult(
            action=HealingAction.NONE, attempted=False, message="无解法",
        ))
        # 确保所有自愈策略也失败
        executor._retry_healed_step = AsyncMock(side_effect=RuntimeError("retry failed"))
        executor._wait_for_page_ready = AsyncMock()

        step = {"type": "click", "selector": ".btn"}
        output = _make_output()

        _run(executor.execute_step(0, step, output))

        # on_failure hook 应被触发
        executor._hook_registry.fire.assert_called()
        call_args = executor._hook_registry.fire.call_args
        from core.feedback_loops import HookPhase
        self.assertEqual(call_args[0][0], HookPhase.ON_FAILURE)


class TestStepExecResult(unittest.TestCase):
    """StepExecResult 数据结构"""

    def test_default_values(self):
        r = StepExecResult(step_result={"index": 0})
        self.assertFalse(r.should_break)
        self.assertEqual(r.break_reason, "")

    def test_with_break(self):
        r = StepExecResult(step_result={}, should_break=True, break_reason="error")
        self.assertTrue(r.should_break)
        self.assertEqual(r.break_reason, "error")



class TestMultiStrategyFallback(unittest.TestCase):
    """v2 多策略降级链"""

    def test_knowledge_fix_fails_then_cdp_relocate_succeeds(self):
        """知识库修复失败 → 降级到 CDP 重定位成功"""
        executor = _make_executor()

        call_count = {"dispatch": 0, "retry": 0}

        async def flaky_dispatch(*args):
            call_count["dispatch"] += 1
            if call_count["dispatch"] == 1:
                raise RuntimeError("element not found")
            return {}

        executor._dispatch = AsyncMock(side_effect=flaky_dispatch)

        # heal 返回知识库命中，但 fix_code 执行后重试仍失败
        heal_result = HealingResult(
            action=HealingAction.KNOWLEDGE_FIX, attempted=True, success=True,
            message="命中", fix_code="void(0)",
            knowledge_source="ref.md",
        )
        executor._healing.heal = MagicMock(return_value=heal_result)
        executor._wait_for_page_ready = AsyncMock()

        # knowledge fix_code 策略：retry 第一次失败
        # cdp_relocate 策略：retry 第二次成功
        retry_count = {"n": 0}

        async def mock_retry(step, step_result):
            retry_count["n"] += 1
            if retry_count["n"] == 1:
                raise RuntimeError("still broken")
            # 第二次成功

        executor._retry_healed_step = AsyncMock(side_effect=mock_retry)

        # CDP relocate 能找到一个备选 selector
        async def mock_relocate(selector):
            return "[data-testid='btn']"

        executor._try_relocate_element = AsyncMock(side_effect=mock_relocate)

        step = {"type": "click", "selector": ".old-btn", "description": "点击"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "pass")
        self.assertTrue(result.step_result.get("healed"))
        self.assertEqual(retry_count["n"], 2)

    def test_multi_round_retry_with_backoff(self):
        """多轮重试：第 0 轮失败 → 第 1 轮成功"""
        executor = _make_executor()

        call_count = {"dispatch": 0}

        async def flaky_dispatch(*args):
            call_count["dispatch"] += 1
            if call_count["dispatch"] == 1:
                raise RuntimeError("timeout waiting for element")
            return {}

        executor._dispatch = AsyncMock(side_effect=flaky_dispatch)
        executor._wait_for_page_ready = AsyncMock()

        heal_result = HealingResult(
            action=HealingAction.RETRY, attempted=True, success=True,
            message="环境抖动",
        )
        executor._healing.heal = MagicMock(return_value=heal_result)
        executor._retry_healed_step = AsyncMock()  # 重试成功

        step = {"type": "click", "selector": ".btn", "description": "点击"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))
        self.assertFalse(result.should_break)
        self.assertEqual(result.step_result["status"], "pass")

    def test_all_strategies_exhausted_records_attempts(self):
        """所有策略耗尽 → 记录所有尝试到 healAttempts"""
        executor = _make_executor()
        executor._dispatch = AsyncMock(side_effect=RuntimeError("unknown"))
        executor._healing.heal = MagicMock(return_value=HealingResult(
            action=HealingAction.NONE, attempted=False, message="无解法",
        ))
        executor._retry_healed_step = AsyncMock(side_effect=RuntimeError("all fail"))
        executor._wait_for_page_ready = AsyncMock()

        step = {"type": "click", "selector": ".btn", "description": "点击"}
        output = _make_output()

        result = _run(executor.execute_step(0, step, output))

        self.assertTrue(result.should_break)
        # healAttempts 应被记录
        attempts = result.step_result.get("healAttempts", [])
        self.assertGreater(len(attempts), 0)
        # 每个 attempt 都应有 strategy 字段
        for a in attempts:
            self.assertIn("strategy", a)


class TestPageReadinessWait(unittest.TestCase):
    """v2 页面稳定性检测"""

    def test_wait_for_page_ready_returns_when_ready(self):
        """页面就绪时立即返回"""
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=True)

        _run(executor._wait_for_page_ready(timeout_ms=1000))
        executor._cdp.evaluate.assert_called()

    def test_wait_for_page_ready_timeout_no_exception(self):
        """超时不抛异常"""
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=False)

        # 不应抛异常
        _run(executor._wait_for_page_ready(timeout_ms=300))


class TestEnhancedRelocate(unittest.TestCase):
    """v2 增强版元素重定位"""

    def test_relocate_strip_pseudo_class(self):
        """去除 :nth-child 伪类"""
        executor = _make_executor()

        async def mock_eval(expr):
            if ":nth" not in expr:
                return True
            return False

        executor._cdp.evaluate = AsyncMock(side_effect=mock_eval)
        result = _run(executor._try_relocate_element(".list-item:nth-child(3)"))
        self.assertEqual(result, ".list-item")

    def test_relocate_data_attribute(self):
        """通过 data-* 属性重定位"""
        executor = _make_executor()

        call_count = {"n": 0}

        async def mock_eval(expr):
            call_count["n"] += 1
            # 前几个策略（简化、父级、最后 class 段）都失败
            if "data-testid" in expr:
                return True
            return False

        executor._cdp.evaluate = AsyncMock(side_effect=mock_eval)
        result = _run(executor._try_relocate_element('[data-testid="submit-btn"]'))
        self.assertEqual(result, '[data-testid="submit-btn"]')

    def test_relocate_fuzzy_class(self):
        """通过模糊 class 匹配重定位"""
        executor = _make_executor()

        async def mock_eval(expr):
            # json.dumps 会转义内部双引号，用 class*= 子串匹配
            if 'class*=' in expr and 'ant-btn' in expr and '.ant-btn-x7k2m' not in expr:
                return True
            return False

        executor._cdp.evaluate = AsyncMock(side_effect=mock_eval)
        result = _run(executor._try_relocate_element(".ant-btn-x7k2m"))
        self.assertEqual(result, '[class*="ant-btn"]')

    def test_relocate_all_fail_returns_none(self):
        """所有策略都失败返回 None"""
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=False)
        result = _run(executor._try_relocate_element(".nonexistent-xyz"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
