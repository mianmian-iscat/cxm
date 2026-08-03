"""
tool_registry.py — 工具注册表

原创保护 Harness 工具注册与发现：
- 统一工具注册和发现
- Schema 校验（基于 JSON Schema）
- 工具依赖解析
- MCP Adapter 桥接

使用方式:
    from core.tool_registry import ToolRegistry
    registry = ToolRegistry.from_json("harness/registry.json")
    tool_info = registry.get_tool("op_exec_assistant")
    registry.validate_params("op_exec_assistant", {"case_id": "OP-TC-0001"})
"""

import os
import json
import re
import time
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Optional, Callable


@dataclass
class ToolSchema:
    """工具 Schema 定义"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    triggers: list = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    returns: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)
    timeout_ms: int = 60000
    retry_policy: dict = field(default_factory=dict)
    validation_rules: list = field(default_factory=list)
    health_check_url: str = ""   # 健康检查端点（可选）

    @classmethod
    def from_dict(cls, data: dict) -> "ToolSchema":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            parameters=data.get("parameters", {}),
            returns=data.get("returns", {}),
            dependencies=data.get("dependencies", []),
            timeout_ms=data.get("timeout_ms", 60000),
            retry_policy=data.get("retry_policy", {}),
            validation_rules=data.get("validation_rules", []),
            health_check_url=data.get("health_check_url", ""),
        )


@dataclass
class ToolStats:
    """工具调用统计"""
    calls: int = 0
    success: int = 0
    fail: int = 0
    total_latency_ms: int = 0
    last_call_at: float = 0.0
    last_error: str = ""

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.calls, 1)

    @property
    def success_rate(self) -> float:
        return self.success / max(self.calls, 1) * 100

    def to_dict(self) -> dict:
        return {
            "calls": self.calls, "success": self.success, "fail": self.fail,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "success_rate": round(self.success_rate, 1),
            "last_call_at": self.last_call_at, "last_error": self.last_error,
        }


@dataclass
class ToolInfo:
    """已注册的工具信息"""
    name: str
    schema: ToolSchema
    schema_path: str = ""
    handler: Any = None
    enabled: bool = True
    metadata: dict = field(default_factory=dict)
    stats: ToolStats = field(default_factory=ToolStats)  # 调用统计
    healthy: bool = True   # 健康状态（由 ToolHealthMonitor 更新）


@dataclass
class ValidationResult:
    """参数校验结果"""
    valid: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    normalized_params: dict = field(default_factory=dict)


class ToolRegistry:
    """
    工具注册表：统一管理原创保护 Harness 的所有工具。
    """

    def __init__(self, domain: str = "original-protection", version: str = "1.0.0"):
        self.domain = domain
        self.version = version
        self._tools: dict[str, ToolInfo] = {}
        self._schemas_cache: dict[str, ToolSchema] = {}

    @classmethod
    def from_json(cls, registry_path: str) -> "ToolRegistry":
        """从 registry.json 加载注册表"""
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        registry = cls(
            domain=data.get("domain", "original-protection"),
            version=data.get("version", "1.0.0"),
        )

        base_dir = os.path.dirname(registry_path)
        for tool_entry in data.get("tools", []):
            name = tool_entry.get("name", "")
            schema_path = tool_entry.get("schema_path", "")

            full_path = os.path.join(base_dir, schema_path) if schema_path else ""
            schema = None
            if full_path and os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as sf:
                    schema_data = json.load(sf)
                schema = ToolSchema.from_dict(schema_data)
            else:
                schema = ToolSchema(name=name)

            registry.register(ToolInfo(
                name=name,
                schema=schema,
                schema_path=full_path,
            ))

        return registry

    # ── 注册/注销 ──

    def register(self, tool_info: ToolInfo):
        """注册工具"""
        self._tools[tool_info.name] = tool_info
        self._schemas_cache[tool_info.name] = tool_info.schema

    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._schemas_cache.pop(name, None)

    def register_handler(self, name: str, handler: Any):
        """为已注册工具绑定处理函数"""
        if name in self._tools:
            self._tools[name].handler = handler

    # ── 查询 ──

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """检查工具是否已注册"""
        return name in self._tools

    def list_tools(self, enabled_only: bool = True) -> list:
        """列出所有工具名称"""
        tools = list(self._tools.values())
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return [t.name for t in tools]

    def load_all(self, tools_dir: str):
        """
        从目录加载所有 *.json 工具定义（支持子目录递归）。
        """
        if not os.path.isdir(tools_dir):
            return
        for root, _dirs, files in os.walk(tools_dir):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    schema = ToolSchema.from_dict(data)
                    name = schema.name or fname.replace(".schema.json", "").replace(".json", "")
                    if not schema.name:
                        schema.name = name
                    self.register(ToolInfo(name=name, schema=schema, schema_path=fpath))
                except (json.JSONDecodeError, KeyError) as e:
                    pass  # 跳过无效文件

    def semantic_match(self, trigger: str) -> Optional[dict]:
        """
        模糊匹配工具名/触发词。
        返回最佳匹配的工具 dict，无匹配返回 None。
        """
        trigger_lower = trigger.lower()
        best_match = None
        best_score = 0
        for info in self._tools.values():
            # 检查触发词
            for t in info.schema.triggers:
                if trigger_lower in t.lower() or t.lower() in trigger_lower:
                    score = len(t) / max(len(trigger), 1)
                    if score > best_score:
                        best_score = score
                        best_match = info
            # 检查名称
            if info.name and (info.name in trigger_lower or trigger_lower in info.name):
                score = len(info.name) / max(len(trigger), 1)
                if score > best_score:
                    best_score = score
                    best_match = info
            # 检查描述
            desc = info.schema.description.lower()
            if desc and trigger_lower in desc:
                score = 0.5
                if score > best_score:
                    best_score = score
                    best_match = info
        if best_match:
            return {
                "name": best_match.name,
                "parameters": best_match.schema.parameters,
                "description": best_match.schema.description,
                "triggers": best_match.schema.triggers,
            }
        return None

    def find_by_trigger(self, trigger: str) -> list[ToolInfo]:
        """按触发词查找工具"""
        return [
            t for t in self._tools.values()
            if trigger in t.schema.triggers and t.enabled
        ]

    def find_by_dependency(self, dependency: str) -> list[ToolInfo]:
        """查找依赖某工具的所有工具"""
        return [
            t for t in self._tools.values()
            if dependency in t.schema.dependencies
        ]

    # ── 参数校验 ──

    def validate_params(self, tool_name: str, params: dict) -> ValidationResult:
        """
        校验工具调用参数。

        Returns:
            ValidationResult
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ValidationResult(
                valid=False,
                errors=[f"工具未注册: {tool_name}"],
            )

        schema = tool.schema
        param_schema = schema.parameters
        if not param_schema:
            return ValidationResult(valid=True, normalized_params=dict(params))

        errors = []
        warnings = []
        normalized = dict(params)

        required = param_schema.get("required", [])
        properties = param_schema.get("properties", {})

        for req_field in required:
            if req_field not in params:
                errors.append(f"缺少必填参数: {req_field}")

        for field_name, field_def in properties.items():
            if field_name not in params:
                if "default" in field_def:
                    normalized[field_name] = field_def["default"]
                continue

            value = params[field_name]
            expected_type = field_def.get("type", "")

            if not self._check_type(value, expected_type):
                errors.append(f"参数 '{field_name}' 类型错误: 期望 {expected_type}")
                continue

            if "enum" in field_def:
                if value not in field_def["enum"]:
                    errors.append(f"参数 '{field_name}' 值非法")

            if "pattern" in field_def:
                if isinstance(value, str) and not re.match(field_def["pattern"], value):
                    errors.append(f"参数 '{field_name}' 格式错误")

        for key in params:
            if key not in properties and key != "type":
                warnings.append(f"未知参数: {key}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_params=normalized,
        )

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """检查值类型"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        py_type = type_map.get(expected_type)
        if py_type is None:
            return True
        return isinstance(value, py_type)

    # ── 依赖解析 ──

    def resolve_dependencies(self, tool_name: str) -> list[str]:
        """解析工具的依赖链（递归）"""
        visited = set()
        result = []

        def _resolve(name: str):
            if name in visited:
                return
            visited.add(name)
            tool = self._tools.get(name)
            if not tool:
                return
            for dep in tool.schema.dependencies:
                _resolve(dep)
                if dep not in result:
                    result.append(dep)

        _resolve(tool_name)
        return result

    def check_dependencies_available(self, tool_name: str) -> dict:
        """检查工具的所有依赖是否已注册且可用（含传递依赖）"""
        tool = self._tools.get(tool_name)
        if not tool:
            return {"available": False, "missing": [tool_name]}

        # 递归收集所有传递依赖
        all_deps = []
        visited = set()

        def _collect_deps(name):
            if name in visited:
                return
            visited.add(name)
            t = self._tools.get(name)
            if t:
                for dep in t.schema.dependencies:
                    if dep not in visited:
                        all_deps.append(dep)
                        _collect_deps(dep)
            else:
                all_deps.append(name)

        for dep in tool.schema.dependencies:
            all_deps.append(dep)
            _collect_deps(dep)

        # 去重保留顺序
        seen = set()
        unique_deps = []
        for d in all_deps:
            if d not in seen:
                seen.add(d)
                unique_deps.append(d)

        missing = [
            dep for dep in unique_deps
            if dep not in self._tools or not self._tools[dep].enabled
        ]
        return {
            "available": len(missing) == 0,
            "missing": missing,
            "satisfied": [dep for dep in unique_deps if dep not in missing],
        }

    # ── 工具执行沙箱 ──

    async def execute_with_sandbox(
        self,
        tool_name: str,
        params: dict,
        timeout_ms: int = 0,
    ) -> dict:
        """
        在沙箱中执行工具：超时保护 + 异常捕获 + 统计记录。

        Args:
            tool_name: 工具名称
            params: 调用参数
            timeout_ms: 超时毫秒数（0=使用 Schema 中定义的超时）

        Returns:
            {"success": bool, "result": Any, "error": str, "latency_ms": int}
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "result": None, "error": f"工具未注册: {tool_name}", "latency_ms": 0}
        if not tool.handler:
            return {"success": False, "result": None, "error": f"工具无 handler: {tool_name}", "latency_ms": 0}
        if not tool.enabled:
            return {"success": False, "result": None, "error": f"工具已禁用: {tool_name}", "latency_ms": 0}
        if not tool.healthy:
            return {"success": False, "result": None, "error": f"工具不健康: {tool_name}", "latency_ms": 0}

        # 参数校验
        validation = self.validate_params(tool_name, params)
        if not validation.valid:
            return {"success": False, "result": None,
                    "error": f"参数校验失败: {validation.errors}", "latency_ms": 0}

        effective_timeout = (timeout_ms or tool.schema.timeout_ms) / 1000
        start = time.time()
        result = None
        error = ""
        success = False

        try:
            if asyncio.iscoroutinefunction(tool.handler):
                result = await asyncio.wait_for(
                    tool.handler(**validation.normalized_params),
                    timeout=effective_timeout,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: tool.handler(**validation.normalized_params)
                    ),
                    timeout=effective_timeout,
                )
            success = True
        except asyncio.TimeoutError:
            error = f"工具执行超时 ({effective_timeout:.1f}s)"
        except Exception as e:
            error = f"工具执行异常: {e}"
        finally:
            latency = int((time.time() - start) * 1000)
            # 更新统计
            tool.stats.calls += 1
            tool.stats.total_latency_ms += latency
            tool.stats.last_call_at = time.time()
            if success:
                tool.stats.success += 1
            else:
                tool.stats.fail += 1
                tool.stats.last_error = error

        return {"success": success, "result": result, "error": error, "latency_ms": latency}

    def get_stats(self, tool_name: str = "") -> dict:
        """获取工具调用统计（指定名称或全部）"""
        if tool_name:
            tool = self._tools.get(tool_name)
            return tool.stats.to_dict() if tool else {}
        return {
            name: info.stats.to_dict()
            for name, info in self._tools.items()
            if info.stats.calls > 0
        }

    # ── MCP 桥接 ──

    def get_mcp_tools(self) -> list[dict]:
        """获取所有需要 MCP Adapter 桥接的工具"""
        return [
            {
                "name": t.name,
                "description": t.schema.description,
                "parameters": t.schema.parameters,
                "mcp_dependencies": [d for d in t.schema.dependencies if d.startswith("mcp:")],
            }
            for t in self._tools.values()
            if any(d.startswith("mcp:") for d in t.schema.dependencies)
        ]

    # ── 导出 ──

    def to_dict(self) -> dict:
        """导出注册表为字典"""
        return {
            "domain": self.domain,
            "version": self.version,
            "tools": [
                {
                    "name": t.name,
                    "version": t.schema.version,
                    "description": t.schema.description,
                    "enabled": t.enabled,
                    "dependencies": t.schema.dependencies,
                }
                for t in self._tools.values()
            ],
        }

    def to_json(self, output_path: str = "") -> str:
        """导出为 JSON"""
        data = self.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)
        return json_str


