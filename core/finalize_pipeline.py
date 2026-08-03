"""
finalize_pipeline.py — 收尾流水线

基于 PipelineEngine (pipeline_dsl.py) 驱动的收尾流程：
- 从 YAML 加载 DAG 定义（harness/pipelines/finalize_flow.yaml）
- 注册工具处理函数
- 按拓扑顺序执行，单步失败 on_error=skip 不阻断后续

使用方式:
    from core.finalize_pipeline import FinalizePipeline, FinalizeContext
    ctx = FinalizeContext(cdp=cdp, artifacts=artifacts, ...)
    finalizer = FinalizePipeline(ctx)
    await finalizer.run(output)
"""

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.pipeline_dsl import PipelineEngine

@dataclass
class FinalizeContext:
    """FinalizePipeline 运行上下文。

    按职责分组封装所有依赖，消除 21 个位置参数的长签名。
    """

    # ── 运行时资源 ──
    cdp: Any = None
    recorder: Any = None
    capture_manager: Any = None
    checkpoint_manager: Any = None

    # ── 度量与产物 ──
    artifacts: Any = None
    metrics_logger: Any = None
    evidence: Any = None

    # ── 评估与质量 ──
    assertion: Any = None
    eval_engine: Any = None
    quality_scorer: Any = None
    privacy_guard: Any = None

    # ── 治理子系统 ──
    badcase_collector: Any = None
    budget_guard: Any = None
    circuit_breaker: Any = None
    failure_classifier: Any = None
    kbase: Any = None
    orchestrator: Any = None
    hook_registry: Any = None

    # ── 执行元信息 ──
    input_data: dict = field(default_factory=dict)
    run_id: str = ""
    business_type: str = "unknown"
    complexity_result: Any = None
    complexity_level: Any = None

    # ── 优化配置 ──
    screenshot_external: bool = True
    output_compact: bool = True
    max_response_size_kb: int = 50

