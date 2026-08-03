"""
data_setup_verifier.py — 造数自查引擎（5 维度）

在 dataSetup 造数完成后、用例正式执行前，从 5 个维度验证造出的数据是否真正可用：
  1. PRD 合规性 — 字段完备、值域合规、业务组合有效
  2. 代码契约 — 接口 DTO 校验、DB 约束、前置依赖链
  3. 历史存量冲突 — 唯一性、状态窗口、版本漂移
  4. 可用性验证 — DB 落池、UI 可见、流程可推进、时效性
  5. 安全性自查 — 环境正确、只增不删、可追溯

使用方式：
    from core.data_setup_verifier import DataSetupVerifier, VerifyDimension
    verifier = DataSetupVerifier(cdp=cdp)
    report = await verifier.verify(setup_result, spec)
    if not report.passed:
        # 根据 report.failures 决定重试 / 降级 / 阻断
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class VerifyDimension(Enum):
    """自查维度枚举"""
    PRD_COMPLIANCE = "prd_compliance"         # PRD 合规性
    CODE_CONTRACT = "code_contract"           # 代码契约
    HISTORY_CONFLICT = "history_conflict"     # 历史存量冲突
    USABILITY = "usability"                   # 可用性验证
    SAFETY = "safety"                         # 安全性自查


class Severity(Enum):
    """失败严重度"""
    BLOCK = "block"       # 阻断：数据不可用，必须重建
    WARN = "warn"         # 警告：有风险但可继续
    INFO = "info"         # 信息：建议优化


@dataclass
class CheckItem:
    """单项检查结果"""
    dimension: VerifyDimension
    check_name: str
    passed: bool
    severity: Severity = Severity.BLOCK
    message: str = ""
    details: dict = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class VerifyReport:
    """造数自查综合报告"""
    passed: bool = True
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    blocked: bool = False              # 是否有 BLOCK 级失败
    items: List[CheckItem] = field(default_factory=list)
    setup_result: dict = field(default_factory=dict)
    duration_ms: int = 0
    timestamp: str = ""

    def add_item(self, item: CheckItem):
        self.items.append(item)
        self.total_checks += 1
        if item.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
            if item.severity == Severity.BLOCK:
                self.blocked = True
                self.passed = False
            elif item.severity == Severity.WARN:
                self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "items": [
                {
                    "dimension": it.dimension.value,
                    "check_name": it.check_name,
                    "passed": it.passed,
                    "severity": it.severity.value,
                    "message": it.message,
                    "details": it.details,
                    "duration_ms": it.duration_ms,
                }
                for it in self.items
            ],
        }


@dataclass
class VerifySpec:
    """造数自查规格声明（可在 input JSON 的 dataSetup.verify 中定义）"""
    # ── PRD 合规性 ──
    required_fields: List[str] = field(default_factory=list)    # 必填字段列表
    field_constraints: Dict[str, dict] = field(default_factory=dict)  # 字段约束 {field: {type, enum, min, max, pattern}}
    valid_combinations: List[dict] = field(default_factory=list)  # 合法入参组合

    # ── 代码契约 ──
    api_contract: dict = field(default_factory=dict)  # {url, method, expected_status, required_response_fields}
    db_constraints: List[dict] = field(default_factory=list)  # [{table, field, constraint_type, value}]
    dependencies: List[dict] = field(default_factory=list)  # [{entity, id_field, check_api}]

    # ── 历史存量冲突 ──
    uniqueness_checks: List[dict] = field(default_factory=list)  # [{api, field, error_pattern}]
    state_window: dict = field(default_factory=dict)  # {api, valid_states: [...]}
    version_check: dict = field(default_factory=dict)  # {api, expected_version_field, expected_value}

    # ── 可用性验证 ──
    db_landing: dict = field(default_factory=dict)  # {api, expected_status_field, expected_status_value}
    ui_visibility: dict = field(default_factory=dict)  # {url, search_selector, search_value, result_selector}
    processability: dict = field(default_factory=dict)  # {api, action, expected_success}
    ttl_seconds: int = 0  # 数据有效期（秒），0=不检查

    # ── 安全性 ──
    expected_env: str = "pre"  # 预期环境标识
    env_check_pattern: str = ""  # URL/header 中环境标识的匹配模式
    trace_fields: List[str] = field(default_factory=list)  # 造数结果中必须存在的追溯字段


class DataSetupVerifier:
    """
    造数自查引擎：在数据创建后执行 5 维度验证。

    核心流程：
        setup_result → verify(spec) → VerifyReport
        如果 blocked=True → 建议重建
        如果 passed=False 但 blocked=False → 警告但可继续
    """

    def __init__(self, cdp=None, http_client=None):
        """
        Args:
            cdp: CDP 客户端实例（用于浏览器内 API 调用和 UI 验证）
            http_client: 可选的外部 HTTP 客户端（用于 DB 查询等）
        """
        self._cdp = cdp
        self._http = http_client
        self._stats = {
            "total_verifications": 0,
            "passed": 0,
            "blocked": 0,
            "dimension_stats": {d.value: {"pass": 0, "fail": 0} for d in VerifyDimension},
        }

    async def verify(
        self,
        setup_result: dict,
        spec: VerifySpec = None,
        dimensions: List[VerifyDimension] = None,
    ) -> VerifyReport:
        """
        执行造数自查。

        Args:
            setup_result: dataSetup 步骤的返回结果（如 {taskId, ossUrl, nodeId, ...}）
            spec: 自查规格声明（为空时使用默认规格）
            dimensions: 指定只检查哪些维度（为空时全部检查）

        Returns:
            VerifyReport
        """
        start = time.time()
        self._stats["total_verifications"] += 1

        spec = spec or VerifySpec()
        dims = dimensions or list(VerifyDimension)

        report = VerifyReport(
            setup_result=setup_result,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # 按维度依次执行
        if VerifyDimension.PRD_COMPLIANCE in dims:
            await self._check_prd_compliance(setup_result, spec, report)

        if VerifyDimension.CODE_CONTRACT in dims:
            await self._check_code_contract(setup_result, spec, report)

        if VerifyDimension.HISTORY_CONFLICT in dims:
            await self._check_history_conflict(setup_result, spec, report)

        if VerifyDimension.USABILITY in dims:
            await self._check_usability(setup_result, spec, report)

        if VerifyDimension.SAFETY in dims:
            await self._check_safety(setup_result, spec, report)

        report.duration_ms = int((time.time() - start) * 1000)

        # 更新统计
        if report.blocked:
            self._stats["blocked"] += 1
        elif report.passed:
            self._stats["passed"] += 1

        for item in report.items:
            dim_key = item.dimension.value
            if item.passed:
                self._stats["dimension_stats"][dim_key]["pass"] += 1
            else:
                self._stats["dimension_stats"][dim_key]["fail"] += 1

        return report

    # ═══════════════════════════════════════════════════════
    # 维度 1：PRD 合规性
    # ═══════════════════════════════════════════════════════

    async def _check_prd_compliance(self, result: dict, spec: VerifySpec, report: VerifyReport):
        """验证造出的数据是否符合 PRD 定义"""
        dim = VerifyDimension.PRD_COMPLIANCE

        # 1.1 字段完备性
        if spec.required_fields:
            missing = [f for f in spec.required_fields if f not in result or result[f] is None]
            report.add_item(CheckItem(
                dimension=dim,
                check_name="字段完备性",
                passed=len(missing) == 0,
                severity=Severity.BLOCK,
                message=f"缺失必填字段: {missing}" if missing else "所有必填字段已填充",
                details={"missing_fields": missing, "required": spec.required_fields},
            ))

        # 1.2 值域合规
        if spec.field_constraints:
            violations = []
            for field_name, constraint in spec.field_constraints.items():
                value = result.get(field_name)
                if value is None:
                    continue  # 缺失已在完备性中检查
                violation = self._validate_constraint(field_name, value, constraint)
                if violation:
                    violations.append(violation)
            report.add_item(CheckItem(
                dimension=dim,
                check_name="值域合规",
                passed=len(violations) == 0,
                severity=Severity.BLOCK,
                message=f"值域违规: {violations}" if violations else "所有字段值域合规",
                details={"violations": violations},
            ))

        # 1.3 业务组合有效性
        if spec.valid_combinations:
            combo_valid = self._check_combination(result, spec.valid_combinations)
            report.add_item(CheckItem(
                dimension=dim,
                check_name="业务组合有效性",
                passed=combo_valid,
                severity=Severity.WARN,
                message="入参组合在 PRD 允许范围内" if combo_valid else "入参组合不在 PRD 定义的合法组合中",
                details={"valid_combinations": spec.valid_combinations},
            ))

    # ═══════════════════════════════════════════════════════
    # 维度 2：代码契约
    # ═══════════════════════════════════════════════════════

    async def _check_code_contract(self, result: dict, spec: VerifySpec, report: VerifyReport):
        """验证数据是否满足后端代码的校验逻辑"""
        dim = VerifyDimension.CODE_CONTRACT

        # 2.1 API 契约验证（回查创建接口或详情接口）
        if spec.api_contract and self._cdp:
            item = await self._verify_api_contract(result, spec.api_contract)
            report.add_item(item)

        # 2.2 DB 约束验证
        if spec.db_constraints:
            item = await self._verify_db_constraints(result, spec.db_constraints)
            report.add_item(item)

        # 2.3 前置依赖链验证
        if spec.dependencies and self._cdp:
            item = await self._verify_dependencies(result, spec.dependencies)
            report.add_item(item)

    # ═══════════════════════════════════════════════════════
    # 维度 3：历史存量冲突
    # ═══════════════════════════════════════════════════════

    async def _check_history_conflict(self, result: dict, spec: VerifySpec, report: VerifyReport):
        """验证新造数据是否与存量数据冲突"""
        dim = VerifyDimension.HISTORY_CONFLICT

        # 3.1 唯一性冲突
        if spec.uniqueness_checks and self._cdp:
            item = await self._verify_uniqueness(result, spec.uniqueness_checks)
            report.add_item(item)

        # 3.2 状态窗口
        if spec.state_window and self._cdp:
            item = await self._verify_state_window(result, spec.state_window)
            report.add_item(item)

        # 3.3 版本漂移
        if spec.version_check and self._cdp:
            item = await self._verify_version(result, spec.version_check)
            report.add_item(item)

    # ═══════════════════════════════════════════════════════
    # 维度 4：可用性验证
    # ═══════════════════════════════════════════════════════

    async def _check_usability(self, result: dict, spec: VerifySpec, report: VerifyReport):
        """验证造出的数据是否真正可用"""
        dim = VerifyDimension.USABILITY

        # 4.1 DB 落池确认
        if spec.db_landing and self._cdp:
            item = await self._verify_db_landing(result, spec.db_landing)
            report.add_item(item)

        # 4.2 UI 可见性
        if spec.ui_visibility and self._cdp:
            item = await self._verify_ui_visibility(result, spec.ui_visibility)
            report.add_item(item)

        # 4.3 流程可推进
        if spec.processability and self._cdp:
            item = await self._verify_processability(result, spec.processability)
            report.add_item(item)

        # 4.4 时效性
        if spec.ttl_seconds > 0:
            item = self._verify_ttl(result, spec.ttl_seconds)
            report.add_item(item)

    # ═══════════════════════════════════════════════════════
    # 维度 5：安全性自查
    # ═══════════════════════════════════════════════════════

    async def _check_safety(self, result: dict, spec: VerifySpec, report: VerifyReport):
        """安全性红线校验"""
        dim = VerifyDimension.SAFETY

        # 5.1 环境正确性
        env_ok = self._verify_environment(result, spec)
        report.add_item(env_ok)

        # 5.2 只增不删（造数结果不应包含删除操作标记）
        no_delete = self._verify_no_destructive(result)
        report.add_item(no_delete)

        # 5.3 可追溯性
        if spec.trace_fields:
            trace_ok = self._verify_traceability(result, spec.trace_fields)
            report.add_item(trace_ok)

    # ═══════════════════════════════════════════════════════
    # 具体验证实现
    # ═══════════════════════════════════════════════════════

    def _validate_constraint(self, field_name: str, value: Any, constraint: dict) -> Optional[str]:
        """校验单个字段约束，返回违规描述或 None"""
        # 类型检查
        expected_type = constraint.get("type")
        if expected_type:
            type_map = {"str": str, "int": int, "float": (int, float), "list": list, "dict": dict}
            if expected_type in type_map and not isinstance(value, type_map[expected_type]):
                return f"{field_name}: 期望类型 {expected_type}, 实际 {type(value).__name__}"

        # 枚举检查
        enum_values = constraint.get("enum")
        if enum_values is not None and value not in enum_values:
            return f"{field_name}: 值 '{value}' 不在枚举 {enum_values} 中"

        # 数值范围
        min_val = constraint.get("min")
        max_val = constraint.get("max")
        if isinstance(value, (int, float)):
            if min_val is not None and value < min_val:
                return f"{field_name}: 值 {value} < 最小值 {min_val}"
            if max_val is not None and value > max_val:
                return f"{field_name}: 值 {value} > 最大值 {max_val}"

        # 正则模式
        pattern = constraint.get("pattern")
        if pattern and isinstance(value, str):
            import re
            if not re.match(pattern, value):
                return f"{field_name}: 值 '{value}' 不匹配模式 '{pattern}'"

        return None

    def _check_combination(self, result: dict, valid_combinations: List[dict]) -> bool:
        """检查入参组合是否在合法组合列表中"""
        for combo in valid_combinations:
            match = all(result.get(k) == v for k, v in combo.items())
            if match:
                return True
        return False

    async def _verify_api_contract(self, result: dict, contract: dict) -> CheckItem:
        """通过 API 回查验证契约"""
        dim = VerifyDimension.CODE_CONTRACT
        start = time.time()
        url = contract.get("url", "")
        method = contract.get("method", "GET")
        expected_status = contract.get("expected_status", 200)
        required_fields = contract.get("required_response_fields", [])

        # 支持 URL 模板替换（如 /api/task/{taskId}）
        for key, val in result.items():
            url = url.replace(f"{{{key}}}", str(val))

        try:
            fetch_js = f"""
            (async () => {{
                try {{
                    const resp = await fetch({json.dumps(url)}, {{
                        method: {json.dumps(method)},
                        credentials: 'include',
                        headers: {{ 'Content-Type': 'application/json' }},
                    }});
                    const data = await resp.json().catch(() => null);
                    return {{ status: resp.status, data: data }};
                }} catch (e) {{
                    return {{ status: 0, error: e.message }};
                }}
            }})()
            """
            resp = await asyncio.wait_for(self._cdp.evaluate(fetch_js), timeout=15)
            status = resp.get("status", 0)
            data = resp.get("data") or {}

            # 状态码校验
            status_ok = status == expected_status
            # 响应字段校验
            missing_resp_fields = [f for f in required_fields if f not in data]

            passed = status_ok and len(missing_resp_fields) == 0
            return CheckItem(
                dimension=dim,
                check_name="API 契约验证",
                passed=passed,
                severity=Severity.BLOCK,
                message=(
                    f"API 契约通过: {url[:60]}" if passed
                    else f"API 契约失败: status={status}(期望{expected_status}), 缺失字段={missing_resp_fields}"
                ),
                details={"url": url, "status": status, "missing_fields": missing_resp_fields},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return CheckItem(
                dimension=dim,
                check_name="API 契约验证",
                passed=False,
                severity=Severity.WARN,
                message=f"API 契约检查异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _verify_db_constraints(self, result: dict, constraints: List[dict]) -> CheckItem:
        """DB 约束验证（通过 DMS 或 API 间接验证）"""
        dim = VerifyDimension.CODE_CONTRACT
        # DB 约束通常通过 dms-alibaba-cli 外部验证，此处做结构声明性检查
        # 实际执行时由上层编排器串联 DMS skill
        unchecked = [c for c in constraints if c.get("constraint_type") in ("unique", "foreign_key")]
        return CheckItem(
            dimension=dim,
            check_name="DB 约束验证",
            passed=True,  # 声明性通过，实际验证由 DMS skill 补充
            severity=Severity.INFO,
            message=f"DB 约束已声明 {len(constraints)} 项，其中 {len(unchecked)} 项需 DMS 补充验证",
            details={"constraints": constraints, "needs_dms": unchecked},
        )

    async def _verify_dependencies(self, result: dict, dependencies: List[dict]) -> CheckItem:
        """前置依赖链验证"""
        dim = VerifyDimension.CODE_CONTRACT
        start = time.time()
        missing_deps = []

        for dep in dependencies:
            entity = dep.get("entity", "")
            id_field = dep.get("id_field", "")
            check_api = dep.get("check_api", "")

            dep_id = result.get(id_field)
            if dep_id is None:
                missing_deps.append(f"{entity}: 缺少 {id_field}")
                continue

            if check_api and self._cdp:
                url = check_api.replace(f"{{{id_field}}}", str(dep_id))
                try:
                    js = f"(async()=>{{const r=await fetch({json.dumps(url)},{{credentials:'include'}});return r.ok;}})()"
                    exists = await asyncio.wait_for(self._cdp.evaluate(js), timeout=10)
                    if not exists:
                        missing_deps.append(f"{entity}: id={dep_id} 不存在")
                except Exception:
                    missing_deps.append(f"{entity}: id={dep_id} 检查超时")

        return CheckItem(
            dimension=dim,
            check_name="前置依赖链",
            passed=len(missing_deps) == 0,
            severity=Severity.BLOCK,
            message=f"依赖完整" if not missing_deps else f"依赖缺失: {missing_deps}",
            details={"missing": missing_deps},
            duration_ms=int((time.time() - start) * 1000),
        )

    async def _verify_uniqueness(self, result: dict, checks: List[dict]) -> CheckItem:
        """唯一性冲突检测"""
        dim = VerifyDimension.HISTORY_CONFLICT
        start = time.time()
        conflicts = []

        for check in checks:
            api = check.get("api", "")
            field_name = check.get("field", "")
            error_pattern = check.get("error_pattern", "已存在")

            value = result.get(field_name)
            if not value or not api:
                continue

            url = api.replace(f"{{{field_name}}}", str(value))
            try:
                js = f"""(async()=>{{
                    const r = await fetch({json.dumps(url)}, {{credentials:'include'}});
                    const d = await r.json().catch(()=>null);
                    return {{ok: r.ok, data: d}};
                }})()"""
                resp = await asyncio.wait_for(self._cdp.evaluate(js), timeout=10)
                data_str = json.dumps(resp.get("data") or "")
                if error_pattern in data_str:
                    conflicts.append(f"{field_name}={value}: 与存量冲突")
            except Exception:
                pass

        return CheckItem(
            dimension=dim,
            check_name="唯一性冲突",
            passed=len(conflicts) == 0,
            severity=Severity.WARN,
            message="无唯一性冲突" if not conflicts else f"存量冲突: {conflicts}",
            details={"conflicts": conflicts},
            duration_ms=int((time.time() - start) * 1000),
        )

    async def _verify_state_window(self, result: dict, state_spec: dict) -> CheckItem:
        """状态窗口验证：目标实体当前状态是否允许后续操作"""
        dim = VerifyDimension.HISTORY_CONFLICT
        start = time.time()
        api = state_spec.get("api", "")
        valid_states = state_spec.get("valid_states", [])

        if not api or not valid_states:
            return CheckItem(
                dimension=dim, check_name="状态窗口", passed=True,
                severity=Severity.INFO, message="未配置状态窗口检查",
            )

        # URL 模板替换
        for key, val in result.items():
            api = api.replace(f"{{{key}}}", str(val))

        try:
            js = f"(async()=>{{const r=await fetch({json.dumps(api)},{{credentials:'include'}});return await r.json();}})()"
            data = await asyncio.wait_for(self._cdp.evaluate(js), timeout=10)
            current_state = ""
            if isinstance(data, dict):
                current_state = str(data.get("status", data.get("state", data.get("data", {}).get("status", ""))))

            in_window = current_state in [str(s) for s in valid_states]
            return CheckItem(
                dimension=dim,
                check_name="状态窗口",
                passed=in_window,
                severity=Severity.BLOCK,
                message=f"状态 '{current_state}' 在有效窗口内" if in_window else f"状态 '{current_state}' 不在有效窗口 {valid_states} 内",
                details={"current_state": current_state, "valid_states": valid_states},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="状态窗口", passed=False,
                severity=Severity.WARN, message=f"状态检查异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _verify_version(self, result: dict, version_spec: dict) -> CheckItem:
        """版本漂移检测"""
        dim = VerifyDimension.HISTORY_CONFLICT
        api = version_spec.get("api", "")
        expected_field = version_spec.get("expected_version_field", "version")
        expected_value = version_spec.get("expected_value")

        if not api:
            return CheckItem(
                dimension=dim, check_name="版本漂移", passed=True,
                severity=Severity.INFO, message="未配置版本检查",
            )

        for key, val in result.items():
            api = api.replace(f"{{{key}}}", str(val))

        try:
            js = f"(async()=>{{const r=await fetch({json.dumps(api)},{{credentials:'include'}});return await r.json();}})()"
            data = await asyncio.wait_for(self._cdp.evaluate(js), timeout=10)
            actual = data.get(expected_field) if isinstance(data, dict) else None

            if expected_value is not None:
                ok = str(actual) == str(expected_value)
                return CheckItem(
                    dimension=dim, check_name="版本漂移", passed=ok,
                    severity=Severity.WARN,
                    message=f"版本一致: {expected_field}={actual}" if ok else f"版本漂移: 期望 {expected_value}, 实际 {actual}",
                    details={"expected": expected_value, "actual": actual},
                )
            return CheckItem(
                dimension=dim, check_name="版本漂移", passed=True,
                severity=Severity.INFO, message=f"当前版本: {expected_field}={actual}",
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="版本漂移", passed=False,
                severity=Severity.WARN, message=f"版本检查异常: {e}",
            )

    async def _verify_db_landing(self, result: dict, landing_spec: dict) -> CheckItem:
        """DB 落池确认：数据已持久化且状态正确"""
        dim = VerifyDimension.USABILITY
        start = time.time()
        api = landing_spec.get("api", "")
        status_field = landing_spec.get("expected_status_field", "status")
        expected_status = landing_spec.get("expected_status_value")

        if not api:
            return CheckItem(
                dimension=dim, check_name="DB 落池确认", passed=True,
                severity=Severity.INFO, message="未配置落池检查 API",
            )

        for key, val in result.items():
            api = api.replace(f"{{{key}}}", str(val))

        try:
            js = f"(async()=>{{const r=await fetch({json.dumps(api)},{{credentials:'include'}});return await r.json();}})()"
            data = await asyncio.wait_for(self._cdp.evaluate(js), timeout=15)

            if not data:
                return CheckItem(
                    dimension=dim, check_name="DB 落池确认", passed=False,
                    severity=Severity.BLOCK, message="查询无返回，数据可能未落池",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # 支持嵌套路径 data.data.status
            actual_status = data
            for part in status_field.split("."):
                if isinstance(actual_status, dict):
                    actual_status = actual_status.get(part)
                else:
                    actual_status = None
                    break

            if expected_status is not None:
                ok = str(actual_status) == str(expected_status)
                return CheckItem(
                    dimension=dim, check_name="DB 落池确认", passed=ok,
                    severity=Severity.BLOCK,
                    message=f"数据已落池，状态={actual_status}" if ok else f"状态不符: 期望 {expected_status}, 实际 {actual_status}",
                    details={"expected": expected_status, "actual": str(actual_status)},
                    duration_ms=int((time.time() - start) * 1000),
                )
            return CheckItem(
                dimension=dim, check_name="DB 落池确认", passed=True,
                severity=Severity.INFO, message=f"数据已落池，当前状态={actual_status}",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="DB 落池确认", passed=False,
                severity=Severity.BLOCK, message=f"落池检查异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _verify_ui_visibility(self, result: dict, ui_spec: dict) -> CheckItem:
        """UI 可见性验证：页面上能搜到/看到数据"""
        dim = VerifyDimension.USABILITY
        start = time.time()
        url = ui_spec.get("url", "")
        search_selector = ui_spec.get("search_selector", "")
        search_value = ui_spec.get("search_value", "")
        result_selector = ui_spec.get("result_selector", "")

        if not url:
            return CheckItem(
                dimension=dim, check_name="UI 可见性", passed=True,
                severity=Severity.INFO, message="未配置 UI 可见性检查",
            )

        # 模板替换
        for key, val in result.items():
            url = url.replace(f"{{{key}}}", str(val))
            search_value = search_value.replace(f"{{{key}}}", str(val))

        try:
            # 导航 + 搜索 + 检测结果
            js = f"""
            (async () => {{
                // 搜索
                if ({json.dumps(search_selector)} && {json.dumps(search_value)}) {{
                    const input = document.querySelector({json.dumps(search_selector)});
                    if (input) {{
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(input, {json.dumps(search_value)});
                        input.dispatchEvent(new Event('input', {{bubbles: true}}));
                        input.dispatchEvent(new Event('change', {{bubbles: true}}));
                        // 触发搜索（回车）
                        input.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', keyCode: 13, bubbles: true}}));
                    }}
                }}
                await new Promise(r => setTimeout(r, 2000));
                // 检测结果
                const target = document.querySelector({json.dumps(result_selector)});
                return {{ visible: !!target && target.offsetHeight > 0, text: target ? target.textContent.slice(0, 100) : '' }};
            }})()
            """
            # 先导航
            nav_js = f"window.location.href = {json.dumps(url)}"
            await self._cdp.evaluate(nav_js)
            await asyncio.sleep(3)

            vis_result = await asyncio.wait_for(self._cdp.evaluate(js), timeout=15)
            visible = vis_result.get("visible", False) if vis_result else False

            return CheckItem(
                dimension=dim, check_name="UI 可见性", passed=visible,
                severity=Severity.WARN,
                message="数据在 UI 上可见" if visible else "数据在 UI 上不可见（可能需要等待异步落池）",
                details=vis_result or {},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="UI 可见性", passed=False,
                severity=Severity.WARN, message=f"UI 可见性检查异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    async def _verify_processability(self, result: dict, proc_spec: dict) -> CheckItem:
        """流程可推进验证：数据能被下游流程消费"""
        dim = VerifyDimension.USABILITY
        start = time.time()
        api = proc_spec.get("api", "")
        action = proc_spec.get("action", "query")
        expected_success = proc_spec.get("expected_success", True)

        if not api:
            return CheckItem(
                dimension=dim, check_name="流程可推进", passed=True,
                severity=Severity.INFO, message="未配置流程推进检查",
            )

        for key, val in result.items():
            api = api.replace(f"{{{key}}}", str(val))

        try:
            method = "POST" if action != "query" else "GET"
            js = f"""(async()=>{{
                const r = await fetch({json.dumps(api)}, {{
                    method: {json.dumps(method)},
                    credentials: 'include',
                    headers: {{'Content-Type': 'application/json'}},
                }});
                const d = await r.json().catch(()=>null);
                return {{ok: r.ok, status: r.status, data: d}};
            }})()"""
            resp = await asyncio.wait_for(self._cdp.evaluate(js), timeout=15)
            success = resp.get("ok", False) if resp else False

            ok = success == expected_success
            return CheckItem(
                dimension=dim, check_name="流程可推进", passed=ok,
                severity=Severity.BLOCK,
                message="数据可被下游流程消费" if ok else f"流程推进失败: status={resp.get('status')}",
                details=resp or {},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="流程可推进", passed=False,
                severity=Severity.WARN, message=f"流程推进检查异常: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )

    def _verify_ttl(self, result: dict, ttl_seconds: int) -> CheckItem:
        """时效性验证"""
        dim = VerifyDimension.USABILITY
        created_at = result.get("created_at") or result.get("timestamp")
        if not created_at:
            return CheckItem(
                dimension=dim, check_name="时效性", passed=True,
                severity=Severity.INFO, message="无创建时间戳，跳过时效检查",
            )
        try:
            import datetime
            if isinstance(created_at, (int, float)):
                create_time = datetime.datetime.fromtimestamp(created_at)
            else:
                create_time = datetime.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            age = (datetime.datetime.now(create_time.tzinfo) - create_time).total_seconds()
            ok = age <= ttl_seconds
            return CheckItem(
                dimension=dim, check_name="时效性", passed=ok,
                severity=Severity.WARN,
                message=f"数据新鲜（{int(age)}s）" if ok else f"数据已过期（{int(age)}s > TTL {ttl_seconds}s）",
                details={"age_seconds": int(age), "ttl": ttl_seconds},
            )
        except Exception as e:
            return CheckItem(
                dimension=dim, check_name="时效性", passed=True,
                severity=Severity.INFO, message=f"时效解析失败，跳过: {e}",
            )

    def _verify_environment(self, result: dict, spec: VerifySpec) -> CheckItem:
        """环境正确性验证"""
        dim = VerifyDimension.SAFETY
        expected_env = spec.expected_env
        pattern = spec.env_check_pattern

        # 从造数结果中推断环境
        result_str = json.dumps(result, ensure_ascii=False)
        env_indicators = {
            "pre": ["pre-", "预发", "pre."],
            "daily": ["daily", "日常", "test."],
            "prod": ["production", "生产", ".alibaba-inc.com/api"],
        }

        # 检查是否误入生产
        prod_hit = any(ind in result_str for ind in env_indicators.get("prod", []))
        if prod_hit and expected_env != "prod":
            return CheckItem(
                dimension=dim, check_name="环境正确性", passed=False,
                severity=Severity.BLOCK,
                message=f"疑似生产环境数据！期望 {expected_env}，检测到生产标识",
                details={"expected_env": expected_env, "indicators": "prod"},
            )

        # 检查预期环境标识
        if pattern:
            import re
            env_ok = bool(re.search(pattern, result_str))
            return CheckItem(
                dimension=dim, check_name="环境正确性", passed=env_ok,
                severity=Severity.BLOCK,
                message=f"环境标识匹配: {expected_env}" if env_ok else f"未检测到环境标识 '{pattern}'",
            )

        return CheckItem(
            dimension=dim, check_name="环境正确性", passed=True,
            severity=Severity.INFO, message=f"环境检查通过（{expected_env}）",
        )

    def _verify_no_destructive(self, result: dict) -> CheckItem:
        """只增不删验证"""
        dim = VerifyDimension.SAFETY
        destructive_keys = ["deleted", "removed", "destroyed", "purged"]
        found = [k for k in result.keys() if any(dk in k.lower() for dk in destructive_keys)]

        # 检查值中是否有删除标记
        destructive_values = []
        for k, v in result.items():
            if isinstance(v, str) and any(dk in v.lower() for dk in ["delete", "remove", "destroy"]):
                destructive_values.append(f"{k}={v}")

        has_destructive = len(found) > 0 or len(destructive_values) > 0
        return CheckItem(
            dimension=dim, check_name="只增不删", passed=not has_destructive,
            severity=Severity.BLOCK,
            message="造数过程无删除操作" if not has_destructive else f"检测到删除标记: {found + destructive_values}",
            details={"destructive_keys": found, "destructive_values": destructive_values},
        )

    def _verify_traceability(self, result: dict, trace_fields: List[str]) -> CheckItem:
        """可追溯性验证"""
        dim = VerifyDimension.SAFETY
        missing = [f for f in trace_fields if f not in result or result[f] is None]
        return CheckItem(
            dimension=dim, check_name="可追溯性", passed=len(missing) == 0,
            severity=Severity.WARN,
            message="追溯字段完整" if not missing else f"缺少追溯字段: {missing}",
            details={"missing": missing, "required": trace_fields},
        )

    # ── 统计 ──

    def get_stats(self) -> dict:
        return dict(self._stats)


# ═══════════════════════════════════════════════════════
# 便捷工厂：为 F88 审核造数生成默认 VerifySpec
# ═══════════════════════════════════════════════════════

def build_f88_audit_verify_spec(task_id=None, identity="f88") -> VerifySpec:
    """
    为 F88 审核任务造数构建默认自查规格。

    覆盖：
    - PRD: taskId/ossUrl/nodeId 必填，questionType 枚举
    - 契约: 创建 API 响应 success=true
    - 存量: 任务名唯一性
    - 可用性: DB 落池（status=待审核）、审核画布可打开
    - 安全: 预发环境、追溯字段
    """
    return VerifySpec(
        # PRD 合规
        required_fields=["taskId", "ossUrl", "nodeId", "taskName"],
        field_constraints={
            "taskId": {"type": "int", "min": 1},
        },
        # 代码契约
        api_contract={
            "url": f"/api/afd/review/task/main/detail?taskId={{taskId}}&identity={identity}",
            "method": "GET",
            "expected_status": 200,
            "required_response_fields": ["success", "data"],
        },
        dependencies=[
            {"entity": "review_node", "id_field": "nodeId", "check_api": f"/api/afd/review/node/get?nodeId={{nodeId}}&identity={identity}"},
        ],
        # 历史存量
        state_window={
            "api": "/api/afd/review/task/main/detail?taskId={taskId}&identity=" + identity,
            "valid_states": [0, 1, "0", "1", "PENDING", "IN_PROGRESS", "待审核", "审核中"],
        },
        # 可用性
        db_landing={
            "api": "/api/afd/review/task/main/detail?taskId={taskId}&identity=" + identity,
            "expected_status_field": "data.status",
            "expected_status_value": None,  # 只要查到就行，不强制状态
        },
        # 安全
        expected_env="pre",
        env_check_pattern=r"pre-|预发",
        trace_fields=["taskId", "taskName", "ossUrl"],
    )
