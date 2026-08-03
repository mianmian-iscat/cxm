"""
feedback_loops.py — 四大互喂闭环

差距 2.3 补齐。职责：
- 闭环 A（知识沉淀 Hook）: Pipeline 步骤完成后自动回写 patterns/
- 闭环 B（场景生成 Hook）: 从知识库 patterns 生成测试场景骨架
- 闭环 C（已有，扩展）: on_complete 回调钩子
- 闭环 D（BadCase 修复 Hook）: 失败用例自动生成 BadCase 记录并写入 patterns/
- 统一 Hook 注册机制: FeedbackHookRegistry

使用方式:
    from core.feedback_loops import FeedbackHookRegistry, HookPhase
    registry = FeedbackHookRegistry()
    registry.register(HookPhase.AFTER_STEP, "my_hook", my_func)
    registry.fire(HookPhase.AFTER_STEP, {"step_id": "s1"})
"""

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import  Callable, Dict, List, Optional

# ── 数据模型 ──

class HookPhase(Enum):
    """Hook 触发阶段"""
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"

@dataclass
class HookEvent:
    """Hook 事件"""
    phase: HookPhase
    step_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "step_id": self.step_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "errors": self.errors,
        }

@dataclass
class HookRegistration:
    """Hook 注册条目"""
    phase: HookPhase
    name: str
    callback: Callable
    priority: int = 0
    enabled: bool = True

# ── Hook 注册表 ──

class FeedbackHookRegistry:
    """
    统一 Hook 注册机制。

    支持 before_step / after_step / on_success / on_failure 四个阶段。
    Hook 之间互不影响，单个 hook 异常不会阻断其他 hook 执行。
    """

    def __init__(self):
        self._hooks: Dict[HookPhase, List[HookRegistration]] = {
            phase: [] for phase in HookPhase
        }

    def register(
        self,
        phase: HookPhase,
        name: str,
        callback: Callable,
        priority: int = 0,
    ):
        """注册 Hook"""
        reg = HookRegistration(
            phase=phase, name=name, callback=callback, priority=priority
        )
        self._hooks[phase].append(reg)
        # 按优先级排序（高优先级先执行）
        self._hooks[phase].sort(key=lambda r: r.priority, reverse=True)

    def unregister(self, phase: HookPhase, name: str):
        """注销 Hook"""
        self._hooks[phase] = [
            h for h in self._hooks[phase] if h.name != name
        ]

    def get_hooks(self, phase: HookPhase) -> List[HookRegistration]:
        """获取指定阶段的所有 Hook"""
        return list(self._hooks.get(phase, []))

    def fire(self, phase: HookPhase, ctx: dict) -> List[str]:
        """
        触发指定阶段的所有 Hook。

        Args:
            phase: Hook 阶段
            ctx: 上下文数据

        Returns:
            错误列表（空=全部成功）
        """
        errors = []
        for reg in self._hooks.get(phase, []):
            if not reg.enabled:
                continue
            try:
                reg.callback(ctx)
            except Exception as e:
                errors.append(f"{reg.name}: {str(e)}")
        return errors

    def fire_event(self, event: HookEvent) -> List[str]:
        """通过 HookEvent 对象触发"""
        return self.fire(event.phase, event.data)

    def list_all(self) -> Dict[str, List[str]]:
        """列出所有已注册的 Hook"""
        return {
            phase.value: [h.name for h in hooks]
            for phase, hooks in self._hooks.items()
        }

# ── 闭环 A: 知识沉淀 Hook ──

