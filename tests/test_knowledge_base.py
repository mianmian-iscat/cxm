"""test_knowledge_base.py — 知识层与记忆晋升单元测试 (Gap 2.1)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.knowledge_base import KnowledgeBase, KnowledgeEntry, MemoryLayer, SearchResult


class TestKnowledgeEntry(unittest.TestCase):

    def test_to_dict_roundtrip(self):
        entry = KnowledgeEntry(category="patterns", title="登录态失效", content="cookie过期导致")
        d = entry.to_dict()
        restored = KnowledgeEntry.from_dict(d)
        self.assertEqual(restored.title, "登录态失效")
        self.assertEqual(restored.category, "patterns")

    def test_default_values(self):
        entry = KnowledgeEntry(category="features", title="test", content="body")
        self.assertEqual(entry.retrieval_count, 0)
        self.assertEqual(entry.level, 0)


class TestKnowledgeBase(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase(root="/tmp/_test_kb_nonexistent")

    def test_add_entry(self):
        entry = KnowledgeEntry(category="patterns", title="Bug1", content="desc")
        self.assertTrue(self.kb.add_entry(entry))
        self.assertEqual(len(self.kb.get_entries("patterns")), 1)

    def test_add_invalid_category(self):
        entry = KnowledgeEntry(category="unknown", title="x", content="y")
        self.assertFalse(self.kb.add_entry(entry))

    def test_remove_entry(self):
        entry = KnowledgeEntry(category="patterns", title="Bug1", content="desc")
        self.kb.add_entry(entry)
        self.assertTrue(self.kb.remove_entry("patterns", "Bug1"))
        self.assertEqual(len(self.kb.get_entries("patterns")), 0)

    def test_remove_nonexistent(self):
        self.assertFalse(self.kb.remove_entry("patterns", "nope"))

    def test_search_by_keyword(self):
        self.kb.add_entry(KnowledgeEntry(category="patterns", title="登录态失效", content="cookie过期"))
        self.kb.add_entry(KnowledgeEntry(category="patterns", title="页面白屏", content="JS报错"))
        results = self.kb.search("登录")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entry.title, "登录态失效")

    def test_search_by_tag(self):
        self.kb.add_entry(KnowledgeEntry(
            category="patterns", title="Bug1", content="desc", tags=["P0", "login"]
        ))
        results = self.kb.search("Bug1", tags=["P0"])
        self.assertEqual(len(results), 1)

    def test_search_category_filter(self):
        self.kb.add_entry(KnowledgeEntry(category="patterns", title="test", content="hello"))
        self.kb.add_entry(KnowledgeEntry(category="features", title="test2", content="hello"))
        results = self.kb.search("hello", categories=["patterns"])
        self.assertEqual(len(results), 1)

    def test_search_empty(self):
        results = self.kb.search("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_increments_retrieval_count(self):
        entry = KnowledgeEntry(category="patterns", title="Bug1", content="desc")
        self.kb.add_entry(entry)
        self.kb.search("Bug1")
        self.assertEqual(entry.retrieval_count, 1)

    def test_record_hit(self):
        entry = KnowledgeEntry(category="patterns", title="Bug1", content="desc")
        self.kb.add_entry(entry)
        self.kb.record_hit(entry)
        self.assertEqual(entry.hit_count, 1)


class TestPromotion(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase(root="/tmp/_test_kb_nonexistent")

    def test_auto_promotion_on_retrieval(self):
        entry = KnowledgeEntry(category="patterns", title="Bug1", content="desc", level=0)
        self.kb.add_entry(entry)
        # Simulate 3 retrievals
        for _ in range(3):
            self.kb.search("Bug1")
        # Entry should be promoted
        self.assertGreaterEqual(entry.level, 1)

    def test_auto_promotion_on_hit(self):
        entry = KnowledgeEntry(category="patterns", title="Bug2", content="desc", level=0)
        self.kb.add_entry(entry)
        for _ in range(2):
            self.kb.record_hit(entry)
        self.assertGreaterEqual(entry.level, 1)

    def test_promote_session_to_daily(self):
        entry = KnowledgeEntry(category="patterns", title="S1", content="session data", level=0)
        self.kb.add_entry(entry)
        self.kb.promote_session_to_daily("session-001")
        self.assertEqual(entry.level, 1)

    def test_promotion_log(self):
        entry = KnowledgeEntry(category="patterns", title="Bug3", content="desc", level=0)
        self.kb.add_entry(entry)
        for _ in range(3):
            self.kb.search("Bug3")
        log = self.kb.get_promotion_log()
        self.assertGreater(len(log), 0)


class TestMemoryLimit(unittest.TestCase):

    def test_memory_layer_size(self):
        layer = MemoryLayer(name="test", max_size_bytes=100)
        layer.entries.append(KnowledgeEntry(category="x", title="t", content="a" * 50))
        self.assertFalse(layer.is_full)
        layer.entries.append(KnowledgeEntry(category="x", title="t2", content="b" * 60))
        self.assertTrue(layer.is_full)


class TestStats(unittest.TestCase):

    def test_get_stats(self):
        kb = KnowledgeBase(root="/tmp/_test_kb_nonexistent")
        kb.add_entry(KnowledgeEntry(category="patterns", title="B1", content="d"))
        kb.add_entry(KnowledgeEntry(category="features", title="F1", content="d"))
        stats = kb.get_stats()
        self.assertEqual(stats["total_entries"], 2)
        self.assertEqual(stats["by_category"]["patterns"], 1)
        self.assertEqual(stats["by_category"]["features"], 1)


if __name__ == "__main__":
    unittest.main()
