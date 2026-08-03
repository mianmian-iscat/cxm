"""
acceptance_report.py — 质量验收 SOP 对齐报告生成器

来源：智能运营场景质量验收SOP（钉钉文档）
三阶段验收标准：
    1. 工具交付阶段 — 工具调用成功率 / 工具结果正确性 / 工具响应时长
    2. Agent交付阶段 — 任务完成率 / 任务响应时长 / 工具结果一致性
    3. 产品交付阶段 — 权限控制 / 内容合规 + 场景功能用例

报告输出格式对齐 SOP 中的"产出报告内容"表格结构，
可直接粘贴到钉钉文档或作为验收邮件正文。

使用方式：
    from core.acceptance_report import AcceptanceReportGenerator

    generator = AcceptanceReportGenerator(run_id="xxx")
    generator.add_tool_result("商品流入流出宽表", success_rate=1.0, consistency="一致", avg_rt_ms=45000)
    generator.add_agent_result(completion_rate=0.98, avg_duration_s=600, consistency_rate=0.98)
    generator.add_product_result(permission_ok=True, compliance_ok=True, case_pass_rate=0.95)
    report = generator.generate()
    # report.markdown  — Markdown 格式报告
    # report.to_dict() — 结构化数据
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


# ── SOP 通用标准定义 ──

TOOL_STANDARDS = {
    "success_rate": {
        "name": "工具调用成功率",
        "definition": "接口响应成功且数据查询成功非空",
        "formula": "调用次数中成功/总调用次数（各场景入参枚举×多次调用）",
        "threshold": 0.95,
    },
    "result_correctness": {
        "name": "工具结果正确性",
        "definition": "有参考数据：参考对比数据源验证；无参考数据：列举指标值，业务方核验",
        "formula": "数据结果一致性",
        "threshold": None,  # 定性判断
    },
    "response_time": {
        "name": "工具响应时长",
        "definition": "工具多次调用的平均响应RT",
        "formula": "1天:≤1min / 7天:≤3min / 30天:≤4min",
        "threshold_ms": {"1d": 60000, "7d": 180000, "30d": 240000},
    },
}

AGENT_STANDARDS = {
    "completion_rate": {
        "name": "任务完成率",
        "definition": "任务输出最终结论，无异常中断",
        "formula": "调用次数中完成/总调用次数（各场景入参枚举×多次调用）",
        "threshold": 0.95,
    },
    "response_time": {
        "name": "任务响应时长",
        "definition": "任务从发起到结束的整体时长",
        "formula": "分场景基线",
        "threshold_s": 600,  # 默认 10min
    },
    "result_consistency": {
        "name": "工具结果一致性",
        "definition": "生成结果中的内容全部和工具调用的结果相关，无编造的数据和内容",
        "formula": "一致性样本数/总样本数",
        "threshold": 0.95,
    },
}

PRODUCT_STANDARDS = {
    "permission_control": {
        "name": "权限控制",
        "definition": "工程层面、Agent层面、工具层面完整进行权限控制，无数据安全风险",
    },
    "content_compliance": {
        "name": "内容合规",
        "definition": "内容符合法律法规、伦理规范，无有害信息或潜在风险",
    },
}


@dataclass
class ToolAcceptanceResult:
    """工具验收结果"""
    tool_name: str
    total_calls: int = 0
    success_calls: int = 0
    consistency: str = ""          # "一致" / "不一致" / "待业务方核验"
    consistency_detail: str = ""   # 对比范围说明
    avg_rt_ms: int = 0
    rt_scope: str = "1d"           # 1d / 7d / 30d
    sample_range: str = ""         # 抽样范围说明

    @property
    def success_rate(self) -> float:
        return self.success_calls / max(self.total_calls, 1)

    @property
    def rt_passed(self) -> bool:
        threshold = TOOL_STANDARDS["response_time"]["threshold_ms"].get(self.rt_scope, 60000)
        return self.avg_rt_ms <= threshold

    @property
    def passed(self) -> bool:
        rate_ok = self.success_rate >= TOOL_STANDARDS["success_rate"]["threshold"]
        consistency_ok = self.consistency in ("一致", "待业务方核验", "")
        return rate_ok and consistency_ok and self.rt_passed


@dataclass
class AgentAcceptanceResult:
    """Agent 验收结果"""
    total_tasks: int = 0
    completed_tasks: int = 0
    avg_duration_s: int = 0
    consistency_total: int = 0
    consistency_passed: int = 0
    scenario_standards: Dict[str, Any] = field(default_factory=dict)  # 场景标准（PRD评审后三方确认）

    @property
    def completion_rate(self) -> float:
        return self.completed_tasks / max(self.total_tasks, 1)

    @property
    def consistency_rate(self) -> float:
        return self.consistency_passed / max(self.consistency_total, 1)

    @property
    def duration_passed(self) -> bool:
        return self.avg_duration_s <= AGENT_STANDARDS["response_time"]["threshold_s"]

    @property
    def passed(self) -> bool:
        return (
            self.completion_rate >= AGENT_STANDARDS["completion_rate"]["threshold"]
            and self.duration_passed
            and self.consistency_rate >= AGENT_STANDARDS["result_consistency"]["threshold"]
        )


@dataclass
class ProductAcceptanceResult:
    """产品验收结果"""
    permission_ok: bool = True
    compliance_ok: bool = True
    case_total: int = 0
    case_passed: int = 0
    tester: str = ""
    notes: str = ""

    @property
    def case_pass_rate(self) -> float:
        return self.case_passed / max(self.case_total, 1)

    @property
    def passed(self) -> bool:
        return self.permission_ok and self.compliance_ok


class AcceptanceReportGenerator:
    """
    质量验收 SOP 对齐报告生成器。

    按 SOP 三阶段（工具→Agent→产品）组织验收数据，
    输出符合团队验收标准的结构化报告。
    """

    def __init__(self, run_id: str = "", requirement_id: str = "", tester: str = ""):
        self.run_id = run_id
        self.requirement_id = requirement_id
        self.tester = tester
        self._tool_results: List[ToolAcceptanceResult] = []
        self._agent_result: Optional[AgentAcceptanceResult] = None
        self._product_result: Optional[ProductAcceptanceResult] = None
        self._evidence_items: List[Dict[str, Any]] = []
        self._created_at = datetime.now(timezone.utc)

    # ── 数据录入 ──

    def add_tool_result(
        self,
        tool_name: str,
        total_calls: int = 0,
        success_calls: int = 0,
        consistency: str = "",
        consistency_detail: str = "",
        avg_rt_ms: int = 0,
        rt_scope: str = "1d",
        sample_range: str = "",
    ):
        """添加工具验收结果"""
        self._tool_results.append(ToolAcceptanceResult(
            tool_name=tool_name, total_calls=total_calls, success_calls=success_calls,
            consistency=consistency, consistency_detail=consistency_detail,
            avg_rt_ms=avg_rt_ms, rt_scope=rt_scope, sample_range=sample_range,
        ))

    def add_agent_result(
        self,
        total_tasks: int = 0,
        completed_tasks: int = 0,
        avg_duration_s: int = 0,
        consistency_total: int = 0,
        consistency_passed: int = 0,
        scenario_standards: Optional[dict] = None,
    ):
        """添加 Agent 验收结果"""
        self._agent_result = AgentAcceptanceResult(
            total_tasks=total_tasks, completed_tasks=completed_tasks,
            avg_duration_s=avg_duration_s,
            consistency_total=consistency_total, consistency_passed=consistency_passed,
            scenario_standards=scenario_standards or {},
        )

    def add_product_result(
        self,
        permission_ok: bool = True,
        compliance_ok: bool = True,
        case_total: int = 0,
        case_passed: int = 0,
        notes: str = "",
    ):
        """添加产品验收结果"""
        self._product_result = ProductAcceptanceResult(
            permission_ok=permission_ok, compliance_ok=compliance_ok,
            case_total=case_total, case_passed=case_passed,
            tester=self.tester, notes=notes,
        )

    def add_evidence(
        self,
        evidence_type: str,
        path: str = "",
        label: str = "",
        detail: str = "",
        stage: str = "",
    ):
        """添加证据链条目。

        evidence_type: screenshot / network_capture / sls_log / data_snapshot / video
        path: 文件路径或 URL
        label: 简短描述
        detail: 补充信息（如接口状态码、日志关键词等）
        stage: 关联的执行阶段
        """
        self._evidence_items.append({
            "type": evidence_type,
            "path": path,
            "label": label,
            "detail": detail,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_evidence_from_output(self, output: dict):
        """从执行 output 自动提取证据链（截图、抓包、录屏等）"""
        artifacts = output.get("artifacts", {})
        # 截图
        if artifacts.get("screenshotPath"):
            self.add_evidence("screenshot", path=artifacts["screenshotPath"], label="执行截图", stage="finalize")
        # 录屏
        if artifacts.get("videoPath"):
            self.add_evidence("video", path=artifacts["videoPath"], label="执行录屏", stage="full")
        # 抓包
        for req in output.get("capture", {}).get("requests", [])[:5]:
            self.add_evidence(
                "network_capture",
                path=req.get("url", ""),
                label=f"{req.get('method', 'GET')} {req.get('url', '').split('?')[0].split('/')[-1]}",
                detail=f"status={req.get('status', 0)}, rt={req.get('durationMs', 0)}ms",
                stage="capture",
            )
        # HAR 文件
        if output.get("capture", {}).get("harPath"):
            self.add_evidence("network_capture", path=output["capture"]["harPath"], label="HAR 完整抓包", stage="capture")
        # Evidence Store
        if artifacts.get("evidencePath"):
            self.add_evidence("data_snapshot", path=artifacts["evidencePath"], label="证据链 JSON", stage="finalize")
        # 契约校验结果
        if output.get("contractVerification"):
            cv = output["contractVerification"]
            self.add_evidence(
                "data_snapshot",
                label=f"五契约校验 {cv.get('passed_checks', 0)}/{cv.get('total_checks', 0)}",
                detail=f"passed={cv.get('passed', False)}, compliance={cv.get('compliance_rate', 0):.0%}",
                stage="finalize",
            )
        # 双因子裁决
        if output.get("dualFactorVerdict"):
            df = output["dualFactorVerdict"]
            self.add_evidence(
                "data_snapshot",
                label=f"双因子裁决 level={df.get('release_level', '?')}",
                detail=f"blocked={df.get('blocked', False)}, skip_rate={df.get('skip_rate', 0):.0%}",
                stage="finalize",
            )

    # ── 报告生成 ──

    def generate(self) -> "AcceptanceReport":
        """生成完整验收报告"""
        tool_passed = all(t.passed for t in self._tool_results) if self._tool_results else None
        agent_passed = self._agent_result.passed if self._agent_result else None
        product_passed = self._product_result.passed if self._product_result else None

        # 总体结论
        stages = [p for p in [tool_passed, agent_passed, product_passed] if p is not None]
        overall = all(stages) if stages else False

        return AcceptanceReport(
            run_id=self.run_id,
            requirement_id=self.requirement_id,
            tester=self.tester,
            created_at=self._created_at.isoformat(),
            overall_passed=overall,
            tool_results=self._tool_results,
            tool_passed=tool_passed,
            agent_result=self._agent_result,
            agent_passed=agent_passed,
            product_result=self._product_result,
            product_passed=product_passed,
            evidence_items=self._evidence_items,
        )


class AcceptanceReport:
    """验收报告实体：结构化数据 + Markdown 渲染"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        """结构化输出"""
        result = {
            "run_id": self.run_id,
            "requirement_id": self.requirement_id,
            "tester": self.tester,
            "created_at": self.created_at,
            "overall_passed": self.overall_passed,
            "stages": {},
        }

        if self.tool_results:
            result["stages"]["tool"] = {
                "passed": self.tool_passed,
                "tools": [
                    {
                        "name": t.tool_name,
                        "success_rate": f"{t.success_rate:.0%}",
                        "consistency": t.consistency or "—",
                        "avg_rt": f"{t.avg_rt_ms}ms",
                        "passed": t.passed,
                    }
                    for t in self.tool_results
                ],
            }

        if self.agent_result:
            a = self.agent_result
            result["stages"]["agent"] = {
                "passed": self.agent_passed,
                "completion_rate": f"{a.completion_rate:.0%}",
                "avg_duration": f"{a.avg_duration_s}s",
                "consistency_rate": f"{a.consistency_rate:.0%}",
            }

        if self.product_result:
            p = self.product_result
            result["stages"]["product"] = {
                "passed": self.product_passed,
                "permission_ok": p.permission_ok,
                "compliance_ok": p.compliance_ok,
                "case_pass_rate": f"{p.case_pass_rate:.0%}",
            }

        # 证据链
        if getattr(self, 'evidence_items', None):
            result["evidence_chain"] = self.evidence_items

        return result

    @property
    def markdown(self) -> str:
        """Markdown 格式报告（对齐 SOP 产出报告内容表格）"""
        lines = [
            f"# 质量验收报告",
            f"",
            f"- **需求ID**: {self.requirement_id or '—'}",
            f"- **执行ID**: {self.run_id or '—'}",
            f"- **测试人**: {self.tester or '—'}",
            f"- **生成时间**: {self.created_at}",
            f"- **总体结论**: {'✅ 通过' if self.overall_passed else '❌ 不通过'}",
            f"",
        ]

        # ── 工具验收 ──
        if self.tool_results:
            lines.extend([
                f"## 一、工具验收 {'✅' if self.tool_passed else '❌'}",
                f"",
                f"| 工具 | 指标 | 测试结果 |",
                f"|------|------|----------|",
            ])
            for t in self.tool_results:
                lines.append(f"| {t.tool_name} | 调用成功率 | {t.success_rate:.0%} ({t.success_calls}/{t.total_calls}) |")
                lines.append(f"|  | 数据一致性 | {t.consistency or '—'}{('（' + t.consistency_detail + '）') if t.consistency_detail else ''} |")
                rt_threshold = TOOL_STANDARDS['response_time']['threshold_ms'].get(t.rt_scope, 60000)
                lines.append(f"|  | 调用耗时 | {t.avg_rt_ms}ms（阈值 {rt_threshold}ms, {t.rt_scope}）{'✅' if t.rt_passed else '❌'} |")
            lines.append("")

        # ── Agent 验收 ──
        if self.agent_result:
            a = self.agent_result
            lines.extend([
                f"## 二、Agent 验收 {'✅' if self.agent_passed else '❌'}",
                f"",
                f"| 标准 | 评测集 | 评测结果 |",
                f"|------|--------|----------|",
                f"| 任务完成率 | 完成定义：任务输出最终结论，无异常中断 | {a.completion_rate:.0%} ({a.completed_tasks}/{a.total_tasks}) |",
                f"| 任务响应时长 | 任务从发起到结束的整体时长 | {a.avg_duration_s}s（阈值 {AGENT_STANDARDS['response_time']['threshold_s']}s）|",
                f"| 工具结果一致性 | 生成结果全部和工具调用结果相关，无编造数据 | {a.consistency_rate:.0%} ({a.consistency_passed}/{a.consistency_total}) |",
            ])
            if a.scenario_standards:
                lines.append(f"")
                lines.append(f"**场景标准**（PRD评审后 PD/算法/测试三方确认）：")
                for k, v in a.scenario_standards.items():
                    lines.append(f"- {k}: {v}")
            lines.append("")

        # ── 产品验收 ──
        if self.product_result:
            p = self.product_result
            lines.extend([
                f"## 三、产品验收 {'✅' if self.product_passed else '❌'}",
                f"",
                f"| 标准 | 衡量方式 | 结果 |",
                f"|------|----------|------|",
                f"| 权限控制 | 工程/Agent/工具层面完整权限控制，无数据安全风险 | {'✅' if p.permission_ok else '❌'} |",
                f"| 内容合规 | 内容符合法律法规、伦理规范，无有害信息 | {'✅' if p.compliance_ok else '❌'} |",
                f"| 功能用例 | 场景负责测试产出用例，执行后输出功能测试结论 | {p.case_pass_rate:.0%} ({p.case_passed}/{p.case_total}) |",
            ])
            if p.notes:
                lines.extend([f"", f"**备注**: {p.notes}"])
            lines.append("")

        # ── 证据链 ──
        evidence = getattr(self, 'evidence_items', None) or []
        if evidence:
            _TYPE_ICON = {
                "screenshot": "🖼️",
                "video": "🎥",
                "network_capture": "📡",
                "sls_log": "📝",
                "data_snapshot": "📦",
            }
            lines.extend([
                f"## 四、证据链",
                f"",
                f"| # | 类型 | 说明 | 详情 | 阶段 |",
                f"|---|------|------|------|------|",
            ])
            for i, ev in enumerate(evidence, 1):
                icon = _TYPE_ICON.get(ev.get("type", ""), "📎")
                path_str = f"`{ev['path']}`" if ev.get("path") else "—"
                lines.append(
                    f"| {i} | {icon} {ev.get('type', '')} | {ev.get('label', '')} | {ev.get('detail', '') or path_str} | {ev.get('stage', '')} |"
                )
            lines.append("")

        return "\n".join(lines)
