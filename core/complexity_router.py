"""
complexity_router.py — 复杂度路由器 (Gap 2.2)

主Agent控制面子系统。职责：
- 在执行入口判断任务复杂度（SIMPLE / MEDIUM / COMPLEX）
- 返回建议执行模式（direct / pipeline / multi_agent）
- 提供并行执行提示

使用方式：
    from core.complexity_router import ComplexityRouter, ComplexityLevel
    router = ComplexityRouter()
    result = router.route(input_data)
    # result = {level: "MEDIUM", suggested_mode: "pipeline", parallel_hint: True}
"""

from enum import Enum

class ComplexityLevel(Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"

class ComplexityRouter:
    """
    复杂度路由器：根据 input_data 特征判断任务复杂度。
    """

    def route(self, input_data: dict) -> dict:
        """
        判断复杂度并返回路由建议。

        判断规则：
        - SIMPLE:  steps <= 10 且无 pipeline 且无 LLM
        - MEDIUM:  steps <= 30 或有 pipeline 或有 realtime_asserts
        - COMPLEX: steps > 30 或 (pipeline + LLM + multi-page)

        Returns:
            {level, suggested_mode, parallel_hint, reason}
        """
        steps = input_data.get("steps", [])
        has_pipeline = "pipeline" in input_data
        has_llm = bool(input_data.get("llm", {}).get("calls"))
        step_count = len(steps)

        # 检查是否有 realtime_asserts
        has_realtime_asserts = any(
            step.get("realtime_asserts") for step in steps
        )

        # 检查是否多页面（多个 navigate 步骤）
        navigate_count = sum(1 for s in steps if s.get("type") == "navigate")
        is_multi_page = navigate_count >= 2

        # 判断复杂度
        if step_count > 30 or (has_pipeline and has_llm and is_multi_page):
            level = ComplexityLevel.COMPLEX
            mode = "multi_agent"
            parallel = True
            reason = f"steps={step_count}, pipeline={has_pipeline}, llm={has_llm}, multi_page={is_multi_page}"

        elif step_count > 10 or has_pipeline or has_realtime_asserts:
            level = ComplexityLevel.MEDIUM
            mode = "pipeline" if has_pipeline else "direct"
            parallel = has_pipeline and step_count > 15
            reason = f"steps={step_count}, pipeline={has_pipeline}, realtime_asserts={has_realtime_asserts}"

        else:
            level = ComplexityLevel.SIMPLE
            mode = "direct"
            parallel = False
            reason = f"steps={step_count}, 无 pipeline/LLM"

        return {
            "level": level.value,
            "suggested_mode": mode,
            "parallel_hint": parallel,
            "reason": reason,
            "step_count": step_count,
            "has_pipeline": has_pipeline,
            "has_llm": has_llm,
            "is_multi_page": is_multi_page,
        }
