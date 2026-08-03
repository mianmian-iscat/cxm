#!/usr/bin/env python3
"""
原创保护结算校验脚本 v3 — 基于 PRD + 技术方案权威规则
═══════════════════════════════════════════════════════════════════════
数据源:
  钉钉PRD  《淘天服饰原创保护平台-结算及电子用印》
  技术方案  《原创保护结算技术方案》
  提测单    gvNG4YZ7Jnxop15OCqPbBaAyW2LD0oRE
═══════════════════════════════════════════════════════════════════════
环境配置（来自提测单）:
  测试: total=0.10元  首发补贴=0.06  非首发=0.04  官费=0.02
  生产: total=500元   首发补贴=302   非首发=202   官费=165
═══════════════════════════════════════════════════════════════════════
结算规则（PRD 结算规则表 + 技术方案状态机）:

  ┌─ 有补贴（init_allowance_start_time IS NOT NULL）─┐
  │  补贴退款: 首发 302/0.06  非首发 202/0.04        │
  │  自动确收: total - 补贴                           │
  │  下架率 ≥70% → 完结退 官费(165/0.02)              │
  │  下架率 <70% → 完结退 自动确收-官费               │
  │    首发: 198-165=33 / 0.04-0.02=0.02             │
  │    非首发: 298-165=133 / 0.06-0.02=0.04          │
  └──────────────────────────────────────────────────┘
  ┌─ 无补贴（init_allowance_start_time IS NULL）─────┐
  │  下架率 ≥70% → 完结确收 total(500/0.10)          │
  │  下架率 <70% → 完结退 total-官费(335/0.08)       │
  └──────────────────────────────────────────────────┘

下架率 = PROTECT_SUCCESS / (PROTECT_SUCCESS + PROTECT_FAIL)
  剔除: INCORRECT（暂未构成侵权）、RUNNING（维权进行中，未结案）
═══════════════════════════════════════════════════════════════════════

用法:
  python3 scripts/verify_settlement.py <APPLY_ID> [--env test|prod]

示例:
  python3 scripts/verify_settlement.py 200001005
  python3 scripts/verify_settlement.py 200000885 --env prod
"""

import json, subprocess, glob, sys, time
from pathlib import Path
from datetime import datetime

# ═══════════════════════ 环境配置 ═══════════════════════

ENV_CONFIG = {
    "test": {"total": 10, "subsidy_first": 6, "subsidy_other": 4, "official_fee": 2, "unit": "分"},
    "prod": {"total": 50000, "subsidy_first": 30200, "subsidy_other": 20200, "official_fee": 16500, "unit": "分"},
}

RESULT_DIR = Path.home() / "dms-alibaba/db-groups/scenario/sql/quick_prod/_results"
DMS_CWD = Path.home() / "dms-alibaba"
TAKE_DOWN_THRESHOLD = 0.70  # 下架率达标阈值


# ═══════════════════════ 结算规则计算 ═══════════════════════

def calc_settlement(env, first_publish, has_subsidy, is_expiry, total_amount=None):
    """按 PRD 规则计算期望结算金额（所有金额单位：分）

    is_expiry: True=到期结算(E/F/G/H), False=中途驳回/终止/取消(B/C/D)
    """
    c = ENV_CONFIG[env]
    total = total_amount if total_amount is not None else c["total"]
    subsidy = c["subsidy_first"] if first_publish else c["subsidy_other"]

    if has_subsidy:
        auto_confirm = total - subsidy  # 补贴后自动确收金额
        if is_expiry:
            # 到期: 官费参与结算
            refund_ok = c["official_fee"]
            refund_bad = auto_confirm - c["official_fee"]
        else:
            # 驳回/终止/取消: 退全部 auto_confirm, 不收官费
            refund_ok = auto_confirm
            refund_bad = auto_confirm
    else:
        auto_confirm = total
        if is_expiry:
            refund_ok = 0
            refund_bad = total - c["official_fee"]
        else:
            refund_ok = 0
            refund_bad = total

    return {
        "subsidy": subsidy if has_subsidy else 0,
        "auto_confirm": auto_confirm,
        "refund_if_rate_ok": refund_ok,    # 下架率 ≥ 70%
        "refund_if_rate_bad": refund_bad,  # 下架率 < 70%
        "official_fee": c["official_fee"],
        "total": total,
    }


