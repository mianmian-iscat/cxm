"""
impl.py — 执行编排入口

控制状态机，完成「动作 → 监听 → 产物」闭环。
不写业务逻辑，只做编排：

    INIT → CONNECT → CAPTURE_START → STEPS → FINALIZE → DONE
                                        ↓ (出错)
                                      ERROR

使用方式（CLI）：
    python impl.py input.json [output.json]

使用方式（Python import）：
    from impl import run_test
    result = asyncio.run(run_test(input_data))
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

# ── 核心组件 ──
from core.cdp_client import CDPClient
from core.video_recorder import VideoRecorder
from core.artifact_manager import ArtifactManager
from core.checkpoint_manager import CheckpointManager

# ── 抽取后的模块 ──
from core.subsystem_factory import create_subsystems
from core.browser_setup import inject_cookies, ensure_alibaba_sso, handle_login
from core.output_formatter import init_output, print_verbose

# ── 执行模块 ──
from core.step_executor import StepExecutor
from core.capture_manager import CaptureManager
from core.finalize_pipeline import FinalizePipeline, FinalizeContext
from core.state_machine import StateMachineEngine


# ── 状态机 ──

_SM_YAML = os.path.join(os.path.dirname(__file__), "harness", "state_machines", "test_execution.yaml")
_state_machine = StateMachineEngine.from_yaml(_SM_YAML) if os.path.exists(_SM_YAML) else None


class _StateTracker:
    """状态追踪器：包装 StateMachineEngine，提供简洁的 transition API。"""

    def __init__(self):
        self.current = "INIT"

    def transition_to(self, to_state: str, context: dict = None):
        if _state_machine:
            result = _state_machine.validate_transition(self.current, to_state, context or {})
            if not result.valid:
                print(
                    f"[state_machine] 警告: 非法状态转换 {self.current} → {to_state}: {result.errors}",
                    file=sys.stderr,
                )
        self.current = to_state

    @property
    def is_error(self) -> bool:
        return self.current == "ERROR"


class _CheckpointSignal(Exception):
    """内部信号：当前段已保存，需要续跑（不是真正的错误）。"""
    pass


# ── 主入口 ──

async def run_test(input_data: dict, resume_run_id: str = None) -> dict:
    """
    执行一个测试用例，返回符合 output.schema.json 的结果。

    resume_run_id:
        传入时从已有 run 的 checkpoint 续跑，跳过已完成步骤。
        不传时全新执行，自动生成 run_id。
    """
    # ── 配置解析 ──
    checkpoint_cfg = input_data.get("checkpoint", {})
    checkpoint_enabled = checkpoint_cfg.get("enabled", False)
    segment_size = checkpoint_cfg.get("segmentSize", 8)
    output_size_limit_kb = checkpoint_cfg.get("outputSizeLimitKb", 200)

    context_opt = input_data.get("contextOptimization", {})
    screenshot_external = context_opt.get("screenshotExternal", True)
    max_response_size_kb = context_opt.get("maxResponseSizeKb", 50)
    output_compact = context_opt.get("outputCompact", True)
    verbose_mode = context_opt.get("verboseMode", "summary")

    if resume_run_id:
        run_id = resume_run_id
        checkpoint_enabled = True
    else:
        run_id = f"{input_data['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    _scene = input_data.get("scene") or input_data.get("knowledgeId", "").split("-")[0] or None
    artifacts = ArtifactManager(run_id, scene=_scene)
    artifacts.save_input(input_data)

    business_type = input_data.get("businessType", input_data.get("context", {}).get("urlPattern", "unknown"))

    # ── 子系统一行初始化 ──
    subs = create_subsystems(input_data, run_id, business_type)

    # ── 维度3: 加载数据新鲜度声明 ──
    if input_data.get("data_freshness"):
        subs.variable_store.load_freshness_from_input(input_data)

    # ── Checkpoint 初始化 ──
    ckpt: Optional[CheckpointManager] = None
    resume_ctx = None
    if checkpoint_enabled:
        ckpt = CheckpointManager(
            run_id=run_id, run_dir=artifacts.run_dir,
            total_steps=len(input_data.get("steps", [])),
            segment_size=segment_size, output_size_limit_kb=output_size_limit_kb,
        )
        if resume_run_id:
            resume_ctx = ckpt.get_resume_context()
            print(
                f"[checkpoint] 续跑模式：从步骤 {resume_ctx['nextStepIndex']} 开始，"
                f"已完成 {len(resume_ctx['completedSegments'])} 段",
                file=sys.stderr,
            )

    output = init_output(input_data, run_id)
    state = _StateTracker()
    ctx = input_data.get("context", {})
    cdp = CDPClient(port=ctx.get("cdpPort"), ws_endpoint=ctx.get("cdpWsEndpoint"))
    recorder: Optional[VideoRecorder] = None
    capture_mgr: Optional[CaptureManager] = None

    # checkpoint 段状态
    all_steps = input_data.get("steps", [])

    # ── includeAtom 展开（把公共原子模板就地替换为内部步骤）──
    # 展开后索引 = 实际执行索引，checkpoint.resume_start 基于展开后的索引
    try:
        from core.atom_loader import AtomLoader
        _atom_loader = AtomLoader()
        _pre_expanded = len(all_steps)
        all_steps = _atom_loader.expand(all_steps)
        if len(all_steps) != _pre_expanded:
            print(
                f"[atoms] includeAtom 展开: {_pre_expanded} → {len(all_steps)} 步",
                file=sys.stderr,
            )
    except Exception as _e:
        print(f"[atoms] includeAtom 展开异常（保留原步骤）: {_e}", file=sys.stderr)

    resume_start = resume_ctx["nextStepIndex"] if resume_ctx else 0
    current_seg_index = resume_ctx["currentSegIndex"] if resume_ctx else 0
    current_seg_start_step = resume_start
    current_seg_steps: list = []
    current_seg_apis: dict = {}
    _failure_reports = []
    executor = None  # 在 try 中创建，在 finally 中访问

    try:
        # ── CONNECT ──
        state.transition_to("CONNECT")
        _launch_new = ctx.get("isolated", False)
        _launch_options = ctx.get("launchOptions") or {}
        await cdp.connect(
            url_pattern=ctx.get("urlPattern"), url=ctx.get("url"),
            launch_new=_launch_new,
            launch_options=_launch_options if _launch_new else None,
        )
        if cdp.is_isolated:
            print(f"[cdp] 已启动独立 Chrome 实例（PID={cdp.chrome_pid}，{cdp.cdp_url}）", file=sys.stderr)
        await cdp.set_fixed_viewport()

        # 阻止 macOS Passkey / WebAuthn 弹窗（在所有导航之前生效）
        try:
            await cdp.disable_webauthn()
        except Exception:
            pass

        # Cookie 注入 + SSO 预热
        cookie_injected = await inject_cookies(cdp, ctx)
        target_url = ctx.get("url") or ""
        if not target_url.startswith("http") and ctx.get("urlPattern", "").startswith("http"):
            target_url = ctx.get("urlPattern", "")
        if cookie_injected and target_url.startswith("http"):
            await cdp._send_cmd("navigate", {"url": target_url})
            await asyncio.sleep(3)
        if ctx.get("ssoWarmup", True) and (
            "alibaba-inc.com" in target_url or "alibaba-inc.com" in ctx.get("urlPattern", "")
        ):
            await ensure_alibaba_sso(cdp, target_url, ctx.get("urlPattern", ""))

        # 登录检测
        if not await handle_login(cdp, ctx, output):
            return output

        # ── 维度1: 环境预检（Pre-flight Health Check）──
        try:
            from core.preflight_check import PreflightChecker
            preflight = PreflightChecker(cdp=cdp)
            preflight_report = await preflight.run(
                target_url=target_url,
                expected_login=bool(ctx.get("ssoWarmup", True)),
            )
            if not preflight_report.all_passed:
                output["preflightWarning"] = preflight_report.to_dict()
                _blockers = [i.message for i in preflight_report.blockers]
                print(f"[preflight] 预检发现阻断级问题: {_blockers}", file=sys.stderr)
            elif preflight_report.issues:
                output["preflightWarning"] = preflight_report.to_dict()
                print(f"[preflight] 预检完成，{len(preflight_report.issues)} 个警告", file=sys.stderr)
        except Exception as _pf_err:
            print(f"[preflight] 预检异常（不影响执行）: {_pf_err}", file=sys.stderr)

        # ── CAPTURE_START ──
        state.transition_to("CAPTURE_START")
        capture_cfg = input_data.get("capture", {})
        if capture_cfg.get("enabled", True):
            capture_mgr = CaptureManager(cdp, max_response_size_kb=max_response_size_kb)
            await capture_mgr.start(
                url_filter=capture_cfg.get("filter", ""),
                capture_body=capture_cfg.get("captureBody", True),
            )

        # 视频录制
        video_cfg = input_data.get("video", {})
        if video_cfg.get("enabled") and VideoRecorder.is_ffmpeg_available():
            recorder = VideoRecorder(cdp, artifacts.video_path())
            await recorder.start()

        # 等待渲染 + 关闭弹窗 + Pre-Assert
        await asyncio.sleep(ctx.get("waitAfterLoad", 2000) / 1000)
        if ctx.get("dismissModals", True):
            await cdp.dismiss_modals()
        pre_asserts = ctx.get("pre_asserts")
        if pre_asserts:
            for pr in subs.assertion.run_pre_asserts(ctx, pre_asserts):
                if not pr.pass_ and pr.severity == "CRITICAL":
                    output["status"] = "fail"
                    output["error"] = {"stepIndex": -1, "message": f"前置断言失败: {pr.message}"}
                    return output

        # ── STEPS ──
        state.transition_to("STEPS")
        screenshot_cfg = input_data.get("screenshot", {})
        if resume_ctx and resume_ctx.get("capturedApis") and capture_mgr:
            apis = resume_ctx["capturedApis"]
            if apis:
                capture_mgr.last_api_entry = list(apis.values())[-1]

        executor = StepExecutor(
            cdp=cdp, registry=subs.registry, variable_store=subs.variable_store,
            assertion=subs.assertion, evidence=subs.evidence,
            self_healing=subs.self_healing, failure_classifier=subs.failure_classifier,
            circuit_breaker=subs.circuit_breaker, budget_guard=subs.budget_guard,
            hook_registry=subs.hook_registry, metrics_logger=subs.metrics_logger,
            artifacts=artifacts, screenshot_cfg=screenshot_cfg,
            screenshot_external=screenshot_external, capture_manager=capture_mgr,
            checkpoint_manager=ckpt,
        )

        # ── 步骤循环 ──
        for i, step in enumerate(all_steps):
            if i < resume_start:
                continue

            exec_result = await executor.execute_step(i, step, output, {
                "seg_index": current_seg_index, "seg_start_step": current_seg_start_step,
                "seg_steps": current_seg_steps, "seg_apis": current_seg_apis,
            })

            if step["type"] == "waitForAPI" and capture_mgr and capture_mgr.last_api_entry and ckpt:
                current_seg_apis[step["urlPattern"]] = {
                    "url": capture_mgr.last_api_entry.get("url"),
                    "responseBody": capture_mgr.last_api_entry.get("responseBody"),
                }

            if exec_result.should_break:
                break

            # Checkpoint 触发判断
            step_result = exec_result.step_result
            if ckpt and step_result["status"] in ("pass", "fail"):
                _shot_paths = [
                    s["path"] for s in output["screenshots"]
                    if s.get("stepIndex") == i and "path" in s
                ]
                if ckpt.track_step(step_result, _shot_paths) and i < len(all_steps) - 1:
                    try:
                        _cur_url = await cdp.evaluate("window.location.href")
                    except Exception:
                        _cur_url = "unknown"
                    ckpt.save_segment(
                        seg_index=current_seg_index,
                        step_range=(current_seg_start_step, i),
                        steps_results=current_seg_steps,
                        captured_apis=current_seg_apis,
                        last_page_url=_cur_url, seg_status="pass",
                    )
                    print(
                        f"[checkpoint] 段 {current_seg_index} 已保存"
                        f"（步骤 {current_seg_start_step}~{i}），返回 checkpoint_saved",
                        file=sys.stderr,
                    )
                    ckpt.reset_seg_counter()
                    current_seg_index += 1
                    current_seg_start_step = i + 1
                    current_seg_steps = []
                    current_seg_apis = {}

                    output["status"] = "checkpoint_saved"
                    output["checkpoint"] = {
                        "runId": run_id, "completedSteps": i + 1,
                        "totalSteps": len(all_steps),
                        "remainingSteps": len(all_steps) - i - 1,
                        "nextSegmentStart": i + 1,
                        "stateFile": ckpt._state_path(),
                    }
                    raise _CheckpointSignal()

    except _CheckpointSignal:
        state.transition_to("FINALIZE", {"trigger": "checkpoint_signal"})

    except Exception as e:
        state.transition_to("ERROR")
        output["status"] = "error"
        output["error"] = {"stepIndex": -1, "message": str(e)}

    finally:
        # ── FINALIZE ──
        if state.current != "FINALIZE":
            state.transition_to("FINALIZE")

        fin_ctx = FinalizeContext(
            cdp=cdp, recorder=recorder, capture_manager=capture_mgr,
            artifacts=artifacts, metrics_logger=subs.metrics_logger,
            assertion=subs.assertion, evidence=subs.evidence,
            eval_engine=subs.eval_engine, privacy_guard=subs.privacy_guard,
            quality_scorer=subs.quality_scorer, badcase_collector=subs.badcase_collector,
            budget_guard=subs.budget_guard, circuit_breaker=subs.circuit_breaker,
            failure_classifier=subs.failure_classifier, kbase=subs.kbase,
            orchestrator=subs.orchestrator, hook_registry=subs.hook_registry,
            input_data=input_data, run_id=run_id, business_type=business_type,
            complexity_result=subs.complexity_result, complexity_level=subs.complexity_level,
            screenshot_external=screenshot_external, output_compact=output_compact,
            max_response_size_kb=max_response_size_kb, checkpoint_manager=ckpt,
        )
        finalizer = FinalizePipeline(fin_ctx)
        await finalizer.run(output, failure_reports=_failure_reports)

        # ── 维度10: 自愈经验晋升到知识库 ──
        try:
            promote_result = subs.self_healing.promote_memories()
            if promote_result.get("promoted", 0) > 0:
                print(
                    f"[healing_memory] 晋升 {promote_result['promoted']} 条经验到知识库",
                    file=sys.stderr,
                )
        except Exception as _pm_err:
            print(f"[healing_memory] 经验晋升异常: {_pm_err}", file=sys.stderr)

        # ── 维度12: 自愈效果度量报告 ──
        try:
            healing_report = subs.self_healing.get_healing_report()
            output["healingAnalytics"] = healing_report.to_dict()
        except Exception as _hr_err:
            print(f"[healing_analytics] 度量报告异常: {_hr_err}", file=sys.stderr)

        # ── 维度11: 失败聚类分析报告 ──
        if executor and executor._failure_clusterer:
            try:
                cluster_report = executor._failure_clusterer.analyze()
                if cluster_report.total_failures > 0:
                    output["failureClustering"] = cluster_report.to_dict()
            except Exception as _fc_err:
                print(f"[failure_clustering] 聚类报告异常: {_fc_err}", file=sys.stderr)

        # ── 策略组合学习: 持久化 + 报告 ──
        try:
            if subs.self_healing.chain_learner:
                subs.self_healing.save_chain_learner()
                chain_stats = subs.self_healing.chain_learner.get_stats()
                if chain_stats["total_chains"] > 0:
                    output["strategyChainStats"] = chain_stats
        except Exception as _sc_err:
            print(f"[strategy_chain] 持久化异常: {_sc_err}", file=sys.stderr)

        # 最后一段 checkpoint
        if ckpt and current_seg_steps and output["status"] != "checkpoint_saved":
            try:
                _cur_url = await cdp.evaluate("window.location.href")
            except Exception:
                _cur_url = "unknown"
            ckpt.save_segment(
                seg_index=current_seg_index,
                step_range=(current_seg_start_step, len(all_steps) - 1),
                steps_results=current_seg_steps, captured_apis=current_seg_apis,
                last_page_url=_cur_url, seg_status=output["status"],
            )
            ckpt.save_final_state(output["status"])

        state.transition_to("DONE")

    print_verbose(output, verbose_mode)
    return output


# ── CLI 入口 ──

def main():
    """
    用法：
      python impl.py input.json                        # 全新执行
      python impl.py input.json output.json            # 全新执行 + 指定输出文件
      python impl.py input.json --resume <run_id>      # 从断点续跑
    """
    args = sys.argv[1:]
    if not args:
        print("Usage: python impl.py <input.json> [output.json] [--resume <run_id>]", file=sys.stderr)
        sys.exit(1)

    resume_run_id = None
    output_path = None
    positional = []

    idx = 0
    while idx < len(args):
        if args[idx] == "--resume" and idx + 1 < len(args):
            resume_run_id = args[idx + 1]
            idx += 2
        else:
            positional.append(args[idx])
            idx += 1

    if not positional:
        print("Error: 缺少 input.json 参数", file=sys.stderr)
        sys.exit(1)

    raw = positional[0]
    if len(positional) > 1:
        output_path = positional[1]

    input_data = json.loads(raw) if raw.strip().startswith("{") else json.load(open(raw, encoding="utf-8"))

    if resume_run_id:
        print(f"[impl] 续跑模式：run_id={resume_run_id}", file=sys.stderr)

    result = asyncio.run(run_test(input_data, resume_run_id=resume_run_id))

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"结果已写入: {output_path}", file=sys.stderr)
    elif input_data.get("contextOptimization", {}).get("verboseMode", "summary") == "full":
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["status"] == "checkpoint_saved":
        sys.exit(2)
    elif result["status"] in ("pass", "login_required"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
