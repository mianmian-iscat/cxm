"""tests/test_assertion_framework.py — Harness 三层断言子系统单元测试"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.assertion_framework import (
    AssertionFrameworkHarness as AF, AssertionResult,
    _safe_eval, _validate_expression, _preprocess_expression, _contains,
    check_sql_readonly, resolve_json_path, assert_value, _JSON_PATH_MISSING,
)


class TestSafeEval(unittest.TestCase):

    def test_simple_comparison(self):
        self.assertTrue(_safe_eval("x > 10", {"x": 20}))
        self.assertFalse(_safe_eval("x > 10", {"x": 5}))

    def test_arithmetic(self):
        self.assertEqual(_safe_eval("a + b", {"a": 3, "b": 4}), 7)

    def test_len_function(self):
        self.assertEqual(_safe_eval("len(items)", {"items": [1, 2, 3]}), 3)

    def test_boolean_logic(self):
        self.assertTrue(_safe_eval("a > 0 and b > 0", {"a": 1, "b": 2}))
        self.assertFalse(_safe_eval("a > 0 and b > 0", {"a": 1, "b": -1}))

    def test_string_operations(self):
        self.assertTrue(_safe_eval("status == 'pass'", {"status": "pass"}))

    def test_percentage_expression(self):
        self.assertEqual(_safe_eval("30% of total", {"total": 100}), 30.0)

    def test_dangerous_import_blocked(self):
        with self.assertRaises(ValueError):
            _safe_eval("import os", {})

    def test_dangerous_exec_blocked(self):
        with self.assertRaises(ValueError):
            _safe_eval("exec('print(1)')", {})

    def test_dangerous_os_blocked(self):
        with self.assertRaises(ValueError):
            _safe_eval("os.system('ls')", {})


class TestPreprocessExpression(unittest.TestCase):

    def test_contains_replacement(self):
        self.assertIn("_contains", _preprocess_expression("title contains 'hello'"))

    def test_percentage_of(self):
        self.assertIn("50 / 100.0", _preprocess_expression("50% of total"))

    def test_no_preprocessing_needed(self):
        self.assertEqual(_preprocess_expression("x > 10"), "x > 10")


class TestContains(unittest.TestCase):

    def test_string_contains(self):
        self.assertTrue(_contains("hello world", "world"))
        self.assertFalse(_contains("hello", "xyz"))

    def test_list_contains(self):
        self.assertTrue(_contains([1, 2, 3], "2"))


class TestPreAsserts(unittest.TestCase):

    def setUp(self):
        self.af = AF()

    def test_empty(self):
        self.assertEqual(self.af.run_pre_asserts({"url": "ok"}, []), [])

    def test_pass(self):
        results = self.af.run_pre_asserts(
            {"url": "https://example.com"},
            [{"id": "url_check", "expression": "ctx_url != ''", "severity": "CRITICAL"}]
        )
        self.assertTrue(results[0].pass_)

    def test_fail(self):
        results = self.af.run_pre_asserts(
            {"url": ""},
            [{"id": "url_check", "expression": "ctx_url != ''", "severity": "CRITICAL"}]
        )
        self.assertFalse(results[0].pass_)
        self.assertEqual(results[0].severity, "CRITICAL")

    def test_none(self):
        self.assertEqual(self.af.run_pre_asserts({}, None), [])


class TestRealtimeAsserts(unittest.TestCase):

    def setUp(self):
        self.af = AF()

    def test_pass(self):
        results = self.af.run_realtime_asserts(
            {"type": "click"}, {"status": "pass", "duration": 200},
            [{"id": "lat", "expression": "duration_ms < 5000", "severity": "WARNING"}]
        )
        self.assertTrue(results[0].pass_)

    def test_fail(self):
        results = self.af.run_realtime_asserts(
            {"type": "wait"}, {"status": "pass", "duration": 8000},
            [{"id": "lat", "expression": "duration_ms < 5000", "severity": "WARNING"}]
        )
        self.assertFalse(results[0].pass_)

    def test_empty(self):
        self.assertEqual(self.af.run_realtime_asserts({}, {}, None), [])


class TestPostAsserts(unittest.TestCase):

    def setUp(self):
        self.af = AF()

    def test_pass(self):
        output = {"status": "pass", "steps": [{"status": "pass"}] * 3 + [{"status": "fail"}]}
        results = self.af.run_post_asserts(
            output,
            [{"id": "comp", "expression": "completed_steps / total_steps >= 0.5", "severity": "CRITICAL"}]
        )
        self.assertTrue(results[0].pass_)

    def test_fail(self):
        output = {"status": "fail", "steps": [{"status": "fail"}] * 3 + [{"status": "pass"}]}
        results = self.af.run_post_asserts(
            output,
            [{"id": "comp", "expression": "completed_steps / total_steps >= 0.5", "severity": "CRITICAL"}]
        )
        self.assertFalse(results[0].pass_)

    def test_expression_error(self):
        results = self.af.run_post_asserts(
            {"steps": []},
            [{"id": "bad", "expression": "undefined_var > 0", "severity": "WARNING"}]
        )
        self.assertFalse(results[0].pass_)
        self.assertIsNotNone(results[0].error)


class TestQuery(unittest.TestCase):

    def setUp(self):
        self.af = AF()

    def test_has_critical_failures_true(self):
        self.af.run_pre_asserts({"url": ""}, [{"id": "c1", "expression": "ctx_url != ''", "severity": "CRITICAL"}])
        self.assertTrue(self.af.has_critical_failures())

    def test_has_critical_failures_false(self):
        self.af.run_pre_asserts({"url": "ok"}, [{"id": "c1", "expression": "ctx_url != ''", "severity": "WARNING"}])
        self.assertFalse(self.af.has_critical_failures())

    def test_to_summary(self):
        self.af.run_pre_asserts({"url": "ok"}, [{"id": "c1", "expression": "ctx_url != ''", "severity": "CRITICAL"}])
        s = self.af.to_summary()
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["passed"], 1)
        self.assertEqual(s["failed"], 0)

    def test_get_all_results(self):
        self.af.run_pre_asserts({}, [{"id": "a", "expression": "True", "severity": "INFO"}])
        r = self.af.get_all_results()
        self.assertIn("pre", r)
        self.assertEqual(len(r["pre"]), 1)

    def test_get_failed_results(self):
        self.af.run_pre_asserts(
            {"url": ""},
            [{"id": "f1", "expression": "ctx_url != ''", "severity": "CRITICAL"},
             {"id": "f2", "expression": "True", "severity": "WARNING"}]
        )
        self.assertEqual(len(self.af.get_failed_results()), 1)
        self.assertEqual(len(self.af.get_failed_results(severity="CRITICAL")), 1)


class TestAssertionResult(unittest.TestCase):

    def test_to_dict(self):
        r = AssertionResult(id="t1", pass_=True, severity="INFO", message="OK", expression="x>0", evaluated_value=True)
        d = r.to_dict()
        self.assertEqual(d["id"], "t1")
        self.assertTrue(d["pass"])

    def test_to_dict_with_error(self):
        r = AssertionResult(id="t2", pass_=False, severity="CRITICAL", message="fail",
                            expression="x>0", error="err", auto_action="notify")
        d = r.to_dict()
        self.assertIn("error", d)
        self.assertEqual(d["autoAction"], "notify")


class TestCheckSqlReadonly(unittest.TestCase):

    def test_select_pass(self):
        self.assertIsNone(check_sql_readonly("SELECT * FROM t"))
        self.assertIsNone(check_sql_readonly("  select id, name FROM t WHERE a = 1"))

    def test_with_pass(self):
        self.assertIsNone(check_sql_readonly("WITH cte AS (SELECT 1) SELECT * FROM cte"))

    def test_explain_pass(self):
        self.assertIsNone(check_sql_readonly("EXPLAIN SELECT 1"))

    def test_string_literal_with_forbidden_keyword(self):
        # 'delete' 在字符串字面量中，不应误判
        self.assertIsNone(check_sql_readonly("SELECT name FROM t WHERE status = 'delete'"))
        self.assertIsNone(check_sql_readonly('SELECT "insert" AS k FROM t'))

    def test_comment_with_forbidden_keyword(self):
        # -- delete 在行注释中
        self.assertIsNone(check_sql_readonly("SELECT 1 -- delete"))
        # /* delete */ 在块注释中
        self.assertIsNone(check_sql_readonly("SELECT 1 /* delete */ FROM t"))

    def test_delete_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("DELETE FROM t")

    def test_drop_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("DROP TABLE t")

    def test_update_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("UPDATE t SET a=1")

    def test_insert_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("INSERT INTO t VALUES (1)")

    def test_multi_statement_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("SELECT 1; DROP TABLE t")

    def test_into_outfile_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly('SELECT * INTO OUTFILE "/tmp/x" FROM t')

    def test_empty_sql_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("")
        with self.assertRaises(ValueError):
            check_sql_readonly("   ")

    def test_too_long_blocked(self):
        with self.assertRaises(ValueError):
            check_sql_readonly("SELECT 1" + " " * 5000)


class TestResolveJsonPath(unittest.TestCase):

    def test_nested_dict(self):
        self.assertEqual(resolve_json_path({"a": {"b": 1}}, "a.b"), 1)

    def test_list_index(self):
        self.assertEqual(resolve_json_path({"a": {"b": [10, 20, 30]}}, "a.b.1"), 20)

    def test_dollar_prefix(self):
        self.assertEqual(resolve_json_path({"a": 1}, "$.a"), 1)

    def test_missing_returns_sentinel(self):
        result = resolve_json_path({"a": 1}, "a.b")
        self.assertIs(result, _JSON_PATH_MISSING)

    def test_none_intermediate(self):
        result = resolve_json_path({"a": None}, "a.b")
        self.assertIs(result, _JSON_PATH_MISSING)

    def test_wildcard_list(self):
        self.assertEqual(resolve_json_path({"a": [1, 2, 3]}, "a.*"), [1, 2, 3])

    def test_empty_path(self):
        data = {"a": 1}
        self.assertIs(resolve_json_path(data, ""), data)

    def test_index_out_of_range(self):
        result = resolve_json_path({"a": [1]}, "a.5")
        self.assertIs(result, _JSON_PATH_MISSING)

    def test_value_is_none(self):
        # 字段存在但值为 None，应返回 None（不是 sentinel）
        result = resolve_json_path({"a": None}, "a")
        self.assertIsNone(result)
        self.assertIsNot(result, _JSON_PATH_MISSING)


class TestAssertValue(unittest.TestCase):

    def test_equals_pass(self):
        passed, failures = assert_value(1, equals=1)
        self.assertTrue(passed)
        self.assertEqual(failures, [])

    def test_equals_fail(self):
        passed, failures = assert_value(1, equals=2)
        self.assertFalse(passed)
        self.assertEqual(len(failures), 1)

    def test_contains_pass(self):
        passed, _ = assert_value("hello world", contains="world")
        self.assertTrue(passed)

    def test_contains_fail(self):
        passed, _ = assert_value("hello", contains="world")
        self.assertFalse(passed)

    def test_matches_pass(self):
        passed, _ = assert_value("hello123", matches=r"\d+")
        self.assertTrue(passed)

    def test_matches_fail(self):
        passed, _ = assert_value("hello", matches=r"^\d+$")
        self.assertFalse(passed)

    def test_matches_invalid_regex(self):
        passed, failures = assert_value("hello", matches=r"(")
        self.assertFalse(passed)
        self.assertTrue(any("正则编译失败" in f for f in failures))

    def test_value_type_pass(self):
        self.assertTrue(assert_value(1, value_type="number")[0])
        self.assertTrue(assert_value("x", value_type="string")[0])
        self.assertTrue(assert_value([1], value_type="array")[0])
        self.assertTrue(assert_value({"a": 1}, value_type="object")[0])
        self.assertTrue(assert_value(None, value_type="null")[0])

    def test_value_type_fail(self):
        passed, _ = assert_value("x", value_type="number")
        self.assertFalse(passed)

    def test_value_type_unknown(self):
        passed, failures = assert_value(1, value_type="unknown")
        self.assertFalse(passed)
        self.assertTrue(any("不支持的类型" in f for f in failures))

    def test_multi_check_accumulates_failures(self):
        passed, failures = assert_value("hello", equals="world", contains="xyz")
        self.assertFalse(passed)
        self.assertEqual(len(failures), 2)

    def test_contains_on_dict(self):
        # 非字符串会被 json.dumps
        passed, _ = assert_value({"name": "foo"}, contains="foo")
        self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
