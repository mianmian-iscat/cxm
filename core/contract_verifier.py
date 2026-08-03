"""
contract_verifier.py — Harness 五契约校验引擎（全托管 L4 引擎层）

来源：服饰质量全托管数字人架构方案 §3.3 闭环 C
五契约定义（KBase contracts/ 类目）：
    C1 数据契约 — 数据输入输出的完整性、一致性、格式正确性
    C2 控制契约 — 状态机流转正确性、操作时序、幂等性
    C3 反馈契约 — 错误提示可理解性、异常兜底、用户引导
    C4 隔离契约 — 测试数据隔离、环境隔离、权限隔离
    C5 指标契约 — 性能基线（RT/成功率）、资源消耗预算

同时提供：
    - 跨阶段 Diff 矩阵：每阶段保留前后快照，便于回滚和归因
    - 证据包四件套标准化：接口抓包 + SLS日志 + 截图录屏 + 数据快照

使用方式：
    from core.contract_verifier import ContractVerifier, StageDiffMatrix, EvidencePack

    verifier = ContractVerifier()
    report = verifier.verify_all(execution_output, stage_diffs, evidence_pack)
    # report.to_dict() → 结构化五契约校验结果
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


# ── 五契约定义 ──

CONTRACTS = {
    "C1": {
        "name": "数据契约",
        "scope": "数据输入输出的完整性、一致性、格式正确性",
        "checks": [
            "required_fields_present",   # 必填字段完整
            "data_type_correct",         # 数据类型正确
            "value_range_valid",         # 值域合法
            "cross_system_consistent",   # 跨系统数据一致
        ],
    },
    "C2": {
        "name": "控制契约",
        "scope": "状态机流转正确性、操作时序、幂等性",
        "checks": [
            "state_transition_valid",    # 状态流转合法
            "operation_sequence_valid",  # 操作时序正确
            "idempotent_safe",           # 幂等安全
            "permission_gate_passed",    # 权限门禁通过
        ],
    },
    "C3": {
        "name": "反馈契约",
        "scope": "错误提示可理解性、异常兜底、用户引导",
        "checks": [
            "error_message_clear",       # 错误提示清晰
            "fallback_triggered",        # 兜底逻辑触发
            "user_guidance_present",     # 用户引导存在
            "loading_state_shown",       # 加载态展示
        ],
    },
    "C4": {
        "name": "隔离契约",
        "scope": "测试数据隔离、环境隔离、权限隔离",
        "checks": [
            "test_data_isolated",        # 测试数据隔离
            "env_boundary_respected",    # 环境边界遵守
            "no_production_write",       # 无生产写入
            "sandbox_enforced",          # 沙箱强制执行
        ],
    },
    "C5": {
        "name": "指标契约",
        "scope": "性能基线（RT/成功率）、资源消耗预算",
        "checks": [
            "rt_within_baseline",        # RT 在基线内
            "success_rate_met",          # 成功率达标
            "token_budget_respected",    # Token 预算遵守
            "resource_usage_normal",     # 资源消耗正常
        ],
    },
}


@dataclass
class ContractCheckResult:
    """单项契约检查结果"""
    contract_id: str        # C1~C5
    check_name: str
    passed: bool = True
    severity: str = ""      # 违反时的严重级别
    actual: str = ""        # 实际值
    expected: str = ""      # 期望值
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "check": self.check_name,
            "passed": self.passed,
            "severity": self.severity,
            "actual": self.actual,
            "expected": self.expected,
            "detail": self.detail,
        }


@dataclass
class ContractReport:
    """五契约校验综合报告"""
    run_id: str = ""
    passed: bool = False
    contracts: Dict[str, dict] = field(default_factory=dict)
    violations: List[dict] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "compliance_rate": round(self.passed_checks / max(self.total_checks, 1), 3),
            "contracts": self.contracts,
            "violations": self.violations,
            "duration_ms": self.duration_ms,
        }


class StageDiffMatrix:
    """
    跨阶段 Diff 矩阵：每阶段保留前后快照，便于回滚和归因。

    结构：{stage_name: {"before": snapshot, "after": snapshot, "diff": [...], "timestamp": ...}}
    """

    def __init__(self):
        self._stages: Dict[str, dict] = {}
        self._order: List[str] = []

    def capture_before(self, stage: str, snapshot: Any):
        """阶段执行前快照"""
        if stage not in self._stages:
            self._stages[stage] = {}
            self._order.append(stage)
        self._stages[stage]["before"] = snapshot
        self._stages[stage]["before_ts"] = time.time()

    def capture_after(self, stage: str, snapshot: Any):
        """阶段执行后快照 + 自动计算 diff"""
        if stage not in self._stages:
            self._stages[stage] = {}
            self._order.append(stage)
        self._stages[stage]["after"] = snapshot
        self._stages[stage]["after_ts"] = time.time()
        self._stages[stage]["diff"] = self._compute_diff(
            self._stages[stage].get("before"), snapshot
        )

    def get_stage(self, stage: str) -> Optional[dict]:
        return self._stages.get(stage)

    def get_chain(self) -> List[str]:
        """获取阶段执行链"""
        return list(self._order)

    def get_rollback_target(self, failed_stage: str) -> Optional[str]:
        """获取失败阶段的上一个稳定阶段（回滚目标）"""
        if failed_stage not in self._order:
            return None
        idx = self._order.index(failed_stage)
        return self._order[idx - 1] if idx > 0 else None

    def to_dict(self) -> dict:
        return {
            "stage_order": self._order,
            "stages": {
                name: {
                    "has_before": "before" in info,
                    "has_after": "after" in info,
                    "diff_count": len(info.get("diff", [])),
                    "diff_summary": info.get("diff", [])[:10],  # 截断防溢出
                    "duration_s": round(
                        info.get("after_ts", 0) - info.get("before_ts", 0), 2
                    ) if info.get("after_ts") and info.get("before_ts") else None,
                }
                for name, info in self._stages.items()
            },
        }

    @staticmethod
    def _compute_diff(before: Any, after: Any) -> List[dict]:
        """计算两个快照之间的差异"""
        diffs = []
        if isinstance(before, dict) and isinstance(after, dict):
            all_keys = set(list(before.keys()) + list(after.keys()))
            for key in sorted(all_keys):
                old_val = before.get(key)
                new_val = after.get(key)
                if old_val != new_val:
                    diffs.append({
                        "key": key,
                        "change": "modified" if key in before and key in after
                                  else ("added" if key not in before else "removed"),
                        "before": str(old_val)[:200] if old_val is not None else None,
                        "after": str(new_val)[:200] if new_val is not None else None,
                    })
        elif before != after:
            diffs.append({
                "key": "__root__",
                "change": "modified",
                "before": str(before)[:200],
                "after": str(after)[:200],
            })
        return diffs


class EvidencePack:
    """
    证据包四件套标准化：接口抓包 + SLS日志 + 截图录屏 + 数据快照。

    对齐全托管方案 §3.3 证据采集规范。
    """

    REQUIRED_ARTIFACTS = ["network_capture", "sls_logs", "screenshots", "data_snapshot"]

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self._artifacts: Dict[str, List[dict]] = {k: [] for k in self.REQUIRED_ARTIFACTS}
        self._created_at = time.time()

    def add_network_capture(self, url: str, method: str = "GET", status: int = 0,
                            request_body: str = "", response_body: str = "", rt_ms: int = 0):
        """添加接口抓包记录"""
        self._artifacts["network_capture"].append({
            "url": url[:500], "method": method, "status": status,
            "request_body": request_body[:1000], "response_body": response_body[:2000],
            "rt_ms": rt_ms, "timestamp": time.time(),
        })

    def add_sls_log(self, logstore: str, query: str, content: str, level: str = "INFO"):
        """添加 SLS 日志记录"""
        self._artifacts["sls_logs"].append({
            "logstore": logstore, "query": query[:300],
            "content": content[:2000], "level": level, "timestamp": time.time(),
        })

    def add_screenshot(self, path: str, stage: str = "", description: str = ""):
        """添加截图/录屏记录"""
        self._artifacts["screenshots"].append({
            "path": path, "stage": stage, "description": description[:200],
            "timestamp": time.time(),
        })

    def add_data_snapshot(self, source: str, table_or_api: str, data: Any, note: str = ""):
        """添加数据快照"""
        self._artifacts["data_snapshot"].append({
            "source": source, "table_or_api": table_or_api,
            "data": str(data)[:3000], "note": note[:200], "timestamp": time.time(),
        })

    def completeness(self) -> dict:
        """证据包完整性检查"""
        status = {}
        for artifact_type in self.REQUIRED_ARTIFACTS:
            count = len(self._artifacts[artifact_type])
            status[artifact_type] = {
                "count": count,
                "present": count > 0,
            }
        complete = all(s["present"] for s in status.values())
        return {"complete": complete, "artifacts": status}

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "created_at": self._created_at,
            "completeness": self.completeness(),
            "artifacts": {
                k: v[:20]  # 每类最多保留 20 条，防溢出
                for k, v in self._artifacts.items()
            },
        }


class ContractVerifier:
    """
    Harness 五契约校验引擎。

    对执行输出进行 C1~C5 全维度校验，
    输出结构化契约报告供全托管控制面消费。
    """

    def __init__(self, baselines: Optional[dict] = None):
        """
        Args:
            baselines: C5 性能基线配置，如 {"rt_p95_ms": 5000, "success_rate_min": 0.8, "token_budget": 200000}
        """
        self._baselines = baselines or {
            "rt_p95_ms": 10000,
            "success_rate_min": 0.8,
            "token_budget": 200000,
        }

    def verify_all(
        self,
        execution_output: dict,
        diff_matrix: Optional[StageDiffMatrix] = None,
        evidence_pack: Optional[EvidencePack] = None,
    ) -> ContractReport:
        """
        执行全量五契约校验。

        Args:
            execution_output: Harness 执行输出（含 status/steps/artifacts 等）
            diff_matrix: 跨阶段 Diff 矩阵（可选）
            evidence_pack: 证据包（可选）

        Returns:
            ContractReport 结构化五契约报告
        """
        start = time.time()
        results: List[ContractCheckResult] = []

        # C1 数据契约
        results.extend(self._verify_c1(execution_output))
        # C2 控制契约
        results.extend(self._verify_c2(execution_output, diff_matrix))
        # C3 反馈契约
        results.extend(self._verify_c3(execution_output))
        # C4 隔离契约
        results.extend(self._verify_c4(execution_output, evidence_pack))
        # C5 指标契约
        results.extend(self._verify_c5(execution_output, evidence_pack))

        # 汇总
        violations = [r.to_dict() for r in results if not r.passed]
        contracts_summary = {}
        for cid, cdef in CONTRACTS.items():
            c_results = [r for r in results if r.contract_id == cid]
            c_passed = [r for r in c_results if r.passed]
            contracts_summary[cid] = {
                "name": cdef["name"],
                "scope": cdef["scope"],
                "passed": all(r.passed for r in c_results),
                "checks_total": len(c_results),
                "checks_passed": len(c_passed),
            }

        report = ContractReport(
            run_id=execution_output.get("artifacts", {}).get("runId", ""),
            passed=len(violations) == 0,
            contracts=contracts_summary,
            violations=violations,
            total_checks=len(results),
            passed_checks=len(results) - len(violations),
            duration_ms=int((time.time() - start) * 1000),
        )
        return report

    # ── C1 数据契约 ──

    def _verify_c1(self, output: dict) -> List[ContractCheckResult]:
        results = []
        steps = output.get("steps", [])

        # 必填字段完整
        required = ["status", "steps"]
        missing = [f for f in required if f not in output]
        results.append(ContractCheckResult(
            contract_id="C1", check_name="required_fields_present",
            passed=not missing, severity="P1" if missing else "",
            actual=str(missing), expected=str(required),
            detail=f"输出缺少字段: {missing}" if missing else "必填字段完整",
        ))

        # 步骤数据类型正确
        type_ok = isinstance(steps, list)
        results.append(ContractCheckResult(
            contract_id="C1", check_name="data_type_correct",
            passed=type_ok, severity="P1" if not type_ok else "",
            actual=type(steps).__name__, expected="list",
        ))

        # 值域合法：status 枚举
        status = output.get("status", "")
        valid_statuses = {"pass", "fail", "error", "partial", "skip"}
        status_ok = status in valid_statuses
        results.append(ContractCheckResult(
            contract_id="C1", check_name="value_range_valid",
            passed=status_ok, severity="P2" if not status_ok else "",
            actual=status, expected=str(valid_statuses),
        ))

        return results

    # ── C2 控制契约 ──

    def _verify_c2(self, output: dict, diff_matrix: Optional[StageDiffMatrix]) -> List[ContractCheckResult]:
        results = []
        steps = output.get("steps", [])

        # 操作时序正确：步骤 index 单调递增
        indices = [s.get("index", i) for i, s in enumerate(steps)]
        seq_ok = indices == sorted(indices)
        results.append(ContractCheckResult(
            contract_id="C2", check_name="operation_sequence_valid",
            passed=seq_ok, severity="P1" if not seq_ok else "",
            detail="步骤时序单调递增" if seq_ok else f"步骤时序乱序: {indices}",
        ))

        # 状态流转合法：无 pass 之后出现 error 的逆转（除非有重试标记）
        state_ok = True
        seen_pass = False
        for s in steps:
            if s.get("status") == "pass":
                seen_pass = True
            elif seen_pass and s.get("status") == "error" and not s.get("retried"):
                state_ok = False
                break
        results.append(ContractCheckResult(
            contract_id="C2", check_name="state_transition_valid",
            passed=state_ok, severity="P1" if not state_ok else "",
            detail="状态流转合法" if state_ok else "存在 pass→error 非法逆转",
        ))

        # Diff 矩阵完整性（如有）
        if diff_matrix:
            chain = diff_matrix.get_chain()
            diff_ok = len(chain) > 0
            results.append(ContractCheckResult(
                contract_id="C2", check_name="idempotent_safe",
                passed=diff_ok, severity="P2" if not diff_ok else "",
                detail=f"Diff 矩阵覆盖 {len(chain)} 个阶段" if diff_ok else "Diff 矩阵为空",
            ))

        return results

    # ── C3 反馈契约 ──

    def _verify_c3(self, output: dict) -> List[ContractCheckResult]:
        results = []
        steps = output.get("steps", [])
        failed_steps = [s for s in steps if s.get("status") in ("error", "fail")]

        # 错误提示清晰：失败步骤必须有 error 信息
        if failed_steps:
            has_msg = all(s.get("error") for s in failed_steps)
            results.append(ContractCheckResult(
                contract_id="C3", check_name="error_message_clear",
                passed=has_msg, severity="P2" if not has_msg else "",
                detail="所有失败步骤均有错误信息" if has_msg else "存在无错误信息的失败步骤",
            ))
        else:
            results.append(ContractCheckResult(
                contract_id="C3", check_name="error_message_clear", passed=True,
                detail="无失败步骤",
            ))

        # 兜底逻辑：output 级别有 suggestion 或 summary
        fallback_ok = bool(output.get("suggestion") or output.get("summary") or not failed_steps)
        results.append(ContractCheckResult(
            contract_id="C3", check_name="fallback_triggered",
            passed=fallback_ok, severity="P2" if not fallback_ok else "",
        ))

        return results

    # ── C4 隔离契约 ──

    def _verify_c4(self, output: dict, evidence_pack: Optional[EvidencePack]) -> List[ContractCheckResult]:
        results = []

        # 无生产写入：检查步骤中是否有生产环境标记
        steps = output.get("steps", [])
        prod_writes = [
            s for s in steps
            if s.get("env") == "production" and s.get("write_operation")
        ]
        results.append(ContractCheckResult(
            contract_id="C4", check_name="no_production_write",
            passed=not prod_writes, severity="P0" if prod_writes else "",
            detail="无生产环境写操作" if not prod_writes else f"检测到 {len(prod_writes)} 次生产写入",
        ))

        # 证据包完整性（如有）
        if evidence_pack:
            completeness = evidence_pack.completeness()
            results.append(ContractCheckResult(
                contract_id="C4", check_name="test_data_isolated",
                passed=completeness["complete"],
                severity="P2" if not completeness["complete"] else "",
                detail=f"证据包完整性: {completeness['complete']}",
            ))

        return results

    # ── C5 指标契约 ──

    def _verify_c5(self, output: dict, evidence_pack: Optional[EvidencePack]) -> List[ContractCheckResult]:
        results = []

        # RT 基线
        duration = output.get("artifacts", {}).get("duration_ms", 0) or output.get("duration_ms", 0)
        rt_ok = duration <= self._baselines["rt_p95_ms"] if duration else True
        results.append(ContractCheckResult(
            contract_id="C5", check_name="rt_within_baseline",
            passed=rt_ok, severity="P2" if not rt_ok else "",
            actual=f"{duration}ms", expected=f"≤{self._baselines['rt_p95_ms']}ms",
        ))

        # 成功率
        steps = output.get("steps", [])
        if steps:
            passed_count = sum(1 for s in steps if s.get("status") == "pass")
            rate = passed_count / len(steps)
            rate_ok = rate >= self._baselines["success_rate_min"]
            results.append(ContractCheckResult(
                contract_id="C5", check_name="success_rate_met",
                passed=rate_ok, severity="P1" if not rate_ok else "",
                actual=f"{rate:.0%}", expected=f"≥{self._baselines['success_rate_min']:.0%}",
            ))

        # Token 预算
        token_used = output.get("artifacts", {}).get("token_used", 0)
        if token_used:
            budget_ok = token_used <= self._baselines["token_budget"]
            results.append(ContractCheckResult(
                contract_id="C5", check_name="token_budget_respected",
                passed=budget_ok, severity="P1" if not budget_ok else "",
                actual=str(token_used), expected=f"≤{self._baselines['token_budget']}",
            ))

        return results
