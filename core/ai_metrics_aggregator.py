"""
ai_metrics_aggregator.py — 跨 run AI 内核指标聚合（维度 ∞）

把每次 run 的 AI 能力产出（自愈成功 / LLM 裁决 / 知识检索 / 策略链学习）
按行追加到 JSONL，并提供聚合查询与趋势分析。

解决的问题：
- 单次 HealingAnalytics 只覆盖一次 run，缺长期趋势看板
- LLM 裁决命中率 / 知识检索召回率 没有跨 run 的量化指标
- 自愈策略的长期表现无法对比

使用方式：
    from core.ai_metrics_aggregator import AiMetricsAggregator

    # 在 FinalizePipeline 末尾调用一次
    agg = AiMetricsAggregator()
    agg.record(output, run_id="xxx", business_type="f88")

    # 查询近 30 天聚合
    report = agg.aggregate(days=30, business_type="f88")
    print(report)

存储位置：
    {artifacts_root}/ai_metrics/metrics.jsonl        # 每行一条 run 记录
    {artifacts_root}/ai_metrics/latest_summary.json  # 最近一次聚合结果缓存
"""

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


# ── 默认存储路径 ──

def _default_metrics_dir() -> str:
    """默认存储目录：{skill_root}/artifacts/ai_metrics/"""
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_dir = os.environ.get("WEB_AUTO_ARTIFACTS_DIR")
    base = env_dir if env_dir else os.path.join(skill_root, "artifacts")
    return os.path.join(base, "ai_metrics")


@dataclass
class AiMetricSnapshot:
    """单次聚合的指标快照"""
    window_days: int
    business_type: Optional[str]
    sample_size: int
    timestamp: str

    # 自愈能力
    healing_attempts: int = 0
    healing_successes: int = 0
    healing_success_rate: float = 0.0
    top_healing_strategies: List[dict] = field(default_factory=list)
    degraded_strategies: List[str] = field(default_factory=list)

    # LLM 裁决（如果本次 run 调用了 llm_judge）
    llm_judge_invocations: int = 0
    llm_judge_agreements: int = 0
    llm_judge_agreement_rate: float = 0.0

    # 知识检索
    knowledge_hits: int = 0
    knowledge_misses: int = 0
    knowledge_recall: float = 0.0

    # 策略链学习
    chain_learning_total: int = 0
    chain_learning_effective: int = 0
    chain_learning_rate: float = 0.0

    # 失败聚类
    total_failures: int = 0
    failure_clusters: int = 0

    # 趋势（按日）
    daily_trend: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "window_days": self.window_days,
            "business_type": self.business_type,
            "sample_size": self.sample_size,
            "timestamp": self.timestamp,
            "healing": {
                "attempts": self.healing_attempts,
                "successes": self.healing_successes,
                "success_rate": round(self.healing_success_rate, 4),
                "top_strategies": self.top_healing_strategies,
                "degraded": self.degraded_strategies,
            },
            "llm_judge": {
                "invocations": self.llm_judge_invocations,
                "agreements": self.llm_judge_agreements,
                "agreement_rate": round(self.llm_judge_agreement_rate, 4),
            },
            "knowledge": {
                "hits": self.knowledge_hits,
                "misses": self.knowledge_misses,
                "recall": round(self.knowledge_recall, 4),
            },
            "chain_learning": {
                "total": self.chain_learning_total,
                "effective": self.chain_learning_effective,
                "rate": round(self.chain_learning_rate, 4),
            },
            "failure_clustering": {
                "total": self.total_failures,
                "clusters": self.failure_clusters,
            },
            "daily_trend": self.daily_trend,
        }


