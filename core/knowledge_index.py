"""
knowledge_index.py — 统一知识体系入口

整合三套知识来源，提供单一检索 API：
1. knowledge/*.json — 页面级场景知识（由 knowledge/index.json 索引）
2. references/*.md  — 通用参考文档（操作手册、错误模式映射等）
3. core/knowledge_base.py — KnowledgeBase 四类目结构化存储 + 记忆晋升

使用方式：
    from core.knowledge_index import KnowledgeIndex
    ki = KnowledgeIndex(root=".")
    results = ki.search("登录态失效", limit=5)
    page_knowledge = ki.get_page_knowledge(url="https://xiaoer.alibaba-inc.com/quality-pulse/product-management")
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from core.knowledge_base import KnowledgeBase, KnowledgeEntry

@dataclass
class PageKnowledge:
    """页面级知识（来自 knowledge/*.json）"""
    id: str
    platform: str
    description: str
    host: str
    route: str
    file: str
    covers: List[str] = field(default_factory=list)
    selectors: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    auth: dict = field(default_factory=dict)
    skill: Optional[str] = None

@dataclass
class ReferenceDoc:
    """参考文档（来自 references/*.md 或 .json）"""
    filename: str
    title: str
    content: str
    doc_type: str = "markdown"  # markdown / json

@dataclass
class UnifiedSearchResult:
    """统一搜索结果"""
    source: str       # "knowledge_base" / "page_knowledge" / "reference"
    title: str
    content: str
    score: float = 0.0
    metadata: dict = field(default_factory=dict)

class KnowledgeIndex:
    """
    统一知识索引：聚合三套知识来源，提供统一检索接口。

    知识来源优先级：
    1. KnowledgeBase（结构化知识库，含 patterns/features/infra/contracts）
    2. Page Knowledge（页面级场景知识，URL 匹配）
    3. References（参考文档，关键词匹配）
    """

    def __init__(self, root: str = None):
        """
        Args:
            root: 项目根目录，默认为当前文件向上两级
        """
        if root is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._root = root

        # 1. KnowledgeBase
        kb_root = os.path.join(root, "harness", "knowledge")
        self._kbase = KnowledgeBase(root=kb_root)

        # 2. Page Knowledge Index
        self._page_index: List[dict] = []
        self._load_page_index()

        # 3. Reference docs (lazy loaded)
        self._references: Optional[List[ReferenceDoc]] = None

    # ── 加载 ──

    def _load_page_index(self):
        """加载 knowledge/index.json 页面索引。"""
        index_path = os.path.join(self._root, "knowledge", "index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._page_index = data.get("entries", [])
            except (json.JSONDecodeError, IOError):
                self._page_index = []

    def _load_references(self) -> List[ReferenceDoc]:
        """懒加载 references/ 目录下的参考文档。"""
        if self._references is not None:
            return self._references
        self._references = []
        ref_dir = os.path.join(self._root, "references")
        if not os.path.isdir(ref_dir):
            return self._references
        for fname in sorted(os.listdir(ref_dir)):
            fpath = os.path.join(ref_dir, fname)
            if not os.path.isfile(fpath):
                continue
            title = os.path.splitext(fname)[0].replace("-", " ").replace("_", " ").title()
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                doc_type = "json" if fname.endswith(".json") else "markdown"
                self._references.append(ReferenceDoc(
                    filename=fname, title=title, content=content, doc_type=doc_type
                ))
            except IOError:
                continue
        return self._references

    # ── 中文感知分词 ──

    @staticmethod
    def _tokenize(query: str) -> list:
        """
        中文感知分词：空格分词 + 中文连续字符 bigram 拆分。

        例："F88模板匹配规则" → ["f88模板匹配规则", "f88", "模板", "板匹", "匹配", "配规", "规则"]
        """
        q = query.lower().strip()
        tokens = set()
        # 1) 空格分词
        for part in q.split():
            if part:
                tokens.add(part)
        # 2) 中文连续字符 → bigram
        chinese_segments = re.findall(r'[\u4e00-\u9fff]{2,}', q)
        for seg in chinese_segments:
            tokens.add(seg)  # 整体也加入
            for i in range(len(seg) - 1):
                tokens.add(seg[i:i+2])
        # 3) 英文/数字连续段也提取
        alpha_segments = re.findall(r'[a-z0-9_]{2,}', q)
        for seg in alpha_segments:
            tokens.add(seg)
        return list(tokens)

    # ── 统一检索 ──

    def search(self, query: str, limit: int = 10, sources: List[str] = None) -> List[UnifiedSearchResult]:
        """
        统一知识检索。

        Args:
            query: 检索关键词（URL、场景描述、错误信息等）
            limit: 最多返回结果数
            sources: 限定搜索源 ["knowledge_base", "page_knowledge", "reference"]，
                     默认 None 表示搜索所有源

        Returns:
            按相关性排序的统一搜索结果
        """
        results: List[UnifiedSearchResult] = []
        allowed = set(sources) if sources else {"knowledge_base", "page_knowledge", "reference"}

        # 1. KnowledgeBase 搜索（分数归一化到 0-1）
        if "knowledge_base" in allowed:
            try:
                kb_results = self._kbase.search(query, limit=limit)
                for sr in kb_results:
                    # KB 原始分数是累积制（标题+3/内容+1/标签+2），归一化到 0-1
                    normalized_score = min(sr.score / 15.0, 1.0)
                    results.append(UnifiedSearchResult(
                        source="knowledge_base",
                        title=sr.entry.title,
                        content=sr.entry.content,
                        score=normalized_score,
                        metadata={
                            "category": sr.entry.category,
                            "tags": sr.entry.tags,
                            "level": sr.entry.level,
                        },
                    ))
            except Exception:
                pass

        # 2. Page Knowledge 匹配（索引 + 详情全文）
        if "page_knowledge" in allowed:
            page_results = self._search_page_knowledge(query)
            results.extend(page_results)
            # 2b. 详情文件全文搜索（补充索引未命中的内容）
            ft_results = self._search_page_knowledge_fulltext(query, limit=limit)
            results.extend(ft_results)

        # 3. Reference 关键词匹配
        if "reference" in allowed:
            ref_results = self._search_references(query, limit=limit)
            results.extend(ref_results)

        # 按 score 降序排序，去重（同 title 只保留最高分），取 top N
        results.sort(key=lambda r: r.score, reverse=True)
        seen_titles = set()
        deduped = []
        for r in results:
            if r.title not in seen_titles:
                seen_titles.add(r.title)
                deduped.append(r)
        return deduped[:limit]

    # ── 页面知识 ──

    def get_page_knowledge(self, url: str) -> Optional[PageKnowledge]:
        """
        根据 URL 精确匹配页面知识。

        匹配规则：URL 同时包含 host 且包含 route 时命中。
        """
        for entry in self._page_index:
            host = entry.get("host", "")
            host_pre = entry.get("hostPre", "")
            route = entry.get("route", "")
            if (host and host in url or host_pre and host_pre in url) and route and route in url:
                return self._load_page_detail(entry)
        return None

    def _load_page_detail(self, index_entry: dict) -> PageKnowledge:
        """加载页面知识的详细 JSON 文件。"""
        pk = PageKnowledge(
            id=index_entry.get("id", ""),
            platform=index_entry.get("platform", ""),
            description=index_entry.get("description", ""),
            host=index_entry.get("host", ""),
            route=index_entry.get("route", ""),
            file=index_entry.get("file", ""),
            covers=index_entry.get("covers", []),
            auth=index_entry.get("auth", {}),
            skill=index_entry.get("skill"),
        )
        # 加载详细 JSON
        detail_path = os.path.join(self._root, index_entry.get("file", ""))
        if os.path.exists(detail_path):
            try:
                with open(detail_path, "r", encoding="utf-8") as f:
                    detail = json.load(f)
                pk.selectors = detail.get("selectors", {})
                pk.steps = detail.get("steps", [])
            except (json.JSONDecodeError, IOError):
                pass
        return pk

    def _search_page_knowledge(self, query: str) -> List[UnifiedSearchResult]:
        """
        搜索页面知识索引（关键词级别匹配 + 同义词别名）。

        改进点（vs 旧版纯子串匹配）：
        - 查询分词后逐关键词匹配 covers
        - 支持 aliases 同义词映射
        - 平台名/描述也做关键词匹配而非整段子串
        """
        results = []
        query_lower = query.lower()
        tokens = self._tokenize(query)

        for entry in self._page_index:
            score = 0.0
            platform = entry.get("platform", "").lower()
            description = entry.get("description", "").lower()
            covers = entry.get("covers", [])
            aliases = entry.get("aliases", [])

            # URL 精确匹配（最高优先级）
            if entry.get("host", "") in query or entry.get("route", "") in query:
                score = 1.0
            # 平台名/别名匹配
            elif any(t in platform for t in tokens) or any(
                alias.lower() in query_lower or query_lower in alias.lower()
                for alias in aliases
            ):
                score = 0.85
            # 描述关键词匹配
            elif any(t in description for t in tokens if len(t) >= 2):
                score = 0.7
            else:
                # covers 关键词级别匹配
                matched_covers = 0
                for cover in covers:
                    cover_lower = cover.lower()
                    # 整体子串匹配
                    if query_lower in cover_lower or cover_lower in query_lower:
                        matched_covers += 1
                        continue
                    # 分词后逐 token 匹配
                    for token in tokens:
                        if len(token) >= 2 and token in cover_lower:
                            matched_covers += 1
                            break
                if matched_covers > 0:
                    # 多 cover 命中加分
                    score = min(0.6 + 0.05 * (matched_covers - 1), 0.8)

            if score > 0:
                results.append(UnifiedSearchResult(
                    source="page_knowledge",
                    title=f"{entry.get('platform', '')} - {entry.get('description', '')}",
                    content=json.dumps(entry, ensure_ascii=False)[:500],
                    score=score,
                    metadata={"id": entry.get("id", ""), "file": entry.get("file", "")},
                ))
        return results

    def _search_page_knowledge_fulltext(self, query: str, limit: int = 5) -> List[UnifiedSearchResult]:
        """
        在知识详情 JSON 文件中进行全文搜索。

        补充 _search_page_knowledge 只搜 index covers 的不足：
        打开详情 JSON，搜索 selectors/knownIssues/steps/其他字段的内容。
        """
        results = []
        tokens = self._tokenize(query)
        # 过滤太短的 token（避免噪音）
        tokens = [t for t in tokens if len(t) >= 2]
        if not tokens:
            return results

        for entry in self._page_index:
            detail_path = os.path.join(self._root, entry.get("file", ""))
            if not os.path.exists(detail_path):
                continue
            try:
                with open(detail_path, "r", encoding="utf-8") as f:
                    detail_text = f.read()
            except IOError:
                continue

            detail_lower = detail_text.lower()
            matched_tokens = sum(1 for t in tokens if t in detail_lower)
            if matched_tokens > 0:
                # 按命中 token 比例打分，上限 0.5（低于索引级匹配）
                ratio = matched_tokens / len(tokens)
                score = min(0.3 + 0.2 * ratio, 0.5)
                # 取匹配上下文摘要
                snippet = self._extract_snippet(detail_text, tokens)
                results.append(UnifiedSearchResult(
                    source="page_knowledge",
                    title=f"{entry.get('platform', '')} - {entry.get('description', '')} (全文)",
                    content=snippet,
                    score=score,
                    metadata={"id": entry.get("id", ""), "file": entry.get("file", "")},
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    @staticmethod
    def _extract_snippet(text: str, tokens: list, max_len: int = 300) -> str:
        """从文本中提取包含关键词的上下文摘要。"""
        text_lower = text.lower()
        best_pos = -1
        for token in tokens:
            pos = text_lower.find(token)
            if pos >= 0:
                best_pos = pos
                break
        if best_pos < 0:
            return text[:max_len].strip()
        start = max(0, best_pos - 50)
        end = min(len(text), start + max_len)
        return text[start:end].strip()

    # ── 参考文档 ──

    def _search_references(self, query: str, limit: int = 5) -> List[UnifiedSearchResult]:
        """在参考文档中进行关键词搜索（中文感知）。"""
        refs = self._load_references()
        results = []
        query_lower = query.lower()
        tokens = self._tokenize(query)

        for ref in refs:
            title_lower = ref.title.lower()
            content_lower = ref.content.lower()
            score = 0.0

            # 标题匹配
            if query_lower in title_lower:
                score = 0.9
            elif any(t in title_lower for t in tokens if len(t) >= 2):
                score = 0.7
            else:
                # 关键词部分匹配（用 token 而非原始 split）
                matched = sum(1 for t in tokens if len(t) >= 2 and t in content_lower[:3000])
                if matched > 0:
                    score = 0.3 + 0.15 * min(matched, 5) / 5

            if score > 0:
                # 取内容摘要（前 300 字符）
                snippet = ref.content[:300].strip()
                results.append(UnifiedSearchResult(
                    source="reference",
                    title=ref.title,
                    content=snippet,
                    score=score,
                    metadata={"filename": ref.filename, "doc_type": ref.doc_type},
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    # ── KnowledgeBase 代理方法 ──

    @property
    def knowledge_base(self) -> KnowledgeBase:
        """获取底层 KnowledgeBase 实例（用于高级操作）。"""
        return self._kbase

    def add_entry(self, entry: KnowledgeEntry):
        """向 KnowledgeBase 添加条目。"""
        self._kbase.add_entry(entry)

    def record_hit(self, entry: KnowledgeEntry):
        """记录知识条目被命中。"""
        self._kbase.record_hit(entry)

    # ── 统计 ──

    def get_stats(self) -> dict:
        """返回知识索引统计信息。"""
        refs = self._load_references()
        return {
            "knowledge_base_entries": len(self._kbase._entries) if hasattr(self._kbase, '_entries') else 0,
            "page_knowledge_entries": len(self._page_index),
            "reference_docs": len(refs),
            "reference_types": {
                "markdown": sum(1 for r in refs if r.doc_type == "markdown"),
                "json": sum(1 for r in refs if r.doc_type == "json"),
            },
        }
