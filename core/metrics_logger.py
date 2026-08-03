"""
metrics_logger.py — 统一结构化度量日志

负责：
- 为每次执行生成符合统一 Schema 的结构化日志条目
- 提供 log_step() / log_llm_call() / log_error() 三个写入方法
- FINALIZE 时批量写入 artifacts/{run_id}/metrics.json
- 同时以 JSON-Lines 格式追加到全局 metrics.log（供 SLS 采集）

日志条目 Schema：
    {
      "task_id": "uuid",
      "business_type": "f88_material | original_protection | xiaoer | ...",
      "step": "navigate | click | fill | assert | llm_plan | screenshot | ...",
      "action": "具体操作描述",
      "result": "success | failed | retrying | skipped",
      "duration_ms": 1234,
      "token_used": 500,
      "confidence": 0.95,
      "error_code": "ELEMENT_NOT_FOUND | TIMEOUT | LLM_HALLUCINATION | ...",
      "screenshot_path": "/absolute/path/to/screenshot.jpg",
      "timestamp": "2026-06-29T22:25:00+08:00"
    }

使用方式：
    from core.metrics_logger import MetricsLogger
    logger = MetricsLogger(task_id="run-001", business_type="f88_material")
    logger.log_step("click", "点击搜索按钮", "success", 320)
    logger.log_llm_call("plan", "生成操作计划", 500, 0.92)
    logger.flush(run_dir, global_log_path)
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List

from core.log_level import LogLevel, passes_filter, get_min_level_from_env, validate_level


# ── 错误码常量 ──

class ErrorCode:
    """标准化错误码，与告警规则和 SLS 索引对齐"""
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    ASSERT_FAILED = "ASSERT_FAILED"
    LLM_HALLUCINATION = "LLM_HALLUCINATION"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"
    NETWORK_ERROR = "NETWORK_ERROR"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    SELECTOR_STALE = "SELECTOR_STALE"
    UNKNOWN = "UNKNOWN"

    # ── 环境限制类错误码（解决自动化阻塞原因分类）──
    FULLSCREEN_BLOCKED = "FULLSCREEN_BLOCKED"       # 全屏模式受限
    DRAG_NOT_SUPPORTED = "DRAG_NOT_SUPPORTED"       # 拖拽操作受限
    KEYBOARD_EVENT_FAILED = "KEYBOARD_EVENT_FAILED"  # 键盘事件未触发
    PLAY_OBSERVATION_LIMITED = "PLAY_OBSERVATION_LIMITED"  # 播放观察受限
    ZOOM_NOT_TRIGGERED = "ZOOM_NOT_TRIGGERED"       # 缩放操作未触发
    FOCUS_REQUIRED = "FOCUS_REQUIRED"               # 焦点状态缺失
    SHORTCUT_CONFLICT = "SHORTCUT_CONFLICT"          # 快捷键冲突
    PANEL_TRANSITION_FAILED = "PANEL_TRANSITION_FAILED"  # 面板交互受限
    EXCEPTION_SIM_FAILED = "EXCEPTION_SIM_FAILED"    # 异常模拟受限


# ── 日志条目 ──

@dataclass
class MetricLogEntry:
    """单条度量日志条目"""
    task_id: str
    business_type: str
    step: str
    action: str
    result: str                      # success | failed | retrying | skipped
    duration_ms: int
    level: str = "INFO"              # DEBUG | INFO | WARNING | ERROR
    token_used: Optional[int] = None
    confidence: Optional[float] = None
    error_code: Optional[str] = None
    screenshot_path: Optional[str] = None
    is_false_positive: Optional[bool] = None   # assert 步骤专用：是否为误报
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """转换为 dict，过滤 None 值以保持日志整洁"""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


# ── 日志器 ──

class MetricsLogger:
    """
    度量日志收集器。
    每次执行实例化一次，在执行过程中通过 log_step/log_llm_call/log_error 记录日志，
    FINALIZE 阶段调用 flush() 持久化。
    """

    def __init__(self, task_id: str, business_type: str = "unknown", min_level: Optional[str] = None):
        self.task_id = task_id
        self.business_type = business_type
        self.min_level = validate_level(min_level) if min_level else get_min_level_from_env()
        self._entries: List[MetricLogEntry] = []

    @property
    def entries(self) -> List[MetricLogEntry]:
        return list(self._entries)

    # ── 写入方法 ──

    def log_step(
        self,
        step: str,
        action: str,
        result: str,
        duration_ms: int,
        error_code: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        is_false_positive: Optional[bool] = None,
    ) -> MetricLogEntry:
        """
        记录一个操作步骤的度量日志。

        Args:
            step: 步骤类型（navigate/click/fill/assert/screenshot/wait 等）
            action: 具体操作描述
            result: success | failed | retrying | skipped
            duration_ms: 步骤耗时（毫秒）
            error_code: 错误码（失败时填写）
            screenshot_path: 截图路径（如有）
            is_false_positive: assert 步骤专用，标记是否为误报
        """
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result=result,
            duration_ms=duration_ms,
            level=LogLevel.INFO,
            error_code=error_code,
            screenshot_path=screenshot_path,
            is_false_positive=is_false_positive,
        )
        self._entries.append(entry)
        return entry

    def log_llm_call(
        self,
        step: str,
        action: str,
        token_used: int,
        confidence: float,
        result: str = "success",
        duration_ms: int = 0,
        error_code: Optional[str] = None,
    ) -> MetricLogEntry:
        """
        记录一次 LLM 调用的度量日志。

        Args:
            step: LLM 操作类型（llm_plan/llm_assert/llm_heal 等）
            action: 具体操作描述
            token_used: Token 消耗数
            confidence: LLM 决策置信度（0.0 ~ 1.0）
            result: success | failed | retrying
            duration_ms: 调用耗时（毫秒）
            error_code: 错误码（失败时填写，如 LLM_HALLUCINATION / LLM_TIMEOUT）
        """
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result=result,
            duration_ms=duration_ms,
            level=LogLevel.INFO,
            token_used=token_used,
            confidence=confidence,
            error_code=error_code,
        )
        self._entries.append(entry)
        return entry

    def log_error(
        self,
        step: str,
        action: str,
        error_code: str,
        duration_ms: int = 0,
        screenshot_path: Optional[str] = None,
    ) -> MetricLogEntry:
        """
        记录一个错误事件。

        Args:
            step: 步骤类型
            action: 具体操作描述
            error_code: 错误码（使用 ErrorCode 常量）
            duration_ms: 步骤耗时
            screenshot_path: 错误截图路径
        """
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result="failed",
            duration_ms=duration_ms,
            level=LogLevel.ERROR,
            error_code=error_code,
            screenshot_path=screenshot_path,
        )
        self._entries.append(entry)
        return entry

    # ── 分级写入方法 ──

    def log_debug(
        self,
        step: str,
        action: str,
        result: str = "success",
        duration_ms: int = 0,
        **kwargs,
    ) -> MetricLogEntry:
        """记录 DEBUG 级别日志（详细调试信息，默认不写入全局日志）"""
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result=result,
            duration_ms=duration_ms,
            level=LogLevel.DEBUG,
            **kwargs,
        )
        self._entries.append(entry)
        return entry

    def log_info(
        self,
        step: str,
        action: str,
        result: str = "success",
        duration_ms: int = 0,
        **kwargs,
    ) -> MetricLogEntry:
        """记录 INFO 级别日志（常规操作记录）"""
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result=result,
            duration_ms=duration_ms,
            level=LogLevel.INFO,
            **kwargs,
        )
        self._entries.append(entry)
        return entry

    def log_warning(
        self,
        step: str,
        action: str,
        result: str = "failed",
        duration_ms: int = 0,
        error_code: Optional[str] = None,
        **kwargs,
    ) -> MetricLogEntry:
        """记录 WARNING 级别日志（可恢复异常、降级操作）"""
        entry = MetricLogEntry(
            task_id=self.task_id,
            business_type=self.business_type,
            step=step,
            action=action,
            result=result,
            duration_ms=duration_ms,
            level=LogLevel.WARNING,
            error_code=error_code,
            **kwargs,
        )
        self._entries.append(entry)
        return entry

    # ── 持久化 ──

    def flush(self, run_dir: str, global_log_path: str = None) -> str:
        """
        将日志条目持久化到文件。

        1. 写入 {run_dir}/metrics.json（完整 JSON 数组）
        2. 追加到 global_log_path（JSON-Lines，供 SLS 采集）

        Args:
            run_dir: 本次执行的产物目录
            global_log_path: 全局滚动日志路径（默认 artifacts/metrics.log）

        Returns:
            metrics.json 的文件路径
        """
        # 1. 写入 run_dir/metrics.json（全量，含 DEBUG）
        entries_dicts = [e.to_dict() for e in self._entries]
        metrics_path = os.path.join(run_dir, "metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(entries_dicts, f, ensure_ascii=False, indent=2)

        # 2. 追加到全局 JSON-Lines 日志（按 min_level 过滤，DEBUG 默认不写入）
        if global_log_path is None:
            global_log_path = os.path.join(os.path.dirname(run_dir), "metrics.log")

        filtered_entries = [
            d for d in entries_dicts
            if passes_filter(d.get("level", LogLevel.INFO), self.min_level)
        ]

        os.makedirs(os.path.dirname(global_log_path), exist_ok=True)
        with open(global_log_path, "a", encoding="utf-8") as f:
            for entry_dict in filtered_entries:
                f.write(json.dumps(entry_dict, ensure_ascii=False) + "\n")

        return metrics_path

    # ── 查询接口 ──

    def get_entries_by_step(self, step: str) -> List[MetricLogEntry]:
        """获取特定步骤类型的所有日志"""
        return [e for e in self._entries if e.step == step]

    def get_entries_by_result(self, result: str) -> List[MetricLogEntry]:
        """获取特定结果状态的所有日志"""
        return [e for e in self._entries if e.result == result]

    def get_failed_entries(self) -> List[MetricLogEntry]:
        """获取所有失败的日志"""
        return self.get_entries_by_result("failed")

    def get_llm_entries(self) -> List[MetricLogEntry]:
        """获取所有 LLM 调用日志"""
        return [e for e in self._entries if e.token_used is not None]

    def get_total_duration_ms(self) -> int:
        """获取所有日志的总耗时"""
        return sum(e.duration_ms for e in self._entries)

    def get_total_token_used(self) -> int:
        """获取所有 LLM 调用的总 Token 消耗"""
        return sum(e.token_used for e in self._entries if e.token_used is not None)

    @staticmethod
    def infer_error_code(error_msg: str) -> str:
        """从错误消息中推断标准错误码"""
        if not error_msg:
            return ErrorCode.UNKNOWN

        msg_lower = error_msg.lower()

        # 超时类
        if "timeout" in msg_lower or "超时" in error_msg:
            return ErrorCode.TIMEOUT

        # 元素找不到
        if any(kw in error_msg for kw in [
            "find error", "找不到", "未找到", "not found",
            "querySelector", "offsetParent", "no element",
        ]):
            return ErrorCode.ELEMENT_NOT_FOUND

        # 导航错误
        if any(kw in msg_lower for kw in ["navigate", "navigation", "net::err"]):
            return ErrorCode.NAVIGATION_ERROR

        # 断言失败
        if "assert" in msg_lower or "不包含" in error_msg:
            return ErrorCode.ASSERT_FAILED

        # 登录
        if "login" in msg_lower or "登录" in error_msg:
            return ErrorCode.LOGIN_REQUIRED

        # Selector 失效
        if "stale" in msg_lower:
            return ErrorCode.SELECTOR_STALE

        # 网络错误
        if any(kw in msg_lower for kw in ["econnrefused", "network", "fetch"]):
            return ErrorCode.NETWORK_ERROR

        # 合规拦截
        if "compliance" in msg_lower or "合规" in error_msg or "拦截" in error_msg:
            return ErrorCode.COMPLIANCE_BLOCKED

        # 环境限制类（自动化阻塞原因自动分类）
        if any(kw in msg_lower for kw in ["fullscreen", "全屏", "requestfullscreen"]):
            return ErrorCode.FULLSCREEN_BLOCKED
        if any(kw in error_msg for kw in ["拖拽", "drag", "trim", "handle"]):
            return ErrorCode.DRAG_NOT_SUPPORTED
        if any(kw in msg_lower for kw in ["keyevent", "space键", "keyboard", "键盘事件", "dispatchkeyevent"]):
            return ErrorCode.KEYBOARD_EVENT_FAILED
        if any(kw in msg_lower for kw in ["播放头", "playhead", "screencast", "播放观察"]):
            return ErrorCode.PLAY_OBSERVATION_LIMITED
        if any(kw in error_msg for kw in ["缩放", "zoom", "放大"]):
            return ErrorCode.ZOOM_NOT_TRIGGERED
        if any(kw in error_msg for kw in ["焦点", "focus", "setFocus", "快捷键"]):
            return ErrorCode.FOCUS_REQUIRED
        if any(kw in msg_lower for kw in ["shortcut", "ctrl+z", "快捷键冲突", "快捷键被拦截"]):
            return ErrorCode.SHORTCUT_CONFLICT
        if any(kw in msg_lower for kw in ["panel", "面板", "loading遮罩", "transition", "过渡"]):
            return ErrorCode.PANEL_TRANSITION_FAILED
        if any(kw in msg_lower for kw in ["mock", "断网", "模拟", "故障注入"]):
            return ErrorCode.EXCEPTION_SIM_FAILED

        return ErrorCode.UNKNOWN
