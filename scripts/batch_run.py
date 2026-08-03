#!/usr/bin/env python3
"""batch_run.py — 批量执行 eval 用例并收集结果

Usage:
  python3 scripts/batch_run.py f88-test         # 执行 f88-test 域全部用例
  python3 scripts/batch_run.py op-test           # 执行 op-test 域全部用例  
  python3 scripts/batch_run.py --subdir "审核管理"  # 只执行指定子目录
  python3 scripts/batch_run.py --limit 10        # 只执行前10个
"""
import json, os, glob, sys, subprocess, time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE, "eval", "cases")
RESULTS_DIR = os.path.join(BASE, "artifacts")
IMPL = os.path.join(BASE, "impl.py")

def run_case(filepath, timeout=90):
    """执行单个用例，返回结果"""
    out_path = os.path.join(RESULTS_DIR, "_batch_tmp.json")
    start = time.time()
    try:
        result = subprocess.run(
            ["python3", IMPL, filepath, out_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=BASE
        )
        elapsed = round(time.time() - start, 1)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # 解析结果
        status = "unknown"
        steps_info = ""
        if "测试用例 通过" in stdout or "✅" in stdout:
            status = "pass"
        elif "测试用例 error" in stdout or "❌" in stdout:
            status = "fail"
        elif result.returncode != 0:
            status = "error"
        elif "超时" in stderr or "timeout" in stderr.lower():
            status = "timeout"

        # 提取步骤信息
        for line in stdout.split("\n"):
            if "步骤：" in line or "步骤:" in line:
                steps_info = line.strip()
                break
            if "错误" in line or "Error" in line:
                steps_info = line.strip()[:100]
                break

        return {
            "status": status,
            "elapsed": elapsed,
            "steps": steps_info,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        return {"status": "timeout", "elapsed": elapsed, "steps": "timeout", "returncode": -1}
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"status": "error", "elapsed": elapsed, "steps": str(e)[:100], "returncode": -1}


def main():
    domain = None
    subdir_filter = None
    limit = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--subdir" and i + 1 < len(args):
            subdir_filter = args[i + 1]
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif not args[i].startswith("--"):
            domain = args[i]
            i += 1
        else:
            i += 1

    if not domain:
        print("Usage: python3 scripts/batch_run.py <domain> [--subdir <name>] [--limit N]")
        sys.exit(1)

    # 收集用例文件
    pattern = os.path.join(CASES_DIR, domain, "**/*.json")
    files = sorted(glob.glob(pattern, recursive=True))

    if subdir_filter:
        files = [f for f in files if subdir_filter in f]

    if limit:
        files = files[:limit]

    print(f"批量执行 {domain}: {len(files)} 个用例")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    pass_count = 0
    fail_count = 0
    error_count = 0
    timeout_count = 0

    for idx, filepath in enumerate(files):
        rel = os.path.relpath(filepath, CASES_DIR)
        short = os.path.basename(filepath).replace(".json", "")

        sys.stdout.write(f"[{idx+1}/{len(files)}] {short[:50]}... ")
        sys.stdout.flush()

        r = run_case(filepath)
        r["file"] = rel
        r["name"] = short
        results.append(r)

        status_emoji = {"pass": "✅", "fail": "❌", "error": "💥", "timeout": "⏰"}.get(r["status"], "❓")
        print(f"{status_emoji} {r['status']} ({r['elapsed']}s) {r['steps'][:40]}")

        if r["status"] == "pass":
            pass_count += 1
        elif r["status"] == "fail":
            fail_count += 1
        elif r["status"] == "error":
            error_count += 1
        elif r["status"] == "timeout":
            timeout_count += 1

    # 写结果
    summary = {
        "domain": domain,
        "subdir_filter": subdir_filter,
        "total": len(files),
        "pass": pass_count,
        "fail": fail_count,
        "error": error_count,
        "timeout": timeout_count,
        "pass_rate": round(pass_count * 100 / len(files), 1) if files else 0,
        "total_elapsed": round(sum(r["elapsed"] for r in results), 1),
        "timestamp": datetime.now().isoformat(),
        "results": results
    }

    out_file = os.path.join(RESULTS_DIR, f"batch-{domain}-results.json")
    if subdir_filter:
        out_file = os.path.join(RESULTS_DIR, f"batch-{domain}-{subdir_filter}-results.json")

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总计: {len(files)} | ✅通过: {pass_count} | ❌失败: {fail_count} | 💥错误: {error_count} | ⏰超时: {timeout_count}")
    print(f"通过率: {summary['pass_rate']}%")
    print(f"总耗时: {summary['total_elapsed']}s ({summary['total_elapsed']/60:.1f}min)")
    print(f"结果文件: {out_file}")


if __name__ == "__main__":
    main()
