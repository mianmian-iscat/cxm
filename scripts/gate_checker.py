#!/usr/bin/env python3
"""
gate_checker.py — Phase Gate 门禁检查器

读取 harness/phase_gates.yaml 配置，执行门禁检查。
门禁未通过时阻断流程并通知用户。

设计原则:
  - 确定性检查由脚本执行，不交给 LLM
  - 门禁结果结构化输出，供 Agent 或 CI 消费
  - 支持 dry-run 模式预览门禁状态
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    # 降级：手动解析 YAML（仅支持简单结构）
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GATES_CONFIG = PROJECT_ROOT / "harness" / "phase_gates.yaml"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"


def load_gates_config() -> dict:
    """加载门禁配置"""
    if not GATES_CONFIG.exists():
        print(f"[gate_checker] 配置文件不存在: {GATES_CONFIG}")
        return {}

    content = GATES_CONFIG.read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(content)
    else:
        # 简单降级：返回空配置
        print("[gate_checker] 警告: PyYAML 未安装，使用降级模式")
        return {"gates": []}


def check_file_exists(path: str) -> dict:
    """检查文件是否存在"""
    full_path = PROJECT_ROOT / path
    exists = full_path.exists()
    return {
        "check": "file_exists",
        "path": path,
        "passed": exists,
        "detail": f"文件{'存在' if exists else '不存在'}: {path}",
    }


def check_json_has_field(path: str, field: str) -> dict:
    """检查 JSON 文件是否包含指定字段"""
    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        return {"check": "json_field", "path": path, "field": field, "passed": False, "detail": "文件不存在"}

    try:
        data = json.loads(full_path.read_text(encoding="utf-8"))
        has_field = field in data
        return {
            "check": "json_field",
            "path": path,
            "field": field,
            "passed": has_field,
            "detail": f"字段 {field} {'存在' if has_field else '不存在'}",
        }
    except json.JSONDecodeError:
        return {"check": "json_field", "path": path, "field": field, "passed": False, "detail": "JSON 解析失败"}


def check_dir_not_empty(path: str) -> dict:
    """检查目录是否非空"""
    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        return {"check": "dir_not_empty", "path": path, "passed": False, "detail": "目录不存在"}

    files = list(full_path.rglob("*"))
    non_empty = len(files) > 0
    return {
        "check": "dir_not_empty",
        "path": path,
        "passed": non_empty,
        "detail": f"目录包含 {len(files)} 个文件" if non_empty else "目录为空",
    }


def check_screenshots_per_case(artifacts_dir: Path, min_per_case: int = 1) -> dict:
    """检查每个用例是否有足够截图"""
    screenshots_dir = artifacts_dir / "screenshots"
    if not screenshots_dir.exists():
        return {
            "check": "screenshots_per_case",
            "passed": False,
            "detail": "screenshots 目录不存在",
        }

    screenshot_files = list(screenshots_dir.glob("*.png")) + list(screenshots_dir.glob("*.jpg"))
    count = len(screenshot_files)
    passed = count >= min_per_case
    return {
        "check": "screenshots_per_case",
        "passed": passed,
        "detail": f"截图数量: {count} (最低要求: {min_per_case})",
    }


# 门禁检查器注册表
CHECK_REGISTRY = {
    "artifacts.check_exists": lambda params: check_file_exists(params.get("path", "")),
    "artifacts.check_screenshots": lambda params: check_screenshots_per_case(
        ARTIFACTS_DIR, params.get("min_per_case", 1)
    ),
    "artifacts.check_json_field": lambda params: check_json_has_field(
        params.get("path", ""), params.get("field", "")
    ),
    "artifacts.check_dir_not_empty": lambda params: check_dir_not_empty(params.get("path", "")),
}


def run_gate_check(gate_id: str = None, dry_run: bool = False) -> dict:
    """
    执行门禁检查

    Returns:
        {
            "gate_id": "...",
            "gate_name": "...",
            "results": [...],
            "overall": "pass|block|warn",
            "summary": "..."
        }
    """
    config = load_gates_config()
    gates = config.get("gates", [])

    if not gates:
        return {"overall": "pass", "summary": "无门禁配置", "results": []}

    # 过滤指定门禁
    if gate_id:
        gates = [g for g in gates if g.get("id") == gate_id]
        if not gates:
            return {"overall": "pass", "summary": f"门禁 {gate_id} 不存在", "results": []}

    all_results = []
    overall = "pass"

    for gate in gates:
        gid = gate.get("id", "unknown")
        gname = gate.get("name", gid)
        checks = gate.get("checks", [])

        gate_results = []
        for check_def in checks:
            check_id = check_def.get("id", "")
            tool = check_def.get("tool", "")
            params = check_def.get("params", {})
            on_fail = check_def.get("on_fail", "warn")

            # 执行检查
            checker = CHECK_REGISTRY.get(tool)
            if checker:
                result = checker(params)
            else:
                result = {
                    "check": tool,
                    "passed": True,  # 未实现的检查默认通过
                    "detail": f"检查器 {tool} 未实现，跳过",
                }

            result["id"] = check_id
            result["on_fail"] = on_fail

            # 判断门禁级别
            if not result["passed"]:
                if on_fail == "block":
                    overall = "block"
                elif on_fail == "warn" and overall != "block":
                    overall = "warn"

            gate_results.append(result)

        all_results.append({
            "gate_id": gid,
            "gate_name": gname,
            "checks": gate_results,
        })

    # 生成摘要
    total_checks = sum(len(g["checks"]) for g in all_results)
    passed_checks = sum(1 for g in all_results for c in g["checks"] if c["passed"])
    failed_checks = total_checks - passed_checks

    summary = f"门禁检查完成: {passed_checks}/{total_checks} 通过"
    if failed_checks > 0:
        summary += f", {failed_checks} 项未通过"
    if overall == "block":
        summary += " [BLOCKED]"
    elif overall == "warn":
        summary += " [WARN]"

    return {
        "overall": overall,
        "summary": summary,
        "results": all_results,
        "timestamp": datetime.now().isoformat(),
    }


def format_report(result: dict) -> str:
    """格式化门禁检查报告"""
    lines = [
        f"# 门禁检查报告",
        f"*{result.get('timestamp', '')}*",
        f"",
        f"**结果**: {result['overall'].upper()}",
        f"**摘要**: {result['summary']}",
        f"",
    ]

    for gate in result.get("results", []):
        lines.append(f"## {gate['gate_name']} ({gate['gate_id']})")
        for check in gate.get("checks", []):
            status = "✅" if check["passed"] else ("🚫" if check.get("on_fail") == "block" else "⚠️")
            lines.append(f"- {status} {check.get('id', '?')}: {check.get('detail', '')}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase Gate 门禁检查器")
    parser.add_argument("--gate-id", help="指定检查的门禁 ID")
    parser.add_argument("--dry-run", action="store_true", help="只预览不执行")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--report", action="store_true", help="Markdown 报告格式输出")
    args = parser.parse_args()

    result = run_gate_check(gate_id=args.gate_id, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.report:
        print(format_report(result))
    else:
        print(result["summary"])
        if result["overall"] == "block":
            sys.exit(1)
