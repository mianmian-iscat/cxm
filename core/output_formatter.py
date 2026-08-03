"""
output_formatter.py — 输出格式化与初始化

从 impl.py 抽取的输出相关函数：
- init_output(): 初始化 output 字典结构
- print_verbose(): 根据 verbose_mode 格式化输出摘要

使用方式:
    from core.output_formatter import init_output, print_verbose
    output = init_output(input_data, run_id)
    print_verbose(output, "summary")
"""

from datetime import datetime, timezone


def init_output(input_data: dict, run_id: str) -> dict:
    """创建符合 output.schema.json 的初始输出结构。"""
    return {
        "id": input_data["id"],
        "name": input_data["name"],
        "status": "pass",
        "startTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration": 0,
        "steps": [],
        "screenshots": [],
        "capture": {"requests": []},
        "artifacts": {"runId": run_id},
    }


def print_verbose(output: dict, verbose_mode: str):
    """根据 verbose_mode 输出执行摘要到 stdout。

    Modes:
        full:    不输出（由调用方直接 print JSON）
        minimal: 仅输出一行状态
        summary: 输出结构化执行摘要
    """
    status = output.get("status", "unknown")
    icon = "✅" if status == "pass" else ("⏳" if status == "checkpoint_saved" else "❌")

    if verbose_mode == "full":
        return

    if verbose_mode == "minimal":
        print(f"{icon} {output.get('id', '')} {status}")
        return

    # summary 模式
    steps = output.get("steps", [])
    passed = sum(1 for s in steps if s.get("status") == "pass")
    total = len(steps)
    shots = output.get("screenshots", [])
    reqs = output.get("capture", {}).get("requests", [])
    run_dir = output.get("artifacts", {}).get("runDir", "")
    duration_ms = output.get("duration", 0)

    lines = [
        f"{icon} 测试用例 {'通过' if status == 'pass' else status}",
        "",
        "📊 执行摘要",
        f"  用例：{output.get('id', '')}",
        f"  时长：{duration_ms / 1000:.1f}s",
        f"  步骤：{passed}/{total} 通过",
    ]

    if output.get("error"):
        err = output["error"]
        lines.append(f"  ❌ 错误：[step {err.get('stepIndex', '?')}] {err.get('message', '')}")

    if shots:
        lines.append(f"\n📸 截图：{len(shots)} 张")
        if run_dir:
            lines.append(f"   见：{run_dir}/screenshots/")

    if reqs:
        cap_summary = output.get("capture", {}).get("summary", {})
        total_reqs = cap_summary.get("totalRequests", len(reqs))
        lines.append(f"\n📡 抓包：{total_reqs} 个请求")
        if run_dir:
            lines.append(f"   见：{run_dir}/capture.json")

    if output.get("status") == "checkpoint_saved":
        ckpt_info = output.get("checkpoint", {})
        lines.append(f"\n⏳ Checkpoint 已保存")
        lines.append(f"   已完成：{ckpt_info.get('completedSteps', '?')}/{ckpt_info.get('totalSteps', '?')} 步")
        lines.append(f"   续跑：python impl.py input.json --resume {ckpt_info.get('runId', '')}")

    if run_dir:
        lines.append(f"\n📁 完整产物：{run_dir}/")

    print("\n".join(lines))
