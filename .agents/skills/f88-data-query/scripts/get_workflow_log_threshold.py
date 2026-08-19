#!/usr/bin/env python3
"""动态获取 workflow_record_log 的最小安全 id 阈值。

用法示例:
    python3 get_workflow_log_threshold.py --days 7
    python3 get_workflow_log_threshold.py --days 7 --output sql
    python3 get_workflow_log_threshold.py --date "2026-08-12 00:00:00" --output json
    python3 get_workflow_log_threshold.py --days 3 --fallback-id 6400000

原理:
    workflow_record_log 按 id 自增，id 与 gmt_create 基本单调。
    脚本通过二分查找定位满足 gmt_create >= cutoff 的最小 id，
    查询走主键索引，避免全表扫描导致 20s 超时。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from typing import Optional

DEFAULT_DB_GROUP = "stylespot"
DEFAULT_DB_INSTANCE = "rm-lgay0v5lor8396yka"
DEFAULT_TABLE = "workflow_record_log"
DEFAULT_FALLBACK_ID = 6_400_000
DMS_ALIBABA = os.path.expanduser("~/dms-alibaba/bin/dms-alibaba")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="动态获取 workflow_record_log 查询安全 id 阈值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
输出格式:
    id   -> 仅打印阈值 id（默认）
    sql  -> 打印 "id >= {threshold}"
    json -> 打印包含 threshold_id/cutoff/max_id 的 JSON
        """.strip(),
    )
    parser.add_argument(
        "--days",
        type=float,
        default=7,
        help="查询最近 N 天的数据（默认 7，可小数）",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="显式指定 cutoff 时间，如 '2026-08-12 00:00:00'（覆盖 --days）",
    )
    parser.add_argument(
        "--table",
        type=str,
        default=DEFAULT_TABLE,
        help=f"目标表名（默认 {DEFAULT_TABLE}）",
    )
    parser.add_argument(
        "--db-group",
        type=str,
        default=DEFAULT_DB_GROUP,
        help=f"dms-alibaba 数据库组（默认 {DEFAULT_DB_GROUP}）",
    )
    parser.add_argument(
        "--db-instance",
        type=str,
        default=DEFAULT_DB_INSTANCE,
        help=f"dms-alibaba --db 实例/组名（默认 {DEFAULT_DB_INSTANCE}）",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="若指定，则在计算阈值时额外过滤 env='{value}'（默认不过滤）",
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["id", "sql", "json"],
        default="id",
        help="输出格式（默认 id）",
    )
    parser.add_argument(
        "--fallback-id",
        type=int,
        default=DEFAULT_FALLBACK_ID,
        help=f"DB 不可用时返回的兜底阈值（默认 {DEFAULT_FALLBACK_ID}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的 SQL，不真正查询",
    )
    parser.add_argument(
        "--cli-path",
        type=str,
        default=DMS_ALIBABA,
        help=f"dms-alibaba CLI 路径（默认 {DMS_ALIBABA}）",
    )
    return parser.parse_args()


def now() -> datetime.datetime:
    return datetime.datetime.now()


def compute_cutoff(days: float, date_str: Optional[str]) -> datetime.datetime:
    if date_str:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析 cutoff 时间: {date_str}")
    return now() - datetime.timedelta(days=days)


def build_sql(
    table: str,
    columns: str,
    where: str,
    order_limit: str = "",
) -> str:
    sql = f"SELECT {columns} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order_limit:
        sql += f" {order_limit}"
    return sql


