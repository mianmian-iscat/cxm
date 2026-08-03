"""
variable_store.py — 上下文与状态管理子系统 (Variable Store)

Harness 五大子系统之一。职责：
- 每步输出自动绑定为命名变量，后续步骤通过 ${step_id.field} 引用
- 支持 JSONPath 简单表达式提取步骤输出
- 支持模板变量解析（替换 ${...} 占位符）
- 与 CheckpointManager 集成的 checkpoint/restore 能力

使用方式：
    from core.variable_store import VariableStore
    store = VariableStore()

    # 步骤执行后绑定输出
    store.bind_step_output("step_query", {
        "responseBody": {"data": [...], "total": 10},
        "status": 200,
    }, output_binding={"result_data": "$.responseBody.data", "total": "$.responseBody.total"})

    # 后续步骤引用
    resolved = store.resolve_params({
        "items": "${step_query.result_data}",
        "count": "${step_query.total}",
    })
"""

import copy
import json
import re
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


# ── JSONPath 简单实现 ──

def _jsonpath_extract(data: Any, path: str) -> Any:
    """
    简单的 JSONPath 提取器，支持：
    - "$" 根节点
    - ".field" 字段访问
    - "[index]" 数组索引
    - "[?(@.field=='value')]" 简单过滤（返回匹配数组）

    不支持复杂的 JSONPath 表达式。
    """
    if not path or path == "$":
        return data

    # 移除开头的 "$." 或 "$"
    path = path.lstrip("$").lstrip(".")

    current = data
    for part in _split_path(path):
        if current is None:
            return None

        # 数组索引 [0], [1] 等
        idx_match = re.match(r'^\[(\d+)\]$', part)
        if idx_match:
            idx = int(idx_match.group(1))
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
            continue

        # 过滤表达式 [?(@.field=='value')]
        filter_match = re.match(r"^\[\?\(@\.(\w+)==['\"](.+?)['\"]\)\]$", part)
        if filter_match:
            field, value = filter_match.group(1), filter_match.group(2)
            if isinstance(current, list):
                current = [item for item in current if isinstance(item, dict) and str(item.get(field)) == value]
            else:
                return None
            continue

        # 普通字段访问
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current


def _split_path(path: str) -> List[str]:
    """将 JSONPath 路径拆分为各级"""
    parts = []
    current = ""
    bracket_depth = 0

    for char in path:
        if char == "[":
            if bracket_depth == 0 and current:
                parts.append(current)
                current = ""
            bracket_depth += 1
            current += char
        elif char == "]":
            bracket_depth -= 1
            current += char
        elif char == "." and bracket_depth == 0:
            if current:
                parts.append(current)
            current = ""
        else:
            current += char

    if current:
        parts.append(current)
    return parts


# ── 模板变量解析 ──

_VAR_PATTERN = re.compile(r'\$\{(\w+(?:\.\w+)*)\}')


def _deep_get(variables: Dict[str, Any], path: str) -> Any:
    """
    深度路径解析：先尝试直接 key 命中，失败后按 '.' 拆分逐级下钻。
    例: 'store_picked.picked.firstTaskId' →
        variables['store_picked.picked'] → dict → ['firstTaskId']
    """
    # 1. 直接命中（bind_step_output 注册的扁平 key）
    if path in variables:
        return variables[path]
    # 2. 逐级下钻
    parts = path.split(".")
    for split_idx in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:split_idx])
        if prefix in variables:
            current = variables[prefix]
            for part in parts[split_idx:]:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list) and part.isdigit():
                    idx = int(part)
                    current = current[idx] if 0 <= idx < len(current) else None
                else:
                    current = None
                    break
            if current is not None:
                return current
    return None


def _resolve_template(template: str, variables: Dict[str, Any]) -> Any:
    """
    解析模板字符串中的 ${...} 变量引用。

    如果整个字符串只有一个变量引用且无其他文本，直接返回原始值（保持类型）。
    否则替换为字符串形式。
    支持嵌套路径：${store_picked.picked.firstTaskId} 会逐级下钻。
    """
    matches = list(_VAR_PATTERN.finditer(template))
    if not matches:
        return template

    # 单变量完整替换：保持原始类型
    if len(matches) == 1 and matches[0].start() == 0 and matches[0].end() == len(template):
        var_path = matches[0].group(1)
        resolved = _deep_get(variables, var_path)
        return resolved if resolved is not None else template

    # 多变量或部分替换：转为字符串
    def replacer(m):
        var_path = m.group(1)
        value = _deep_get(variables, var_path)
        if value is None:
            return m.group(0)  # 保持原始占位符
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return _VAR_PATTERN.sub(replacer, template)


