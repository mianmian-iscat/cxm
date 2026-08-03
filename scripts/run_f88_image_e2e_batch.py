#!/usr/bin/env python3
"""批量执行 F88 图片审核 9 按钮 e2e 用例"""
import asyncio, json, os, sys, glob, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from impl import run_test

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "eval", "cases", "f88-test")
E2E_PATTERN = os.path.join(CASE_DIR, "e2e_f88_image_action_*.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")


async def run_one(case_path: str) -> dict:
    """执行单个 e2e 用例"""
    case_name = os.path.basename(case_path)
    print(f"\n{'='*60}")
    print(f"▶ 执行: {case_name}")
    print(f"{'='*60}")

    with open(case_path) as f:
        case_data = json.load(f)

    t0 = time.time()
    try:
        result = await asyncio.wait_for(
            run_test(case_data),
            timeout=120  # 每个用例最多 120 秒
        )
        elapsed = time.time() - t0
        status = result.get("status", "unknown")
        icon = "✅" if status in ("pass", "done") else "❌" if status in ("error", "fail") else "⚠️"
        print(f"  {icon} 状态: {status} | 耗时: {elapsed:.1f}s")

        # 断言统计
        asserts = result.get("assertions", {})
        if asserts:
            total = asserts.get("total", 0)
            passed = asserts.get("passed", 0)
            print(f"  📊 断言: {passed}/{total} 通过")

        return {
            "case": case_name,
            "id": case_data.get("id", ""),
            "name": case_data.get("name", ""),
            "status": status,
            "elapsed": round(elapsed, 1),
            "assertions": asserts,
            "error": result.get("error", ""),
        }
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  ⏱️ 超时 ({elapsed:.1f}s)")
        return {"case": case_name, "id": case_data.get("id", ""), "name": case_data.get("name", ""),
                "status": "timeout", "elapsed": round(elapsed, 1), "error": "执行超时120s"}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ 异常: {e}")
        return {"case": case_name, "id": case_data.get("id", ""), "name": case_data.get("name", ""),
                "status": "error", "elapsed": round(elapsed, 1), "error": str(e)}


async def main():
    cases = sorted(glob.glob(E2E_PATTERN))
    print(f"📋 图片审核 9 按钮 e2e 用例批量执行")
    print(f"📁 用例目录: {CASE_DIR}")
    print(f"🔢 用例数量: {len(cases)}")
    for c in cases:
        print(f"   - {os.path.basename(c)}")

    results = []
    for case_path in cases:
        result = await run_one(case_path)
        results.append(result)

    # 汇总
    print(f"\n{'='*60}")
    print(f"📊 批量执行汇总")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r["status"] in ("pass", "done"))
    failed = sum(1 for r in results if r["status"] in ("error", "fail", "timeout"))
    skipped = len(results) - passed - failed
    print(f"总计: {len(results)} | ✅ pass: {passed} | ❌ fail: {failed} | ⏭ skip: {skipped}")
    for r in results:
        icon = "✅" if r["status"] in ("pass", "done") else "❌" if r["status"] in ("error", "fail", "timeout") else "⏭"
        err_msg = r.get("error", "")
        if isinstance(err_msg, dict):
            err_msg = str(err_msg.get("message", ""))
        err = f" ({str(err_msg)[:60]})" if err_msg else ""
        print(f"  {icon} {r['case']} [{r['status']}] {r['elapsed']}s{err}")

    # 写结果
    output_path = os.path.join(OUTPUT_DIR, "f88-image-e2e-results.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"summary": {"total": len(results), "passed": passed, "failed": failed, "skipped": skipped},
                    "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\n📁 结果已保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
