"""test_schema_validator.py — 轻量 JSON Schema 校验器单元测试"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.schema_validator import (
    _check_type,
    _validate_against_schema,
    validate_all,
    validate_case_json,
    validate_knowledge_json,
)


class TestCheckType(unittest.TestCase):

    def test_string(self):
        self.assertTrue(_check_type("hi", "string"))
        self.assertFalse(_check_type(1, "string"))

    def test_integer_rejects_float(self):
        self.assertTrue(_check_type(3, "integer"))
        self.assertFalse(_check_type(3.0, "integer"))

    def test_integer_rejects_bool(self):
        self.assertFalse(_check_type(True, "integer"))

    def test_number_accepts_int_and_float(self):
        self.assertTrue(_check_type(3, "number"))
        self.assertTrue(_check_type(3.5, "number"))

    def test_number_rejects_bool(self):
        self.assertFalse(_check_type(True, "number"))

    def test_boolean(self):
        self.assertTrue(_check_type(True, "boolean"))
        self.assertFalse(_check_type(1, "boolean"))

    def test_array_and_object(self):
        self.assertTrue(_check_type([], "array"))
        self.assertTrue(_check_type({}, "object"))
        self.assertFalse(_check_type({}, "array"))

    def test_unknown_type_skips_check(self):
        self.assertTrue(_check_type("anything", "null"))


class TestValidateAgainstSchema(unittest.TestCase):

    def test_passes_valid_object(self):
        schema = {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        }
        self.assertEqual(_validate_against_schema({"id": "x"}, schema), [])

    def test_non_object_top_level(self):
        schema = {"type": "object"}
        errors = _validate_against_schema(["not", "a", "dict"], schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("期望 object", errors[0])

    def test_missing_required_field(self):
        schema = {"type": "object", "required": ["name"], "properties": {}}
        errors = _validate_against_schema({}, schema)
        self.assertTrue(any("name" in e for e in errors))

    def test_wrong_property_type(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        errors = _validate_against_schema({"count": "not-int"}, schema)
        self.assertTrue(any("count" in e and "类型错误" in e for e in errors))

    def test_none_value_skips_type_check(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        self.assertEqual(_validate_against_schema({"count": None}, schema), [])

    def test_enum_violation(self):
        schema = {
            "type": "object",
            "properties": {"status": {"enum": ["pass", "fail"]}},
        }
        errors = _validate_against_schema({"status": "unknown"}, schema)
        self.assertTrue(any("枚举" in e for e in errors))

    def test_enum_pass(self):
        schema = {
            "type": "object",
            "properties": {"status": {"enum": ["pass", "fail"]}},
        }
        self.assertEqual(_validate_against_schema({"status": "pass"}, schema), [])

    def test_one_of_matches(self):
        schema = {
            "type": "object",
            "properties": {"val": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
        }
        self.assertEqual(_validate_against_schema({"val": 5}, schema), [])
        self.assertEqual(_validate_against_schema({"val": "s"}, schema), [])

    def test_one_of_no_match(self):
        schema = {
            "type": "object",
            "properties": {"val": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
        }
        errors = _validate_against_schema({"val": [1, 2]}, schema)
        self.assertTrue(any("val" in e for e in errors))

    def test_array_item_type_error(self):
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        errors = _validate_against_schema({"tags": ["ok", 123]}, schema)
        self.assertTrue(any("tags[1]" in e for e in errors))

    def test_array_item_errors_capped_at_three(self):
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        bad = {"tags": [1, 2, 3, 4, 5, 6]}
        errors = _validate_against_schema(bad, schema)
        # 最多 3 个类型错误 + 1 个"省略"提示
        omitted = [e for e in errors if "省略" in e]
        self.assertEqual(len(omitted), 1)
        self.assertIn("3", omitted[0])


class TestPublicValidators(unittest.TestCase):

    def _write(self, content):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_knowledge_json_decode_error(self):
        path = self._write("{invalid json")
        errors = validate_knowledge_json(path)
        self.assertTrue(any("JSON 解析失败" in e for e in errors))

    def test_case_json_decode_error(self):
        path = self._write("not json at all")
        errors = validate_case_json(path)
        self.assertTrue(any("JSON 解析失败" in e for e in errors))

    def test_file_not_found(self):
        errors = validate_knowledge_json("/nonexistent/path/x.json")
        self.assertTrue(any("文件不存在" in e for e in errors))

    def test_valid_json_structure_returns_list(self):
        path = self._write(json.dumps({"id": "x", "name": "y"}))
        # 结果类型必须是列表（可能有 Schema 校验错误，但不应抛异常）
        self.assertIsInstance(validate_case_json(path), list)


class TestValidateAll(unittest.TestCase):

    def test_missing_directory(self):
        result = validate_all("/no/such/dir")
        self.assertIn("/no/such/dir", result)

    def test_empty_directory_returns_empty(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(validate_all(d), {})

    def test_skips_index_json_for_knowledge(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        idx = os.path.join(d, "index.json")
        with open(idx, "w", encoding="utf-8") as f:
            f.write("{invalid")
        # index.json 被跳过，所以无错误
        self.assertEqual(validate_all(d, schema_type="knowledge"), {})

    def test_reports_bad_file(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        bad = os.path.join(d, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{invalid")
        result = validate_all(d, schema_type="case")
        self.assertIn(bad, result)


if __name__ == "__main__":
    unittest.main()
