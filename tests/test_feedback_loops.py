"""test_feedback_loops.py — 四大互喂闭环单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.feedback_loops import (
    FeedbackHookRegistry, HookEvent, HookPhase,
    KnowledgeSinkHook, ScenarioGeneratorHook, BadCaseCollectorHook,
)


class TestHookRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = FeedbackHookRegistry()

    def test_register_hook(self):
        def my_hook(ctx):
            pass
        self.registry.register(HookPhase.AFTER_STEP, "test_hook", my_hook)
        hooks = self.registry.get_hooks(HookPhase.AFTER_STEP)
        self.assertEqual(len(hooks), 1)

    def test_unregister_hook(self):
        def my_hook(ctx):
            pass
        self.registry.register(HookPhase.AFTER_STEP, "test_hook", my_hook)
        self.registry.unregister(HookPhase.AFTER_STEP, "test_hook")
        hooks = self.registry.get_hooks(HookPhase.AFTER_STEP)
        self.assertEqual(len(hooks), 0)

    def test_fire_hooks(self):
        results = []
        def hook_a(ctx):
            results.append("a")
        def hook_b(ctx):
            results.append("b")
        self.registry.register(HookPhase.ON_SUCCESS, "a", hook_a)
        self.registry.register(HookPhase.ON_SUCCESS, "b", hook_b)
        self.registry.fire(HookPhase.ON_SUCCESS, {"step": "s1"})
        self.assertEqual(sorted(results), ["a", "b"])

    def test_fire_empty(self):
        # Should not raise
        self.registry.fire(HookPhase.BEFORE_STEP, {})

    def test_hook_error_isolation(self):
        def bad_hook(ctx):
            raise RuntimeError("boom")
        def good_hook(ctx):
            ctx["touched"] = True
        self.registry.register(HookPhase.AFTER_STEP, "bad", bad_hook)
        self.registry.register(HookPhase.AFTER_STEP, "good", good_hook)
        ctx = {}
        errors = self.registry.fire(HookPhase.AFTER_STEP, ctx)
        self.assertEqual(len(errors), 1)
        self.assertTrue(ctx.get("touched"))


class TestHookEvent(unittest.TestCase):

    def test_create_event(self):
        event = HookEvent(phase=HookPhase.ON_FAILURE, step_id="s1", data={"error": "x"})
        self.assertEqual(event.phase, HookPhase.ON_FAILURE)
        self.assertEqual(event.step_id, "s1")


class TestKnowledgeSinkHook(unittest.TestCase):

    def test_writes_pattern(self):
        sink = KnowledgeSinkHook(output_dir="/tmp/_test_feedback_kb")
        ctx = {
            "step_id": "s1",
            "status": "fail",
            "error": "selector timeout",
            "category": "patterns",
            "title": "页面加载超时",
        }
        result = sink(ctx)
        self.assertTrue(result["written"])
        # Cleanup
        import shutil
        shutil.rmtree("/tmp/_test_feedback_kb", ignore_errors=True)


class TestScenarioGeneratorHook(unittest.TestCase):

    def test_generates_skeleton(self):
        gen = ScenarioGeneratorHook()
        ctx = {"patterns": [{"title": "登录失败", "tags": ["auth"]}]}
        result = gen(ctx)
        self.assertIn("scenarios", result)
        self.assertGreater(len(result["scenarios"]), 0)


class TestBadCaseCollectorHook(unittest.TestCase):

    def test_collects_on_failure(self):
        collector = BadCaseCollectorHook()
        ctx = {
            "step_id": "s1",
            "status": "fail",
            "error": "assertion failed: expected 200 got 500",
            "case_id": "OP-TC-0001",
        }
        result = collector(ctx)
        self.assertTrue(result["collected"])
        self.assertEqual(result["bad_case"]["case_id"], "OP-TC-0001")

    def test_skips_on_success(self):
        collector = BadCaseCollectorHook()
        ctx = {"step_id": "s1", "status": "pass"}
        result = collector(ctx)
        self.assertFalse(result["collected"])


if __name__ == "__main__":
    unittest.main()
