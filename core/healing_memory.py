"""
healing_memory.py — 自愈经验记忆与晋升引擎 (维度10)

将自愈从"无状态重试"升级为"经验驱动的自适应修复"：
- Session 级记忆：本次执行内成功的修复经验立即复用
- 持久化晋升：Session 结束时将高置信经验写入 error-pattern-map.json
- 失败降级：同类错误连续 N 次自愈失败后自动降级为"需人工介入"

使用方式：
    from core.healing_memory import HealingMemory
    mem = HealingMemory()

    # 自愈成功后记录
    mem.record_success(
        error_pattern="ant-select.*timeout",
        fix_strategy="mouse.click on ant-select-arrow",
        context={"selector": ".ant-select-arrow"},
    )

    # 下次遇到类似错误时优先查历史经验
    hit = mem.lookup("ant-select dropdown timeout")
    if hit:
        # 直接应用历史经验
        ...

    # Session 结束时晋升
    mem.promote_to_knowledge(base_dir="/path/to/web-automation")
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime, timezone


@dataclass
class HealingExperience:
    """一条自愈经验"""
    error_pattern: str          # 正则或关键词（匹配错误消息）
    fix_strategy: str           # 修复策略名称或描述
    fix_code: str = ""          # 修复代码片段（可选）
    success_count: int = 1      # 成功次数
    fail_count: int = 0         # 失败次数
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: dict = field(default_factory=dict)
    source: str = "session"     # session | promoted | loaded
    scene: str = ""             # 场景标签（如 f88, op, product）

    @property
    def confidence(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict:
        return {
            "error_pattern": self.error_pattern,
            "fix_strategy": self.fix_strategy,
            "fix_code": self.fix_code,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_seen": self.last_seen,
            "context": self.context,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "scene": self.scene,
        }


class HealingMemory:
    """
    自愈经验记忆引擎：
    - 记录每次自愈的 (error_pattern, fix_strategy, success/fail)
    - 下次同类错误优先使用历史经验
    - Session 结束时将高置信度经验晋升到 error-pattern-map.json
    - 连续失败降级：同类错误连续 N 次失败后标记为"需人工介入"
    """

    # 晋升阈值：成功率 >= 此值 且 成功次数 >= PROMOTE_MIN_COUNT
    PROMOTE_CONFIDENCE_THRESHOLD = 0.7
    PROMOTE_MIN_COUNT = 2
    # 连续失败降级阈值
    CONSECUTIVE_FAIL_LIMIT = 3

    def __init__(self):
        self._experiences: List[HealingExperience] = []
        self._consecutive_fails: Dict[str, int] = {}  # error_pattern -> count

    # ── 记录 ──

    def record_success(
        self,
        error_pattern: str,
        fix_strategy: str,
        fix_code: str = "",
        context: dict = None,
    ):
        """记录一次自愈成功"""
        exp = self._find_or_create(error_pattern, fix_strategy)
        exp.success_count += 1
        exp.last_seen = datetime.now(timezone.utc).isoformat()
        if fix_code:
            exp.fix_code = fix_code
        if context:
            exp.context.update(context)
        # 重置连续失败计数
        self._consecutive_fails.pop(self._pattern_key(error_pattern), None)

    def record_failure(
        self,
        error_pattern: str,
        fix_strategy: str,
    ):
        """记录一次自愈失败"""
        exp = self._find_or_create(error_pattern, fix_strategy)
        exp.fail_count += 1
        exp.last_seen = datetime.now(timezone.utc).isoformat()
        # 更新连续失败计数
        key = self._pattern_key(error_pattern)
        self._consecutive_fails[key] = self._consecutive_fails.get(key, 0) + 1

    # ── 查询 ──

    def lookup(self, error_msg: str, top_k: int = 3) -> List[HealingExperience]:
        """
        根据错误消息查找历史自愈经验，按置信度排序。
        支持模糊语义匹配（编辑距离 + 关键词提取）。

        Args:
            error_msg: 当前错误消息
            top_k: 返回最多 k 条匹配

        Returns:
            按 confidence 降序排列的 HealingExperience 列表
        """
        error_lower = error_msg.lower()
        error_keywords = self._extract_keywords(error_msg)
        scored = []

        for exp in self._experiences:
            # 精确匹配（正则 + 关键词）
            exact_score = self._match_score(exp.error_pattern, error_lower)
            if exact_score > 0:
                scored.append((exact_score * exp.confidence, exp, "exact"))
                continue

            # 模糊语义匹配
            fuzzy_score = self._fuzzy_match(exp.error_pattern, error_msg, error_keywords)
            if fuzzy_score > 0.4:  # 阈值：40% 相似度
                scored.append((fuzzy_score * exp.confidence, exp, "fuzzy"))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp, _ in scored[:top_k]]

    def is_blacklisted(self, error_pattern: str) -> bool:
        """
        检查某类错误是否已被标记为"需人工介入"（连续失败超限）。
        """
        key = self._pattern_key(error_pattern)
        return self._consecutive_fails.get(key, 0) >= self.CONSECUTIVE_FAIL_LIMIT

    def get_blacklisted_patterns(self) -> List[str]:
        """获取所有被标记为需人工介入的错误模式"""
        return [
            pat for pat, count in self._consecutive_fails.items()
            if count >= self.CONSECUTIVE_FAIL_LIMIT
        ]

    # ── 晋升 ──

    def get_promotable(self) -> List[HealingExperience]:
        """
        获取符合晋升条件的经验列表。
        条件：置信度 >= 阈值 且 成功次数 >= 最小值 且 来源为 session。
        """
        return [
            exp for exp in self._experiences
            if (exp.source == "session"
                and exp.confidence >= self.PROMOTE_CONFIDENCE_THRESHOLD
                and exp.success_count >= self.PROMOTE_MIN_COUNT)
        ]

    def promote_to_knowledge(self, base_dir: str) -> dict:
        """
        将高置信度经验晋升到 error-pattern-map.json。
        支持跨场景知识共享（通过 scene 标签）。

        Args:
            base_dir: web-automation 根目录

        Returns:
            晋升摘要 {"promoted": int, "skipped": int, "entries": [...]}
        """
        promotable = self.get_promotable()
        if not promotable:
            return {"promoted": 0, "skipped": len(self._experiences), "entries": []}

        map_path = os.path.join(base_dir, "references", "error-pattern-map.json")
        existing_map = self._load_pattern_map(map_path)
        mappings = existing_map.get("mappings", [])

        promoted_entries = []
        for exp in promotable:
            # 检查是否已存在类似 pattern + 场景
            existing = [
                m for m in mappings
                if self._patterns_similar(m.get("pattern", ""), exp.error_pattern)
                and m.get("scene", "") == exp.scene
            ]
            if existing:
                continue

            new_entry = {
                "pattern": exp.error_pattern,
                "standard_fix": exp.fix_strategy,
                "code": exp.fix_code,
                "keywords": self._extract_keywords(exp.error_pattern),
                "confidence": round(exp.confidence, 3),
                "success_count": exp.success_count,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "scene": exp.scene or "global",  # 场景标签（默认 global）
            }
            mappings.append(new_entry)
            exp.source = "promoted"
            promoted_entries.append(exp.error_pattern)

        # 写回
        existing_map["mappings"] = mappings
        try:
            os.makedirs(os.path.dirname(map_path), exist_ok=True)
            with open(map_path, "w", encoding="utf-8") as f:
                json.dump(existing_map, f, ensure_ascii=False, indent=2)
        except (OSError, IOError):
            pass

        return {
            "promoted": len(promoted_entries),
            "skipped": len(self._experiences) - len(promotable),
            "entries": promoted_entries,
        }

    def load_from_knowledge(self, base_dir: str):
        """
        从 error-pattern-map.json 加载历史经验（启动时调用）。
        """
        map_path = os.path.join(base_dir, "references", "error-pattern-map.json")
        data = self._load_pattern_map(map_path)
        for entry in data.get("mappings", []):
            pattern = entry.get("pattern", "")
            if not pattern:
                continue
            exp = HealingExperience(
                error_pattern=pattern,
                fix_strategy=entry.get("standard_fix", ""),
                fix_code=entry.get("code", ""),
                success_count=entry.get("success_count", 1),
                source="loaded",
                scene=entry.get("scene", ""),  # 场景标签
            )
            self._experiences.append(exp)

    # ── 跨场景知识共享 ──

    def lookup_global(self, error_msg: str, current_scene: str = "", top_k: int = 3) -> List[HealingExperience]:
        """
        跨场景知识共享查询：先查当前场景，再查全局经验。

        Args:
            error_msg: 当前错误消息
            current_scene: 当前场景标签（如 f88, op）
            top_k: 返回最多 k 条匹配

        Returns:
            按置信度排序的 HealingExperience 列表
        """
        # 1. 先查当前场景
        scene_matches = []
        for exp in self._experiences:
            if exp.scene and exp.scene == current_scene:
                exact_score = self._match_score(exp.error_pattern, error_msg.lower())
                if exact_score > 0:
                    scene_matches.append((exact_score * exp.confidence, exp))
                    continue
                fuzzy_score = self._fuzzy_match(
                    exp.error_pattern,
                    error_msg,
                    self._extract_keywords(error_msg)
                )
                if fuzzy_score > 0.4:
                    scene_matches.append((fuzzy_score * exp.confidence, exp))

        # 2. 再查全局经验（scene="global" 或 scene=""）
        global_matches = []
        for exp in self._experiences:
            if not exp.scene or exp.scene == "global":
                exact_score = self._match_score(exp.error_pattern, error_msg.lower())
                if exact_score > 0:
                    global_matches.append((exact_score * exp.confidence * 0.9, exp))
                    continue
                fuzzy_score = self._fuzzy_match(
                    exp.error_pattern,
                    error_msg,
                    self._extract_keywords(error_msg)
                )
                if fuzzy_score > 0.4:
                    global_matches.append((fuzzy_score * exp.confidence * 0.9, exp))

        # 3. 合并并排序（场景经验优先）
        scene_matches.sort(key=lambda x: x[0], reverse=True)
        global_matches.sort(key=lambda x: x[0], reverse=True)
        combined = scene_matches[:top_k] + global_matches[:top_k]
        combined.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in combined[:top_k]]

    # ── 统计 ──

    def get_stats(self) -> dict:
        total = len(self._experiences)
        session = sum(1 for e in self._experiences if e.source == "session")
        promoted = sum(1 for e in self._experiences if e.source == "promoted")
        loaded = sum(1 for e in self._experiences if e.source == "loaded")
        total_success = sum(e.success_count for e in self._experiences)
        total_fail = sum(e.fail_count for e in self._experiences)
        return {
            "total_experiences": total,
            "session_count": session,
            "promoted_count": promoted,
            "loaded_count": loaded,
            "total_success": total_success,
            "total_fail": total_fail,
            "blacklisted_patterns": self.get_blacklisted_patterns(),
        }

    def get_all_experiences(self) -> List[dict]:
        return [exp.to_dict() for exp in self._experiences]

    # ── 内部方法 ──

    def _find_or_create(self, error_pattern: str, fix_strategy: str) -> HealingExperience:
        """查找已有经验或创建新的"""
        key = self._pattern_key(error_pattern)
        for exp in self._experiences:
            if self._pattern_key(exp.error_pattern) == key and exp.fix_strategy == fix_strategy:
                return exp
        exp = HealingExperience(error_pattern=error_pattern, fix_strategy=fix_strategy)
        self._experiences.append(exp)
        return exp

    @staticmethod
    def _pattern_key(pattern: str) -> str:
        """标准化 pattern 用于去重比较"""
        return re.sub(r'\s+', '', pattern.lower().strip())

    # ── 模糊匹配辅助方法 ──

    @staticmethod
    def _fuzzy_match(pattern: str, error_msg: str, error_keywords: List[str]) -> float:
        """
        计算 error_msg 与 pattern 的模糊语义相似度 (0.0~1.0)
        综合编辑距离 + 关键词相似度 + 核心词匹配
        """
        pattern_lower = pattern.lower()
        error_lower = error_msg.lower()

        # 1. 编辑距离相似度（归一化）
        edit_sim = HealingMemory._edit_distance_similarity(pattern_lower, error_lower)

        # 2. 关键词相似度
        pattern_keywords = HealingMemory._extract_keywords(pattern)
        keyword_sim = HealingMemory._keyword_overlap(pattern_keywords, error_keywords)

        # 3. 核心词匹配（技术关键词）
        core_words = ["timeout", "element", "selector", "click", "wait", "navigate",
                     "cookie", "session", "network", "api", "button", "input", "modal"]
        pattern_core = [w for w in core_words if w in pattern_lower]
        error_core = [w for w in core_words if w in error_lower]
        core_sim = len(set(pattern_core) & set(error_core)) / max(len(set(pattern_core) | set(error_core)), 1)

        # 加权综合（关键词权重最高）
        final_score = 0.3 * edit_sim + 0.4 * keyword_sim + 0.3 * core_sim
        return final_score

    @staticmethod
    def _edit_distance_similarity(s1: str, s2: str) -> float:
        """计算两字符串的编辑距离相似度 (0.0~1.0)"""
        len1, len2 = len(s1), len(s2)
        if len1 == 0 and len2 == 0:
            return 1.0
        max_len = max(len1, len2)
        if max_len > 100:  # 超长字符串截断
            s1, s2 = s1[:100], s2[:100]
            max_len = 100

        # 动态规划计算编辑距离
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i-1] == s2[j-1] else 1
                dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)

        distance = dp[len1][len2]
        return 1.0 - (distance / max_len)

    @staticmethod
    def _keyword_overlap(keywords1: List[str], keywords2: List[str]) -> float:
        """计算两组关键词的 Jaccard 相似度"""
        set1 = set(w.lower() for w in keywords1)
        set2 = set(w.lower() for w in keywords2)
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _match_score(pattern: str, error_lower: str) -> float:
        """计算 error_pattern 与 error_msg 的匹配得分（0.0~1.0）"""
        # 尝试正则匹配
        try:
            if re.search(pattern, error_lower, re.IGNORECASE):
                return 1.0
        except re.error:
            pass

        # 关键词匹配（拆分 pattern 中的词）
        keywords = [w for w in re.split(r'[\s\-\.\_\(\)\[\]\{\}]+', pattern.lower()) if len(w) > 3]
        if not keywords:
            return 0.0
        hits = sum(1 for kw in keywords if kw in error_lower)
        return hits / len(keywords) if keywords else 0.0

    @staticmethod
    def _patterns_similar(p1: str, p2: str) -> bool:
        """判断两个 pattern 是否相似（避免重复晋升）"""
        if not p1 or not p2:
            return False
        k1 = HealingMemory._pattern_key(p1)
        k2 = HealingMemory._pattern_key(p2)
        if k1 == k2:
            return True
        # 子串关系
        return k1 in k2 or k2 in k1

    @staticmethod
    def _extract_keywords(pattern: str) -> List[str]:
        """从 pattern 中提取关键词（用于 KnowledgeResolver 搜索）"""
        words = re.split(r'[\s\-\.\_\(\)\[\]\{\}\*\+\?\|]+', pattern)
        return [w for w in words if len(w) > 3 and not w.isdigit()][:5]

    @staticmethod
    def _load_pattern_map(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return {"mappings": []}
