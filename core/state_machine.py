"""
state_machine.py — 状态机引擎

原创保护 Harness 核心组件：
- 加载状态机 YAML 定义（states + transitions + guards + side_effects）
- 校验状态转换合法性（from→to 是否在定义中）
- 评估 Guard 条件表达式
- 验证 Side Effects 完整性
- 检测非法状态跳跃

使用方式:
    from core.state_machine import StateMachineEngine
    engine = StateMachineEngine.from_yaml("harness/state_machines/patent_application.yaml")
    result = engine.validate_transition("SUBMITTED", "PRE_EXAM_PASSED", context={})
"""

import time
import yaml
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class Transition:
    """状态转换定义"""
    from_state: str
    to_state: str
    trigger: str = ""
    guard: str = ""
    side_effects: list = field(default_factory=list)
    timeout_seconds: int = 0     # 0=无超时，>0 表示在此状态停留超过该时间后可自动转换
    on_timeout: str = ""         # 超时后自动跳转的目标状态（空=不自动跳转）

@dataclass
class TransitionResult:
    """状态转换校验结果"""
    valid: bool
    from_state: str
    to_state: str
    guard_evaluated: dict = field(default_factory=dict)
    side_effects_verified: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    executed: bool = False        # 是否已执行状态流转
    previous_state: str = ""      # 流转前的状态（用于回滚参考）

@dataclass
class StateMachineDefinition:
    """状态机定义"""
    name: str
    states: list
    transitions: list
    entity: str = ""
    id_field: str = ""
    initial_state: str = ""
    state_metadata: dict = field(default_factory=dict)  # 各状态的扩展元数据（如 description/timeout）

