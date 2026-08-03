"""
subsystem_factory.py — 子系统统一工厂

将 impl.py 中散落的 15+ 子系统初始化逻辑收敛为单一入口。
职责：
- 创建所有 Harness 子系统实例
- 返回 Subsystems dataclass，通过属性访问

使用方式:
    from core.subsystem_factory import create_subsystems
    subs = create_subsystems(input_data, run_id, business_type)
    executor = StepExecutor(cdp=cdp, registry=subs.registry, ...)
"""

import os
from dataclasses import dataclass

from core.tool_registry import ToolRegistry
from core.variable_store import VariableStore
from core.assertion_framework import AssertionFramework
from core.evidence_store import EvidenceStore
from core.complexity_router import ComplexityRouter
from core.budget_guard import BudgetGuard
from core.knowledge_base import KnowledgeBase
from core.badcase_collector import BadCaseCollector
from core.failure_classifier import FailureClassifier
from core.circuit_breaker import CircuitBreaker
from core.desensitize_filter import DesensitizeFilter
from core.quality_scorer import QualityScorer
from core.orchestrator import Orchestrator
from core.self_healing import SelfHealingEngine
from core.feedback_loops import FeedbackHookRegistry, setup_default_hooks
from core.evaluation import EvaluationEngine
from core.privacy_guard import PrivacyGuard
from core.metrics_logger import MetricsLogger


@dataclass
class Subsystems:
    """所有 Harness 子系统的聚合容器。"""

    # ── 工具与变量 ──
    registry: ToolRegistry
    variable_store: VariableStore
    assertion: AssertionFramework
    evidence: EvidenceStore

    # ── 路由与预算 ──
    complexity_router: ComplexityRouter
    complexity_result: object          # ComplexityRouter.route() 返回值
    budget_guard: BudgetGuard

    # ── 知识与质量 ──
    kbase: KnowledgeBase
    badcase_collector: BadCaseCollector
    failure_classifier: FailureClassifier
    circuit_breaker: CircuitBreaker
    desensitize_filter: DesensitizeFilter
    quality_scorer: QualityScorer

    # ── 编排与自愈 ──
    orchestrator: Orchestrator
    complexity_level: object           # Orchestrator.judge_complexity() 返回值
    self_healing: SelfHealingEngine
    hook_registry: FeedbackHookRegistry

    # ── 评估与安全 ──
    eval_engine: EvaluationEngine
    privacy_guard: PrivacyGuard

    # ── 度量 ──
    metrics_logger: MetricsLogger


def create_subsystems(input_data: dict, run_id: str, business_type: str) -> Subsystems:
    """
    一次性创建所有子系统实例。

    Args:
        input_data: 测试用例输入 JSON
        run_id: 本次运行 ID
        business_type: 业务类型标识

    Returns:
        Subsystems dataclass 实例
    """
    # 工具注册
    _tools_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema", "tools")
    registry = ToolRegistry()
    registry.load_all(_tools_dir)

    # 基础子系统
    variable_store = VariableStore()
    assertion = AssertionFramework()
    evidence = EvidenceStore(trace_id=run_id, pipeline=business_type)

    # 路由与预算
    complexity_router = ComplexityRouter()
    complexity_result = complexity_router.route(input_data)
    budget_guard = BudgetGuard(limit=1_000_000)

    # 知识与质量
    kbase = KnowledgeBase()
    badcase_collector = BadCaseCollector()
    failure_classifier = FailureClassifier()
    circuit_breaker = CircuitBreaker()
    desensitize_filter = DesensitizeFilter()
    quality_scorer = QualityScorer(business_type=business_type)

    # 编排与自愈
    orchestrator = Orchestrator()
    complexity_level = orchestrator.judge_complexity(input_data)

    # ── LLM 裁决配置 ──
    _base_dir = os.path.dirname(os.path.dirname(__file__))
    _llm_judge_fn = None
    try:
        from core.llm_judge import create_llm_judge, load_llm_config_from_yaml
        _llm_config = load_llm_config_from_yaml(_base_dir)
        if _llm_config:
            _llm_judge_fn = create_llm_judge(_llm_config)
    except Exception as _llm_err:
        import sys
        print(f"[llm_judge] 加载 LLM 配置异常（不影响执行）: {_llm_err}", file=sys.stderr)

    self_healing = SelfHealingEngine(
        scene=input_data.get("scene", input_data.get("env", {}).get("scene")),
        base_dir=_base_dir,
        llm_judge_fn=_llm_judge_fn,
    )
    hook_registry = FeedbackHookRegistry()
    _harness_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "harness", "knowledge", "patterns"
    )
    setup_default_hooks(hook_registry, output_dir=_harness_dir)

    # 评估与安全
    eval_engine = EvaluationEngine()
    privacy_guard = PrivacyGuard()

    # 度量
    metrics_logger = MetricsLogger(task_id=run_id, business_type=business_type)

    return Subsystems(
        registry=registry,
        variable_store=variable_store,
        assertion=assertion,
        evidence=evidence,
        complexity_router=complexity_router,
        complexity_result=complexity_result,
        budget_guard=budget_guard,
        kbase=kbase,
        badcase_collector=badcase_collector,
        failure_classifier=failure_classifier,
        circuit_breaker=circuit_breaker,
        desensitize_filter=desensitize_filter,
        quality_scorer=quality_scorer,
        orchestrator=orchestrator,
        complexity_level=complexity_level,
        self_healing=self_healing,
        hook_registry=hook_registry,
        eval_engine=eval_engine,
        privacy_guard=privacy_guard,
        metrics_logger=metrics_logger,
    )
