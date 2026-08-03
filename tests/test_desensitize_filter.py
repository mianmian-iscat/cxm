"""test_desensitize_filter.py — 证据脱敏过滤器单元测试 (Gap 2.5)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.desensitize_filter import DesensitizeFilter


class TestSensitiveKeys(unittest.TestCase):

    def setUp(self):
        self.f = DesensitizeFilter()

    def test_cookie_masked(self):
        result = self.f.filter_dict({"cookie": "session=abc123xyz"})
        self.assertNotEqual(result["cookie"], "session=abc123xyz")
        self.assertIn("脱敏", result["cookie"])

    def test_token_masked(self):
        result = self.f.filter_dict({"token": "eyJhbGciOiJIUzI1NiJ9.longtoken"})
        self.assertIn("脱敏", result["token"])

    def test_password_masked(self):
        result = self.f.filter_dict({"password": "REDACTED_TEST_VALUE"})
        self.assertIn("脱敏", result["password"])

    def test_non_sensitive_preserved(self):
        result = self.f.filter_dict({"username": "testuser", "age": 25})
        self.assertEqual(result["username"], "testuser")
        self.assertEqual(result["age"], 25)

    def test_case_insensitive_keys(self):
        result = self.f.filter_dict({"Cookie": "abc123", "TOKEN": "xyz789"})
        self.assertIn("脱敏", result["Cookie"])
        self.assertIn("脱敏", result["TOKEN"])


class TestNestedStructures(unittest.TestCase):

    def setUp(self):
        self.f = DesensitizeFilter()

    def test_nested_dict(self):
        data = {"user": {"name": "test", "password": "REDACTED_TEST_VALUE"}}
        result = self.f.filter_dict(data)
        self.assertEqual(result["user"]["name"], "test")
        self.assertIn("脱敏", result["user"]["password"])

    def test_list_of_dicts(self):
        data = [{"token": "abc123"}, {"name": "test"}]
        result = self.f.filter_dict(data)
        self.assertIn("脱敏", result[0]["token"])
        self.assertEqual(result[1]["name"], "test")

    def test_deep_nesting(self):
        data = {"level1": {"level2": {"level3": {"secret": "deep_value"}}}}
        result = self.f.filter_dict(data)
        self.assertIn("脱敏", result["level1"]["level2"]["level3"]["secret"])


class TestPatternMatching(unittest.TestCase):

    def setUp(self):
        self.f = DesensitizeFilter()

    def test_phone_number(self):
        result = self.f.filter_dict({"message": "联系手机号 13812345678 获取帮助"})
        self.assertIn("手机号已脱敏", result["message"])

    def test_id_card(self):
        result = self.f.filter_dict({"message": "身份证号 110101199001011234 已验证"})
        self.assertIn("身份证已脱敏", result["message"])

    def test_email(self):
        result = self.f.filter_dict({"message": "邮箱 user@example.com 已发送"})
        self.assertIn("邮箱已脱敏", result["message"])

    def test_bearer_token(self):
        result = self.f.filter_dict({"header": "Bearer eyJhbGciOiJIUzI1NiJ9longtokenvalue"})
        self.assertIn("token已脱敏", result["header"])


class TestExtraKeys(unittest.TestCase):

    def test_custom_sensitive_key(self):
        f = DesensitizeFilter(extra_keys={"mySecret", "internalCode"})
        result = f.filter_dict({"mySecret": "hidden", "public": "visible"})
        self.assertIn("脱敏", result["mySecret"])
        self.assertEqual(result["public"], "visible")


class TestFilterEvidence(unittest.TestCase):

    def test_filter_evidence_trace(self):
        f = DesensitizeFilter()
        trace = {
            "trace_id": "run1",
            "entries": [
                {"tool": "click", "input": {"token": "abc123"}, "output": {"clicked": True}},
            ],
        }
        result = f.filter_evidence(trace)
        self.assertEqual(result["trace_id"], "run1")
        self.assertIn("脱敏", result["entries"][0]["input"]["token"])


class TestStats(unittest.TestCase):

    def test_stats_tracking(self):
        f = DesensitizeFilter()
        f.filter_dict({"token": "abc", "password": "xyz"})
        stats = f.get_stats()
        self.assertEqual(stats["keys_masked"], 2)

    def test_reset_stats(self):
        f = DesensitizeFilter()
        f.filter_dict({"token": "abc"})
        f.reset_stats()
        stats = f.get_stats()
        self.assertEqual(stats["keys_masked"], 0)


class TestEdgeCases(unittest.TestCase):

    def test_none_value(self):
        f = DesensitizeFilter()
        result = f.filter_dict({"token": None})
        self.assertIsNone(result["token"])

    def test_empty_dict(self):
        f = DesensitizeFilter()
        result = f.filter_dict({})
        self.assertEqual(result, {})

    def test_non_dict_types(self):
        f = DesensitizeFilter()
        self.assertEqual(f.filter_dict(42), 42)
        self.assertEqual(f.filter_dict(True), True)

    def test_list_value_for_sensitive_key(self):
        f = DesensitizeFilter()
        result = f.filter_dict({"cookies": [{"name": "a", "value": "b"}]})
        self.assertIn("脱敏", result["cookies"])


if __name__ == "__main__":
    unittest.main()
