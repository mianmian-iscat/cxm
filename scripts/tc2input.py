#!/usr/bin/env python3
"""
tc2input.py - 将 optimize-test-case 输出的 YAML 元数据转换为 web-automation 的 input.json

用法：
    python scripts/tc2input.py --yaml design.yaml --tc-id TC-XXX-001 --out input.json
    python scripts/tc2input.py --yaml design.yaml --all --outdir ./examples/

转换规则：
    YAML test_cases[].steps[].action → input.json steps[].type
    navigate → navigate (url from step or page.url)
    click    → click (text preferred, fallback to selector)
    fill     → fill (selector + value, react=true)
    assert   → assert (target="page", contains=expected text)
    observe  → screenshot (label from target)
    wait     → wait (ms from step or default 2000)
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 支持从 Markdown 文件中提取 YAML 块
    yaml_match = re.search(
        r"```yaml\s*\n(# --- (?:optimize-test-case|测试设计) 结构化[^\n]*\n.*?)```",
        content,
        re.DOTALL,
    )
    if yaml_match:
        yaml_str = yaml_match.group(1)
    else:
        yaml_str = content

    return yaml.safe_load(yaml_str)


def tc_id_to_kebab(tc_id: str) -> str:
    return tc_id.lower().replace("_", "-")


def convert_step(step: dict, tc: dict) -> dict:
    action = step.get("action", "")
    target = step.get("target", "")

    if action == "navigate":
        url = step.get("url", "")
        if not url:
            url = tc.get("page", {}).get("url", "")
        result = {"type": "navigate", "url": url}
        if step.get("waitText"):
            result["waitText"] = step["waitText"]
        return result

    elif action == "click":
        result = {"type": "click"}
        if step.get("text"):
            result["text"] = step["text"]
        elif step.get("selector"):
            result["selector"] = step["selector"]
        else:
            result["text"] = target
        if step.get("description"):
            result["description"] = step["description"]
        return result

    elif action == "fill":
        result = {
            "type": "fill",
            "selector": step.get("selector", f'input[placeholder*="{target}"]'),
            "value": step.get("value", ""),
            "react": step.get("react", True),
        }
        if step.get("selectorIndex") is not None:
            result["selectorIndex"] = step["selectorIndex"]
        if step.get("description"):
            result["description"] = step["description"]
        return result

    elif action == "assert":
        result = {
            "type": "assert",
            "target": step.get("assertTarget", "page"),
            "contains": step.get("contains", target),
        }
        if step.get("urlPattern"):
            result["urlPattern"] = step["urlPattern"]
        if step.get("path"):
            result["path"] = step["path"]
        return result

    elif action == "observe":
        return {
            "type": "screenshot",
            "label": target or "observe",
        }

    elif action == "wait":
        return {
            "type": "wait",
            "ms": step.get("ms", 2000),
        }

    elif action == "waitForAPI":
        result = {
            "type": "waitForAPI",
            "urlPattern": step.get("urlPattern", target),
        }
        if step.get("timeout"):
            result["timeout"] = step["timeout"]
        return result

    elif action == "waitForUrl":
        return {
            "type": "waitForUrl",
            "urlContains": step.get("urlContains", target),
        }

    else:
        return {
            "type": "screenshot",
            "label": f"unknown-action-{action}",
            "description": f"未识别的动作: {action} → {target}",
        }


def convert_tc(tc: dict) -> dict:
    tc_id = tc.get("tc_id", "unknown")
    page = tc.get("page", {})

    input_json = {
        "id": tc_id_to_kebab(tc_id),
        "name": tc.get("title", tc_id),
        "context": {},
        "steps": [],
    }

    # context
    if page.get("url"):
        input_json["context"]["url"] = page["url"]
    if page.get("url_pattern"):
        input_json["context"]["urlPattern"] = page["url_pattern"]

    # preconditions → cookies
    preconditions = tc.get("preconditions", {})
    if preconditions.get("cookies_url"):
        input_json["context"]["cookiesUrl"] = preconditions["cookies_url"]

    # steps
    steps = tc.get("steps", [])
    for step in steps:
        converted = convert_step(step, tc)
        if converted:
            input_json["steps"].append(converted)

    # expected_results → append assert steps
    for expected in tc.get("expected_results", []):
        if expected:
            input_json["steps"].append({
                "type": "assert",
                "target": "page",
                "contains": expected,
            })

    # capture from api_patterns
    api_patterns = tc.get("api_patterns", [])
    if api_patterns:
        input_json["capture"] = {
            "enabled": True,
            "filter": api_patterns[0],
        }

    # screenshot config
    input_json["screenshot"] = {
        "onEachStep": False,
        "onError": True,
    }

    return input_json


def main():
    parser = argparse.ArgumentParser(
        description="将 optimize-test-case YAML 元数据转换为 web-automation input.json"
    )
    parser.add_argument(
        "--yaml", required=True, help="YAML 文件路径（支持 .yaml 或含 YAML 块的 .md）"
    )
    parser.add_argument("--tc-id", help="指定转换单条用例的 TC-ID")
    parser.add_argument("--all", action="store_true", help="转换所有用例")
    parser.add_argument("--out", help="输出文件路径（单条用例时使用）")
    parser.add_argument("--outdir", help="输出目录（--all 时使用）")

    args = parser.parse_args()

    data = load_yaml(args.yaml)
    test_cases = data.get("test_cases", [])

    if not test_cases:
        print("错误：未找到 test_cases 数据", file=sys.stderr)
        sys.exit(1)

    if args.tc_id:
        tc = next((t for t in test_cases if t.get("tc_id") == args.tc_id), None)
        if not tc:
            print(f"错误：未找到 TC-ID = {args.tc_id}", file=sys.stderr)
            sys.exit(1)

        result = convert_tc(tc)
        output = json.dumps(result, ensure_ascii=False, indent=2)

        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已生成: {args.out}")
        else:
            print(output)

    elif args.all:
        outdir = Path(args.outdir or ".")
        outdir.mkdir(parents=True, exist_ok=True)

        for tc in test_cases:
            result = convert_tc(tc)
            filename = f"input_{tc_id_to_kebab(tc.get('tc_id', 'unknown'))}.json"
            filepath = outdir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"已生成: {filepath}")

    else:
        print("错误：请指定 --tc-id 或 --all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