class FinalizePipeline:
    """
    收尾流水线：按顺序执行所有收尾步骤，单步失败不阻断后续步骤。
    """

    def __init__(self, ctx: FinalizeContext = None, **kwargs):
        """
        Args:
            ctx: FinalizeContext 实例（推荐）。
            **kwargs: 向后兼容的命名参数，自动转为 FinalizeContext。
        """
        if ctx is None:
            ctx = FinalizeContext(**kwargs)
        self._cdp = ctx.cdp
        self._recorder = ctx.recorder
        self._capture = ctx.capture_manager
        self._artifacts = ctx.artifacts
        self._metrics_logger = ctx.metrics_logger
        self._assertion = ctx.assertion
        self._evidence = ctx.evidence
        self._eval_engine = ctx.eval_engine
        self._privacy_guard = ctx.privacy_guard
        self._quality_scorer = ctx.quality_scorer
        self._badcase_collector = ctx.badcase_collector
        self._budget_guard = ctx.budget_guard
        self._circuit_breaker = ctx.circuit_breaker
        self._failure_classifier = ctx.failure_classifier
        self._kbase = ctx.kbase
        self._orchestrator = ctx.orchestrator
        self._hook_registry = ctx.hook_registry
        self._input_data = ctx.input_data
        self._run_id = ctx.run_id
        self._business_type = ctx.business_type
        self._complexity_result = ctx.complexity_result
        self._complexity_level = ctx.complexity_level
        self._screenshot_external = ctx.screenshot_external
        self._output_compact = ctx.output_compact
        self._max_response_size_kb = ctx.max_response_size_kb
        self._ckpt = ctx.checkpoint_manager

        # 加载 Pipeline YAML 定义
        self._pipeline = self._load_pipeline()

    def _load_pipeline(self) -> Optional[PipelineEngine]:
        """Load the finalize pipeline YAML and register tool handlers."""
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "harness", "pipelines", "finalize_flow.yaml"
        )
        if not os.path.exists(yaml_path):
            return None
        engine = PipelineEngine.from_yaml(yaml_path)
        # 注册工具处理函数
        engine.register_tool("video_recorder.stop", self._tool_stop_recording)
        engine.register_tool("capture_manager.flush", self._tool_flush_capture)
        engine.register_tool("cdp.disconnect", self._tool_disconnect)
        engine.register_tool("metrics_logger.flush", self._tool_flush_metrics)
        engine.register_tool("evidence_store.save", self._tool_persist_evidence)
        engine.register_tool("artifacts.save_output", self._tool_save_output)
        engine.register_tool("knowledge_updater.apply", self._tool_knowledge_update)
        engine.register_tool("badcase_collector.collect", self._tool_badcase_collect)
        engine.register_tool("quality_scorer.score", self._tool_quality_score)
        engine.register_tool("eval_engine.evaluate", self._tool_evaluation)
        engine.register_tool("privacy_guard.sanitize", self._tool_privacy_sanitize)
        engine.register_tool("artifacts.finalize", self._tool_finalize_artifacts)
        # ── 全托管架构新增工具（四大能力落地）──
        engine.register_tool("dual_factor.verdict", self._tool_dual_factor_verdict)
        engine.register_tool("kbase_promotion.evaluate", self._tool_kbase_promotion)
        engine.register_tool("contract_verifier.verify", self._tool_contract_verify)
        engine.register_tool("acceptance_report.generate", self._tool_acceptance_report)
        return engine

    async def run(self, output: dict, failure_reports: list = None):
        """执行完整收尾流水线。就地修改 output。

        若 Pipeline YAML 已加载，通过 PipelineEngine 拓扑执行；
        否则 fallback 到顺序执行以确保向后兼容。
        """
        # 存储 output 和 failure_reports 以供工具处理函数使用
        self._output = output
        self._failure_reports = failure_reports or []
        self._metrics_report = None

        if self._pipeline:
            # Pipeline 驱动模式：通过 DAG 拓扑顺序执行各步骤
            import asyncio
            result = await self._pipeline.execute(context={
                "run_id": self._run_id,
                "business_type": self._business_type,
            })
            # Pipeline 执行完成后补充报告字段
            self._write_reports(output, failure_reports)
        else:
            # Fallback：顺序执行（同原始 impl.py 行为）
            await self._run_sequential(output, failure_reports)

        # ── 产物自动清理（保留 7 天，防止本地膨胀）──
        try:
            from core.artifact_manager import ArtifactManager
            ArtifactManager.cleanup_old_runs(retention_days=7)
        except Exception as _clean_err:
            import sys as _sys
            print(f"[finalize] 产物清理异常（忽略）: {_clean_err}", file=_sys.stderr)

        # ── 跨 run AI 内核指标聚合（不影响主流程）──
        try:
            from core.ai_metrics_aggregator import AiMetricsAggregator
            _agg = AiMetricsAggregator()
            _rec = _agg.record(
                output=output,
                run_id=self._run_id,
                business_type=self._business_type or "unknown",
                input_data=self._input_data,
            )
            output["aiMetricsRecord"] = {
                "run_id": _rec.get("run_id"),
                "timestamp": _rec.get("timestamp"),
            }
        except Exception as _e:
            import sys as _sys
            print(f"[finalize] ai_metrics_aggregator 落盘异常（忽略）: {_e}", file=_sys.stderr)

        # ── Flaky test 历史落盘（对标 Cypress Cloud Flake Detection 2025）──
        try:
            from core.flaky_detector import FlakyDetector
            _fd = FlakyDetector()
            # 从 input_data 提取用例标识
            _case_id = (self._input_data or {}).get("id") or self._run_id or "unknown"
            _final_status = output.get("status", "unknown")
            # 失败堆栈：从 releaseDecision / error 拼接
            _err_parts = []
            _release = output.get("releaseDecision") or {}
            for w in _release.get("warnings", []):
                _err_parts.append(str(w))
            _err_obj = output.get("error") or {}
            if isinstance(_err_obj, dict) and _err_obj.get("message"):
                _err_parts.append(str(_err_obj["message"]))
            _err_sig = " | ".join(_err_parts) if _err_parts else ""
            _fd.record(
                case_id=_case_id,
                status=_final_status if _final_status in ("pass", "fail") else "pass",
                duration_ms=int(output.get("duration", 0)),
                error_signature=_err_sig,
                run_id=self._run_id or "",
                business_type=self._business_type or "unknown",
            )
            output["flakyRecord"] = {
                "case_id": _case_id,
                "status": _final_status,
                "duration_ms": int(output.get("duration", 0)),
                "error_signature_preview": _err_sig[:200],
            }
        except Exception as _e:
            import sys as _sys
            print(f"[finalize] flaky_detector 落盘异常（忽略）: {_e}", file=_sys.stderr)

    # ── Pipeline Tool Handlers ──

    async def _tool_stop_recording(self, params):
        if self._recorder:
            video_path = await self._recorder.stop()
            if video_path:
                self._output["artifacts"]["videoPath"] = video_path
        return {"stopped": True}

    async def _tool_flush_capture(self, params):
        if self._capture:
            await self._capture.flush_pending_bodies(timeout=params.get("timeout", 5.0))
            requests_out = self._capture.get_captured_requests()
            self._output["capture"]["requests"] = requests_out
            self._artifacts.save_capture(requests_out)
            if self._input_data.get("capture", {}).get("exportHAR"):
                har_path = self._artifacts.save_har(requests_out)
                self._output["capture"]["harPath"] = har_path
        return {"flushed": True}

    async def _tool_disconnect(self, params):
        await self._cdp.disconnect()
        return {"disconnected": True}

    async def _tool_flush_metrics(self, params):
        from datetime import datetime
        output = self._output
        output["duration"] = int((time.time() - _parse_time(output["startTime"])) * 1000)

        # LLM 日志
        for llm_call in self._input_data.get("llm", {}).get("calls", []):
            self._metrics_logger.log_llm_call(
                step=llm_call.get("step", "llm_plan"),
                action=llm_call.get("action", "LLM call"),
                token_used=llm_call.get("tokenUsed", 0),
                confidence=llm_call.get("confidence", 0.0),
                result=llm_call.get("result", "success"),
                duration_ms=llm_call.get("durationMs", 0),
                error_code=llm_call.get("errorCode"),
            )

        from core.metrics_collector import MetricsCollector
        _metrics_path = self._metrics_logger.flush(self._artifacts.run_dir)
        self._artifacts._register("metrics", _metrics_path)

        _collector = MetricsCollector(
            task_id=self._run_id,
            business_type=self._business_type,
            overall_status=output.get("status", "error"),
            task_duration_ms=output.get("duration", 0),
        )
        self._metrics_report = _collector.compute(self._metrics_logger.entries)
        _report_path = MetricsCollector.save_report(self._metrics_report, self._artifacts.run_dir)
        self._artifacts._register("metrics_report", _report_path)
        output["metrics"] = self._metrics_report.to_summary_dict()
        output["metrics"]["fullReportPath"] = _report_path
        return {"metrics_path": _metrics_path}

    async def _tool_persist_evidence(self, params):
        output = self._output
        # Post-Assert
        post_asserts = self._input_data.get("post_asserts")
        if post_asserts:
            self._assertion.run_post_asserts(output, post_asserts)

        _assertion_summary = self._assertion.to_summary()
        if _assertion_summary["total"] > 0:
            output["assertions"] = _assertion_summary
            if self._assertion.has_critical_failures():
                output["status"] = "fail"

        _failed_assertions = self._assertion.get_failed_results("CRITICAL")
        if _failed_assertions:
            self._evidence.set_conclusion(f"执行失败: {len(_failed_assertions)} 个 CRITICAL 断言未通过")
        elif output["status"] == "pass":
            self._evidence.set_conclusion("执行通过，所有断言和步骤正常")
        else:
            self._evidence.set_conclusion(f"执行状态: {output['status']}")

        _evidence_path = self._evidence.save(self._artifacts.run_dir)
        self._artifacts._register("evidence", _evidence_path)
        output["artifacts"]["evidencePath"] = _evidence_path
        output["evidence"] = self._evidence.to_summary_dict()
        return {"evidence_path": _evidence_path}

    async def _tool_save_output(self, params):
        self._artifacts.save_output(self._output)
        return {"saved": True}

    async def _tool_knowledge_update(self, params):
        from core.knowledge_updater import KnowledgeUpdater
        page_url = self._input_data.get("context", {}).get("url") or \
                   self._input_data.get("context", {}).get("urlPattern", "")
        updater = KnowledgeUpdater(page_url=page_url)
        ku_summary = updater.apply(output=self._output, input_data=self._input_data)
        self._output["artifacts"]["knowledgeUpdate"] = ku_summary
        self._artifacts.save_knowledge_update(ku_summary)
        return ku_summary

    async def _tool_badcase_collect(self, params):
        _badcases = self._badcase_collector.collect(
            self._output,
            self._evidence.to_summary_dict() if hasattr(self._evidence, 'to_summary_dict') else {}
        )
        if _badcases:
            _patterns_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "patterns")
            self._badcase_collector.save_to_patterns(_badcases, _patterns_dir)
            self._output["badcaseCount"] = len(_badcases)
        return {"badcases": len(_badcases) if _badcases else 0}

    async def _tool_quality_score(self, params):
        _quality_report = self._quality_scorer.score(
            self._metrics_report,
            self._output.get("assertions", {}),
            self._output.get("evidence", {}),
            self._output.get("steps", []),
        )
        self._output["qualityRating"] = _quality_report.rating
        self._output["qualityReport"] = _quality_report.to_dict()
        return {"rating": _quality_report.rating}

    async def _tool_evaluation(self, params):
        from core.evaluation import LaunchRating
        output = self._output
        _pass_steps = sum(1 for s in output.get("steps", []) if s.get("status") == "pass")
        _total_steps = len(output.get("steps", [])) or 1
        _assertion_pass_rate = (
            output.get("assertions", {}).get("passed", 0) /
            max(output.get("assertions", {}).get("total", 1), 1)
        )
        _eval_metrics = {
            "pass_rate": _pass_steps / _total_steps,
            "assertion_pass_rate": _assertion_pass_rate,
            "step_count": _total_steps,
            "duration_ms": output.get("duration", 0),
            "retry_count": sum(s.get("retries", 0) for s in output.get("steps", [])),
            "heal_count": sum(1 for s in output.get("steps", []) if s.get("healAttempt")),
        }
        _eval_report = self._eval_engine.evaluate(_eval_metrics)
        _launch_rating = LaunchRating.from_report(_eval_report)
        output["launchRating"] = _launch_rating.value
        output["evalRadar"] = _eval_report.to_radar_data()
        return {"rating": _launch_rating.value}

    async def _tool_privacy_sanitize(self, params):
        self._output.update(self._privacy_guard.sanitize_dict(self._output))
        return {"sanitized": True}

    async def _tool_finalize_artifacts(self, params):
        output = self._output
        if self._output_compact:
            _compact_output(output, self._max_response_size_kb)
        manifest = self._artifacts.finalize()
        output["artifacts"]["runDir"] = self._artifacts.run_dir
        output["artifacts"]["manifest"] = manifest
        return {"manifest": manifest}

    # ── 全托管架构新增 Pipeline Tool Handlers ──

    async def _tool_dual_factor_verdict(self, params):
        """双因子裁决：规则层+LLM层一致性裁决 + P0/P1/P2 分级放行"""
        from core.dual_factor_verdict import DualFactorVerdictEngine
        output = self._output
        engine = DualFactorVerdictEngine(base_dir=os.path.dirname(os.path.dirname(__file__)))
        failed_steps = [s for s in output.get("steps", []) if s.get("status") in ("error", "fail")]
        if not failed_steps:
            return {"verdicts": 0, "suggestion": "全部通过"}
        verdicts = engine.verdict_batch(failed_steps)
        decision = engine.release_decision(verdicts)
        output["dualFactorVerdict"] = decision
        output["releaseDecision"] = {
            "blocked": decision["blocked"],
            "release_level": decision["release_level"],
            "warnings": decision["p1_warnings"],
            "skipped": decision["p2_skipped"],
            "human_reviews": decision["human_reviews"],
            "skip_rate": decision["skip_rate"],
            "suggestion": decision["suggestion"],
        }
        return {"release_level": decision["release_level"], "blocked": decision["blocked"]}

    async def _tool_kbase_promotion(self, params):
        """KBase 量化晋升：检索≥3/需求≥2/7天窗口"""
        from core.kbase_promotion import KBasePromotionEngine
        output = self._output
        promo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "kbase_promotion_tracking.json")
        promo = KBasePromotionEngine(tracking_path=promo_path)
        page_url = self._input_data.get("context", {}).get("urlPattern", "")
        req_id = self._input_data.get("requirementId", "")
        if page_url:
            promo.record_search_hit(f"page#{page_url}", requirement_id=req_id, session_id=self._run_id)
        result = promo.execute_promotion(dry_run=False)
        output["kbasePromotion"] = result
        return {"promoted": len(result.get("promoted", []))}

    async def _tool_contract_verify(self, params):
        """五契约校验：C1数据/C2控制/C3反馈/C4隔离/C5指标"""
        from core.contract_verifier import ContractVerifier, StageDiffMatrix, EvidencePack
        output = self._output
        cv = ContractVerifier()
        diff_matrix = StageDiffMatrix()
        for s in output.get("steps", []):
            stage = s.get("type", f"step{s.get('index', 0)}")
            diff_matrix.capture_before(stage, {"status": "pending"})
            diff_matrix.capture_after(stage, {"status": s.get("status", "unknown")})
        ev_pack = EvidencePack(run_id=self._run_id)
        for req in output.get("capture", {}).get("requests", [])[:10]:
            ev_pack.add_network_capture(
                url=req.get("url", ""), method=req.get("method", "GET"),
                status=req.get("status", 0), rt_ms=req.get("durationMs", 0),
            )
        report = cv.verify_all(output, diff_matrix, ev_pack)
        output["contractVerification"] = report.to_dict()
        return {"passed": report.passed, "compliance": f"{report.passed_checks}/{report.total_checks}"}

    async def _tool_acceptance_report(self, params):
        """验收报告 SOP 对齐：工具/Agent/产品三阶段标准 + 证据链，上传钉钉知识库"""
        from core.acceptance_report import AcceptanceReportGenerator
        from core.report_uploader import upload_to_dingtalk, F88_WORKSPACE_ID, F88_REPORT_FOLDER_ID
        output = self._output
        gen = AcceptanceReportGenerator(
            run_id=self._run_id,
            requirement_id=self._input_data.get("requirementId", ""),
        )
        total_steps = len(output.get("steps", []))
        passed_steps = sum(1 for s in output.get("steps", []) if s.get("status") == "pass")
        gen.add_agent_result(
            total_tasks=total_steps,
            completed_tasks=passed_steps,
            avg_duration_s=output.get("duration", 0) // 1000,
            consistency_total=total_steps,
            consistency_passed=passed_steps,
        )
        gen.add_evidence_from_output(output)
        report = gen.generate()
        output["acceptanceReport"] = report.to_dict()
        output["acceptanceReportMarkdown"] = report.markdown
        # 上传钉钉知识库（不留本地）
        try:
            req_name = self._input_data.get("requirementName", "") or self._input_data.get("requirementId", "") or self._run_id
            doc_url = upload_to_dingtalk(
                title=f"{req_name}验收报告",
                markdown=report.markdown,
                workspace_id=self._input_data.get("dingtalkWorkspaceId", F88_WORKSPACE_ID),
                folder_id=self._input_data.get("dingtalkFolderId", F88_REPORT_FOLDER_ID),
            )
            output["artifacts"]["acceptanceReportUrl"] = doc_url
        except Exception as e:
            output["acceptanceReportUploadError"] = str(e)
        return {"passed": report.overall_passed, "url": output.get("artifacts", {}).get("acceptanceReportUrl", "")}

    # ── Pipeline 执行后报告字段补充 ──

    def _write_reports(self, output: dict, failure_reports: list = None):
        """在 Pipeline 执行完成后，补充非工具步骤的报告字段。"""
        # Knowledge Base 检索频次
        try:
            _page_url = self._input_data.get("context", {}).get("urlPattern", "")
            if _page_url:
                _kb_results = self._kbase.search(_page_url, limit=5)
                for _r in _kb_results:
                    self._kbase.record_hit(_r.entry)
        except Exception as e:
            print(f"[finalize] knowledge_base 检索异常: {e}", file=sys.stderr)

        # 复杂度/预算/熔断报告
        output["complexity"] = {
            "level": self._complexity_level.value if hasattr(self._complexity_level, 'value') else str(self._complexity_level),
            **(self._complexity_result if isinstance(self._complexity_result, dict) else {})
        }
        output["budgetReport"] = self._budget_guard.get_report()
        output["circuitBreaker"] = self._circuit_breaker.get_report()

        # 失败分级放行决策
        if failure_reports:
            try:
                _release = self._failure_classifier.get_release_decision(failure_reports)
                output["releaseDecision"] = {
                    "blocked": _release.get("blocked", False),
                    "warnings": _release.get("warnings", []),
                    "skipped": _release.get("skipped", []),
                }
            except Exception as e:
                print(f"[finalize] release_decision 异常: {e}", file=sys.stderr)

    # ── Fallback 顺序执行 ──

    async def _run_sequential(self, output: dict, failure_reports: list = None):
        """顺序执行收尾流程（当 YAML 不存在时的 fallback）。"""
        if self._recorder:
            try:
                video_path = await self._recorder.stop()
                if video_path:
                    output["artifacts"]["videoPath"] = video_path
            except Exception as e:
                print(f"[finalize] video_recorder.stop 异常: {e}", file=sys.stderr)

        # ── 等待 body fetch 完成 ──
        if self._capture:
            await self._capture.flush_pending_bodies(timeout=5.0)

        # ── 整理抓包结果 ──
        if self._capture:
            requests_out = self._capture.get_captured_requests()
            output["capture"]["requests"] = requests_out
            self._artifacts.save_capture(requests_out)

            if self._input_data.get("capture", {}).get("exportHAR"):
                har_path = self._artifacts.save_har(requests_out)
                output["capture"]["harPath"] = har_path

        # ── 断开浏览器 ──
        try:
            await self._cdp.disconnect()
        except Exception as e:
            print(f"[finalize] cdp.disconnect 异常: {e}", file=sys.stderr)

        # ── 计算时长 ──
        from datetime import datetime
        output["duration"] = int(
            (time.time() - _parse_time(output["startTime"])) * 1000
        )

        # ── LLM 调用日志采集 ──
        llm_cfg = self._input_data.get("llm", {})
        for llm_call in llm_cfg.get("calls", []):
            self._metrics_logger.log_llm_call(
                step=llm_call.get("step", "llm_plan"),
                action=llm_call.get("action", "LLM call"),
                token_used=llm_call.get("tokenUsed", 0),
                confidence=llm_call.get("confidence", 0.0),
                result=llm_call.get("result", "success"),
                duration_ms=llm_call.get("durationMs", 0),
                error_code=llm_call.get("errorCode"),
            )

        # ── Metrics 持久化 ──
        from core.metrics_collector import MetricsCollector
        _metrics_path = self._metrics_logger.flush(self._artifacts.run_dir)
        self._artifacts._register("metrics", _metrics_path)

        _collector = MetricsCollector(
            task_id=self._run_id,
            business_type=self._business_type,
            overall_status=output.get("status", "error"),
            task_duration_ms=output.get("duration", 0),
        )
        _metrics_report = _collector.compute(self._metrics_logger.entries)
        _report_path = MetricsCollector.save_report(_metrics_report, self._artifacts.run_dir)
        self._artifacts._register("metrics_report", _report_path)

        output["metrics"] = _metrics_report.to_summary_dict()
        output["metrics"]["fullReportPath"] = _report_path

        # ── Post-Assert（后置断言）──
        post_asserts = self._input_data.get("post_asserts")
        if post_asserts:
            self._assertion.run_post_asserts(output, post_asserts)

        # ── 断言摘要写入 output ──
        _assertion_summary = self._assertion.to_summary()
        if _assertion_summary["total"] > 0:
            output["assertions"] = _assertion_summary
            if self._assertion.has_critical_failures():
                output["status"] = "fail"

        # ── Evidence Store 持久化 ──
        _failed_assertions = self._assertion.get_failed_results("CRITICAL")
        if _failed_assertions:
            self._evidence.set_conclusion(f"执行失败: {len(_failed_assertions)} 个 CRITICAL 断言未通过")
        elif output["status"] == "pass":
            self._evidence.set_conclusion("执行通过，所有断言和步骤正常")
        else:
            self._evidence.set_conclusion(f"执行状态: {output['status']}")

        _evidence_path = self._evidence.save(self._artifacts.run_dir)
        self._artifacts._register("evidence", _evidence_path)
        output["artifacts"]["evidencePath"] = _evidence_path
        output["evidence"] = self._evidence.to_summary_dict()

        # ── 先保存完整 output ──
        self._artifacts.save_output(output)

        # ── 上下文优化精简 ──
        if self._output_compact:
            _compact_output(output, self._max_response_size_kb)
        manifest = self._artifacts.finalize()
        output["artifacts"]["runDir"] = self._artifacts.run_dir
        output["artifacts"]["manifest"] = manifest

        # ── Knowledge Update ──
        try:
            from core.knowledge_updater import KnowledgeUpdater
            page_url = self._input_data.get("context", {}).get("url") or \
                       self._input_data.get("context", {}).get("urlPattern", "")
            updater = KnowledgeUpdater(page_url=page_url)
            ku_summary = updater.apply(output=output, input_data=self._input_data)
            output["artifacts"]["knowledgeUpdate"] = ku_summary
            self._artifacts.save_knowledge_update(ku_summary)
        except Exception as ku_err:
            output["artifacts"]["knowledgeUpdateError"] = str(ku_err)

        # ── BadCase Collector ──
        try:
            _badcases = self._badcase_collector.collect(
                output,
                self._evidence.to_summary_dict() if hasattr(self._evidence, 'to_summary_dict') else {}
            )
            if _badcases:
                _patterns_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "patterns")
                self._badcase_collector.save_to_patterns(_badcases, _patterns_dir)
                output["badcaseCount"] = len(_badcases)
        except Exception as _bc_err:
            output["badcaseError"] = str(_bc_err)

        # ── Quality Scorer ──
        try:
            _quality_report = self._quality_scorer.score(
                _metrics_report,
                output.get("assertions", {}),
                output.get("evidence", {}),
                output.get("steps", []),
            )
            output["qualityRating"] = _quality_report.rating
            output["qualityReport"] = _quality_report.to_dict()
        except Exception as _qs_err:
            output["qualityError"] = str(_qs_err)

        # ── Evaluation 五维评估 ──
        try:
            from core.evaluation import LaunchRating
            _pass_steps = sum(1 for s in output.get("steps", []) if s.get("status") == "pass")
            _total_steps = len(output.get("steps", [])) or 1
            _assertion_pass_rate = (
                output.get("assertions", {}).get("passed", 0) /
                max(output.get("assertions", {}).get("total", 1), 1)
            )
            _eval_metrics = {
                "pass_rate": _pass_steps / _total_steps,
                "assertion_pass_rate": _assertion_pass_rate,
                "step_count": _total_steps,
                "duration_ms": output.get("duration", 0),
                "retry_count": sum(s.get("retries", 0) for s in output.get("steps", [])),
                "heal_count": sum(1 for s in output.get("steps", []) if s.get("healAttempt")),
            }
            _eval_report = self._eval_engine.evaluate(_eval_metrics)
            _launch_rating = LaunchRating.from_report(_eval_report)
            output["launchRating"] = _launch_rating.value
            output["evalRadar"] = _eval_report.to_radar_data()
        except Exception as _eval_err:
            output["evalError"] = str(_eval_err)

        # ── Privacy Guard 脱敏 ──
        try:
            output.update(self._privacy_guard.sanitize_dict(output))
        except Exception as _pg_err:
            output["privacyError"] = str(_pg_err)

        # ── Knowledge Base 检索频次 ──
        try:
            _page_url = self._input_data.get("context", {}).get("urlPattern", "")
            if _page_url:
                _kb_results = self._kbase.search(_page_url, limit=5)
                for _r in _kb_results:
                    self._kbase.record_hit(_r.entry)
        except Exception as e:
            print(f"[finalize] knowledge_base 检索异常: {e}", file=sys.stderr)

        # ── 复杂度 / 预算 / 熔断 报告 ──
        output["complexity"] = {
            "level": self._complexity_level.value if hasattr(self._complexity_level, 'value') else str(self._complexity_level),
            **(self._complexity_result if isinstance(self._complexity_result, dict) else {})
        }
        output["budgetReport"] = self._budget_guard.get_report()
        output["circuitBreaker"] = self._circuit_breaker.get_report()

        # ── 失败分级放行决策（升级为双因子裁决）──
        if failure_reports:
            try:
                _release = self._failure_classifier.get_release_decision(failure_reports)
                output["releaseDecision"] = {
                    "blocked": _release.get("blocked", False),
                    "warnings": _release.get("warnings", []),
                    "skipped": _release.get("skipped", []),
                }
            except Exception as e:
                print(f"[finalize] release_decision 异常: {e}", file=sys.stderr)

        # ── 双因子裁决（全托管闭环 D：规则层+LLM层一致性裁决）──
        try:
            from core.dual_factor_verdict import DualFactorVerdictEngine
            _df_engine = DualFactorVerdictEngine(base_dir=os.path.dirname(os.path.dirname(__file__)))
            _failed_steps = [s for s in output.get("steps", []) if s.get("status") in ("error", "fail")]
            if _failed_steps:
                _verdicts = _df_engine.verdict_batch(_failed_steps)
                _df_decision = _df_engine.release_decision(_verdicts)
                output["dualFactorVerdict"] = _df_decision
                # 双因子结果覆盖简单分级放行（更准确）
                output["releaseDecision"] = {
                    "blocked": _df_decision["blocked"],
                    "release_level": _df_decision["release_level"],
                    "warnings": _df_decision["p1_warnings"],
                    "skipped": _df_decision["p2_skipped"],
                    "human_reviews": _df_decision["human_reviews"],
                    "skip_rate": _df_decision["skip_rate"],
                    "suggestion": _df_decision["suggestion"],
                }
        except Exception as _df_err:
            output["dualFactorError"] = str(_df_err)

        # ── KBase 量化晋升（全托管 §3.1：检索≥3/需求≥2/7天窗口）──
        try:
            from core.kbase_promotion import KBasePromotionEngine
            _promo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "kbase_promotion_tracking.json")
            _promo = KBasePromotionEngine(tracking_path=_promo_path)
            # 记录本次执行中 knowledge 检索命中
            _page_url = self._input_data.get("context", {}).get("urlPattern", "")
            _req_id = self._input_data.get("requirementId", "")
            if _page_url:
                _promo.record_search_hit(f"page#{_page_url}", requirement_id=_req_id, session_id=self._run_id)
            # 记录 badcase 命中
            for bc in output.get("badcaseCount", []) if isinstance(output.get("badcaseCount"), list) else []:
                _promo.record_search_hit(f"badcase#{bc}", requirement_id=_req_id, session_id=self._run_id)
            _promo_result = _promo.execute_promotion(dry_run=False)
            output["kbasePromotion"] = _promo_result
        except Exception as _promo_err:
            output["kbasePromotionError"] = str(_promo_err)

        # ── 五契约校验（全托管 §3.3：C1数据/C2控制/C3反馈/C4隔离/C5指标）──
        try:
            from core.contract_verifier import ContractVerifier, StageDiffMatrix, EvidencePack
            _cv = ContractVerifier()
            _diff_matrix = StageDiffMatrix()
            # 从步骤构建 Diff 矩阵
            for _s in output.get("steps", []):
                _stage = _s.get("type", f"step{_s.get('index', 0)}")
                _diff_matrix.capture_before(_stage, {"status": "pending"})
                _diff_matrix.capture_after(_stage, {"status": _s.get("status", "unknown")})
            # 构建证据包
            _ev_pack = EvidencePack(run_id=self._run_id)
            for _req in output.get("capture", {}).get("requests", [])[:10]:
                _ev_pack.add_network_capture(
                    url=_req.get("url", ""), method=_req.get("method", "GET"),
                    status=_req.get("status", 0), rt_ms=_req.get("durationMs", 0),
                )
            _screenshot = output.get("artifacts", {}).get("screenshotPath", "")
            if _screenshot:
                _ev_pack.add_screenshot(_screenshot, stage="finalize")
            _contract_report = _cv.verify_all(output, _diff_matrix, _ev_pack)
            output["contractVerification"] = _contract_report.to_dict()
        except Exception as _cv_err:
            output["contractVerificationError"] = str(_cv_err)

        # ── 验收报告 SOP 对齐（工具/Agent/产品三阶段标准）──
        # 如果 _tool_acceptance_report 已经执行过（YAML pipeline 路径），跳过重复生成和上传
        if output.get("acceptanceReport"):
            pass  # 已由 _tool_acceptance_report 工具步骤完成
        else:
            try:
                from core.acceptance_report import AcceptanceReportGenerator
                _ar_gen = AcceptanceReportGenerator(
                    run_id=self._run_id,
                    requirement_id=self._input_data.get("requirementId", ""),
                )
                # 从执行数据自动填充 Agent 验收指标
                _total_steps = len(output.get("steps", []))
                _passed_steps = sum(1 for s in output.get("steps", []) if s.get("status") == "pass")
                _ar_gen.add_agent_result(
                    total_tasks=_total_steps,
                    completed_tasks=_passed_steps,
                    avg_duration_s=output.get("duration", 0) // 1000,
                    consistency_total=_total_steps,
                    consistency_passed=_passed_steps,
                )
                # 自动提取证据链（截图/抓包/录屏/契约/裁决）
                _ar_gen.add_evidence_from_output(output)
                _ar_report = _ar_gen.generate()
                output["acceptanceReport"] = _ar_report.to_dict()
                # Markdown 内容存入 output（供上传钉钉知识库，不留本地）
                output["acceptanceReportMarkdown"] = _ar_report.markdown
                # 上传钉钉知识库（F88 产物按需求维度组织）
                try:
                    from core.report_uploader import upload_to_dingtalk, F88_WORKSPACE_ID, F88_REPORT_FOLDER_ID
                    _req_name = self._input_data.get("requirementName", "") or self._input_data.get("requirementId", "") or self._run_id
                    _doc_title = f"{_req_name}验收报告"
                    _doc_url = upload_to_dingtalk(
                        title=_doc_title,
                        markdown=_ar_report.markdown,
                        workspace_id=self._input_data.get("dingtalkWorkspaceId", F88_WORKSPACE_ID),
                        folder_id=self._input_data.get("dingtalkFolderId", F88_REPORT_FOLDER_ID),
                    )
                    output["artifacts"]["acceptanceReportUrl"] = _doc_url
                except Exception as _upload_err:
                    output["acceptanceReportUploadError"] = str(_upload_err)
            except Exception as _ar_err:
                output["acceptanceReportError"] = str(_ar_err)

        # ── Checkpoint 最后一段 ──
        # (由调用方在 impl.py 中处理)

