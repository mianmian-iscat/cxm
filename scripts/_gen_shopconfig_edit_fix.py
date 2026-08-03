#!/usr/bin/env python3
"""
店铺信息配置-编辑表单交互用例补充
基于实际操作验证:
1. textarea编辑+字数计数器(15/100)
2. 100字截断限制(100/100)
3. sellerid自动带入名称("2219662018344"→"F88测试店铺")
4. 名称字段自动disabled
5. 关闭图标删除竞店行
"""
import json, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "eval" / "cases" / "f88-test"
CTX = {
    "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
    "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig",
    "waitAfterLoad": 3000, "auth": "buc",
    "captureFilter": "bzb.api.fsyx_quality_guard",
}
URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig"

def meta(id, name, desc, steps, pre="", notes="", risks=None, pri="P1"):
    ctx = dict(CTX)
    return {
        "id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": ctx, "steps": steps,
        "screenshot": {"onError": True},
        "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
        "_expected": {"status": "pass"},
        "_testDesign": {"preconditions": pre, "realDomNotes": notes, "riskPoints": risks or []}
    }

def w(path, data):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [OK] {p.name}")

# ── 1. textarea编辑+字数计数器 ──
w("atomic_f88_mc-edit-textarea.json", meta(
    "atomic-f88-mc-edit-textarea",
    "UI：店铺信息配置-编辑textarea字数计数器验证",
    "进入编辑表单，在视觉偏好textarea输入文本，验证字数计数器实时更新",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 4000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const ta = document.querySelector('textarea[placeholder*=\"室内\"]'); const counter = ta?.parentElement?.textContent?.match(/(\\d+)\\s*\\/\\s*(\\d+)/); return { foundTextarea: !!ta, counterBefore: counter ? counter[0] : 'not found' }; })()",
         "description": "查找视觉偏好-场景textarea", "storeAs": "taBefore"},
        {"type": "fill", "selector": "textarea[placeholder*='室内']", "value": "室内浅色棚拍背景，简约纯色风格", "react": True, "description": "输入场景偏好文本"},
        {"type": "wait", "ms": 500, "description": "等待计数器更新"},
        {"type": "evaluate",
         "expression": "(() => { const ta = document.querySelector('textarea[placeholder*=\"室内\"]'); const counter = ta?.parentElement?.textContent?.match(/(\\d+)\\s*\\/\\s*(\\d+)/); return { value: ta?.value || '', counterAfter: counter ? counter[0] : 'not found', currentCount: counter ? parseInt(counter[1]) : 0, maxCount: counter ? parseInt(counter[2]) : 0 }; })()",
         "description": "验证字数计数器更新", "storeAs": "taAfter"},
        {"type": "assertStore", "key": "taAfter", "path": "currentCount", "gt": 0, "description": "字数计数器大于0"},
        {"type": "assertStore", "key": "taAfter", "path": "maxCount", "equals": 100, "description": "最大字数为100"},
        {"type": "screenshot", "label": "mc-edit-textarea-counter", "description": "textarea字数计数器"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="实测: 输入'室内浅色棚拍背景，简约纯色风格'(15字) → 计数器'15 / 100'实时更新"
))

# ── 2. 100字截断限制 ──
w("atomic_f88_mc-edit-maxlen.json", meta(
    "atomic-f88-mc-edit-maxlen",
    "UI：店铺信息配置-textarea100字截断验证",
    "在textarea输入超过100字文本，验证自动截断到100字",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 4000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "fill", "selector": "textarea[placeholder*='统一亚洲']", "value": "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的文本内容用来测试一百个字的字数限制功能是否正常工作", "react": True, "description": "输入超过100字的文本"},
        {"type": "wait", "ms": 500, "description": "等待截断"},
        {"type": "evaluate",
         "expression": "(() => { const ta = document.querySelector('textarea[placeholder*=\"统一亚洲\"]'); const counter = ta?.parentElement?.textContent?.match(/(\\d+)\\s*\\/\\s*(\\d+)/); return { actualLength: ta?.value?.length || 0, counterText: counter ? counter[0] : 'not found', currentCount: counter ? parseInt(counter[1]) : 0, isTruncated: (ta?.value?.length || 0) <= 100 }; })()",
         "description": "验证文本被截断到100字", "storeAs": "maxLen"},
        {"type": "assertStore", "key": "maxLen", "path": "isTruncated", "equals": True, "description": "文本长度不超过100"},
        {"type": "assertStore", "key": "maxLen", "path": "currentCount", "equals": 100, "description": "计数器显示100"},
        {"type": "screenshot", "label": "mc-edit-maxlen-100", "description": "100字截断验证"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="实测: 输入超100字文本 → textarea自动截断到100字，计数器显示'100 / 100'"
))

# ── 3. sellerid自动带入名称 ──
w("atomic_f88_mc-competitor-autofill.json", meta(
    "atomic-f88-mc-competitor-autofill",
    "UI：店铺信息配置-参考竞店sellerid自动带入名称验证",
    "添加参考竞店后输入sellerid，验证名称自动带入且名称字段disabled",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 4000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const addBtn = Array.from(document.querySelectorAll('span,a,button')).find(el => el.textContent.trim() === '添加' && el.closest('main')); if(addBtn) { addBtn.click(); return 'added'; } return 'no add btn'; })()",
         "description": "点击添加参考竞店"},
        {"type": "wait", "ms": 1000, "description": "等待新行出现"},
        {"type": "evaluate",
         "expression": "(() => { const sidInput = document.querySelector('input[placeholder=\"请输入 sellerid\"]'); if(!sidInput) return {error: 'no sellerid input'}; const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; nativeSetter.call(sidInput, '2219662018344'); sidInput.dispatchEvent(new Event('input', {bubbles:true})); sidInput.dispatchEvent(new Event('change', {bubbles:true})); return {filled: true}; })()",
         "description": "输入sellerid触发自动带入", "storeAs": "sidFill"},
        {"type": "wait", "ms": 3000, "description": "等待API查询名称"},
        {"type": "evaluate",
         "expression": "(() => { const nameInput = document.querySelector('input[placeholder=\"输入 sellerid 后自动带入\"]'); return { autoFilledName: nameInput?.value || '', nameDisabled: nameInput?.disabled, nameHasValue: !!(nameInput?.value) }; })()",
         "description": "验证名称自动带入", "storeAs": "autoFill"},
        {"type": "assertStore", "key": "autoFill", "path": "nameHasValue", "equals": True, "description": "名称字段自动填入值"},
        {"type": "assertStore", "key": "autoFill", "path": "nameDisabled", "equals": True, "description": "名称字段自动disabled不可编辑"},
        {"type": "screenshot", "label": "mc-competitor-autofill", "description": "sellerid自动带入名称"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；sellerid=2219662018344对应'F88测试店铺'",
    notes="实测: 输入sellerid '2219662018344' → 名称自动带入'F88测试店铺'，名称input自动disabled"
))

print("\n✅ 编辑表单交互用例补充完成: 3条新增")
print("  - mc-edit-textarea: textarea字数计数器")
print("  - mc-edit-maxlen: 100字截断限制")
print("  - mc-competitor-autofill: sellerid自动带入名称")