def run_query(cli_path: str, db_group: str, db_instance: str, sql: str, dry_run: bool) -> dict:
    if dry_run:
        print(f"[DRY-RUN] SQL: {sql}", file=sys.stderr)
        return {"success": True, "rows": []}

    if not os.path.isfile(cli_path):
        raise FileNotFoundError(f"dms-alibaba CLI 未找到: {cli_path}")

    cmd = [
        cli_path,
        "sql",
        "query",
        db_group,
        "--db",
        db_instance,
        "--sql",
        sql,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"dms-alibaba 执行失败: {proc.stderr or proc.stdout}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"无法解析 CLI 输出: {proc.stdout}") from exc

    if not data.get("success"):
        raise RuntimeError(f"SQL 执行未成功: {data.get('message')} (output: {proc.stdout})")
    return data


def get_max_id(
    cli_path: str,
    db_group: str,
    db_instance: str,
    table: str,
    env: Optional[str],
    dry_run: bool,
) -> int:
    where = f"env = '{env}'" if env else "1=1"
    sql = build_sql(table, "MAX(id) AS max_id", where)
    data = run_query(cli_path, db_group, db_instance, sql, dry_run)
    if dry_run:
        return 0
    rows = data.get("rows") or []
    if not rows:
        raise RuntimeError("MAX(id) 查询返回空")
    max_id = rows[0].get("max_id")
    if max_id is None:
        raise RuntimeError("MAX(id) 返回 NULL，表可能为空")
    return int(max_id)


def get_row_at_or_after(
    cli_path: str,
    db_group: str,
    db_instance: str,
    table: str,
    target_id: int,
    env: Optional[str],
    dry_run: bool,
) -> Optional[dict]:
    conditions = [f"id >= {target_id}"]
    if env:
        conditions.append(f"env = '{env}'")
    sql = build_sql(
        table,
        "id, gmt_create",
        " AND ".join(conditions),
        "ORDER BY id ASC LIMIT 1",
    )
    data = run_query(cli_path, db_group, db_instance, sql, dry_run)
    if dry_run:
        return None
    rows = data.get("rows") or []
    if not rows:
        return None
    return rows[0]


def parse_gmt_create(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def find_threshold_id(
    cli_path: str,
    db_group: str,
    db_instance: str,
    table: str,
    cutoff: datetime.datetime,
    env: Optional[str],
    dry_run: bool,
) -> int:
    """二分查找满足 gmt_create >= cutoff 的最小 id。"""
    if dry_run:
        return 0

    max_id = get_max_id(cli_path, db_group, db_instance, table, env, dry_run)

    # 最新记录都比 cutoff 老 -> 返回 max_id+1，使 id >= threshold 结果为空
    latest = get_row_at_or_after(cli_path, db_group, db_instance, table, max_id, env, dry_run)
    if latest is None or parse_gmt_create(latest["gmt_create"]) < cutoff:
        return max_id + 1

    low, high = 1, max_id
    while low < high:
        mid = (low + high) // 2
        row = get_row_at_or_after(cli_path, db_group, db_instance, table, mid, env, dry_run)
        if row is None:
            # 该 id 之后无记录，向左缩
            high = mid
            continue
        row_time = parse_gmt_create(row["gmt_create"])
        if row_time >= cutoff:
            high = mid
        else:
            low = mid + 1
    return low


def main() -> int:
    args = parse_args()
    cutoff = compute_cutoff(args.days, args.date)

    try:
        threshold = find_threshold_id(
            args.cli_path,
            args.db_group,
            args.db_instance,
            args.table,
            cutoff,
            args.env,
            args.dry_run,
        )
        max_id: Optional[int] = None
        if args.output == "json" and not args.dry_run:
            try:
                max_id = get_max_id(
                    args.cli_path,
                    args.db_group,
                    args.db_instance,
                    args.table,
                    args.env,
                    args.dry_run,
                )
            except Exception:
                max_id = None
    except Exception as exc:
        print(f"[WARN] 动态阈值获取失败: {exc}", file=sys.stderr)
        print(f"[WARN] 回退到兜底阈值 id={args.fallback_id}", file=sys.stderr)
        threshold = args.fallback_id
        max_id = None

    if args.output == "id":
        print(threshold)
    elif args.output == "sql":
        print(f"id >= {threshold}")
    elif args.output == "json":
        print(
            json.dumps(
                {
                    "threshold_id": threshold,
                    "cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
                    "max_id": max_id,
                    "table": args.table,
                    "lookback_days": args.days if args.date is None else None,
                    "env": args.env,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
