"""test_privacy_guard.py — 安全红线与隐私隔离单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.privacy_guard import (
    PrivacyGuard, PrivacyFilter, RedlineChecker,
    RedlineViolation, MaskRule,
)


class TestMaskRule(unittest.TestCase):

    def test_phone_mask(self):
        rule = MaskRule.phone()
        masked = rule.apply("手机号13812345678请联系")
        self.assertNotIn("13812345678", masked)
        self.assertIn("138****5678", masked)

    def test_id_card_mask(self):
        rule = MaskRule.id_card()
        masked = rule.apply("身份证330102199001011234已验证")
        self.assertNotIn("330102199001011234", masked)

    def test_email_mask(self):
        rule = MaskRule.email()
        masked = rule.apply("邮箱test@example.com发送")
        self.assertNotIn("test@example.com", masked)
        self.assertIn("***@example.com", masked)

    def test_token_mask(self):
        rule = MaskRule.token()
        masked = rule.apply("Bearer eyJhbGciOiJIUzI1NiJ9.xxxx")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", masked)

    def test_no_match_unchanged(self):
        rule = MaskRule.phone()
        self.assertEqual(rule.apply("没有手机号"), "没有手机号")


class TestPrivacyFilter(unittest.TestCase):

    def test_chain_filters(self):
        pf = PrivacyFilter()
        pf.add_rule(MaskRule.phone())
        pf.add_rule(MaskRule.id_card())
        text = "手机13812345678身份证330102199001011234"
        masked = pf.apply(text)
        self.assertNotIn("13812345678", masked)
        self.assertNotIn("330102199001011234", masked)

    def test_filter_dict(self):
        pf = PrivacyFilter()
        pf.add_rule(MaskRule.phone())
        data = {"name": "张三", "phone": "13812345678", "note": "手机13812345678"}
        filtered = pf.apply_dict(data)
        self.assertNotIn("13812345678", str(filtered))

    def test_empty_text(self):
        pf = PrivacyFilter()
        pf.add_rule(MaskRule.phone())
        self.assertEqual(pf.apply(""), "")


class TestRedlineChecker(unittest.TestCase):

    def setUp(self):
        self.checker = RedlineChecker()
        # Add default redlines
        self.checker.add_redline("no_personal_data_in_group", "群聊禁止读取个人敏感字段")
        self.checker.add_redline("public_only_memory", "MEMORY.md仅可读取[PUBLIC]标签")
        self.checker.add_redline("sanitize_before_upload", "BadCase上传前必须脱敏")

    def test_check_passes(self):
        result = self.checker.check("no_personal_data_in_group", {"context": "private"})
        self.assertTrue(result.passed)

    def test_check_violation(self):
        result = self.checker.check("no_personal_data_in_group", {"context": "group", "has_personal": True})
        self.assertFalse(result.passed)
        self.assertEqual(result.violation_count, 1)

    def test_multiple_redlines(self):
        self.checker.add_redline("cross_workspace_confirm", "跨workspace需二次确认")
        self.assertEqual(len(self.checker.list_redlines()), 4)

    def test_list_redlines(self):
        redlines = self.checker.list_redlines()
        self.assertEqual(len(redlines), 3)


class TestPrivacyGuard(unittest.TestCase):

    def setUp(self):
        self.guard = PrivacyGuard()

    def test_full_pipeline(self):
        text = "用户手机13812345678，邮箱test@example.com"
        result = self.guard.sanitize(text)
        self.assertNotIn("13812345678", result)
        self.assertNotIn("test@example.com", result)

    def test_check_redlines(self):
        self.guard.add_redline("test_rule", "测试规则")
        violations = self.guard.check_all({"context": "private"})
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()
