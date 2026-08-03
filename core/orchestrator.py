"""
orchestrator.py — 主Agent控制面框架

Harness 编排控制面：
- 复杂度判断节点: 简单 / 中等 / 复杂三档
- Token 预算控制: 设定上限，超额降级
- 并发控制: 并发上限，超额排队
- Agent 接口预留: SubAgent 抽象基类 + AgentRegistry
- 熔断器: 委托 core.circuit_breaker.CircuitBreaker（三态状态机）

使用方式:
    from core.orchestrator import Orchestrator
    orch = Orchestrator.from_config("harness/orchestrator_config.yaml")
    level = orch.judge_complexity(task_input)
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import  Awaitable, Callable, Optional

from core.circuit_breaker import CircuitBreaker
from core.knowledge_base import KnowledgeBase, KnowledgeCompletenessValidator

try:
    import yaml
except ImportError:
    yaml = None

class ComplexityLevel(Enum):
    """复杂度级别"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"

# ── 预算控制 ──

@dataclass
class BudgetController:
    """Token 预算控制器"""
    max_tokens: int = 1_000_000
    used_tokens: int = 0

    @property
    def within_budget(self) -> bool:
        return self.used_tokens < self.max_tokens

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    @property
    def usage_pct(self) -> float:
        if self.max_tokens <= 0:
            return 100.0
        return round(self.used_tokens / self.max_tokens * 100, 1)

    def consume(self, tokens: int):
        """消耗 token"""
        self.used_tokens += tokens

    def reset(self):
        """重置预算"""
        self.used_tokens = 0

    def should_degrade(self) -> bool:
        """是否应降级为 Plan 模式"""
        return not self.within_budget

# ── 子Agent 接口 ──

class SubAgent(ABC):
    """子Agent 抽象基类"""
    name: str = ""

    @abstractmethod
    def execute(self, task: dict) -> dict:
        """执行任务，返回结果"""
        ...

class AgentRegistry:
    """Agent 注册表"""

    def __init__(self):
        self._agents: dict[str, SubAgent] = {}

    def register(self, agent: SubAgent):
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[SubAgent]:
        return self._agents.get(name)

    def unregister(self, name: str):
        self._agents.pop(name, None)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

# ── 编排器 ──

@dataclass
class OrchestratorConfig:
    """编排器配置"""
    max_tokens: int = 1_000_000
    max_concurrency: int = 5
    circuit_breaker_failures: int = 3
    circuit_breaker_rate: float = 0.4
    simple_threshold: dict = field(default_factory=lambda: {"steps": 3, "tools": 2})
    complex_threshold: dict = field(default_factory=lambda: {"steps": 10, "tools": 5, "conditions": 3})

