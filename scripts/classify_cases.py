#!/usr/bin/env python3
"""
classify_cases.py — 测试用例自动分级脚本

基于用例特征（文件名、category、步骤数、断言数、依赖关系等）自动评估优先级，
生成分级报告并可选写回用例文件。

分级规则：
  P0（核心）: 冒烟/E2E/全链路 + 核心业务流程 + 自愈验证
  P1（重要）: 正常流程 + 回归 + 状态机 + 功能验证
  P2（一般）: 边界条件 + API 契约 + 原子操作
  P3（低优）: 探索性/实验性 + 超长步骤但无断言

使用方式:
    # 生成报告（不修改文件）
    python3 scripts/classify_cases.py

    # 写回分级结果
    python3 scripts/classify_cases.py --write

    # 仅处理指定场景
    python3 scripts/classify_cases.py --scene f88-test
"""

import json
import os
import sys
import glob
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone


# ── 分级规则权重 ──

RULE_WEIGHTS = {
    # 文件名关键词
    "smoke": 3,           # smoke_ 开头 → P0
    "e2e": 3,             # E2E 全链路 → P0
    "heal": 3,            # 自愈验证 → P0
    "error_": 2,          # 错误处理 → P1
    "boundary": 1,        # 边界条件 → P2
    "regression": 2,      # 回归 → P1
    "normal": 2,          # 正常流程 → P1

    # category 加分
    "cat_smoke": 3,
    "cat_e2e": 3,
    "cat_e2e_flow": 3,
    "cat_self_healing_validation": 3,
    "cat_normal_flow": 2,
    "cat_regression": 2,
    "cat_state_machine": 2,
    "cat_functional": 2,
    "cat_boundary": 1,
    "cat_api_contract": 1,
    "cat_atomic": 1,
    "cat_error_flow": 1,

    # 结构特征
    "has_assertions": 1,  # 有断言 +1
    "many_steps": 0,      # 步骤多不加分（可能是臃肿用例）
    "has_capture": 1,     # 需要抓包 +1
    "has_preconditions": 1,  # 有前置条件 +1
    "has_depends_on": 1,  # 有依赖 +1（说明是链路中的关键节点）
}


def classify_case(case: dict, filepath: str) -> tuple:
    """
    对单个用例进行分级。

    Returns:
        (priority, score, reasons) — 如 ("P0", 8, ["smoke前缀", "category=smoke"])
    """
    score = 0
    reasons = []
    basename = os.path.basename(filepath).lower()
    category = case.get("category", "").lower()
    name = case.get("name", "").lower()
    steps = case.get("steps", [])
    step_count = len(steps)

    # ── 1. 文件名关键词 ──
    if basename.startswith("smoke"):
        score += RULE_WEIGHTS["smoke"]
        reasons.append("smoke前缀")
    if "e2e" in basename or "tc-e2e" in basename:
        score += RULE_WEIGHTS["e2e"]
        reasons.append("E2E全链路")
    if basename.startswith("heal") or "heal" in basename:
        score += RULE_WEIGHTS["heal"]
        reasons.append("自愈验证")
    if basename.startswith("error_"):
        score += RULE_WEIGHTS["error_"]
        reasons.append("错误处理")
    if basename.startswith("boundary"):
        score += RULE_WEIGHTS["boundary"]
        reasons.append("边界条件")
    if "regression" in basename:
        score += RULE_WEIGHTS["regression"]
        reasons.append("回归")

    # ── 2. category 加分 ──
    cat_key = f"cat_{category}"
    if cat_key in RULE_WEIGHTS:
        score += RULE_WEIGHTS[cat_key]
        reasons.append(f"category={category}")

    # ── 3. 结构特征 ──
    # 检查是否有断言
    has_assert = False
    for step in steps:
        if step.get("assert") or step.get("asserts") or step.get("assertion"):
            has_assert = True
            break
        if step.get("type") in ("assert", "assertStore", "assertAPI"):
            has_assert = True
            break
    if has_assert:
        score += RULE_WEIGHTS["has_assertions"]
        reasons.append("有断言")

    # 抓包
    capture = case.get("capture", {})
    if isinstance(capture, dict) and capture.get("enabled"):
        score += RULE_WEIGHTS["has_capture"]
        reasons.append("需要抓包")

    # 前置条件
    if case.get("preconditions"):
        score += RULE_WEIGHTS["has_preconditions"]
        reasons.append("有前置条件")

    # 依赖
    if case.get("depends_on"):
        score += RULE_WEIGHTS["has_depends_on"]
        reasons.append("有依赖")

    # ── 4. 扣分项 ──
    # 步骤过多但无断言（臃肿用例）
    if step_count > 30 and not has_assert:
        score -= 2
        reasons.append("步骤多但无断言(扣分)")

    # ── 5. 映射到优先级 ──
    if score >= 6:
        priority = "P0"
    elif score >= 3:
        priority = "P1"
    elif score >= 1:
        priority = "P2"
    else:
        priority = "P3"

    return priority, score, reasons