class VariableStore:
    """
    变量存储与上下文传递。
    替代 impl.py 中手动传递 last_api_entry 的方式，实现声明式数据绑定。

    支持作用域隔离：
    - 默认全局作用域，变量全局可见
    - push_scope(name) 创建命名作用域，bind_step_output 绑定到当前作用域
    - pop_scope() 退出当前作用域，作用域内变量保留但不再参与全局解析
    - 解析时优先查找当前作用域，再回退到全局
    """

    def __init__(self):
        self._variables: Dict[str, Any] = {}  # "step_id.field" -> value
        self._step_outputs: Dict[str, dict] = {}  # step_id -> full output dict
        self._scope_stack: List[str] = []  # 当前作用域栈
        self._scoped_variables: Dict[str, Dict[str, Any]] = {}  # scope -> variables

    # ── 存储 ──

    def store(self, key: str, value: Any, ttl: int = 3600):
        """
        存储一个变量。

        Args:
            key: 变量名（支持 "step_id.field" 格式）
            value: 变量值
            ttl: 生存时间（秒），当前版本未实现自动过期
        """
        self._variables[key] = value

    def retrieve(self, key: str) -> Any:
        """获取变量值，优先当前作用域，再回退全局。不存在返回 None"""
        # 优先查找当前作用域
        if self._scope_stack:
            scope = self._scope_stack[-1]
            scoped = self._scoped_variables.get(scope, {})
            if key in scoped:
                return scoped[key]
        return self._variables.get(key)

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """
        按关键词搜索变量（简单子串匹配）。

        Returns:
            [{"key": ..., "value": ...}, ...]
        """
        query_lower = query.lower()
        results = []
        for key, value in self._variables.items():
            if query_lower in key.lower():
                results.append({"key": key, "value": value})
                if len(results) >= top_k:
                    break
        return results

    # ── 步骤输出绑定 ──

    def bind_step_output(self, step_id: str, step_output: dict, output_binding: dict = None):
        """
        将步骤输出绑定到变量。

        Args:
            step_id: 步骤 ID
            step_output: 步骤执行结果 dict
            output_binding: 输出绑定映射 {变量名: JSONPath表达式}
                例: {"result_data": "$.responseBody.data"}
        """
        if not step_id:
            return

        # 存储完整输出（通过 step_id.* 访问）
        self._step_outputs[step_id] = step_output

        # 确定绑定目标：当前作用域 or 全局
        if self._scope_stack:
            scope = self._scope_stack[-1]
            if scope not in self._scoped_variables:
                self._scoped_variables[scope] = {}
            target = self._scoped_variables[scope]
        else:
            target = self._variables

        # 将完整输出的顶层字段注册为变量
        if isinstance(step_output, dict):
            for field, value in step_output.items():
                target[f"{step_id}.{field}"] = value

        # 按 output_binding 中的 JSONPath 提取并绑定
        if output_binding and isinstance(step_output, dict):
            for var_name, jsonpath in output_binding.items():
                extracted = _jsonpath_extract(step_output, jsonpath)
                target[f"{step_id}.{var_name}"] = extracted

    # ── 模板解析 ──

    def resolve(self, template: Any) -> Any:
        """
        解析模板中的 ${step_id.field} 变量引用。

        Args:
            template: 字符串模板或包含模板的 dict/list

        Returns:
            解析后的值（保持原始类型）
        """
        if isinstance(template, str):
            return _resolve_template(template, self._variables)
        elif isinstance(template, dict):
            return {k: self.resolve(v) for k, v in template.items()}
        elif isinstance(template, list):
            return [self.resolve(item) for item in template]
        return template

    def resolve_params(self, params: dict) -> dict:
        """
        解析步骤参数中的所有变量引用。

        Args:
            params: 步骤参数 dict

        Returns:
            变量替换后的新 dict（深拷贝）
        """
        return self.resolve(params)

    # ── 检查点 ──

    def checkpoint(self) -> dict:
        """
        序列化当前状态，用于断点续跑。

        Returns:
            可 JSON 序列化的状态 dict
        """
        return {
            "variables": copy.deepcopy(self._variables),
            "step_outputs": copy.deepcopy(self._step_outputs),
            "scope_stack": list(self._scope_stack),
            "scoped_variables": copy.deepcopy(self._scoped_variables),
        }

    def restore(self, state: dict):
        """
        从检查点恢复状态。

        Args:
            state: checkpoint() 返回的状态 dict
        """
        self._variables = state.get("variables", {})
        self._step_outputs = state.get("step_outputs", {})
        self._scope_stack = list(state.get("scope_stack", []))
        self._scoped_variables = state.get("scoped_variables", {})

    # ── 查询 ──

    def get_all_variables(self) -> Dict[str, Any]:
        """返回所有变量的副本"""
        return copy.deepcopy(self._variables)

    def get_step_output(self, step_id: str) -> Optional[dict]:
        """获取某步骤的完整输出"""
        return self._step_outputs.get(step_id)

    def clear(self):
        """清空所有变量"""
        self._variables.clear()
        self._step_outputs.clear()

    # ── 作用域管理 ──

    @property
    def current_scope(self) -> Optional[str]:
        """当前作用域名称，None 表示全局"""
        return self._scope_stack[-1] if self._scope_stack else None

    def push_scope(self, name: str):
        """压入命名作用域。后续 bind_step_output 绑定到该作用域。"""
        self._scope_stack.append(name)
        if name not in self._scoped_variables:
            self._scoped_variables[name] = {}

    def pop_scope(self) -> Optional[str]:
        """弹出当前作用域。作用域内变量保留但不再参与全局解析。"""
        if self._scope_stack:
            return self._scope_stack.pop()
        return None

    def get_scope_variables(self, scope: str) -> Dict[str, Any]:
        """获取指定作用域的所有变量"""
        return copy.deepcopy(self._scoped_variables.get(scope, {}))

    # ── 维度3: 数据新鲜度检测 ──

    @dataclass
    class _FreshnessSpec:
        """数据新鲜度声明"""
        variable_key: str
        condition: str  # "not_empty" | "min_length:N" | "matches:regex" | "api_check:url"
        ttl_seconds: int = 3600  # 数据最大存活时间
        fallback: str = ""  # 备选数据源
        last_validated: float = field(default_factory=time.time)
        is_valid: bool = True

    _FRESHNESS_SPECS: Dict[str, '_FreshnessSpec'] = {}

    def register_freshness(self, variable_key: str, condition: str,
                             ttl_seconds: int = 3600, fallback: str = ""):
        """
        注册数据新鲜度声明。

        Args:
            variable_key: 变量键名
            condition: 有效条件（not_empty/min_length:N/matches:regex/api_check:url）
            ttl_seconds: 最大存活时间（秒）
            fallback: 备选数据源描述
        """
        self._FRESHNESS_SPECS[variable_key] = self._FreshnessSpec(
            variable_key=variable_key,
            condition=condition,
            ttl_seconds=ttl_seconds,
            fallback=fallback,
        )

    def check_data_freshness(self, variable_key: str = None) -> Dict[str, dict]:
        """
        检查数据新鲜度。

        Args:
            variable_key: 指定检查某个变量，为 None 时检查所有已注册的变量

        Returns:
            {variable_key: {"valid": bool, "reason": str, "fallback": str}}
        """
        results = {}
        keys = [variable_key] if variable_key else list(self._FRESHNESS_SPECS.keys())

        for key in keys:
            spec = self._FRESHNESS_SPECS.get(key)
            if not spec:
                continue

            value = self.retrieve(key)
            now = time.time()
            result = {"valid": True, "reason": "", "fallback": spec.fallback}

            # TTL 检查
            if now - spec.last_validated > spec.ttl_seconds:
                result["valid"] = False
                result["reason"] = f"数据已过期 (TTL={spec.ttl_seconds}s)"

            # 条件检查
            if result["valid"] and spec.condition:
                cond = spec.condition
                if cond == "not_empty":
                    if not value or (isinstance(value, str) and not value.strip()):
                        result["valid"] = False
                        result["reason"] = "数据为空"
                elif cond.startswith("min_length:"):
                    min_len = int(cond.split(":")[1])
                    if not value or (isinstance(value, (str, list)) and len(value) < min_len):
                        result["valid"] = False
                        result["reason"] = f"数据长度不足 (min={min_len})"
                elif cond.startswith("matches:"):
                    pattern = cond.split(":", 1)[1]
                    if not value or not re.search(pattern, str(value)):
                        result["valid"] = False
                        result["reason"] = f"数据不匹配模式 ({pattern})"

            # 更新状态
            spec.is_valid = result["valid"]
            if result["valid"]:
                spec.last_validated = now

            results[key] = result

        return results

    def get_stale_variables(self) -> List[str]:
        """获取所有已过期的变量键名列表"""
        stale = []
        freshness = self.check_data_freshness()
        for key, info in freshness.items():
            if not info["valid"]:
                stale.append(key)
        return stale

    def load_freshness_from_input(self, input_data: dict):
        """
        从 input JSON 加载 data_freshness 声明。

        input_data 格式:
        {
            "data_freshness": {
                "step_query.result_data": {
                    "condition": "not_empty",
                    "ttl_seconds": 1800,
                    "fallback": "重新查询商品列表"
                }
            }
        }
        """
        freshness_config = input_data.get("data_freshness", {})
        for var_key, spec in freshness_config.items():
            if isinstance(spec, dict):
                self.register_freshness(
                    variable_key=var_key,
                    condition=spec.get("condition", "not_empty"),
                    ttl_seconds=spec.get("ttl_seconds", 3600),
                    fallback=spec.get("fallback", ""),
                )
