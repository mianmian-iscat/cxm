"""
context_manager.py — 上下文管理器

原创保护 Harness 上下文与状态管理：
- Case-Execution 双向追溯绑定
- Session Memory 管理
- 覆盖率矩阵计算
- 与 MetricsCollector 集成

使用方式:
    from core.context_manager import ContextManager
    ctx = ContextManager(run_id="run-001")
    ctx.bind_case_execution("OP-TC-0312", execution_result)
    report = ctx.compute_coverage_matrix()
"""

import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from collections import defaultdict


@dataclass
class CaseExecutionBinding:
    """用例-执行绑定记录"""
    case_id: str
    requirement_ref: str = ""      # 关联需求文档编号
    pipeline_run_id: str = ""
    execution: dict = field(default_factory=dict)
    coverage_tags: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CoverageEntry:
    """覆盖率矩阵单行"""
    module: str
    total_cases: int = 0
    executed: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def coverage_rate(self) -> float:
        return self.executed / self.total_cases if self.total_cases > 0 else 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.executed if self.executed > 0 else 0.0


@dataclass
class SessionMemory:
    """会话记忆"""
    session_id: str = ""
    started_at: str = ""
    last_active_at: str = ""
    variables: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    tags: list = field(default_factory=list)


class ContextManager:
    """
    上下文管理器：原创保护 Harness 的 Case-Execution 追溯引擎。

    核心能力:
    1. 每条用例的执行结果与原始需求双向追溯
    2. 会话级记忆管理
    3. 覆盖率矩阵自动计算
    4. 与 MetricsCollector 集成输出报告
    """

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self._bindings: dict[str, CaseExecutionBinding] = {}
        self._module_cases: dict[str, list[str]] = defaultdict(list)  # module -> [case_ids]
        self._session: Optional[SessionMemory] = None
        self._artifacts_dir: str = ""

    # ── Case-Execution 绑定 ──

    def bind_case_execution(
        self,
        case_id: str,
        execution_result: dict = None,
        requirement_ref: str = "",
        pipeline_run_id: str = "",
        coverage_tags: list = None,
        module: str = "",
    ) -> CaseExecutionBinding:
        """
        绑定用例与执行结果。
        
        Args:
            case_id: 用例 ID (格式: OP-TC-NNNN)
            execution_result: 执行结果字典
            requirement_ref: 需求文档编号
            pipeline_run_id: Pipeline 运行 ID
            coverage_tags: 覆盖标签
            module: 所属模块
        """
        now = datetime.now().isoformat()

        binding = CaseExecutionBinding(
            case_id=case_id,
            requirement_ref=requirement_ref,
            pipeline_run_id=pipeline_run_id or self.run_id,
            execution=execution_result or {},
            coverage_tags=coverage_tags or [],
            created_at=now,
            updated_at=now,
        )

        self._bindings[case_id] = binding

        # 按模块分组（去重）
        if module:
            if case_id not in self._module_cases[module]:
                self._module_cases[module].append(case_id)

        return binding

    def get_binding(self, case_id: str) -> Optional[CaseExecutionBinding]:
        """获取用例绑定"""
        return self._bindings.get(case_id)

    def get_bindings_by_module(self, module: str) -> list[CaseExecutionBinding]:
        """按模块获取绑定"""
        case_ids = self._module_cases.get(module, [])
        return [self._bindings[cid] for cid in case_ids if cid in self._bindings]

    def get_bindings_by_tag(self, tag: str) -> list[CaseExecutionBinding]:
        """按覆盖标签获取绑定"""
        return [b for b in self._bindings.values() if tag in b.coverage_tags]

    def get_bindings_by_requirement(self, requirement_ref: str) -> list[CaseExecutionBinding]:
        """按需求编号获取绑定"""
        return [b for b in self._bindings.values() if b.requirement_ref == requirement_ref]

    def get_failed_cases(self) -> list[CaseExecutionBinding]:
        """获取所有失败用例"""
        return [
            b for b in self._bindings.values()
            if b.execution.get("result") == "FAIL"
            or b.execution.get("status") == "fail"
        ]

    def get_traceability(self, case_id: str) -> dict:
        """
        获取用例的完整追溯链。
        
        从需求 → 用例 → 执行 → 证据，双向追溯。
        """
        binding = self._bindings.get(case_id)
        if not binding:
            return {"error": f"用例未绑定: {case_id}"}

        return {
            "case_id": case_id,
            "requirement_ref": binding.requirement_ref,
            "pipeline_run_id": binding.pipeline_run_id,
            "execution": binding.execution,
            "coverage_tags": binding.coverage_tags,
            "created_at": binding.created_at,
            "related_cases": [
                b.case_id for b in self._bindings.values()
                if b.requirement_ref == binding.requirement_ref
                and b.case_id != case_id
            ],
        }

    # ── Session Memory ──

    def init_session(self, session_id: str = "", tags: list = None) -> SessionMemory:
        """初始化会话记忆"""
        now = datetime.now().isoformat()
        self._session = SessionMemory(
            session_id=session_id or f"sess-{self.run_id}",
            started_at=now,
            last_active_at=now,
            tags=tags or [],
        )
        return self._session

    def update_session(self, key: str, value: Any):
        """更新会话变量"""
        if self._session:
            self._session.variables[key] = value
            self._session.last_active_at = datetime.now().isoformat()

    def get_session_var(self, key: str, default: Any = None) -> Any:
        """获取会话变量"""
        if self._session:
            return self._session.variables.get(key, default)
        return default

    def record_session_event(self, event: str, details: dict = None):
        """记录会话事件"""
        if self._session:
            self._session.history.append({
                "event": event,
                "timestamp": datetime.now().isoformat(),
                "details": details or {},
            })

    # ── 覆盖率矩阵 ──

    def register_module_cases(self, module: str, case_ids: list[str]):
        """注册模块的用例清单（用于覆盖率计算）"""
        self._module_cases[module] = list(set(self._module_cases.get(module, []) + case_ids))

    def compute_coverage_matrix(self) -> list[CoverageEntry]:
        """
        计算覆盖率矩阵。
        
        基于已注册的模块用例和实际执行绑定计算。
        """
        matrix = []

        for module, case_ids in sorted(self._module_cases.items()):
            entry = CoverageEntry(
                module=module,
                total_cases=len(case_ids),
            )

            for cid in case_ids:
                binding = self._bindings.get(cid)
                if binding and binding.execution:
                    entry.executed += 1
                    result = (
                        binding.execution.get("result", "")
                        or binding.execution.get("status", "")
                    ).upper()
                    if result in ("PASS", "PASSED"):
                        entry.passed += 1
                    elif result in ("FAIL", "FAILED"):
                        entry.failed += 1
                    else:
                        entry.skipped += 1
                # 未执行的用例不计入 executed

            matrix.append(entry)

        # 合计行
        if matrix:
            total = CoverageEntry(module="合计")
            for e in matrix:
                total.total_cases += e.total_cases
                total.executed += e.executed
                total.passed += e.passed
                total.failed += e.failed
                total.skipped += e.skipped
            matrix.append(total)

        return matrix

    def coverage_to_table(self) -> str:
        """覆盖率矩阵格式化为文本表格"""
        matrix = self.compute_coverage_matrix()
        if not matrix:
            return "无覆盖率数据"

        lines = [
            f"{'模块':<16}│{'用例数':>6}│{'已执行':>6}│{'PASS':>5}│{'FAIL':>5}│{'覆盖率':>7}",
            "─" * 60,
        ]
        for e in matrix:
            lines.append(
                f"{e.module:<16}│{e.total_cases:>6}│{e.executed:>6}│{e.passed:>5}│"
                f"{e.failed:>5}│{e.coverage_rate:>6.0%}"
            )

        return "\n".join(lines)

    # ── 持久化 ──

    def flush(self, output_dir: str) -> dict:
        """将上下文数据持久化到文件"""
        os.makedirs(output_dir, exist_ok=True)
        paths = {}

        # 1. 绑定数据
        bindings_path = os.path.join(output_dir, "case_execution_bindings.json")
        bindings_data = {
            "run_id": self.run_id,
            "total_bindings": len(self._bindings),
            "bindings": {
                cid: {
                    "case_id": b.case_id,
                    "requirement_ref": b.requirement_ref,
                    "pipeline_run_id": b.pipeline_run_id,
                    "execution": b.execution,
                    "coverage_tags": b.coverage_tags,
                    "created_at": b.created_at,
                }
                for cid, b in self._bindings.items()
            },
        }
        with open(bindings_path, "w", encoding="utf-8") as f:
            json.dump(bindings_data, f, ensure_ascii=False, indent=2)
        paths["bindings"] = bindings_path

        # 2. 覆盖率矩阵
        coverage_path = os.path.join(output_dir, "coverage_matrix.json")
        matrix = self.compute_coverage_matrix()
        coverage_data = {
            "generated_at": datetime.now().isoformat(),
            "matrix": [
                {
                    "module": e.module,
                    "total_cases": e.total_cases,
                    "executed": e.executed,
                    "passed": e.passed,
                    "failed": e.failed,
                    "coverage_rate": round(e.coverage_rate, 4),
                    "pass_rate": round(e.pass_rate, 4),
                }
                for e in matrix
            ],
        }
        with open(coverage_path, "w", encoding="utf-8") as f:
            json.dump(coverage_data, f, ensure_ascii=False, indent=2)
        paths["coverage"] = coverage_path

        # 3. 会话记忆
        if self._session:
            session_path = os.path.join(output_dir, "session_memory.json")
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self._session.session_id,
                    "started_at": self._session.started_at,
                    "last_active_at": self._session.last_active_at,
                    "variables": self._session.variables,
                    "history_count": len(self._session.history),
                    "history": self._session.history[-50:],  # 最近50条
                }, f, ensure_ascii=False, indent=2)
            paths["session"] = session_path

        return paths

    # ── 集成 MetricsCollector ──

    def to_metrics_summary(self) -> dict:
        """生成与 MetricsCollector 兼容的摘要"""
        matrix = self.compute_coverage_matrix()
        total = next((e for e in matrix if e.module == "合计"), None)

        return {
            "run_id": self.run_id,
            "total_bindings": len(self._bindings),
            "failed_cases": len(self.get_failed_cases()),
            "coverage": {
                "total_cases": total.total_cases if total else 0,
                "executed": total.executed if total else 0,
                "passed": total.passed if total else 0,
                "failed": total.failed if total else 0,
                "coverage_rate": round(total.coverage_rate, 4) if total else 0,
            },
            "modules_count": len(self._module_cases),
            "session_active": self._session is not None,
        }