class KnowledgeSinkHook:
    """
    闭环 A: Pipeline 步骤完成后自动回写 patterns/

    当步骤失败时，将失败信息写入 patterns/ 目录作为 BadCase 知识。
    """

    def __init__(self, output_dir: str = "harness/knowledge/patterns"):
        self._output_dir = output_dir

    def __call__(self, ctx: dict) -> dict:
        """
        执行知识沉淀。

        ctx 需要包含:
        - step_id: 步骤 ID
        - status: pass/fail
        - error: 错误信息（失败时）
        - category: 知识类目（默认 patterns）
        - title: 知识标题

        Returns:
            {"written": True/False, "path": "..."}
        """
        if ctx.get("status") != "fail":
            return {"written": False}

        os.makedirs(self._output_dir, exist_ok=True)

        step_id = ctx.get("step_id", "unknown")
        title = ctx.get("title", f"failure_{step_id}")
        category = ctx.get("category", "patterns")
        error = ctx.get("error", "")

        entry = {
            "id": f"auto_{step_id}_{int(time.time())}",
            "category": category,
            "title": title,
            "content": {"error": error, "step_id": step_id},
            "tags": ["auto_generated", "badcase"],
            "created_at": time.time(),
            "hit_count": 0,
        }

        safe_name = title.replace("/", "_").replace(" ", "_")[:50]
        path = os.path.join(self._output_dir, f"{safe_name}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        return {"written": True, "path": path}

# ── 闭环 B: 场景生成 Hook ──

class ScenarioGeneratorHook:
    """
    闭环 B: 从知识库 patterns 生成测试场景骨架。

    输入 patterns 列表，输出结构化的测试场景。
    """

    def __call__(self, ctx: dict) -> dict:
        """
        生成测试场景。

        ctx 需要包含:
        - patterns: list[dict] — 知识库中的 pattern 列表

        Returns:
            {"scenarios": [...]}
        """
        patterns = ctx.get("patterns", [])
        if not patterns:
            return {"scenarios": []}

        scenarios = []
        for pattern in patterns:
            title = pattern.get("title", "unknown")
            tags = pattern.get("tags", [])

            scenario = {
                "id": f"SC-{title[:20].replace(' ', '_')}",
                "title": f"[自动生成] {title}",
                "description": f"基于 BadCase '{title}' 生成的测试场景",
                "tags": tags + ["auto_generated"],
                "steps": [
                    {"action": "setup", "description": "准备测试环境"},
                    {"action": "execute", "description": f"复现 '{title}' 场景"},
                    {"action": "assert", "description": "验证修复是否生效"},
                ],
                "priority": "P1" if "P0" in tags else "P2",
                "source_pattern": title,
            }
            scenarios.append(scenario)

        return {"scenarios": scenarios}

# ── 闭环 D: BadCase 采集 Hook ──

class BadCaseCollectorHook:
    """
    闭环 D: 失败用例自动生成 BadCase 记录。

    当步骤失败时，收集失败信息并标记为待分析的 BadCase。
    """

    def __init__(self):
        self._collected: List[dict] = []

    def __call__(self, ctx: dict) -> dict:
        """
        采集 BadCase。

        ctx 需要包含:
        - step_id: 步骤 ID
        - status: pass/fail
        - error: 错误信息
        - case_id: 用例 ID（可选）

        Returns:
            {"collected": True/False, "bad_case": {...}}
        """
        if ctx.get("status") != "fail":
            return {"collected": False}

        bad_case = {
            "case_id": ctx.get("case_id", f"auto_{ctx.get('step_id', 'unknown')}"),
            "step_id": ctx.get("step_id", ""),
            "error": ctx.get("error", ""),
            "timestamp": time.time(),
            "severity": self._classify_severity(ctx.get("error", "")),
            "tags": ["auto_collected"],
        }

        self._collected.append(bad_case)
        return {"collected": True, "bad_case": bad_case}

    def get_collected(self) -> List[dict]:
        """获取所有已采集的 BadCase"""
        return list(self._collected)

    def clear(self):
        """清空已采集的 BadCase"""
        self._collected.clear()

    @staticmethod
    def _classify_severity(error: str) -> str:
        """根据错误信息分类严重度"""
        error_lower = error.lower()
        if any(kw in error_lower for kw in ["timeout", "connection", "500", "502", "503"]):
            return "P0"
        elif any(kw in error_lower for kw in ["assertion", "expected", "mismatch"]):
            return "P1"
        else:
            return "P2"

# ── 闭环 C 扩展: Pipeline 完成回调 ──

class PipelineCompleteHook:
    """
    闭环 C 扩展: Pipeline 执行完成后的回调钩子。

    汇总执行结果，触发知识沉淀和 BadCase 采集。
    """

    def __init__(
        self,
        knowledge_sink: Optional[KnowledgeSinkHook] = None,
        badcase_collector: Optional[BadCaseCollectorHook] = None,
    ):
        self._knowledge_sink = knowledge_sink or KnowledgeSinkHook()
        self._badcase_collector = badcase_collector or BadCaseCollectorHook()

    def __call__(self, ctx: dict) -> dict:
        """
        Pipeline 完成回调。

        ctx 需要包含:
        - pipeline_id: Pipeline ID
        - steps: list[dict] — 各步骤执行结果
        - status: overall status

        Returns:
            {"patterns_written": int, "badcases_collected": int}
        """
        steps = ctx.get("steps", [])
        patterns_written = 0
        badcases_collected = 0

        for step in steps:
            step_ctx = {
                "step_id": step.get("step_id", step.get("id", "")),
                "status": step.get("status", "unknown"),
                "error": step.get("error", ""),
                "title": step.get("title", step.get("step_id", "unknown")),
            }

            # 知识沉淀
            sink_result = self._knowledge_sink(step_ctx)
            if sink_result.get("written"):
                patterns_written += 1

            # BadCase 采集
            collector_result = self._badcase_collector(step_ctx)
            if collector_result.get("collected"):
                badcases_collected += 1

        return {
            "patterns_written": patterns_written,
            "badcases_collected": badcases_collected,
        }

def setup_default_hooks(registry: FeedbackHookRegistry, output_dir: str = "") -> FeedbackHookRegistry:
    """
    为 FeedbackHookRegistry 注册默认四大闭环 Hook。

    Args:
        registry: Hook 注册表
        output_dir: 知识沉淀输出目录

    Returns:
        配置好的 registry
    """
    sink = KnowledgeSinkHook(output_dir=output_dir or "harness/knowledge/patterns")
    scenario_gen = ScenarioGeneratorHook()
    badcase = BadCaseCollectorHook()
    pipeline_complete = PipelineCompleteHook(knowledge_sink=sink, badcase_collector=badcase)

    registry.register(HookPhase.AFTER_STEP, "knowledge_sink", sink, priority=10)
    registry.register(HookPhase.BEFORE_STEP, "scenario_generator", scenario_gen, priority=5)
    registry.register(HookPhase.ON_FAILURE, "badcase_collector", badcase, priority=10)
    registry.register(HookPhase.ON_SUCCESS, "pipeline_complete", pipeline_complete, priority=1)

    return registry
