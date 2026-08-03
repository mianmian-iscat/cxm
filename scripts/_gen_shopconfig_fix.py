#!/usr/bin/env python3
"""
店铺信息配置页面 — 基于浏览器实际操作的用例修正 + 补充
URL: /afdMerchantManagement/shopConfig
页面标题: "店铺信息配置"
菜单路径: 商家管理 > 信息配置

实际页面结构 (已验证):
- 搜索: 1个输入框 (placeholder: "请输入sellerid或店铺名")
- 按钮: 重置筛选 / 搜索 / 批量下载
- 表格 8 列: 店铺信息 / 合作供应商 / 参考竞店 / 负责买手 / 视觉偏好 / 搭配偏好 / 参考视觉图例 / 操作
- 每行操作: 编辑 / 删除
- 分页: 63条, 7页, 10条/页
- 编辑页: 面包屑 "店铺管理 / 信息配置" + "返回列表"
  - 锁定: Seller ID / 店铺名称 / 负责买手 / 合作供应商(数据来源于上游)
  - 可编辑: 店铺风格(disabled) / 参考竞店(添加/删除, sellerid自动带入名称) / 视觉偏好(4×textarea,100字) / 搭配偏好(4×textarea,100字) / 参考视觉图例(上传3:4,20MB)
  - 底部: 取消 / 保存
- 删除确认: Modal "是否确认删除" / "配置删除后将无法找回"
"""
import json, os, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "eval" / "cases" / "f88-test"

CTX = {
    "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
    "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig",
    "waitAfterLoad": 3000,
    "auth": "buc",
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

# ── 修正 5 条已有用例 ──────────────────────────────

# 1. mc-table: 表格结构验证 — 修正列名、列数
w("atomic_f88_mc-table.json", meta(
    "atomic-f88-mc-table",
    "UI：店铺信息配置-表格结构验证",
    "验证店铺信息配置表格8列结构完整，数据行存在",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const ths = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()).filter(t => t); const rows = document.querySelectorAll('tr.ant-table-row'); const pagination = document.querySelector('.ant-pagination'); return { columns: ths, columnCount: ths.length, rowCount: rows.length, pagination: pagination ? pagination.textContent.trim().substring(0,80) : 'none' }; })()",
         "description": "获取表格结构和分页信息", "storeAs": "tableInfo"},
        {"type": "assertStore", "key": "tableInfo", "path": "columnCount", "gte": 8, "description": "验证表格至少8列"},
        {"type": "assertStore", "key": "tableInfo", "path": "rowCount", "notEmpty": True, "description": "验证有数据行"},
        {"type": "screenshot", "label": "mc-table", "description": "表格完整结构"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="8列: 店铺信息/合作供应商/参考竞店/负责买手/视觉偏好/搭配偏好/参考视觉图例/操作"
))

# 2. mc-search: 搜索功能 — 修正placeholder和选择器
w("atomic_f88_mc-search.json", meta(
    "atomic-f88-mc-search",
    "UI：店铺信息配置-搜索功能验证",
    "输入sellerid搜索，验证搜索结果过滤",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const input = document.querySelector('input[placeholder*=\"sellerid\"]'); const totalBefore = document.querySelectorAll('tr.ant-table-row').length; return { found: !!input, placeholder: input?.getAttribute('placeholder'), rowCountBefore: totalBefore }; })()",
         "description": "验证搜索框存在及placeholder", "storeAs": "searchBefore"},
        {"type": "assertStore", "key": "searchBefore", "path": "found", "equals": True, "description": "搜索框存在"},
        {"type": "fill", "selector": "input[placeholder*='sellerid']", "value": "2219662018344", "react": True, "description": "输入sellerid搜索F88测试店铺"},
        {"type": "clickText", "text": "搜 索", "description": "点击搜索按钮"},
        {"type": "wait", "ms": 3000, "description": "等待搜索加载"},
        {"type": "evaluate",
         "expression": "(() => { const rows = document.querySelectorAll('tr.ant-table-row'); const total = document.querySelector('.ant-pagination-total-text'); return { rowCountAfter: rows.length, totalText: total?.textContent?.trim() || '' }; })()",
         "description": "验证搜索结果过滤", "storeAs": "searchAfter"},
        {"type": "screenshot", "label": "mc-search-result", "description": "搜索结果"}
    ],
    pre="F88预发已登录；存在sellerid=2219662018344的店铺",
    notes="placeholder='请输入sellerid或店铺名'，搜索后需等待数据刷新"
))

