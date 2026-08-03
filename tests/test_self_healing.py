"""test_self_healing.py — 智能自愈与分级放行单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.self_healing import (
    SelfHealingEngine, FailureClassifier, FailureCategory,
    SeverityLevel, HealingAction, HealingResult,
)


class TestFailureClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = FailureClassifier()

    def test_classify_true_bug(self):
        cat = self.classifier.classify({
            "error_type": "assertion_failed",
            "message": "expected 200 got 500",
        })
        self.assertEqual(cat, FailureCategory.TRUE_BUG)

    def test_classify_script_issue(self):
        cat = self.classifier.classify({
            "error_type": "selector_not_found",
            "message": "element .btn-timeout not found",
        })
        self.assertEqual(cat, FailureCategory.SCRIPT_ISSUE)

    def test_classify_data_invalid(self):
        cat = self.classifier.classify({
            "error_type": "data_error",
            "message": "test data expired",
        })
        self.assertEqual(cat, FailureCategory.DATA_INVALID)

    def test_classify_env_issue(self):
        cat = self.classifier.classify({
            "error_type": "network_error",
            "message": "connection refused",
        })
        self.assertEqual(cat, FailureCategory.ENV_ISSUE)

    def test_classify_unknown(self):
        cat = self.classifier.classify({"error_type": "weird", "message": "???"})
        self.assertEqual(cat, FailureCategory.UNKNOWN)


class TestSeverityLevel(unittest.TestCase):

    def test_p0_blocks(self):
        self.assertEqual(SeverityLevel.P0.action, "block")

    def test_p1_warns(self):
        self.assertEqual(SeverityLevel.P1.action, "warn")

    def test_p2_skips(self):
        self.assertEqual(SeverityLevel.P2.action, "skip")


class TestSelfHealingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = SelfHealingEngine()

    def test_heal_element_drift(self):
        result = self.engine.heal(FailureCategory.SCRIPT_ISSUE, {
            "error_type": "selector_not_found",
            "selector": ".old-class",
        })
        self.assertEqual(result.action, HealingAction.CDP_RELOCATE)
        self.assertTrue(result.attempted)

    def test_heal_data_invalid(self):
        result = self.engine.heal(FailureCategory.DATA_INVALID, {
            "error_type": "data_error",
        })
        self.assertEqual(result.action, HealingAction.SANDBOX_RESET)
        self.assertTrue(result.attempted)

    def test_heal_true_bug_no_action(self):
        result = self.engine.heal(FailureCategory.TRUE_BUG, {
            "error_type": "assertion_failed",
        })
        self.assertEqual(result.action, HealingAction.NONE)
        self.assertFalse(result.attempted)

    def test_heal_unknown_no_action(self):
        result = self.engine.heal(FailureCategory.UNKNOWN, {})
        self.assertEqual(result.action, HealingAction.NONE)

    # ── 字符串兼容测试（修复 failure_classifier.py 字符串 → 枚举类型断裂）──

    def test_heal_string_real_bug_maps_to_true_bug(self):
        """failure_classifier 返回 'real_bug'，应等效于 FailureCategory.TRUE_BUG"""
        result = self.engine.heal("real_bug", {"error_type": "assertion_failed"})
        self.assertEqual(result.action, HealingAction.NONE)
        self.assertFalse(result.attempted)

    def test_heal_string_script_issue_maps_to_script_issue(self):
        """failure_classifier 返回 'script_issue'，应触发 CDP 重定位"""
        result = self.engine.heal("script_issue", {
            "error_type": "selector_not_found", "selector": ".btn"
        })
        self.assertEqual(result.action, HealingAction.CDP_RELOCATE)
        self.assertTrue(result.attempted)

    def test_heal_string_env_failure_maps_to_env_issue(self):
        """failure_classifier 返回 'env_failure'，应触发重试建议"""
        result = self.engine.heal("env_failure", {"error": "connection refused"})
        self.assertEqual(result.action, HealingAction.RETRY)

    def test_heal_string_data_invalid_maps_to_data_invalid(self):
        """failure_classifier 返回 'data_invalid'，应触发沙箱重置"""
        result = self.engine.heal("data_invalid", {"error": "expired"})
        self.assertEqual(result.action, HealingAction.SANDBOX_RESET)

    def test_normalize_category_enum_passthrough(self):
        """FailureCategory 枚举应直接通过"""
        self.assertEqual(
            SelfHealingEngine._normalize_category(FailureCategory.SCRIPT_ISSUE),
            FailureCategory.SCRIPT_ISSUE,
        )

    def test_normalize_category_unknown_string(self):
        """未知字符串应回退到 UNKNOWN"""
        self.assertEqual(
            SelfHealingEngine._normalize_category("some_random_string"),
            FailureCategory.UNKNOWN,
        )

    def test_yaml_keywords_loaded(self):
        """传入 base_dir 时应加载 harness/self_healing_rules.yaml 的关键词"""
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        engine = SelfHealingEngine(base_dir=base)
        # YAML 中 env_issue.keywords 含 "502"，应匹配到 ENV_ISSUE
        result = engine.classifier.classify({"error_type": "unknown", "message": "HTTP 502 Bad Gateway"})
        self.assertEqual(result, FailureCategory.ENV_ISSUE)
        # YAML 中 true_bug.keywords 含 "数据不一致"
        result = engine.classifier.classify({"error_type": "unknown", "message": "数据不一致"})
        self.assertEqual(result, FailureCategory.TRUE_BUG)


class TestGradedRelease(unittest.TestCase):

    def setUp(self):
        self.engine = SelfHealingEngine()

    def test_p0_blocks_and_notifies(self):
        decision = self.engine.grade_release(FailureCategory.TRUE_BUG, severity="P0")
        self.assertEqual(decision["level"], "P0")
        self.assertEqual(decision["action"], "block")
        self.assertTrue(decision["notify"])

    def test_p1_warns(self):
        decision = self.engine.grade_release(FailureCategory.SCRIPT_ISSUE, severity="P1")
        self.assertEqual(decision["level"], "P1")
        self.assertEqual(decision["action"], "warn")

    def test_p2_skips(self):
        decision = self.engine.grade_release(FailureCategory.ENV_ISSUE, severity="P2")
        self.assertEqual(decision["level"], "P2")
        self.assertEqual(decision["action"], "skip")



if __name__ == "__main__":
    unittest.main()
