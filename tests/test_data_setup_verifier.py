"""
test_data_setup_verifier.py — 造数自查引擎单元测试
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.data_setup_verifier import (
    DataSetupVerifier,
    VerifyDimension,
    VerifySpec,
    VerifyReport,
    CheckItem,
    Severity,
    build_f88_audit_verify_spec,
)


class TestVerifyReport(unittest.TestCase):
    """VerifyReport 数据结构测试"""

    def test_empty_report_passes(self):
        report = VerifyReport()
        self.assertTrue(report.passed)
        self.assertFalse(report.blocked)
        self.assertEqual(report.total_checks, 0)

    def test_add_passing_item(self):
        report = VerifyReport()
        report.add_item(CheckItem(
            dimension=VerifyDimension.SAFETY,
            check_name="test",
            passed=True,
        ))
        self.assertTrue(report.passed)
        self.assertEqual(report.passed_checks, 1)

    def test_add_blocking_item(self):
        report = VerifyReport()
        report.add_item(CheckItem(
            dimension=VerifyDimension.CODE_CONTRACT,
            check_name="API 契约",
            passed=False,
            severity=Severity.BLOCK,
            message="契约失败",
        ))
        self.assertFalse(report.passed)
        self.assertTrue(report.blocked)
        self.assertEqual(report.failed_checks, 1)

    def test_warn_item_fails_but_not_blocks(self):
        report = VerifyReport()
        report.add_item(CheckItem(
            dimension=VerifyDimension.HISTORY_CONFLICT,
            check_name="唯一性",
            passed=False,
            severity=Severity.WARN,
        ))
        self.assertFalse(report.passed)
        self.assertFalse(report.blocked)

    def test_to_dict(self):
        report = VerifyReport(timestamp="2026-07-27T10:00:00")
        report.add_item(CheckItem(
            dimension=VerifyDimension.PRD_COMPLIANCE,
            check_name="字段完备",
            passed=True,
        ))
        d = report.to_dict()
        self.assertIn("items", d)
        self.assertEqual(d["items"][0]["dimension"], "prd_compliance")
        self.assertTrue(d["passed"])


class TestPRDCompliance(unittest.TestCase):
    """维度1: PRD 合规性测试"""

    def setUp(self):
        self.verifier = DataSetupVerifier()

    def test_required_fields_all_present(self):
        spec = VerifySpec(required_fields=["taskId", "ossUrl", "nodeId"])
        result = {"taskId": 123, "ossUrl": "http://x", "nodeId": 169}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertTrue(report.passed)

    def test_required_fields_missing(self):
        spec = VerifySpec(required_fields=["taskId", "ossUrl", "nodeId"])
        result = {"taskId": 123}  # 缺 ossUrl, nodeId
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertFalse(report.passed)
        self.assertTrue(report.blocked)

    def test_field_constraint_enum(self):
        spec = VerifySpec(
            field_constraints={"questionType": {"enum": [1, 2, 4]}}
        )
        result = {"questionType": 4}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertTrue(report.passed)

    def test_field_constraint_enum_violation(self):
        spec = VerifySpec(
            field_constraints={"questionType": {"enum": [1, 2, 4]}}
        )
        result = {"questionType": 99}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertFalse(report.passed)

    def test_field_constraint_min_max(self):
        spec = VerifySpec(
            field_constraints={"taskId": {"type": "int", "min": 1}}
        )
        result = {"taskId": 0}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertFalse(report.passed)

    def test_valid_combination(self):
        spec = VerifySpec(
            valid_combinations=[
                {"identity": "f88", "questionType": 4},
                {"identity": "afd", "questionType": 1},
            ]
        )
        result = {"identity": "f88", "questionType": 4}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        self.assertTrue(report.passed)

    def test_invalid_combination(self):
        spec = VerifySpec(
            valid_combinations=[
                {"identity": "f88", "questionType": 4},
            ]
        )
        result = {"identity": "f88", "questionType": 99}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.PRD_COMPLIANCE]
        ))
        # 组合检查是 WARN 级别
        self.assertFalse(report.passed)
        self.assertFalse(report.blocked)


class TestSafetyDimension(unittest.TestCase):
    """维度5: 安全性自查测试"""

    def setUp(self):
        self.verifier = DataSetupVerifier()

    def test_environment_pre_passes(self):
        spec = VerifySpec(expected_env="pre", env_check_pattern=r"pre-|预发")
        result = {"taskId": 1, "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/xxx"}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        self.assertTrue(report.passed)

    def test_environment_prod_blocks(self):
        spec = VerifySpec(expected_env="pre")
        result = {"taskId": 1, "url": "https://production.alibaba-inc.com/api"}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        self.assertTrue(report.blocked)

    def test_no_destructive_operations(self):
        spec = VerifySpec()
        result = {"taskId": 1, "taskName": "test", "ossUrl": "http://x"}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        self.assertTrue(report.passed)

    def test_destructive_detected(self):
        spec = VerifySpec()
        result = {"taskId": 1, "deleted_items": [1, 2, 3]}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        self.assertTrue(report.blocked)

    def test_traceability_complete(self):
        spec = VerifySpec(trace_fields=["taskId", "taskName", "ossUrl"])
        result = {"taskId": 1, "taskName": "test", "ossUrl": "http://x"}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        self.assertTrue(report.passed)

    def test_traceability_missing(self):
        spec = VerifySpec(trace_fields=["taskId", "taskName", "ossUrl"])
        result = {"taskId": 1}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.SAFETY]
        ))
        # 追溯是 WARN 级别
        self.assertFalse(report.passed)
        self.assertFalse(report.blocked)


class TestUsabilityDimension(unittest.TestCase):
    """维度4: 可用性验证测试"""

    def setUp(self):
        self.verifier = DataSetupVerifier()

    def test_ttl_fresh(self):
        import time
        spec = VerifySpec(ttl_seconds=3600)
        result = {"taskId": 1, "created_at": time.time()}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.USABILITY]
        ))
        self.assertTrue(report.passed)

    def test_ttl_expired(self):
        import time
        spec = VerifySpec(ttl_seconds=60)
        result = {"taskId": 1, "created_at": time.time() - 120}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.USABILITY]
        ))
        self.assertFalse(report.passed)

    def test_no_ttl_config_passes(self):
        spec = VerifySpec(ttl_seconds=0)
        result = {"taskId": 1}
        report = asyncio.run(self.verifier.verify(
            result, spec, [VerifyDimension.USABILITY]
        ))
        self.assertTrue(report.passed)


class TestF88AuditSpecFactory(unittest.TestCase):
    """F88 审核造数默认规格工厂测试"""

    def test_build_spec_has_required_fields(self):
        spec = build_f88_audit_verify_spec(task_id=12345)
        self.assertIn("taskId", spec.required_fields)
        self.assertIn("ossUrl", spec.required_fields)
        self.assertEqual(spec.expected_env, "pre")
        self.assertIn("taskId", spec.trace_fields)

    def test_build_spec_api_contract(self):
        spec = build_f88_audit_verify_spec(identity="f88")
        self.assertIn("f88", spec.api_contract["url"])
        self.assertEqual(spec.api_contract["method"], "GET")

    def test_build_spec_state_window(self):
        spec = build_f88_audit_verify_spec()
        self.assertIn(0, spec.state_window["valid_states"])
        self.assertIn(1, spec.state_window["valid_states"])


class TestVerifierStats(unittest.TestCase):
    """统计功能测试"""

    def test_stats_initial(self):
        verifier = DataSetupVerifier()
        stats = verifier.get_stats()
        self.assertEqual(stats["total_verifications"], 0)
        self.assertEqual(stats["passed"], 0)

    def test_stats_after_verify(self):
        verifier = DataSetupVerifier()
        spec = VerifySpec(required_fields=["taskId"])
        asyncio.run(verifier.verify({"taskId": 1}, spec, [VerifyDimension.PRD_COMPLIANCE]))
        stats = verifier.get_stats()
        self.assertEqual(stats["total_verifications"], 1)
        self.assertEqual(stats["passed"], 1)


if __name__ == "__main__":
    unittest.main()
