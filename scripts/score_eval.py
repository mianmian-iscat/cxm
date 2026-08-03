"""
score_eval.py — 质量评分器

职责：
- 检查执行结果是否符合预期（output.schema.json）
- 对比 DOM 快照与预期状态
- 统计各维度质量指标：
    - step_pass_rate    步骤通过率
    - assert_pass_rate  断言通过率
    - capture_quality   抓包完整性（有响应体的比例）
    - screenshot_count  截图数量
    - has_error         是否有异常
- 输出综合评分（0~100）和失败原因

使用方式：
    python score_eval.py output.json [expected.json]
"""

import json
import sys
from typing import Optional


def score(output: dict, expected: Optional[dict] = None) -> dict:
    """
    对执行结果评分，返回评分报告。

    output: 符合 output.schema.json 的执行结果
    expected: 可选的预期结果（用于对比）
    """
    report = {
        "overall_score": 0,
        "status": output.get("status"),
        "dimensions": {},
        "issues": [],
        "passed": False,
    }

    steps = output.get("steps", [])
    total_steps = len(steps)

    # ── 维度 1：步骤通过率（权重 40%）──
    if total_steps > 0:
        passed_steps = sum(1 for s in steps if s.get("status") == "pass")
        step_pass_rate = passed_steps / total_steps
    else:
        step_pass_rate = 0.0
        report["issues"].append("无任何步骤执行记录")

    report["dimensions"]["step_pass_rate"] = round(step_pass_rate, 3)

    # ── 维度 2：断言通过率（权重 30%）──
    assert_steps = [s for s in steps if s.get("type") == "assert"]
    if assert_steps:
        assert_passed = sum(1 for s in assert_steps if s.get("assertResult", {}).get("pass"))
        assert_pass_rate = assert_passed / len(assert_steps)
        for s in assert_steps:
            if not s.get("assertResult", {}).get("pass"):
                report["issues"].append(
                    f"断言失败 step[{s['index']}]: 期望包含 \"{s['assertResult'].get('expected')}\""
                )
    else:
        assert_pass_rate = 1.0  # 无断言视为通过

    report["dimensions"]["assert_pass_rate"] = round(assert_pass_rate, 3)

    # ── 维度 3：抓包完整性（权重 20%）──
    requests = output.get("capture", {}).get("requests", [])
    if requests:
        with_body = sum(1 for r in requests if r.get("responseBody") is not None)
        capture_quality = with_body / len(requests)
    else:
        capture_quality = 1.0  # 无抓包配置视为不考核

    report["dimensions"]["capture_quality"] = round(capture_quality, 3)
    report["dimensions"]["capture_count"] = len(requests)

    # ── 维度 4：证据完整性（权重 10%）──
    screenshots = output.get("screenshots", [])
    has_error = output.get("status") == "error"
    has_error_screenshot = any(s.get("label", "").startswith("error") for s in screenshots)

    if has_error and not has_error_screenshot:
        report["issues"].append("执行异常但无错误截图")
        evidence_score = 0.5
    else:
        evidence_score = 1.0

    report["dimensions"]["screenshot_count"] = len(screenshots)
    report["dimensions"]["evidence_score"] = evidence_score

    # ── 异常扣分 ──
    if output.get("status") == "error":
        report["issues"].append(f"执行异常: {output.get('error', {}).get('message', '未知错误')}")
        deduction = 0.5  # 异常直接扣 50%
    else:
        deduction = 0.0

    # ── 综合评分 ──
    raw_score = (
        step_pass_rate * 0.40 +
        assert_pass_rate * 0.30 +
        capture_quality * 0.20 +
        evidence_score * 0.10
    ) * (1 - deduction)

    report["overall_score"] = round(raw_score * 100)
    report["passed"] = report["overall_score"] >= 80 and output.get("status") != "error"

    # ── 与预期对比（可选）──
    if expected:
        expected_status = expected.get("status")
        if expected_status and expected_status != output.get("status"):
            report["issues"].append(
                f"状态不符: 预期 {expected_status}，实际 {output.get('status')}"
            )
            report["passed"] = False

    return report


def print_report(report: dict):
    """打印人可读的评分报告"""
    icon = "✅" if report["passed"] else "❌"
    print(f"\n{icon} 综合评分: {report['overall_score']}/100  (状态: {report['status']})")
    print("\n各维度得分:")
    dims = report["dimensions"]
    print(f"  步骤通过率:   {dims.get('step_pass_rate', 0):.1%}")
    print(f"  断言通过率:   {dims.get('assert_pass_rate', 0):.1%}")
    print(f"  抓包完整性:   {dims.get('capture_quality', 0):.1%}  ({dims.get('capture_count', 0)} 条)")
    print(f"  证据完整性:   {dims.get('evidence_score', 0):.1%}  ({dims.get('screenshot_count', 0)} 张截图)")

    if report["issues"]:
        print("\n问题清单:")
        for issue in report["issues"]:
            print(f"  ⚠️  {issue}")


# CLI 使用
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python score_eval.py output.json [expected.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        output_data = json.load(f)

    expected_data = None
    if len(sys.argv) >= 3:
        with open(sys.argv[2], encoding="utf-8") as f:
            expected_data = json.load(f)

    result = score(output_data, expected_data)
    print_report(result)
    print(f"\n详细报告:\n{json.dumps(result, ensure_ascii=False, indent=2)}")
    sys.exit(0 if result["passed"] else 1)
