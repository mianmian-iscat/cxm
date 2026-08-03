import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

# Common step templates based on actual UI behavior
COMMON_HEAD = [
    {"type": "navigate", "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center",
     "waitUntil": "networkidle", "screenshot": True, "description": "打开个人任务中心"},
    {"type": "wait", "ms": 3000, "description": "等待任务列表"},
    {"type": "selectOption", "label": "审核状态", "option": "待审核", "description": "筛选待审核任务"},
    {"type": "wait", "ms": 2000, "description": "等待筛选结果"},
    {"type": "evaluate",
     "expression": "(() => { const rows = Array.from(document.querySelectorAll('.ant-table-row, tr[data-row-key]')); const row = rows[0]; return row ? { taskId: row.getAttribute('data-row-key') } : null; })()",
     "storeAs": "firstTask", "description": "读取首行任务ID"},
    {"type": "clickText", "text": "审核", "description": "打开第一条待审核任务"},
    {"type": "wait", "ms": 2500, "description": "等待审核详情Drawer打开"},
    {"type": "evaluate",
     "expression": "(() => { const imgs = Array.from(document.querySelectorAll('img')).filter(i => i.src && i.src.includes('scene-ossgw') && i.getBoundingClientRect().width > 100); const materialImg = imgs.find(i => i.src.includes('/llm/')); return materialImg ? { originUrl: materialImg.src.substring(0, 120) } : null; })()",
     "storeAs": "originImage", "description": "记录原始图片URL(llm路径)"},
    {"type": "evaluate",
     "expression": "(() => { const cb = document.querySelector('[class*=MaterialSlider] input[type=checkbox]'); if(cb && !cb.checked) cb.click(); return 'checked'; })()",
     "description": "勾选素材图(如未勾选)"}
]

def make_toolbar_click(aria_label, desc):
    return {"type": "evaluate",
     "expression": f'(async () => {{ await page.mouse.move(900, 350); await page.waitForTimeout(1000); const icon = await page.locator(\'[aria-label="{aria_label}"]\').last(); const box = await icon.boundingBox(); if(box) {{ await page.mouse.click(box.x+box.width/2, box.y+box.height/2); return \'clicked {aria_label}\'; }} return \'not found\'; }})()',
     "description": desc}

def make_post_edit_verify(action_name):
    return [
        {"type": "wait", "ms": 3000, "description": f"等待{action_name}结果渲染"},
        {"type": "evaluate",
         "expression": "(() => { const radios = Array.from(document.querySelectorAll('[role=radio], input[type=radio]')); const labels = radios.map(r => ({label: r.parentElement?.textContent?.trim()?.substring(0,10), checked: r.checked || r.getAttribute('aria-checked')==='true'})); const editedImg = Array.from(document.querySelectorAll('img')).find(i => i.src && i.src.includes('/localUpload/')); return { hasToggle: radios.length >= 2, labels, editedUrl: editedImg ? editedImg.src.substring(0, 120) : null }; })()",
         "storeAs": "editResult", "description": f"验证编辑前/后切换及{action_name}后URL(localUpload路径)"},
        {"type": "assertStore", "key": "editResult", "path": "editedUrl", "notEmpty": True,
         "description": f"断言{action_name}后URL存在(localUpload路径)"},
        {"type": "assertStore", "key": "editResult", "path": "hasToggle", "equals": "true",
         "description": "断言编辑前/后切换存在"}
    ]