def run_classification(cases_dir: str, scene_filter: str = None) -> dict:
    """
    对全部用例执行分级。

    Returns:
        分级报告 dict
    """
    results = {
        "total": 0,
        "original_priority": Counter(),
        "new_priority": Counter(),
        "changed": 0,
        "unchanged": 0,
        "details": defaultdict(list),  # priority -> list of (filepath, old, new, score, reasons)
        "by_scene": defaultdict(lambda: Counter()),
    }

    for filepath in sorted(glob.glob(os.path.join(cases_dir, "**/*.json"), recursive=True)):
        try:
            case = json.load(open(filepath, encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            continue

        # 场景过滤
        if scene_filter:
            parts = filepath.split(os.sep)
            scene = parts[2] if len(parts) > 2 else ""
            if scene_filter not in scene:
                continue

        old_priority = case.get("priority", "NONE")
        new_priority, score, reasons = classify_case(case, filepath)

        results["total"] += 1
        results["original_priority"][old_priority] += 1
        results["new_priority"][new_priority] += 1

        # 检测场景
        parts = filepath.split(os.sep)
        scene = parts[2] if len(parts) > 2 else "unknown"
        results["by_scene"][scene][new_priority] += 1

        if old_priority != new_priority:
            results["changed"] += 1
        else:
            results["unchanged"] += 1

        results["details"][new_priority].append({
            "file": filepath,
            "old": old_priority,
            "new": new_priority,
            "score": score,
            "reasons": reasons,
            "changed": old_priority != new_priority,
        })

    return results


def print_report(results: dict):
    """打印分级报告"""
    print("=" * 70)
    print("测试用例分级报告")
    print(f"生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    print(f"\n用例总数: {results['total']}")
    print(f"优先级变更: {results['changed']} 条 | 未变更: {results['unchanged']} 条")

    print("\n── 优先级分布对比 ──")
    print(f"{'级别':<8} {'原始':>8} {'新分级':>8} {'变化':>8}")
    print("-" * 36)
    for p in ["P0", "P1", "P2", "P3", "NONE"]:
        old = results["original_priority"].get(p, 0)
        new = results["new_priority"].get(p, 0)
        diff = new - old
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        if old or new:
            print(f"{p:<8} {old:>8} {new:>8} {diff_str:>8}")

    print("\n── 按场景分布 ──")
    for scene in sorted(results["by_scene"].keys()):
        counts = results["by_scene"][scene]
        parts = " | ".join(f"{p}={counts.get(p, 0)}" for p in ["P0", "P1", "P2", "P3"] if counts.get(p, 0))
        print(f"  {scene}: {parts}")

    # 变更明细（仅显示变更的前 20 条）
    changed_items = [
        d for items in results["details"].values() for d in items if d["changed"]
    ]
    if changed_items:
        print(f"\n── 变更明细（前 {min(20, len(changed_items))} 条）──")
        for item in changed_items[:20]:
            status = "↑" if item["new"] < item["old"] else "↓"
            print(f"  {status} {item['old']}→{item['new']} (score={item['score']}) "
                  f"{os.path.basename(item['file'])[:50]}")
            if item["reasons"]:
                print(f"    原因: {', '.join(item['reasons'][:3])}")

    print("\n" + "=" * 70)


def write_classification(cases_dir: str, results: dict):
    """将分级结果写回用例文件"""
    written = 0
    for items in results["details"].values():
        for item in items:
            if not item["changed"]:
                continue
            filepath = item["file"]
            try:
                case = json.load(open(filepath, encoding="utf-8"))
                case["priority"] = item["new"]
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(case, f, ensure_ascii=False, indent=2)
                written += 1
            except (json.JSONDecodeError, IOError) as e:
                print(f"  [WARN] 写入失败: {filepath}: {e}", file=sys.stderr)
    print(f"\n已写入 {written} 个用例的分级结果。")


def main():
    parser = argparse.ArgumentParser(description="测试用例自动分级")
    parser.add_argument("--write", action="store_true", help="将分级结果写回用例文件")
    parser.add_argument("--scene", type=str, default="", help="仅处理指定场景（如 f88-test）")
    parser.add_argument("--cases-dir", type=str, default="eval/cases", help="用例目录")
    args = parser.parse_args()

    if not os.path.isdir(args.cases_dir):
        print(f"错误: 用例目录不存在: {args.cases_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"扫描目录: {args.cases_dir}")
    if args.scene:
        print(f"场景过滤: {args.scene}")

    results = run_classification(args.cases_dir, scene_filter=args.scene or None)
    print_report(results)

    if args.write:
        write_classification(args.cases_dir, results)


if __name__ == "__main__":
    main()