class StateMachineEngine:
    """
    状态机引擎：加载 YAML 定义并校验状态转换合法性。
    
    支持:
    - 状态转换合法性校验
    - Guard 条件表达式评估
    - Side Effects 完整性验证
    - 非法状态跳跃检测
    - 状态路径分析
    - 运行时状态管理（current_state）
    - 状态持久化（checkpoint 保存/恢复）
    - Mermaid 图导出
    - 状态超时检测
    """

    def __init__(self, definition: StateMachineDefinition, initial_state: str = ""):
        self.definition = definition
        self._transition_map: dict[tuple[str, str], list[Transition]] = {}
        self._build_transition_map()
        # 运行时状态
        self._current_state: str = initial_state or definition.initial_state or (
            definition.states[0] if definition.states else ""
        )
        self._entered_at: float = 0.0   # 进入当前状态的时间戳
        self._transition_history: list[dict] = []  # 流转历史

    def _build_transition_map(self):
        """构建 (from, to) -> [Transition] 索引"""
        for t in self.definition.transitions:
            key = (t.from_state, t.to_state)
            if key not in self._transition_map:
                self._transition_map[key] = []
            self._transition_map[key].append(t)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "StateMachineEngine":
        """从 YAML 文件加载状态机定义"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "StateMachineEngine":
        """从字典构建状态机"""
        # 支持顶层 state_machine 嵌套
        sm_data = data.get("state_machine", data)

        states = sm_data.get("states", [])
        transitions_raw = sm_data.get("transitions", [])
        state_metadata = sm_data.get("state_metadata", {})

        transitions = []
        for t in transitions_raw:
            transitions.append(Transition(
                from_state=t["from"],
                to_state=t["to"],
                trigger=t.get("trigger", ""),
                guard=t.get("guard", ""),
                side_effects=t.get("side_effects", []),
                timeout_seconds=t.get("timeout_seconds", 0),
                on_timeout=t.get("on_timeout", ""),
            ))

        definition = StateMachineDefinition(
            name=data.get("name", sm_data.get("name", "unnamed")),
            states=states,
            transitions=transitions,
            entity=sm_data.get("entity", ""),
            id_field=sm_data.get("id_field", ""),
            initial_state=sm_data.get("initial_state", states[0] if states else ""),
            state_metadata=state_metadata,
        )
        return cls(definition)

    # ── 核心校验 ──

    def validate_transition(
        self,
        from_state: str,
        to_state: str,
        context: dict = None,
        actual_side_effects: list = None,
    ) -> TransitionResult:
        """
        校验一次状态转换的合法性。
        
        Args:
            from_state: 当前状态
            to_state: 目标状态
            context: Guard 条件评估上下文（变量字典）
            actual_side_effects: 实际执行的 Side Effects 列表
        
        Returns:
            TransitionResult
        """
        context = context or {}
        actual_side_effects = actual_side_effects or []
        errors = []
        warnings = []
        guard_evaluated = {}
        side_effects_verified = []

        # 1. 状态值合法性
        if from_state not in self.definition.states:
            errors.append(f"非法源状态: '{from_state}'，合法状态: {self.definition.states}")
        if to_state not in self.definition.states:
            errors.append(f"非法目标状态: '{to_state}'，合法状态: {self.definition.states}")
        if errors:
            return TransitionResult(
                valid=False, from_state=from_state, to_state=to_state,
                errors=errors
            )

        # 2. 转换合法性
        key = (from_state, to_state)
        candidates = self._transition_map.get(key, [])
        if not candidates:
            # 检测是否为非法跳跃
            reachable = self._find_reachable(from_state)
            if to_state in reachable:
                errors.append(
                    f"非法状态跳跃: '{from_state}' → '{to_state}' 不是直接转换，"
                    f"需经过中间状态"
                )
            else:
                errors.append(
                    f"非法状态转换: '{from_state}' → '{to_state}' 未在状态机中定义"
                )
            return TransitionResult(
                valid=False, from_state=from_state, to_state=to_state,
                errors=errors
            )

        # 3. Guard 条件评估（尝试所有候选转换）
        matched_transition = None
        for transition in candidates:
            if transition.guard:
                guard_result = self._evaluate_guard(transition.guard, context)
                guard_evaluated[transition.guard] = guard_result
                if guard_result:
                    matched_transition = transition
                    break
            else:
                matched_transition = transition
                break

        if matched_transition is None:
            errors.append(f"所有候选转换的 Guard 条件均不满足: {from_state} → {to_state}")
            return TransitionResult(
                valid=False, from_state=from_state, to_state=to_state,
                guard_evaluated=guard_evaluated, errors=errors
            )

        # 4. Side Effects 验证
        if matched_transition.side_effects:
            side_effects_verified = self._verify_side_effects(
                matched_transition.side_effects, actual_side_effects, context
            )
            for se in side_effects_verified:
                if not se.get("verified", False):
                    warnings.append(f"Side Effect 未验证: {se.get('expected', '')}")

        return TransitionResult(
            valid=True,
            from_state=from_state,
            to_state=to_state,
            guard_evaluated=guard_evaluated,
            side_effects_verified=side_effects_verified,
            errors=errors,
            warnings=warnings,
        )

    def validate_sequence(self, transitions_seq: list[dict]) -> list[TransitionResult]:
        """
        校验一系列状态转换。
        
        Args:
            transitions_seq: [{"from": "A", "to": "B", "context": {}}, ...]
        
        Returns:
            每个转换的校验结果列表
        """
        results = []
        for t in transitions_seq:
            result = self.validate_transition(
                from_state=t["from"],
                to_state=t["to"],
                context=t.get("context", {}),
                actual_side_effects=t.get("side_effects", []),
            )
            results.append(result)

            # 检测连续性：当前转换的 to_state 应与下一个转换的 from_state 一致
        for i in range(len(results) - 1):
            if results[i].to_state != transitions_seq[i + 1].get("from"):
                results[i + 1].errors.append(
                    f"状态不连续: 上一步到达 '{results[i].to_state}'，"
                    f"但下一步从 '{transitions_seq[i + 1].get('from')}' 开始"
                )
                results[i + 1].valid = False

        return results

    # ── Guard 表达式评估 ──

    def _evaluate_guard(self, guard_expr: str, context: dict) -> bool:
        """
        评估 Guard 条件表达式。
        
        支持的语法:
        - 简单比较: "field == value", "field >= number"
        - 复合条件: "cond1 AND cond2"
        - 函数: "now() - Nd" (时间计算)
        """
        if not guard_expr:
            return True

        # 处理 AND 复合条件
        if " AND " in guard_expr:
            parts = guard_expr.split(" AND ")
            return all(self._evaluate_guard(p.strip(), context) for p in parts)

        # 处理 OR 复合条件
        if " OR " in guard_expr:
            parts = guard_expr.split(" OR ")
            return any(self._evaluate_guard(p.strip(), context) for p in parts)

        # 简单比较表达式
        for op in ("==", "!=", ">=", "<=", ">", "<"):
            if op in guard_expr:
                left, right = guard_expr.split(op, 1)
                left_val = self._resolve_value(left.strip(), context)
                right_val = self._resolve_value(right.strip(), context)
                # 如果左侧解析为字符串且右侧未解析到值，将右侧视为字符串字面量
                if isinstance(left_val, str) and right_val is None:
                    right_val = right.strip().strip('"').strip("'")
                try:
                    if op == "==": return left_val == right_val
                    if op == "!=": return left_val != right_val
                    if op == ">=": return float(left_val) >= float(right_val)
                    if op == "<=": return float(left_val) <= float(right_val)
                    if op == ">":  return float(left_val) > float(right_val)
                    if op == "<":  return float(left_val) < float(right_val)
                except (ValueError, TypeError):
                    return False

        # 布尔字段直接查 context
        return bool(context.get(guard_expr.strip(), False))

    def _resolve_value(self, expr: str, context: dict) -> Any:
        """解析表达式中的变量和字面量"""
        expr = expr.strip()

        # 字面量
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]
        if expr.startswith("'") and expr.endswith("'"):
            return expr[1:-1]
        try:
            return int(expr)
        except ValueError:
            pass
        try:
            return float(expr)
        except ValueError:
            pass
        if expr.lower() in ("true", "false"):
            return expr.lower() == "true"
        if expr.lower() == "null" or expr.lower() == "none":
            return None

        # 从 context 解析
        if "." in expr:
            parts = expr.split(".")
            val = context
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    return None
            return val

        return context.get(expr)

    # ── Side Effects 验证 ──

    def _verify_side_effects(
        self, expected: list, actual: list, context: dict
    ) -> list[dict]:
        """验证 Side Effects 是否完整执行"""
        results = []
        actual_strs = [str(a) for a in actual]

        for se in expected:
            se_str = self._format_side_effect(se)
            verified = False

            # 在 actual 中查找匹配
            for a_str in actual_strs:
                if self._side_effect_match(se_str, a_str, se, context):
                    verified = True
                    break

            # 也检查 context 中对应字段是否已更新
            if not verified and isinstance(se, dict):
                if se.get("type") == "SET" or "set" in se:
                    field_name = se.get("field", se.get("set", "").split("=")[0].strip())
                    if field_name in context:
                        verified = True

            results.append({
                "expected": se_str,
                "verified": verified,
                "type": se.get("type", "unknown") if isinstance(se, dict) else "raw",
            })

        return results

    def _format_side_effect(self, se) -> str:
        """格式化 Side Effect 为可读字符串"""
        if isinstance(se, dict):
            if "set" in se:
                return f"SET: {se['set']}"
            if "deduct" in se:
                return f"DEDUCT: {se['deduct']}"
            if "log" in se:
                return f"LOG: {se['log']}"
            return str(se)
        return str(se)

    def _side_effect_match(self, expected_str: str, actual_str: str, se_def, context: dict) -> bool:
        """判断 expected 和 actual side effect 是否匹配"""
        return expected_str.lower() in actual_str.lower() or actual_str.lower() in expected_str.lower()

    # ── 路径分析 ──

    def _find_reachable(self, from_state: str) -> set:
        """查找从某状态可达的所有状态（BFS）"""
        visited = set()
        queue = [from_state]
        while queue:
            current = queue.pop(0)
            for t in self.definition.transitions:
                if t.from_state == current and t.to_state not in visited:
                    visited.add(t.to_state)
                    queue.append(t.to_state)
        return visited

    def get_all_paths(self, from_state: str, to_state: str, max_depth: int = 20) -> list[list[str]]:
        """查找两个状态之间的所有路径（DFS，限深度）"""
        paths = []

        def dfs(current: str, path: list, visited: set):
            if len(path) > max_depth:
                return
            if current == to_state:
                paths.append(list(path))
                return
            for t in self.definition.transitions:
                if t.from_state == current and t.to_state not in visited:
                    visited.add(t.to_state)
                    path.append(t.to_state)
                    dfs(t.to_state, path, visited)
                    path.pop()
                    visited.remove(t.to_state)

        dfs(from_state, [from_state], {from_state})
        return paths

    def get_legal_transitions(self, state: str) -> list[Transition]:
        """获取某状态的所有合法出转换"""
        return [t for t in self.definition.transitions if t.from_state == state]

    def get_transition_triggers(self, from_state: str, to_state: str) -> list[str]:
        """获取两个状态之间所有触发条件"""
        key = (from_state, to_state)
        return [t.trigger for t in self._transition_map.get(key, []) if t.trigger]

    # ── 运行时状态管理 ──

    @property
    def current_state(self) -> str:
        """当前运行时状态"""
        return self._current_state

    @property
    def entered_at(self) -> float:
        """进入当前状态的时间戳"""
        return self._entered_at

    @property
    def state_duration(self) -> float:
        """在当前状态已停留的秒数"""
        if self._entered_at <= 0:
            return 0.0
        return time.time() - self._entered_at

    def transition(
        self,
        to_state: str,
        context: dict = None,
        actual_side_effects: list = None,
    ) -> TransitionResult:
        """
        执行状态流转：校验合法性 → 更新 current_state → 记录历史。

        与 validate_transition 的区别：本方法会实际更新引擎状态。

        Returns:
            TransitionResult（executed=True 表示状态已流转）
        """
        from_state = self._current_state
        result = self.validate_transition(
            from_state=from_state,
            to_state=to_state,
            context=context,
            actual_side_effects=actual_side_effects,
        )
        if result.valid:
            prev = self._current_state
            self._current_state = to_state
            self._entered_at = time.time()
            result.executed = True
            result.previous_state = prev
            self._transition_history.append({
                "from": prev, "to": to_state,
                "timestamp": self._entered_at,
                "context_keys": list((context or {}).keys()),
            })
        return result

    def reset(self, state: str = ""):
        """重置运行时状态（回到初始状态或指定状态）"""
        self._current_state = state or self.definition.initial_state or (
            self.definition.states[0] if self.definition.states else ""
        )
        self._entered_at = time.time()

    def check_timeout(self) -> Optional[str]:
        """
        检查当前状态是否超时，返回超时后应跳转的目标状态（无超时返回 None）。
        """
        if not self._entered_at or not self._current_state:
            return None
        elapsed = time.time() - self._entered_at
        for t in self.definition.transitions:
            if t.from_state == self._current_state and t.timeout_seconds > 0:
                if elapsed >= t.timeout_seconds and t.on_timeout:
                    return t.on_timeout
        # 也检查 state_metadata 中的超时配置
        meta = self.definition.state_metadata.get(self._current_state, {})
        timeout_sec = meta.get("timeout_seconds", 0)
        on_timeout = meta.get("on_timeout", "")
        if timeout_sec > 0 and elapsed >= timeout_sec and on_timeout:
            return on_timeout
        return None

    def get_history(self, limit: int = 50) -> list[dict]:
        """获取状态流转历史（最近 N 条）"""
        return self._transition_history[-limit:]

    # ── 状态持久化 ──

    def save_checkpoint(self, path: str):
        """将当前状态持久化到文件（JSON）"""
        import json as _json
        data = {
            "machine_name": self.definition.name,
            "current_state": self._current_state,
            "entered_at": self._entered_at,
            "history": self._transition_history[-100:],  # 最近 100 条
        }
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)

    def load_checkpoint(self, path: str) -> bool:
        """从文件恢复状态（成功返回 True）"""
        import json as _json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if data.get("machine_name") != self.definition.name:
                return False
            self._current_state = data.get("current_state", self.definition.initial_state)
            self._entered_at = data.get("entered_at", time.time())
            self._transition_history = data.get("history", [])
            return True
        except Exception:
            return False

    # ── Mermaid 图导出 ──

    def to_mermaid(self, title: str = "") -> str:
        """
        导出状态机为 Mermaid 流程图语法，可直接嵌入文档。

        Returns:
            Mermaid 格式的字符串
        """
        lines = [f"stateDiagram-v2"]
        if title:
            lines.append(f"    %% {title}")
        # 初始状态
        if self.definition.initial_state:
            lines.append(f"    [*] --> {self.definition.initial_state}")
        # 所有转换
        for t in self.definition.transitions:
            label = t.trigger or ""
            if t.guard:
                label = f"{label} [{t.guard}]" if label else f"[{t.guard}]"
            if label:
                lines.append(f"    {t.from_state} --> {t.to_state} : {label}")
            else:
                lines.append(f"    {t.from_state} --> {t.to_state}")
        # 标注当前状态（如有）
        if self._current_state:
            lines.append(f"    note right of {self._current_state} : CURRENT")
        return "\n".join(lines)