def make_post_confirm_verify(action_name):
    return [
        {"_comment": f"========== postConfirmVerify: 确认CopyURL/下载得到的是{action_name}后数据 ==========", "type": "noop"},
        {"type": "evaluate",
         "expression": "(() => { const imgs = Array.from(document.querySelectorAll('img')).filter(i => i.src && i.src.includes('scene-ossgw')); const img = imgs.find(i => i.getBoundingClientRect().width > 100); return img ? { currentUrl: img.src.substring(0, 120) } : null; })()",
         "storeAs": "afterEdit", "description": f"【postConfirmVerify】获取{action_name}后图片URL"},
        {"type": "assert", "target": "store.afterEdit.currentUrl", "notEquals": "${store.originImage.originUrl}",
         "description": f"【postConfirmVerify-CopyURL】{action_name}后图片URL必须≠原始URL"},
        {"type": "clickText", "text": "复制", "description": f"【postConfirmVerify-CopyURL】点击复制URL按钮"},
        {"type": "wait", "ms": 1000, "description": "等待复制操作完成"},
        {"type": "clickText", "text": "下载", "description": f"【postConfirmVerify-下载】点击下载按钮"},
        {"type": "wait", "ms": 3000, "description": "等待下载完成"},
        {"type": "screenshot", "label": f"f88-{action_name}-postconfirm-verify", "description": f"截图-{action_name}确认后CopyURL/下载验证"}
    ]

def make_confirm_and_api(action_name, api_pattern):
    return [
        {"type": "evaluate",
         "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*认/.test(b.textContent) && b.className && b.className.includes('primary')); if(btn){btn.click();return 'clicked confirm';} return 'no btn'; })()",
         "description": "点击顶部工具栏'确认'按钮完成审核"},
        {"type": "waitForAPI", "urlPattern": api_pattern, "timeout": 15000, "description": "等待审核通过API"},
        {"type": "wait", "ms": 3000, "description": "等待自动流转下一任务"}
    ]

TAIL = [
    {"type": "apiCall", "api": "bzb.api.fsyx_quality_guard.f88.queryMaterialAuditDetail",
     "v": "1.0", "data": {"taskId": "${store.firstTask.taskId}"}, "storeAs": "auditDetail",
     "description": "调用审核详情API"},
    {"type": "assert", "target": "api", "path": "data.data.auditStatus", "equals": "APPROVED",
     "description": "API断言审核状态为已通过"},
    {"type": "dbQuery",
     "sql": "SELECT id, url, local_adjust_url, status FROM material WHERE task_id = '${store.firstTask.taskId}' ORDER BY id DESC LIMIT 1",
     "storeAs": "materialDb", "description": "DB查询素材记录"},
    {"type": "assertDbResult",
     "expectations": [{"field": "status", "equals": "APPROVED"}, {"field": "url", "notEmpty": True}, {"field": "local_adjust_url", "notEmpty": True}],
     "description": "DB断言状态与URL字段"}
]

# ---- Case 1: Replace ----
replace_steps = list(COMMON_HEAD)
replace_steps.append(make_toolbar_click("replace", "hover主图→点击replace图标打开替换"))
replace_steps.append({"type": "wait", "ms": 1500, "description": "等待替换文件选择器"})
replace_steps.append({"type": "upload", "filePath": "test-fixtures/images/sample.png", "description": "上传替换图片"})
replace_steps.append({"type": "wait", "ms": 2000, "description": "等待上传完成"})
replace_steps.append({"type": "evaluate",
    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定/.test(b.textContent) && !b.disabled); if(btn){btn.click();return 'clicked';} return 'no btn'; })()",
    "description": "点击确定提交替换"})
replace_steps.append({"type": "waitForAPI", "urlPattern": "submitLocalAdjust|replaceMaterial|material/write",
    "timeout": 15000, "description": "等待替换提交API"})
replace_steps.extend(make_post_edit_verify("替换"))
replace_steps.extend(make_post_confirm_verify("替换"))
replace_steps.extend(make_confirm_and_api("替换", "approveMaterial|audit/approve|confirm"))
replace_steps.extend(TAIL)
replace_steps.append({"type": "screenshot", "label": "f88-replace-e2e-done", "description": "截图-替换端到端完成"})

