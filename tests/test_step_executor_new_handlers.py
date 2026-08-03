"""
test_step_executor_new_handlers.py — 一期三件套 handler 单元测试

覆盖：
- _handle_db_assert: SQL 只读预检、bridge 调用（mock subprocess）、expect/rowCount/jsonPath 断言
- _handle_assert_api: status/jsonPath/contains/matches/maxDurationMs/captureAll 断言
- _handle_assert_ui: visible/disabled/text/count/attribute/cssProperty 断言
"""
import asyncio
import json
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.step_executor import StepExecutor
from core.assertion_framework import _JSON_PATH_MISSING


# ── Mock Helpers ──────────────────────────────────────────────────────────────


def _make_executor(capture=None) -> StepExecutor:
    cdp = AsyncMock()
    cdp.evaluate = AsyncMock(return_value={"type": "object", "value": {"count": 0, "failures": []}})

    registry = MagicMock()
    registry.validate_params = MagicMock(return_value={"valid": True, "error": None})

    variable_store = MagicMock()
    variable_store.resolve_params = MagicMock(side_effect=lambda s: s)
    variable_store.bind_step_output = MagicMock()
    variable_store.get_all_variables = MagicMock(return_value={})

    assertion = MagicMock()
    evidence = MagicMock()
    evidence.record_step = MagicMock()
    evidence.get_latest_entry = MagicMock(return_value=None)

    self_healing = MagicMock()
    from core.self_healing import HealingAction, HealingResult
    self_healing.heal = MagicMock(return_value=HealingResult(
        action=HealingAction.NONE, attempted=False, message="无解法",
    ))

    from core.failure_classifier import FailureReport
    failure_classifier = MagicMock()
    failure_classifier.classify = MagicMock(return_value=FailureReport(
        step_id="s", step_type="x", category="unknown",
        severity="P2", action="continue", suggestion="",
    ))

    circuit_breaker = MagicMock()
    circuit_breaker.record_result = MagicMock()
    circuit_breaker.should_break = MagicMock(return_value=False)

    budget_guard = MagicMock()
    budget_guard.record_usage = MagicMock()
    budget_guard.check_budget = MagicMock(return_value=MagicMock(degraded=False))

    hook_registry = MagicMock()
    metrics_logger = MagicMock()
    artifacts = MagicMock()

    return StepExecutor(
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
        capture_manager=capture,
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── _handle_db_assert ──────────────────────────────────────────────────────


class TestDbAssertSQLReadonly(unittest.TestCase):
    """SQL 只读预检：在调用 CLI 之前直接返回 fail。"""

    def setUp(self):
        self.executor = _make_executor()
        self.output = {"screenshots": []}

    def test_delete_sql_fails_fast(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "DELETE FROM t"}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertEqual(self.output["status"], "fail")
        self.assertFalse(result["matched"])
        self.assertTrue(any("SQL 只读检查失败" in f for f in result["failures"]))

    def test_drop_sql_fails_fast(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "DROP TABLE t"}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertEqual(self.output["status"], "fail")
        self.assertTrue(any("DROP" in f for f in result["failures"]))

    def test_select_with_param_substitution(self):
        """参数替换后再做只读检查（含字符串 'delete' 不应误判）。"""
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT * FROM t WHERE status=:status",
                "params": {"status": "delete"}}
        # patch subprocess 避免真调 CLI
        fake_out = json.dumps({
            "status": "ok", "rows": [{"status": "delete"}],
            "rowCount": 1, "durationMs": 100,
        }).encode()
        fake_err = b""
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, fake_err))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        # 只读检查通过，且 SQL 已替换
        self.assertIn("'delete'", result["sql"])
        self.assertTrue(result["matched"])