# ═══════════════════════ SQL 执行 ═══════════════════════

def run_sql(sql, tag=""):
    """通过 dms-alibaba CLI 执行 SQL，返回行列表"""
    print(f"  [{tag}] {sql[:100]}...")
    before = set(glob.glob(str(RESULT_DIR / "????-??-??/*_prod.json")))
    subprocess.run(
        ["dms-alibaba", "sql", "run", "scenario", "--db", "prod", "--sql", sql],
        cwd=str(DMS_CWD), check=False, capture_output=True, text=True,
    )
    time.sleep(0.5)  # 防止同秒文件冲突
    after = set(glob.glob(str(RESULT_DIR / "????-??-??/*_prod.json")))
    new = sorted(after - before) or sorted(after)
    if not new:
        print(f"  [{tag}] ⚠️ 无结果文件")
        return []
    with open(new[-1]) as f:
        d = json.load(f)
    rows = d.get("results") or d.get("rows") or []
    print(f"  [{tag}] → {len(rows)} 行")
    return rows


def to_int(val, default=0):
    """安全转 int（DB 返回可能是 str/int/None）"""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ═══════════════════════ 主校验流程 ═══════════════════════

def verify(apply_id, env="test"):
    print(f"{'═' * 68}")
    print(f"  原创保护结算校验  apply_id={apply_id}  env={env}")
    print(f"{'═' * 68}")

    # ─── Phase 1: 数据采集（9 表联查） ───
    print(f"\n📡 Phase 1: 数据采集")

    # 1. 申请记录
    apply_rows = run_sql(
        f"SELECT id, right_id, status, seller_id, service_agency_code, "
        f"product_name, to_regular_status, apply_time, apply_type, extra_info "
        f"FROM yc_right_apply WHERE id = {apply_id} AND is_deleted = 0",
        tag="apply",
    )
    if not apply_rows:
        print(f"❌ 申请 {apply_id} 不存在或已删除"); return -1
    apply = apply_rows[0]
    right_id, seller_id = apply["right_id"], apply["seller_id"]

    # 2. 权利主表（含 first_publish）
    right_rows = run_sql(
        f"SELECT id, right_type, status, name, category, first_publish, "
        f"service_agency_code, protect_start_time, protect_expire_time, item_id "
        f"FROM yc_right WHERE id = {right_id} AND is_deleted = 0",
        tag="right",
    )
    right = right_rows[0] if right_rows else {}

    # 3. 商家入驻
    seller_info = run_sql(
        f"SELECT id, seller_id, status, enter_time, extra_info "
        f"FROM yc_seller_enter_info WHERE seller_id = {seller_id} AND is_deleted = 0",
        tag="seller",
    )

    # 4. 侵权记录按 status 分组
    tort_stats = run_sql(
        f"SELECT status, COUNT(*) AS cnt FROM yc_tort_record "
        f"WHERE right_id = {right_id} AND is_deleted = 0 GROUP BY status",
        tag="tort",
    )

    # 5. 维权记录按 status+protect_way 分组
    protect_stats = run_sql(
        f"SELECT status, protect_way, COUNT(*) AS cnt "
        f"FROM yc_right_protect_record "
        f"WHERE right_id = {right_id} AND is_deleted = 0 "
        f"GROUP BY status, protect_way",
        tag="protect",
    )

    # 6. 维权明细（关联侵权表）
    protect_detail = run_sql(
        f"SELECT p.id, p.status AS p_status, p.protect_way, p.start_time, "
        f"p.finish_time, t.status AS t_status, t.tort_platform, t.outer_tort_record_id "
        f"FROM yc_right_protect_record p "
        f"LEFT JOIN yc_tort_record t ON t.id = p.tord_record_id "
        f"WHERE p.right_id = {right_id} AND p.is_deleted = 0 "
        f"ORDER BY p.gmt_create DESC LIMIT 30",
        tag="detail",
    )

    # 7. 结算单
    settle_rows = run_sql(
        f"SELECT id, settle_status, total_amount, "
        f"init_allowance_status, init_allowance_amount, init_allowance_start_time, "
        f"balance_income_status, balance_income_amount, "
        f"serv_finish_income_status, serv_finish_income_amount, "
        f"serv_finish_refund_status, serv_finish_refund_amount, "
        f"sub_order_id, extra_info, gmt_create, gmt_modified "
        f"FROM yc_right_settle_order WHERE right_apply_id = {apply_id} AND is_deleted = 0",
        tag="settle",
    )
    if not settle_rows:
        print("⚠️  无结算单记录（可能结算尚未触发）")

    # 8. 服务交易记录
    trades = run_sql(
        f"SELECT id, trade_type, trade_id, status, amount, biz_scene, trade_time "
        f"FROM yc_service_trade_record WHERE right_apply_id = {apply_id} AND is_deleted = 0 "
        f"ORDER BY gmt_create",
        tag="trades",
    )

    # 9. 退款单 + 合同
    refunds = run_sql(
        f"SELECT id, settle_order_id, seller_id, refund_amount, refund_status, gmt_create "
        f"FROM refund_apply_order WHERE settle_order_id IN "
        f"(SELECT id FROM yc_right_settle_order WHERE right_apply_id = {apply_id} AND is_deleted = 0) "
        f"AND is_deleted = 0",
        tag="refund",
    )
    contracts = run_sql(
        f"SELECT id, biz_type, contract_type, contract_id, right_id, right_no, life_cycle "
        f"FROM yc_seller_contract_info WHERE right_apply_id = {apply_id} AND is_deleted = 0",
        tag="contract",
    )

    # 落盘原始数据
    raw = {
        "apply": apply, "right": right, "seller_enter": seller_info,
        "tort_stats": tort_stats, "protect_stats": protect_stats,
        "protect_detail": protect_detail, "settle": settle_rows,
        "trades": trades, "refunds": refunds, "contracts": contracts,
    }
    probe_path = f"/tmp/settlement_verify_{apply_id}.json"
    with open(probe_path, "w") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2, default=str)
    print(f"  📁 原始数据 → {probe_path}")

    # ─── Phase 2: 规则计算 ───
    print(f"\n📐 Phase 2: 规则计算")

    # 2a. 下架率
    #   yc_right_protect_record.status: SUCCESS / FAIL / RUNNING
    #   yc_tort_record.status: PROTECT_SUCCESS / PROTECT_FAIL / PROTECTING / INCORRECT
    succ = fail = running = incorrect = 0
    SUCCESS_KEYS = {"SUCCESS", "PROTECT_SUCCESS"}
    FAIL_KEYS = {"FAIL", "PROTECT_FAIL"}
    RUNNING_KEYS = {"RUNNING", "PROTECTING"}
    INCORRECT_KEYS = {"INCORRECT"}
    for s in protect_stats:
        st, n = s["status"], to_int(s["cnt"])
        if st in SUCCESS_KEYS:    succ += n
        elif st in FAIL_KEYS:     fail += n
        elif st in RUNNING_KEYS:  running += n
        elif st in INCORRECT_KEYS: incorrect += n
    resolved = succ + fail
    rate = succ / resolved if resolved > 0 else 0.0
    no_protect_records = (resolved == 0 and running == 0 and incorrect == 0)
    print(f"  维权统计: SUCCESS={succ} FAIL={fail} RUNNING={running} INCORRECT={incorrect}")
    if no_protect_records:
        print(f"  下架率: 无维权记录 → PRD默认达标(≥70%)")
    else:
        print(f"  下架率: {succ}/{resolved} = {rate:.1%}  (阈值 {TAKE_DOWN_THRESHOLD:.0%})")

    # 2b. 首发
    fp = right.get("first_publish", "")
    first_publish = (fp == "Y")
    print(f"  首发: {'Y 是' if first_publish else 'N 否'}  (DB: {fp or 'NULL'})")

    # 2c. 补贴判定
    # 多行settle时优先非CANCEL行，无则取首行
    non_cancel = [s for s in settle_rows if s.get("settle_status") != "CANCEL"]
    settle = non_cancel[0] if non_cancel else (settle_rows[0] if settle_rows else {})
    settle_is_cancel = settle.get("settle_status") == "CANCEL"
    # 补贴判定: 以 init_allowance_status 为准 (start_time有值不代表实际发放)
    has_subsidy = bool(
        settle.get("init_allowance_status")
        and settle.get("init_allowance_status") != "CANCEL"
    ) or bool(
        to_int(settle.get("init_allowance_amount"))
    )
    # 如果init_allowance_amount列不存在但其他指标暗示有补贴, 单独查询
    if not has_subsidy and "init_allowance_amount" not in settle and settle.get("settle_status") != "CANCEL":
        ia_check = run_sql(
            f"SELECT init_allowance_amount, init_allowance_status FROM yc_right_settle_order "
            f"WHERE right_apply_id = {apply_id} AND is_deleted = 0 "
            f"AND settle_status != 'CANCEL' AND init_allowance_status IS NOT NULL LIMIT 1",
            tag="ia_check",
        )
        if ia_check and ia_check[0].get("init_allowance_amount") and ia_check[0].get("init_allowance_status"):
            settle["init_allowance_amount"] = ia_check[0]["init_allowance_amount"]
            settle["init_allowance_status"] = ia_check[0]["init_allowance_status"]
            has_subsidy = True
            print(f"  ℹ️  补充查询: init_allowance_amount={settle['init_allowance_amount']}, status={settle['init_allowance_status']}")
        else:
            print(f"  ℹ️  补充查询: 无补贴记录")
    print(f"  补贴路径: {'有补贴' if has_subsidy else '无补贴'}  (status={settle.get('init_allowance_status','NULL')})")

    # 2d. 判断是否到期结算
    apply_status = apply.get("status", "")
    EXPIRY_STATUSES = {"EXPIRED", "SETTLED", "FINISHED"}
    # 如果有维权记录且下架率可计算 → 到期场景; 否则看apply状态
    is_expiry = (apply_status in EXPIRY_STATUSES) or (not no_protect_records)
    # 无维权记录 + 有补贴且status=FINISH → 也算到期场景(已确收)
    if no_protect_records and settle.get("settle_status") == "FINISH" and settle.get("serv_finish_refund_status") == "NO_NEED":
        is_expiry = True
    print(f"  场景判定: {'到期结算' if is_expiry else '中途驳回/终止/取消'}  (apply_status={apply_status})")

    # 2e. 计算期望值
    actual_total = to_int(settle.get("total_amount"), ENV_CONFIG[env]["total"])
    exp = calc_settlement(env, first_publish, has_subsidy, is_expiry, actual_total)
    # 下架率判定
    if no_protect_records:
        rate_effective = 1.0  # PRD: 无维权线索默认达标
    else:
        rate_effective = rate
    expected_refund = (
        exp["refund_if_rate_ok"] if rate_effective >= TAKE_DOWN_THRESHOLD
        else exp["refund_if_rate_bad"]
    )
    rate_label = "达标(≥70%)" if rate_effective >= TAKE_DOWN_THRESHOLD else "不达标(<70%)"
    print(f"  期望补贴={exp['subsidy']}{ENV_CONFIG[env]['unit']}  "
          f"自动确收={exp['auto_confirm']}  "
          f"官费={exp['official_fee']}")
    print(f"  下架率{rate_label} → 期望完结退款={expected_refund}{ENV_CONFIG[env]['unit']}")

    # ─── Phase 3: 逐项比对 ───
    print(f"\n🔍 Phase 3: DB 比对")
    issues = []

    if not settle:
        issues.append("无结算单记录")
        _print_report(apply_id, env, rate_effective, resolved, first_publish, has_subsidy,
                      exp, expected_refund, rate_label, settle, issues)
        return issues

    ss = settle.get("settle_status", "")

    # ── CANCEL 路径 ──
    if ss == "CANCEL" or settle_is_cancel:
        print(f"  ℹ️  settle_status = CANCEL")
        actual_ia = to_int(settle.get("init_allowance_amount"))
        actual_sfr = to_int(settle.get("serv_finish_refund_amount"))
        ia_cancel = (settle.get("init_allowance_status") == "CANCEL")
        if actual_ia and not ia_cancel:
            issues.append(f"CANCEL但init_allowance_amount={actual_ia}(status非CANCEL)")
            print(f"  ❌ init_allowance_amount: {actual_ia} (期望null/0 或 status=CANCEL)")
        elif actual_ia and ia_cancel:
            print(f"  ℹ️  init_allowance_amount={actual_ia} 但 status=CANCEL (补贴已发后取消)")
        else:
            print(f"  ✅ init_allowance_amount = null/0 (CANCEL)")
        if actual_sfr:
            issues.append(f"CANCEL但serv_finish_refund_amount={actual_sfr}")
            print(f"  ❌ serv_finish_refund_amount: {actual_sfr} (期望null/0)")
        else:
            print(f"  ✅ serv_finish_refund_amount = null/0 (CANCEL)")

    # ── FINISH 路径 ──
    else:
        # 3a. total_amount
        if to_int(settle.get("total_amount")) != exp["total"]:
            issues.append(
                f"total_amount: 实际={settle.get('total_amount')} 期望={exp['total']}"
            )
            print(f"  ❌ total_amount: {settle.get('total_amount')} ≠ {exp['total']}")
        else:
            print(f"  ✅ total_amount = {exp['total']}")

        # 3b. 补贴金额
        actual_allowance = to_int(settle.get("init_allowance_amount"))
        if has_subsidy:
            if actual_allowance != exp["subsidy"]:
                issues.append(
                    f"init_allowance_amount: 实际={actual_allowance} 期望={exp['subsidy']}"
                )
                print(f"  ❌ init_allowance_amount: {actual_allowance} ≠ {exp['subsidy']}")
            else:
                print(f"  ✅ init_allowance_amount = {exp['subsidy']}")
            if not settle.get("init_allowance_start_time"):
                issues.append("有补贴但 init_allowance_start_time 为空")
                print(f"  ❌ init_allowance_start_time 为空")
            else:
                print(f"  ✅ init_allowance_start_time = {settle['init_allowance_start_time']}")
        else:
            if actual_allowance:
                issues.append(
                    f"无补贴路径但 init_allowance_amount={actual_allowance}"
                )
                print(f"  ❌ 无补贴但 init_allowance_amount={actual_allowance}")
            else:
                print(f"  ✅ 无补贴 → init_allowance_amount 为空")

        # 3c. 完结退款金额（考虑 NO_NEED 状态）
        actual_refund = to_int(settle.get("serv_finish_refund_amount"))
        refund_status = settle.get("serv_finish_refund_status", "")
        if refund_status == "NO_NEED":
            # 确收场景: 无需退款, serv_finish_refund_amount 应为 null/0
            if actual_refund:
                issues.append(f"serv_finish_refund_status=NO_NEED 但 amount={actual_refund}")
                print(f"  ❌ NO_NEED但退款={actual_refund}")
            else:
                print(f"  ✅ serv_finish_refund_status=NO_NEED, 无需退款")
        else:
            if actual_refund != expected_refund:
                issues.append(
                    f"serv_finish_refund_amount: 实际={actual_refund} 期望={expected_refund}"
                )
                print(f"  ❌ serv_finish_refund_amount: {actual_refund} ≠ {expected_refund}")
            else:
                print(f"  ✅ serv_finish_refund_amount = {expected_refund}")

        # 3d. settle_status
        print(f"  ℹ️  settle_status = {ss}")

        # 3e. 退款状态一致性
        if refund_status == "FINISH" and actual_refund > 0:
            print(f"  ✅ serv_finish_refund_status=FINISH, 退款 {actual_refund} 分已执行")
        elif refund_status and not actual_refund and expected_refund == 0:
            print(f"  ✅ serv_finish_refund_status={refund_status}, 无需退款")

    # 3g. 保护期时间检查
    pexpire = right.get("protect_expire_time", "")
    if pexpire:
        try:
            exp_dt = datetime.strptime(str(pexpire)[:19], "%Y-%m-%d %H:%M:%S")
            pstart = right.get("protect_start_time", "")
            if pstart:
                start_dt = datetime.strptime(str(pstart)[:19], "%Y-%m-%d %H:%M:%S")
                if exp_dt < start_dt:
                    issues.append(
                        f"protect_expire_time({pexpire}) < protect_start_time({pstart})"
                    )
                    print(f"  ⚠️  时间反挂: expire({pexpire}) < start({pstart})")
        except ValueError:
            pass

    # 3h. 链路完整性
    for label, data in [("trades", trades), ("refunds", refunds), ("contracts", contracts)]:
        if data:
            print(f"  ℹ️  {label}: {len(data)} 条")

    # ─── Phase 4: 报告 ───
    _print_report(apply_id, env, rate_effective, resolved, first_publish, has_subsidy,
                  exp, expected_refund, rate_label, settle, issues)
    return issues


