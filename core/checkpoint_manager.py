"""
checkpoint_manager.py — 断点续跑管理器

职责：
- 每段执行完成后写 checkpoints/seg-{N}.json
- 维护 checkpoints/state.json（全局进度状态）
- 提供续跑时的状态恢复接口
- 判断当前段是否需要触发分段（步数 or 体积超限）

目录结构：
    artifacts/{run_id}/
    └── checkpoints/
        ├── state.json          ← 全局状态，续跑时读这个
        ├── seg-000.json        ← 第 0 段结果
        ├── seg-001.json        ← 第 1 段结果
        └── ...
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

class CheckpointManager:
    """
    在 impl.py 中每个 segment 执行后调用，负责持久化断点状态。

    使用方式：
        cm = CheckpointManager(run_id, artifacts_dir, segment_size=8)

        # 续跑时恢复状态
        state = cm.load_state()
        start_step = state["lastCompletedStep"] + 1

        # 每步执行后判断是否需要分段
        if cm.should_checkpoint(step_result, output_size_kb):
            cm.save_segment(seg_id, seg_steps, captured_apis, last_page_url)
    """

    def __init__(
        self,
        run_id: str,
        run_dir: str,
        total_steps: int,
        segment_size: int = 8,
        output_size_limit_kb: int = 200,
    ):
        self.run_id = run_id
        self.run_dir = run_dir
        self.total_steps = total_steps
        self.segment_size = segment_size
        self.output_size_limit_kb = output_size_limit_kb

        self.checkpoint_dir = os.path.join(run_dir, "checkpoints")
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        # 当前段内部计数器
        self._seg_step_count = 0
        self._seg_output_kb = 0.0
        self._current_seg_index = 0

    # ─────────────────────────────────────────
    # 触发判断
    # ─────────────────────────────────────────

    def track_step(self, step_result: dict, screenshot_paths: list[str] = None) -> bool:
        """
        记录一步的输出体积，返回是否应该触发分段保存。

        触发条件（满足其一）：
          1. 当前段内步数 >= segment_size
          2. 当前段累积输出体积 >= output_size_limit_kb
        """
        self._seg_step_count += 1

        # 估算体积：step_result JSON + 截图文件大小
        kb = len(json.dumps(step_result, ensure_ascii=False)) / 1024
        for p in (screenshot_paths or []):
            try:
                kb += os.path.getsize(p) / 1024
            except OSError:
                pass
        self._seg_output_kb += kb

        should = (
            self._seg_step_count >= self.segment_size
            or self._seg_output_kb >= self.output_size_limit_kb
        )
        return should

    def reset_seg_counter(self):
        """保存完一段后调用，重置段内计数器。"""
        self._seg_step_count = 0
        self._seg_output_kb = 0.0
        self._current_seg_index += 1

    # ─────────────────────────────────────────
    # 保存 & 加载
    # ─────────────────────────────────────────

    def save_segment(
        self,
        seg_index: int,
        step_range: tuple[int, int],      # (start_step, end_step) inclusive
        steps_results: list[dict],
        captured_apis: dict,               # urlKeyword -> last responseBody
        last_page_url: str,
        seg_status: str = "pass",          # pass | fail | error
    ) -> str:
        """
        将一段执行结果持久化到 checkpoints/seg-{N:03d}.json。
        同时更新 state.json。
        返回 seg 文件路径。
        """
        seg_id = f"seg-{seg_index:03d}"
        seg_path = os.path.join(self.checkpoint_dir, f"{seg_id}.json")

        seg_data = {
            "segId": seg_id,
            "segIndex": seg_index,
            "stepRange": list(step_range),
            "status": seg_status,
            "stepsResults": steps_results,
            "capturedApis": captured_apis,
            "lastPageUrl": last_page_url,
            "completedAt": _now_iso(),
        }
        _write_json(seg_path, seg_data)

        # 更新全局 state
        self._update_state(
            seg_index=seg_index,
            seg_id=seg_id,
            step_range=step_range,
            seg_status=seg_status,
            captured_apis=captured_apis,
            last_page_url=last_page_url,
        )

        return seg_path

    def save_final_state(self, overall_status: str):
        """整个用例执行完毕后调用，更新 state.json 的顶层 status。"""
        state = self.load_state() or {}
        state["status"] = overall_status
        state["finishedAt"] = _now_iso()
        _write_json(self._state_path(), state)

    def load_state(self) -> Optional[dict]:
        """加载 state.json，不存在返回 None。"""
        path = self._state_path()
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def load_segment(self, seg_index: int) -> Optional[dict]:
        """加载某段结果，不存在返回 None。"""
        path = os.path.join(self.checkpoint_dir, f"seg-{seg_index:03d}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # ─────────────────────────────────────────
    # 续跑辅助
    # ─────────────────────────────────────────

    def get_resume_context(self) -> dict:
        """
        续跑前调用，返回恢复所需的上下文。

        返回：
            {
              "nextStepIndex": 8,           # 从哪步开始
              "completedSegments": [...],   # 已完成段信息
              "capturedApis": {...},        # 前段所有抓包（合并）
              "lastPageUrl": "https://...", # 当前浏览器应在的页面
              "currentSegIndex": 1,         # 下一段序号
            }
        """
        state = self.load_state()
        if not state:
            return {
                "nextStepIndex": 0,
                "completedSegments": [],
                "capturedApis": {},
                "lastPageUrl": None,
                "currentSegIndex": 0,
            }

        # 合并所有段的 capturedApis（后段覆盖前段，保留最新）
        merged_apis = {}
        for seg_info in state.get("segments", []):
            if seg_info.get("status") == "pass":
                seg_data = self.load_segment(seg_info["segIndex"])
                if seg_data:
                    merged_apis.update(seg_data.get("capturedApis", {}))

        last_completed = state.get("lastCompletedStep", -1)
        completed_segs = state.get("segments", [])
        current_seg_index = len([s for s in completed_segs if s["status"] == "pass"])

        return {
            "nextStepIndex": last_completed + 1,
            "completedSegments": completed_segs,
            "capturedApis": merged_apis,
            "lastPageUrl": state.get("lastPageUrl"),
            "currentSegIndex": current_seg_index,
        }

    # ─────────────────────────────────────────
    # 内部工具
    # ─────────────────────────────────────────

    def _state_path(self) -> str:
        return os.path.join(self.checkpoint_dir, "state.json")

    def _update_state(
        self,
        seg_index: int,
        seg_id: str,
        step_range: tuple,
        seg_status: str,
        captured_apis: dict,
        last_page_url: str,
    ):
        state = self.load_state() or {
            "runId": self.run_id,
            "totalSteps": self.total_steps,
            "segments": [],
            "lastCompletedStep": -1,
            "lastPageUrl": None,
            "capturedApis": {},
            "status": "running",
            "startedAt": _now_iso(),
        }

        # 追加或更新段信息
        existing = next(
            (s for s in state["segments"] if s["segIndex"] == seg_index), None
        )
        seg_entry = {
            "segIndex": seg_index,
            "segId": seg_id,
            "stepRange": list(step_range),
            "status": seg_status,
            "completedAt": _now_iso(),
        }
        if existing:
            idx = state["segments"].index(existing)
            state["segments"][idx] = seg_entry
        else:
            state["segments"].append(seg_entry)

        # 更新顶层字段
        if seg_status == "pass":
            state["lastCompletedStep"] = step_range[1]
        state["lastPageUrl"] = last_page_url

        # 合并 capturedApis（新段覆盖旧段）
        state.setdefault("capturedApis", {}).update(captured_apis)

        # 推断整体状态
        completed = sum(1 for s in state["segments"] if s["status"] == "pass")
        if state["lastCompletedStep"] >= self.total_steps - 1:
            state["status"] = "done"
        elif seg_status in ("fail", "error"):
            state["status"] = seg_status
        else:
            state["status"] = "running"

        _write_json(self._state_path(), state)

# ─────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _write_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
