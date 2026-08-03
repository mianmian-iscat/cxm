"""test_pipeline_dsl.py — Pipeline DSL 解析器单元测试"""

import os
import sys
import unittest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.pipeline_dsl import PipelineEngine, PipelineDefinition, PipelineStep


class TestPipelineParsing(unittest.TestCase):

    def test_from_dict(self):
        data = {
            "name": "test_pipeline",
            "version": "1.0",
            "steps": [
                {"id": "step1", "tool": "tool_a", "params": {"x": 1}},
                {"id": "step2", "tool": "tool_b", "depends_on": ["step1"]},
            ],
        }
        engine = PipelineEngine.from_dict(data)
        self.assertEqual(engine.definition.name, "test_pipeline")
        self.assertEqual(len(engine.definition.steps), 2)

    def test_topological_sort(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "c", "tool": "t", "depends_on": ["b"]},
                {"id": "a", "tool": "t"},
                {"id": "b", "tool": "t", "depends_on": ["a"]},
            ],
        })
        order = engine._topological_sort()
        self.assertEqual(order, ["a", "b", "c"])

    def test_circular_dependency_detection(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "a", "tool": "t", "depends_on": ["b"]},
                {"id": "b", "tool": "t", "depends_on": ["a"]},
            ],
        })
        with self.assertRaises(ValueError):
            engine._topological_sort()


class TestVariableBinding(unittest.TestCase):

    def setUp(self):
        self.engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [{"id": "s1", "tool": "t"}],
        })
        self.engine._variables = {
            "user": {"name": "Alice", "age": 30},
            "x": 42,
        }

    def test_simple_variable(self):
        result = self.engine._resolve_variables("${x}")
        self.assertEqual(result, 42)

    def test_nested_variable(self):
        result = self.engine._resolve_variables("${user.name}")
        self.assertEqual(result, "Alice")

    def test_string_interpolation(self):
        result = self.engine._resolve_variables("Hello ${user.name}, age ${user.age}")
        self.assertEqual(result, "Hello Alice, age 30")

    def test_dict_resolution(self):
        result = self.engine._resolve_variables({"key": "${x}", "nested": {"val": "${user.name}"}})
        self.assertEqual(result, {"key": 42, "nested": {"val": "Alice"}})

    def test_no_variable(self):
        result = self.engine._resolve_variables("plain text")
        self.assertEqual(result, "plain text")


class TestConditionEvaluation(unittest.TestCase):

    def setUp(self):
        self.engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [{"id": "s1", "tool": "t"}],
        })
        self.engine._variables = {"flag": True, "count": 5}

    def test_true_condition(self):
        self.assertTrue(self.engine._evaluate_condition("${flag}"))

    def test_false_condition(self):
        self.engine._variables["flag"] = False
        self.assertFalse(self.engine._evaluate_condition("${flag}"))

    def test_empty_condition(self):
        self.assertTrue(self.engine._evaluate_condition(""))


class TestPipelineExecution(unittest.TestCase):

    def test_successful_execution(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "s1", "tool": "tool_a", "params": {"x": 1}},
                {"id": "s2", "tool": "tool_b", "depends_on": ["s1"]},
            ],
        })
        # 注册工具
        engine.register_tool("tool_a", lambda params: {"result": "ok", "value": 42})
        engine.register_tool("tool_b", lambda params: {"result": "ok"})

        result = asyncio.run(engine.execute())
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.step_results), 2)

    def test_step_failure(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "s1", "tool": "fail_tool", "params": {}},
                {"id": "s2", "tool": "tool_b", "depends_on": ["s1"]},
            ],
        })

        def fail_handler(params):
            raise RuntimeError("intentional failure")

        engine.register_tool("fail_tool", fail_handler)
        engine.register_tool("tool_b", lambda p: {"ok": True})

        result = asyncio.run(engine.execute())
        self.assertEqual(result.status, "fail")

    def test_skip_on_dependency_failure(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "s1", "tool": "fail_tool"},
                {"id": "s2", "tool": "tool_b", "depends_on": ["s1"]},
            ],
        })

        def fail_handler(params):
            raise RuntimeError("fail")

        engine.register_tool("fail_tool", fail_handler)
        engine.register_tool("tool_b", lambda p: {"ok": True})

        result = asyncio.run(engine.execute())
        self.assertEqual(result.step_results["s2"].status, "skip")

    def test_output_binding(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {
                    "id": "s1", "tool": "tool_a",
                    "params": {},
                    "output_binding": {"app_id": "$.application_id"},
                },
            ],
        })
        engine.register_tool("tool_a", lambda p: {"application_id": "APP_001"})

        result = asyncio.run(engine.execute())
        self.assertEqual(result.variables.get("app_id"), "APP_001")

    def test_condition_skip(self):
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [
                {"id": "s1", "tool": "tool_a"},
                {"id": "s2", "tool": "tool_b", "condition": "${run_optional}"},
            ],
        })
        engine.register_tool("tool_a", lambda p: {})
        engine.register_tool("tool_b", lambda p: {})

        result = asyncio.run(engine.execute({"run_optional": False}))
        self.assertEqual(result.step_results["s2"].status, "skip")


if __name__ == "__main__":
    unittest.main()