class TestDbAssertBridgeCall(unittest.TestCase):
    """Bridge 调用与输出解析。"""

    def setUp(self):
        self.executor = _make_executor()
        self.output = {"screenshots": []}

    def test_bridge_returns_ok(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT id FROM t", "rowCount": 2}
        fake_out = json.dumps({
            "status": "ok", "rows": [{"id": 1}, {"id": 2}],
            "rowCount": 2, "durationMs": 50,
        }).encode()
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, b""))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertTrue(result["matched"])
        self.assertEqual(result["rowCount"], 2)
        self.assertNotIn("status", self.output)  # 没 fail 就不会设 status

    def test_bridge_returns_error(self):
        step = {"type": "dbAssert", "group": "g", "db": "d", "sql": "SELECT 1"}
        fake_out = json.dumps({
            "status": "error", "error": "auth failed",
        }).encode()
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, b""))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertEqual(self.output["status"], "fail")
        self.assertFalse(result["matched"])
        self.assertTrue(any("auth failed" in f for f in result["failures"]))

    def test_bridge_subprocess_timeout(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT 1", "timeoutMs": 100}
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        fake_proc.kill = MagicMock()
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertTrue(any("超时" in f for f in result["failures"]))

    def test_bridge_node_not_installed(self):
        step = {"type": "dbAssert", "group": "g", "db": "d", "sql": "SELECT 1"}
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(side_effect=FileNotFoundError("no node"))):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertEqual(self.output["status"], "fail")
        self.assertTrue(any("node 未安装" in f for f in result["failures"]))

    def test_expect_row_mismatch(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT id FROM t",
                "expect": [{"id": 99}]}
        fake_out = json.dumps({
            "status": "ok", "rows": [{"id": 1}],
            "rowCount": 1, "durationMs": 50,
        }).encode()
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, b""))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertTrue(any("row[0].id" in f for f in result["failures"]))

    def test_jsonpath_equals(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT name FROM t LIMIT 1",
                "jsonPath": "$.name", "equals": "foo"}
        fake_out = json.dumps({
            "status": "ok", "rows": [{"name": "foo"}],
            "rowCount": 1, "durationMs": 50,
        }).encode()
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, b""))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertTrue(result["matched"])

    def test_row_count_mismatch(self):
        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT 1", "rowCount": 5}
        fake_out = json.dumps({
            "status": "ok", "rows": [{"1": 1}],
            "rowCount": 1, "durationMs": 50,
        }).encode()
        fake_proc = MagicMock()
        fake_proc.communicate = AsyncMock(return_value=(fake_out, b""))
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=fake_proc)):
            result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertTrue(any("rowCount" in f for f in result["failures"]))


# ── _handle_assert_api ──────────────────────────────────────────────────────


def _make_capture_with_entries(entries, last_entry=None):
    capture = MagicMock()
    capture.last_api_entry = last_entry if last_entry is not None else (
        entries[-1] if entries else None)
    capture.get_api_entry = MagicMock(
        side_effect=lambda pattern: next(
            (e for e in entries if pattern in e.get("url", "")), None))
    capture.get_all_api_entries = MagicMock(
        side_effect=lambda pattern: [e for e in entries if pattern in e.get("url", "")]
        if pattern else entries)
    return capture