replace_case = {
    "id": "e2e-f88-image-action-replace",
    "name": "端到端：F88 图片替换 → 确认 → URL/状态一致性校验",
    "description": "进入图片审核详情，勾选素材→hover主图→点击replace图标→上传新图片→确定→验证编辑前/后切换及URL变化→CopyURL/下载验证→点击确认完成审核→自动流转下一任务。",
    "businessType": "f88_material_audit", "scene": "f88-test", "priority": "P0", "category": "e2e_flow",
    "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
        "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center",
        "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
    "steps": replace_steps,
    "screenshot": {"onError": True},
    "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
    "_expected": {"status": "pass"},
    "_testDesign": {"preconditions": "F88预发已登录；存在待审核图片任务；test-fixtures/images/sample.png存在。",
        "realDomNotes": "replace图标打开文件选择器→上传→确定→编辑前/后Radio切换→确认→自动流转。URL从llm/变为localUpload/。",
        "riskPoints": ["无待审核任务时无法进入详情", "上传文件路径需存在", "replace图标需hover主图才出现"]}
}

# ---- Case 2: Crop ----
crop_steps = list(COMMON_HEAD)
crop_steps.append(make_toolbar_click("crop", "hover主图→点击crop图标打开裁剪面板"))
crop_steps.append({"type": "wait", "ms": 2000, "description": "等待裁剪面板"})
crop_steps.append({"type": "evaluate",
    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定/.test(b.textContent) && !b.disabled); if(btn){btn.click();return 'clicked';} return 'no btn'; })()",
    "description": "点击确定提交裁剪"})
crop_steps.append({"type": "waitForAPI", "urlPattern": "submitLocalAdjust|material/write|crop",
    "timeout": 15000, "description": "等待裁剪提交API"})
crop_steps.extend(make_post_edit_verify("裁剪"))
crop_steps.extend(make_post_confirm_verify("裁剪"))
crop_steps.extend(make_confirm_and_api("裁剪", "approveMaterial|audit/approve|confirm"))
crop_steps.extend(TAIL)
crop_steps.append({"type": "screenshot", "label": "f88-crop-e2e-done", "description": "截图-裁剪端到端完成"})

crop_case = {
    "id": "e2e-f88-image-action-crop",
    "name": "端到端：F88 图片裁剪 → 确认 → URL/状态一致性校验",
    "description": "进入图片审核详情，勾选素材→hover主图→点击crop图标→裁剪面板→确定→验证编辑前/后切换及URL变化→CopyURL/下载验证→点击确认完成审核→自动流转下一任务。",
    "businessType": "f88_material_audit", "scene": "f88-test", "priority": "P0", "category": "e2e_flow",
    "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
        "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center",
        "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
    "steps": crop_steps,
    "screenshot": {"onError": True},
    "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
    "_expected": {"status": "pass"},
    "_testDesign": {"preconditions": "F88预发已登录；存在待审核图片任务。",
        "realDomNotes": "crop图标打开裁剪面板→确定→编辑前/后Radio切换→确认→自动流转。URL从llm/变为localUpload/。",
        "riskPoints": ["无待审核任务时无法进入详情", "crop图标需hover主图才出现", "裁剪面板可能有比例选择"]}
}

# ---- Case 3: HD Enhance ----
hd_steps = list(COMMON_HEAD)
hd_steps.append(make_toolbar_click("hd", "hover主图→点击hd图标触发高清化"))
hd_steps.append({"type": "wait", "ms": 3000, "description": "等待高清化处理"})
hd_steps.append({"type": "evaluate",
    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定/.test(b.textContent) && !b.disabled); if(btn){btn.click();return 'clicked';} return 'no btn'; })()",
    "description": "点击确定提交高清化"})
hd_steps.append({"type": "waitForAPI", "urlPattern": "submitLocalAdjust|material/write|hdEnhance",
    "timeout": 20000, "description": "等待高清化提交API"})
hd_steps.extend(make_post_edit_verify("高清化"))
hd_steps.extend(make_post_confirm_verify("高清化"))
hd_steps.extend(make_confirm_and_api("高清化", "approveMaterial|audit/approve|confirm"))
hd_steps.extend(TAIL)
hd_steps.append({"type": "screenshot", "label": "f88-hd-e2e-done", "description": "截图-高清化端到端完成"})

