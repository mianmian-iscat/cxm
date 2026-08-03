"""test_tool_registry.py — 工具注册表单元测试"""

import os
import sys
import json
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.tool_registry import ToolRegistry, ToolInfo, ToolSchema


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(ToolInfo(
            name="op_exec_assistant",
            schema=ToolSchema(
                name="op_exec_assistant",
                version="2.0.0",
                description="执行助手",
                triggers=["执行测试用例", "回归测试"],
                parameters={
                    "type": "object",
                    "required": ["case_id"],
                    "properties": {
                        "case_id": {"type": "string", "pattern": "^OP-TC-\\d{4}$"},
                        "execution_mode": {"type": "string", "enum": ["FULL", "API_ONLY"], "default": "FULL"},
                        "env": {"type": "string", "enum": ["PRE", "DAILY"], "default": "PRE"},
                    },
                },
                dependencies=["dms-mcp", "browser-use"],
            ),
        ))

    def test_get_tool(self):
        tool = self.registry.get_tool("op_exec_assistant")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "op_exec_assistant")

    def test_get_nonexistent_tool(self):
        self.assertIsNone(self.registry.get_tool("nonexistent"))

    def test_list_tools(self):
        tools = self.registry.list_tools()
        self.assertEqual(len(tools), 1)

    def test_find_by_trigger(self):
        results = self.registry.find_by_trigger("回归测试")
        self.assertEqual(len(results), 1)

    def test_unregister(self):
        self.registry.unregister("op_exec_assistant")
        self.assertIsNone(self.registry.get_tool("op_exec_assistant"))


class TestParameterValidation(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(ToolInfo(
            name="test_tool",
            schema=ToolSchema(
                name="test_tool",
                parameters={
                    "type": "object",
                    "required": ["case_id"],
                    "properties": {
                        "case_id": {"type": "string", "pattern": "^OP-TC-\\d{4}$"},
                        "mode": {"type": "string", "enum": ["FULL", "FAST"], "default": "FULL"},
                    },
                },
            ),
        ))

    def test_valid_params(self):
        result = self.registry.validate_params("test_tool", {"case_id": "OP-TC-0001"})
        self.assertTrue(result.valid)
        self.assertEqual(result.normalized_params["mode"], "FULL")

    def test_missing_required(self):
        result = self.registry.validate_params("test_tool", {"mode": "FULL"})
        self.assertFalse(result.valid)
        self.assertTrue(any("缺少必填" in e for e in result.errors))

    def test_invalid_pattern(self):
        result = self.registry.validate_params("test_tool", {"case_id": "INVALID"})
        self.assertFalse(result.valid)
        self.assertTrue(any("格式错误" in e for e in result.errors))

    def test_invalid_enum(self):
        result = self.registry.validate_params("test_tool", {"case_id": "OP-TC-0001", "mode": "SLOW"})
        self.assertFalse(result.valid)
        self.assertTrue(any("值非法" in e for e in result.errors))

    def test_unknown_tool(self):
        result = self.registry.validate_params("nonexistent", {})
        self.assertFalse(result.valid)

    def test_unknown_param_warning(self):
        result = self.registry.validate_params("test_tool", {"case_id": "OP-TC-0001", "extra": "val"})
        self.assertTrue(result.valid)
        self.assertTrue(any("未知参数" in w for w in result.warnings))


class TestDependencyResolution(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(ToolInfo(
            name="tool_a",
            schema=ToolSchema(name="tool_a", dependencies=["tool_b"]),
        ))
        self.registry.register(ToolInfo(
            name="tool_b",
            schema=ToolSchema(name="tool_b", dependencies=["tool_c"]),
        ))
        self.registry.register(ToolInfo(
            name="tool_c",
            schema=ToolSchema(name="tool_c"),
        ))

    def test_resolve_dependencies(self):
        deps = self.registry.resolve_dependencies("tool_a")
        self.assertEqual(deps, ["tool_c", "tool_b"])

    def test_check_dependencies_available(self):
        result = self.registry.check_dependencies_available("tool_a")
        self.assertTrue(result["available"])

    def test_missing_dependency(self):
        self.registry.unregister("tool_c")
        result = self.registry.check_dependencies_available("tool_a")
        self.assertFalse(result["available"])
        self.assertIn("tool_c", result["missing"])


class TestFromJson(unittest.TestCase):

    def test_load_from_registry_json(self):
        registry_data = {
            "version": "1.0.0",
            "domain": "test",
            "tools": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            registry = ToolRegistry.from_json(f.name)
            self.assertEqual(registry.domain, "test")
            os.unlink(f.name)

    def test_export_to_dict(self):
        registry = ToolRegistry(domain="op", version="2.0")
        registry.register(ToolInfo(
            name="t1", schema=ToolSchema(name="t1", version="1.0"),
        ))
        d = registry.to_dict()
        self.assertEqual(d["domain"], "op")
        self.assertEqual(len(d["tools"]), 1)


if __name__ == "__main__":
    unittest.main()
