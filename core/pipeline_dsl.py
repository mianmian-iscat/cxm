"""
pipeline_dsl.py — Pipeline DSL 解析器

原创保护 Harness 执行引擎：
- 解析 Pipeline YAML（含 state_machine 原生支持）
- 步骤依赖解析（depends_on DAG）
- 变量绑定和输出提取（output_binding）
- 条件执行（condition）
- 错误处理和回滚策略（rollback_and_report）
- 与 impl.py 的 run_test 对接

使用方式:
    from core.pipeline_dsl import PipelineEngine
    engine = PipelineEngine.from_yaml("harness/pipelines/to_regular_full_flow.yaml")
    result = await engine.execute(context={"test_merchant_id": "M001"})
"""

import re
import yaml
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from collections import defaultdict

@dataclass
class PipelineStep:
    """Pipeline 步骤定义"""
    id: str
    tool: str
    params: dict = field(default_factory=dict)
    depends_on: list = field(default_factory=list)
    output_binding: dict = field(default_factory=dict)
    condition: str = ""
    on_error: str = ""            # fail / skip / rollback
    retry: dict = field(default_factory=dict)  # max_retries, backoff_ms

@dataclass
class PipelineDefinition:
    """Pipeline 定义"""
    name: str
    version: str = "1.0"
    description: str = ""
    trigger: dict = field(default_factory=dict)
    state_machine: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    error_handling: dict = field(default_factory=dict)
    cleanup: list = field(default_factory=list)

@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    status: str = "pending"       # pending / running / pass / fail / skip / rolled_back
    output: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    retries: int = 0

@dataclass
class PipelineResult:
    """Pipeline 执行结果"""
    pipeline_name: str = ""
    status: str = "pending"       # pending / running / pass / fail / partial / rolled_back
    step_results: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    duration_ms: int = 0
    errors: list = field(default_factory=list)
    rollbacks_executed: list = field(default_factory=list)

    def to_summary(self) -> dict:
        passed = sum(1 for r in self.step_results.values() if r.status == "pass")
        failed = sum(1 for r in self.step_results.values() if r.status == "fail")
        skipped = sum(1 for r in self.step_results.values() if r.status == "skip")
        return {
            "pipeline": self.pipeline_name,
            "status": self.status,
            "steps_total": len(self.step_results),
            "steps_passed": passed,
            "steps_failed": failed,
            "steps_skipped": skipped,
            "duration_ms": self.duration_ms,
        }

