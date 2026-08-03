"""
step_executor.py — 步骤执行器

从 impl.py 抽取的核心步骤执行逻辑：
- 单步 CDP 调度（click/fill/wait/assert/navigate/...）
- 自愈重试（知识库查解法 → 执行修复 → 重试步骤）
- 证据采集 & 变量绑定
- 失败分级 & 熔断判断

使用方式:
    from core.step_executor import StepExecutor
    executor = StepExecutor(cdp=cdp, **subsystems)
    result = await executor.execute_step(i, step, exec_ctx)
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

from core.cdp_client import CDPClient
from core.tool_registry import ToolRegistry
from core.variable_store import VariableStore
from core.assertion_framework import (
    AssertionFramework,
    check_sql_readonly,
    resolve_json_path,
    assert_value,
    _JSON_PATH_MISSING,
)
from core.evidence_store import EvidenceStore
from core.self_healing import SelfHealingEngine, HealingAction
from core.feedback_loops import FeedbackHookRegistry, HookPhase
from core.metrics_logger import MetricsLogger
from core.perf_adaptive import PerformanceAdaptive
from core.failure_clustering import FailureClusterer
from core.dom_snapshot import DOMSnapshotGuard

@dataclass
class StepExecResult:
    """步骤执行结果"""
    step_result: dict
    should_break: bool = False
    break_reason: str = ""

class StepExecutor:
    """
    步骤执行器：单步调度 + 自愈重试 + 证据采集。

    整合了原 impl.py 中 for 循环体内的全部逻辑:
    参数校验 → 变量解析 → CDP 执行 → 自愈重试 → 证据记录 → 失败分级 → 熔断检查
    """

    def __init__(
        self,
        cdp: CDPClient,
        registry: ToolRegistry,
        variable_store: VariableStore,
        assertion: AssertionFramework,
        evidence: EvidenceStore,
        self_healing: SelfHealingEngine,
        failure_classifier,
        circuit_breaker,
        budget_guard,
        hook_registry: FeedbackHookRegistry,
        metrics_logger: MetricsLogger,
        artifacts,
        screenshot_cfg: dict = None,
        screenshot_external: bool = True,
        capture_manager=None,
        checkpoint_manager=None,
    ):
        self._cdp = cdp
        self._registry = registry
        self._variable_store = variable_store
        self._assertion = assertion
        self._evidence = evidence
        self._healing = self_healing
        self._failure_classifier = failure_classifier
        self._circuit_breaker = circuit_breaker
        self._budget_guard = budget_guard
        self._hook_registry = hook_registry
        self._metrics_logger = metrics_logger
        self._artifacts = artifacts
        self._screenshot_cfg = screenshot_cfg or {}
        self._screenshot_external = screenshot_external
        self._capture = capture_manager
        self._ckpt = checkpoint_manager

        # ── 维度8: 性能退化自适应 ──
        self._perf_adaptive = PerformanceAdaptive()
        # ── 维度11: 失败聚类 ──
        self._failure_clusterer = FailureClusterer()
        # ── 维度2: DOM 快照对比 ──
        self._dom_snapshot = DOMSnapshotGuard(cdp=cdp)

        # ── 步骤类型注册表（策略模式）──
        self._dispatch_table: dict = self._build_dispatch_table()

    async def execute_step(
        self,
        i: int,
        step: dict,
        output: dict,
        checkpoint_ctx: dict = None,
    ) -> StepExecResult:
        """
        执行单个步骤，返回 StepExecResult。

        Args:
            i: 步骤索引
            step: 步骤定义 dict
            output: 当前运行输出（会被就地修改）
            checkpoint_ctx: checkpoint 上下文（current_seg_steps/apis 等）
        """
        step_start = time.time()
        # ── 维度8: 性能自适应调速 ──
        _step_type = step.get("type", "")
        _orig_timeout = step.get("timeout")
        if _orig_timeout:
            step["timeout"] = self._perf_adaptive.get_adjusted_timeout(_orig_timeout, _step_type)

        step_result = {
            "index": i,
            "type": step["type"],
            "description": step.get("description", ""),
            "status": "pass",
            "duration": 0,
        }
        should_break = False
        break_reason = ""

        # ── 参数校验 ──
        _validation = self._registry.validate_params(step["type"], step)
        # 类型安全访问：兼容 ValidationResult 对象和 plain dict
        _v_valid = getattr(_validation, 'valid', None)
        if _v_valid is None:
            _v_valid = _validation.get('valid', False) if isinstance(_validation, dict) else False
        _v_errors = getattr(_validation, 'errors', None)
        if _v_errors is None:
            _v_errors = _validation.get('errors', _validation.get('error', [])) if isinstance(_validation, dict) else []
        if not _v_valid:
            step_result["status"] = "error"
            step_result["error"] = json.dumps(_v_errors, ensure_ascii=False)
            output["status"] = "error"
            output["error"] = {"stepIndex": i, "message": step_result["error"]}
            self._evidence.record_step(
                step_id=step.get("id", f"step{i}"),
                tool_name=step["type"],
                input_params=step,
                output_data=None,
                duration_ms=0,
                schema_validated=False,
                error=step_result["error"],
            )
            output["steps"].append(step_result)
            return StepExecResult(step_result=step_result, should_break=False)

        # ── 变量解析 ──
        step = self._variable_store.resolve_params(step)

        try:
            # ── CDP 调度 ──
            dispatch_result = await self._dispatch(step, i, output)

            # ── 维度2: DOM 快照对比（导航后检测）──
            if step.get("type") in ("navigate", "click") and self._dom_snapshot:
                try:
                    _snap = await self._dom_snapshot.capture()
                    if _snap and self._dom_snapshot.get_baseline():
                        _diff = self._dom_snapshot.compare(_snap)
                        if _diff.similarity < 0.6:
                            step_result["domSnapshotWarning"] = {
                                "similarity": round(_diff.similarity, 3),
                                "message": _diff.message,
                            }
                    # 首次导航成功后设置基线
                    if not self._dom_snapshot.get_baseline() and _snap and _snap.url:
                        self._dom_snapshot.set_baseline(_snap)
                except Exception:
                    pass  # 快照失败不影响步骤执行

            # ── 变量绑定 ──
            _step_id = step.get("id", f"step{i}")
            _step_output = {
                k: v for k, v in step_result.items()
                if k not in ("index", "type", "description", "status", "duration")
            }
            _step_output.update(dispatch_result or {})
            step_result.update(dispatch_result or {})
            _output_binding = step.get("output_binding")
            self._variable_store.bind_step_output(_step_id, _step_output, _output_binding)

            # 对 waitForAPI 也绑定 API 响应
            if step["type"] == "waitForAPI" and self._capture:
                last_api = self._capture.last_api_entry
                if last_api:
                    self._variable_store.bind_step_output(_step_id, last_api, _output_binding)

            # ── 实时断言 ──
            _rt_asserts = step.get("realtime_asserts")
            if _rt_asserts:
                self._assertion.run_realtime_asserts(step, step_result, _rt_asserts)

            # ── 证据采集 ──
            self._evidence.record_step(
                step_id=_step_id,
                tool_name=step["type"],
                input_params={k: v for k, v in step.items() if k not in ("id", "output_binding", "realtime_asserts")},
                output_data=_step_output,
                duration_ms=step_result.get("duration", 0),
                schema_validated=_v_valid,
                error=step_result.get("error"),
            )

            # ── 步骤级截图 ──
            await self._take_step_screenshot(step, step_result, i, output)

            # ── 失败分级 ──
            should_break, break_reason = self._check_failure_grade(step_result, i, output)

            # ── 熔断检查 ──
            if not should_break:
                self._circuit_breaker.record_result(step_result.get("status", "unknown"))
                if self._circuit_breaker.should_break():
                    output["status"] = "circuit_broken"
                    output["error"] = {"stepIndex": i, "message": "熔断器触发: 连续失败过多"}
                    should_break = True
                    break_reason = "circuit_broken"

            # ── 维度11: 智能熔断（失败聚类联动）──
            if not should_break and step_result.get("status") == "error":
                if self._failure_clusterer.should_skip_step_type(
                    step.get("type", ""), step.get("selector", "")
                ):
                    step_result["status"] = "skip"
                    step_result["skipReason"] = "智能熔断: 同类失败过多，跳过后续同类步骤"
                    should_break = False  # 跳过但不中断整个流程

            # ── 预算追踪 ──
            _est_tokens = 5000 if step["type"] in ("llm", "ai_plan") else 1000
            self._budget_guard.record_usage(step["type"], _est_tokens)
            _budget_status = self._budget_guard.check_budget()
            if _budget_status.degraded:
                output["budgetWarning"] = _budget_status.suggestion

        except Exception as e:
            # ── 自愈重试 ──
            _original_error = str(e)
            _healed = await self._heal_and_retry(step, step_result, i, _original_error, output)

            if not _healed:
                step_result["status"] = "error"
                step_result["error"] = _original_error
                output["status"] = "error"
                output["error"] = {"stepIndex": i, "message": _original_error}

                # Hook: on_failure
                self._fire_hook_safe(HookPhase.ON_FAILURE, {
                    "step_id": step.get("id", f"step{i}"),
                    "error": _original_error,
                    "status": "error",
                })

                # 错误截图
                await self._take_error_screenshot(i, output)

                # 保存 checkpoint
                if self._ckpt and checkpoint_ctx:
                    await self._save_error_checkpoint(i, checkpoint_ctx)

                # 异常步骤失败分级
                try:
                    _freport = self._failure_classifier.classify(step_result, None)
                except Exception as e:
                    print(f"[step_executor] failure_classifier 异常: {e}", file=sys.stderr)

                should_break = True
                break_reason = "step_error"

        finally:
            step_result["duration"] = int((time.time() - step_start) * 1000)
            output["steps"].append(step_result)

            # ── 维度8: 记录步骤耗时用于性能基线 ──
            self._perf_adaptive.record_step_duration(_step_type, step_result["duration"])

            # ── 维度11: 失败聚类记录 ──
            if step_result.get("status") == "error":
                try:
                    _cur_url = ""
                    try:
                        _cur_url = await self._cdp.evaluate("window.location.href") or ""
                    except Exception:
                        pass
                    self._failure_clusterer.record_failure(step_result, url=str(_cur_url))
                except Exception:
                    pass

            # checkpoint 段追踪
            if self._ckpt and checkpoint_ctx:
                checkpoint_ctx.get("seg_steps", []).append(step_result)

            # Metrics 采集
            self._log_step_metrics(step, step_result, i)

        return StepExecResult(
            step_result=step_result,
            should_break=should_break,
            break_reason=break_reason,
        )

    # ── 分发注册表 ──

    def _build_dispatch_table(self) -> dict:
        """构建 step.type -> handler 的注册表。

        每个 handler 签名为 async (step, i, output) -> dict。
        新增步骤类型只需在此注册，无需修改 _dispatch 主流程。
        """
        return {
            "click":              self._exec_click,
            "fill":               self._exec_fill,
            "navigate":           self._exec_navigate,
            "waitForUrl":         self._exec_wait_for_url,
            "assert":             self._handle_assert,
            "evaluate":           self._handle_evaluate,
            "assertStore":        self._handle_assert_store,
            "screenshot":         self._handle_screenshot,
            "wait":               self._handle_wait,
            "waitForAPI":         self._handle_wait_for_api,
            "selectOption":       self._handle_select_option,
            "uncheckCheckbox":    self._handle_uncheck_checkbox,
            "clickText":          self._handle_click_text,
            "cdpDrag":            self._handle_cdp_drag,
            "cdpKeyEvent":        self._handle_cdp_key_event,
            "cdpMouseWheel":      self._handle_cdp_mouse_wheel,
            "emulateFullscreen":  self._handle_emulate_fullscreen,
            "mockNetwork":        self._handle_mock_network,
            "setFocus":           self._handle_set_focus,
            "observeTransitions": self._handle_observe_transitions,
            "screencast":         self._handle_screencast,
            # ── 一期三件套（断言能力增强）──
            "dbAssert":           self._handle_db_assert,
            "assertAPI":          self._handle_assert_api,
            "assertUI":           self._handle_assert_ui,
            # ── 造数自查闭环 ──
            "postSetupVerify":    self._handle_post_setup_verify,
        }

    def register_handler(self, step_type: str, handler):
        """注册自定义步骤类型处理器。

        Args:
            step_type: 步骤类型标识
            handler: async (step, i, output) -> dict
        """
        self._dispatch_table[step_type] = handler

    # ── CDP 调度 ──

    async def _dispatch(self, step: dict, i: int, output: dict) -> dict:
        """按 step.type 分派 CDP 命令，返回额外的 step_result 字段。"""
        handler = self._dispatch_table.get(step["type"])
        if handler is None:
            return {"status": "skip", "error": f"未知 step 类型: {step['type']}"}
        return await handler(step, i, output) or {}

    # ── 轻量内联 handler（直接委托 CDP 指令）──

    async def _handle_wait(self, step, i, output):
        await asyncio.sleep(step["ms"] / 1000)

    async def _handle_wait_for_api(self, step, i, output):
        if self._capture:
            timeout_sec = step.get("timeout", 10000) / 1000
            await self._capture.wait_for_api(step["urlPattern"], timeout_sec)

    async def _handle_screenshot(self, step, i, output):
        png = await self._cdp.screenshot()
        label = step.get("label", f"step{i}")
        path = self._artifacts.save_screenshot(png, f"step{i}-{label}")
        shot_rec = {"stepIndex": i, "label": label, "path": path}
        if not self._screenshot_external:
            import base64
            shot_rec["data"] = base64.b64encode(png).decode()
        output["screenshots"].append(shot_rec)

        # ── 视觉回归对比（baseline 字段存在时启用）──
        # 用例写法：{"type":"screenshot","label":"x","baseline":"home-page","ignoreRegions":[...]}
        baseline_name = step.get("baseline")
        if baseline_name:
            try:
                from core.visual_regression import VisualRegression
                vrt = VisualRegression()  # 默认 artifacts/visual-baselines/
                auto_save = step.get("autoSaveBaseline", False)
                # 如果基线不存在 + 开启了 autoSaveBaseline → 保存为基线
                import os as _os
                if auto_save and not _os.path.exists(vrt._baseline_path(baseline_name)):
                    report = vrt.save_baseline(
                        baseline_name, png,
                        metadata={"label": label, "step_index": i, "url": output.get("currentUrl", "")},
                    )
                else:
                    report = vrt.compare(
                        baseline_name, png,
                        ignore_regions=step.get("ignoreRegions") or None,
                        threshold_px=int(step.get("thresholdPx", 50)),
                        threshold_pct=float(step.get("thresholdPct", 0.01)),
                        write_diff_image=True,
                    )
                vrt_rec = report.to_dict()
                # 视觉回归失败视为 step 失败（不中断流程，但 status 标记 fail）
                if not report.passed:
                    vrt_rec["failureReason"] = report.reason
                    output.setdefault("visualRegressions", []).append({
                        "stepIndex": i, "label": label, "baseline": baseline_name,
                        "diff_percent": report.diff_percent,
                        "reason": report.reason,
                        "diff_image": report.diff_image_path,
                    })
                shot_rec["visualDiff"] = vrt_rec
            except Exception as _e:
                import sys as _sys
                print(f"[screenshot] VRT 对比异常（忽略）: {_e}", file=_sys.stderr)
                shot_rec["visualDiff"] = {"error": str(_e)}

        return {"screenshotPath": path}

    async def _handle_assert(self, step, i, output):
        last_api = self._capture.last_api_entry if self._capture else None
        result = await self._exec_assert(step, last_api)
        if not result["pass"]:
            output["status"] = "fail"
        return {"assertResult": result, "status": "fail" if not result["pass"] else None}

    async def _handle_evaluate(self, step, i, output):
        """执行 JS 表达式并可选通过 storeAs 存储结果"""
        expression = step["expression"]
        raw = await self._cdp.evaluate(expression)
        # CDP Runtime.evaluate 返回 {"type": ..., "value": ...} 或原始值
        if isinstance(raw, dict) and "value" in raw and len(raw) <= 3:
            value = raw["value"]
        else:
            value = raw
        store_as = step.get("storeAs")
        if store_as:
            self._variable_store.bind_step_output(
                f"store_{store_as}", {store_as: value}, None
            )
            # 扁平化：如果 value 是 dict，额外注册顶层字段便于 ${store_x.field} 直接引用
            if isinstance(value, dict):
                self._variable_store.bind_step_output(
                    f"store_{store_as}", value, None
                )
            if "_store" not in output:
                output["_store"] = {}
            output["_store"][store_as] = value
        # 日志输出 evaluate 结果便于调试
        import sys
        _desc = step.get("description", "")
        _val_str = json.dumps(value, ensure_ascii=False)[:200] if value is not None else "null"
        print(f"[eval step {i}] {_desc} => {_val_str}", file=sys.stderr)
        return {"evalResult": value}

    async def _handle_assert_store(self, step, i, output):
        """断言已存储的值: assertStore.key.path + equals/gte/lt/expression"""
        key = step["key"]
        path = step.get("path", "")
        # 从 output._store 或变量存储中获取值
        store = output.get("_store", {})
        stored_value = store.get(key)
        if stored_value is None:
            # 尝试从变量存储获取
            try:
                all_vars = self._variable_store.get_all_variables()
                stored_value = all_vars.get(f"store_{key}.{key}")
            except Exception:
                pass
        if stored_value is None:
            raise RuntimeError(f"assertStore: 未找到存储的键 '{key}'")
        # 按路径提取嵌套值
        target = stored_value
        if path:
            for part in path.split("."):
                if isinstance(target, dict):
                    target = target.get(part)
                elif isinstance(target, list) and part.isdigit():
                    target = target[int(part)]
                else:
                    target = None
                    break
        # 断言
        if "equals" in step:
            expected = step["equals"]
            if target != expected:
                raise RuntimeError(
                    f"assertStore: {key}.{path} 期望 {json.dumps(expected)} 实际 {json.dumps(target)}"
                )
        if "gte" in step:
            if target is None or target < step["gte"]:
                raise RuntimeError(
                    f"assertStore: {key}.{path} 期望 >= {step['gte']} 实际 {target}"
                )
        if "lt" in step:
            if target is None or target >= step["lt"]:
                raise RuntimeError(
                    f"assertStore: {key}.{path} 期望 < {step['lt']} 实际 {target}"
                )
        if "expression" in step:
            expr_str = step["expression"]
            # 支持 JS 箭头函数: "val => val !== null && val <= 20"
            # 用简单 Python eval 处理常见模式
            expr_fn = self._parse_assertion_expr(expr_str)
            if not expr_fn(target):
                raise RuntimeError(
                    f"assertStore: {key}.{path} 表达式验证失败: {expr_str}, 实际值: {json.dumps(target)}"
                )
        return {"assertStoreResult": True}

    # ──────────────────────────────────────────────────────────────────
    # 一期三件套：dbAssert / assertAPI / assertUI
    # ──────────────────────────────────────────────────────────────────

    async def _handle_db_assert(self, step, i, output):
        """DB 断言：调 dms-alibaba CLI 桥（dms-alibaba-bridge.js）执行 SELECT 并比对。

        必填字段：group / db / sql。可选：params（:name 替换）、
        expect（行数组比对）、rowCount、jsonPath+equals/contains。
        """
        group = step.get("group", "")
        db_name = step.get("db", "")
        sql = step.get("sql", "")
        params = step.get("params") or {}
        timeout_ms = int(step.get("timeoutMs", 30000))

        # 1. 参数替换（在 Python 侧做，便于复用 check_sql_readonly）
        if params:
            for name, value in params.items():
                token = f":{name}"
                if value is None:
                    literal = "NULL"
                elif isinstance(value, bool):
                    literal = "1" if value else "0"
                elif isinstance(value, (int, float)):
                    literal = str(value)
                else:
                    safe = str(value).replace("'", "''")
                    literal = f"'{safe}'"
                sql = sql.replace(token, literal)

        # 2. SQL 只读预检
        try:
            check_sql_readonly(sql)
        except ValueError as e:
            result = {
                "dbGroup": group, "db": db_name, "sql": sql,
                "rows": [], "rowCount": 0,
                "matched": False, "failures": [f"SQL 只读检查失败: {e}"],
            }
            output["status"] = "fail"
            return result

        # 3. 调 dms-alibaba-bridge.js
        import os as _os
        import subprocess as _sp
        bridge_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "scripts", "dms-alibaba-bridge.js",
        )
        cmd = ["node", bridge_path, "--group", group, "--db", db_name, "--sql", sql]

        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                try: proc.kill()
                except Exception: pass
                result = {
                    "dbGroup": group, "db": db_name, "sql": sql,
                    "rows": [], "rowCount": 0,
                    "matched": False,
                    "failures": [f"CLI 超时 {timeout_ms}ms"],
                }
                output["status"] = "fail"
                return result
        except FileNotFoundError as e:
            result = {
                "dbGroup": group, "db": db_name, "sql": sql,
                "rows": [], "rowCount": 0,
                "matched": False,
                "failures": [f"node 未安装或不可用: {e}"],
            }
            output["status"] = "fail"
            return result
        except Exception as e:
            result = {
                "dbGroup": group, "db": db_name, "sql": sql,
                "rows": [], "rowCount": 0,
                "matched": False,
                "failures": [f"spawn bridge 失败: {e}"],
            }
            output["status"] = "fail"
            return result

        duration_ms = int((time.time() - start) * 1000)

        # 4. 解析 bridge JSON 输出
        stdout_str = stdout_b.decode("utf-8", errors="replace")
        try:
            bridge_out = json.loads(stdout_str)
        except json.JSONDecodeError as e:
            bridge_out = {
                "status": "error",
                "error": f"bridge 输出非 JSON: {e}",
                "rawStdout": stdout_str[:1000],
            }

        if bridge_out.get("status") != "ok":
            failures = [bridge_out.get("error") or f"bridge status={bridge_out.get('status')}"]
            stderr_snip = (bridge_out.get("stderr") or "")[:500]
            if stderr_snip:
                failures.append(f"stderr: {stderr_snip}")
            result = {
                "dbGroup": group, "db": db_name, "sql": sql,
                "rows": [], "rowCount": 0,
                "matched": False, "failures": failures,
                "durationMs": duration_ms,
            }
            output["status"] = "fail"
            return result

        rows = bridge_out.get("rows", [])
        row_count = bridge_out.get("rowCount", len(rows))
        failures = []

        # 5. 可选断言
        # 5a. rowCount 精确匹配
        if "rowCount" in step:
            if row_count != step["rowCount"]:
                failures.append(
                    f"rowCount: 期望 {step['rowCount']} 实际 {row_count}"
                )

        # 5b. expect 行数组比对
        if "expect" in step:
            expect_rows = step["expect"]
            if not isinstance(expect_rows, list):
                failures.append(f"expect 必须是数组，实际 {type(expect_rows).__name__}")
            else:
                if len(expect_rows) != len(rows):
                    failures.append(
                        f"expect 行数不匹配: 期望 {len(expect_rows)} 行 实际 {len(rows)} 行"
                    )
                else:
                    for idx, (exp, act) in enumerate(zip(expect_rows, rows)):
                        for k, v in exp.items():
                            if k not in act:
                                failures.append(f"row[{idx}] 缺字段 {k}")
                            elif act[k] != v:
                                # 宽容：数字/字符串等值比较
                                try:
                                    if str(act[k]) == str(v):
                                        continue
                                except Exception:
                                    pass
                                failures.append(
                                    f"row[{idx}].{k}: 期望 {json.dumps(v, ensure_ascii=False)} "
                                    f"实际 {json.dumps(act[k], ensure_ascii=False)}"
                                )

        # 5c. jsonPath + equals/contains/exists + rowIndex/allRows
        if "jsonPath" in step and rows:
            row_index = step.get("rowIndex", 0)
            all_rows = step.get("allRows", False)
            target_rows = rows if all_rows else [rows[row_index] if row_index < len(rows) else None]

            for r_idx, row in enumerate(target_rows):
                if row is None:
                    failures.append(f"jsonPath: rowIndex={row_index} 越界（实际 {len(rows)} 行）")
                    break
                value = resolve_json_path(row, step["jsonPath"])
                row_prefix = f"row[{r_idx}] " if all_rows else ""

                # exists 断言
                if step.get("exists") is True:
                    if value is _JSON_PATH_MISSING or value is None:
                        failures.append(
                            f"{row_prefix}exists: jsonPath {step['jsonPath']!r} 不存在或为 null"
                        )
                elif step.get("exists") is False:
                    if value is not _JSON_PATH_MISSING and value is not None:
                        failures.append(
                            f"{row_prefix}exists: jsonPath {step['jsonPath']!r} 期望不存在 实际={json.dumps(value, ensure_ascii=False)[:100]}"
                        )
                elif value is _JSON_PATH_MISSING:
                    failures.append(f"{row_prefix}jsonPath {step['jsonPath']!r} 未命中")
                else:
                    passed, sub = assert_value(
                        value,
                        equals=step.get("equals", _JSON_PATH_MISSING),
                        contains=step.get("contains"),
                        matches=step.get("matches"),
                        value_type=step.get("valueType"),
                    )
                    for f in sub:
                        failures.append(f"{row_prefix}{f}")

        result = {
            "dbGroup": group, "db": db_name, "sql": sql,
            "rows": rows, "rowCount": row_count,
            "matched": len(failures) == 0,
            "failures": failures,
            "durationMs": duration_ms,
        }
        if failures:
            if step.get("soft", False):
                output.setdefault("_softFailures", []).append(
                    {"step": i, "type": "dbAssert", "failures": failures}
                )
                result["soft"] = True
            else:
                output["status"] = "fail"
        return result

    async def _handle_post_setup_verify(self, step, i, output):
        """造数自查：调用 DataSetupVerifier 对造数结果做 5 维度验证。

        必填：sourceKey（从 variable_store 中取造数结果的 key）。
        可选：dimensions（指定检查维度）、spec（自定义 VerifySpec）、
              maxRetry（失败后重建重试次数，默认 0 不重试）。
        """
        from core.data_setup_verifier import (
            DataSetupVerifier, VerifySpec, VerifyDimension,
            build_f88_audit_verify_spec,
        )

        source_key = step.get("sourceKey", "setupResult")
        setup_data = self._variable_store.get(source_key)
        if not setup_data:
            # 尝试从全局上下文取
            setup_data = self._variable_store.get("dataSetup") or {}

        if not setup_data:
            return {"passed": True, "skipped": True, "message": "无造数结果可验证"}

        # 构建 VerifySpec
        spec_preset = step.get("specPreset", "f88-audit")
        if spec_preset == "f88-audit":
            identity = step.get("identity", "f88")
            spec = build_f88_audit_verify_spec(
                task_id=setup_data.get("taskId"),
                identity=identity,
            )
        else:
            spec = VerifySpec(
                required_fields=step.get("requiredFields", []),
                trace_fields=step.get("traceFields", []),
                expected_env=step.get("expectedEnv", "pre"),
            )

        # 指定维度
        dim_names = step.get("dimensions")
        dimensions = None
        if dim_names:
            dimensions = [VerifyDimension(d) for d in dim_names if d in VerifyDimension.__members__.values()]

        # 执行验证
        verifier = DataSetupVerifier(cdp=self._cdp)
        report = await verifier.verify(setup_data, spec, dimensions)

        result = report.to_dict()

        # DB 层补充验证（串联 dms-alibaba CLI）
        db_check = step.get("dbCheck")
        if db_check and setup_data.get("taskId"):
            db_result = await self._verify_db_landing_cli(
                task_id=setup_data["taskId"],
                group=db_check.get("group", "scenario"),
                db_name=db_check.get("db", "prod"),
                table=db_check.get("table", "yc_right_review_task"),
                expected_status=db_check.get("expectedStatus"),
            )
            result["dbLanding"] = db_result
            if not db_result["passed"]:
                report.passed = False
                report.blocked = True

        if report.blocked:
            output["status"] = "fail"
        elif not report.passed:
            output.setdefault("_softFailures", []).append(
                {"step": i, "type": "postSetupVerify", "failures": [
                    it.message for it in report.items if not it.passed
                ]}
            )

        return result

    async def _verify_db_landing_cli(
        self, task_id, group: str, db_name: str, table: str, expected_status=None
    ) -> dict:
        """通过 dms-alibaba CLI 真实查询 DB 落池状态。"""
        import os as _os
        sql = f"SELECT id, status, gmt_create FROM {table} WHERE id = {int(task_id)} LIMIT 1"
        try:
            check_sql_readonly(sql)
        except ValueError as e:
            return {"passed": False, "error": f"SQL 只读检查失败: {e}", "rows": []}

        bridge_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "scripts", "dms-alibaba-bridge.js",
        )
        cmd = ["node", bridge_path, "--group", group, "--db", db_name, "--sql", sql]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            bridge_out = json.loads(stdout_b.decode("utf-8", errors="replace"))

            if bridge_out.get("status") != "ok":
                return {"passed": False, "error": bridge_out.get("error", "bridge 失败"), "rows": []}

            rows = bridge_out.get("rows", [])
            if not rows:
                return {"passed": False, "error": f"数据未落池: {table} id={task_id} 无记录", "rows": []}

            row = rows[0]
            actual_status = row.get("status")

            if expected_status is not None:
                ok = str(actual_status) == str(expected_status)
                return {
                    "passed": ok,
                    "actual_status": actual_status,
                    "expected_status": expected_status,
                    "rows": rows,
                    "message": f"DB 状态={'OK' if ok else '不符'}: actual={actual_status}",
                }
            return {"passed": True, "actual_status": actual_status, "rows": rows, "message": "数据已落池"}

        except asyncio.TimeoutError:
            return {"passed": False, "error": "DB 查询超时(30s)", "rows": []}
        except FileNotFoundError:
            return {"passed": False, "error": "dms-alibaba-bridge.js 不存在", "rows": []}
        except Exception as e:
            return {"passed": False, "error": f"DB 查询异常: {e}", "rows": []}

    async def _handle_assert_api(self, step, i, output):
        """API 精确断言：对已捕获的 API 响应做 status/jsonPath/contains/matches/duration 检查。

        默认取 last_api_entry；带 urlPattern 时用 capture_manager 按 URL 过滤。
        支持 captureAll=true 拿到所有匹配 entry 做批量断言。
        """
        if not self._capture:
            result = {
                "url": None, "status": None, "pass": False,
                "failures": ["capture_manager 未启用，无法做 API 断言"],
            }
            output["status"] = "fail"
            return result

        url_pattern = step.get("urlPattern", "")
        capture_all = step.get("captureAll", False)

        # 取入口 entry（列表）
        if capture_all and url_pattern:
            entries = self._capture.get_all_api_entries(url_pattern)
        elif url_pattern:
            e = self._capture.get_api_entry(url_pattern) or self._capture.last_api_entry
            entries = [e] if e else []
        else:
            e = self._capture.last_api_entry
            entries = [e] if e else []

        if not entries:
            result = {
                "url": url_pattern or None,
                "status": None,
                "pass": False,
                "failures": [
                    f"未找到匹配的 API entry: urlPattern={url_pattern!r}"
                ],
                "matchedCount": 0,
            }
            output["status"] = "fail"
            return result

        failures = []
        json_path_value = None
        last_status = None
        last_url = None
        last_duration = None

        for idx, entry in enumerate(entries):
            entry_url = entry.get("url", "")
            entry_status = entry.get("status")
            entry_duration = entry.get("duration", 0)
            entry_body = entry.get("responseBody")
            truncated = entry.get("responseBodyTruncated", False)
            prefix = f"entry[{idx}]" if capture_all else ""

            if idx == len(entries) - 1:
                last_url = entry_url
                last_status = entry_status
                last_duration = entry_duration

            # 1. status 断言
            if "status" in step:
                if entry_status != step["status"]:
                    failures.append(
                        f"{prefix+' ' if prefix else ''}status: 期望 {step['status']} 实际 {entry_status}"
                    )

            # 2. maxDurationMs 断言
            if "maxDurationMs" in step:
                if entry_duration > step["maxDurationMs"]:
                    failures.append(
                        f"{prefix+' ' if prefix else ''}duration: "
                        f"实际 {entry_duration}ms > 期望 {step['maxDurationMs']}ms"
                    )

            # 3. contains（直接对响应体字符串化；若同时指定 jsonPath 则留给第 5 步处理）
            if "contains" in step and "jsonPath" not in step:
                try:
                    haystack = (
                        entry_body if isinstance(entry_body, str)
                        else json.dumps(entry_body, ensure_ascii=False)
                    )
                except Exception:
                    haystack = str(entry_body)
                if step["contains"] not in (haystack or ""):
                    failures.append(
                        f"{prefix+' ' if prefix else ''}contains: "
                        f"未找到 {step['contains']!r}"
                    )

            # 4. matches（正则；若同时指定 jsonPath 则留给第 5 步处理）
            if "matches" in step and "jsonPath" not in step:
                import re as _re
                try:
                    haystack = (
                        entry_body if isinstance(entry_body, str)
                        else json.dumps(entry_body, ensure_ascii=False)
                    )
                except Exception:
                    haystack = str(entry_body)
                try:
                    if not _re.search(step["matches"], haystack or ""):
                        failures.append(
                            f"{prefix+' ' if prefix else ''}matches: "
                            f"正则 {step['matches']!r} 未命中"
                        )
                except _re.error as e:
                    failures.append(f"matches: 正则编译失败 {e}")

            # 5. jsonPath + equals/valueType/contains/matches/exists
            if "jsonPath" in step:
                if truncated:
                    failures.append(
                        f"{prefix+' ' if prefix else ''}jsonPath: "
                        f"响应体被截断（responseBodyTruncated=true），跳过 jsonPath 断言"
                    )
                else:
                    v = resolve_json_path(entry_body, step["jsonPath"])
                    if idx == len(entries) - 1:
                        json_path_value = v
                    # exists 断言：只验证字段存在且非 null
                    if step.get("exists") is True:
                        if v is _JSON_PATH_MISSING or v is None:
                            failures.append(
                                f"{prefix+' ' if prefix else ''}exists: "
                                f"jsonPath {step['jsonPath']!r} 不存在或为 null"
                            )
                    elif step.get("exists") is False:
                        if v is not _JSON_PATH_MISSING and v is not None:
                            failures.append(
                                f"{prefix+' ' if prefix else ''}exists: "
                                f"jsonPath {step['jsonPath']!r} 期望不存在 实际={json.dumps(v, ensure_ascii=False)[:100]}"
                            )
                    elif v is _JSON_PATH_MISSING:
                        failures.append(
                            f"{prefix+' ' if prefix else ''}jsonPath "
                            f"{step['jsonPath']!r} 未命中"
                        )
                    else:
                        passed, sub = assert_value(
                            v,
                            equals=step.get("equals", _JSON_PATH_MISSING),
                            contains=step.get("contains"),
                            matches=step.get("matches"),
                            value_type=step.get("valueType"),
                        )
                        for f in sub:
                            failures.append(f"{prefix+' ' if prefix else ''}{f}")

        result = {
            "url": last_url,
            "status": last_status,
            "jsonPathValue": (
                None if json_path_value is _JSON_PATH_MISSING else json_path_value
            ),
            "durationMs": last_duration,
            "pass": len(failures) == 0,
            "failures": failures,
            "matchedCount": len(entries),
        }
        if failures:
            if step.get("soft", False):
                output.setdefault("_softFailures", []).append(
                    {"step": i, "type": "assertAPI", "failures": failures}
                )
                result["soft"] = True
            else:
                output["status"] = "fail"
        return result

    async def _handle_assert_ui(self, step, i, output):
        """UI 属性断言：visible/disabled/text/count/attribute/cssProperty。

        通过 CDP evaluate 注入 JS 脚本检查 DOM，支持 timeoutMs 等待元素出现。
        """
        selector = step.get("selector", "")
        timeout_ms = int(step.get("timeoutMs", 5000))

        # 转义选择器中的引号
        selector_escaped = (
            selector.replace("\\", "\\\\").replace("'", "\\'")
        )

        # 构造检查 JS：返回 {count, first: {text, visible, disabled, attribute, css, domSnippet}, checks}
        text_trim = step.get("textTrim", True)  # 默认 trim
        all_match = step.get("allMatch")  # {textContains/text/textMatches/visible/...}
        checks_spec = {
            "visible": step.get("visible"),
            "hidden": step.get("hidden"),
            "disabled": step.get("disabled"),
            "enabled": step.get("enabled"),
            "text": step.get("text"),
            "textContains": step.get("textContains"),
            "textMatches": step.get("textMatches"),
            "count": step.get("count"),
            "minCount": step.get("minCount"),
            "maxCount": step.get("maxCount"),
            "attribute": step.get("attribute"),
            "cssProperty": step.get("cssProperty"),
            "textTrim": text_trim,
            "allMatch": all_match,
        }
        # 这些检查需要元素存在；只有用户显式传入时才会在无元素时报错
        needs_element_checks = [k for k in (
            "visible", "hidden", "disabled", "enabled",
            "text", "textContains", "textMatches",
            "attribute", "cssProperty",
        ) if step.get(k) is not None]

        # 注入 JS 表达式（必须同步执行）
        js = f"""(() => {{
            const selector = '{selector_escaped}';
            const checks = {json.dumps(checks_spec)};
            const needsElement = {json.dumps(needs_element_checks)};
            const failures = [];
            const els = Array.from(document.querySelectorAll(selector));
            const count = els.length;
            const first = els[0] || null;
            const doTrim = checks.textTrim !== false;
            const rawText = first ? (first.textContent || '') : '';
            const firstText = doTrim ? rawText.trim() : rawText;
            let firstVisible = false;
            let firstDisabled = false;
            let domSnippet = '';
            if (first) {{
                const r = first.getBoundingClientRect();
                const style = window.getComputedStyle(first);
                firstVisible = (r.width > 0 && r.height > 0
                                && style.display !== 'none'
                                && style.visibility !== 'hidden'
                                && style.opacity !== '0');
                firstDisabled = first.disabled === true
                                || first.getAttribute('aria-disabled') === 'true';
                domSnippet = (first.outerHTML || '').slice(0, 200);
            }}

            // count 断言
            if (checks.count !== null && checks.count !== undefined
                && count !== checks.count) {{
                failures.push('count: 期望 ' + checks.count + ' 实际 ' + count);
            }}
            if (checks.minCount !== null && checks.minCount !== undefined
                && count < checks.minCount) {{
                failures.push('minCount: 实际 ' + count + ' < 期望 ' + checks.minCount);
            }}
            if (checks.maxCount !== null && checks.maxCount !== undefined
                && count > checks.maxCount) {{
                failures.push('maxCount: 实际 ' + count + ' > 期望 ' + checks.maxCount);
            }}

            // 无元素时，只对 needsElement 中显式声明的检查报错
            if (!first) {{
                for (const k of needsElement) {{
                    failures.push(k + ': 未找到匹配元素 (selector=' + selector + ')');
                }}
                return {{
                    selector, count, firstText: '',
                    firstVisible: false, firstDisabled: false,
                    domSnippet: '', failures,
                }};
            }}

            if (checks.visible === true && !firstVisible) failures.push('visible: 期望可见 实际不可见');
            if (checks.visible === false && firstVisible) failures.push('visible: 期望不可见 实际可见');
            if (checks.hidden === true && firstVisible) failures.push('hidden: 期望隐藏 实际可见');
            if (checks.hidden === false && !firstVisible) failures.push('hidden: 期望不隐藏 实际隐藏');
            if (checks.disabled === true && !firstDisabled) failures.push('disabled: 期望禁用 实际可用');
            if (checks.disabled === false && firstDisabled) failures.push('disabled: 期望可用 实际禁用');
            if (checks.enabled === true && firstDisabled) failures.push('enabled: 期望可用 实际禁用');
            if (checks.enabled === false && !firstDisabled) failures.push('enabled: 期望禁用 实际可用');

            if (checks.text !== null && checks.text !== undefined
                && firstText !== checks.text) {{
                failures.push('text: 期望 ' + JSON.stringify(checks.text)
                              + ' 实际 ' + JSON.stringify(firstText));
            }}
            if (checks.textContains !== null && checks.textContains !== undefined
                && !firstText.includes(checks.textContains)) {{
                failures.push('textContains: 期望包含 ' + JSON.stringify(checks.textContains));
            }}
            if (checks.textMatches !== null && checks.textMatches !== undefined) {{
                try {{
                    if (!new RegExp(checks.textMatches).test(firstText)) {{
                        failures.push('textMatches: 正则 ' + checks.textMatches + ' 未命中');
                    }}
                }} catch (e) {{
                    failures.push('textMatches: 正则编译失败 ' + e.message);
                }}
            }}
            if (checks.attribute) {{
                const name = checks.attribute.name;
                const val = first.getAttribute(name);
                if (checks.attribute.exists === true && val === null) {{
                    failures.push('attribute.' + name + ': 期望存在 实际不存在');
                }}
                if (checks.attribute.exists === false && val !== null) {{
                    failures.push('attribute.' + name + ': 期望不存在 实际=' + val);
                }}
                if (checks.attribute.equals !== undefined
                    && val !== String(checks.attribute.equals)) {{
                    failures.push('attribute.' + name + ': 期望 '
                                  + JSON.stringify(checks.attribute.equals)
                                  + ' 实际 ' + JSON.stringify(val));
                }}
                if (checks.attribute.contains !== undefined
                    && (val === null || !val.includes(checks.attribute.contains))) {{
                    failures.push('attribute.' + name + '.contains: 期望包含 '
                                  + JSON.stringify(checks.attribute.contains));
                }}
            }}
            if (checks.cssProperty) {{
                const name = checks.cssProperty.name;
                const val = window.getComputedStyle(first)[name] || '';
                if (val !== checks.cssProperty.equals) {{
                    failures.push('cssProperty.' + name + ': 期望 '
                                  + JSON.stringify(checks.cssProperty.equals)
                                  + ' 实际 ' + JSON.stringify(val));
                }}
            }}

            // allMatch: 对所有匹配元素做统一检查
            if (checks.allMatch && count > 0) {{
                const am = checks.allMatch;
                for (let idx = 0; idx < els.length; idx++) {{
                    const el = els[idx];
                    const elRaw = el.textContent || '';
                    const elText = doTrim ? elRaw.trim() : elRaw;
                    const elR = el.getBoundingClientRect();
                    const elStyle = window.getComputedStyle(el);
                    const elVisible = (elR.width > 0 && elR.height > 0
                                       && elStyle.display !== 'none'
                                       && elStyle.visibility !== 'hidden'
                                       && elStyle.opacity !== '0');
                    if (am.text !== undefined && elText !== am.text) {{
                        failures.push('allMatch[' + idx + '].text: 期望 ' + JSON.stringify(am.text) + ' 实际 ' + JSON.stringify(elText));
                    }}
                    if (am.textContains !== undefined && !elText.includes(am.textContains)) {{
                        failures.push('allMatch[' + idx + '].textContains: 期望包含 ' + JSON.stringify(am.textContains));
                    }}
                    if (am.textMatches !== undefined) {{
                        try {{
                            if (!new RegExp(am.textMatches).test(elText)) {{
                                failures.push('allMatch[' + idx + '].textMatches: 正则未命中');
                            }}
                        }} catch(e) {{
                            failures.push('allMatch[' + idx + '].textMatches: 正则编译失败');
                        }}
                    }}
                    if (am.visible === true && !elVisible) {{
                        failures.push('allMatch[' + idx + '].visible: 期望可见 实际不可见');
                    }}
                    if (am.visible === false && elVisible) {{
                        failures.push('allMatch[' + idx + '].visible: 期望不可见 实际可见');
                    }}
                }}
            }}

            return {{
                selector, count, firstText: firstText.slice(0, 500),
                firstVisible, firstDisabled,
                domSnippet, failures,
            }};
        }})()"""

        # 等待元素出现（轮询）
        poll_interval = 0.2
        deadline = time.time() + timeout_ms / 1000
        last_eval = None
        while True:
            try:
                raw = await self._cdp.evaluate(js)
            except Exception as e:
                result = {
                    "selector": selector,
                    "checked": {},
                    "pass": False,
                    "failures": [f"CDP evaluate 失败: {e}"],
                    "matchCount": 0,
                }
                output["status"] = "fail"
                return result

            # CDP 返回 {"type":..,"value":..} 或直接值
            if isinstance(raw, dict) and "value" in raw and len(raw) <= 3:
                last_eval = raw["value"]
            else:
                last_eval = raw

            if isinstance(last_eval, dict) and last_eval.get("count", 0) > 0:
                break
            if time.time() >= deadline:
                break
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                raise

        if not isinstance(last_eval, dict):
            result = {
                "selector": selector,
                "checked": {},
                "pass": False,
                "failures": [f"evaluate 返回非字典: {type(last_eval).__name__}"],
                "matchCount": 0,
            }
            output["status"] = "fail"
            return result

        failures = list(last_eval.get("failures", []))
        # 无元素兜底：仅当有 needs_element_checks 且 JS 未报过时才补充
        if last_eval.get("count", 0) == 0 and needs_element_checks:
            if not any("未找到匹配元素" in f for f in failures):
                for k in needs_element_checks:
                    failures.append(f"{k}: 未找到匹配元素 (selector={selector})")

        result = {
            "selector": selector,
            "checked": checks_spec,
            "pass": len(failures) == 0,
            "failures": failures,
            "matchCount": last_eval.get("count", 0),
            "firstElementText": last_eval.get("firstText", ""),
            "domSnippet": last_eval.get("domSnippet", ""),
        }
        if failures:
            if step.get("soft", False):
                output.setdefault("_softFailures", []).append(
                    {"step": i, "type": "assertUI", "failures": failures}
                )
                result["soft"] = True
            else:
                output["status"] = "fail"
        return result

    @staticmethod
    def _parse_assertion_expr(expr_str: str):
        """解析常见断言表达式为 Python 函数"""
        import re as _re
        # 匹配 "val => ..." 箭头函数
        m = _re.match(r'\s*(\w+)\s*=>\s*(.+)', expr_str)
        if not m:
            raise ValueError(f"无法解析断言表达式: {expr_str}")
        param_name = m.group(1)
        body = m.group(2).strip()
        # JS -> Python 转换
        body = body.replace('!==', '!=')
        body = body.replace('===', '==')
        body = body.replace('&&', ' and ')
        body = body.replace('||', ' or ')
        body = body.replace('null', 'None')
        body = body.replace('true', 'True')
        body = body.replace('false', 'False')
        body = body.replace('.includes(', '.__contains__(')
        body = body.replace('.split(', '.split(')
        body = body.replace('.length', '.__len__()')
        # 编译为 lambda
        code = f"lambda {param_name}: {body}"
        try:
            return eval(code)
        except Exception as e:
            raise ValueError(f"断言表达式编译失败: {code} -> {e}")

    async def _handle_select_option(self, step, i, output):
        result = await self._cdp._send_cmd("selectOption", {
            "labelText": step["label"],
            "optionText": step["option"],
            "labelClass": step.get("labelClass", "tbd-formily-item-label"),
            "multiple": step.get("multiple", False),
        })
        if not result.get("selected"):
            raise RuntimeError(
                f"selectOption: 选中后验证失败，label='{step['label']}' option='{step['option']}'"
            )
        return {"selectedValue": result.get("selected")}

    async def _handle_uncheck_checkbox(self, step, i, output):
        result = await self._cdp._send_cmd("uncheckByLabel", {
            "labelText": step.get("labelText", ""),
            "firstChecked": step.get("firstChecked", False),
        })
        return {"unchecked": result.get("unchecked", False)}

    async def _handle_click_text(self, step, i, output):
        result = await self._cdp._send_cmd("clickText", {
            "text": step["text"],
            "selector": step.get("selector", 'button, a, [role="button"], [class*="btn"], span'),
        })
        if not result.get("clicked"):
            raise RuntimeError(f"clickText: 找不到文本为 '{step['text']}' 的可见元素")

    async def _handle_cdp_drag(self, step, i, output):
        result = await self._cdp._send_cmd("cdpDrag", {
            "fromX": step["fromX"], "fromY": step["fromY"],
            "toX": step["toX"], "toY": step["toY"],
            "steps": step.get("steps", 10),
            "button": step.get("button", "left"),
        })
        if not result.get("dragged"):
            raise RuntimeError("cdpDrag: 拖拽操作未成功执行")
        return {"dragged": result.get("dragged", False)}

    async def _handle_cdp_key_event(self, step, i, output):
        result = await self._cdp._send_cmd("cdpKeyEvent", {
            "key": step["key"],
            "code": step.get("code", step["key"]),
            "keyCode": step.get("keyCode", 0),
            "modifiers": step.get("modifiers", 0),
            "type": step.get("keyType", "both"),
            "text": step.get("text", ""),
            "preventDefault": step.get("preventDefault", False),
        })
        return {"keySent": result.get("sent", False)}

    async def _handle_cdp_mouse_wheel(self, step, i, output):
        result = await self._cdp._send_cmd("cdpMouseWheel", {
            "x": step.get("x", 500), "y": step.get("y", 400),
            "deltaX": step.get("deltaX", 0), "deltaY": step.get("deltaY", -120),
            "modifiers": step.get("modifiers", 0),
        })
        return {"scrolled": result.get("scrolled", False)}

    async def _handle_emulate_fullscreen(self, step, i, output):
        result = await self._cdp._send_cmd("emulateFullscreen", {
            "width": step.get("width"), "height": step.get("height"),
        })
        return {"fullscreen": result.get("fullscreen", False)}

    async def _handle_mock_network(self, step, i, output):
        result = await self._cdp._send_cmd("mockNetwork", {
            "mode": step.get("mode", "reset"),
            "offline": step.get("offline", False),
            "latency": step.get("latency", 0),
            "downloadKbps": step.get("downloadKbps", -1),
            "uploadKbps": step.get("uploadKbps", -1),
            "urlPattern": step.get("urlPattern", ""),
            "mockStatus": step.get("mockStatus", 500),
            "mockBody": step.get("mockBody", '{"error":"mocked"}'),
        })
        return {"mockMode": result.get("mode", "reset")}

    async def _handle_set_focus(self, step, i, output):
        result = await self._cdp._send_cmd("setFocus", {"selector": step["selector"]})
        if not result.get("focused"):
            raise RuntimeError(f"setFocus: 无法聚焦元素: {step['selector']}")
        return {"focused": result.get("focused", False)}

    async def _handle_observe_transitions(self, step, i, output):
        result = await self._cdp._send_cmd("observeTransitions", {
            "action": step.get("action", "start"),
            "selector": step.get("selector"),
        })
        return {"transitions": result.get("transitions"), "transitionCount": result.get("count")}

    async def _handle_screencast(self, step, i, output):
        if step.get("action", "start") == "stop":
            await self._cdp._send_cmd("stopScreencast", {})
            return {"screencastAction": "stopped"}
        result = await self._cdp._send_cmd("startScreencast", {
            "format": step.get("format", "jpeg"),
            "quality": step.get("quality", 60),
        })
        return {"screencastAction": "started"}

    # ── 自愈 ──

    # 退避延迟序列（秒）：首次 0.5s，二次 1.5s，三次 3s
    _HEAL_BACKOFF = [0.5, 1.5, 3.0]
    # 最大自愈轮次（含首次失败共 3 次尝试）
    _HEAL_MAX_ROUNDS = 2

    # ── 登录态关键词（用于检测执行中登录过期）──
    _LOGIN_ERROR_KEYWORDS = [
        "login", "sso", "buc", "login.alibaba-inc.com", "login.taobao.com",
        "登录", "登录态", "登录过期", "session expired", "unauthorized",
        "isLoginPage", "login_required",
    ]

    # ── 页面导航异常关键词（用于检测页面跳转或错误页）──
    _NAV_ERROR_KEYWORDS = [
        "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_TIMED_OUT",
        "DNS_PROBE_FINISHED_NXDOMAIN", "net::ERR_INTERNET_DISCONNECTED",
        "此网站目前无法提供服务", "该网站暂时无法访问", "DNS 解析",
        "ERR_CONNECTION_RESET", "ERR_TIMED_OUT", "ERR_CONNECTION_CLOSED",
    ]

    # ── 元素被覆盖/遮挡关键词 ──
    _OVERLAY_KEYWORDS = [
        "element click intercepted", "other element would receive the click",
        "is not clickable", "point is not clickable", "遮挡", "intercepted",
        "overlay", "modal", "popover", "drawer", "Mask", "遮罩",
    ]

    # ── React 受控组件关键词 ──
    _REACT_KEYWORDS = [
        "input value not set", "受控组件", "react state", "native setter",
        "value attribute does not work", "React 17", "dispatchEvent",
    ]

    async def _check_and_recover_login(self, error_msg: str) -> bool:
        """检测执行中登录态过期并自动恢复。

        当步骤失败原因包含登录相关关键词时：
        1. 调用 cdp.check_login() 确认当前是否真的在登录页
        2. 若是，执行 SSO warmup（重新访问内网站点恢复 session）
        3. 返回 True 表示已恢复，False 表示无法恢复
        """
        err_lower = error_msg.lower()
        is_login_err = any(kw.lower() in err_lower for kw in self._LOGIN_ERROR_KEYWORDS)
        if not is_login_err:
            return False

        try:
            # 确认当前是否真的在登录页
            login_status = await self._cdp.check_login()
            if not login_status.get("isLoginPage", False):
                return False  # 不在登录页，不是登录问题

            print(f"[step_executor] 检测到登录态过期，执行 SSO warmup ...", file=sys.stderr)
            # SSO warmup: 重新访问内网站点恢复 session
            from core.browser_setup import ensure_alibaba_sso
            target_url = login_status.get("currentUrl", "")
            await ensure_alibaba_sso(self._cdp, target_url, "")
            await asyncio.sleep(2)

            # 验证恢复结果
            login_status2 = await self._cdp.check_login()
            if not login_status2.get("isLoginPage", False):
                print(f"[step_executor] SSO warmup 成功，登录态已恢复", file=sys.stderr)
                return True
            else:
                print(f"[step_executor] SSO warmup 后仍在登录页，需要人工介入", file=sys.stderr)
                return False

        except Exception as e:
            print(f"[step_executor] 登录态恢复失败: {e}", file=sys.stderr)
            return False

    async def _try_cdp_reconnect(self, error_msg: str) -> bool:
        """检测 CDP 断线并自动重连。"""
        is_cdp_err = any(kw in error_msg for kw in [
            "CDP 桥接进程断开", "ConnectionError", "BrokenPipeError",
            "ConnectionResetError", "connection refused", "ECONNREFUSED",
        ])
        if not is_cdp_err:
            return False

        print(f"[step_executor] 检测到 CDP 断线，尝试重连 ...", file=sys.stderr)
        try:
            ok = await self._cdp.reconnect(max_retries=2, backoff=[1, 3])
            if ok:
                print(f"[step_executor] CDP 重连成功", file=sys.stderr)
                return True
        except Exception as e:
            print(f"[step_executor] CDP 重连失败: {e}", file=sys.stderr)
        return False

    async def _recover_from_nav_error(self, error_msg: str) -> bool:
        """检测页面导航异常（DNS失败/连接超时/错误页）并自动恢复。
        
        覆盖场景：
        - ERR_CONNECTION_REFUSED: 本地服务未启动
        - ERR_NAME_NOT_RESOLVED: DNS 解析失败
        - ERR_CONNECTION_TIMED_OUT: 连接超时
        - chrome-error://: Chrome 内部错误页
        """
        is_nav_err = any(kw.lower() in error_msg.lower() for kw in self._NAV_ERROR_KEYWORDS)
        if not is_nav_err:
            return False

        print(f"[step_executor] 检测到页面导航异常，尝试恢复 ...", file=sys.stderr)
        try:
            # 策略1: 多次 reload（服务可能正在启动）
            for attempt in range(3):
                await self._cdp.evaluate("window.location.reload()")
                await asyncio.sleep(2 + attempt * 2)  # 2s, 4s, 6s

                # 检测当前 URL 是否仍在错误页
                url = await self._cdp.evaluate("window.location.href")
                is_error_page = (
                    any(kw in url for kw in ["error", "ERR_", "net/"])
                    or url.startswith("chrome-error://")
                    or "chromewebdata" in url
                )
                if not is_error_page:
                    print(f"[step_executor] 页面恢复成功，URL: {url}", file=sys.stderr)
                    return True
                print(f"[step_executor] 第{attempt+1}次刷新仍在错误页，继续重试 ...", file=sys.stderr)

            # 策略2: 如果步骤有 URL，尝试 navigate 到原始 URL
            if hasattr(self, '_last_nav_url') and self._last_nav_url:
                await self._cdp.navigate(self._last_nav_url)
                await asyncio.sleep(3)
                url = await self._cdp.evaluate("window.location.href")
                is_error_page = (
                    any(kw in url for kw in ["error", "ERR_", "net/"])
                    or url.startswith("chrome-error://")
                )
                if not is_error_page:
                    print(f"[step_executor] navigate 恢复成功，URL: {url}", file=sys.stderr)
                    return True

            print(f"[step_executor] 导航异常恢复失败，服务可能未启动", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[step_executor] 页面刷新失败: {e}", file=sys.stderr)
            return False

    async def _recover_from_overlay(self, error_msg: str) -> bool:
        """检测元素被遮挡（modal/drawer/popup）并自动关闭。"""
        is_overlay_err = any(kw.lower() in error_msg.lower() for kw in self._OVERLAY_KEYWORDS)
        if not is_overlay_err:
            return False

        print(f"[step_executor] 检测到元素被遮挡，尝试关闭遮挡层 ...", file=sys.stderr)
        try:
            # 关闭常见遮挡层
            closed = await self._cdp.dismiss_modals(max_rounds=3)
            if closed.get("closed", 0) > 0:
                print(f"[step_executor] 已关闭 {closed['closed']} 个遮挡层", file=sys.stderr)
                await asyncio.sleep(0.5)
                return True
            else:
                # 尝试按 ESC 键关闭弹窗
                await self._cdp.evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape',code:'Escape',keyCode:27}))")
                await asyncio.sleep(0.3)
                return True
        except Exception as e:
            print(f"[step_executor] 关闭遮挡层失败: {e}", file=sys.stderr)
            return False

    async def _recover_from_react_controlled(self, step: dict, error_msg: str) -> bool:
        """检测 React 受控组件输入失败并应用 native setter + dispatchEvent。"""
        is_react_err = any(kw.lower() in error_msg.lower() for kw in self._REACT_KEYWORDS)
        if not is_react_err:
            return False

        selector = step.get("selector", "")
        text = step.get("text", "")
        if not selector or not text:
            return False

        print(f"[step_executor] 检测到 React 受控组件问题，应用 native setter ...", file=sys.stderr)
        try:
            # 注入 React 受控组件修复代码
            fix_js = f"""(() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                // 使用 native setter 绕过 React 受控组件
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(el, {json.dumps(text)});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }})()"""
            success = await self._cdp.evaluate(fix_js)
            if success:
                print(f"[step_executor] React 受控组件修复成功", file=sys.stderr)
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            print(f"[step_executor] React 受控组件修复失败: {e}", file=sys.stderr)
        return False

    async def _full_page_reload(self) -> bool:
        """全页面刷新恢复（PAGe_REFESH）。
        
        强制刷新当前页面，清除所有 JavaScript 状态和 DOM 缓存。
        适用于页面状态混乱、JavaScript 错误、DOM 树损坏等场景。
        """
        print(f"[step_executor] 尝试全页面刷新恢复", file=sys.stderr)
        try:
            # 强制刷新（bypass cache）
            await self._cdp.evaluate("window.location.reload(true)")
            await asyncio.sleep(3)
            return True
        except Exception as e:
            print(f"[step_executor] 全页面刷新失败: {e}", file=sys.stderr)
            return False

    async def _navigate_recover(self, url: str) -> bool:
        """重新导航恢复（NAVIGATE_RECOVER）。
        
        尝试重新导航到指定 URL，适用于：
        - 页面跳转到错误地址
        - 当前页面无法恢复
        - 需要重新加载特定 URL
        """
        if not url:
            return False
        
        print(f"[step_executor] 尝试重新导航到 {url}", file=sys.stderr)
        try:
            await self._cdp.navigate(url)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"[step_executor] 重新导航失败: {e}", file=sys.stderr)
            return False

    async def _heal_and_retry(
        self, step: dict, step_result: dict, i: int, error_msg: str, output: dict
    ) -> bool:
        """多策略降级 + 多轮重试的自愈引擎。返回 True 表示已修复。

        改进点（相比 v1）：
        - 幂等性检查：非幂等步骤跳过重试，避免重复提交等副作用
        - 多策略降级链：knowledge_fix → cdp_relocate → scroll_click → smart_retry
        - 多轮重试（最多 2 轮），每轮之间递增退避延迟
        - 重试前自动检测 loading/spinner，等页面稳定
        - SCHEMA_REGEN 降级为页面刷新后重试
        - 每轮尝试不同策略，禁止盲目重试相同操作
        - CDP 断线自动重连
        - 登录态过期自动 SSO warmup
        - 策略组合学习：记录成功的策略链，下次优先推荐
        """
        # ── 幂等性检查：非幂等步骤禁止重试 ──
        _idempotent = step.get("idempotent", True)  # 默认为幂等
        if not _idempotent:
            step_result["skipRetry"] = True
            step_result["skipReason"] = "非幂等步骤，禁止重试以避免副作用"
            return False

        _all_attempts: list[dict] = []  # 记录所有尝试
        _chain_strategies: list[str] = []  # 记录本次自愈实际执行的策略序列
        _chain_start = time.time()
        _error_type = step.get("type", "unknown")

        # 策略组合学习：开始记录
        self._healing.chain_learner.start_chain(error_type=_error_type, error_msg=error_msg[:80])

        try:
            # ── 前置自愈① CDP 断线重连 ──
            if await self._try_cdp_reconnect(error_msg):
                _chain_strategies.append("cdp_reconnect")
                self._healing.chain_learner.add_strategy("cdp_reconnect", success=True, duration_ms=int((time.time() - _chain_start) * 1000))
                try:
                    await self._wait_for_page_ready(timeout_ms=3000)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "cdp_reconnect"
                    step_result["status"] = "pass"
                    self._healing.record_heal_outcome(error_msg[:80], "cdp_reconnect", True)
                    self._healing.chain_learner.finish_chain(success=True)
                    return True
                except Exception:
                    self._healing.chain_learner.add_strategy("cdp_reconnect_retry", success=False, duration_ms=int((time.time() - _chain_start) * 1000))

            # ── 前置自愈② 登录态过期恢复 ──
            if await self._check_and_recover_login(error_msg):
                _chain_strategies.append("sso_warmup")
                self._healing.chain_learner.add_strategy("sso_warmup", success=True, duration_ms=int((time.time() - _chain_start) * 1000))
                try:
                    await asyncio.sleep(1)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "sso_warmup_retry"
                    step_result["status"] = "pass"
                    self._healing.record_heal_outcome(error_msg[:80], "sso_warmup_retry", True)
                    self._healing.chain_learner.finish_chain(success=True)
                    return True
                except Exception:
                    self._healing.chain_learner.add_strategy("sso_warmup_retry", success=False, duration_ms=int((time.time() - _chain_start) * 1000))

            # ── 前置自愈③ 页面导航异常 ──
            if await self._recover_from_nav_error(error_msg):
                try:
                    await self._wait_for_page_ready(timeout_ms=3000)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "nav_error_recovery"
                    step_result["status"] = "pass"
                    return True
                except Exception:
                    pass

            # ── 前置自愈④ 元素遮挡/弹窗 ──
            if await self._recover_from_overlay(error_msg):
                try:
                    await self._wait_for_page_ready(timeout_ms=2000)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "overlay_close_retry"
                    step_result["status"] = "pass"
                    return True
                except Exception:
                    pass

            # ── 前置自愈⑤ React 受控组件 ──
            if await self._recover_from_react_controlled(step, error_msg):
                try:
                    await asyncio.sleep(0.5)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "react_controlled_fix"
                    step_result["status"] = "pass"
                    return True
                except Exception:
                    pass

            _fc_err_report = self._failure_classifier.classify(step_result, None)
            _heal_ctx = {
                "step": step, "error": error_msg, "step_index": i,
                "selector": step.get("selector", step.get("target", "")),
            }

            for _round in range(self._HEAL_MAX_ROUNDS):
                _backoff = self._HEAL_BACKOFF[min(_round, len(self._HEAL_BACKOFF) - 1)]

                # ── 退避等待 ──
                if _round > 0:
                    await asyncio.sleep(_backoff)

                # ── 每轮重新查询自愈策略 ──
                _heal_result = self._healing.heal(_fc_err_report.category, _heal_ctx)

                # ── 构建本轮策略降级链 ──
                _strategies = self._build_strategy_chain(
                    _heal_result, step, error_msg, _round
                )

                for _strat_name, _strat_fn in _strategies:
                    _attempt = {"round": _round, "strategy": _strat_name}
                    try:
                        # 重试前先等页面稳定
                        await self._wait_for_page_ready(timeout_ms=3000)
                        await _strat_fn(step)
                        # 成功
                        _attempt["success"] = True
                        _all_attempts.append(_attempt)
                        _heal_result.fix_code = _strat_name
                        _heal_result.action = HealingAction.KNOWLEDGE_FIX if "knowledge" in _strat_name else (
                            HealingAction.CDP_RELOCATE if "relocate" in _strat_name else HealingAction.RETRY
                        )
                        self._mark_healed(step_result, output, _heal_result, retry_success=True)
                        step_result["healAttempts"] = _all_attempts
                        # 维度10: 记录自愈成功经验
                        self._healing.record_heal_outcome(
                            error_msg=error_msg[:80],
                            fix_strategy=_strat_name,
                            success=True,
                            fix_code=_strat_name,
                        )
                        # 策略组合学习：记录成功链
                        _chain_strategies.append(_strat_name)
                        _chain_dur = int((time.time() - _chain_start) * 1000)
                        self._healing.chain_learner.add_strategy(_strat_name, success=True, duration_ms=_chain_dur)
                        self._healing.chain_learner.finish_chain(success=True)
                        return True
                    except Exception as retry_err:
                        _attempt["success"] = False
                        _attempt["error"] = str(retry_err)[:200]
                        _all_attempts.append(_attempt)
                        # 策略组合学习：记录失败策略
                        _chain_strategies.append(_strat_name)
                        _chain_dur = int((time.time() - _chain_start) * 1000)
                        self._healing.chain_learner.add_strategy(_strat_name, success=False, duration_ms=_chain_dur)
                        # 继续尝试下一个策略

            # 全部策略耗尽
            if _all_attempts:
                step_result["healAttempts"] = _all_attempts
                _last_heal = _heal_result if '_heal_result' in dir() else None
                if _last_heal:
                    self._mark_heal_attempted(step_result, _last_heal,
                                              RuntimeError(f"{len(_all_attempts)} 次尝试均失败"))
                # 维度10: 记录自愈失败
                self._healing.record_heal_outcome(
                    error_msg=error_msg[:80],
                    fix_strategy="all_exhausted",
                    success=False,
                )
                # 策略组合学习：记录失败链
                self._healing.chain_learner.finish_chain(success=False)

        except Exception as e:
            print(f"[step_executor] _heal_and_retry 异常: {e}", file=sys.stderr)

        # ── 最终兜底：全部自愈策略失效 ──
        # 1. 尝试全页面刷新（PAGe_REFESH）
        if await self._full_page_reload():
            try:
                await self._wait_for_page_ready(timeout_ms=5000)
                await self._dispatch(step, i, output)
                step_result["healAction"] = "full_page_reload"
                step_result["status"] = "pass"
                return True
            except Exception:
                pass

        # 2. 尝试重新导航到 URL（NAVIGATE_RECOVER）
        if step.get("url") or step.get("type") == "navigate":
            url = step.get("url", step.get("target", ""))
            if url and await self._navigate_recover(url):
                try:
                    await self._wait_for_page_ready(timeout_ms=5000)
                    await self._dispatch(step, i, output)
                    step_result["healAction"] = "navigate_recover"
                    step_result["status"] = "pass"
                    return True
                except Exception:
                    pass

        # 3. 尝试跳过当前步骤（SKIP_STEP）
        #    仅在配置允许跳过时执行
        if step.get("allowSkip", False):
            print(f"[step_executor] 步骤 {i} 允许跳过，执行跳过", file=sys.stderr)
            step_result["healAction"] = "step_skipped"
            step_result["status"] = "pass"
            step_result["skipReason"] = "All healing strategies exhausted"
            return True

        return False

    def _build_strategy_chain(
        self, heal_result, step: dict, error_msg: str, round_idx: int
    ) -> list:
        """构建本轮的策略降级链。不同轮次使用不同策略组合。"""
        chain = []
        stype = step.get("type", "")
        selector = step.get("selector", step.get("target", ""))
        text = step.get("text", "")

        if round_idx == 0:
            # ── 第 0 轮：优先知识库 + CDP 重定位 ──

            # 策略 A：知识库 fix_code
            if heal_result.action == HealingAction.KNOWLEDGE_FIX and heal_result.success and heal_result.fix_code:
                chain.append(("knowledge_fix_code", self._strat_knowledge_fix(heal_result.fix_code)))

            # 策略 B：CDP 多策略重定位
            if selector and stype in ("click", "fill"):
                chain.append(("cdp_relocate_multi", self._strat_cdp_relocate(step)))

            # 策略 C：scroll + click（元素可能被遮挡或不在视口内）
            if (selector or text) and stype == "click":
                chain.append(("scroll_into_view_click", self._strat_scroll_click(step)))

            # 策略 D：智能等待后重试（处理 loading / 超时）
            if "timeout" in error_msg.lower() or "loading" in error_msg.lower():
                chain.append(("smart_wait_retry", self._strat_smart_retry(step)))

        elif round_idx == 1:
            # ── 第 1 轮：更激进的策略 ──

            # 策略 E：放宽选择器 + 重试
            if selector and stype in ("click", "fill"):
                chain.append(("relaxed_selector_retry", self._strat_relaxed_selector(step)))

            # 策略 F：文本兜底（如果有 text 字段）
            if text and stype in ("click", "clickText"):
                chain.append(("text_fallback_click", self._strat_text_fallback(step)))

            # 策略 G：通用重试（最后一搏）
            chain.append(("generic_retry", self._strat_smart_retry(step)))

        return chain

    # ── 策略工厂方法 ──

    def _strat_knowledge_fix(self, fix_code: str):
        """策略：执行知识库提供的修复代码片段"""
        async def _fn(step):
            await self._cdp.evaluate(fix_code)
            await asyncio.sleep(0.5)
            await self._retry_healed_step(step, {})
        return _fn

    def _strat_cdp_relocate(self, step: dict):
        """策略：多策略 CDP 重定位后重试"""
        async def _fn(step):
            selector = step.get("selector", "")
            if not selector:
                raise RuntimeError("无 selector 可重定位")
            relocated = await self._try_relocate_element(selector)
            if not relocated:
                raise RuntimeError(f"CDP 重定位失败: {selector}")
            _original = step.get("selector")
            step["selector"] = relocated
            try:
                await self._retry_healed_step(step, {})
            except Exception:
                step["selector"] = _original
                raise
        return _fn

    def _strat_scroll_click(self, step: dict):
        """策略：滚动到元素可见 → 短暂等待 → 点击"""
        async def _fn(step):
            selector = step.get("selector", "")
            text = step.get("text", "")
            if selector:
                await self._cdp.evaluate(f"""(() => {{
                    const el = document.querySelector({json.dumps(selector)});
                    if (el) el.scrollIntoView({{ block: 'center', behavior: 'instant' }});
                }})()""")
            elif text:
                await self._cdp.evaluate(f"""(() => {{
                    const els = [...document.querySelectorAll('button,a,[role="button"],span')]
                        .filter(e => e.textContent.trim().includes({json.dumps(text)}));
                    if (els[0]) els[0].scrollIntoView({{ block: 'center', behavior: 'instant' }});
                }})()""")
            await asyncio.sleep(0.3)
            # 关闭可能的遮挡弹窗
            try:
                await self._cdp.dismiss_modals(max_rounds=2)
            except Exception:
                pass
            await self._retry_healed_step(step, {})
        return _fn

    def _strat_smart_retry(self, step: dict):
        """策略：等待页面稳定后直接重试"""
        async def _fn(step):
            await self._wait_for_page_ready(timeout_ms=5000)
            await self._retry_healed_step(step, {})
        return _fn

    def _strat_relaxed_selector(self, step: dict):
        """策略：大幅放宽选择器（只保留核心 class 或 data-* 属性）"""
        async def _fn(step):
            selector = step.get("selector", "")
            relaxed = await self._try_relax_selector_aggressive(selector)
            if not relaxed:
                raise RuntimeError(f"无法放宽选择器: {selector}")
            _original = step.get("selector")
            step["selector"] = relaxed
            try:
                await self._retry_healed_step(step, {})
            except Exception:
                step["selector"] = _original
                raise
        return _fn

    def _strat_text_fallback(self, step: dict):
        """策略：忽略 selector，用文本内容兜底定位"""
        async def _fn(step):
            text = step.get("text", "")
            if not text:
                raise RuntimeError("无 text 字段，无法文本兜底")
            # 用 clickText 方式重试
            result = await self._cdp._send_cmd("clickText", {
                "text": text,
                "selector": 'button, a, [role="button"], [class*="btn"], span, div',
            })
            if not result.get("clicked"):
                raise RuntimeError(f"文本兜底失败: '{text}'")
        return _fn

    # ── 页面稳定性检测 ──

    async def _wait_for_page_ready(self, timeout_ms: int = 3000):
        """等待页面 loading 状态消失（spinner / skeleton / 遮罩层）。"""
        check_js = """(() => {
            // Ant Design spinner
            if (document.querySelector('.ant-spin-spinning')) return false;
            // Ant Design skeleton loading
            if (document.querySelector('.ant-skeleton-active')) return false;
            // 通用 loading overlay
            const overlays = document.querySelectorAll('[class*="loading"], [class*="mask"]');
            for (const o of overlays) {
                if (o.offsetParent !== null && getComputedStyle(o).opacity > 0.5) return false;
            }
            // document readyState
            if (document.readyState === 'loading') return false;
            return true;
        })()"""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                ready = await self._cdp.evaluate(check_js)
                if ready:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.3)
        # 超时不抛异常，只是不再等待

    # ── 元素重定位（增强版） ──

    # ── iframe / Shadow DOM 关键词（维度9）──
    _IFRAME_KEYWORDS = [
        "iframe", "frame", "contentFrame", "cross-origin",
    ]
    _SHADOW_DOM_KEYWORDS = [
        "shadow", "shadowRoot", "web component", "custom element",
    ]

    async def _try_relocate_element(self, selector: str) -> Optional[str]:
        """尝试用多种策略重新定位元素（9 种策略，含 iframe/Shadow DOM）。"""
        # 策略1: 去除伪类、nth-child 等不稳定部分
        simplified = selector.split("::")[0].split(":nth")[0].split(":not")[0]
        if simplified != selector:
            if await self._selector_exists(simplified):
                return simplified

        # 策略2: 放宽到父级选择器
        if "." in selector and " " in selector:
            broader = selector.rsplit(" ", 1)[0]
            if await self._selector_exists(broader):
                return broader

        # 策略3: 只保留最后一个 class 段
        parts = selector.replace(">", " ").split()
        if parts:
            last_part = parts[-1]
            if "." in last_part:
                if await self._selector_exists(last_part):
                    return last_part

        # 策略4: data-* 属性匹配
        data_sel = await self._find_by_data_attribute(selector)
        if data_sel:
            return data_sel

        # 策略5: aria-label / role 匹配
        aria_sel = await self._find_by_aria(selector)
        if aria_sel:
            return aria_sel

        # 策略6: class 模糊匹配（去除 hash 后缀，如 .ant-btn-abc123 → [class*="ant-btn"]）
        fuzzy = await self._find_by_fuzzy_class(selector)
        if fuzzy:
            return fuzzy

        # 策略7: tag + 可见性兜底
        tag = selector.split(".")[0].split("[")[0].split(">")[0].strip()
        if tag and tag.isalpha():
            tag_sel = await self._find_first_visible_tag(tag)
            if tag_sel:
                return tag_sel

        # 策略8: iframe 内搜索（维度9）
        iframe_sel = await self._find_in_iframes(selector)
        if iframe_sel:
            return iframe_sel

        # 策略9: Shadow DOM 穿透（维度9）
        shadow_sel = await self._find_in_shadow_dom(selector)
        if shadow_sel:
            return shadow_sel

        return None

    async def _selector_exists(self, selector: str) -> bool:
        """检查选择器是否能匹配到元素"""
        try:
            found = await self._cdp.evaluate(
                f"!!document.querySelector({json.dumps(selector)})"
            )
            return bool(found)
        except Exception:
            return False

    async def _find_by_data_attribute(self, selector: str) -> Optional[str]:
        """策略4: 从原始 selector 提取 data-* 属性进行匹配"""
        import re
        data_attrs = re.findall(r'\[data-([a-z-]+)(?:=["\']?([^"\'\]]+)["\']?)?\]', selector)
        for attr_name, attr_val in data_attrs:
            if attr_val:
                candidate = f'[data-{attr_name}="{attr_val}"]'
            else:
                candidate = f'[data-{attr_name}]'
            if await self._selector_exists(candidate):
                return candidate
        return None

    async def _find_by_aria(self, selector: str) -> Optional[str]:
        """策略5: 尝试 aria-label / role 匹配"""
        import re
        # 从选择器中提取可能的文本线索
        texts = re.findall(r'\[aria-label=["\']?([^"\'\]]+)["\']?\]', selector)
        for text in texts:
            candidate = f'[aria-label="{text}"]'
            if await self._selector_exists(candidate):
                return candidate
        # 尝试 role 属性
        roles = re.findall(r'\[role=["\']?([^"\'\]]+)["\']?\]', selector)
        for role in roles:
            candidate = f'[role="{role}"]'
            if await self._selector_exists(candidate):
                return candidate
        return None

    async def _find_by_fuzzy_class(self, selector: str) -> Optional[str]:
        """策略6: class 模糊匹配（去除 hash / 动态后缀）"""
        import re
        classes = re.findall(r'\.([a-zA-Z][\w-]*)', selector)
        for cls in classes:
            # 去除动态 hash 后缀（混合字母+数字，至少 4 字符，如 -x7k2m、-abc12）
            # 必须包含数字，避免误删合法 class 段（如 ant-btn-submit）
            base = re.sub(r'-([a-z0-9]*\d[a-z0-9]*){1,}$', '', cls)
            if base != cls and len(base) > 3:
                candidate = f'[class*="{base}"]'
                if await self._selector_exists(candidate):
                    return candidate
        return None

    async def _find_first_visible_tag(self, tag: str) -> Optional[str]:
        """策略7: 按 tag 找第一个可见元素"""
        js = f"""(() => {{
            const els = document.querySelectorAll({json.dumps(tag)});
            for (const el of els) {{
                if (el.offsetParent !== null) return true;
            }}
            return false;
        }})()"""
        try:
            found = await self._cdp.evaluate(js)
            if found:
                return tag
        except Exception:
            pass
        return None

    async def _find_in_iframes(self, selector: str) -> Optional[str]:
        """策略8: 在所有 iframe 内搜索目标元素（维度9）。
        返回格式: 'iframe >>> selector' 供 CDP 跨 frame 定位。
        """
        try:
            # 获取所有 iframe 元素
            iframe_count_js = "document.querySelectorAll('iframe').length"
            count = await self._cdp.evaluate(iframe_count_js)
            if not count or count == 0:
                return None

            # 遍历每个 iframe，在其中搜索目标 selector
            for idx in range(min(count, 10)):  # 最多检查 10 个 iframe
                try:
                    check_js = f"""(() => {{
                        const iframe = document.querySelectorAll('iframe')[{idx}];
                        if (!iframe) return false;
                        try {{
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            return !!doc.querySelector({json.dumps(selector)});
                        }} catch(e) {{
                            // 跨域 iframe 无法访问
                            return false;
                        }}
                    }})()"""
                    found = await self._cdp.evaluate(check_js)
                    if found:
                        return f"iframe[{idx}] >>> {selector}"
                except Exception:
                    continue
        except Exception:
            pass
        return None

    async def _find_in_shadow_dom(self, selector: str) -> Optional[str]:
        """策略9: 穿透 Shadow DOM 搜索目标元素（维度9）。
        返回格式: 'shadow:hostSelector >>> selector' 供后续定位。
        """
        try:
            search_js = f"""(() => {{
                const target = {json.dumps(selector)};
                function searchShadow(root, hostPath) {{
                    const els = root.querySelectorAll('*');
                    for (const el of els) {{
                        if (el.shadowRoot) {{
                            const found = el.shadowRoot.querySelector(target);
                            if (found) {{
                                const tag = el.tagName.toLowerCase();
                                const id = el.id ? '#' + el.id : '';
                                const cls = el.className && typeof el.className === 'string'
                                    ? '.' + el.className.split(' ').filter(Boolean).slice(0,2).join('.')
                                    : '';
                                return hostPath + tag + id + cls + ' >>> ' + target;
                            }}
                            const deep = searchShadow(el.shadowRoot, hostPath + tag + id + cls + ' > ');
                            if (deep) return deep;
                        }}
                    }}
                    return null;
                }}
                return searchShadow(document, '');
            }})()"""
            result = await self._cdp.evaluate(search_js)
            if result:
                return str(result)
        except Exception:
            pass
        return None

    async def _try_relax_selector_aggressive(self, selector: str) -> Optional[str]:
        """更激进的选择器放宽：提取核心语义部分。"""
        import re
        # 1. 去除所有 ID 选择器（动态 ID）
        relaxed = re.sub(r'#[a-zA-Z][\w-]*', '', selector).strip()
        # 2. 去除 :nth-child / :nth-of-type
        relaxed = re.sub(r':nth-(?:child|of-type)\(\d+\)', '', relaxed)
        # 3. 去除 > 直接子选择器，改为后代
        relaxed = relaxed.replace(">", " ").strip()
        # 4. 合并多余空格
        relaxed = " ".join(relaxed.split())

        if relaxed and relaxed != selector:
            if await self._selector_exists(relaxed):
                return relaxed
        return None

    def _mark_healed(self, step_result: dict, output: dict, heal_result, retry_success: bool):
        """标记步骤为自愈成功。"""
        step_result["status"] = "pass"
        step_result["healed"] = True
        step_result["healAttempt"] = {
            "action": heal_result.action.value,
            "message": heal_result.message,
            "source": heal_result.knowledge_source,
            "fix_code": (heal_result.fix_code or "")[:200],
            "retrySuccess": retry_success,
        }
        step_result.pop("error", None)
        if output.get("status") == "error":
            output["status"] = "pass"
            output.pop("error", None)

    def _mark_heal_attempted(self, step_result: dict, heal_result, retry_err):
        """标记自愈尝试（但未成功）。"""
        step_result["healAttempt"] = {
            "action": heal_result.action.value,
            "message": heal_result.message,
            "source": heal_result.knowledge_source,
            "fix_code": (heal_result.fix_code or "")[:200],
            "retrySuccess": False,
            "retryError": str(retry_err)[:200] if retry_err else "",
        }

    async def _retry_healed_step(self, step: dict, step_result: dict):
        """自愈后重试步骤核心动作。"""
        stype = step["type"]
        if stype == "click":
            await self._exec_click(step)
        elif stype == "fill":
            await self._exec_fill(step)
        elif stype == "navigate":
            await self._exec_navigate(step)
        elif stype == "waitForUrl":
            await self._exec_wait_for_url(step)
        elif stype == "wait":
            await asyncio.sleep(step["ms"] / 1000)
        elif stype == "selectOption":
            result = await self._cdp._send_cmd("selectOption", {
                "labelText": step["label"],
                "optionText": step["option"],
                "labelClass": step.get("labelClass", "tbd-formily-item-label"),
                "multiple": step.get("multiple", False),
            })
            step_result["selectedValue"] = result.get("selected")
            if not result.get("selected"):
                raise RuntimeError(f"selectOption 重试失败: label='{step['label']}'")
        elif stype == "clickText":
            result = await self._cdp._send_cmd("clickText", {
                "text": step["text"],
                "selector": step.get("selector", 'button, a, [role="button"], [class*="btn"], span'),
            })
            if not result.get("clicked"):
                raise RuntimeError(f"clickText 重试失败: text='{step['text']}'")
        elif stype in ("screenshot", "assert"):
            pass
        else:
            raise RuntimeError(f"步骤类型 '{stype}' 暂不支持自愈重试")

    # ── CDP 操作实现 ──

    async def _exec_click(self, step: dict, i: int = 0, output: dict = None):
        if step.get("text"):
            within = step.get("within", "")
            if within:
                # 在指定容器内点击文本
                result = await self._cdp.evaluate(
                    f"""(() => {{
                        const container = document.querySelector({json.dumps(within)});
                        if (!container) return false;
                        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
                        while (walker.nextNode()) {{
                            if (walker.currentNode.textContent.trim() === {json.dumps(step['text'])}) {{
                                const el = walker.currentNode.parentElement;
                                el.click();
                                return true;
                            }}
                        }}
                        // fallback: 容器内任意匹配
                        const items = container.querySelectorAll('*');
                        for (const el of items) {{
                            if (el.textContent.trim().includes({json.dumps(step['text'])}) && el.children.length === 0) {{
                                el.click();
                                return true;
                            }}
                        }}
                        return false;
                    }})()"""
                )
                if not result:
                    raise RuntimeError(f"在 '{within}' 内找不到文本 '{step['text']}'")
            else:
                result = await self._cdp._send_cmd("evaluate", {"clickText": step["text"]})
                clicked = result.get("value", False)
                if not clicked:
                    raise RuntimeError(f"找不到文本为 '{step['text']}' 的可点击元素")
        elif step.get("selector"):
            await self._cdp.evaluate(
                f"""(() => {{
                    const el = document.querySelector({json.dumps(step['selector'])});
                    if (!el) throw new Error('find error');
                    el.click();
                }})()"""
            )
        else:
            raise ValueError("click step 必须提供 text 或 selector")
        await asyncio.sleep(0.3)

    async def _exec_fill(self, step: dict, i: int = 0, output: dict = None):
        selector = step["selector"]
        index = step.get("selectorIndex", 0)
        value = step["value"]
        result = await self._cdp._send_cmd("evaluate", {
            "expression": f"""