hd_case = {
    "id": "e2e-f88-image-action-hd-enhance",
    "name": "端到端：F88 图片高清化 → 确认 → URL/状态一致性校验",
    "description": "进入图片审核详情，勾选素材→hover主图→点击hd图标→高清化处理→确定→验证编辑前/后切换及URL变化→CopyURL/下载验证→点击确认完成审核→自动流转下一任务。",
    "businessType": "f88_material_audit", "scene": "f88-test", "priority": "P0", "category": "e2e_flow",
    "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
        "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center",
        "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
    "steps": hd_steps,
    "screenshot": {"onError": True},
    "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
    "_expected": {"status": "pass"},
    "_testDesign": {"preconditions": "F88预发已登录；存在待审核图片任务。",
        "realDomNotes": "hd图标触发高清化处理→确定→编辑前/后Radio切换→确认→自动流转。URL从llm/变为localUpload/。高清化可能异步处理较慢。",
        "riskPoints": ["无待审核任务时无法进入详情", "hd图标需hover主图才出现", "高清化可能异步处理较慢"]}
}

# ---- Case 4: Remove BG ----
bg_steps = list(COMMON_HEAD)
bg_steps.append(make_toolbar_click("cut", "hover主图→点击cut图标触发去背景"))
bg_steps.append({"type": "wait", "ms": 2000, "description": "等待去背景处理"})
bg_steps.append({"type": "evaluate",
    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定/.test(b.textContent) && !b.disabled); if(btn){btn.click();return 'clicked';} return 'no btn'; })()",
    "description": "点击确定提交去背景"})
bg_steps.append({"type": "waitForAPI", "urlPattern": "submitLocalAdjust|material/write|removeBg",
    "timeout": 15000, "description": "等待去背景提交API"})
bg_steps.extend(make_post_edit_verify("去背景"))
bg_steps.extend(make_post_confirm_verify("去背景"))
bg_steps.extend(make_confirm_and_api("去背景", "approveMaterial|audit/approve|confirm"))
bg_steps.extend(TAIL)
bg_steps.append({"type": "screenshot", "label": "f88-remove-bg-e2e-done", "description": "截图-去背景端到端完成"})

bg_case = {
    "id": "e2e-f88-image-action-remove-bg",
    "name": "端到端：F88 图片去背景 → 确认 → URL/状态一致性校验",
    "description": "进入图片审核详情，勾选素材→hover主图→点击cut图标→去背景处理→确定→验证编辑前/后切换及URL变化→CopyURL/下载验证→点击确认完成审核→自动流转下一任务。",
    "businessType": "f88_material_audit", "scene": "f88-test", "priority": "P0", "category": "e2e_flow",
    "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
        "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center",
        "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
    "steps": bg_steps,
    "screenshot": {"onError": True},
    "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
    "_expected": {"status": "pass"},
    "_testDesign": {"preconditions": "F88预发已登录；存在待审核图片任务。",
        "realDomNotes": "cut图标触发抠图处理→确定→编辑前/后Radio切换→确认→自动流转。URL从llm/变为localUpload/。",
        "riskPoints": ["无待审核任务时无法进入详情", "cut图标需hover主图才出现", "去背景按钮可能不在所有链路的工具栏中"]}
}

# Write all 3 cases (去背景已从当前UI移除，不再生成用例)
cases = {
    "e2e_f88_image_action_replace.json": replace_case,
    "e2e_f88_image_action_crop.json": crop_case,
    "e2e_f88_image_action_hd_enhance.json": hd_case,
}

for fname, case in cases.items():
    path = os.path.join(BASE, fname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    step_count = len(case["steps"])
    print(f"✅ {fname}: {step_count} steps")

print("\nDone! All 4 cases updated.")
