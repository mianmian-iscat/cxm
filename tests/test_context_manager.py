"""test_context_manager.py — 上下文管理器单元测试"""

import os
import sys
import json
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.context_manager import ContextManager


class TestCaseExecutionBinding(unittest.TestCase):

    def setUp(self):
        self.ctx = ContextManager(run_id="test-run-001")

    def test_bind_case(self):
        binding = self.ctx.bind_case_execution(
            case_id="OP-TC-0001",
            execution_result={"result": "PASS", "duration_ms": 5000},
            requirement_ref="PRD-OP-§3.2",
            module="签约流程",
        )
        self.assertEqual(binding.case_id, "OP-TC-0001")
        self.assertEqual(binding.requirement_ref, "PRD-OP-§3.2")

    def test_get_binding(self):
        self.ctx.bind_case_execution("OP-TC-0001", {"result": "PASS"})
        binding = self.ctx.get_binding("OP-TC-0001")
        self.assertIsNotNone(binding)

    def test_get_nonexistent_binding(self):
        self.assertIsNone(self.ctx.get_binding("OP-TC-9999"))

    def test_get_by_module(self):
        self.ctx.bind_case_execution("OP-TC-0001", {"result": "PASS"}, module="签约")
        self.ctx.bind_case_execution("OP-TC-0002", {"result": "FAIL"}, module="签约")
        self.ctx.bind_case_execution("OP-TC-0003", {"result": "PASS"}, module="结算")

        results = self.ctx.get_bindings_by_module("签约")
        self.assertEqual(len(results), 2)

    def test_get_by_tag(self):
        self.ctx.bind_case_execution("OP-TC-0001", {"result": "PASS"}, coverage_tags=["state-machine", "settlement"])
        self.ctx.bind_case_execution("OP-TC-0002", {"result": "PASS"}, coverage_tags=["ui"])

        results = self.ctx.get_bindings_by_tag("state-machine")
        self.assertEqual(len(results), 1)

    def test_get_failed_cases(self):
        self.ctx.bind_case_execution("OP-TC-0001", {"result": "PASS"})
        self.ctx.bind_case_execution("OP-TC-0002", {"result": "FAIL"})
        self.ctx.bind_case_execution("OP-TC-0003", {"status": "fail"})

        failed = self.ctx.get_failed_cases()
        self.assertEqual(len(failed), 2)

    def test_traceability(self):
        self.ctx.bind_case_execution(
            "OP-TC-0001",
            {"result": "PASS"},
            requirement_ref="PRD-001",
        )
        self.ctx.bind_case_execution(
            "OP-TC-0002",
            {"result": "PASS"},
            requirement_ref="PRD-001",
        )

        trace = self.ctx.get_traceability("OP-TC-0001")
        self.assertEqual(trace["requirement_ref"], "PRD-001")
        self.assertIn("OP-TC-0002", trace["related_cases"])

    def test_traceability_not_found(self):
        trace = self.ctx.get_traceability("OP-TC-9999")
        self.assertIn("error", trace)


class TestSessionMemory(unittest.TestCase):

    def setUp(self):
        self.ctx = ContextManager(run_id="test-run-001")

    def test_init_session(self):
        session = self.ctx.init_session(session_id="sess-001", tags=["regression"])
        self.assertEqual(session.session_id, "sess-001")

    def test_update_and_get_session_var(self):
        self.ctx.init_session()
        self.ctx.update_session("merchant_id", "M001")
        self.assertEqual(self.ctx.get_session_var("merchant_id"), "M001")

    def test_get_default_var(self):
        self.ctx.init_session()
        self.assertEqual(self.ctx.get_session_var("nonexistent", "default"), "default")

    def test_record_event(self):
        self.ctx.init_session()
        self.ctx.record_session_event("step_executed", {"step": "s1"})
        self.assertEqual(len(self.ctx._session.history), 1)


class TestCoverageMatrix(unittest.TestCase):

    def setUp(self):
        self.ctx = ContextManager(run_id="test-run-001")

    def test_compute_coverage(self):
        # 注册模块用例
        self.ctx.register_module_cases("签约流程", ["OP-TC-0001", "OP-TC-0002"])
        self.ctx.register_module_cases("结算对赌", ["OP-TC-0003", "OP-TC-0004", "OP-TC-0005"])

        # 绑定执行结果
        self.ctx.bind_case_execution("OP-TC-0001", {"result": "PASS"}, module="签约流程")
        self.ctx.bind_case_execution("OP-TC-0002", {"result": "PASS"}, module="签约流程")
        self.ctx.bind_case_execution("OP-TC-0003", {"result": "PASS"}, module="结算对赌")
        self.ctx.bind_case_execution("OP-TC-0004", {"result": "FAIL"}, module="结算对赌")

        matrix = self.ctx.compute_coverage_matrix()
        # 应该有3行：签约流程、结算对赌、合计
        self.assertEqual(len(matrix), 3)

        # 签约流程 100% 覆盖
        sign_row = next(e for e in matrix if e.module == "签约流程")
        self.assertEqual(sign_row.total_cases, 2)
        self.assertEqual(sign_row.executed, 2)
        self.assertEqual(sign_row.passed, 2)
        self.assertAlmostEqual(sign_row.coverage_rate, 1.0)

        # 结算对赌 66.7% 覆盖
        settle_row = next(e for e in matrix if e.module == "结算对赌")
        self.assertEqual(settle_row.total_cases, 3)
        self.assertEqual(settle_row.executed, 2)

        # 合计
        total_row = next(e for e in matrix if e.module == "合计")
        self.assertEqual(total_row.total_cases, 5)

    def test_coverage_table(self):
        self.ctx.register_module_cases("测试", ["TC1"])
        self.ctx.bind_case_execution("TC1", {"result": "PASS"}, module="测试")
        table = self.ctx.coverage_to_table()
        self.assertIn("测试", table)

    def test_empty_coverage(self):
        matrix = self.ctx.compute_coverage_matrix()
        self.assertEqual(len(matrix), 0)


class TestPersistence(unittest.TestCase):

    def test_flush(self):
        ctx = ContextManager(run_id="test-run")
        ctx.init_session(tags=["test"])
        ctx.register_module_cases("模块A", ["TC1", "TC2"])
        ctx.bind_case_execution("TC1", {"result": "PASS"}, module="模块A")

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = ctx.flush(tmpdir)
            self.assertIn("bindings", paths)
            self.assertIn("coverage", paths)
            self.assertIn("session", paths)

            # 验证文件内容
            with open(paths["bindings"]) as f:
                data = json.load(f)
            self.assertEqual(data["total_bindings"], 1)

    def test_metrics_summary(self):
        ctx = ContextManager(run_id="test-run")
        ctx.register_module_cases("A", ["TC1"])
        ctx.bind_case_execution("TC1", {"result": "PASS"}, module="A")

        summary = ctx.to_metrics_summary()
        self.assertEqual(summary["total_bindings"], 1)
        self.assertEqual(summary["coverage"]["passed"], 1)


if __name__ == "__main__":
    unittest.main()