class Orchestrator:
    """
    主Agent控制面：复杂度判断 + 预算 + 并发 + 熔断。
    """

    def __init__(
        self,
        max_tokens: int = 1_000_000,
        max_concurrency: int = 5,
        circuit_breaker_failures: int = 3,
        circuit_breaker_rate: float = 0.4,
        knowledge_base: KnowledgeBase = None,
    ):
        self._config = OrchestratorConfig(
            max_tokens=max_tokens,
            max_concurrency=max_concurrency,
            circuit_breaker_failures=circuit_breaker_failures,
            circuit_breaker_rate=circuit_breaker_rate,
        )
        self._budget = BudgetController(max_tokens=max_tokens)
        self._breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_failures,
            failure_rate_threshold=circuit_breaker_rate,
        )  # 委托 core.circuit_breaker 正式版（三态状态机）
        self._agent_registry = AgentRegistry()
        self._active_slots = 0
        self._kb = knowledge_base
        self._knowledge_validator = (
            KnowledgeCompletenessValidator(knowledge_base) if knowledge_base else None
        )

    @classmethod
    def from_config(cls, config_path: str) -> "Orchestrator":
        """从 YAML 配置加载"""
        if not os.path.exists(config_path) or not yaml:
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            max_tokens=data.get("max_tokens", 1_000_000),
            max_concurrency=data.get("max_concurrency", 5),
            circuit_breaker_failures=data.get("circuit_breaker_failures", 3),
            circuit_breaker_rate=data.get("circuit_breaker_rate", 0.4),
        )

    # ── 复杂度判断 ──

    def judge_complexity(self, task_input: dict) -> ComplexityLevel:
        """
        基于输入特征判断任务复杂度。

        特征: steps(步骤数), tools(工具数), conditions(条件数)
        """
        steps = task_input.get("steps", 0)
        tools = task_input.get("tools", 0)
        conditions = task_input.get("conditions", 0)

        # steps/tools/conditions 可能是列表，取长度作为计数
        if isinstance(steps, list):
            steps = len(steps)
        if isinstance(tools, list):
            tools = len(tools)
        if isinstance(conditions, list):
            conditions = len(conditions)

        ct = self._config.complex_threshold
        st = self._config.simple_threshold

        if (steps >= ct.get("steps", 10)
                or tools >= ct.get("tools", 5)
                or conditions >= ct.get("conditions", 3)):
            return ComplexityLevel.COMPLEX

        if (steps > st.get("steps", 3)
                or tools > st.get("tools", 2)):
            return ComplexityLevel.MEDIUM

        return ComplexityLevel.SIMPLE

    # ── 预算控制 ──

    @property
    def budget(self) -> BudgetController:
        return self._budget

    def consume_tokens(self, tokens: int):
        self._budget.consume(tokens)

    # ── 并发控制 ──

    @property
    def max_concurrency(self) -> int:
        return self._config.max_concurrency

    @property
    def active_count(self) -> int:
        return self._active_slots

    @property
    def queued_count(self) -> int:
        return 0  # 预留：实际排队数需外部调度器维护

    def acquire_slot(self) -> bool:
        """获取并发槽"""
        if self._active_slots < self._config.max_concurrency:
            self._active_slots += 1
            return True
        return False

    def release_slot(self):
        """释放并发槽"""
        if self._active_slots > 0:
            self._active_slots -= 1

    async def run_concurrent(
        self,
        tasks: list[Callable[[], Awaitable]],
        max_concurrency: int = None,
    ) -> list[dict]:
        """并发执行多个异步任务，受 max_concurrency 限制。

        每个 task 是 async 无参 callable。返回结果列表（与 tasks 顺序对齐），
        失败的任务返回 {"error": str(exception)}。

        Args:
            tasks: 异步任务列表，每个为 () -> Awaitable
            max_concurrency: 并发上限（None 则使用 self.max_concurrency）

        Returns:
            与 tasks 等长的结果列表
        """
        limit = max_concurrency or self._config.max_concurrency
        semaphore = asyncio.Semaphore(limit)
        results: list = [None] * len(tasks)

        async def _run_one(idx: int, task_fn: Callable):
            async with semaphore:
                self._active_slots += 1
                try:
                    results[idx] = await task_fn()
                except Exception as e:
                    results[idx] = {"error": str(e)}
                finally:
                    self._active_slots -= 1

        await asyncio.gather(
            *[_run_one(i, fn) for i, fn in enumerate(tasks)]
        )
        return results

    # ── 熔断 ──

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._breaker

    def record_result(self, status: str):
        """委托给正式版 CircuitBreaker.record_result()"""
        self._breaker.record_result(status)

    @property
    def is_circuit_open(self) -> bool:
        return self._breaker.should_break()

    # ── Agent 注册 ──

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    def register_agent(self, agent: SubAgent):
        self._agent_registry.register(agent)

    # ── 知识完整性校验 ──

    @property
    def knowledge_validator(self) -> Optional[KnowledgeCompletenessValidator]:
        return self._knowledge_validator

    def set_knowledge_base(self, kb: KnowledgeBase):
        """注入或替换知识库"""
        self._kb = kb
        self._knowledge_validator = KnowledgeCompletenessValidator(kb)

    def check_knowledge_completeness(
        self,
        required_topics: list[str] = None,
        output_text: str = None,
    ):
        """
        前置知识完整性校验。

        在 Agent 输出前调用，检查知识库是否足够支撑当前主题。
        如果注入了 output_text，还会检测推测性表述。

        Returns:
            CompletenessReport 或 None（未配置知识库时）
        """
        if not self._knowledge_validator:
            return None

        if output_text:
            return self._knowledge_validator.validate_output(
                output_text, required_topics=required_topics
            )
        return self._knowledge_validator.validate(
            required_topics=required_topics
        )

    # ── 综合状态 ──

    def get_status(self) -> dict:
        status = {
            "budget": {
                "used": self._budget.used_tokens,
                "max": self._budget.max_tokens,
                "usage_pct": self._budget.usage_pct,
                "should_degrade": self._budget.should_degrade(),
            },
            "concurrency": {
                "active": self._active_slots,
                "max": self._config.max_concurrency,
            },
            "circuit_breaker": self._breaker.get_report(),
            "agents": self._agent_registry.list_agents(),
        }
        if self._kb:
            status["knowledge"] = self._kb.get_stats()
        return status
