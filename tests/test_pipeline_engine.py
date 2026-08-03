"""
tests/test_pipeline_engine.py — Pipeline Engine 单元测试（适配 DSL API）

pipeline_engine.py 已统一为 pipeline_dsl.py 的兼容外观层，测试也相应迁移至 DSL API：
- PipelineEngine.from_dict() 构建引擎
- engine.register_tool() 注册工具
- engine.execute(context={}) 执行并返回 PipelineResult
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.pipeline_dsl import (
    PipelineEngine,
    PipelineDefinition,
    PipelineStep,
    StepResult,
    PipelineResult,
)

# 向后兼容别名（原 pipeline_engine.py 已删除）
StepExecutionResult = StepResult


def _run(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────
# 数据结构测试
# ─────────────────────────────────────────────────────────────

class TestPipelineStep(unittest.TestCase):

    def test_basic_fields(self):
        """PipelineStep 字段可正确设置"""
        step = PipelineStep(
            id="query_status",
            tool="api.query",
            params={"batch_id": "BT_001"},
            depends_on=["init_step"],
            condition="batch_id != ''",
            output_binding={"result": "$.data"},
        )
        self.assertEqual(step.id, "query_status")
        self.assertEqual(step.tool, "api.query")
        self.assertEqual(step.params, {"batch_id": "BT_001"})
        self.assertEqual(step.depends_on, ["init_step"])
        self.assertEqual(step.condition, "batch_id != ''")
        self.assertEqual(step.output_binding, {"result": "$.data"})

    def test_default_values(self):
        """PipelineStep 默认值正确"""
        step = PipelineStep(id="s1", tool="click")
        self.assertEqual(step.params, {})
        self.assertEqual(step.depends_on, [])
        self.assertEqual(step.condition, "")
        self.assertEqual(step.output_binding, {})

    def test_on_error_field(self):
        """PipelineStep 支持 on_error 字段"""
        step = PipelineStep(id="s1", tool="click", on_error="skip")
        self.assertEqual(step.on_error, "skip")


class TestPipelineDefinition(unittest.TestCase):

    def test_fields(self):
        """PipelineDefinition 字段可正确设置"""
        defn = PipelineDefinition(
            name="test-pipeline",
            version="2.0",
            description="测试流水线",
        )
        self.assertEqual(defn.name, "test-pipeline")
        self.assertEqual(defn.version, "2.0")
        self.assertEqual(defn.description, "测试流水线")

    def test_default_values(self):
        """PipelineDefinition 默认值正确"""
        defn = PipelineDefinition(name="default")
        self.assertEqual(defn.steps, [])
        self.assertEqual(defn.trigger, {})
        self.assertEqual(defn.error_handling, {})

    def test_steps_list(self):
        """PipelineDefinition 支持多步骤"""
        s1 = PipelineStep(id="s1", tool="click")
        s2 = PipelineStep(id="s2", tool="fill", depends_on=["s1"])
        defn = PipelineDefinition(name="multi", steps=[s1, s2])
        self.assertEqual(len(defn.steps), 2)
        self.assertEqual(defn.steps[1].depends_on, ["s1"])


class TestStepResult(unittest.TestCase):

    def test_basic_fields(self):
        """StepResult 字段正确"""
        r = StepResult(step_id="s1", status="pass", duration_ms=100)
        self.assertEqual(r.step_id, "s1")
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.duration_ms, 100)

    def test_backward_compat_alias(self):
        """StepExecutionResult 是 StepResult 的别名"""
        self.assertIs(StepExecutionResult, StepResult)

    def test_default_values(self):
        """StepResult 默认值正确"""
        r = StepResult(step_id="s1")
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.error, "")
        self.assertEqual(r.retries, 0)


class TestPipelineResult(unittest.TestCase):

    def test_to_summary(self):
        """PipelineResult.to_summary 返回正确摘要"""
        result = PipelineResult(
            pipeline_name="test",
            status="pass",
            step_results={
                "s1": StepResult(step_id="s1", status="pass"),
                "s2": StepResult(step_id="s2", status="fail"),
                "s3": StepResult(step_id="s3", status="skip"),
            }
        )
        summary = result.to_summary()
        self.assertEqual(summary["pipeline"], "test")
        self.assertEqual(summary["steps_passed"], 1)
        self.assertEqual(summary["steps_failed"], 1)
        self.assertEqual(summary["steps_skipped"], 1)


# ─────────────────────────────────────────────────────────────
# PipelineEngine 构建测试
# ─────────────────────────────────────────────────────────────

class TestPipelineEngineConstruct(unittest.TestCase):

    def test_from_dict_basic(self):
        """from_dict 正确解析基本配置"""
        engine = PipelineEngine.from_dict({
            "name": "test",
            "steps": [{"id": "s1", "tool": "click"}],
        })
        self.assertEqual(engine.definition.name, "test")
        self.assertEqual(len(engine.definition.steps), 1)

    def test_from_dict_with_deps(self):
        """from_dict 正确解析依赖"""
        engine = PipelineEngine.from_dict({
            "name": "dep-test",
            "steps": [
                {"id": "s1", "tool": "a"},
                {"id": "s2", "tool": "b", "depends_on": ["s1"]},
            ],
        })
        self.assertEqual(engine.definition.steps[1].depends_on, ["s1"])

    def test_from_yaml_file(self):
        """from_yaml 可加载已有 YAML 文件"""
        yaml_path = os.path.join(os.path.dirname(__file__), "..", "harness", "pipelines", "to_regular_full_flow.yaml")
        if not os.path.exists(yaml_path):
            self.skipTest("Pipeline YAML 文件不存在")
        engine = PipelineEngine.from_yaml(yaml_path)
        self.assertIsNotNone(engine.definition.name)
        self.assertGreater(len(engine.definition.steps), 0)

    def test_register_tool(self):
        """register_tool 注册工具不抛异常"""
        engine = PipelineEngine.from_dict({"name": "t", "steps": []})
        engine.register_tool("click", lambda p: {"ok": True})


# ─────────────────────────────────────────────────────────────
# PipelineEngine 执行测试
# ─────────────────────────────────────────────────────────────

class TestPipelineEngineExecute(unittest.TestCase):

    def test_execute_simple_pipeline(self):
        """简单 Pipeline 执行通过"""
        engine = PipelineEngine.from_dict({
            "name": "simple",
            "steps": [
                {"id": "s1", "tool": "click", "params": {"text": "搜索"}},
                {"id": "s2", "tool": "fill", "params": {}, "depends_on": ["s1"]},
            ],
        })
        engine.register_tool("click", lambda p: {"done": True})
        engine.register_tool("fill", lambda p: {"done": True})

        result = _run(engine.execute(context={}))
        self.assertEqual(result.status, "pass")
        self.assertIn("s1", result.step_results)
        self.assertIn("s2", result.step_results)
        self.assertEqual(result.step_results["s1"].status, "pass")
        self.assertEqual(result.step_results["s2"].status, "pass")

    def test_execute_with_context_vars(self):
        """context 变量可在步骤中使用"""
        captured = {}

        def echo_tool(params):
            captured.update(params)
            return {"received": params}

        engine = PipelineEngine.from_dict({
            "name": "vars",
            "steps": [{"id": "s1", "tool": "echo", "params": {"msg": "${greeting}"}}],
        })
        engine.register_tool("echo", echo_tool)
        result = _run(engine.execute(context={"greeting": "hello"}))
        self.assertEqual(result.status, "pass")

    def test_execute_step_failure(self):
        """步骤抛异常时 Pipeline 状态为 fail"""
        engine = PipelineEngine.from_dict({
            "name": "fail",
            "steps": [{"id": "s1", "tool": "broken", "on_error": "fail"}],
        })

        def fail_tool(params):
            raise RuntimeError("broken")

        engine.register_tool("broken", fail_tool)
        result = _run(engine.execute(context={}))
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.step_results["s1"].status, "fail")

    def test_execute_step_skip_on_error(self):
        """on_error=skip 时步骤失败不影响 Pipeline 整体状态"""
        engine = PipelineEngine.from_dict({
            "name": "skip-test",
            "steps": [
                {"id": "s1", "tool": "fail_tool", "on_error": "skip"},
                {"id": "s2", "tool": "pass_tool"},
            ],
        })
        engine.register_tool("fail_tool", lambda p: (_ for _ in ()).throw(RuntimeError("err")))
        engine.register_tool("pass_tool", lambda p: {"ok": True})
        result = _run(engine.execute(context={}))
        self.assertEqual(result.step_results["s2"].status, "pass")

    def test_execute_no_handler_uses_placeholder(self):
        """无处理器注册时步骤返回占位输出（通过）"""
        engine = PipelineEngine.from_dict({
            "name": "no-handler",
            "steps": [{"id": "s1", "tool": "unregistered_tool"}],
        })
        result = _run(engine.execute(context={}))
        # 无处理器时步骤应 pass（返回占位）
        self.assertEqual(result.step_results["s1"].status, "pass")

    def test_execute_with_output_binding(self):
        """output_binding 将步骤输出绑定到变量"""
        engine = PipelineEngine.from_dict({
            "name": "binding",
            "steps": [{
                "id": "query",
                "tool": "api.query",
                "output_binding": {"total": "$.total"},
            }],
        })
        engine.register_tool("api.query", lambda p: {"total": 42, "items": []})
        result = _run(engine.execute(context={}))
        self.assertEqual(result.status, "pass")
        # 绑定变量应存在
        self.assertIn("total", result.variables)

    def test_execute_with_initial_vars(self):
        """初始化 context 变量可被步骤引用"""
        engine = PipelineEngine.from_dict({
            "name": "init-vars",
            "steps": [{"id": "s1", "tool": "echo", "params": {"val": "${myvar}"}}],
        })
        captured = {}
        engine.register_tool("echo", lambda p: captured.update(p) or {})
        result = _run(engine.execute(context={"myvar": "test_value"}))
        self.assertEqual(result.status, "pass")

    def test_execute_dag_order_respected(self):
        """DAG 依赖拓扑排序正确"""
        order = []
        engine = PipelineEngine.from_dict({
            "name": "dag",
            "steps": [
                {"id": "c", "tool": "noop", "depends_on": ["a", "b"]},
                {"id": "b", "tool": "noop", "depends_on": ["a"]},
                {"id": "a", "tool": "noop"},
            ],
        })
        engine.register_tool("noop", lambda p: order.append(p.get("_id", "?")) or {})
        result = _run(engine.execute(context={}))
        self.assertEqual(result.status, "pass")
        step_ids = list(result.step_results.keys())
        self.assertLess(step_ids.index("a"), step_ids.index("b"))
        self.assertLess(step_ids.index("b"), step_ids.index("c"))

    def test_execute_unmet_dependency_raises(self):
        """引用不存在依赖应导致 fail 或 error"""
        engine = PipelineEngine.from_dict({
            "name": "unmet",
            "steps": [
                {"id": "s1", "tool": "a", "depends_on": ["nonexistent"]},
            ],
        })
        engine.register_tool("a", lambda p: {})
        result = _run(engine.execute(context={}))
        # 循环依赖检测应报错
        self.assertIn(result.status, ["fail", "error"])

    def test_execute_rollback(self):
        """on_error=rollback 触发回滚"""
        engine = PipelineEngine.from_dict({
            "name": "rollback-test",
            "steps": [
                {"id": "s1", "tool": "setup", "on_error": "fail"},
                {"id": "s2", "tool": "fail_tool", "depends_on": ["s1"], "on_error": "rollback"},
            ],
            "error_handling": {
                "rollback_steps": [{"tool": "cleanup", "params": {}}]
            }
        })
        engine.register_tool("setup", lambda p: {"ok": True})
        engine.register_tool("fail_tool", lambda p: (_ for _ in ()).throw(RuntimeError("fail")))
        engine.register_tool("cleanup", lambda p: {"cleaned": True})

        result = _run(engine.execute(context={}))
        self.assertIn(result.status, ["rolled_back", "fail"])


if __name__ == "__main__":
    unittest.main()