# ── 工具健康监控器 ──

class ToolHealthMonitor:
    """
    工具健康监控器：定期探测工具可用性，异常时自动禁用。

    支持两种健康检查方式：
    - HTTP 检查：调用工具的 health_check_url（200=健康）
    - Handler 检查：调用工具的 handler(health_check=True)

    使用方式:
        monitor = ToolHealthMonitor(registry, interval_seconds=60)
        monitor.start()  # 启动后台线程
        # ...
        monitor.stop()
    """

    def __init__(
        self,
        registry: "ToolRegistry",
        interval_seconds: int = 60,
        unhealthy_threshold: int = 3,  # 连续失败 N 次才标记不健康
    ):
        self._registry = registry
        self._interval = interval_seconds
        self._threshold = unhealthy_threshold
        self._fail_counts: dict[str, int] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log: list[dict] = []

    def start(self):
        """启动后台健康检查线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def check_once(self, tool_name: str) -> bool:
        """立即对单个工具进行一次健康检查"""
        tool = self._registry.get_tool(tool_name)
        if not tool or not tool.enabled:
            return False
        healthy = self._do_check(tool)
        self._update_health(tool, healthy)
        return healthy

    def check_all(self) -> dict[str, bool]:
        """立即对所有已启用工具进行一次健康检查"""
        results = {}
        for name, tool in self._registry._tools.items():
            if not tool.enabled:
                continue
            healthy = self._do_check(tool)
            self._update_health(tool, healthy)
            results[name] = healthy
        return results

    def get_log(self, limit: int = 20) -> list[dict]:
        return self._log[-limit:]

    def _loop(self):
        while self._running:
            try:
                self.check_all()
            except Exception:
                pass
            time.sleep(self._interval)

    def _do_check(self, tool: "ToolInfo") -> bool:
        """执行实际的健康检查"""
        # HTTP 检查
        if tool.schema.health_check_url:
            try:
                import urllib.request
                req = urllib.request.Request(tool.schema.health_check_url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status == 200
            except Exception:
                return False

        # Handler 检查（约定 handler 支持 health_check 参数）
        if tool.handler:
            try:
                if asyncio.iscoroutinefunction(tool.handler):
                    # 异步 handler 不在同步线程中检查，默认健康
                    return True
                result = tool.handler(health_check=True)
                return bool(result)
            except TypeError:
                # handler 不支持 health_check 参数，默认健康
                return True
            except Exception:
                return False

        return True  # 无 handler 的工具默认健康

    def _update_health(self, tool: "ToolInfo", healthy: bool):
        """更新工具健康状态"""
        name = tool.name
        if healthy:
            self._fail_counts[name] = 0
            if not tool.healthy:
                tool.healthy = True
                self._log.append({
                    "tool": name, "status": "recovered", "timestamp": time.time()
                })
        else:
            self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
            if self._fail_counts[name] >= self._threshold and tool.healthy:
                tool.healthy = False
                self._log.append({
                    "tool": name, "status": "unhealthy",
                    "consecutive_fails": self._fail_counts[name],
                    "timestamp": time.time(),
                })