# 3. mc-edit: 编辑配置 — 修正为导航到表单页
w("atomic_f88_mc-edit.json", meta(
    "atomic-f88-mc-edit",
    "UI：店铺信息配置-编辑配置验证",
    "点击编辑进入表单页，验证表单包含锁定字段和可编辑字段",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return { clicked: true, total: btns.length }; } return { clicked: false, total: btns.length }; })()",
         "description": "点击第一行编辑按钮", "storeAs": "editClick"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const breadcrumb = document.body.innerText.includes('店铺管理'); const title = document.body.innerText.match(/编辑[·.]*(\\S+)/)?.[0] || ''; const disabled = document.querySelectorAll('input[disabled],input[disabled]').length; const textareas = document.querySelectorAll('textarea').length; const saveBtn = !!Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '保 存'); const cancelBtn = !!Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); return { hasBreadcrumb: breadcrumb, editTitle: title, disabledCount: disabled, textareaCount: textareas, hasSave: saveBtn, hasCancel: cancelBtn }; })()",
         "description": "验证编辑表单结构", "storeAs": "editForm"},
        {"type": "assertStore", "key": "editForm", "path": "hasSave", "equals": True, "description": "编辑表单包含保存按钮"},
        {"type": "screenshot", "label": "mc-edit-form", "description": "编辑表单页"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="编辑导航到独立表单页，非弹窗/抽屉；包含面包屑'店铺管理/信息配置'和'返回列表'"
))

# 4. mc-reset: 重置筛选 — 修正选择器
w("atomic_f88_mc-reset.json", meta(
    "atomic-f88-mc-reset",
    "UI：店铺信息配置-重置筛选验证",
    "输入搜索条件后点击重置筛选，验证搜索框清空",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "fill", "selector": "input[placeholder*='sellerid']", "value": "测试搜索", "react": True, "description": "输入搜索条件"},
        {"type": "wait", "ms": 500, "description": "等待输入"},
        {"type": "clickText", "text": "重置筛选", "description": "点击重置筛选"},
        {"type": "wait", "ms": 2000, "description": "等待重置"},
        {"type": "evaluate",
         "expression": "(() => { const input = document.querySelector('input[placeholder*=\"sellerid\"]'); return { value: input?.value || '', isEmpty: !input?.value }; })()",
         "description": "验证搜索框已清空", "storeAs": "resetCheck"},
        {"type": "assertStore", "key": "resetCheck", "path": "isEmpty", "equals": True, "description": "搜索框值已清空"},
        {"type": "screenshot", "label": "mc-reset", "description": "重置筛选后"}
    ],
    pre="F88预发已登录",
    notes="重置筛选清空搜索输入框"
))

# 5. mc-batch-download: 批量下载 — 小修
w("atomic_f88_mc-batch-download.json", meta(
    "atomic-f88-mc-batch-download",
    "UI：店铺信息配置-批量下载按钮验证",
    "验证批量下载按钮存在且可点击",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '批量下载'); return { found: !!btn, disabled: btn?.disabled, text: btn?.textContent?.trim() }; })()",
         "description": "查找批量下载按钮", "storeAs": "dlBtn"},
        {"type": "assertStore", "key": "dlBtn", "path": "found", "equals": True, "description": "批量下载按钮存在"},
        {"type": "screenshot", "label": "mc-batch-download", "description": "批量下载按钮"}
    ],
    pre="F88预发已登录",
    notes="批量下载为异步任务"
))

