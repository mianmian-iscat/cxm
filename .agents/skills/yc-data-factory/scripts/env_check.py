#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
env_check.py — 原创保护 HSF 写操作前置环境校验脚本

用途：在调用任何会修改 yc_right_apply / yc_right / yc_right_settle_order 的 HSF Tool 服务前，
      强制确认目标记录的 env 字段为 'staging'。只有 staging 数据才允许继续写操作。

退出码：
  0 — 校验通过，目标为 staging 数据
  1 — 参数错误 / 环境错误 / 查询失败
  2 — 目标为生产数据（env='prod'/'production'）或 env 异常，必须中止

使用方式：
  python3 scripts/env_check.py --apply-id 200001005
  python3 scripts/env_check.py --apply-id 200001005 --db-group scenario --db-name prod
  APPLY_ID=200001005 python3 scripts/env_check.py
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Optional


DEFAULT_DB_GROUP = "scenario"
DEFAULT_DB_NAME = "prod"
SQL_TEMPLATE = "SELECT id, env FROM yc_right_apply WHERE id = {apply_id}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="原创保护 HSF 写操作前置环境校验：仅允许 env='staging'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 scripts/env_check.py --apply-id 200001005
  python3 scripts/env_check.py --apply-id 200001005 --db-group scenario --db-name prod
        """,
    )
    parser.add_argument(
        "--apply-id",
        type=str,
        default=os.environ.get("APPLY_ID"),
        help="目标申请编号（yc_right_apply.id），也可通过环境变量 APPLY_ID 传入",
    )
    parser.add_argument(
        "--db-group",
        type=str,
        default=os.environ.get("DB_GROUP", DEFAULT_DB_GROUP),
        help=f"dms-alibaba 数据库组名，默认 {DEFAULT_DB_GROUP}",
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=os.environ.get("DB_NAME", DEFAULT_DB_NAME),
        help=f"dms-alibaba 数据库名，默认 {DEFAULT_DB_NAME}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式结果，便于下游脚本解析",
    )
    return parser


def run_query(db_group: str, db_name: str, apply_id: str) -> dict:
    """调用 dms-alibaba sql query 执行只读校验 SQL，返回解析后的 JSON。"""
    sql = SQL_TEMPLATE.format(apply_id=apply_id)
    cmd = [
        "dms-alibaba",
        "sql",
        "query",
        db_group,
        "--db",
        db_name,
        "--sql",
        sql,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("dms-alibaba CLI 未找到，请确认已安装并加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("dms-alibaba 查询超时（60s），请检查网络或稍后重试") from exc

    # CLI 可能在 stdout 前面打印清理日志，取最后一行 JSON
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"dms-alibaba 无输出，stderr: {result.stderr.strip()}")

    last_line = stdout.splitlines()[-1]
    try:
        data = json.loads(last_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"无法解析 dms-alibaba 输出: {last_line}") from exc

    if not data.get("success"):
        msg = data.get("message") or data.get("error") or "未知错误"
        raise RuntimeError(f"dms-alibaba 查询失败: {msg}")

    return data


def parse_env(data: dict, apply_id: str) -> tuple[str, Optional[str]]:
    """从查询结果中解析 env 字段。返回 (status, env_value)。"""
    rows = data.get("rows", [])
    if not rows:
        return "missing", None

    # 取第一行
    row = rows[0]
    env_value = (row.get("env") or "").strip().lower()
    record_id = row.get("id")

    if str(record_id) != str(apply_id):
        return "mismatch", env_value

    if env_value == "staging":
        return "staging", env_value

    if env_value in ("prod", "production"):
        return "production", env_value

    return "unknown", env_value


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    apply_id = args.apply_id
    if not apply_id:
        message = "缺少 --apply-id 参数或 APPLY_ID 环境变量"
        if args.json:
            print(json.dumps({"pass": False, "code": 1, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] ❌ {message}")
        return 1

    # 基础数字校验
    if not apply_id.isdigit():
        message = f"apply_id 必须是纯数字，收到: {apply_id}"
        if args.json:
            print(json.dumps({"pass": False, "code": 1, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] ❌ {message}")
        return 1

    try:
        data = run_query(args.db_group, args.db_name, apply_id)
        status, env_value = parse_env(data, apply_id)
    except RuntimeError as exc:
        message = str(exc)
        if args.json:
            print(json.dumps({"pass": False, "code": 1, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] ❌ 查询失败: {message}")
        return 1

    if status == "staging":
        message = f"apply_id={apply_id} env=staging，校验通过，允许执行写操作"
        if args.json:
            print(json.dumps({"pass": True, "code": 0, "apply_id": apply_id, "env": "staging"}, ensure_ascii=False))
        else:
            print(f"[env_check] ✅ {message}")
        return 0

    if status == "production":
        message = (
            f"apply_id={apply_id} env={env_value}，检测到生产数据，"
            f"禁止执行任何 HSF 写操作！"
        )
        if args.json:
            print(json.dumps({"pass": False, "code": 2, "apply_id": apply_id, "env": env_value, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] 🚨 {message}")
        return 2

    if status == "missing":
        message = f"apply_id={apply_id} 在 yc_right_apply 中未找到记录"
        if args.json:
            print(json.dumps({"pass": False, "code": 2, "apply_id": apply_id, "env": None, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] 🚨 {message}")
        return 2

    if status == "mismatch":
        message = f"apply_id={apply_id} 查询结果 ID 不匹配，可能存在 SQL 注入或数据异常"
        if args.json:
            print(json.dumps({"pass": False, "code": 2, "apply_id": apply_id, "env": env_value, "message": message}, ensure_ascii=False))
        else:
            print(f"[env_check] 🚨 {message}")
        return 2

    # unknown env
    message = f"apply_id={apply_id} env='{env_value}' 不是预期的 staging，禁止写操作"
    if args.json:
        print(json.dumps({"pass": False, "code": 2, "apply_id": apply_id, "env": env_value, "message": message}, ensure_ascii=False))
    else:
        print(f"[env_check] 🚨 {message}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
