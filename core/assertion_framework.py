"""
assertion_framework.py — 统一断言框架

提供两套互补的断言能力：

1. AssertionFramework — 四层领域断言（状态机/结算/契约/合规）
   用于业务逻辑级别的正确性验证。

2. ExecutionAssertions (AssertionFrameworkHarness) — 三层执行断言（Pre/Realtime/Post）
   用于测试执行流程中的前置/实时/后置检查。

3. UnifiedAssertionEngine — 统一门面，组合两套断言能力。

使用方式:
    from core.assertion_framework import AssertionFramework, ExecutionAssertions, UnifiedAssertionEngine
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, Any, Dict

try:
    import yaml
except ImportError:
    yaml = None

try:
    from core.state_machine import StateMachineEngine, TransitionResult
except ImportError:
    StateMachineEngine = None
    TransitionResult = None

try:
    from core.settlement_calc import SettlementCalculator, CaseData, SettlementResult
except ImportError:
    SettlementCalculator = None

try:
    from core.compliance_checker import ComplianceChecker, ComplianceCaseData, ComplianceReport
except ImportError:
    ComplianceChecker = None

@dataclass
class ContractAssertion:
    """跨系统契约断言定义"""
    system_name: str
    api_pattern: str
    expected_fields: dict
    timeout_ms: int = 10000
    required: bool = True

@dataclass
class LayerResult:
    """单层断言结果"""
    layer: str
    passed: bool = False
    assertions: int = 0
    passed_count: int = 0
    failed_count: int = 0
    details: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def skip(self) -> bool:
        return self.assertions == 0

@dataclass
class AssertionReport:
    """四层断言综合报告"""
    case_id: str = ""
    passed: bool = False
    layers: dict = field(default_factory=dict)
    total_assertions: int = 0
    total_passed: int = 0
    total_failed: int = 0
    duration_ms: int = 0

    def to_summary(self) -> dict:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "total_assertions": self.total_assertions,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "layers": {
                name: {
                    "result": "PASS" if lr.passed else ("SKIP" if lr.skip else "FAIL"),
                    "assertions": lr.assertions,
                    "passed": lr.passed_count,
                }
                for name, lr in self.layers.items()
            },
        }

class AssertionFramework:
    """
    四层断言框架：原创保护专用统一断言引擎。
    """

    def __init__(
        self,
        state_machine_path: str = "",
        contracts_path: str = "",
    ):
        self._sm_engine: Optional[object] = None
        self._settlement_calc = SettlementCalculator() if SettlementCalculator else None
        self._compliance_checker = ComplianceChecker() if ComplianceChecker else None
        self._contracts: list[ContractAssertion] = []

        if state_machine_path and os.path.exists(state_machine_path) and StateMachineEngine:
            self._sm_engine = StateMachineEngine.from_yaml(state_machine_path)

        if contracts_path and os.path.exists(contracts_path):
            self._load_contracts(contracts_path)

    def _load_contracts(self, contracts_path: str):
        """加载跨系统契约定义"""
        if not yaml:
            return
        with open(contracts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for contract in data.get("contracts", []):
            self._contracts.append(ContractAssertion(
                system_name=contract.get("system_name", ""),
                api_pattern=contract.get("api_pattern", ""),
                expected_fields=contract.get("expected_fields", {}),
                timeout_ms=contract.get("timeout_ms", 10000),
                required=contract.get("required", True),
            ))

    # ── Layer 1: 状态机断言 ──

    def assert_state_machine(
        self,
        from_state: str,
        to_state: str,
        context: dict = None,
        actual_side_effects: list = None,
    ) -> LayerResult:
        """执行状态机断言"""
        layer = LayerResult(layer="state_machine")

        if not self._sm_engine:
            layer.errors.append("状态机引擎未初始化")
            return layer

        result = self._sm_engine.validate_transition(
            from_state, to_state, context, actual_side_effects
        )

        layer.assertions = 1
        if result.valid:
            layer.passed_count = 1
            layer.passed = True
            layer.details.append({
                "check": "状态转换合法性",
                "result": "PASS",
                "from": from_state,
                "to": to_state,
                "guard_evaluated": result.guard_evaluated,
            })
        else:
            layer.failed_count = 1
            layer.errors.extend(result.errors)
            layer.details.append({
                "check": "状态转换合法性",
                "result": "FAIL",
                "from": from_state,
                "to": to_state,
                "errors": result.errors,
            })

        if result.warnings:
            layer.details.append({"check": "warnings", "warnings": result.warnings})

        return layer

    def assert_state_sequence(self, transitions_seq: list[dict]) -> LayerResult:
        """执行状态序列断言"""
        layer = LayerResult(layer="state_machine")

        if not self._sm_engine:
            layer.errors.append("状态机引擎未初始化")
            return layer

        results = self._sm_engine.validate_sequence(transitions_seq)
        layer.assertions = len(results)

        for r in results:
            if r.valid:
                layer.passed_count += 1
            else:
                layer.failed_count += 1
                layer.errors.extend(r.errors)

        layer.passed = layer.failed_count == 0
        layer.details = [
            {"from": r.from_state, "to": r.to_state, "valid": r.valid, "errors": r.errors}
            for r in results
        ]
        return layer

    # ── Layer 2: 结算断言 ──

    def assert_settlement(self, case_data) -> LayerResult:
        """执行结算断言"""
        layer = LayerResult(layer="settlement")

        if not self._settlement_calc:
            layer.errors.append("结算计算器未初始化")
            return layer

        checks = []

        # 效果对赌校验
        gamble_result = self._settlement_calc.verify_effect_gamble(case_data)
        checks.append(gamble_result)

        # 原子性校验
        if case_data.charge_record.charge_order_id:
            atomic_result = self._settlement_calc.verify_atomic_deduction(
                case_data.charge_record,
                case_data.application_state,
                case_data.to_regular_status,
            )
            checks.append(atomic_result)

        # 精度校验
        from decimal import Decimal
        precision_result = self._settlement_calc.verify_precision(
            case_data.settlement_record.amount,
            self._settlement_calc.calculate_settlement(
                case_data.contract.service_fee,
                case_data.enforcement_results.takedown_count,
                case_data.enforcement_results.total_count,
            ),
        )
        checks.append(precision_result)

        layer.assertions = len(checks)
        for check in checks:
            if check.passed:
                layer.passed_count += 1
            else:
                layer.failed_count += 1
                layer.errors.append(check.message)
            layer.details.append({
                "check": check.check_type,
                "passed": check.passed,
                "expected": check.expected,
                "actual": check.actual,
                "message": check.message,
            })

        layer.passed = layer.failed_count == 0
        return layer

    # ── Layer 3: 跨系统契约断言 ──

    def assert_cross_system(self, captured_responses: dict) -> LayerResult:
        """跨系统契约断言"""
        layer = LayerResult(layer="cross_system")

        if not self._contracts:
            return layer

        for contract in self._contracts:
            response = captured_responses.get(contract.system_name)
            if response is None:
                if contract.required:
                    layer.assertions += 1
                    layer.failed_count += 1
                    layer.errors.append(f"未捕获到 {contract.system_name} 的响应")
                    layer.details.append({
                        "system": contract.system_name,
                        "result": "MISSING",
                        "required": contract.required,
                    })
                continue

            layer.assertions += 1
            field_errors = self._verify_contract_fields(response, contract.expected_fields)

            if field_errors:
                layer.failed_count += 1
                layer.errors.extend(field_errors)
                layer.details.append({
                    "system": contract.system_name,
                    "result": "FAIL",
                    "errors": field_errors,
                })
            else:
                layer.passed_count += 1
                layer.details.append({
                    "system": contract.system_name,
                    "result": "PASS",
                })

        layer.passed = layer.failed_count == 0
        return layer

    def _verify_contract_fields(self, response: Any, expected_fields: dict) -> list[str]:
        """验证响应中的字段是否符合契约"""
        errors = []
        if not isinstance(response, dict):
            return [f"响应不是字典类型: {type(response)}"]

        for field_path, expected in expected_fields.items():
            actual = self._get_nested_field(response, field_path)
            if actual is None:
                errors.append(f"缺少字段: {field_path}")
                continue

            if isinstance(expected, str) and expected.startswith("type:"):
                expected_type = expected[5:].strip()
                type_map = {
                    "string": str, "str": str,
                    "int": int, "integer": int,
                    "float": float, "number": (int, float),
                    "bool": bool, "boolean": bool,
                    "list": list, "array": list,
                    "dict": dict, "object": dict,
                }
                py_type = type_map.get(expected_type)
                if py_type and not isinstance(actual, py_type):
                    errors.append(
                        f"字段 {field_path} 类型不匹配: 期望 {expected_type}, "
                        f"实际 {type(actual).__name__}"
                    )
            elif actual != expected:
                errors.append(
                    f"字段 {field_path} 值不匹配: 期望 {expected}, 实际 {actual}"
                )

        return errors

    def _get_nested_field(self, data: dict, field_path: str) -> Any:
        """通过点号路径获取嵌套字段"""
        parts = field_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None
            if current is None:
                return None
        return current

    # ── Layer 4: 合规断言 ──

    def assert_compliance(self, case_data) -> LayerResult:
        """执行合规断言"""
        layer = LayerResult(layer="compliance")

        if not self._compliance_checker:
            layer.errors.append("合规检查器未初始化")
            return layer

        report = self._compliance_checker.check_all(case_data)

        layer.assertions = report.total_checks
        layer.passed_count = report.passed_checks
        layer.failed_count = report.failed_checks
        layer.passed = report.passed
        layer.details = [
            {
                "check": r.check_name,
                "passed": r.passed,
                "message": r.message,
                "severity": r.severity,
            }
            for r in report.results
        ]
        layer.errors = [r.message for r in report.results if not r.passed and r.severity == "ERROR"]

        return layer

    # ── 综合执行 ──

    def run_all_assertions(
        self,
        case_id: str = "",
        state_transition: dict = None,
        settlement_case=None,
        captured_responses: dict = None,
        compliance_case=None,
    ) -> AssertionReport:
        """综合执行四层断言"""
        report = AssertionReport(case_id=case_id)

        if state_transition:
            sm_result = self.assert_state_machine(
                from_state=state_transition.get("from", ""),
                to_state=state_transition.get("to", ""),
                context=state_transition.get("context", {}),
                actual_side_effects=state_transition.get("side_effects", []),
            )
            report.layers["state_machine"] = sm_result

        if settlement_case:
            st_result = self.assert_settlement(settlement_case)
            report.layers["settlement"] = st_result

        if captured_responses:
            cs_result = self.assert_cross_system(captured_responses)
            report.layers["cross_system"] = cs_result

        if compliance_case:
            comp_result = self.assert_compliance(compliance_case)
            report.layers["compliance"] = comp_result

        for lr in report.layers.values():
            report.total_assertions += lr.assertions
            report.total_passed += lr.passed_count
            report.total_failed += lr.failed_count

        report.passed = report.total_failed == 0 and report.total_assertions > 0
        return report

# ============================================================
# 三层执行断言子系统（Pre / Realtime / Post）
# 用于测试执行过程中的前置条件、实时校验、后置汇总
# ============================================================

from dataclasses import dataclass, field

@dataclass
class AssertionResult:
    """断言结果"""
    id: str
    pass_: bool
    severity: str
    message: str = ""
    expression: str = ""
    evaluated_value: Any = None
    auto_action: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self):
        d = {"id": self.id, "pass": self.pass_, "severity": self.severity,
             "message": self.message, "expression": self.expression,
             "evaluatedValue": self.evaluated_value}
        if self.auto_action:
            d["autoAction"] = self.auto_action
        if self.error:
            d["error"] = self.error
        return d

def _safe_eval(expression: str, context: Dict[str, Any]) -> Any:
    """安全表达式求值"""
    import re
    expr = expression.strip()
    dangerous = ["import ", "exec(", "eval(", "open(", "os.", "sys.", "__import__",
                 "lambda ", "compile(", "getattr", "setattr", "globals", "locals"]
    for kw in dangerous:
        if kw in expr:
            raise ValueError(f"禁止使用 {kw}")
    expr = _preprocess_expression(expr)
    expr = re.sub(r'(\d+(?:\.\d+)?)%', lambda m: str(float(m.group(1)) / 100.0), expr)
    if len(expr) > 500:
        raise ValueError("表达式长度不得超过 500 字符")
    _safe_globals = {"len": len, "abs": abs, "round": round, "int": int, "float": float,
                     "str": str, "bool": bool, "list": list, "dict": dict, "tuple": tuple,
                     "sum": sum, "min": min, "max": max, "range": range, "enumerate": enumerate,
                     "zip": zip, "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
                     "True": True, "False": False, "None": None}
    _safe_globals["__builtins__"] = {}
    _safe_globals.update(context)
    _safe_globals["_contains"] = _contains
    _safe_globals["_safe_eval"] = _safe_eval
    try:
        return eval(expr, _safe_globals)
    except Exception as e:
        raise ValueError(f"表达式求值失败: {e}")

def _preprocess_expression(expr: str) -> str:
    import re
    expr = re.sub(r'\b(\w+)\s+contains\s+(["\'])(.*?)\2',
                  r'_contains(\1, \2\3\2)', expr)
    expr = re.sub(r'(\d+(?:\.\d+)?)%?\s+of\s+(\w+)',
                  r'\1 / 100.0 * \2', expr)
    return expr

def _validate_expression(expr: str) -> None:
    _safe_eval(expr, {})

def _contains(haystack, needle) -> bool:
    if isinstance(haystack, str):
        return str(needle) in haystack
    elif isinstance(haystack, list):
        return needle in haystack or str(needle) in [str(x) for x in haystack]
    else:
        return False

class AssertionFrameworkHarness:
    """Harness 三层断言框架"""

    def __init__(self):
        self._results = {"pre": [], "realtime": [], "post": []}

    def run_pre_asserts(self, ctx, rules):
        results = []
        if not rules:
            return results
        context = {f"ctx_{k}": v for k, v in ctx.items()}
        for rule in rules:
            rid = rule.get("id", "unknown")
            expr = rule.get("expression", "")
            sev = rule.get("severity", "WARNING")
            msg = rule.get("message", "")
            try:
                val = _safe_eval(expr, context)
                results.append(AssertionResult(
                    id=rid, pass_=bool(val), severity=sev, message=msg,
                    expression=expr, evaluated_value=val))
            except Exception as e:
                results.append(AssertionResult(
                    id=rid, pass_=False, severity=sev, message=msg,
                    expression=expr, error=str(e)))
        self._results["pre"] = results
        return results

    def run_realtime_asserts(self, step_ctx, step_output, rules):
        results = []
        if not rules:
            return results
        context = {}
        context.update({f"step_{k}": v for k, v in step_ctx.items()})
        context.update({f"step_{k}": v for k, v in step_output.items()})
        context["duration_ms"] = step_output.get("duration", 0)
        context["status"] = step_output.get("status", "")
        context["response_code"] = step_output.get("responseCode", 0)
        for rule in rules:
            rid = rule.get("id", "unknown")
            expr = rule.get("expression", "")
            sev = rule.get("severity", "WARNING")
            msg = rule.get("message", "")
            try:
                val = _safe_eval(expr, context)
                results.append(AssertionResult(
                    id=rid, pass_=bool(val), severity=sev, message=msg,
                    expression=expr, evaluated_value=val))
            except Exception as e:
                results.append(AssertionResult(
                    id=rid, pass_=False, severity=sev, message=msg,
                    expression=expr, error=str(e)))
        self._results["realtime"] = results
        return results

    def run_post_asserts(self, output, rules):
        results = []
        if not rules:
            return results
        steps = output.get("steps", [])
        context = {"total_steps": len(steps),
                   "completed_steps": sum(1 for s in steps if s.get("status") == "pass"),
                   "failed_steps": sum(1 for s in steps if s.get("status") == "fail"),
                   "status": output.get("status", "")}
        context.update({f"out_{k}": v for k, v in output.items() if k != "steps"})
        for rule in rules:
            rid = rule.get("id", "unknown")
            expr = rule.get("expression", "")
            sev = rule.get("severity", "WARNING")
            msg = rule.get("message", "")
            try:
                val = _safe_eval(expr, context)
                results.append(AssertionResult(
                    id=rid, pass_=bool(val), severity=sev, message=msg,
                    expression=expr, evaluated_value=val))
            except Exception as e:
                results.append(AssertionResult(
                    id=rid, pass_=False, severity=sev, message=msg,
                    expression=expr, error=str(e)))
        self._results["post"] = results
        return results

    def to_summary(self):
        all_results = self._results["pre"] + self._results["realtime"] + self._results["post"]
        passed = sum(1 for r in all_results if r.pass_)
        failed = sum(1 for r in all_results if not r.pass_)
        return {"total": len(all_results), "passed": passed, "failed": failed,
                "pre": [r.to_dict() for r in self._results["pre"]],
                "realtime": [r.to_dict() for r in self._results["realtime"]],
                "post": [r.to_dict() for r in self._results["post"]]}

    def has_critical_failures(self):
        for layer in self._results.values():
            for r in layer:
                if not r.pass_ and r.severity == "CRITICAL":
                    return True
        return False

    def get_all_results(self):
        return dict(self._results)

    def get_failed_results(self, severity=None):
        failed = []
        for layer in self._results.values():
            for r in layer:
                if not r.pass_:
                    if severity is None or r.severity == severity:
                        failed.append(r)
        return failed

    def run_all_assertions(self, **kwargs):
        pre_rules = kwargs.get("pre_rules", [])
        realtime_rules = kwargs.get("realtime_rules", [])
        post_rules = kwargs.get("post_rules", [])
        ctx = kwargs.get("ctx", {})
        step_ctx = kwargs.get("step_ctx", {})
        step_output = kwargs.get("step_output", {})
        output = kwargs.get("output", {})
        self.run_pre_asserts(ctx, pre_rules)
        self.run_realtime_asserts(step_ctx, step_output, realtime_rules)
        self.run_post_asserts(output, post_rules)
        return self.to_summary()

# ============================================================
# 统一门面 & 别名
# ============================================================

# 清晰别名（推荐新代码使用）
ExecutionAssertions = AssertionFrameworkHarness

class UnifiedAssertionEngine:
    """统一断言引擎：组合四层领域断言 + 三层执行断言"""

    def __init__(self, state_machine_path=None, contracts=None):
        self.domain = AssertionFramework(
            state_machine_path=state_machine_path,
            contracts=contracts or []
        )
        self.execution = AssertionFrameworkHarness()

    def run_domain_assertions(self, case_data: dict) -> 'AssertionReport':
        """运行四层领域断言"""
        return self.domain.run_all_assertions(case_data)

    def run_execution_assertions(self, **kwargs) -> dict:
        """运行三层执行断言"""
        return self.execution.run_all_assertions(**kwargs)

    def run_all(self, case_data: dict = None, execution_kwargs: dict = None) -> dict:
        """一次性运行全部断言"""
        result = {"domain": None, "execution": None, "passed": True}

        if case_data:
            domain_report = self.run_domain_assertions(case_data)
            result["domain"] = domain_report.to_summary()
            if not domain_report.passed:
                result["passed"] = False

        if execution_kwargs:
            exec_summary = self.run_execution_assertions(**execution_kwargs)
            result["execution"] = exec_summary
            if exec_summary.get("failed", 0) > 0:
                result["passed"] = False

        return result

# ============================================================
# 断言工具函数（一期三件套共用）
# ============================================================

import re as _re

# SQL 只读检查的禁用关键字（大写匹配）
_SQL_FORBIDDEN_KEYWORDS = (
    "DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE",
    "INSERT", "UPDATE", "DELETE", "MERGE",
    "CREATE", "EXEC", "EXECUTE",
)

# 允许 SQL 注释与字符串字面量之外的危险模式（如 SELECT ... INTO OUTFILE）
_SQL_FORBIDDEN_PATTERNS = [
    _re.compile(r'\bINTO\s+(OUTFILE|DUMPFILE)\b', _re.IGNORECASE),
    _re.compile(r';\s*(?:DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|EXEC)\b', _re.IGNORECASE),
]


def _strip_sql_strings_and_comments(sql: str) -> str:
    """剥离 SQL 字符串字面量与注释，避免误判 SELECT 'delete' FROM t 为 DML。"""
    # 剥离块注释 /* ... */
    sql = _re.sub(r'/\*.*?\*/', ' ', sql, flags=_re.DOTALL)
    # 剥离行注释 -- ...
    sql = _re.sub(r'--[^\n]*', ' ', sql)
    # 剥离单引号字符串（支持 '' 转义）
    sql = _re.sub(r"'(?:''|[^'])*'", "'__STR__'", sql)
    # 剥离双引号标识符（支持 "" 转义）
    sql = _re.sub(r'"(?:""|[^"])*"', '"__ID__"', sql)
    return sql


def check_sql_readonly(sql: str) -> None:
    """
    检查 SQL 是否只读（仅允许 SELECT）。
    命中禁用关键字或模式时抛出 ValueError。
    """
    if not sql or not sql.strip():
        raise ValueError("SQL 不能为空")
    if len(sql) > 4000:
        raise ValueError("SQL 长度不得超过 4000 字符")

    stripped = _strip_sql_strings_and_comments(sql)
    upper = stripped.upper()

    # 必须以 SELECT 或 WITH 开头（允许前置空白和括号）
    first_token = _re.search(r'\b\w+\b', stripped)
    if not first_token:
        raise ValueError("SQL 无法解析")
    if first_token.group(0).upper() not in ("SELECT", "WITH", "EXPLAIN"):
        raise ValueError(
            f"仅允许 SELECT/WITH/EXPLAIN，实际首关键字: {first_token.group(0)}"
        )

    for kw in _SQL_FORBIDDEN_KEYWORDS:
        # 单词边界匹配，避免误判 SELECTED 为 SELECT + ED
        if _re.search(rf'\b{kw}\b', upper):
            raise ValueError(f"SQL 包含禁用关键字: {kw}")

    for pat in _SQL_FORBIDDEN_PATTERNS:
        if pat.search(stripped):
            raise ValueError(f"SQL 命中禁用模式: {pat.pattern}")


class _JsonPathMissingSentinel:
    """jsonPath 缺失哨兵：与 None 区分，便于错误报告。"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<JSON_PATH_MISSING>"

    def __str__(self):
        return "<JSON_PATH_MISSING>"

    def __bool__(self):
        return False


