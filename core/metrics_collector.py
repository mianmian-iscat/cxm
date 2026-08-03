"""
metrics_collector.py — 度量指标计算引擎

负责：
- 从 MetricsLogger 的原始日志中聚合计算核心统一指标和业务差异化指标
- 输出结构化的 MetricsReport，供 Dashboard / 告警 / 产物归档使用

核心统一指标（所有业务必须监控）：
    - task_success_rate:    任务成功率
    - avg_task_duration:    平均任务耗时（ms）
    - cost_per_task:        Token/资源消耗比
    - false_positive_rate:  误报率
    - change_frequency:     脚本/提示词变更频率（次/月）

业务差异化指标（F88 / 原创保护）：
    - llm_confidence_avg:       LLM 决策置信度均值
    - self_heal_success_rate:   自愈成功率
    - compliance_intercept_count: 合规拦截触发次数
    - visual_evidence_score:    视觉取证完整率

使用方式：
    from core.metrics_collector import MetricsCollector
    collector = MetricsCollector(task_id="run-001", business_type="f88_material")
    report = collector.compute(metrics_logger.entries)
    collector.save_report(report, run_dir)
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

from core.metrics_logger import MetricLogEntry

# ── 变更频率统计 ──

_CHANGELOG_PATH = os.path.join(os.path.dirname(__file__), "..", "history", "CHANGELOG.md")

def _count_monthly_changes(changelog_path: str = _CHANGELOG_PATH) -> int:
    """
    从 CHANGELOG.md 统计本月变更次数。
    通过匹配日期格式 [YYYY-MM-DD] 的行数来计算。
    """
    if not os.path.exists(changelog_path):
        return 0

    now = datetime.now(timezone.utc)
    current_month_prefix = now.strftime("%Y-%m")

    try:
        with open(changelog_path, encoding="utf-8") as f:
            content = f.read()

        # 匹配形如 [2026-06-29] 或 - [2026-06-29] 的行
        pattern = rf"\[{re.escape(current_month_prefix)}-\d{{2}}\]"
        matches = re.findall(pattern, content)
        return len(matches)
    except Exception:
        return 0

# ── 指标报告 ──

@dataclass
class CoreMetrics:
    """五大核心统一指标"""
    task_success_rate: float = 0.0       # 0.0 ~ 1.0
    avg_task_duration_ms: int = 0        # 毫秒
    cost_per_task: int = 0               # Token 数（0 表示无 LLM 调用）
    false_positive_rate: float = 0.0     # 0.0 ~ 1.0
    change_frequency: int = 0            # 本月变更次数

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BusinessMetrics:
    """业务差异化指标"""
    llm_confidence_avg: Optional[float] = None        # 0.0 ~ 1.0，无 LLM 时为 None
    self_heal_success_rate: Optional[float] = None    # 0.0 ~ 1.0
    compliance_intercept_count: int = 0               # 合规拦截次数
    visual_evidence_score: float = 1.0                # 0.0 ~ 1.0，截图有效比例

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

@dataclass
class MetricsReport:
    """完整度量报告"""
    task_id: str
    business_type: str
    core_metrics: CoreMetrics = field(default_factory=CoreMetrics)
    business_metrics: BusinessMetrics = field(default_factory=BusinessMetrics)
    raw_log_count: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "business_type": self.business_type,
            "core_metrics": self.core_metrics.to_dict(),
            "business_metrics": self.business_metrics.to_dict(),
            "raw_log_count": self.raw_log_count,
            "generated_at": self.generated_at,
        }

    def to_summary_dict(self) -> dict:
        """生成附加到 output["metrics"] 的精简摘要"""
        summary = {
            "businessType": self.business_type,
            "taskSuccessRate": self.core_metrics.task_success_rate,
            "avgDurationMs": self.core_metrics.avg_task_duration_ms,
            "totalTokenUsed": self.core_metrics.cost_per_task,
            "falsePositiveRate": self.core_metrics.false_positive_rate,
            "visualEvidenceScore": self.business_metrics.visual_evidence_score,
        }
        # 提效比：AI 耗时 / 人工基线耗时（默认基线 200s）
        _baseline_ms = 200000
        if self.core_metrics.avg_task_duration_ms > 0:
            summary["efficiencyRatio"] = round(
                self.core_metrics.avg_task_duration_ms / _baseline_ms, 4
            )
        if self.business_metrics.llm_confidence_avg is not None:
            summary["llmConfidenceAvg"] = self.business_metrics.llm_confidence_avg
        if self.business_metrics.self_heal_success_rate is not None:
            summary["selfHealSuccessRate"] = self.business_metrics.self_heal_success_rate
        return summary

# ── 指标计算引擎 ──

class MetricsCollector:
    """
    从原始 MetricLogEntry 列表中计算度量指标。
    每次执行实例化一次，调用 compute() 生成完整报告。
    """

    def __init__(
        self,
        task_id: str,
        business_type: str = "unknown",
        overall_status: str = "pass",
        task_duration_ms: int = 0,
    ):
        """
        Args:
            task_id: 本次执行的 run_id
            business_type: 业务类型标识
            overall_status: 整体执行状态（pass/fail/error）
            task_duration_ms: 任务总耗时（从 impl.py output["duration"] 获取）
        """
        self.task_id = task_id
        self.business_type = business_type
        self.overall_status = overall_status
        self.task_duration_ms = task_duration_ms

    def compute(self, entries: List[MetricLogEntry]) -> MetricsReport:
        """
        从原始日志计算完整度量报告。

        Args:
            entries: MetricsLogger 收集的日志条目列表

        Returns:
            MetricsReport 实例
        """
        report = MetricsReport(
            task_id=self.task_id,
            business_type=self.business_type,
            raw_log_count=len(entries),
        )

        # ── 核心指标 ──
        report.core_metrics = self._compute_core_metrics(entries)

        # ── 业务差异化指标 ──
        report.business_metrics = self._compute_business_metrics(entries)

        return report

    def _compute_core_metrics(self, entries: List[MetricLogEntry]) -> CoreMetrics:
        """计算五大核心统一指标"""
        metrics = CoreMetrics()

        if not entries:
            return metrics

        # 1. task_success_rate: 整体任务维度（1 个任务，通过 overall_status 判断）
        metrics.task_success_rate = 1.0 if self.overall_status == "pass" else 0.0

        # 2. avg_task_duration: 任务级耗时（单次执行 = 该任务耗时）
        metrics.avg_task_duration_ms = self.task_duration_ms

        # 3. cost_per_task: 总 Token 消耗（单次执行 = 该任务的 Token 总数）
        total_tokens = sum(e.token_used for e in entries if e.token_used is not None)
        metrics.cost_per_task = total_tokens

        # 4. false_positive_rate: assert 步骤中标记为误报的比例
        assert_entries = [e for e in entries if e.step == "assert"]
        false_positives = [e for e in assert_entries if e.is_false_positive is True]
        if assert_entries:
            metrics.false_positive_rate = len(false_positives) / len(assert_entries)
        else:
            metrics.false_positive_rate = 0.0

        # 5. change_frequency: 本月 CHANGELOG 变更次数
        metrics.change_frequency = _count_monthly_changes()

        return metrics

    def _compute_business_metrics(self, entries: List[MetricLogEntry]) -> BusinessMetrics:
        """计算业务差异化指标"""
        metrics = BusinessMetrics()

        # 1. llm_confidence_avg: LLM 调用的置信度均值
        llm_entries = [e for e in entries if e.confidence is not None]
        if llm_entries:
            metrics.llm_confidence_avg = round(
                sum(e.confidence for e in llm_entries) / len(llm_entries), 4
            )

        # 2. self_heal_success_rate: retrying -> success 的转换比例
        #    统计方式：同一 step+action 组合中，先出现 retrying 后出现 success 的比例
        retry_groups = {}
        for e in entries:
            key = (e.step, e.action)
            if key not in retry_groups:
                retry_groups[key] = []
            retry_groups[key].append(e.result)

        heal_attempts = 0
        heal_successes = 0
        for key, results in retry_groups.items():
            for i, r in enumerate(results):
                if r == "retrying":
                    heal_attempts += 1
                    # 检查后续是否有 success
                    if any(results[j] == "success" for j in range(i + 1, len(results))):
                        heal_successes += 1

        if heal_attempts > 0:
            metrics.self_heal_success_rate = round(heal_successes / heal_attempts, 4)

        # 3. compliance_intercept_count: 合规拦截触发次数
        metrics.compliance_intercept_count = sum(
            1 for e in entries if e.error_code == "COMPLIANCE_BLOCKED"
        )

        # 4. visual_evidence_score: 截图完整率
        #    计算方式：有 screenshot_path 且文件存在的步骤比例
        screenshot_expected = [
            e for e in entries
            if e.step in ("screenshot", "click", "fill", "navigate", "assert")
            and e.result in ("success", "failed")
        ]
        if screenshot_expected:
            valid_screenshots = sum(
                1 for e in screenshot_expected
                if e.screenshot_path and os.path.isfile(e.screenshot_path)
            )
            metrics.visual_evidence_score = round(
                valid_screenshots / len(screenshot_expected), 4
            )
        else:
            metrics.visual_evidence_score = 1.0

        return metrics

    # ── 持久化 ──

    @staticmethod
    def save_report(report: MetricsReport, run_dir: str) -> str:
        """
        将度量报告写入 artifacts/{run_id}/metrics_report.json。

        Args:
            report: MetricsReport 实例
            run_dir: 本次执行的产物目录

        Returns:
            报告文件路径
        """
        report_path = os.path.join(run_dir, "metrics_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        return report_path
