"""
knowledge_base.py — 知识层与记忆晋升

原创保护 Harness 知识管理：
- KBase 四类目结构化存储: features / infra / patterns / contracts
- 三层记忆晋升: session(短记忆) -> daily(日记忆) -> long(MEMORY.md) -> KBase
- 自滚机制: 被检索>=3次或命中>=2个需求 -> 自动晋升
- MEMORY.md 硬上限 10KB，超量自动降级

使用方式:
    from core.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(root="harness/knowledge")
    kb.add_entry(KnowledgeEntry(category="patterns", title="登录态失效", ...))
    results = kb.search("登录", categories=["patterns"])
"""

import os
import json
import re
import time
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None

# ── 数据模型 ──

@dataclass
class KnowledgeEntry:
    """知识条目"""
    category: str               # features / infra / patterns / contracts
    title: str
    content: str
    tags: list = field(default_factory=list)
    source: str = ""            # 来源（session_id / daily_log / manual）
    retrieval_count: int = 0
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    promoted_at: float = 0.0
    level: int = 0              # 0=raw, 1=daily, 2=long, 3=kbase
    related_entries: list = field(default_factory=list)  # 关联条目 title 列表
    embedding: list = field(default_factory=list)        # 向量嵌入（可选，由 EmbeddingProvider 填充）

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "retrieval_count": self.retrieval_count,
            "hit_count": self.hit_count,
            "created_at": self.created_at,
            "promoted_at": self.promoted_at,
            "level": self.level,
            "related_entries": self.related_entries,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(**{k: data[k] for k in data if k in cls.__dataclass_fields__})

@dataclass
class MemoryLayer:
    """记忆层"""
    name: str                   # session / daily / long / kbase
    entries: list = field(default_factory=list)
    max_size_bytes: int = 10240  # 10KB default

    @property
    def current_size_bytes(self) -> int:
        return sum(len(e.content.encode("utf-8")) for e in self.entries)

    @property
    def is_full(self) -> bool:
        return self.current_size_bytes >= self.max_size_bytes

@dataclass
class SearchResult:
    """搜索结果"""
    entry: KnowledgeEntry
    score: float = 0.0
    matched_keywords: list = field(default_factory=list)
    vector_score: float = 0.0   # 向量相似度得分（0~1）
    keyword_score: float = 0.0  # 关键词得分
    is_related: bool = False    # 是否通过关系链接发现

@dataclass
class PromotionEvent:
    """晋升事件"""
    entry_title: str
    from_level: int
    to_level: int
    reason: str
    timestamp: float = field(default_factory=time.time)

# ── 知识层引擎 ──

