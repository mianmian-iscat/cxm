#!/usr/bin/env python3
"""批量增强 F88 骨架测试用例:
1. SPA wait 3s→6s + 稳定性检查
2. evaluate 表达式加 return 前缀
3. evaluate 后自动追加 assertStore 断言
4. 按钮/输入类用例追加交互验证步骤
"""
import json, os, sys, copy

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'eval', 'cases', 'f88-test')

STABILITY_CHECK = {
    "type": "evaluate",
    "expression": "return (() => { return { url: window.location.href, bodyLen: (document.body?.innerText || '').length }; })()",
    "description": "验证页面已稳定加载"
}

def fix_return_prefix(expr):
    """给 IIFE 表达式加 return 前缀"""
    if not expr:
        return expr
    expr = expr.strip()
    if expr.startswith('(()') and not expr.startswith('return'):
        return 'return ' + expr
    return expr

def make_assert_store(eval_step):
    """根据 evaluate 步骤生成 assertStore"""
    store_as = eval_step.get('storeAs')
    if not store_as:
        return None
    
    # 分析表达式中可能的返回字段
    expr = eval_step.get('expression', '')
    
    # 通用断言: store 不为空
    return {
        "type": "assertStore",
        "key": store_as,
        "path": "found",
        "equals": True,
        "description": f"验证 {eval_step.get('description', store_as)} 存在"
    }

def make_interaction_steps(eval_step, case_name):
    """根据用例类型生成交互验证步骤"""
    steps = []
    store_as = eval_step.get('storeAs', '')
    desc = (eval_step.get('description', '') + ' ' + case_name).lower()
    
    # 按钮类用例: 点击按钮 → 验证弹窗/状态变化
    if 'btn' in desc or '按钮' in desc or 'button' in desc:
        btn_text = ''
        if '编辑' in desc or 'edit' in desc:
            btn_text = '编辑'
        elif '保存' in desc or 'save' in desc:
            btn_text = '保 存'
        elif '试运行' in desc or 'trial' in desc:
            btn_text = '试运行'
        elif '新增' in desc or '创建' in desc or 'create' in desc or 'add' in desc:
            btn_text = '新增'
        elif '复制' in desc or 'copy' in desc:
            btn_text = '复制'
        elif '重置' in desc or 'reset' in desc:
            btn_text = '重置'
        elif '返回' in desc or 'back' in desc:
            btn_text = '返回'
        elif '下载' in desc or 'download' in desc:
            btn_text = '下载'
        elif '批量' in desc or 'batch' in desc:
            btn_text = '批量'
        
        if btn_text:
            steps.append({
                "type": "clickText",
                "text": btn_text,
                "description": f"点击{btn_text}按钮"
            })
            steps.append({
                "type": "wait",
                "ms": 2000,
                "description": "等待操作响应"
            })
            steps.append({
                "type": "screenshot",
                "label": f"after-click-{store_as or 'action'}",
                "description": f"点击{btn_text}后截图"
            })
    
    # 输入框类用例: 输入内容 → 验证输入生效
    elif 'input' in desc or '输入' in desc or '搜索' in desc or 'search' in desc:
        steps.append({
            "type": "evaluate",
            "expression": "return (() => { const inputs = Array.from(document.querySelectorAll('input[type=text], input:not([type])')).filter(i => i.offsetParent !== null); if (inputs.length === 0) return { filled: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(inputs[0], 'test_input_001'); inputs[0].dispatchEvent(new Event('input', {bubbles:true})); inputs[0].dispatchEvent(new Event('change', {bubbles:true})); return { filled: true, value: inputs[0].value }; })()",
            "description": "填入测试值验证输入框",
            "storeAs": f"{store_as or 'input'}Fill"
        })
    
    # 表格/列表头类用例: 检查列数/行数
    elif 'header' in desc or '列' in desc or 'table' in desc or '表头' in desc:
        steps.append({
            "type": "evaluate",
            "expression": "return (() => { const ths = Array.from(document.querySelectorAll('th, .ant-table-thead th')); return { columnCount: ths.length, headers: ths.slice(0, 15).map(th => (th.textContent || '').trim()) }; })()",
            "description": "检查表格列信息",
            "storeAs": f"{store_as or 'table'}Info"
        })
    
    # 指标卡/数值类: 检查数值格式
    elif '指标' in desc or '任务数' in desc or '进度' in desc or 'metric' in desc or 'count' in desc or 'card' in desc:
        steps.append({
            "type": "evaluate",
            "expression": "return (() => { const cards = Array.from(document.querySelectorAll('.ant-statistic, .ant-card, [class*=statistic], [class*=metric], [class*=card]')); return { cardCount: cards.length, values: cards.slice(0, 8).map(c => (c.textContent || '').trim().substring(0, 50)) }; })()",
            "description": "检查指标卡数值",
            "storeAs": f"{store_as or 'metric'}Values"
        })
    
    return steps

