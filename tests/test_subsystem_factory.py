"""test_subsystem_factory.py — 子系统统一工厂单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.subsystem_factory import Subsystems, create_subsystems
from core.tool_registry import ToolRegistry
from core.variable_store import VariableStore
from core.metrics_logger import MetricsLogger


class TestCreateSubsystems(unittest.TestCase):

    def setUp(self):
        self.input_data = {
            "id": "TC-001",
            "name": "smoke",
            "steps": [{"type": "click", "target": "#a"}],
        }
        self.subs = create_subsystems(self.input_data, "run-abc", "op")

    def test_returns_subsystems_instance(self):
        self.assertIsInstance(self.subs, Subsystems)

    def test_all_core_fields_populated(self):
        # 所有核心子系统都应被实例化，不能为 None
        for field_name in (
            "registry", "variable_store", "assertion", "evidence",
            "complexity_router", "budget_guard", "kbase",
            "badcase_collector", "failure_classifier", "circuit_breaker",
            "desensitize_filter", "quality_scorer", "orchestrator",
            "self_healing", "hook_registry", "eval_engine",
            "privacy_guard", "metrics_logger",
        ):
            self.assertIsNotNone(
                getattr(self.subs, field_name), f"{field_name} 未被初始化"
            )

    def test_field_types(self):
        self.assertIsInstance(self.subs.registry, ToolRegistry)
        self.assertIsInstance(self.subs.variable_store, VariableStore)
        self.assertIsInstance(self.subs.metrics_logger, MetricsLogger)

    def test_complexity_result_computed(self):
        # route() 返回值应存在且含 level 字段
        self.assertIsNotNone(self.subs.complexity_result)
        self.assertIn("level", self.subs.complexity_result)

    def test_run_id_propagated_to_evidence(self):
        self.assertEqual(self.subs.evidence.trace_id, "run-abc")

    def test_business_type_propagated(self):
        # metrics_logger 应携带 business_type
        self.assertEqual(self.subs.metrics_logger.business_type, "op")

    def test_empty_input_still_builds(self):
        # 最小输入（无 steps）也应成功构建
        subs = create_subsystems({"id": "x", "name": "y"}, "run-empty", "f88")
        self.assertIsInstance(subs, Subsystems)
        self.assertIsNotNone(subs.complexity_result)


if __name__ == "__main__":
    unittest.main()