class KnowledgeBase:
    """
    KBase 四类目知识管理引擎。

    支持:
    - 四类目结构化存储
    - 三层记忆晋升（session -> daily -> long -> kbase）
    - 自滚机制（检索>=3次 或 命中>=2次 -> 晋升）
    - MEMORY.md 10KB 硬上限 + 超量降级
    """

    CATEGORIES = ("features", "infra", "patterns", "contracts")
    PROMOTION_RETRIEVAL_THRESHOLD = 3
    PROMOTION_HIT_THRESHOLD = 2
    MEMORY_MAX_BYTES = 10240  # 10KB

    def __init__(self, root: str = "harness/knowledge"):
        self._root = root
        self._entries: dict[str, list[KnowledgeEntry]] = {
            cat: [] for cat in self.CATEGORIES
        }
        self._memory_layers = {
            "session": MemoryLayer(name="session", max_size_bytes=self.MEMORY_MAX_BYTES),
            "daily": MemoryLayer(name="daily", max_size_bytes=self.MEMORY_MAX_BYTES),
            "long": MemoryLayer(name="long", max_size_bytes=self.MEMORY_MAX_BYTES),
            "kbase": MemoryLayer(name="kbase", max_size_bytes=self.MEMORY_MAX_BYTES * 10),
        }
        self._promotion_log: list[PromotionEvent] = []

        if os.path.isdir(root):
            self._load_from_disk()

    # ── 加载 / 持久化 ──

    def _load_from_disk(self):
        """从磁盘加载知识库"""
        for cat in self.CATEGORIES:
            cat_dir = os.path.join(self._root, cat)
            if not os.path.isdir(cat_dir):
                continue
            for fname in os.listdir(cat_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(cat_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    entry = KnowledgeEntry.from_dict(data)
                    entry.category = cat
                    self._entries[cat].append(entry)
                    self._memory_layers["kbase"].entries.append(entry)
                except (json.JSONDecodeError, KeyError):
                    continue

    def save_to_disk(self, root: str = ""):
        """持久化到磁盘"""
        save_root = root or self._root
        for cat in self.CATEGORIES:
            cat_dir = os.path.join(save_root, cat)
            os.makedirs(cat_dir, exist_ok=True)
            for i, entry in enumerate(self._entries[cat]):
                fname = f"{self._slugify(entry.title)}_{i}.json"
                fpath = os.path.join(cat_dir, fname)
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(entry.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def _slugify(text: str) -> str:
        """简单的文件名安全化"""
        safe = text.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return safe[:50] or "untitled"

    # ── 条目管理 ──

    def add_entry(self, entry: KnowledgeEntry) -> bool:
        """添加知识条目"""
        if entry.category not in self.CATEGORIES:
            return False

        self._entries[entry.category].append(entry)
        layer_name = {0: "session", 1: "daily", 2: "long", 3: "kbase"}.get(entry.level, "session")
        self._memory_layers[layer_name].entries.append(entry)

        # 检查是否需要晋升
        self._check_promotion(entry)
        return True

    def remove_entry(self, category: str, title: str) -> bool:
        """删除知识条目"""
        entries = self._entries.get(category, [])
        for i, e in enumerate(entries):
            if e.title == title:
                entries.pop(i)
                return True
        return False

    def get_entries(self, category: str) -> list[KnowledgeEntry]:
        """获取类目下所有条目"""
        return list(self._entries.get(category, []))

    # ── 错误模式归一化 ──

    # 需要归一化的动态模式（数字ID、hash、UUID、路径等）
    _NORMALIZE_PATTERNS = [
        (re.compile(r'\b\d{4,}\b'), '<ID>'),         # 4位以上数字
        (re.compile(r'\b[0-9a-f]{8,}\b'), '<HASH>'),  # hex hash
        (re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-'), '<UUID>'),  # UUID 前缀
        (re.compile(r'//\S+'), '<URL>'),               # URL
        (re.compile(r'"[^"]{20,}"'), '"<STR>"'),       # 长字符串
    ]

    @classmethod
    def normalize_error(cls, text: str) -> str:
        """归一化错误消息：将动态部分（ID/hash/路径）替换为占位符，
        使相同模式的错误能匹配到同一条知识。"""
        result = text
        for pattern, replacement in cls._NORMALIZE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    # ── 检索 ──

    def search(
        self,
        query: str,
        categories: list = None,
        tags: list = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        检索知识条目。

        Args:
            query: 搜索关键词
            categories: 限定类目（None=全部）
            tags: 限定标签
            limit: 最大返回数
            min_score: 最低相关度阈值（0=不过滤）

        Returns:
            按相关度排序的搜索结果列表
        """
        cats = categories or list(self.CATEGORIES)
        query_lower = query.lower()
        # 中文感知分词：空格分词 + 中文 bigram + 英文/数字段
        keywords = list(set(query_lower.split()))
        # 中文连续字符 → bigram
        for seg in re.findall(r'[\u4e00-\u9fff]{2,}', query_lower):
            keywords.append(seg)
            for i in range(len(seg) - 1):
                keywords.append(seg[i:i+2])
        # 英文/数字段
        for seg in re.findall(r'[a-z0-9_]{2,}', query_lower):
            keywords.append(seg)
        # 归一化查询（用于错误模式匹配）
        query_normalized = self.normalize_error(query_lower)
        results = []

        for cat in cats:
            for entry in self._entries.get(cat, []):
                score = 0.0
                matched = []

                title_lower = entry.title.lower()
                content_lower = entry.content.lower()
                entry_normalized = self.normalize_error(content_lower)

                # 标题匹配（权重高）
                for kw in keywords:
                    if kw in title_lower:
                        score += 3.0
                        matched.append(kw)

                # 内容匹配
                for kw in keywords:
                    if kw in content_lower:
                        score += 1.0
                        if kw not in matched:
                            matched.append(kw)

                # 短语子串匹配（原始查询作为整体短语命中）
                if len(query_lower) >= 4 and query_lower in content_lower:
                    score += 2.0
                    if "<phrase>" not in matched:
                        matched.append("<phrase>")

                # 归一化模式匹配（错误消息去噪后比对）
                if query_normalized != query_lower:
                    if query_normalized in entry_normalized:
                        score += 2.5
                        if "<normalized>" not in matched:
                            matched.append("<normalized>")

                # 标签匹配
                for tag in entry.tags:
                    tag_lower = tag.lower()
                    for kw in keywords:
                        if kw in tag_lower:
                            score += 2.0
                            if kw not in matched:
                                matched.append(kw)

                # 标签过滤
                if tags:
                    if not any(t in entry.tags for t in tags):
                        continue

                if score > min_score:
                    # 更新检索计数
                    entry.retrieval_count += 1
                    results.append(SearchResult(
                        entry=entry, score=score, matched_keywords=matched
                    ))

                    # 检查晋升
                    self._check_promotion(entry)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def hybrid_search(
        self,
        query: str,
        categories: list = None,
        tags: list = None,
        limit: int = 10,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
        expand_relations: bool = True,
    ) -> list[SearchResult]:
        """
        混合检索：关键词检索 + 向量检索加权融合。

        当 EmbeddingProvider 已注册且条目有 embedding 时，启用向量检索；
        否则退化为纯关键词检索。

        Args:
            query: 搜索查询
            keyword_weight: 关键词得分权重（默认 0.4）
            vector_weight: 向量相似度权重（默认 0.6）
            expand_relations: 是否通过关系链接扩展结果

        Returns:
            按综合得分排序的 SearchResult 列表
        """
        # 1. 关键词检索（全量打分）
        kw_results = self.search(query, categories=categories, tags=tags, limit=limit * 2, min_score=0.0)
        kw_scores: dict[str, float] = {r.entry.title: r.score for r in kw_results}

        # 2. 向量检索（如有 provider）
        vec_scores: dict[str, float] = {}
        if self._embedding_provider:
            query_vec = self._embedding_provider.embed(query)
            if query_vec:
                for cat in (categories or list(self.CATEGORIES)):
                    for entry in self._entries.get(cat, []):
                        if entry.embedding:
                            sim = self._cosine_sim(query_vec, entry.embedding)
                            vec_scores[entry.title] = sim

        # 3. 融合得分
        all_titles = set(kw_scores.keys()) | set(vec_scores.keys())
        entry_map: dict[str, KnowledgeEntry] = {}
        for cat in (categories or list(self.CATEGORIES)):
            for entry in self._entries.get(cat, []):
                entry_map[entry.title] = entry

        combined: list[SearchResult] = []
        max_kw = max(kw_scores.values()) if kw_scores else 1.0
        for title in all_titles:
            entry = entry_map.get(title)
            if not entry:
                continue
            kw_norm = kw_scores.get(title, 0.0) / max(max_kw, 1e-6)
            vec = vec_scores.get(title, 0.0)
            final_score = keyword_weight * kw_norm + vector_weight * vec
            if final_score > 0.01:
                entry.retrieval_count += 1
                combined.append(SearchResult(
                    entry=entry, score=final_score,
                    keyword_score=kw_scores.get(title, 0.0),
                    vector_score=vec,
                    matched_keywords=kw_results[0].matched_keywords if kw_results else [],
                ))
                self._check_promotion(entry)

        combined.sort(key=lambda r: r.score, reverse=True)
        results = combined[:limit]

        # 4. 关系链接扩展（一跳）
        if expand_relations:
            seen_titles = {r.entry.title for r in results}
            extras = []
            for r in results[:5]:  # 只对 top-5 扩展
                for rel_title in r.entry.related_entries:
                    if rel_title not in seen_titles:
                        rel_entry = self._find_entry_by_title(rel_title)
                        if rel_entry:
                            extras.append(SearchResult(
                                entry=rel_entry, score=r.score * 0.8,
                                is_related=True,
                            ))
                            seen_titles.add(rel_title)
            results.extend(extras[:limit - len(results)])

        return results

    def _find_entry_by_title(self, title: str) -> "KnowledgeEntry | None":
        """按 title 查找条目（跨类目）"""
        for cat in self.CATEGORIES:
            for entry in self._entries.get(cat, []):
                if entry.title == title:
                    return entry
        return None

    @staticmethod
    def _cosine_sim(a: list, b: list) -> float:
        """计算两个向量的余弦相似度"""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Embedding Provider ──

    _embedding_provider = None  # 默认为 None

    def register_embedding_provider(self, provider):
        """
        注册向量嵌入 Provider。

        provider 需实现 embed(text: str) -> list[float] 方法。
        注册后可使用 hybrid_search()。
        """
        self._embedding_provider = provider

    def embed_all(self):
        """为所有未嵌入的条目生成向量（需先 register_embedding_provider）"""
        if not self._embedding_provider:
            return 0
        count = 0
        for cat in self.CATEGORIES:
            for entry in self._entries.get(cat, []):
                if not entry.embedding:
                    text = f"{entry.title} {entry.content}"
                    vec = self._embedding_provider.embed(text)
                    if vec:
                        entry.embedding = vec
                        count += 1
        return count

    def record_hit(self, entry: KnowledgeEntry):
        """记录条目命中（被实际使用）"""
        entry.hit_count += 1
        self._check_promotion(entry)

    # ── 三层记忆晋升 ──

    def promote_session_to_daily(self, session_id: str = ""):
        """session 记忆晋升到 daily"""
        layer = self._memory_layers["session"]
        promoted = []
        remaining = []

        for entry in layer.entries:
            if entry.level == 0:
                entry.level = 1
                entry.promoted_at = time.time()
                promoted.append(entry)
                self._promotion_log.append(PromotionEvent(
                    entry_title=entry.title, from_level=0, to_level=1,
                    reason=f"session({session_id}) -> daily",
                ))
            else:
                remaining.append(entry)

        layer.entries = remaining
        self._memory_layers["daily"].entries.extend(promoted)

    def promote_daily_to_long(self):
        """daily 记忆晋升到 long（MEMORY.md）"""
        layer = self._memory_layers["daily"]
        promoted = []
        remaining = []

        for entry in layer.entries:
            if entry.level == 1 and (
                entry.retrieval_count >= self.PROMOTION_RETRIEVAL_THRESHOLD
                or entry.hit_count >= self.PROMOTION_HIT_THRESHOLD
            ):
                entry.level = 2
                entry.promoted_at = time.time()
                promoted.append(entry)
                self._promotion_log.append(PromotionEvent(
                    entry_title=entry.title, from_level=1, to_level=2,
                    reason=f"retrieval={entry.retrieval_count}, hit={entry.hit_count}",
                ))
            else:
                remaining.append(entry)

        layer.entries = remaining
        long_layer = self._memory_layers["long"]
        long_layer.entries.extend(promoted)

        # 超量降级
        self._enforce_memory_limit(long_layer)

    def promote_long_to_kbase(self):
        """long 记忆晋升到 KBase"""
        layer = self._memory_layers["long"]
        promoted = []
        remaining = []

        for entry in layer.entries:
            if entry.level == 2 and (
                entry.retrieval_count >= self.PROMOTION_RETRIEVAL_THRESHOLD * 2
                or entry.hit_count >= self.PROMOTION_HIT_THRESHOLD * 2
            ):
                entry.level = 3
                entry.promoted_at = time.time()
                promoted.append(entry)
                self._entries[entry.category].append(entry)
                self._promotion_log.append(PromotionEvent(
                    entry_title=entry.title, from_level=2, to_level=3,
                    reason=f"retrieval={entry.retrieval_count}, hit={entry.hit_count}",
                ))
            else:
                remaining.append(entry)

        layer.entries = remaining
        self._memory_layers["kbase"].entries.extend(promoted)

    def _check_promotion(self, entry: KnowledgeEntry):
        """检查单条目是否满足晋升条件"""
        if entry.level < 3 and (
            entry.retrieval_count >= self.PROMOTION_RETRIEVAL_THRESHOLD
            or entry.hit_count >= self.PROMOTION_HIT_THRESHOLD
        ):
            old_level = entry.level
            entry.level = min(entry.level + 1, 3)
            entry.promoted_at = time.time()
            self._promotion_log.append(PromotionEvent(
                entry_title=entry.title, from_level=old_level, to_level=entry.level,
                reason=f"auto: retrieval={entry.retrieval_count}, hit={entry.hit_count}",
            ))

    def _enforce_memory_limit(self, layer: MemoryLayer):
        """超量降级：按检索计数保留高价值条目"""
        if not layer.is_full:
            return

        # 按检索计数排序，保留高价值的
        layer.entries.sort(key=lambda e: e.retrieval_count + e.hit_count, reverse=True)

        kept = []
        current_size = 0
        for entry in layer.entries:
            entry_size = len(entry.content.encode("utf-8"))
            if current_size + entry_size <= layer.max_size_bytes:
                kept.append(entry)
                current_size += entry_size
            # 超量的直接丢弃（降级）

        layer.entries = kept

    # ── 统计 ──

    def get_stats(self) -> dict:
        """知识库统计"""
        return {
            "total_entries": sum(len(v) for v in self._entries.values()),
            "by_category": {cat: len(entries) for cat, entries in self._entries.items()},
            "memory_layers": {
                name: {
                    "entries": len(layer.entries),
                    "size_bytes": layer.current_size_bytes,
                    "max_bytes": layer.max_size_bytes,
                    "usage_pct": round(layer.current_size_bytes / max(layer.max_size_bytes, 1) * 100, 1),
                }
                for name, layer in self._memory_layers.items()
            },
            "promotion_events": len(self._promotion_log),
        }

    def get_promotion_log(self) -> list[dict]:
        """获取晋升事件日志"""
        return [
            {
                "title": e.entry_title,
                "from": e.from_level,
                "to": e.to_level,
                "reason": e.reason,
                "timestamp": e.timestamp,
            }
            for e in self._promotion_log
        ]

    @classmethod
    def from_config(cls, config_path: str) -> "KnowledgeBase":
        """从配置路径加载"""
        return cls(root=config_path)


# ── 知识完整性校验器 ──

@dataclass
class CompletenessGap:
    """知识缺口"""
    topic: str
    severity: str          # "high" / "medium" / "low"
    reason: str            # 为什么认为有缺口
    suggested_action: str  # 建议操作


@dataclass
class CompletenessReport:
    """知识完整性校验报告"""
    total_topics: int = 0
    covered_topics: int = 0
    coverage_pct: float = 0.0
    gaps: list = field(default_factory=list)  # list[CompletenessGap]
    checked_categories: list = field(default_factory=list)
    checked_entries: int = 0

    def to_dict(self) -> dict:
        return {
            "total_topics": self.total_topics,
            "covered_topics": self.covered_topics,
            "coverage_pct": round(self.coverage_pct, 1),
            "gaps": [
                {
                    "topic": g.topic,
                    "severity": g.severity,
                    "reason": g.reason,
                    "suggested_action": g.suggested_action,
                }
                for g in self.gaps
            ],
            "checked_categories": self.checked_categories,
            "checked_entries": self.checked_entries,
        }

    @property
    def is_complete(self) -> bool:
        """覆盖率 >= 80% 且无 high 级缺口视为完整"""
        return self.coverage_pct >= 80.0 and not any(
            g.severity == "high" for g in self.gaps
        )


class KnowledgeCompletenessValidator:
    """
    知识完整性校验器。

    在 Agent 生成输出前，对知识库进行前置校验：
    1. 给定一组必须覆盖的主题关键词，检查知识库是否已有对应条目
    2. 按类目检查知识分布是否均衡
    3. 输出缺口报告，供 Agent 决定是否需要标注“推测”或拒绝回答

    使用方式:
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate(
            required_topics=["模型匹配", "规则匹配", "审核流程"],
            categories=["features", "contracts"],
        )
        if not report.is_complete:
            # Agent 应在输出中标注“知识不完整”
            ...
    """

    # 默认最小覆盖率阈值
    DEFAULT_COVERAGE_THRESHOLD = 80.0
    # 默认最小检索得分（search 的 score 阈值）
    DEFAULT_MIN_SCORE = 2.0

    def __init__(
        self,
        kb: KnowledgeBase,
        coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
        min_score: float = DEFAULT_MIN_SCORE,
    ):
        self._kb = kb
        self._threshold = coverage_threshold
        self._min_score = min_score

    def validate(
        self,
        required_topics: list[str] = None,
        categories: list[str] = None,
        min_entries_per_category: int = 1,
    ) -> CompletenessReport:
        """
        执行知识完整性校验。

        Args:
            required_topics: 必须覆盖的主题关键词列表
            categories: 需要检查的类目（None=全部四类目）
            min_entries_per_category: 每个类目最少条目数

        Returns:
            CompletenessReport
        """
        report = CompletenessReport()
        topics = required_topics or []
        cats = categories or list(KnowledgeBase.CATEGORIES)
        report.checked_categories = cats

        # 统计已检查条目数
        report.checked_entries = sum(
            len(self._kb.get_entries(cat)) for cat in cats
        )

        # ── 1. 主题覆盖率检查 ──
        covered = 0
        for topic in topics:
            results = self._kb.search(topic, categories=cats, limit=3)
            # 有结果且得分达到阈值 → 视为覆盖
            hit = any(r.score >= self._min_score for r in results)
            if hit:
                covered += 1
            else:
                # 判断缺口严重度
                severity = self._assess_severity(topic, results)
                report.gaps.append(CompletenessGap(
                    topic=topic,
                    severity=severity,
                    reason=self._explain_gap(topic, results),
                    suggested_action=self._suggest_action(topic, severity),
                ))

        report.total_topics = len(topics)
        report.covered_topics = covered
        report.coverage_pct = (
            (covered / len(topics) * 100) if topics else 100.0
        )

        # ── 2. 类目均衡性检查 ──
        for cat in cats:
            entries = self._kb.get_entries(cat)
            if len(entries) < min_entries_per_category:
                report.gaps.append(CompletenessGap(
                    topic=f"[类目:{cat}]",
                    severity="medium",
                    reason=f"类目 '{cat}' 仅有 {len(entries)} 条知识，低于阈值 {min_entries_per_category}",
                    suggested_action=f"为 '{cat}' 类目补充知识条目",
                ))

        return report

    def validate_output(
        self,
        output_text: str,
        required_topics: list[str] = None,
    ) -> CompletenessReport:
        """
        对 Agent 生成的输出文本做知识完整性前置校验。

        检测输出中是否包含“推测”“不确定”等标记词，
        同时检查 required_topics 是否都能在知识库中找到支撑。

        Args:
            output_text: Agent 输出的文本
            required_topics: 应该被知识库支撑的主题

        Returns:
            CompletenessReport（额外附加 speculative 标记缺口）
        """
        # 先做基础校验
        report = self.validate(required_topics=required_topics)

        # 检测推测性表述
        speculative_markers = [
            "推测", "猜测", "可能是", "未找到", "没有找到",
            "inferred", "speculative", "not found", "推测实现",
        ]
        for marker in speculative_markers:
            if marker in output_text:
                report.gaps.append(CompletenessGap(
                    topic=f"推测性表述: '{marker}'",
                    severity="high",
                    reason=f"输出中包含推测性标记 '{marker}'，说明知识库未提供确定性信息",
                    suggested_action="先检索知识库确认是否有对应条目，再决定是否标注推测",
                ))
                break  # 只报一次

        return report

    # ── 内部方法 ──

    def _assess_severity(self, topic: str, results: list) -> str:
        """评估缺口严重度"""
        if not results:
            return "high"  # 完全无结果
        best_score = max(r.score for r in results)
        if best_score < 1.0:
            return "high"   # 得分极低，几乎无关
        if best_score < self._min_score:
            return "medium"  # 有弱相关
        return "low"

    def _explain_gap(self, topic: str, results: list) -> str:
        """生成缺口原因说明"""
        if not results:
            return f"知识库中无任何与 '{topic}' 相关的条目"
        best = max(results, key=lambda r: r.score)
        return (
            f"最相关条目 '{best.entry.title}' 得分 {best.score:.1f} "
            f"(阈值 {self._min_score})，匹配关键词: {best.matched_keywords}"
        )

    def _suggest_action(self, topic: str, severity: str) -> str:
        """生成建议操作"""
        if severity == "high":
            return f"必须为 '{topic}' 添加知识条目后再输出结论"
        if severity == "medium":
            return f"建议补充 '{topic}' 相关知识，或在输出中标注为推测"
        return f"'{topic}' 有弱匹配，建议确认知识是否充分"


# ── 上下文窗口管理器 ──

class ContextWindowManager:
    """
    LLM 上下文窗口管理器。

    控制注入 LLM 的知识上下文总量，避免超窗口。
    按相关度优先级裁剪内容，保留高价值条目。

    使用方式:
        mgr = ContextWindowManager(max_tokens=4000)
        context = mgr.build_context(search_results)
        # context 是截断后的文本，总 token 不超过 max_tokens
    """

    # 粗略估算: 1 个中文字符 ≈ 1.5 token， 1 个英文单词 ≈ 1 token
    CHARS_PER_TOKEN_ZH = 1.5
    CHARS_PER_TOKEN_EN = 4.0

    def __init__(self, max_tokens: int = 4000, reserve_for_output: int = 500):
        self._max_tokens = max_tokens
        self._reserve = reserve_for_output

    @property
    def available_tokens(self) -> int:
        return self._max_tokens - self._reserve

    def estimate_tokens(self, text: str) -> int:
        """粗略估算文本的 token 数"""
        zh_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        en_words = len(re.findall(r'[a-zA-Z]+', text))
        return int(zh_chars / self.CHARS_PER_TOKEN_ZH + en_words)

    def build_context(self, results: list) -> str:
        """
        将 SearchResult 列表构建为 LLM 可消费的上下文文本。

        按得分从高到低依次加入条目，超出 token 预算时截断。

        Args:
            results: SearchResult 列表（已按得分排序）

        Returns:
            格式化的上下文文本
        """
        budget = self.available_tokens
        parts = []
        included = 0

        for r in results:
            entry = r.entry if hasattr(r, 'entry') else r
            text = f"[{entry.title}] {entry.content}"
            entry_tokens = self.estimate_tokens(text)
            if entry_tokens > budget:
                # 截断当前条目
                remaining_chars = int(budget * self.CHARS_PER_TOKEN_ZH)
                truncated = text[:remaining_chars] + "..."
                parts.append(truncated)
                included += 1
                break
            parts.append(text)
            budget -= entry_tokens
            included += 1

        header = f"[知识上下文: {included}/{len(results)} 条，约 {self.estimate_tokens(' '.join(parts))} tokens]"
        return header + "\n" + "\n---\n".join(parts)

    def should_suppress(self, text: str) -> bool:
        """检查文本是否超出可用预算"""
        return self.estimate_tokens(text) > self.available_tokens
