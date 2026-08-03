"""test_log_level.py — 日志级别常量与过滤函数单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.log_level import (
    LogLevel,
    get_min_level_from_env,
    passes_filter,
    validate_level,
)


class TestPassesFilter(unittest.TestCase):

    def test_equal_level_passes(self):
        self.assertTrue(passes_filter("INFO", "INFO"))

    def test_higher_level_passes(self):
        self.assertTrue(passes_filter("ERROR", "WARNING"))
        self.assertTrue(passes_filter("WARNING", "INFO"))

    def test_lower_level_filtered(self):
        self.assertFalse(passes_filter("INFO", "WARNING"))
        self.assertFalse(passes_filter("DEBUG", "INFO"))

    def test_debug_passes_when_min_is_debug(self):
        self.assertTrue(passes_filter("DEBUG", "DEBUG"))

    def test_error_always_passes(self):
        for min_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.assertTrue(passes_filter("ERROR", min_level))

    def test_unknown_entry_level_treated_as_zero(self):
        # 未知级别数值为 0，低于任何有效 min_level，被过滤
        self.assertFalse(passes_filter("TRACE", "DEBUG"))

    def test_unknown_min_level_treated_as_zero(self):
        # min_level 未知时数值为 0，任何有效 entry_level 都通过
        self.assertTrue(passes_filter("DEBUG", "VERBOSE"))

    def test_both_unknown_passes(self):
        # 0 >= 0
        self.assertTrue(passes_filter("FOO", "BAR"))


class TestValidateLevel(unittest.TestCase):

    def test_valid_levels_returned_as_is(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.assertEqual(validate_level(level), level)

    def test_invalid_level_falls_back_to_info(self):
        self.assertEqual(validate_level("TRACE"), LogLevel.INFO)
        self.assertEqual(validate_level(""), LogLevel.INFO)

    def test_case_sensitive(self):
        # 小写不合法，回退 INFO
        self.assertEqual(validate_level("info"), LogLevel.INFO)


class TestGetMinLevelFromEnv(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("WEB_AUTO_LOG_LEVEL")
        os.environ.pop("WEB_AUTO_LOG_LEVEL", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("WEB_AUTO_LOG_LEVEL", None)
        else:
            os.environ["WEB_AUTO_LOG_LEVEL"] = self._saved

    def test_default_when_unset(self):
        self.assertEqual(get_min_level_from_env(), LogLevel.INFO)

    def test_reads_valid_env_value(self):
        os.environ["WEB_AUTO_LOG_LEVEL"] = "ERROR"
        self.assertEqual(get_min_level_from_env(), "ERROR")

    def test_lowercase_env_normalized_to_upper(self):
        os.environ["WEB_AUTO_LOG_LEVEL"] = "warning"
        self.assertEqual(get_min_level_from_env(), "WARNING")

    def test_invalid_env_falls_back_to_default(self):
        os.environ["WEB_AUTO_LOG_LEVEL"] = "NOPE"
        self.assertEqual(get_min_level_from_env(), LogLevel.INFO)

    def test_empty_env_falls_back_to_default(self):
        os.environ["WEB_AUTO_LOG_LEVEL"] = ""
        self.assertEqual(get_min_level_from_env(), LogLevel.INFO)


if __name__ == "__main__":
    unittest.main()