class TestAssertApi(unittest.TestCase):

    def test_no_capture(self):
        executor = _make_executor(capture=None)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "status": 200}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("capture_manager" in f for f in result["failures"]))

    def test_no_matching_entry(self):
        capture = _make_capture_with_entries([])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "urlPattern": "no_such", "status": 200}, 0, output))
        self.assertFalse(result["pass"])
        self.assertEqual(output["status"], "fail")

    def test_status_pass(self):
        capture = _make_capture_with_entries(
            [{"url": "https://x/api/foo", "status": 200, "duration": 100,
              "responseBody": {"ok": True}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "status": 200}, 0, output))
        self.assertTrue(result["pass"])

    def test_status_fail(self):
        capture = _make_capture_with_entries(
            [{"url": "https://x/api/foo", "status": 500, "duration": 100,
              "responseBody": {}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "status": 200}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("status" in f for f in result["failures"]))

    def test_jsonpath_equals(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 100,
              "responseBody": {"data": {"batchId": "BT_123"}}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "jsonPath": "$.data.batchId",
             "equals": "BT_123"}, 0, output))
        self.assertTrue(result["pass"])
        self.assertEqual(result["jsonPathValue"], "BT_123")

    def test_jsonpath_missing(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 100,
              "responseBody": {"data": {}}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "jsonPath": "$.data.batchId",
             "equals": "x"}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("未命中" in f for f in result["failures"]))

    def test_contains_pass(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 100,
              "responseBody": {"data": "hello world"}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "contains": "world"}, 0, output))
        self.assertTrue(result["pass"])

    def test_matches_pass(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 100,
              "responseBody": "BT_12345"}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "matches": r"BT_\d+"}, 0, output))
        self.assertTrue(result["pass"])

    def test_max_duration_fail(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 5000,
              "responseBody": {}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "maxDurationMs": 1000}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("duration" in f for f in result["failures"]))

    def test_capture_all(self):
        entries = [
            {"url": "https://x/api/list", "status": 200, "duration": 50,
             "responseBody": {"data": [1]}},
            {"url": "https://x/api/list", "status": 200, "duration": 80,
             "responseBody": {"data": [1, 2]}},
            {"url": "https://x/api/other", "status": 200, "duration": 10,
             "responseBody": {}},
        ]
        capture = _make_capture_with_entries(entries)
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "urlPattern": "api/list",
             "captureAll": True, "status": 200}, 0, output))
        self.assertTrue(result["pass"])
        self.assertEqual(result["matchedCount"], 2)

    def test_value_type_fail(self):
        capture = _make_capture_with_entries(
            [{"url": "u", "status": 200, "duration": 10,
              "responseBody": {"count": "not-a-number"}}])
        executor = _make_executor(capture=capture)
        output = {"screenshots": []}
        result = _run(executor._handle_assert_api(
            {"type": "assertAPI", "jsonPath": "$.count",
             "valueType": "number"}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("valueType" in f for f in result["failures"]))


# ── _handle_assert_ui ──────────────────────────────────────────────────────


class TestAssertUi(unittest.TestCase):

    def _make_eval_result(self, **kwargs):
        base = {
            "type": "object",
            "value": {
                "selector": kwargs.get("selector", ""),
                "count": kwargs.get("count", 0),
                "firstText": kwargs.get("firstText", ""),
                "firstVisible": kwargs.get("firstVisible", False),
                "firstDisabled": kwargs.get("firstDisabled", False),
                "domSnippet": "",
                "failures": list(kwargs.get("failures", [])),
            },
        }
        return base

    def test_no_elements_returns_fail(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(count=0))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "visible": True}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("未找到匹配元素" in f for f in result["failures"]))

    def test_visible_pass(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(
            count=1, firstVisible=True))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "visible": True}, 0, output))
        self.assertTrue(result["pass"])

    def test_text_equals_fail(self):
        executor = _make_executor()
        # JS 侧模拟断言失败
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(
            count=1, firstText="actual",
            failures=["text: 期望 \"expected\" 实际 \"actual\""]))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "text": "expected"}, 0, output))
        self.assertFalse(result["pass"])

    def test_cdp_evaluate_exception(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(side_effect=RuntimeError("CDP broke"))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "count": 0}, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("CDP evaluate" in f for f in result["failures"]))

    def test_count_zero_with_no_elements_pass(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(count=0))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "count": 0}, 0, output))
        self.assertTrue(result["pass"])

    def test_non_dict_eval_return(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value="weird string")
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "visible": True}, 0, output))
        self.assertFalse(result["pass"])


# ── 二期优化：exists / soft / rowIndex / allRows / textTrim / allMatch ────────────