class PipelineEngine:
    """
    Pipeline DSL 解析与执行引擎。

    支持:
    - YAML Pipeline 定义解析
    - DAG 依赖解析（拓扑排序）
    - 变量绑定 ${step.output.field}
    - 条件执行
    - 错误处理和回滚
    - 与 ToolRegistry 集成
    """

    def __init__(self, definition: PipelineDefinition, hook_registry=None):
        self.definition = definition
        self._step_map: dict[str, PipelineStep] = {}
        self._variables: dict[str, Any] = {}
        self._tool_handlers: dict[str, Callable] = {}
        self._hook_registry = hook_registry  # FeedbackHookRegistry 可选注入
        self._build_step_map()

    def set_hook_registry(self, hook_registry):
        """注入 FeedbackHookRegistry 以启用四大闭环 Hook"""
        self._hook_registry = hook_registry

    def _build_step_map(self):
        for step in self.definition.steps:
            self._step_map[step.id] = step

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "PipelineEngine":
        """从 YAML 文件加载 Pipeline"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineEngine":
        """从字典构建 Pipeline"""
        steps = []
        for s in data.get("steps", []):
            steps.append(PipelineStep(
                id=s["id"],
                tool=s.get("tool", ""),
                params=s.get("params", {}),
                depends_on=s.get("depends_on", []),
                output_binding=s.get("output_binding", {}),
                condition=s.get("condition", ""),
                on_error=s.get("on_error", "fail"),
                retry=s.get("retry", {}),
            ))

        definition = PipelineDefinition(
            name=data.get("name", "unnamed"),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            trigger=data.get("trigger", {}),
            state_machine=data.get("state_machine", {}),
            steps=steps,
            error_handling=data.get("error_handling", {}),
            cleanup=data.get("cleanup", []),
        )
        return cls(definition)

    # ── 工具注册 ──

    def register_tool(self, tool_name: str, handler: Callable):
        """注册工具处理函数"""
        self._tool_handlers[tool_name] = handler

    # ── DAG 拓扑排序 ──

    def _topological_sort(self) -> list[str]:
        """按依赖关系拓扑排序步骤"""
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        for step in self.definition.steps:
            if step.id not in in_degree:
                in_degree[step.id] = 0
            for dep in step.depends_on:
                graph[dep].append(step.id)
                in_degree[step.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            queue.sort()  # 确定性排序
            node = queue.pop(0)
            result.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.definition.steps):
            raise ValueError(
                f"Pipeline 存在循环依赖: 已排序 {len(result)}/{len(self.definition.steps)} 步"
            )

        return result

    # ── 变量绑定 ──

    def _resolve_variables(self, value: Any) -> Any:
        """递归解析变量引用 ${step_id.field}"""
        if isinstance(value, str):
            pattern = r"\$\{([^}]+)\}"
            matches = re.findall(pattern, value)
            if not matches:
                return value

            result = value
            for match in matches:
                resolved = self._get_variable(match)
                if len(matches) == 1 and not isinstance(resolved, str):
                    return resolved  # 单变量替换保留原始类型
                result = result.replace(f"${{{match}}}", str(resolved))
            return result

        elif isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
        return value

    def _get_variable(self, path: str) -> Any:
        """从变量存储中获取值（支持嵌套路径）"""
        parts = path.split(".")
        current = self._variables
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _apply_output_binding(self, step_id: str, output: dict, bindings: dict):
        """将步骤输出绑定到变量"""
        for var_name, jsonpath in bindings.items():
            value = self._extract_jsonpath(output, jsonpath)
            # 以 step_id 为命名空间存储
            if step_id not in self._variables:
                self._variables[step_id] = {}
            if isinstance(self._variables[step_id], dict):
                self._variables[step_id][var_name] = value
            # 同时存为顶层变量（方便引用）
            self._variables[var_name] = value

    def _extract_jsonpath(self, data: Any, path: str) -> Any:
        """简化 JSONPath 提取（支持 $. 前缀）"""
        if path == "$" or path == "$.":
            return data
        if path.startswith("$."):
            path = path[2:]
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current

    # ── 条件评估 ──

    def _evaluate_condition(self, condition: str) -> bool:
        """评估条件表达式"""
        if not condition:
            return True
        resolved = self._resolve_variables(condition)
        if isinstance(resolved, bool):
            return resolved
        if isinstance(resolved, str):
            return resolved.lower() in ("true", "1", "yes")
        return bool(resolved)

    # ── Hook 调度 ──

    def _fire_hook(self, phase_name: str, ctx: dict):
        """触发 Hook（安全调用，不影响主流程）"""
        if not self._hook_registry:
            return
        try:
            from core.feedback_loops import HookPhase
            phase_map = {
                "before_step": HookPhase.BEFORE_STEP,
                "after_step": HookPhase.AFTER_STEP,
                "on_success": HookPhase.ON_SUCCESS,
                "on_failure": HookPhase.ON_FAILURE,
            }
            phase = phase_map.get(phase_name)
            if phase:
                self._hook_registry.fire(phase, ctx)
        except ImportError:
            pass

    # ── 执行 ──

    async def execute(self, context: dict = None) -> PipelineResult:
        """
        执行 Pipeline。

        Args:
            context: 初始上下文变量

        Returns:
            PipelineResult
        """
        start_time = time.time()
        self._variables = dict(context or {})
        result = PipelineResult(pipeline_name=self.definition.name)

        # 拓扑排序
        try:
            execution_order = self._topological_sort()
        except ValueError as e:
            result.status = "fail"
            result.errors.append(str(e))
            return result

        result.status = "running"

        for step_id in execution_order:
            step = self._step_map[step_id]

            # 条件检查
            if step.condition and not self._evaluate_condition(step.condition):
                step_result = StepResult(step_id=step_id, status="skip")
                result.step_results[step_id] = step_result
                continue

            # 检查依赖是否全部通过
            deps_ok = True
            for dep in step.depends_on:
                dep_result = result.step_results.get(dep)
                if dep_result and dep_result.status == "fail":
                    deps_ok = False
                    break

            if not deps_ok:
                step_result = StepResult(
                    step_id=step_id,
                    status="skip",
                    error=f"依赖步骤失败: {step.depends_on}",
                )
                result.step_results[step_id] = step_result
                continue

            # 执行步骤
            self._fire_hook("before_step", {"step_id": step_id, "step": step.tool})
            step_result = await self._execute_step(step)
            result.step_results[step_id] = step_result
            self._fire_hook("after_step", {"step_id": step_id, "status": step_result.status, "error": step_result.error or ""})

            # 失败处理
            if step_result.status == "fail":
                self._fire_hook("on_failure", {"step_id": step_id, "error": step_result.error or "", "status": "fail"})
                if step.on_error == "skip":
                    continue
                elif step.on_error == "rollback":
                    await self._execute_rollback(result)
                    result.status = "rolled_back"
                    break
                else:  # fail - 继续执行以标记依赖步骤为 skip
                    result.errors.append(f"步骤 '{step_id}' 失败: {step_result.error}")
                    result.status = "fail"
                    continue

        # 如果所有步骤通过
        if result.status == "running":
            result.status = "pass"
            self._fire_hook("on_success", {"pipeline_id": self.definition.name, "status": "pass", "steps": list(result.step_results.keys())})

        result.variables = dict(self._variables)
        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def _execute_step(self, step: PipelineStep) -> StepResult:
        """执行单个步骤"""
        step_start = time.time()
        max_retries = step.retry.get("max_retries", 0)
        backoff_ms = step.retry.get("backoff_ms", 1000)

        # 解析参数中的变量
        resolved_params = self._resolve_variables(step.params)

        for attempt in range(max_retries + 1):
            try:
                # 查找工具处理函数
                handler = self._tool_handlers.get(step.tool)
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        output = await handler(resolved_params)
                    else:
                        output = handler(resolved_params)
                else:
                    # 无处理器时返回参数作为输出（占位）
                    output = {"_tool": step.tool, "_params": resolved_params, "_status": "no_handler"}

                # 应用输出绑定
                if step.output_binding and isinstance(output, dict):
                    self._apply_output_binding(step.id, output, step.output_binding)

                return StepResult(
                    step_id=step.id,
                    status="pass",
                    output=output if isinstance(output, dict) else {"value": output},
                    duration_ms=int((time.time() - step_start) * 1000),
                    retries=attempt,
                )

            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(backoff_ms / 1000 * (attempt + 1))
                    continue

                return StepResult(
                    step_id=step.id,
                    status="fail",
                    error=str(e),
                    duration_ms=int((time.time() - step_start) * 1000),
                    retries=attempt,
                )

        return StepResult(step_id=step.id, status="fail", error="未知错误")

    async def _execute_rollback(self, result: PipelineResult):
        """执行回滚"""
        error_handling = self.definition.error_handling
        rollback_steps = error_handling.get("rollback_steps", [])

        for rb in rollback_steps:
            tool_name = rb.get("tool", "")
            params = self._resolve_variables(rb.get("params", {}))

            handler = self._tool_handlers.get(tool_name)
            try:
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(params)
                    else:
                        handler(params)
                result.rollbacks_executed.append({
                    "tool": tool_name,
                    "params": params,
                    "status": "executed",
                })
            except Exception as e:
                result.rollbacks_executed.append({
                    "tool": tool_name,
                    "params": params,
                    "status": "failed",
                    "error": str(e),
                })

        # 执行清理
        for cleanup in self.definition.cleanup:
            tool_name = cleanup.get("tool", "")
            params = self._resolve_variables(cleanup.get("params", {}))
            handler = self._tool_handlers.get(tool_name)
            try:
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(params)
                    else:
                        handler(params)
            except Exception:
                pass
