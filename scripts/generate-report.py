#!/usr/bin/env python3
"""
根据 output.json 生成钉钉图文混排测试报告
"""

import json
import sys
import os
from datetime import datetime

def generate_report(output_path, artifacts_dir):
    """生成测试报告"""
    
    with open(output_path, 'r', encoding='utf-8') as f:
        output = json.load(f)
    
    # 状态图标
    status_icon = '✅' if output['status'] == 'pass' else '❌'
    status_text = '通过' if output['status'] == 'pass' else '失败'
    
    # 计算通过步骤数
    passed_steps = sum(1 for s in output['steps'] if s['status'] == 'pass')
    total_steps = len(output['steps'])
    
    # 构建报告 Markdown
    report = f"""# {status_icon} 测试执行报告

## 📊 执行概况

| 项目 | 结果 |
|------|------|
| **测试 ID** | `{output['id']}` |
| **测试名称** | {output['name']} |
| **执行状态** | {status_icon} {status_text} |
| **执行耗时** | {output['duration']/1000:.1f}秒 |
| **步骤进度** | {passed_steps}/{total_steps} |

---

## 📝 执行步骤

"""
    
    # 添加步骤详情
    for step in output['steps']:
        step_icon = '✅' if step['status'] == 'pass' else '❌'
        step_type = step.get('type', 'unknown')
        step_desc = step.get('description', '-')
        step_duration = step.get('duration', 0)
        
        report += f"""### {step_icon} 步骤 {step['index']}: {step_type}

**{step_desc}** · 耗时 {step_duration}ms

"""
        
        # 如果有错误信息，添加到报告
        if 'error' in step:
            report += f"""⚠️ **错误**: `{step['error']}`

"""
    
    # 添加截图（最后一张结果截图）
    screenshots = output.get('screenshots', [])
    if screenshots:
        report += """---

## 📸 执行截图

"""
        # 找到最后一张非错误截图
        result_screenshot = None
        for shot in reversed(screenshots):
            if shot['stepIndex'] >= 0:
                result_screenshot = shot
                break
        
        if result_screenshot:
            # 使用绝对路径
            screenshot_path = result_screenshot['path']
            report += f"""![执行结果截图]({screenshot_path})

"""
    
    # 添加断言结果
    assertions = [s for s in output['steps'] if s['type'] == 'assert']
    if assertions:
        report += """---

## ✅ 断言结果

| 断言内容 | 预期值 | 实际结果 | 状态 |
|---------|--------|---------|------|
"""
        for assertion in assertions:
            desc = assertion.get('description', '-')
            assert_result = assertion.get('assertResult', {})
            expected = assert_result.get('expected', '-')
            actual = assert_result.get('actual', '-')
            passed = assert_result.get('pass', False)
            assert_icon = '✅' if passed else '❌'
            
            report += f"| {desc} | {expected} | {actual} | {assert_icon} |\n"
    
    # 添加结论
    report += f"""
---

## 🎯 结论

**{'✅ 测试通过，所有断言验证成功。' if output['status'] == 'pass' else '❌ 测试失败，请检查错误步骤。'}**

---

*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Asia/Shanghai)*
*产物目录：`{artifacts_dir}`*
"""
    
    return report


def find_result_screenshot(output_path):
    """找到最后一张结果截图的路径"""
    with open(output_path, 'r', encoding='utf-8') as f:
        output = json.load(f)
    
    screenshots = output.get('screenshots', [])
    for shot in reversed(screenshots):
        if shot['stepIndex'] >= 0:
            return shot['path']
    return None


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法：python generate-report.py <output.json 路径> [artifacts 目录]")
        sys.exit(1)
    
    output_path = sys.argv[1]
    artifacts_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(output_path)
    
    report = generate_report(output_path, artifacts_dir)
    print(report)
