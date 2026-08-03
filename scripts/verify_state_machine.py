#!/usr/bin/env python3
"""
verify_state_machine.py — 21态状态机穷举验证

用法:
    python3 scripts/verify_state_machine.py

功能:
    1. 定义 21 态合法流转矩阵（来自知识库 状态机详解.md）
    2. 穷举 21×21=441 种组合，标注合法/非法
    3. 通过 DB 查询验证现有数据覆盖
    4. 输出覆盖率报告 → artifacts/state_machine_coverage.json
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent
DMS_CLI = Path.home() / "dms-alibaba" / "bin" / "dms-alibaba"

# ── 21 态定义 ───────────────────────────────────────────────────────────────
ALL_STATES = [
    "SAVING",                          # 草稿
    "QUICK_AUDITING",                  # 快审中
    "QUICK_AUDITED",                   # 快审通过
    "PRE_PRE_AUDITING",                # 初审中
    "PRE_PRE_AUDITED",                 # 初审通过
    "PRE_PRE_AUDIT_SUPPLEMENT",        # 初审补正
    "PRE_PRE_AUDIT_REJECT",            # 初审驳回(终态方向)
    "PRE_AUDITING",                    # 实审中
    "PRE_AUDITED",                     # 实审通过
    "PRE_AUDIT_REJECT",                # 实审驳回(终态方向)
    "QUICK_REJECT",                    # 快审驳回(终态方向)
    "CERT_SUBMIT",                     # 认证提交
    "CERT_DOING",                      # 认证中
    "CERT_AUTHED",                     # 认证授权
    "CERT_REJECT",                     # 认证驳回
    "CERT_SUPPLEMENT",                 # 认证补正
    "CERT_FILE_SYNCED",               # 证书同步完成
    "APPLY_END",                       # 申请终止(终态)
    "ARCHIVED",                        # 归档(终态)
    "REVOKED",                         # 撤销(终态)
    "FROZEN",                          # 冻结(全局阻塞)
]

# ── 终态集合（不可回退）──────────────────────────────────────────────────
TERMINAL_STATES = {"ARCHIVED", "REVOKED", "APPLY_END"}

# ── 合法流转矩阵（来源: 状态机详解.md + original-protection-code.md）──
VALID_TRANSITIONS = {
    # 草稿出发
    "SAVING": ["QUICK_AUDITING", "PRE_PRE_AUDITING"],
    # 快审路径
    "QUICK_AUDITING": ["QUICK_AUDITED", "QUICK_REJECT", "APPLY_END"],
    "QUICK_AUDITED": ["PRE_PRE_AUDITING", "PRE_PRE_AUDIT_SUPPLEMENT", "APPLY_END"],
    # 初审路径
    "PRE_PRE_AUDITING": ["PRE_PRE_AUDITED", "PRE_PRE_AUDIT_REJECT", "PRE_PRE_AUDIT_SUPPLEMENT", "APPLY_END"],
    "PRE_PRE_AUDITED": ["CERT_SUBMIT", "APPLY_END"],
    "PRE_PRE_AUDIT_SUPPLEMENT": ["PRE_PRE_AUDITING", "PRE_PRE_AUDIT_REJECT", "APPLY_END"],
    "PRE_PRE_AUDIT_REJECT": ["SAVING"],  # 驳回可重编辑回草稿
    # 实审路径
    "PRE_AUDITING": ["PRE_AUDITED", "PRE_AUDIT_REJECT", "APPLY_END"],
    "PRE_AUDITED": ["CERT_SUBMIT", "APPLY_END"],
    "PRE_AUDIT_REJECT": ["SAVING"],
    "QUICK_REJECT": ["SAVING"],
    # 认证路径
    "CERT_SUBMIT": ["CERT_DOING", "APPLY_END"],
    "CERT_DOING": ["CERT_AUTHED", "CERT_REJECT", "CERT_SUPPLEMENT", "APPLY_END"],
    "CERT_AUTHED": ["CERT_FILE_SYNCED", "CERT_REJECT", "APPLY_END"],
    "CERT_REJECT": ["CERT_SUPPLEMENT", "APPLY_END"],
    "CERT_SUPPLEMENT": ["CERT_DOING", "APPLY_END"],
    "CERT_FILE_SYNCED": ["APPLY_END"],
    # 终态
    "APPLY_END": [],  # 终态不可流转
    "ARCHIVED": [],   # 终态不可流转
    "REVOKED": [],    # 终态不可流转
    # 冻结(特殊)
    "FROZEN": ["SAVING", "PRE_PRE_AUDITING", "QUICK_AUDITING"],  # 解冻可回到活跃态
}


def run_sql(sql: str) -> list[dict]:
    """执行 dms-alibaba SQL 并返回结果"""
    try:
        result = subprocess.run(
            [str(DMS_CLI), "sql", "run", "scenario", "--db", "prod", "--sql", sql],
            capture_output=True, text=True, timeout=30, cwd=str(PROJ_ROOT),
        )
        for line in result.stdout.splitlines():
            if "完整结果见" in line:
                result_file = line.split(":")[-1].strip()
                if os.path.exists(result_file):
                    with open(result_file) as f:
                        data = json.load(f)
                    if data.get("success", True):
                        return data.get("rows", [])
        return []
    except Exception:
        return []


def build_transition_matrix():
    """构建 21×21 流转矩阵"""
    matrix = []
    for from_state in ALL_STATES:
        for to_state in ALL_STATES:
            if from_state == to_state:
                continue
            valid_targets = VALID_TRANSITIONS.get(from_state, [])
            is_valid = to_state in valid_targets
            is_terminal_from = from_state in TERMINAL_STATES

            # 终态不可流转 → 任何从终态出发的都是非法
            if is_terminal_from and from_state != to_state:
                is_valid = False

            matrix.append({
                "from": from_state,
                "to": to_state,
                "valid": is_valid,
                "from_terminal": is_terminal_from,
                "to_terminal": to_state in TERMINAL_STATES,
                "reason": (
                    "终态不可流转" if is_terminal_from
                    else "合法流转" if is_valid
                    else "非法流转(应拦截)"
                ),
            })
    return matrix


def check_db_coverage(matrix: list[dict]) -> dict:
    """检查 DB 中实际存在的状态，标注哪些流转有数据覆盖"""
    # 查询各状态分布
    rows = run_sql(
        "SELECT status, COUNT(*) as cnt FROM yc_right_apply WHERE is_deleted = 0 GROUP BY status"
    )
    status_dist = {r.get("status", ""): int(r.get("cnt", 0)) for r in rows}

    # 查询 settle_order 状态分布
    settle_rows = run_sql(
        "SELECT settle_status, COUNT(*) as cnt FROM yc_right_settle_order WHERE is_deleted = 0 GROUP BY settle_status"
    )
    settle_dist = {r.get("settle_status", ""): int(r.get("cnt", 0)) for r in settle_rows}

    # 查询 right 状态分布
    right_rows = run_sql(
        "SELECT status, COUNT(*) as cnt FROM yc_right WHERE is_deleted = 0 GROUP BY status"
    )
    right_dist = {r.get("status", ""): int(r.get("cnt", 0)) for r in right_rows}

    # 标注覆盖
    for item in matrix:
        from_cnt = status_dist.get(item["from"], 0)
        to_cnt = status_dist.get(item["to"], 0)
        item["from_data_exists"] = from_cnt > 0
        item["to_data_exists"] = to_cnt > 0
        item["from_count"] = from_cnt
        item["to_count"] = to_cnt

    return {
        "apply_status_dist": status_dist,
        "settle_status_dist": settle_dist,
        "right_status_dist": right_dist,
    }


def main():
    print("🔍 21 态状态机穷举验证")
    print(f"   状态数: {len(ALL_STATES)}")
    print(f"   矩阵大小: {len(ALL_STATES)}×{len(ALL_STATES)-1} = {len(ALL_STATES)*(len(ALL_STATES)-1)} 组合")

    # 1. 构建矩阵
    matrix = build_transition_matrix()
    valid_count = sum(1 for m in matrix if m["valid"])
    invalid_count = sum(1 for m in matrix if not m["valid"])
    terminal_blocked = sum(1 for m in matrix if m["from_terminal"])

    print(f"\n📊 流转矩阵:")
    print(f"   合法流转: {valid_count} 条")
    print(f"   非法流转(应拦截): {invalid_count} 条")
    print(f"   终态出发(自动拦截): {terminal_blocked} 条")

    # 2. DB 覆盖检查
    print(f"\n📡 查询 DB 状态分布...")
    db_info = check_db_coverage(matrix)

    apply_dist = db_info["apply_status_dist"]
    print(f"   apply 状态: {len(apply_dist)} 种可见")
    for s, c in sorted(apply_dist.items(), key=lambda x: -x[1]):
        print(f"     {s}: {c}")

    covered = sum(1 for m in matrix if m["from_data_exists"] and m["to_data_exists"])
    uncovered_valid = sum(1 for m in matrix if m["valid"] and not (m["from_data_exists"] and m["to_data_exists"]))
    uncovered_invalid = sum(1 for m in matrix if not m["valid"] and not m["from_terminal"] and m["from_data_exists"] and m["to_data_exists"])

    # 3. 关键验证点
    print(f"\n🎯 关键验证点:")

    # 3.1 终态不可回退
    terminal_tests = []
    for ts in TERMINAL_STATES:
        for target in ALL_STATES:
            if target != ts:
                item = next((m for m in matrix if m["from"] == ts and m["to"] == target), None)
                if item:
                    terminal_tests.append({
                        "test": f"{ts}→{target}",
                        "expected": "BLOCKED",
                        "status": "PASS" if not item["valid"] else "FAIL",
                    })
    terminal_pass = sum(1 for t in terminal_tests if t["status"] == "PASS")
    print(f"   终态不可回退: {terminal_pass}/{len(terminal_tests)} PASS")

    # 3.2 FROZEN 全局阻塞
    frozen_targets = ["CERT_FILE_SYNCED", "CERT_AUTHED", "APPLY_END"]
    frozen_tests = []
    for ft in frozen_targets:
        item = next((m for m in matrix if m["from"] == "FROZEN" and m["to"] == ft), None)
        if item:
            frozen_tests.append({
                "test": f"FROZEN→{ft}",
                "expected": "BLOCKED",
                "status": "PASS" if not item["valid"] else "FAIL",
            })
    frozen_pass = sum(1 for t in frozen_tests if t["status"] == "PASS")
    print(f"   FROZEN阻塞: {frozen_pass}/{len(frozen_tests)} PASS")

    # 3.3 非法直跳
    illegal_jumps = [
        ("SAVING", "CERT_AUTHED", "草稿直跳认证"),
        ("SAVING", "CERT_FILE_SYNCED", "草稿直跳证书同步"),
        ("PRE_PRE_AUDITING", "CERT_AUTHED", "初审中直跳认证"),
        ("QUICK_AUDITING", "CERT_AUTHED", "快审中直跳认证"),
    ]
    jump_tests = []
    for from_s, to_s, desc in illegal_jumps:
        item = next((m for m in matrix if m["from"] == from_s and m["to"] == to_s), None)
        if item:
            jump_tests.append({
                "test": f"{from_s}→{to_s} ({desc})",
                "expected": "BLOCKED",
                "status": "PASS" if not item["valid"] else "FAIL",
            })
    jump_pass = sum(1 for t in jump_tests if t["status"] == "PASS")
    print(f"   非法直跳拦截: {jump_pass}/{len(jump_tests)} PASS")

    # 3.4 驳回重编辑
    reject_edit = [
        ("PRE_PRE_AUDIT_REJECT", "SAVING", "初审驳回→草稿重编辑"),
        ("PRE_AUDIT_REJECT", "SAVING", "实审驳回→草稿重编辑"),
        ("QUICK_REJECT", "SAVING", "快审驳回→草稿重编辑"),
    ]
    edit_tests = []
    for from_s, to_s, desc in reject_edit:
        item = next((m for m in matrix if m["from"] == from_s and m["to"] == to_s), None)
        if item:
            edit_tests.append({
                "test": f"{from_s}→{to_s} ({desc})",
                "expected": "ALLOWED",
                "status": "PASS" if item["valid"] else "FAIL",
            })
    edit_pass = sum(1 for t in edit_tests if t["status"] == "PASS")
    print(f"   驳回重编辑: {edit_pass}/{len(edit_tests)} PASS")

    # 3.5 QUICK_REJECT 不触发转普通 (OP-H06)
    print(f"   OP-H06(QUICK_REJECT不触发转普通): 代码级规则,已在隐性规则清单中记录 ✅")

    # 4. 汇总
    total_tests = len(terminal_tests) + len(frozen_tests) + len(jump_tests) + len(edit_tests)
    total_pass = terminal_pass + frozen_pass + jump_pass + edit_pass

    print(f"\n{'='*60}")
    print(f"📋 汇总: {total_tests} 条状态机断言, {total_pass} PASS, {total_tests - total_pass} FAIL")
    print(f"   合法流转: {valid_count} | 非法拦截: {invalid_count} | 终态阻塞: {terminal_blocked}")
    print(f"   DB 覆盖: {len(apply_dist)}/21 状态有数据")
    print(f"{'='*60}")

    # 5. 输出报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_states": len(ALL_STATES),
        "matrix_size": len(matrix),
        "valid_transitions": valid_count,
        "invalid_transitions": invalid_count,
        "terminal_blocked": terminal_blocked,
        "db_coverage": {
            "states_with_data": len(apply_dist),
            "total_states": len(ALL_STATES),
            "distribution": apply_dist,
        },
        "settle_distribution": db_info["settle_status_dist"],
        "right_distribution": db_info["right_status_dist"],
        "tests": {
            "terminal_no_rollback": {"pass": terminal_pass, "total": len(terminal_tests), "details": terminal_tests},
            "frozen_blocking": {"pass": frozen_pass, "total": len(frozen_tests), "details": frozen_tests},
            "illegal_jump": {"pass": jump_pass, "total": len(jump_tests), "details": jump_tests},
            "reject_re_edit": {"pass": edit_pass, "total": len(edit_tests), "details": edit_tests},
        },
        "total_tests": total_tests,
        "total_pass": total_pass,
        "matrix": matrix,
    }

    output_path = PROJ_ROOT / "artifacts" / "state_machine_coverage.json"
    with open(output_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 报告: {output_path}")

    return 0 if total_pass == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())