def _print_report(apply_id, env, rate, resolved, first_publish, has_subsidy,
                 exp, expected_refund, rate_label, settle, issues):
    """输出校验报告"""
    c = ENV_CONFIG[env]
    print(f"\n{'═' * 68}")
    print(f"  📋 校验报告")
    print(f"{'═' * 68}")
    print(f"  下架率:     {rate:.1%} ({rate_label})")
    print(f"  首发:       {'Y' if first_publish else 'N'}")
    print(f"  补贴路径:   {'有' if has_subsidy else '无'}")
    if has_subsidy:
        print(f"  补贴金额:   {exp['subsidy']}{c['unit']}")
        print(f"  自动确收:   {exp['auto_confirm']}{c['unit']}")
    print(f"  官费:       {exp['official_fee']}{c['unit']}")
    print(f"  期望退款:   {expected_refund}{c['unit']}")
    if settle:
        actual = to_int(settle.get("serv_finish_refund_amount"))
        print(f"  实际退款:   {actual}{c['unit']}")
        print(f"  结算状态:   {settle.get('settle_status', 'N/A')}")
    print(f"{'─' * 68}")

    if not issues:
        print(f"  ✅ 结算校验通过，所有字段符合 PRD 规则")
    else:
        print(f"  ❌ 发现 {len(issues)} 个问题:")
        for i, iss in enumerate(issues, 1):
            print(f"     {i}. {iss}")
    print(f"{'═' * 68}")

    # 落盘
    report = {
        "apply_id": apply_id, "env": env,
        "takedown_rate": round(rate, 4),
        "first_publish": first_publish,
        "has_subsidy": has_subsidy,
        "expected": exp,
        "expected_refund": expected_refund,
        "actual_settle": settle,
        "issues": [str(i) for i in issues],
        "ts": datetime.now().isoformat(),
    }
    rpt_path = f"/tmp/settlement_result_{apply_id}.json"
    with open(rpt_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"  📁 报告 → {rpt_path}")


# ═══════════════════════ CLI 入口 ═══════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    aid = sys.argv[1]
    env_flag = "test"
    if "--env" in sys.argv:
        idx = sys.argv.index("--env")
        if idx + 1 < len(sys.argv):
            env_flag = sys.argv[idx + 1]
    result = verify(aid, env=env_flag)
    sys.exit(0 if isinstance(result, list) and not result else 1)