class TestDbAssertEnhancements(unittest.TestCase):
    """dbAssert 优化：rowIndex / allRows / exists / soft"""

    def setUp(self):
        self.executor = _make_executor()
        self.output = {"screenshots": []}

    @patch("asyncio.create_subprocess_exec")
    def test_row_index(self, mock_exec):
        """rowIndex=1 应对第二行做 jsonPath 断言"""
        rows = [{"id": 1, "status": "a"}, {"id": 2, "status": "b"}]
        bridge_out = json.dumps({"status": "ok", "rows": rows, "rowCount": 2})
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(bridge_out.encode(), b""))
        mock_exec.return_value = proc

        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT * FROM t", "jsonPath": "$.status",
                "equals": "b", "rowIndex": 1}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertTrue(result["matched"])

    @patch("asyncio.create_subprocess_exec")
    def test_all_rows(self, mock_exec):
        """allRows=true 对所有行做 jsonPath 断言"""
        rows = [{"status": "ok"}, {"status": "ok"}, {"status": "fail"}]
        bridge_out = json.dumps({"status": "ok", "rows": rows, "rowCount": 3})
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(bridge_out.encode(), b""))
        mock_exec.return_value = proc

        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT * FROM t", "jsonPath": "$.status",
                "equals": "ok", "allRows": True}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertTrue(any("row[2]" in f for f in result["failures"]))

    @patch("asyncio.create_subprocess_exec")
    def test_exists_true(self, mock_exec):
        """exists=true 验证字段存在且非 null"""
        rows = [{"id": 1, "name": None}]
        bridge_out = json.dumps({"status": "ok", "rows": rows, "rowCount": 1})
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(bridge_out.encode(), b""))
        mock_exec.return_value = proc

        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT * FROM t", "jsonPath": "$.name",
                "exists": True}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertTrue(any("exists" in f for f in result["failures"]))

    @patch("asyncio.create_subprocess_exec")
    def test_soft_assert_no_break(self, mock_exec):
        """soft=true 时断言失败不设 output.status=fail"""
        rows = [{"id": 1}]
        bridge_out = json.dumps({"status": "ok", "rows": rows, "rowCount": 1})
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(bridge_out.encode(), b""))
        mock_exec.return_value = proc

        step = {"type": "dbAssert", "group": "g", "db": "d",
                "sql": "SELECT * FROM t", "rowCount": 99, "soft": True}
        result = _run(self.executor._handle_db_assert(step, 0, self.output))
        self.assertFalse(result["matched"])
        self.assertNotEqual(self.output.get("status"), "fail")
        self.assertTrue(result.get("soft"))
        self.assertTrue(len(self.output.get("_softFailures", [])) > 0)


class TestAssertApiEnhancements(unittest.TestCase):
    """assertAPI 优化：exists / contains+jsonPath / soft"""

    def _make_capture(self, entries):
        cap = MagicMock()
        cap.last_api_entry = entries[-1] if entries else None
        cap.get_api_entry = MagicMock(return_value=entries[0] if entries else None)
        cap.get_all_api_entries = MagicMock(return_value=entries)
        return cap

    def test_exists_true_pass(self):
        entry = {"url": "http://x/api", "status": 200, "duration": 100,
                 "responseBody": {"data": {"batchId": "BT_1"}}}
        executor = _make_executor(capture=self._make_capture([entry]))
        output = {"screenshots": []}
        step = {"type": "assertAPI", "jsonPath": "$.data.batchId", "exists": True}
        result = _run(executor._handle_assert_api(step, 0, output))
        self.assertTrue(result["pass"])

    def test_exists_true_fail_when_null(self):
        entry = {"url": "http://x/api", "status": 200, "duration": 100,
                 "responseBody": {"data": {"batchId": None}}}
        executor = _make_executor(capture=self._make_capture([entry]))
        output = {"screenshots": []}
        step = {"type": "assertAPI", "jsonPath": "$.data.batchId", "exists": True}
        result = _run(executor._handle_assert_api(step, 0, output))
        self.assertFalse(result["pass"])
        self.assertTrue(any("exists" in f for f in result["failures"]))

    def test_jsonpath_contains(self):
        """jsonPath + contains 对提取值做包含断言"""
        entry = {"url": "http://x/api", "status": 200, "duration": 100,
                 "responseBody": {"msg": "hello world"}}
        executor = _make_executor(capture=self._make_capture([entry]))
        output = {"screenshots": []}
        step = {"type": "assertAPI", "jsonPath": "$.msg", "contains": "world"}
        result = _run(executor._handle_assert_api(step, 0, output))
        self.assertTrue(result["pass"])

    def test_jsonpath_matches(self):
        """jsonPath + matches 对提取值做正则断言"""
        entry = {"url": "http://x/api", "status": 200, "duration": 100,
                 "responseBody": {"id": "BT_12345"}}
        executor = _make_executor(capture=self._make_capture([entry]))
        output = {"screenshots": []}
        step = {"type": "assertAPI", "jsonPath": "$.id", "matches": "^BT_\\d+$"}
        result = _run(executor._handle_assert_api(step, 0, output))
        self.assertTrue(result["pass"])

    def test_soft_no_break(self):
        entry = {"url": "http://x/api", "status": 500, "duration": 100,
                 "responseBody": {}}
        executor = _make_executor(capture=self._make_capture([entry]))
        output = {"screenshots": []}
        step = {"type": "assertAPI", "status": 200, "soft": True}
        result = _run(executor._handle_assert_api(step, 0, output))
        self.assertFalse(result["pass"])
        self.assertNotEqual(output.get("status"), "fail")
        self.assertTrue(result.get("soft"))


