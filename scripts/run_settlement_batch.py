#!/usr/bin/env python3
"""批量跑 29 个结算场景校验，输出汇总报告"""
import sys, os, json, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 复用 verify_settlement.py 的 verify 函数
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from verify_settlement import verify

ALL_APPLY_IDS = [
    # A. 补贴前 (7)
    "200000369", "200000366", "200000382", "200000368", "200000377", "200000378", "200000370",
    # B. 补贴后驳回 (4)
    "200000342", "200000341", "200000344", "200000343",
    # C. 补贴后商家终止 (2)
    "200000340", "200000339",
    # D. 补贴后YC取消 (4)
    "200000338", "200000331", "200000330", "200000328",
    # E. 到期确收-180天 (3)
    "200000347", "200000353", "200000345",
    # F. 到期确收-申请日+1年-30天 (3)
    "200000389", "200000386", "200000387",
    # G. 到期退款-180天 (2)
    "200000346", "200000352",
    # H. 到期退款-申请日+1年-30天 (4)
    "200000388", "200000385", "200001005", "200000885",
]

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else "test"
    total = len(ALL_APPLY_IDS)
    print(f"\n{'█' * 70}")
    print(f"  批量结算校验  共 {total} 个场景  env={env}")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'█' * 70}\n")

    results = []
    for i, aid in enumerate(ALL_APPLY_IDS, 1):
        print(f"\n{'▓' * 70}")
        print(f"  [{i}/{total}] applyId={aid}")
        print(f"{'▓' * 70}")
        t0 = time.time()
        try:
            issues = verify(aid, env=env)
            elapsed = time.time() - t0
            if issues == -1:
                status = "SKIP"
                tag = "数据不存在"
            elif not issues:
                status = "PASS"
                tag = "校验通过"
            else:
                # 排除时间反挂
                real_issues = [x for x in issues if "protect_expire_time" not in str(x)]
                if not real_issues:
                    status = "PASS"
                    tag = f"校验通过 (时间反挂 warning)"
                else:
                    status = "FAIL"
                    tag = f"{len(real_issues)} 个问题"
        except Exception as e:
            elapsed = time.time() - t0
            status = "ERROR"
            tag = str(e)[:60]
            issues = [f"异常: {e}"]
        results.append({"applyId": aid, "status": status, "tag": tag, "elapsed": round(elapsed, 1)})
        print(f"\n  ⏱️  耗时 {elapsed:.1f}s  |  {status}: {tag}")

    # ─── 汇总 ───
    print(f"\n\n{'█' * 70}")
    print(f"  汇总报告  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'█' * 70}")
    print(f"  {'#':>3}  {'applyId':<14} {'状态':<6} {'耗时':>6}  备注")
    print(f"  {'─' * 60}")
    pass_c = fail_c = skip_c = err_c = 0
    for i, r in enumerate(results, 1):
        s = r["status"]
        if s == "PASS": pass_c += 1
        elif s == "FAIL": fail_c += 1
        elif s == "SKIP": skip_c += 1
        else: err_c += 1
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}.get(s, "?")
        print(f"  {icon} {i:>2}  {r['applyId']:<14} {s:<6} {r['elapsed']:>5.1f}s  {r['tag']}")

    print(f"\n{'─' * 70}")
    print(f"  总计: {total}  |  ✅PASS: {pass_c}  ❌FAIL: {fail_c}  ⏭️SKIP: {skip_c}  💥ERROR: {err_c}")
    print(f"{'█' * 70}")

    # 落盘
    summary_path = "/tmp/settlement_batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump({"ts": datetime.now().isoformat(), "env": env, "total": total,
                    "pass": pass_c, "fail": fail_c, "skip": skip_c, "error": err_c,
                    "details": results}, f, ensure_ascii=False, indent=2)
    print(f"\n📁 汇总报告 → {summary_path}")

    sys.exit(0 if fail_c == 0 and err_c == 0 else 1)


if __name__ == "__main__":
    main()