def enhance_case(path):
    """增强单个骨架用例"""
    with open(path, 'r') as f:
        case = json.load(f)
    
    steps = case.get('steps', [])
    if len(steps) > 5 or len(steps) <= 2:
        return False
    
    new_steps = []
    page_assert_added = False
    url = case.get('context', {}).get('url', '')
    
    # 根据 URL 决定页面断言关键字
    if 'productionDashboard' in url:
        page_kw = '生产'
    elif 'linkList' in url or '/link' in url:
        page_kw = '链路'
    elif 'templateLibrary' in url or 'template' in url:
        page_kw = '模版'
    elif 'shopConfig' in url or 'merchant' in url:
        page_kw = '商家'
    elif 'review' in url or 'audit' in url or 'standard' in url or 'node-management' in url:
        page_kw = '审核'
    elif 'strategy' in url and 'detail' in url:
        page_kw = '策略'
    elif 'list' in url:
        page_kw = '列表'
    else:
        page_kw = 'F88'
    
    for i, step in enumerate(steps):
        stype = step.get('type', '')
        next_step = steps[i+1] if i+1 < len(steps) else None
        
        # 1. 增强 wait 步骤
        if stype == 'wait' and step.get('ms', 0) <= 3000:
            step = dict(step)
            step['ms'] = 6000
            step['description'] = '等待SPA加载完成'
            new_steps.append(step)
            new_steps.append(dict(STABILITY_CHECK))
            continue
        
        # 2. 修复 evaluate return 前缀
        if stype == 'evaluate':
            step = dict(step)
            expr = step.get('expression', '')
            step['expression'] = fix_return_prefix(expr)
            new_steps.append(step)
            
            # 3. 追加 assertStore
            if step.get('storeAs'):
                assert_step = make_assert_store(step)
                if assert_step:
                    new_steps.append(assert_step)
            
            # 4. 追加分页稳定性断言（仅一次，且下一个step不是assert）
            if not page_assert_added and (not next_step or next_step.get('type') != 'assert'):
                new_steps.append({
                    "type": "assert",
                    "target": "page",
                    "contains": page_kw,
                    "description": "验证页面已加载"
                })
                page_assert_added = True
            continue
        
        # 5. 增强 screenshot 步骤: 追加交互验证
        if stype == 'screenshot' and i == len(steps) - 1:
            # 在最终截图前插入交互验证步骤
            interaction_steps = make_interaction_steps(
                steps[i-1] if i > 0 else step,
                case.get('name', '')
            )
            for ist in interaction_steps:
                new_steps.append(ist)
        
        new_steps.append(step)
    
    case['steps'] = new_steps
    
    with open(path, 'w') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    
    return True

def main():
    enhanced = 0
    skipped = 0
    
    for root, dirs, files in os.walk(BASE):
        for f in sorted(files):
            if not f.endswith('.json'):
                continue
            path = os.path.join(root, f)
            try:
                d = json.load(open(path))
                steps = d.get('steps', [])
                if 2 < len(steps) <= 5:
                    if enhance_case(path):
                        enhanced += 1
                        rel = path.replace(BASE + '/', '')
                        print(f'  ✅ {rel}')
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f'  ❌ {path}: {e}')
                skipped += 1
    
    print(f'\n增强完成: {enhanced} 条用例已增强, {skipped} 条跳过')

if __name__ == '__main__':
    main()
