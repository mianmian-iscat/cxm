"""
strategy_chain.py — 策略组合学习与推荐引擎

追踪每次自愈过程中实际应用的策略序列（而非单步策略），
学习"哪些策略组合对哪类错误最有效"，并在后续自愈时优先推荐历史成功的组合。

核心概念：
- StrategyChain: 一次自愈中实际使用的策略序列（如 [cdp_relocate, scroll_click, smart_wait]）
- ChainStats: 某条组合路径的统计（成功次数、失败次数、平均耗时）
- StrategyChainLearner: 学习器，记录组合、查询最优、推荐策略

使用方式：
    from core.strategy_chain import StrategyChainLearner

    learner = StrategyChainLearner()

    # 自愈时记录尝试的策略链
    learner.start_chain(error_type="element_timeout", error_msg="xxx")
    learner.add_strategy("cdp_relocate", success=False, duration_ms=500)
    learner.add_strategy("scroll_click", success=False, duration_ms=300)
    learner.add_strategy("smart_wait", success=True, duration_ms=1200)
    learner.finish_chain(success=True)

    # 下次遇到类似错误时推荐最优组合
    recommended = learner.recommend_chain("element_timeout", "yyy")
    # -> ["cdp_relocate", "scroll_click", "smart_wait"]
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import re


@dataclass
class StrategyStep:
    """组合链中的一步策略"""
    strategy: str
    success: bool
    duration_ms: int
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChainStats:
    """某条策略组合路径的统计"""
    chain: List[str]           # 策略序列，如 ["cdp_relocate", "scroll_click"]
    success_count: int = 0
    fail_count: int = 0
    total_duration_ms: int = 0
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_types: List[str] = field(default_factory=list)  # 曾成功修复的错误类型

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def avg_duration_ms(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.total_duration_ms / total

    def to_dict(self) -> dict:
        return {
            "chain": self.chain,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "last_seen": self.last_seen,
            "error_types": self.error_types,
        }


class StrategyChainLearner:
    """
    策略组合学习引擎：
    - 记录每次自愈的完整策略链
    - 统计各组合的成功率/耗时
    - 推荐历史最优组合
    - 支持持久化到 strategy-chains.json
    """

    # 推荐阈值：成功率 >= 此值才会推荐
    RECOMMEND_THRESHOLD = 0.5
    # 最多推荐组合数
    MAX_RECOMMEND = 3
    # 持久化路径（相对于 base_dir）
    CHAINS_FILE = "references/strategy-chains.json"

    def __init__(self, base_dir: str = ""):
        self._base_dir = base_dir
        self._chains: Dict[str, ChainStats] = {}  # chain_key -> ChainStats
        self._current_chain: Optional[List[StrategyStep]] = None
        self._current_error_type: str = ""
        self._current_error_msg: str = ""

        # 加载已有数据
        if base_dir:
            self._load_from_disk()

    # ── 记录 ──

    def start_chain(self, error_type: str, error_msg: str = ""):
        """开始记录一条新的策略链"""
        self._current_chain = []
        self._current_error_type = error_type
        self._current_error_msg = error_msg

    def add_strategy(self, strategy: str, success: bool, duration_ms: int = 0, detail: str = ""):
        """记录当前链中的一步策略"""
        if self._current_chain is None:
            return
        self._current_chain.append(StrategyStep(
            strategy=strategy,
            success=success,
            duration_ms=duration_ms,
            detail=detail,
        ))

    def finish_chain(self, success: bool) -> dict:
        """
        结束当前链并记录统计。

        Returns:
            {"chain_key": str, "chain": [...], "success": bool}
        """
        if self._current_chain is None:
            return {"chain_key": "", "chain": [], "success": False}

        # 提取策略序列
        chain = [step.strategy for step in self._current_chain]
        total_duration = sum(step.duration_ms for step in self._current_chain)

        if not chain:
            self._current_chain = None
            return {"chain_key": "", "chain": [], "success": False}

        chain_key = self._chain_key(chain)
        stats = self._chains.get(chain_key)
        if stats is None:
            stats = ChainStats(chain=chain)
            self._chains[chain_key] = stats

        if success:
            stats.success_count += 1
            if self._current_error_type and self._current_error_type not in stats.error_types:
                stats.error_types.append(self._current_error_type)
        else:
            stats.fail_count += 1

        stats.total_duration_ms += total_duration
        stats.last_seen = datetime.now(timezone.utc).isoformat()

        result = {
            "chain_key": chain_key,
            "chain": chain,
            "success": success,
            "total_duration_ms": total_duration,
        }

        self._current_chain = None
        return result

    # ── 查询与推荐 ──

    def recommend_chain(self, error_type: str, error_msg: str = "") -> List[str]:
        """
        根据错误类型推荐历史最优的策略组合。

        Returns:
            推荐的策略序列，如 ["cdp_relocate", "scroll_click"]
            如果没有历史数据则返回空列表
        """
        candidates = []
        error_lower = error_msg.lower() if error_msg else ""

        for stats in self._chains.values():
            # 必须达到推荐阈值
            if stats.success_rate < self.RECOMMEND_THRESHOLD:
                continue
            # 至少成功过 1 次
            if stats.success_count < 1:
                continue

            # 计算与当前错误的匹配度
            score = self._error_match_score(stats, error_type, error_lower)
            if score > 0:
                candidates.append((score * stats.success_rate, stats))

        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates:
            return candidates[0][1].chain[:]
        return []

    def get_top_chains(self, error_type: str = "", top_k: int = 5) -> List[ChainStats]:
        """
        获取某类错误的 Top-K 策略组合。

        Args:
            error_type: 错误类型过滤（空则返回全局 Top-K）
            top_k: 返回数量

        Returns:
            按成功率排序的 ChainStats 列表
        """
        filtered = self._chains.values()
        if error_type:
            filtered = [
                s for s in filtered
                if error_type in s.error_types or not s.error_types
            ]
        sorted_chains = sorted(filtered, key=lambda s: s.success_rate, reverse=True)
        return sorted_chains[:top_k]

    def get_all_chains(self) -> List[dict]:
        """获取所有已记录的策略链统计"""
        return [stats.to_dict() for stats in self._chains.values()]

    def get_stats(self) -> dict:
        """获取学习器统计摘要"""
        total_chains = len(self._chains)
        total_success = sum(s.success_count for s in self._chains.values())
        total_fail = sum(s.fail_count for s in self._chains.values())
        avg_success_rate = (
            sum(s.success_rate for s in self._chains.values()) / total_chains
            if total_chains > 0 else 0.0
        )
        return {
            "total_chains": total_chains,
            "total_success": total_success,
            "total_fail": total_fail,
            "avg_success_rate": round(avg_success_rate, 3),
        }

    # ── 持久化 ──

    def save(self, base_dir: str = ""):
        """将策略链统计持久化到 JSON"""
        target_dir = base_dir or self._base_dir
        if not target_dir:
            return
        path = os.path.join(target_dir, self.CHAINS_FILE)
        data = {
            "chains": {k: v.to_dict() for k, v in self._chains.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, IOError):
            pass

    def _load_from_disk(self):
        """从 JSON 加载策略链统计"""
        if not self._base_dir:
            return
        path = os.path.join(self._base_dir, self.CHAINS_FILE)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, entry in data.get("chains", {}).items():
                self._chains[key] = ChainStats(
                    chain=entry.get("chain", []),
                    success_count=entry.get("success_count", 0),
                    fail_count=entry.get("fail_count", 0),
                    total_duration_ms=entry.get("total_duration_ms", 0),
                    last_seen=entry.get("last_seen", ""),
                    error_types=entry.get("error_types", []),
                )
        except (IOError, json.JSONDecodeError):
            pass

    # ── 内部方法 ──

    @staticmethod
    def _chain_key(chain: List[str]) -> str:
        """将策略序列转为唯一 key"""
        return " → ".join(chain)

    @staticmethod
    def _error_match_score(stats: ChainStats, error_type: str, error_lower: str) -> float:
        """计算 ChainStats 与当前错误的匹配度 (0.0~1.0)"""
        score = 0.0

        # 错误类型匹配
        if error_type and error_type in stats.error_types:
            score += 0.6

        # 错误消息关键词匹配
        if error_lower:
            for chain_strategy in stats.chain:
                # 策略名中的词如果出现在错误消息中，加分
                words = [w for w in re.split(r'[\s\-_]+', chain_strategy.lower()) if len(w) > 3]
                if any(w in error_lower for w in words):
                    score += 0.2
                    break

        # 如果完全没有匹配信号，给一个基础分（让历史数据有机会被使用）
        if score == 0.0 and not error_type:
            score = 0.1

        return min(score, 1.0)
