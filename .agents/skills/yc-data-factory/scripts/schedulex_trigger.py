#!/usr/bin/env python3
"""
原创保护结算 Job 链 ScheduleX 触发脚本

使用场景：在预发环境手动触发原创保护结算/退款/确收定时任务，
替代凌晨定时等待，加速端到端验证。

结算 Job 链（必须按顺序执行）：
  1. 715618497 首发补贴退款
  2. 399576024 专利保护定时失效
  3. 719211870 服务完结退款（下架率 < 70% 走此路径）
  4. 721504806 服务完结确认收（下架率 >= 70% 走此路径）

调用方式：
  # 生成操作计划（不实际触发）
  python3 schedulex_trigger.py --dry-run --apply-id 200000874

  # 尝试自动触发（CLI/浏览器），失败则输出手动指南
  python3 schedulex_trigger.py --apply-id 200000874 --job-chain expire,refund

  # 仅触发单个任务
  python3 schedulex_trigger.py --job-id 399576024 --data-time 2026-08-18

  # 触发后持续 DB 验证
  python3 schedulex_trigger.py --apply-id 200000874 --job-chain expire --verify-db
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_CHECK_SCRIPT = os.path.join(SKILL_DIR, "scripts", "env_check.py")

JOB_CHAIN = {
    "full": [715618497, 399576024, 719211870, 721504806],
    "expire": [399576024],          # 专利保护定时失效
    "refund": [719211870],          # 服务完结退款
    "income": [721504806],          # 服务完结确认收
    "allowance_refund": [715618497],# 首发补贴退款
}

JOB_INFO = {
    715618497: {"name": "首发补贴退款", "class": "-", "effect": "处理首发补贴退款"},
    399576024: {"name": "专利保护定时失效", "class": "RightProtectExpiredJob", "effect": "扫描过期申请 -> yc_right.status=YC_PROTECT_INVALID -> 按下架率分流结算单"},
    719211870: {"name": "服务完结退款", "class": "ServFinishRefundJob", "effect": "下架率<70% 执行退款"},
    721504806: {"name": "服务完结确认收", "class": "ServFinishIncomeJob", "effect": "下架率>=70% 执行确收"},
}

SCHEDULEX_CONSOLE = "https://pre.schedulerx2.alibaba-inc.com/#/JobList?regionId=cn-hangzhou&namespace=system_namespace&source=schedulerx"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_cmd(cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
    """执行 shell 命令，返回 (returncode, stdout, stderr)"""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired as e:
        return -1, "", f"timeout after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def check_a1_schedulerx_available() -> bool:
    """检查 a1 schedulerx 命令是否可用"""
    rc, _, _ = run_cmd("a1 schedulerx --help", timeout=10)
    return rc == 0


def check_browser_automation_available() -> bool:
    """检查浏览器自动化依赖是否可用（简化检查：看 python 包）"""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def env_check(apply_id: int) -> bool:
    """调用 env_check.py 确认 applyId 为 staging"""
    if not os.path.exists(ENV_CHECK_SCRIPT):
        log(f"警告：env_check.py 不存在 ({ENV_CHECK_SCRIPT})，跳过 env 校验")
        return True
    rc, out, err = run_cmd(f"python3 {ENV_CHECK_SCRIPT} --apply-id {apply_id}", timeout=30)
    if rc == 0:
        log(f"env 校验通过：applyId={apply_id} 为 staging")
        return True
    log(f"env 校验失败（rc={rc}）：{out or err}")
    return False


def trigger_via_cli(job_id: int, data_time: str, dry_run: bool = False) -> Tuple[bool, str]:
    """
    尝试通过 a1 schedulerx job run 触发。
    当前（2026-08-18）a1 schedulerx 子命令不存在，此函数主要记录期望 CLI。
    """
    if dry_run:
        return True, f"[dry-run] 将执行：a1 schedulerx job run --jobId {job_id} --dataTime {data_time}"

    if not check_a1_schedulerx_available():
        return False, "a1 schedulerx 命令不可用"

    cmd = f"a1 schedulerx job run --jobId {job_id} --dataTime {data_time}"
    rc, out, err = run_cmd(cmd, timeout=60)
    if rc == 0:
        return True, out
    return False, f"命令失败 rc={rc}: {err or out}"


def trigger_via_browser(job_id: int, dry_run: bool = False) -> Tuple[bool, str]:
    """
    尝试通过浏览器自动化点击 ScheduleX 控制台「运行一次」。
    警告：pre.schedulerx2 页面有阿里安全脚本（baxia/sufei_data/AWSC），且「运行一次」
    是 React 渲染的 span，普通 .click() 不触发事件。此路径为实验性，成功率低。
    """
    if dry_run:
        return True, (
            f"[dry-run] 将打开 {SCHEDULEX_CONSOLE}，搜索 Task ID {job_id}，"
            "并尝试通过 CDP 坐标点击「运行一次」按钮。"
        )
    return False, (
        "浏览器自动化触发 ScheduleX 暂不实现。原因：React span 点击失效 + 阿里安全脚本拦截。"
        "请使用手动触发模式：python3 schedulex_trigger.py --manual"
    )


def generate_manual_guide(job_ids: List[int], data_time: str) -> str:
    """生成手动触发操作步骤（严格编号，可直接照做）"""
    lines = [
        "",
        "=" * 70,
        "ScheduleX 手动触发操作步骤（按编号执行，禁止跳过）",
        "=" * 70,
        "",
        "【前置准备】",
        f"  步骤 0.1：打开浏览器，访问控制台：{SCHEDULEX_CONSOLE}",
        f"  步骤 0.2：确认本次处理日期（dataTime）：{data_time}",
        "",
        "【任务执行】（必须等前一个任务完成后再执行下一个）",
    ]
    base_step = 1
    for idx, job_id in enumerate(job_ids, 1):
        info = JOB_INFO.get(job_id, {})
        lines.extend([
            "",
            f"任务 {idx}/{len(job_ids)}：{info.get('name', '-')}（Task ID: {job_id}）",
            f"  步骤 {base_step}：在控制台右上角搜索框输入 {job_id}",
            f"  步骤 {base_step + 1}：按 Enter 键触发搜索，等待任务列表出现对应任务行",
            f"  步骤 {base_step + 2}：点击任务行右侧的「运行一次」按钮",
            f"  步骤 {base_step + 3}：在弹出的参数输入框中填写 dataTime = {data_time}",
            f"  步骤 {base_step + 4}：点击弹窗中的「确定」按钮",
            f"  步骤 {base_step + 5}：等待页面提示「触发成功」或任务状态变为 RUNNING/SUCCESS",
            f"  步骤 {base_step + 6}：确认该任务执行完成后，再继续下一个任务",
        ])
        base_step += 7

    lines.extend([
        "",
        "【结果验证】",
        f"  步骤 {base_step}：等待 1-2 分钟后，执行以下 SQL 验证状态流转",
        "",
        "  SELECT id, status, protect_expire_time, serv_finish_refund_status, serv_finish_income_status",
        "  FROM yc_right",
        "  WHERE right_apply_id = {applyId} AND env = 'staging';",
        "",
        "  SELECT id, settle_status, init_allowance_start_time",
        "  FROM yc_right_settle_order",
        "  WHERE right_apply_id = {applyId} AND env = 'staging';",
        "",
        "⚠️ 关键注意事项：",
        "- 必须等前一个 Job 执行完成再触发下一个，避免状态竞争。",
        "- 若浏览器连接超时，请直接用本机 Chrome 访问控制台手动操作。",
        "- 严禁操作生产环境，所有验证 SQL 必须带 env='staging' 过滤。",
    ])
    return "\n".join(lines)


def verify_db(apply_id: int) -> Tuple[bool, str]:
    """查询 DB 验证结算状态"""
    sql = (
        f"SELECT r.id, r.status, r.protect_expire_time, r.serv_finish_refund_status, r.serv_finish_income_status, "
        f"s.id AS settle_id, s.settle_status, s.init_allowance_start_time "
        f"FROM yc_right r LEFT JOIN yc_right_settle_order s ON r.right_apply_id = s.right_apply_id "
        f"WHERE r.right_apply_id = {apply_id} AND r.env = 'staging' AND (s.env = 'staging' OR s.env IS NULL) "
        f"ORDER BY s.gmt_create DESC LIMIT 1;"
    )
    cmd = f'dms-alibaba sql query scenario --db prod --sql "{sql}"'
    rc, out, err = run_cmd(cmd, timeout=60)
    if rc == 0:
        return True, out
    return False, f"DB 查询失败 rc={rc}: {err or out}"


def main():
    parser = argparse.ArgumentParser(description="原创保护结算 Job 链 ScheduleX 触发脚本")
    parser.add_argument("--apply-id", type=int, help="目标 applyId（用于 env 校验和 DB 验证）")
    parser.add_argument("--job-id", type=int, help="单个 ScheduleX 任务 ID")
    parser.add_argument("--job-chain", type=str, default="full",
                        help=f"任务链名称：{','.join(JOB_CHAIN.keys())}，或逗号分隔 Task ID")
    parser.add_argument("--data-time", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="ScheduleX dataTime 参数，默认今天")
    parser.add_argument("--dry-run", action="store_true", help="仅生成计划，不实际触发")
    parser.add_argument("--manual", action="store_true", help="仅输出手动操作指南")
    parser.add_argument("--verify-db", action="store_true", help="触发后执行 DB 验证")
    parser.add_argument("--verify-interval", type=int, default=30, help="DB 验证轮询间隔（秒）")
    parser.add_argument("--verify-max-wait", type=int, default=300, help="DB 验证最大等待时间（秒）")
    parser.add_argument("--method", type=str, default="auto",
                        choices=["auto", "cli", "browser", "manual"],
                        help="触发方式：auto=自动选择，cli=CLI，browser=浏览器自动化，manual=手动")
    args = parser.parse_args()

    # 解析任务链
    if args.job_id:
        job_ids = [args.job_id]
    elif args.job_chain in JOB_CHAIN:
        job_ids = JOB_CHAIN[args.job_chain]
    else:
        try:
            job_ids = [int(x.strip()) for x in args.job_chain.split(",")]
        except ValueError:
            log(f"错误：无法解析 --job-chain '{args.job_chain}'")
            sys.exit(1)

    # env 校验
    if args.apply_id:
        if not env_check(args.apply_id):
            log("env 校验未通过，中止执行。")
            sys.exit(2)

    # 仅输出手动指南
    if args.manual or args.method == "manual":
        print(generate_manual_guide(job_ids, args.data_time))
        sys.exit(0)

    # 触发任务链
    results = []
    for job_id in job_ids:
        info = JOB_INFO.get(job_id, {})
        log(f"触发任务 {job_id} ({info.get('name', '-')}) ...")

        success, msg = False, ""
        if args.method in ("auto", "cli"):
            success, msg = trigger_via_cli(job_id, args.data_time, args.dry_run)
            if not success and args.method == "auto":
                log(f"CLI 触发失败：{msg}，尝试浏览器自动化...")
                success, msg = trigger_via_browser(job_id, args.dry_run)
        elif args.method == "browser":
            success, msg = trigger_via_browser(job_id, args.dry_run)

        results.append((job_id, success, msg))
        log(f"任务 {job_id} 结果：{'成功' if success else '失败'} - {msg}")

        if not success and not args.dry_run:
            # 任一任务失败即停止，输出手动指南作为降级
            print(generate_manual_guide(job_ids[job_ids.index(job_id):], args.data_time))
            sys.exit(1)

    # DB 验证
    if args.verify_db and args.apply_id and not args.dry_run:
        log("开始 DB 验证...")
        waited = 0
        last_out = ""
        while waited <= args.verify_max_wait:
            ok, out = verify_db(args.apply_id)
            if ok:
                last_out = out
                log(f"DB 验证查询成功：\n{out}")
                # 简单启发式：如果状态不再是初始状态，认为已完成
                if "YC_PROTECT_INVALID" in out or "FINISH" in out or "INCOME" in out:
                    break
            else:
                log(f"DB 验证查询失败：{out}")
            time.sleep(args.verify_interval)
            waited += args.verify_interval
        if waited > args.verify_max_wait:
            log(f"DB 验证超过最大等待时间 {args.verify_max_wait}s，请手动检查。")
            print(generate_manual_guide(job_ids, args.data_time))
            sys.exit(1)

    # 汇总
    print("\n" + "=" * 70)
    print("触发结果汇总")
    print("=" * 70)
    for job_id, success, msg in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{job_id}: {status} - {msg}")

    if args.dry_run:
        print("\n[DRY-RUN] 未实际触发任何任务。")


if __name__ == "__main__":
    main()