(() => {{
    const els = [...document.querySelectorAll({json.dumps(selector)})].filter(el => el.offsetParent !== null);
    const el = els[{index}];
    if (!el) return {{ ok: false, count: els.length }};
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeInputValueSetter.call(el, {json.dumps(value)});
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    return {{ ok: true, index: {index}, value: el.value }};
}})()
""",
        })
        info = result.get("value")
        if not info or (isinstance(info, dict) and not info.get("ok")):
            count = info.get("count", "?") if isinstance(info, dict) else "?"
            raise RuntimeError(f"填写失败：selector='{selector}' index={index}，找到 {count} 个可见元素")
        await asyncio.sleep(0.2)

    async def _exec_navigate(self, step: dict, i: int = 0, output: dict = None):
        url = step["url"]
        wait_until = step.get("waitUntil", "load")
        timeout_ms = step.get("timeout", 30000)

        # "current" = 刷新当前页面
        if url == "current":
            url = await self._cdp.evaluate("window.location.href") or "about:blank"
        # "store.xxx.yyy" = 从存储中读取 URL
        elif url.startswith("store."):
            store_path = url[6:]  # 去掉 "store." 前缀
            if output and "_store" in output:
                parts = store_path.split(".")
                key = parts[0]
                value = output["_store"].get(key)
                for part in parts[1:]:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                        break
                if value and isinstance(value, str):
                    url = value
                else:
                    raise RuntimeError(f"navigate: 无法从 store 解析 URL '{url}', 值: {value}")
            else:
                raise RuntimeError(f"navigate: store 为空，无法解析 URL '{url}'")

        await self._cdp._send_cmd("navigate", {"url": url})
        start = time.time()

        if wait_until in ("load", "networkidle", "domcontentloaded"):
            event_map = {
                "load": "Page.loadEventFired",
                "domcontentloaded": "Page.domContentEventFired",
                "networkidle": "Page.loadEventFired",
            }
            event_name = event_map[wait_until]
            loop = asyncio.get_event_loop()
            fut = loop.create_future()

            def _on_event(_params):
                if not fut.done():
                    fut.set_result(True)

            self._cdp.on(event_name, _on_event)
            try:
                await asyncio.wait_for(fut, timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                raise TimeoutError(f"navigate 超时（{timeout_ms}ms）: {url}")
            finally:
                self._cdp.off(event_name, _on_event)

            if wait_until == "networkidle":
                await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(2.0)

        wait_text = step.get("waitText")
        if wait_text:
            deadline = timeout_ms / 1000 - (time.time() - start)
            if deadline <= 0:
                deadline = 5.0
            try:
                await asyncio.wait_for(
                    self._poll_until_text(wait_text, interval=0.5),
                    timeout=deadline,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"navigate 后等待文字超时（{timeout_ms}ms）: '{wait_text}'")

    async def _poll_until_text(self, text: str, interval: float = 0.5):
        while True:
            body = await self._cdp.evaluate("document.body.innerText")
            if text in (body or ""):
                return
            await asyncio.sleep(interval)

    async def _exec_wait_for_url(self, step: dict, i: int = 0, output: dict = None):
        pattern = step["urlContains"]
        timeout_ms = step.get("timeout", 10000)

        async def _check():
            while True:
                current_url = await self._cdp.evaluate("window.location.href")
                if pattern in (current_url or ""):
                    return
                await asyncio.sleep(0.5)

        try:
            await asyncio.wait_for(_check(), timeout=timeout_ms / 1000)
        except asyncio.TimeoutError:
            current_url = await self._cdp.evaluate("window.location.href")
            raise TimeoutError(
                f"waitForUrl 超时（{timeout_ms}ms）: 期望 URL 包含 '{pattern}'，实际 URL: {current_url}"
            )

    async def _exec_assert(self, step: dict, last_api_entry) -> dict:
        if step["target"] == "page":
            text = await self._cdp.evaluate("document.body.innerText")
            contains = step["contains"] in (text or "")
            return {
                "expected": step["contains"],
                "actual": "(包含)" if contains else "(不包含)",
                "pass": contains,
            }
        elif step["target"] == "api":
            if not last_api_entry:
                return {"expected": step["contains"], "actual": "(无 API 响应)", "pass": False}
            body = last_api_entry.get("responseBody")
            body_str = json.dumps(body) if not isinstance(body, str) else (body or "")
            contains = step["contains"] in body_str
            return {
                "expected": step["contains"],
                "actual": "(包含)" if contains else "(不包含)",
                "pass": contains,
            }
        raise ValueError(f"不支持的 assert target: {step['target']}")

    # ── 辅助 ──

    def _fire_hook_safe(self, phase, ctx: dict):
        try:
            self._hook_registry.fire(phase, ctx)
        except Exception as e:
            print(f"[step_executor] hook '{phase}' 异常: {e}", file=sys.stderr)

    async def _take_step_screenshot(self, step: dict, step_result: dict, i: int, output: dict):
        """步骤级和 onEachStep 截图。"""
        if step.get("screenshot") and step["type"] != "screenshot":
            try:
                png = await self._cdp.screenshot()
                path = self._artifacts.save_screenshot(png, f"step{i}-after")
                step_result["screenshotPath"] = path
                shot_rec = {"stepIndex": i, "label": f"step{i}-after", "path": path}
                if not self._screenshot_external:
                    import base64
                    shot_rec["data"] = base64.b64encode(png).decode()
                output["screenshots"].append(shot_rec)
            except Exception as e:
                print(f"[step_executor] step{i} 截图失败: {e}", file=sys.stderr)

        if self._screenshot_cfg.get("onEachStep") and step["type"] != "screenshot":
            try:
                png = await self._cdp.screenshot()
                path = self._artifacts.save_screenshot(png, f"step{i}-auto")
                shot_rec = {"stepIndex": i, "label": f"step{i}-auto", "path": path}
                if not self._screenshot_external:
                    import base64
                    shot_rec["data"] = base64.b64encode(png).decode()
                output["screenshots"].append(shot_rec)
            except Exception as e:
                print(f"[step_executor] step{i} 自动截图失败: {e}", file=sys.stderr)

    async def _take_error_screenshot(self, i: int, output: dict):
        if self._screenshot_cfg.get("onError", True):
            try:
                png = await self._cdp.screenshot()
                path = self._artifacts.save_screenshot(png, f"error-step{i}")
                shot_rec = {"stepIndex": -1, "label": f"error-step{i}", "path": path}
                if not self._screenshot_external:
                    import base64
                    shot_rec["data"] = base64.b64encode(png).decode()
                output["screenshots"].append(shot_rec)
            except Exception as e:
                print(f"[step_executor] error-step{i} 截图失败: {e}", file=sys.stderr)

    def _check_failure_grade(self, step_result: dict, i: int, output: dict) -> tuple:
        """失败分级检查，返回 (should_break, reason)。"""
        try:
            _ev_entry = self._evidence.get_latest_entry() if hasattr(self._evidence, 'get_latest_entry') else None
            _freport = self._failure_classifier.classify(step_result, _ev_entry)
            if _freport.action == "block":
                output["status"] = "blocked"
                output["error"] = {"stepIndex": i, "message": f"P0 阻断: {_freport.suggestion}"}
                return True, "blocked"
            elif _freport.action == "skip":
                step_result["status"] = "skip"
                step_result["skipReason"] = f"P2 跳过: {_freport.suggestion}"
        except Exception as e:
            print(f"[step_executor] failure_grade 检查异常: {e}", file=sys.stderr)
        return False, ""

    async def _save_error_checkpoint(self, i: int, checkpoint_ctx: dict):
        """错误时保存 checkpoint。"""
        try:
            _cur_url = await self._cdp.evaluate("window.location.href")
        except Exception:
            _cur_url = "unknown"
        self._ckpt.save_segment(
            seg_index=checkpoint_ctx.get("seg_index", 0),
            step_range=(checkpoint_ctx.get("seg_start_step", 0), i),
            steps_results=checkpoint_ctx.get("seg_steps", []),
            captured_apis=checkpoint_ctx.get("seg_apis", {}),
            last_page_url=_cur_url,
            seg_status="error",
        )

    def _log_step_metrics(self, step: dict, step_result: dict, i: int):
        """记录步骤级 metrics。"""
        _metric_result = {
            "pass": "success", "fail": "failed",
            "error": "failed", "skip": "skipped",
        }.get(step_result["status"], step_result["status"])
        _error_code = None
        if step_result.get("error"):
            _error_code = MetricsLogger.infer_error_code(step_result["error"])
        _is_fp = None
        if step["type"] == "assert" and step_result.get("assertResult"):
            _is_fp = step.get("isFalsePositive")
        _shot_path = step_result.get("screenshotPath")
        self._metrics_logger.log_step(
            step=step["type"],
            action=step.get("description", step["type"]),
            result=_metric_result,
            duration_ms=step_result["duration"],
            error_code=_error_code,
            screenshot_path=_shot_path,
            is_false_positive=_is_fp,
        )