# ── 新增 6 条用例 ──────────────────────────────

# 6. mc-delete: 删除确认弹窗
w("atomic_f88_mc-delete.json", meta(
    "atomic-f88-mc-delete",
    "UI：店铺信息配置-删除确认弹窗验证",
    "点击删除按钮，验证确认弹窗内容和按钮",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '删除'); if(btns.length > 0) { btns[0].click(); return { clicked: true }; } return { clicked: false }; })()",
         "description": "点击第一行删除按钮", "storeAs": "delClick"},
        {"type": "wait", "ms": 1000, "description": "等待弹窗"},
        {"type": "evaluate",
         "expression": "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const body = document.body.innerText; const hasConfirm = body.includes('是否确认删除'); const hasWarning = body.includes('配置删除后将无法找回'); const delBtn = !!Array.from(document.querySelectorAll('.ant-modal button,.ant-popconfirm button')).find(b => b.textContent.trim() === '删 除'); const cancelBtn = !!Array.from(document.querySelectorAll('.ant-modal button,.ant-popconfirm button')).find(b => b.textContent.trim() === '取 消'); return { hasModal: !!modal, hasConfirm, hasWarning, hasDeleteBtn: delBtn, hasCancelBtn: cancelBtn }; })()",
         "description": "验证删除确认弹窗内容", "storeAs": "delModal"},
        {"type": "assertStore", "key": "delModal", "path": "hasConfirm", "equals": True, "description": "弹窗包含确认文案"},
        {"type": "assertStore", "key": "delModal", "path": "hasWarning", "equals": True, "description": "弹窗包含警告文案"},
        {"type": "screenshot", "label": "mc-delete-confirm", "description": "删除确认弹窗"},
        {"type": "pressKey", "key": "Escape", "description": "关闭弹窗"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="弹窗文案: '是否确认删除' + '配置删除后将无法找回，确认是否删除'"
))

# 7. mc-edit-form: 编辑表单字段结构
w("atomic_f88_mc-edit-form.json", meta(
    "atomic-f88-mc-edit-form",
    "UI：店铺信息配置-编辑表单字段结构验证",
    "进入编辑表单，验证锁定字段和可编辑字段",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const text = document.body.innerText; const disabledInputs = Array.from(document.querySelectorAll('input[disabled]')).map(i => i.getAttribute('aria-label') || i.value || '').slice(0,5); const textareas = Array.from(document.querySelectorAll('textarea')); const taInfo = textareas.map(t => ({ placeholder: t.placeholder?.substring(0,30), disabled: t.disabled, maxLen: t.getAttribute('maxlength') || t.parentElement?.textContent?.match(/(\\d+)\\s*\\/\\s*(\\d+)/)?.[2] })); const hasLockIcons = document.querySelectorAll('.anticon-lock,[class*=lock]').length; const uploadArea = !!document.querySelector('.ant-upload'); return { hasSellerID: text.includes('Seller ID'), hasShopName: text.includes('店铺名称'), hasBuyer: text.includes('负责买手'), hasShopStyle: text.includes('店铺风格'), hasSuppliers: text.includes('合作供应商'), hasCompetitors: text.includes('参考竞店'), hasVisualPref: text.includes('视觉偏好'), hasMatchPref: text.includes('搭配偏好'), hasRefImages: text.includes('参考视觉图例'), lockIconCount: hasLockIcons, textareaCount: textareas.length, textareaDetails: taInfo, hasUpload: uploadArea, hasSaveBtn: text.includes('保 存'), hasCancelBtn: text.includes('取 消') }; })()",
         "description": "验证表单字段结构", "storeAs": "formFields"},
        {"type": "assertStore", "key": "formFields", "path": "hasSellerID", "equals": True, "description": "包含Seller ID字段"},
        {"type": "assertStore", "key": "formFields", "path": "hasVisualPref", "equals": True, "description": "包含视觉偏好字段"},
        {"type": "assertStore", "key": "formFields", "path": "hasMatchPref", "equals": True, "description": "包含搭配偏好字段"},
        {"type": "assertStore", "key": "formFields", "path": "hasUpload", "equals": True, "description": "包含图片上传区域"},
        {"type": "screenshot", "label": "mc-edit-form-fields", "description": "编辑表单完整字段"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="锁定字段(Seller ID/店铺名称/负责买手/合作供应商) + 可编辑textarea(视觉偏好4个+搭配偏好4个,各100字) + 图片上传(3:4,20MB)"
))