class AiMetricsAggregator:
    """
    跨 run AI 内核指标聚合器。

    设计原则：
    - append-only JSONL，避免写入竞争
    - 每条记录包含 run_id / timestamp / business_type / 四类 AI 能力原始值
    - 聚合按需计算，不持久化中间结果（latest_summary.json 仅缓存最近一次）
    """

    def __init__(self, metrics_dir: Optional[str] = None):
        self.metrics_dir = metrics_dir or _default_metrics_dir()
        self.metrics_file = os.path.join(self.metrics_dir, "metrics.jsonl")
        self.summary_file = os.path.join(self.metrics_dir, "latest_summary.json")
        os.makedirs(self.metrics_dir, exist_ok=True)

    # ── 写入 ──

    def record(
        self,
        output: dict,
        run_id: str = "",
        business_type: str = "unknown",
        input_data: Optional[dict] = None,
    ) -> dict:
        """
        从单次 run 的 output 中提取 AI 能力指标并追加到 JSONL。

        Args:
            output: impl.py 的最终输出 dict
            run_id: 本次 run 的标识
            business_type: 业务域（f88 / op / qianniu 等）
            input_data: 可选，用于补充 case_id / scene 等元信息

        Returns:
            写入的 record dict（不含尾部换行）
        """
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "run_id": run_id,
            "timestamp": now,
            "business_type": business_type,
            "case_id": (input_data or {}).get("id"),
            "scene": (input_data or {}).get("scene"),
            "status": output.get("status", "unknown"),
        }

        # 1. 自愈能力
        healing = output.get("healingAnalytics") or {}
        record["healing"] = {
            "attempts": healing.get("total_heals", 0),
            "successes": healing.get("total_success", 0),
            "strategies": healing.get("strategy_stats", []),
            "degraded": healing.get("degraded_strategies", []),
            "roi": healing.get("roi_score", 0.0),
        }

        # 2. LLM 裁决
        llm = output.get("llmJudge") or output.get("llmJudgeResult") or {}
        record["llm_judge"] = {
            "invocations": llm.get("invocations", 0),
            "agreements": llm.get("agreements", 0),
            "decisions": llm.get("decisions", []),
        }

        # 3. 知识检索
        kb = output.get("knowledgeSearch") or output.get("knowledgeRetrieval") or {}
        record["knowledge"] = {
            "hits": kb.get("hits", 0),
            "misses": kb.get("misses", 0),
            "queries": kb.get("queries", []),
        }

        # 4. 策略链学习
        chain = output.get("strategyChainStats") or {}
        record["chain_learning"] = {
            "total": chain.get("total_chains", 0),
            "effective": chain.get("effective_chains", 0),
            "avg_length": chain.get("avg_chain_length", 0.0),
        }

        # 5. 失败聚类
        clustering = output.get("failureClustering") or {}
        record["failure_clustering"] = {
            "total": clustering.get("total_failures", 0),
            "clusters": clustering.get("num_clusters", 0),
            "top_clusters": clustering.get("top_clusters", []),
        }

        # 追加写入（line-buffered，支持并发读）
        try:
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[ai_metrics] 写入失败（不影响主流程）: {e}", file=sys.stderr)

        return record

    # ── 读取 ──

    def read_records(
        self,
        days: Optional[int] = None,
        business_type: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """
        读取 JSONL 记录，支持多维过滤。

        Args:
            days: 仅返回最近 N 天内的记录（None=不限）
            business_type: 仅返回该业务域的记录（None=不限）
            run_id: 精确匹配 run_id
            limit: 最多返回 N 条（None=不限）

        Returns:
            符合条件的记录列表（按时间正序）
        """
        if not os.path.exists(self.metrics_file):
            return []

        cutoff_ts = None
        if days is not None:
            from datetime import timedelta
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        results = []
        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if cutoff_ts and rec.get("timestamp", "") < cutoff_ts:
                        continue
                    if business_type and rec.get("business_type") != business_type:
                        continue
                    if run_id and rec.get("run_id") != run_id:
                        continue
                    results.append(rec)
                    if limit and len(results) >= limit:
                        break
        except OSError as e:
            print(f"[ai_metrics] 读取失败: {e}", file=sys.stderr)

        return results

    # ── 聚合 ──

    def aggregate(
        self,
        days: int = 30,
        business_type: Optional[str] = None,
        persist_summary: bool = True,
    ) -> Dict[str, Any]:
        """
        聚合最近 N 天的 AI 内核指标，返回快照 dict。

        Args:
            days: 聚合窗口（天）
            business_type: 限定业务域（None=全部）
            persist_summary: 是否把结果缓存到 latest_summary.json

        Returns:
            AiMetricSnapshot.to_dict() 的结果
        """
        records = self.read_records(days=days, business_type=business_type)
        snap = AiMetricSnapshot(
            window_days=days,
            business_type=business_type,
            sample_size=len(records),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if not records:
            result = snap.to_dict()
            if persist_summary:
                self._persist_summary(result)
            return result

        # 自愈
        strat_agg: Dict[str, Dict[str, int]] = defaultdict(lambda: {"attempts": 0, "successes": 0})
        for rec in records:
            h = rec.get("healing", {})
            snap.healing_attempts += h.get("attempts", 0)
            snap.healing_successes += h.get("successes", 0)
            for st in h.get("strategies", []):
                key = st.get("strategy", "unknown")
                strat_agg[key]["attempts"] += st.get("attempts", 0)
                strat_agg[key]["successes"] += st.get("successes", 0)
            snap.degraded_strategies.extend(h.get("degraded", []))

        if snap.healing_attempts:
            snap.healing_success_rate = snap.healing_successes / snap.healing_attempts

        # 自愈 top 策略
        ranked = sorted(
            [
                {
                    "strategy": k,
                    "attempts": v["attempts"],
                    "successes": v["successes"],
                    "success_rate": (v["successes"] / v["attempts"]) if v["attempts"] else 0.0,
                }
                for k, v in strat_agg.items()
            ],
            key=lambda x: (-x["attempts"], -x["success_rate"]),
        )
        snap.top_healing_strategies = ranked[:10]
        # 成功率 < 50% 且尝试数 > 5 视为退化
        snap.degraded_strategies = list(set(
            s["strategy"] for s in ranked
            if s["attempts"] >= 5 and s["success_rate"] < 0.5
        ))

        # LLM 裁决
        for rec in records:
            lj = rec.get("llm_judge", {})
            snap.llm_judge_invocations += lj.get("invocations", 0)
            snap.llm_judge_agreements += lj.get("agreements", 0)
        if snap.llm_judge_invocations:
            snap.llm_judge_agreement_rate = (
                snap.llm_judge_agreements / snap.llm_judge_invocations
            )

        # 知识检索
        for rec in records:
            kb = rec.get("knowledge", {})
            snap.knowledge_hits += kb.get("hits", 0)
            snap.knowledge_misses += kb.get("misses", 0)
        total_kb = snap.knowledge_hits + snap.knowledge_misses
        if total_kb:
            snap.knowledge_recall = snap.knowledge_hits / total_kb

        # 策略链学习
        for rec in records:
            cl = rec.get("chain_learning", {})
            snap.chain_learning_total += cl.get("total", 0)
            snap.chain_learning_effective += cl.get("effective", 0)
        if snap.chain_learning_total:
            snap.chain_learning_rate = (
                snap.chain_learning_effective / snap.chain_learning_total
            )

        # 失败聚类
        for rec in records:
            fc = rec.get("failure_clustering", {})
            snap.total_failures += fc.get("total", 0)
            snap.failure_clusters += fc.get("clusters", 0)

        # 日趋势（按日期聚合自愈成功率）
        daily: Dict[str, Dict[str, int]] = defaultdict(lambda: {"attempts": 0, "successes": 0})
        for rec in records:
            day = rec.get("timestamp", "")[:10]
            if not day:
                continue
            h = rec.get("healing", {})
            daily[day]["attempts"] += h.get("attempts", 0)
            daily[day]["successes"] += h.get("successes", 0)
        snap.daily_trend = sorted(
            [
                {
                    "date": d,
                    "attempts": v["attempts"],
                    "successes": v["successes"],
                    "success_rate": round(
                        v["successes"] / v["attempts"] if v["attempts"] else 0.0, 4
                    ),
                }
                for d, v in daily.items()
            ],
            key=lambda x: x["date"],
        )

        result = snap.to_dict()
        if persist_summary:
            self._persist_summary(result)
        return result

    # ── 内部 ──

    def _persist_summary(self, summary: dict) -> None:
        try:
            with open(self.summary_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(summary, ensure_ascii=False, indent=2))
        except OSError as e:
            print(f"[ai_metrics] 缓存写入失败: {e}", file=sys.stderr)
