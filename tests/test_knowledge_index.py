"""test_knowledge_index.py — 统一知识体系入口单元测试"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.knowledge_index import (
    KnowledgeIndex,
    PageKnowledge,
    UnifiedSearchResult,
)


class TestTokenize(unittest.TestCase):

    def test_space_split(self):
        tokens = KnowledgeIndex._tokenize("login timeout")
        self.assertIn("login", tokens)
        self.assertIn("timeout", tokens)

    def test_chinese_bigram(self):
        tokens = KnowledgeIndex._tokenize("模板匹配")
        self.assertIn("模板", tokens)
        self.assertIn("板匹", tokens)
        self.assertIn("匹配", tokens)

    def test_lowercase(self):
        self.assertIn("f88", KnowledgeIndex._tokenize("F88"))

    def test_alpha_num_segment(self):
        self.assertIn("abc123", KnowledgeIndex._tokenize("abc123 test"))


class TestExtractSnippet(unittest.TestCase):

    def test_returns_context_around_token(self):
        text = "prefix " * 20 + "TARGET_KEYWORD" + " suffix" * 20
        snippet = KnowledgeIndex._extract_snippet(text, ["target_keyword"], max_len=100)
        self.assertIn("TARGET_KEYWORD", snippet)

    def test_no_match_returns_head(self):
        snippet = KnowledgeIndex._extract_snippet("abcdefg", ["zzz"], max_len=3)
        self.assertEqual(snippet, "abc")


class _RootFixture(unittest.TestCase):
    """构造受控的临时知识根目录"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

        # KnowledgeBase 根目录
        os.makedirs(os.path.join(self.root, "harness", "knowledge"), exist_ok=True)

        # 页面知识索引 + 详情
        os.makedirs(os.path.join(self.root, "knowledge", "pages"), exist_ok=True)
        index = {
            "entries": [
                {
                    "id": "pm-page",
                    "platform": "小二平台",
                    "description": "商品管理页面",
                    "host": "xiaoer.alibaba-inc.com",
                    "route": "/product-management",
                    "file": "knowledge/pages/pm.json",
                    "covers": ["商品上架", "商品下架"],
                    "aliases": ["商品管理"],
                }
            ]
        }
        with open(os.path.join(self.root, "knowledge", "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        with open(os.path.join(self.root, "knowledge", "pages", "pm.json"), "w", encoding="utf-8") as f:
            json.dump({"selectors": {"btn": "#publish"}, "steps": [{"type": "click"}],
                       "knownIssues": "偶发弹窗遮挡"}, f, ensure_ascii=False)

        # 参考文档
        os.makedirs(os.path.join(self.root, "references"), exist_ok=True)
        with open(os.path.join(self.root, "references", "login-guide.md"), "w", encoding="utf-8") as f:
            f.write("# Login Guide\n\n处理登录态失效与 SSO warmup 的操作手册。")

        self.ki = KnowledgeIndex(root=self.root)


class TestGetPageKnowledge(_RootFixture):

    def test_url_match_returns_page(self):
        pk = self.ki.get_page_knowledge("https://xiaoer.alibaba-inc.com/product-management/list")
        self.assertIsInstance(pk, PageKnowledge)
        self.assertEqual(pk.id, "pm-page")
        # 详情文件加载了 selectors
        self.assertEqual(pk.selectors["btn"], "#publish")

    def test_no_match_returns_none(self):
        self.assertIsNone(self.ki.get_page_knowledge("https://other.com/x"))

    def test_partial_match_host_only_returns_none(self):
        # 仅 host 匹配、route 不匹配 → 不命中
        self.assertIsNone(self.ki.get_page_knowledge("https://xiaoer.alibaba-inc.com/other"))


class TestSearch(_RootFixture):

    def test_reference_hit(self):
        results = self.ki.search("SSO warmup", sources=["reference"])
        self.assertTrue(any(r.source == "reference" for r in results))

    def test_page_knowledge_hit_by_alias(self):
        results = self.ki.search("商品管理", sources=["page_knowledge"])
        self.assertTrue(any(r.source == "page_knowledge" for r in results))

    def test_limit_respected(self):
        results = self.ki.search("商品", limit=1)
        self.assertLessEqual(len(results), 1)

    def test_results_are_unified_type(self):
        results = self.ki.search("登录", sources=["reference"])
        for r in results:
            self.assertIsInstance(r, UnifiedSearchResult)

    def test_dedup_by_title(self):
        results = self.ki.search("商品管理")
        titles = [r.title for r in results]
        self.assertEqual(len(titles), len(set(titles)))

    def test_sources_filter_excludes_others(self):
        results = self.ki.search("登录", sources=["reference"])
        self.assertTrue(all(r.source == "reference" for r in results))


class TestStats(_RootFixture):

    def test_stats_counts(self):
        stats = self.ki.get_stats()
        self.assertEqual(stats["page_knowledge_entries"], 1)
        self.assertGreaterEqual(stats["reference_docs"], 1)
        self.assertIn("reference_types", stats)


class TestEmptyRoot(unittest.TestCase):

    def test_missing_index_no_error(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "harness", "knowledge"), exist_ok=True)
        ki = KnowledgeIndex(root=root)
        self.assertEqual(ki.get_stats()["page_knowledge_entries"], 0)
        self.assertIsNone(ki.get_page_knowledge("https://x.com/y"))
        self.assertEqual(ki.search("anything"), [])


if __name__ == "__main__":
    unittest.main()