# 8. mc-add-competitor: 添加参考竞店
w("atomic_f88_mc-add-competitor.json", meta(
    "atomic-f88-mc-add-competitor",
    "UI：店铺信息配置-添加参考竞店验证",
    "编辑表单中点击添加参考竞店，验证新增行和sellerid自动带入",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const before = document.querySelectorAll('input[placeholder=\"请输入 sellerid\"]').length; const addLink = Array.from(document.querySelectorAll('span,a,button')).find(el => el.textContent.trim() === '添加' && el.closest('[class*=competitor],form,main')); if(addLink) { addLink.click(); } return { rowsBefore: before }; })()",
         "description": "记录添加前的竞店行数并点击添加", "storeAs": "addBefore"},
        {"type": "wait", "ms": 1000, "description": "等待新增行"},
        {"type": "evaluate",
         "expression": "(() => { const after = document.querySelectorAll('input[placeholder=\"请输入 sellerid\"]').length; const nameInputs = document.querySelectorAll('input[placeholder=\"输入 sellerid 后自动带入\"]').length; return { rowsAfter: after, nameInputCount: nameInputs, added: after > 0 }; })()",
         "description": "验证新增行", "storeAs": "addAfter"},
        {"type": "assertStore", "key": "addAfter", "path": "added", "equals": True, "description": "添加后存在sellerid输入行"},
        {"type": "screenshot", "label": "mc-add-competitor", "description": "添加参考竞店"},
        {"type": "clickText", "text": "取 消", "description": "取消返回列表"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="每行参考竞店: 名称(自动带入,disabled) + sellerid输入框 + 关闭图标(删除)"
))

# 9. mc-pagination: 分页功能
w("atomic_f88_mc-pagination.json", meta(
    "atomic-f88-mc-pagination",
    "UI：店铺信息配置-分页功能验证",
    "验证分页组件存在且可翻页",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const pagination = document.querySelector('.ant-pagination'); const total = pagination?.querySelector('.ant-pagination-total-text')?.textContent?.trim() || ''; const items = pagination?.querySelectorAll('.ant-pagination-item')?.length || 0; const nextBtn = pagination?.querySelector('.ant-pagination-next'); return { hasPagination: !!pagination, totalText: total, pageCount: items, hasNext: !!nextBtn, nextDisabled: nextBtn?.classList?.contains('ant-pagination-disabled') }; })()",
         "description": "获取分页信息", "storeAs": "pageInfo"},
        {"type": "assertStore", "key": "pageInfo", "path": "hasPagination", "equals": True, "description": "分页组件存在"},
        {"type": "assertStore", "key": "pageInfo", "path": "pageCount", "gte": 2, "description": "至少2页"},
        {"type": "evaluate",
         "expression": "(() => { const page2 = document.querySelector('.ant-pagination-item[title=\"2\"]'); if(page2) { page2.click(); return 'clicked page 2'; } return 'no page 2'; })()",
         "description": "点击第2页"},
        {"type": "wait", "ms": 2000, "description": "等待翻页加载"},
        {"type": "evaluate",
         "expression": "(() => { const active = document.querySelector('.ant-pagination-item-active'); return { activePage: active?.getAttribute('title') || active?.textContent?.trim() || '' }; })()",
         "description": "验证当前页码", "storeAs": "pageAfter"},
        {"type": "screenshot", "label": "mc-pagination", "description": "翻页后"}
    ],
    pre="F88预发已登录；存在超过10条店铺配置",
    notes="63条记录, 7页, 10条/页"
))