_JSON_PATH_MISSING = _JsonPathMissingSentinel()


def resolve_json_path(data, path: str):
    """
    按点号路径提取嵌套字段（支持 $.foo.bar.0.name 与 foo.bar 两种写法）。
    列表索引使用纯数字段；缺失字段返回 _MISSING 哨兵（非 None），
    便于区分「字段不存在」与「字段值为 None」。
    """
    if not path:
        return data
    parts = path.strip().split(".")
    if parts and parts[0] == "$":
        parts = parts[1:]
    current = data
    for part in parts:
        if current is None or current is _JSON_PATH_MISSING:
            return _JSON_PATH_MISSING
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return _JSON_PATH_MISSING
        elif isinstance(current, list):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return _JSON_PATH_MISSING
            elif part == "*":
                return current
            else:
                return _JSON_PATH_MISSING
        else:
            return _JSON_PATH_MISSING
    return current


def assert_value(actual, *, equals=_JSON_PATH_MISSING, contains=None,
                 matches=None, value_type=None) -> tuple:
    """
    通用值断言（供 assertAPI / dbAssert / 未来扩展使用）。
    返回 (passed: bool, failures: list[str])。
    所有断言条件全部检查，累积失败不短路。
    """
    failures = []

    if equals is not _JSON_PATH_MISSING:
        if actual != equals:
            failures.append(
                f"equals: 期望 {json.dumps(equals, ensure_ascii=False)} "
                f"实际 {json.dumps(actual, ensure_ascii=False)}"
            )

    if contains is not None:
        try:
            haystack = json.dumps(actual, ensure_ascii=False) if not isinstance(actual, str) else actual
        except Exception:
            haystack = str(actual)
        if contains not in haystack:
            failures.append(f"contains: 期望包含 {contains!r}，实际未找到")

    if matches is not None:
        try:
            haystack = json.dumps(actual, ensure_ascii=False) if not isinstance(actual, str) else actual
        except Exception:
            haystack = str(actual)
        try:
            if not _re.search(matches, haystack):
                failures.append(f"matches: 正则 {matches!r} 未命中")
        except _re.error as e:
            failures.append(f"matches: 正则编译失败 {e}")

    if value_type is not None:
        type_map = {
            "string": str, "str": str,
            "number": (int, float), "int": int, "integer": int, "float": float,
            "boolean": bool, "bool": bool,
            "array": list, "list": list,
            "object": dict, "dict": dict,
            "null": type(None),
        }
        expected = type_map.get(value_type)
        if expected is None:
            failures.append(f"valueType: 不支持的类型 {value_type!r}")
        elif not isinstance(actual, expected):
            failures.append(
                f"valueType: 期望 {value_type} 实际 {type(actual).__name__}"
            )

    return (len(failures) == 0, failures)


__all__ = [
    "AssertionFramework",
    "AssertionFrameworkHarness",
    "ExecutionAssertions",
    "UnifiedAssertionEngine",
    "AssertionResult",
    "AssertionReport",
    "LayerResult",
    "ContractAssertion",
    "check_sql_readonly",
    "resolve_json_path",
    "assert_value",
    "_JSON_PATH_MISSING",
]
