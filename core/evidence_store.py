"""
evidence_store.py — 可观测性与证据链子系统 (Evidence Store)

Harness 五大子系统之一。职责：
- 每次工具调用自动采集四元组证据
- 生成完整证据链 trace JSON
- 持久化到 artifacts/{run_id}/evidence.json
- 支持诊断结论设置

证据四元组格式（符合 Harness 设计文档规范）：
    {
        "step_id": "query_status",
        "tool": "strategy_platform.query_batch_status",
        "input": {...},
        "output": {...},
        "timestamp": "2026-07-06T10:30:00.230+08:00",
        "duration_ms": 230,
        "schema_validated": true
    }

使用方式：
    from core.evidence_store import EvidenceStore
    evidence = EvidenceStore(trace_id="run-001", pipeline="batch-diagnosis")

    evidence.record_step("step1", "click", {"text": "搜索"}, {"clicked": True}, 320, True)
    evidence.set_conclusion("搜索功能正常")
    path = evidence.save(run_dir)
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

@dataclass
class EvidenceEntry:
    """单条证据记录"""
    step_id: str
    tool: str
    input: Any
    output: Any
    timestamp: str
    duration_ms: int
    schema_validated: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "step_id": self.step_id,
            "tool": self.tool,
            "input": self._serialize(self.input),
            "output": self._serialize(self.output),
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "schema_validated": self.schema_validated,
        }
        if self.error:
            d["error"] = self.error
        return d

    @staticmethod
    def _serialize(value: Any) -> Any:
        """确保值可 JSON 序列化"""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, bytes):
            return f"<bytes:{len(value)}>"
        if isinstance(value, (dict, list)):
            try:
                json.dumps(value, ensure_ascii=False)
                return value
            except (TypeError, ValueError):
                return str(value)
        return str(value)

class EvidenceStore:
    """
    证据链采集与存储。
    在执行过程中自动采集每步工具调用的输入/输出证据，
    最终生成完整的诊断 trace。
    """

    def __init__(self, trace_id: str, pipeline: str = "web-automation"):
        self.trace_id = trace_id
        self.pipeline = pipeline
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._steps: List[EvidenceEntry] = []
        self._conclusion: Optional[str] = None

    # ── 记录 ──

    def record_step(
        self,
        step_id: str,
        tool_name: str,
        input_params: Any,
        output_data: Any,
        duration_ms: int,
        schema_validated: bool = True,
        error: Optional[str] = None,
    ):
        """
        记录一步工具调用的证据。

        Args:
            step_id: 步骤标识（如 "step0" 或 step 的 id 字段）
            tool_name: 工具名（step type 或 pipeline 中的 tool 名）
            input_params: 输入参数
            output_data: 输出结果
            duration_ms: 执行耗时（毫秒）
            schema_validated: 是否通过了 schema 校验
            error: 错误信息（如有）
        """
        entry = EvidenceEntry(
            step_id=step_id,
            tool=tool_name,
            input=input_params,
            output=output_data,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            schema_validated=schema_validated,
            error=error,
        )
        self._steps.append(entry)

    def set_conclusion(self, conclusion: str):
        """设置诊断/执行结论"""
        self._conclusion = conclusion

    # ── 查询 ──

    def get_steps(self) -> List[dict]:
        """返回所有证据步骤"""
        return [s.to_dict() for s in self._steps]

    @property
    def evidence_count(self) -> int:
        """证据条数"""
        return len(self._steps)

    @property
    def total_duration_ms(self) -> int:
        """所有步骤总耗时"""
        return sum(s.duration_ms for s in self._steps)

    @property
    def validated_count(self) -> int:
        """通过 schema 校验的步骤数"""
        return sum(1 for s in self._steps if s.schema_validated)

    @property
    def error_count(self) -> int:
        """有错误的步骤数"""
        return sum(1 for s in self._steps if s.error)

    # ── Trace 生成 ──

    def to_trace(self) -> dict:
        """
        生成完整的证据链 trace JSON。
        格式符合 Harness 设计文档中的 evidence chain 标准。
        """
        return {
            "trace_id": self.trace_id,
            "pipeline": self.pipeline,
            "started_at": self.started_at,
            "steps": [s.to_dict() for s in self._steps],
            "conclusion": self._conclusion or "",
            "total_duration_ms": self.total_duration_ms,
            "evidence_count": self.evidence_count,
            "validated_count": self.validated_count,
            "error_count": self.error_count,
        }

    # ── 持久化 ──

    def save(self, run_dir: str, desensitize: bool = True) -> str:
        """
        将证据链持久化到文件。

        Args:
            run_dir: 产物目录路径
            desensitize: 是否脱敏（默认 True，符合 SOUL.md 安全红线）

        Returns:
            evidence.json 的文件路径
        """
        evidence_path = os.path.join(run_dir, "evidence.json")
        trace = self.to_trace()
        if desensitize:
            from core.desensitize_filter import DesensitizeFilter
            trace = DesensitizeFilter().filter_evidence(trace)
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
        return evidence_path

    # ── 摘要 ──

    def to_summary_dict(self) -> dict:
        """生成精简摘要，可嵌入 output.metrics"""
        return {
            "traceId": self.trace_id,
            "evidenceCount": self.evidence_count,
            "validatedCount": self.validated_count,
            "errorCount": self.error_count,
            "totalDurationMs": self.total_duration_ms,
            "conclusion": self._conclusion or "",
        }