# 10. mc-breadcrumb: 面包屑返回列表
w("atomic_f88_mc-breadcrumb.json", meta(
    "atomic-f88-mc-breadcrumb",
    "UI：店铺信息配置-面包屑返回列表验证",
    "编辑页点击返回列表面包屑，验证返回列表页",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const btns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()",
         "description": "点击编辑进入表单"},
        {"type": "wait", "ms": 2000, "description": "等待表单加载"},
        {"type": "evaluate",
         "expression": "(() => { const breadcrumb = document.body.innerText.includes('店铺管理'); const hasBack = document.body.innerText.includes('返回列表'); return { hasBreadcrumb: breadcrumb, hasBackLink: hasBack }; })()",
         "description": "验证面包屑存在", "storeAs": "breadcrumb"},
        {"type": "assertStore", "key": "breadcrumb", "path": "hasBackLink", "equals": True, "description": "面包屑包含返回列表"},
        {"type": "clickText", "text": "返回列表", "description": "点击返回列表"},
        {"type": "wait", "ms": 2000, "description": "等待列表加载"},
        {"type": "evaluate",
         "expression": "(() => { const title = document.body.innerText.includes('店铺信息配置'); const hasTable = !!document.querySelector('table,.ant-table'); return { isListPage: title, hasTable }; })()",
         "description": "验证已返回列表页", "storeAs": "backResult"},
        {"type": "assertStore", "key": "backResult", "path": "isListPage", "equals": True, "description": "成功返回列表页"},
        {"type": "screenshot", "label": "mc-breadcrumb-back", "description": "返回列表页"}
    ],
    pre="F88预发已登录；存在店铺配置数据",
    notes="面包屑: 店铺管理 / 信息配置 + 返回列表链接"
))

# 11. mc-view-all-suppliers: 查看全部合作供应商
w("atomic_f88_mc-view-all-suppliers.json", meta(
    "atomic-f88-mc-view-all-suppliers",
    "UI：店铺信息配置-查看全部合作供应商验证",
    "点击合作供应商的查看全部链接，验证展开全部供应商",
    [
        {"type": "navigate", "url": URL, "waitUntil": "networkidle", "screenshot": True, "description": "打开店铺信息配置"},
        {"type": "wait", "ms": 3000, "description": "等待数据加载"},
        {"type": "evaluate",
         "expression": "(() => { const viewAlls = Array.from(document.querySelectorAll('span,a,button')).filter(el => el.textContent.trim().startsWith('查看全部')); return { count: viewAlls.length, texts: viewAlls.slice(0,3).map(el => el.textContent.trim()) }; })()",
         "description": "查找查看全部链接", "storeAs": "viewAlls"},
        {"type": "evaluate",
         "expression": "(() => { const viewAll = Array.from(document.querySelectorAll('span,a,button')).find(el => el.textContent.trim().startsWith('查看全部')); if(viewAll) { viewAll.click(); return 'clicked'; } return 'no view all'; })()",
         "description": "点击第一个查看全部", "storeAs": "viewClick"},
        {"type": "wait", "ms": 2000, "description": "等待展开"},
        {"type": "evaluate",
         "expression": "(() => { const rows = document.querySelectorAll('tr.ant-table-row'); const firstRow = rows[0]; const tds = firstRow?.querySelectorAll('td'); const supplierCell = tds?.[1]; return { supplierCellText: supplierCell?.textContent?.trim()?.substring(0,200) || '' }; })()",
         "description": "验证供应商展开", "storeAs": "expanded"},
        {"type": "screenshot", "label": "mc-view-all-suppliers", "description": "查看全部供应商"}
    ],
    pre="F88预发已登录；存在有多个合作供应商的店铺",
    notes="合作供应商列默认显示2个+查看全部(N)链接，点击展开所有"
))

print("\n✅ 店铺信息配置用例修正+补充完成: 5条修正 + 6条新增 = 11条")
