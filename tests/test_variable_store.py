"""
tests/test_variable_store.py — Variable Store 子系统单元测试
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.variable_store import VariableStore, _jsonpath_extract, _resolve_template


class TestJsonPathExtract(unittest.TestCase):

    def test_root(self):
        self.assertEqual(_jsonpath_extract({"a": 1}, "$"), {"a": 1})

    def test_simple_field(self):
        self.assertEqual(_jsonpath_extract({"a": 1, "b": 2}, "$.a"), 1)

    def test_nested_field(self):
        data = {"a": {"b": {"c": 42}}}
        self.assertEqual(_jsonpath_extract(data, "$.a.b.c"), 42)

    def test_array_index(self):
        data = {"items": [10, 20, 30]}
        self.assertEqual(_jsonpath_extract(data, "$.items[1]"), 20)

    def test_array_filter(self):
        data = {"items": [{"name": "a", "v": 1}, {"name": "b", "v": 2}]}
        result = _jsonpath_extract(data, "$.items[?(@.name=='b')]")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["v"], 2)

    def test_missing_field(self):
        self.assertIsNone(_jsonpath_extract({"a": 1}, "$.b"))

    def test_out_of_range_index(self):
        self.assertIsNone(_jsonpath_extract({"items": [1]}, "$.items[5]"))

    def test_empty_path(self):
        self.assertEqual(_jsonpath_extract({"a": 1}, ""), {"a": 1})


class TestResolveTemplate(unittest.TestCase):

    def test_no_variable(self):
        self.assertEqual(_resolve_template("hello world", {}), "hello world")

    def test_single_variable_preserves_type(self):
        result = _resolve_template("${count}", {"count": 42})
        self.assertEqual(result, 42)
        self.assertIsInstance(result, int)

    def test_single_variable_string(self):
        result = _resolve_template("${name}", {"name": "test"})
        self.assertEqual(result, "test")

    def test_embedded_variable(self):
        result = _resolve_template("hello ${name}!", {"name": "world"})
        self.assertEqual(result, "hello world!")

    def test_multiple_variables(self):
        result = _resolve_template("${a}+${b}", {"a": 1, "b": 2})
        self.assertEqual(result, "1+2")

    def test_missing_variable_keeps_placeholder(self):
        result = _resolve_template("${missing}", {})
        self.assertEqual(result, "${missing}")

    def test_dict_value_in_embedded(self):
        result = _resolve_template("data=${d}", {"d": {"k": "v"}})
        self.assertIn('"k": "v"', result)


class TestVariableStore(unittest.TestCase):

    def setUp(self):
        self.store = VariableStore()

    def test_store_and_retrieve(self):
        self.store.store("key1", "value1")
        self.assertEqual(self.store.retrieve("key1"), "value1")

    def test_retrieve_missing(self):
        self.assertIsNone(self.store.retrieve("nonexistent"))

    def test_search(self):
        self.store.store("step_query.result", [1, 2, 3])
        self.store.store("step_click.status", "pass")
        results = self.store.search("query")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["key"], "step_query.result")

    def test_search_top_k(self):
        for i in range(10):
            self.store.store(f"step_{i}.data", i)
        results = self.store.search("step", top_k=3)
        self.assertEqual(len(results), 3)

    def test_bind_step_output_auto(self):
        self.store.bind_step_output("step1", {"status": 200, "data": [1, 2]})
        self.assertEqual(self.store.retrieve("step1.status"), 200)
        self.assertEqual(self.store.retrieve("step1.data"), [1, 2])

    def test_bind_step_output_with_binding(self):
        output = {"responseBody": {"data": {"items": [1, 2, 3]}, "total": 10}}
        self.store.bind_step_output(
            "step_query", output,
            output_binding={"items": "$.responseBody.data.items", "total": "$.responseBody.total"}
        )
        self.assertEqual(self.store.retrieve("step_query.items"), [1, 2, 3])
        self.assertEqual(self.store.retrieve("step_query.total"), 10)

    def test_bind_step_output_empty_id(self):
        # 空 step_id 不应报错
        self.store.bind_step_output("", {"a": 1})
        self.assertIsNone(self.store.retrieve(".a"))

    def test_resolve_dict(self):
        self.store.store("s.name", "test")
        result = self.store.resolve({"key": "${s.name}", "plain": "hello"})
        self.assertEqual(result, {"key": "test", "plain": "hello"})

    def test_resolve_list(self):
        self.store.store("s.v", 42)
        result = self.store.resolve(["${s.v}", "static"])
        self.assertEqual(result, [42, "static"])

    def test_resolve_non_string(self):
        self.assertEqual(self.store.resolve(123), 123)
        self.assertIsNone(self.store.resolve(None))

    def test_resolve_params(self):
        self.store.store("s.url", "https://example.com")
        result = self.store.resolve_params({"url": "${s.url}", "timeout": 5000})
        self.assertEqual(result["url"], "https://example.com")
        self.assertEqual(result["timeout"], 5000)

    def test_checkpoint_and_restore(self):
        self.store.store("k1", "v1")
        self.store.bind_step_output("s1", {"data": "hello"})
        state = self.store.checkpoint()

        new_store = VariableStore()
        new_store.restore(state)
        self.assertEqual(new_store.retrieve("k1"), "v1")
        self.assertEqual(new_store.retrieve("s1.data"), "hello")

    def test_get_all_variables(self):
        self.store.store("a", 1)
        self.store.store("b", 2)
        all_vars = self.store.get_all_variables()
        self.assertEqual(all_vars, {"a": 1, "b": 2})

    def test_get_step_output(self):
        self.store.bind_step_output("s1", {"x": 10})
        self.assertEqual(self.store.get_step_output("s1"), {"x": 10})
        self.assertIsNone(self.store.get_step_output("nonexistent"))

    def test_clear(self):
        self.store.store("a", 1)
        self.store.bind_step_output("s1", {"x": 10})
        self.store.clear()
        self.assertIsNone(self.store.retrieve("a"))
        self.assertIsNone(self.store.get_step_output("s1"))


if __name__ == "__main__":
    unittest.main()
