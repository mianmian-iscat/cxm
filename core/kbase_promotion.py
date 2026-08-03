"""
kbase_promotion.py — KBase 三层记忆量化晋升引擎

来源：服饰质量全托管数字人架构方案 §3.1 / §5.2
晋升路径：session(JSONL) → daily(memory/YYYY-MM-DD.md) → long(MEMORY.md) → KBase

晋升规则（一期硬编码，预留二期 yaml 配置化）：
    - search_hits_threshold: 3      被检索次数 ≥3
    - requirement_hits_threshold: 2  命中需求数 ≥2
    - promotion_window_days: 7       滑动窗口 7 天

自滚机制：
    高频复用 BadCase 提升为 patterns/
    高频规则提升为 contracts/

使用方式：
    from core.kbase_promotion import KBasePromotionEngine

    engine = KBasePromotionEngine()
    engine.record_search_hit(entry_id="knownIssues#selector-drift", context={"requirement_id": "REQ-123"})
    candidates = engine.get_promotion_candidates()
    results = engine.execute_promotion()
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict

# ── 晋升阈值（一期硬编码，ADR-D2；二期抽取到 kbase.yaml 支持热更新）──

PROMOTION_RULES = {
    "search_hits_threshold": 3,       # 被检索次数 ≥3
    "requirement_hits_threshold": 2,  # 命中需求数 ≥2
    "promotion_window_days": 7,       # 滑动窗口 7 天
}

# 记忆层级
LEVELS = ["session", "daily", "long", "kbase"]

# KBase 四类目
KBASE_CATEGORIES = ["features", "infra", "patterns", "contracts"]

# 晋升目标映射：条目类型 → KBase 类目
_TYPE_TO_CATEGORY = {
    "badcase": "patterns",
    "known_issue": "patterns",
    "selector_fix": "patterns",
    "business_rule": "features",
    "api_contract": "infra",
    "assertion_rule": "contracts",
    "healing_pattern": "patterns",
}


@dataclass
class HitRecord:
    """单次检索命中记录"""
    timestamp: float
    requirement_id: str = ""
    session_id: str = ""
    query: str = ""


@dataclass
class PromotionCandidate:
    """晋升候选条目"""
    entry_id: str
    current_level: str = "session"
    target_level: str = "daily"
    target_category: str = "patterns"
    search_hits: int = 0
    requirement_hits: int = 0
    window_days: int = 7
    content: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "current_level": self.current_level,
            "target_level": self.target_level,
            "target_category": self.target_category,
            "search_hits": self.search_hits,
            "requirement_hits": self.requirement_hits,
            "reason": self.reason,
        }


class KBasePromotionEngine:
    """
    KBase 三层记忆量化晋升引擎。

    跟踪每条知识/记忆的检索命中情况，
    当满足晋升阈值时自动推荐或执行晋升。
    """

    def __init__(
        self,
        tracking_path: str = "",
        rules: Optional[dict] = None,
    ):
        """
        Args:
            tracking_path: 命中跟踪数据持久化路径（JSON）
            rules: 自定义晋升阈值（None 时使用硬编码默认值）
        """
        self._rules = {**PROMOTION_RULES, **(rules or {})}
        self._tracking_path = tracking_path
        self._hits: Dict[str, List[dict]] = {}       # entry_id → [HitRecord dict]
        self._levels: Dict[str, str] = {}            # entry_id → current level
        self._promoted: Dict[str, str] = {}          # entry_id → promoted_at
        self._stats = {"searches": 0, "promotions": 0, "rejections": 0}

        if tracking_path and os.path.isfile(tracking_path):
            self._load()

    # ── 命中记录 ──

    def record_search_hit(
        self,
        entry_id: str,
        requirement_id: str = "",
        session_id: str = "",
        query: str = "",
        current_level: str = "session",
    ):
        """
        记录一次检索命中。

        Args:
            entry_id: 知识条目唯一标识
            requirement_id: 关联需求 ID（用于 requirement_hits 统计）
            session_id: 会话 ID
            query: 检索 query（用于分析）
            current_level: 条目当前所在层级
        """
        self._stats["searches"] += 1

        if entry_id not in self._hits:
            self._hits[entry_id] = []
        self._hits[entry_id].append({
            "timestamp": time.time(),
            "requirement_id": requirement_id,
            "session_id": session_id,
            "query": query[:200],
        })

        if entry_id not in self._levels:
            self._levels[entry_id] = current_level

        self._save()

    def record_content(self, entry_id: str, content: str, level: str = "session"):
        """登记条目内容与层级（用于晋升时搬运）"""
        self._levels[entry_id] = level
        # 内容存储在跟踪数据的 meta 中
        if entry_id not in self._hits:
            self._hits[entry_id] = []
        # 用特殊标记存储内容
        meta_key = f"__content__{entry_id}"
        self._hits.setdefault("__meta__", {})[entry_id] = content[:2000]
        self._save()

    # ── 晋升评估 ──

    def evaluate_entry(self, entry_id: str) -> Optional[PromotionCandidate]:
        """
        评估单条是否满足晋升条件。

        晋升条件（OR 逻辑）：
        - 滑动窗口内被检索次数 ≥ search_hits_threshold
        - 滑动窗口内命中需求数 ≥ requirement_hits_threshold
        """
        hits = self._hits.get(entry_id, [])
        if not hits:
            return None

        window_start = time.time() - self._rules["promotion_window_days"] * 86400
        window_hits = [h for h in hits if h.get("timestamp", 0) >= window_start]

        search_hits = len(window_hits)
        requirement_ids = {
            h["requirement_id"] for h in window_hits
            if h.get("requirement_id")
        }
        requirement_hits = len(requirement_ids)

        threshold_s = self._rules["search_hits_threshold"]
        threshold_r = self._rules["requirement_hits_threshold"]

        # OR 逻辑：任一条件满足即可晋升
        if search_hits >= threshold_s or requirement_hits >= threshold_r:
            current_level = self._levels.get(entry_id, "session")
            target_level = self._next_level(current_level)
            reasons = []
            if search_hits >= threshold_s:
                reasons.append(f"检索命中 {search_hits}≥{threshold_s}")
            if requirement_hits >= threshold_r:
                reasons.append(f"命中需求 {requirement_hits}≥{threshold_r}")

            content = self._hits.get("__meta__", {}).get(entry_id, "")
            return PromotionCandidate(
                entry_id=entry_id,
                current_level=current_level,
                target_level=target_level,
                target_category=self._infer_category(entry_id, content),
                search_hits=search_hits,
                requirement_hits=requirement_hits,
                window_days=self._rules["promotion_window_days"],
                content=content,
                reason=" + ".join(reasons),
            )

        return None

    def get_promotion_candidates(self) -> List[PromotionCandidate]:
        """获取所有满足晋升条件的候选条目"""
        candidates = []
        for entry_id in list(self._hits.keys()):
            if entry_id == "__meta__" or entry_id in self._promoted:
                continue
            candidate = self.evaluate_entry(entry_id)
            if candidate:
                candidates.append(candidate)
        return candidates

    def execute_promotion(self, dry_run: bool = False) -> dict:
        """
        执行晋升：将所有候选条目晋升到下一层。

        Args:
            dry_run: 仅评估不执行

        Returns:
            {promoted: [...], rejected: [...], stats: {...}}
        """
        candidates = self.get_promotion_candidates()
        promoted = []
        rejected = []

        for c in candidates:
            if c.target_level == c.current_level:
                # 已在最高层
                rejected.append({**c.to_dict(), "reject_reason": "already_at_top"})
                self._stats["rejections"] += 1
                continue

            if not dry_run:
                self._levels[c.entry_id] = c.target_level
                self._promoted[c.entry_id] = datetime.now(timezone.utc).isoformat()
                self._stats["promotions"] += 1
                # 晋升后重置窗口内计数（避免重复晋升）
                self._hits[c.entry_id] = [
                    h for h in self._hits.get(c.entry_id, [])
                    if h.get("timestamp", 0) < time.time() - self._rules["promotion_window_days"] * 86400
                ]

            promoted.append(c.to_dict())

        if not dry_run:
            self._save()

        return {
            "promoted": promoted,
            "rejected": rejected,
            "dry_run": dry_run,
            "stats": self.get_stats(),
        }

    # ── 查询与统计 ──

    def get_entry_status(self, entry_id: str) -> dict:
        """查询单条的命中状态"""
        hits = self._hits.get(entry_id, [])
        window_start = time.time() - self._rules["promotion_window_days"] * 86400
        window_hits = [h for h in hits if h.get("timestamp", 0) >= window_start]
        return {
            "entry_id": entry_id,
            "level": self._levels.get(entry_id, "session"),
            "total_hits": len(hits),
            "window_hits": len(window_hits),
            "window_requirements": len({h["requirement_id"] for h in window_hits if h.get("requirement_id")}),
            "promoted_at": self._promoted.get(entry_id),
            "thresholds": self._rules,
        }

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "tracked_entries": len([k for k in self._hits if k != "__meta__"]),
            "promoted_entries": len(self._promoted),
            "rules": self._rules,
        }

    # ── 内部方法 ──

    @staticmethod
    def _next_level(current: str) -> str:
        """获取下一层级"""
        idx = LEVELS.index(current) if current in LEVELS else 0
        return LEVELS[min(idx + 1, len(LEVELS) - 1)]

    @staticmethod
    def _infer_category(entry_id: str, content: str = "") -> str:
        """推断条目应晋升到 KBase 哪个类目"""
        entry_lower = entry_id.lower()
        for key, category in _TYPE_TO_CATEGORY.items():
            if key in entry_lower:
                return category
        # 内容启发式
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["bug", "badcase", "失败", "修复"]):
            return "patterns"
        if any(kw in content_lower for kw in ["接口", "api", "schema", "swagger"]):
            return "infra"
        if any(kw in content_lower for kw in ["规则", "rule", "业务"]):
            return "features"
        return "patterns"  # 默认进 patterns（BadCase 库）

    def _save(self):
        if not self._tracking_path:
            return
        try:
            data = {
                "hits": {k: v for k, v in self._hits.items()},
                "levels": self._levels,
                "promoted": self._promoted,
                "stats": self._stats,
                "rules": self._rules,
            }
            Path(self._tracking_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._tracking_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self._tracking_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._hits = data.get("hits", {})
            self._levels = data.get("levels", {})
            self._promoted = data.get("promoted", {})
            self._stats = data.get("stats", self._stats)
            # 规则不覆盖（硬编码优先，防止持久化数据篡改阈值）
        except Exception:
            pass