class TestAssertUiEnhancements(unittest.TestCase):
    """assertUI 优化：textTrim / allMatch / soft"""

    def _make_eval_result(self, count=1, firstText="", failures=None,
                          firstVisible=True, firstDisabled=False):
        return {"type": "object", "value": {
            "selector": ".x", "count": count,
            "firstText": firstText, "firstVisible": firstVisible,
            "firstDisabled": firstDisabled, "domSnippet": "",
            "failures": failures or [],
        }}

    def test_text_trim_default(self):
        """默认 trim：JS 侧会 trim textContent"""
        executor = _make_executor()
        # 模拟 JS 侧 trim 后匹配成功
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(
            count=1, firstText="确认"))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "text": "确认"}, 0, output))
        self.assertTrue(result["pass"])
        # 确认 checks_spec 中 textTrim=True
        self.assertTrue(result["checked"]["textTrim"])

    def test_all_match_in_checks(self):
        """allMatch 传入后会包含在 checked 中"""
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(count=3))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "count": 3,
             "allMatch": {"textContains": "ok"}}, 0, output))
        self.assertEqual(result["checked"]["allMatch"], {"textContains": "ok"})

    def test_soft_no_break(self):
        executor = _make_executor()
        executor._cdp.evaluate = AsyncMock(return_value=self._make_eval_result(
            count=1, failures=["visible: 期望可见 实际不可见"]))
        output = {"screenshots": []}
        result = _run(executor._handle_assert_ui(
            {"type": "assertUI", "selector": ".x", "visible": True, "soft": True},
            0, output))
        self.assertFalse(result["pass"])
        self.assertNotEqual(output.get("status"), "fail")
        self.assertTrue(result.get("soft"))
        self.assertTrue(len(output.get("_softFailures", [])) > 0)


class TestVariableInterpolation(unittest.TestCase):
    """变量插值：嵌套路径解析"""

    def test_deep_get_nested(self):
        from core.variable_store import _deep_get
        variables = {
            "store_picked.picked": {"firstTaskId": 123, "rowCount": 5},
        }
        self.assertEqual(_deep_get(variables, "store_picked.picked.firstTaskId"), 123)
        self.assertEqual(_deep_get(variables, "store_picked.picked.rowCount"), 5)

    def test_deep_get_direct(self):
        from core.variable_store import _deep_get
        variables = {"store_x.count": 42}
        self.assertEqual(_deep_get(variables, "store_x.count"), 42)

    def test_deep_get_list_index(self):
        from core.variable_store import _deep_get
        variables = {"store_data.items": [{"id": 1}, {"id": 2}]}
        self.assertEqual(_deep_get(variables, "store_data.items.1.id"), 2)

    def test_resolve_template_nested(self):
        from core.variable_store import _resolve_template
        variables = {"store_picked.picked": {"taskId": 999}}
        result = _resolve_template("${store_picked.picked.taskId}", variables)
        self.assertEqual(result, 999)

    def test_resolve_template_partial(self):
        from core.variable_store import _resolve_template
        variables = {"store_picked.picked": {"name": "hello"}}
        result = _resolve_template("prefix-${store_picked.picked.name}-suffix", variables)
        self.assertEqual(result, "prefix-hello-suffix")


if __name__ == "__main__":
    unittest.main()
