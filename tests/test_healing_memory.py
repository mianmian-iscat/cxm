"""test_healing_memory.py — 自愈经验记忆与晋升引擎单元测试"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.healing_memory import HealingMemory, HealingExperience


class TestHealingExperience(unittest.TestCase):

    def test_confidence_zero_when_no_data(self):
        exp = HealingExperience(error_pattern="p", fix_strategy="s", success_count=0)
        self.assertEqual(exp.confidence, 0.0)

    def test_confidence_ratio(self):
        exp = HealingExperience(error_pattern="p", fix_strategy="s",
                                success_count=3, fail_count=1)
        self.assertEqual(exp.confidence, 0.75)

    def test_to_dict_has_confidence(self):
        d = HealingExperience(error_pattern="p", fix_strategy="s").to_dict()
        self.assertIn("confidence", d)
        self.assertIn("scene", d)


class TestRecord(unittest.TestCase):

    def setUp(self):
        self.mem = HealingMemory()

    def test_record_success_increments(self):
        self.mem.record_success("timeout", "retry")
        self.mem.record_success("timeout", "retry")
        exps = self.mem.get_all_experiences()
        self.assertEqual(len(exps), 1)
        self.assertEqual(exps[0]["success_count"], 3)  # 初始 1 + 2

    def test_record_failure_increments(self):
        self.mem.record_failure("timeout", "retry")
        stats = self.mem.get_stats()
        self.assertEqual(stats["total_fail"], 1)

    def test_success_resets_consecutive_fails(self):
        for _ in range(2):
            self.mem.record_failure("timeout", "retry")
        self.mem.record_success("timeout", "retry")
        self.assertFalse(self.mem.is_blacklisted("timeout"))

    def test_different_strategy_creates_separate_entry(self):
        self.mem.record_success("timeout", "retryA")
        self.mem.record_success("timeout", "retryB")
        self.assertEqual(len(self.mem.get_all_experiences()), 2)

    def test_context_merged(self):
        self.mem.record_success("timeout", "retry", context={"selector": "#a"})
        exps = self.mem.get_all_experiences()
        self.assertEqual(exps[0]["context"]["selector"], "#a")


class TestBlacklist(unittest.TestCase):

    def setUp(self):
        self.mem = HealingMemory()

    def test_blacklisted_after_consecutive_fails(self):
        for _ in range(HealingMemory.CONSECUTIVE_FAIL_LIMIT):
            self.mem.record_failure("timeout", "retry")
        self.assertTrue(self.mem.is_blacklisted("timeout"))

    def test_not_blacklisted_below_limit(self):
        self.mem.record_failure("timeout", "retry")
        self.assertFalse(self.mem.is_blacklisted("timeout"))

    def test_get_blacklisted_patterns(self):
        for _ in range(3):
            self.mem.record_failure("network err", "retry")
        self.assertTrue(len(self.mem.get_blacklisted_patterns()) >= 1)


class TestLookup(unittest.TestCase):

    def setUp(self):
        self.mem = HealingMemory()

    def test_empty_lookup(self):
        self.assertEqual(self.mem.lookup("anything"), [])

    def test_exact_regex_match(self):
        self.mem.record_success("timeout", "retry")
        hits = self.mem.lookup("element timeout occurred")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].fix_strategy, "retry")

    def test_top_k_limit(self):
        for i in range(5):
            self.mem.record_success(f"timeout case {i}", f"fix{i}")
        hits = self.mem.lookup("timeout", top_k=2)
        self.assertLessEqual(len(hits), 2)

    def test_sorted_by_confidence(self):
        self.mem.record_success("timeout", "good")   # confidence 1.0
        self.mem.record_success("timeout", "bad")
        self.mem.record_failure("timeout", "bad")    # confidence 0.5
        hits = self.mem.lookup("timeout error")
        self.assertEqual(hits[0].fix_strategy, "good")


class TestStaticHelpers(unittest.TestCase):

    def test_pattern_key_normalizes(self):
        self.assertEqual(HealingMemory._pattern_key("  Time Out  "), "timeout")

    def test_edit_distance_identical(self):
        self.assertEqual(HealingMemory._edit_distance_similarity("abc", "abc"), 1.0)

    def test_edit_distance_both_empty(self):
        self.assertEqual(HealingMemory._edit_distance_similarity("", ""), 1.0)

    def test_keyword_overlap_jaccard(self):
        self.assertEqual(
            HealingMemory._keyword_overlap(["a", "b"], ["b", "c"]), 1 / 3
        )

    def test_keyword_overlap_empty(self):
        self.assertEqual(HealingMemory._keyword_overlap([], ["a"]), 0.0)

    def test_match_score_regex(self):
        self.assertEqual(HealingMemory._match_score("timeout", "a timeout b"), 1.0)

    def test_match_score_invalid_regex_falls_back_to_keywords(self):
        # "[" 是非法正则，应退回关键词匹配而非抛异常
        score = HealingMemory._match_score("[unclosed", "some text")
        self.assertIsInstance(score, float)

    def test_patterns_similar_substring(self):
        self.assertTrue(HealingMemory._patterns_similar("timeout", "timeout error"))

    def test_patterns_similar_empty(self):
        self.assertFalse(HealingMemory._patterns_similar("", "x"))

    def test_extract_keywords_filters_short_and_digits(self):
        kws = HealingMemory._extract_keywords("timeout.error 123 ab")
        self.assertIn("timeout", kws)
        self.assertNotIn("123", kws)
        self.assertNotIn("ab", kws)


class TestPromotion(unittest.TestCase):

    def setUp(self):
        self.mem = HealingMemory()
        self.base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base_dir, True)

    def test_promotable_requires_min_count(self):
        # HealingExperience 默认 success_count=1，手动构造 count=1 的经验不满足 PROMOTE_MIN_COUNT(2)
        self.mem._experiences.append(
            HealingExperience(error_pattern="timeout", fix_strategy="retry", success_count=1)
        )
        self.assertEqual(self.mem.get_promotable(), [])

    def test_single_record_success_reaches_promote_count(self):
        # record_success 在默认 1 的基础上 +1 → count=2，达到晋升下限
        self.mem.record_success("timeout dropdown", "retry")
        self.assertEqual(len(self.mem.get_promotable()), 1)

    def test_promotable_meets_threshold(self):
        self.mem.record_success("timeout dropdown", "retry")
        self.mem.record_success("timeout dropdown", "retry")
        self.assertEqual(len(self.mem.get_promotable()), 1)

    def test_low_confidence_not_promotable(self):
        for _ in range(2):
            self.mem.record_success("timeout", "retry")
        for _ in range(3):
            self.mem.record_failure("timeout", "retry")
        # confidence 2/5 = 0.4 < 0.7
        self.assertEqual(self.mem.get_promotable(), [])

    def test_promote_writes_file(self):
        self.mem.record_success("timeout dropdown", "click arrow")
        self.mem.record_success("timeout dropdown", "click arrow")
        result = self.mem.promote_to_knowledge(self.base_dir)
        self.assertEqual(result["promoted"], 1)
        map_path = os.path.join(self.base_dir, "references", "error-pattern-map.json")
        self.assertTrue(os.path.exists(map_path))
        with open(map_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["mappings"]), 1)

    def test_promote_marks_source(self):
        self.mem.record_success("timeout dropdown", "click arrow")
        self.mem.record_success("timeout dropdown", "click arrow")
        self.mem.promote_to_knowledge(self.base_dir)
        # 晋升后 source 变为 promoted，不再可晋升
        self.assertEqual(self.mem.get_promotable(), [])

    def test_promote_empty_returns_zero(self):
        result = self.mem.promote_to_knowledge(self.base_dir)
        self.assertEqual(result["promoted"], 0)


class TestLoadAndRoundTrip(unittest.TestCase):

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base_dir, True)

    def test_load_missing_file_no_error(self):
        mem = HealingMemory()
        mem.load_from_knowledge(self.base_dir)  # 不应抛异常
        self.assertEqual(mem.get_stats()["total_experiences"], 0)

    def test_promote_then_load_roundtrip(self):
        writer = HealingMemory()
        writer.record_success("timeout dropdown", "click arrow")
        writer.record_success("timeout dropdown", "click arrow")
        writer.promote_to_knowledge(self.base_dir)

        reader = HealingMemory()
        reader.load_from_knowledge(self.base_dir)
        stats = reader.get_stats()
        self.assertEqual(stats["loaded_count"], 1)


class TestLookupGlobal(unittest.TestCase):

    def test_scene_match_prioritized(self):
        mem = HealingMemory()
        mem._experiences.append(
            HealingExperience(error_pattern="timeout", fix_strategy="scene_fix", scene="f88")
        )
        mem._experiences.append(
            HealingExperience(error_pattern="timeout", fix_strategy="global_fix", scene="global")
        )
        hits = mem.lookup_global("timeout error", current_scene="f88")
        self.assertTrue(hits)
        self.assertEqual(hits[0].fix_strategy, "scene_fix")


if __name__ == "__main__":
    unittest.main()