def _parse_time(iso_str: str) -> float:
    from datetime import datetime
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.timestamp()

def _compact_output(output: dict, max_response_size_kb: int = 50):
    """精简 output 内容，减少上下文消耗。"""
    # 1. 精简 steps
    for step in output.get("steps", []):
        if step.get("status") == "pass":
            keep_keys = {"index", "type", "status", "duration", "description"}
            for key in list(step.keys()):
                if key not in keep_keys:
                    del step[key]

    # 2. 精简抓包
    capture = output.get("capture", {})
    requests = capture.get("requests", [])
    if requests:
        for i, req in enumerate(requests):
            if i >= 20:
                if req.get("responseBodyTruncated"):
                    req["responseBodySummary"] = {
                        "truncated": True,
                        "originalSizeKb": req.get("responseBodySizeKb"),
                        "limitKb": max_response_size_kb,
                    }
                    if "responseBody" in req:
                        del req["responseBody"]

        capture["summary"] = {
            "totalRequests": len(requests),
            "requestsIncluded": min(20, len(requests)),
            "fullDataInArtifacts": True,
        }
        capture["requests"] = requests[:20]

    # 3. 添加提示
    output["_contextOptimization"] = {
        "enabled": True,
        "compactSteps": True,
        "captureTruncated": len(requests) > 20 if requests else False,
        "fullArtifactsPath": output.get("artifacts", {}).get("runDir"),
    }
