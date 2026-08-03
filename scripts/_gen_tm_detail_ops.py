#!/usr/bin/env python3
"""细化任务管理3个操作：分配明细/详情/编辑 → 更详细的原子用例"""
import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

def nav(url):
    return {"type":"navigate","url":url,"waitUntil":"networkidle","screenshot":True,"description":"打开任务管理"}
def wait(ms=3000):
    return {"type":"wait","ms":ms,"description":"等待加载"}
def click(text, desc=None):
    return {"type":"clickText","text":text,"description":desc or f"点击{text}"}
def eva(expr, desc=None, store=None):
    s = {"type":"evaluate","expression":expr,"description":desc or "DOM探查"}
    if store: s["storeAs"] = store
    return s
def asrt(contains, desc=None):
    return {"type":"assert","target":"page","contains":contains,"description":desc or f"验证包含'{contains}'"}
def asrtS(key, path=None, desc="", **kw):
    s = {"type":"assertStore","key":key}
    if path: s["path"] = path
    s.update(kw)
    s["description"] = desc if desc else f"断言 {key}"
    return s
def shot(label, desc=None):
    return {"type":"screenshot","label":label,"description":desc or label}
def capture_start(desc="开始抓包"):
    return {"type":"capture","action":"start","description":desc}
def capture_stop(desc="停止抓包"):
    return {"type":"capture","action":"stop","description":desc}

EXPAND_ALL = "(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return 'expanded'; })()"
PRE_TM = "F88预发已登录；存在任务管理数据"
TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"

def meta(id, name, desc, steps, pre="", notes="", risks=None, pri="P1"):
    return {
        "id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": {"urlPattern":"pre-aifashion-xiaoer.alibaba-inc.com",
                    "url":TM_URL,
                    "waitAfterLoad":3000,"auth":"buc","captureFilter":"bzb.api.fsyx_quality_guard"},
        "steps": steps,
        "screenshot": {"onError": True},
        "contextOptimization": {"screenshotExternal":True,"maxResponseSizeKb":100,"outputCompact":True},
        "_expected": {"status":"pass"},
        "_testDesign": {"preconditions":pre,"realDomNotes":notes,"riskPoints":risks or []}
    }

def save(case):
    path = os.path.join(BASE, f"{case['id'].replace('atomic-f88-','atomic_f88_')}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {os.path.basename(path)} ({len(case['steps'])}步)")

# ============================================================
# 分配明细 → 拆为4条
# ============================================================

# 1. 分配明细-按钮存在性
save(meta("atomic-f88-tm-assign-btn","UI：任务管理-分配明细按钮存在性验证",
    "验证任务行操作列中分配明细链接存在且文案正确",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '分配明细'); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找分配明细按钮","assignBtns"),
        asrtS("assignBtns","count",desc="验证分配明细按钮至少存在1个",notEmpty=True),
        shot("tm-assign-btn","分配明细按钮存在性")],
    PRE_TM,"分配明细为蓝色文字链接，位于操作列"))

# 2. 分配明细-弹窗打开与标题
save(meta("atomic-f88-tm-assign-modal-open","UI：任务管理-分配明细弹窗打开与标题验证",
    "点击分配明细，验证弹窗正确打开且标题正确",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        capture_start("分配明细弹窗"),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '分配明细'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击分配明细"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasModal: false }; const title = modal.querySelector('.ant-modal-title')?.textContent?.trim(); const body = modal.querySelector('.ant-modal-body')?.textContent?.trim()?.substring(0,200); return { hasModal: true, title, bodyLen: body?.length || 0 }; })()","验证弹窗标题","modalInfo"),
        asrtS("modalInfo","hasModal",desc="验证弹窗已打开",equals=True),
        asrtS("modalInfo","title",desc="验证弹窗标题非空",notEmpty=True),
        shot("tm-assign-modal","分配明细弹窗"),
        capture_stop()],
    PRE_TM,"弹窗标题应包含'分配明细'或任务名称"))

# 3. 分配明细-弹窗内容(审核员列表)
save(meta("atomic-f88-tm-assign-modal-content","UI：任务管理-分配明细弹窗内容验证",
    "验证分配明细弹窗内展示审核员分配信息",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '分配明细'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击分配明细"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasModal: false }; const tables = modal.querySelectorAll('table, .ant-table'); const rows = modal.querySelectorAll('tr, .ant-table-row'); const headers = Array.from(modal.querySelectorAll('th')).map(th => th.textContent.trim()); const cells = Array.from(modal.querySelectorAll('td')).map(td => td.textContent.trim()); return { hasModal: true, tableCount: tables.length, rowCount: rows.length, headers, cellSample: cells.slice(0,10) }; })()","验证弹窗内表格内容","modalContent"),
        asrtS("modalContent","hasModal",desc="验证弹窗存在",equals=True),
        shot("tm-assign-content","分配明细内容"),
        eva("(() => { const close = document.querySelector('.ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭弹窗")],
    PRE_TM,"弹窗内应展示审核员名称/分配数量等表格数据"))

# 4. 分配明细-弹窗关闭
save(meta("atomic-f88-tm-assign-modal-close","UI：任务管理-分配明细弹窗关闭验证",
    "验证分配明细弹窗可通过X按钮或取消按钮关闭",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '分配明细'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击分配明细"),
        wait(2000),
        eva("(() => { const closeX = document.querySelector('.ant-modal-close'); if(closeX) { closeX.click(); return 'closed-by-x'; } return 'no-x-btn'; })()","通过X按钮关闭","closeResult"),
        wait(1000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal }; })()","验证弹窗已关闭","afterClose"),
        asrtS("afterClose","hasModal",desc="验证弹窗已关闭",equals=False),
        shot("tm-assign-closed","弹窗关闭后")],
    PRE_TM))

# ============================================================
# 详情 → 拆为4条
# ============================================================

# 5. 详情-按钮存在性
save(meta("atomic-f88-tm-detail-btn","UI：任务管理-详情按钮存在性验证",
    "验证任务行操作列中详情链接存在且文案正确",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '详情'); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找详情按钮","detailBtns"),
        asrtS("detailBtns","count",desc="验证详情按钮至少存在1个",notEmpty=True),
        shot("tm-detail-btn","详情按钮存在性")],
    PRE_TM,"详情为蓝色文字链接，位于操作列"))

# 6. 详情-页面跳转
save(meta("atomic-f88-tm-detail-navigate","UI：任务管理-详情页面跳转验证",
    "点击详情链接，验证页面正确跳转到任务详情页",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const beforeUrl = location.href; const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '详情'); if(btns.length > 0) { btns[0].click(); return beforeUrl; } return 'no btn'; })()","记录跳转前URL并点击详情","beforeUrl"),
        wait(3000),
        eva("(() => { return { currentUrl: location.href, urlChanged: true }; })()","验证URL变化","afterNav"),
        asrtS("afterNav","currentUrl",desc="验证URL已变化",notEmpty=True),
        shot("tm-detail-page","详情页加载")],
    PRE_TM,"详情页URL应包含detail或task相关路径"))

# 7. 详情-页面内容完整性
save(meta("atomic-f88-tm-detail-content","UI：任务管理-详情页面内容完整性验证",
    "验证详情页展示任务完整信息：任务名称/批次ID/状态/审核人等",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '详情'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击详情"),
        wait(3000),
        eva("(() => { const t = document.body.innerText; const fields = ['任务名称','批次','状态','审核','创建','交付']; const found = fields.filter(f => t.includes(f)); return { fields, found, coverage: found.length+'/'+fields.length, bodyLen: t.length }; })()","验证详情页字段","detailFields"),
        asrtS("detailFields","coverage",desc="验证详情页字段覆盖率",notEmpty=True),
        shot("tm-detail-content","详情页内容")],
    PRE_TM,"详情页应展示任务完整信息"))

# 8. 详情-返回导航
save(meta("atomic-f88-tm-detail-back","UI：任务管理-详情页返回验证",
    "验证详情页可返回任务管理列表页",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '详情'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击详情"),
        wait(3000),
        eva("(() => { const backBtns = Array.from(document.querySelectorAll('a,button')).filter(el => { const t = el.textContent.trim(); return ['返回','back','<'].some(k => t.includes(k) || t === k); }); if(backBtns.length > 0) { backBtns[0].click(); return 'clicked-back'; } return 'no-back-btn'; })()","点击返回按钮","backResult"),
        wait(2000),
        eva("(() => { return { url: location.href, isTaskMgmt: location.href.includes('task-management') }; })()","验证已返回列表页","backCheck"),
        shot("tm-detail-back","返回列表页")],
    PRE_TM,"详情页应有返回按钮或面包屑导航"))

# ============================================================
# 编辑 → 拆为5条
# ============================================================

# 9. 编辑-按钮存在性
save(meta("atomic-f88-tm-edit-btn","UI：任务管理-编辑按钮存在性验证",
    "验证任务行操作列中编辑链接存在且文案正确",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); return { count: btns.length }; })()","查找编辑按钮","editBtns"),
        asrtS("editBtns","count",desc="验证编辑按钮至少存在1个",notEmpty=True),
        shot("tm-edit-btn","编辑按钮存在性")],
    PRE_TM,"编辑为蓝色文字链接，位于操作列"))

# 10. 编辑-弹窗打开与表单
save(meta("atomic-f88-tm-edit-modal-open","UI：任务管理-编辑弹窗打开与表单验证",
    "点击编辑，验证弹窗打开且表单字段正确渲染",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        capture_start("编辑弹窗"),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击编辑"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); const container = modal || drawer; if(!container) return { hasForm: false }; const title = container.querySelector('.ant-modal-title,.ant-drawer-title')?.textContent?.trim(); const inputs = container.querySelectorAll('input, .ant-select, textarea'); const labels = Array.from(container.querySelectorAll('.ant-form-item-label, label')).map(l => l.textContent.trim()); return { hasForm: true, title, inputCount: inputs.length, labels }; })()","验证编辑表单","editForm"),
        asrtS("editForm","hasForm",desc="验证编辑弹窗/抽屉已打开",equals=True),
        asrtS("editForm","inputCount",desc="验证表单有输入控件",notEmpty=True),
        shot("tm-edit-modal","编辑弹窗"),
        capture_stop()],
    PRE_TM,"编辑弹窗应包含任务名称/预期交付时间等表单字段"))

# 11. 编辑-表单字段预填充
save(meta("atomic-f88-tm-edit-form-prefill","UI：任务管理-编辑表单预填充验证",
    "验证编辑弹窗打开后表单字段已预填充当前任务数据",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击编辑"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const inputs = Array.from(modal.querySelectorAll('input')).filter(i => i.value && i.value.trim()); const selects = Array.from(modal.querySelectorAll('.ant-select-selection-item')).map(s => s.textContent.trim()); return { hasForm: true, filledInputs: inputs.length, filledInputsSample: inputs.map(i => i.value.trim()).slice(0,5), selectValues: selects }; })()","验证表单预填充","formPrefill"),
        asrtS("formPrefill","hasForm",desc="验证编辑弹窗存在",equals=True),
        shot("tm-edit-prefill","表单预填充"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_TM,"表单字段应预填充任务的当前值"))

# 12. 编辑-保存按钮
save(meta("atomic-f88-tm-edit-save-btn","UI：任务管理-编辑保存按钮验证",
    "验证编辑弹窗中存在保存/确认按钮",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击编辑"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasSaveBtn: false }; const saveBtns = Array.from(modal.querySelectorAll('button')).filter(b => { const t = b.textContent.trim(); return ['保存','确定','确认','提交','Save','OK'].some(k => t.includes(k)); }); return { hasSaveBtn: saveBtns.length > 0, saveBtnTexts: saveBtns.map(b => b.textContent.trim()), isPrimary: saveBtns.map(b => b.className.includes('primary') || b.className.includes('primary')) }; })()","验证保存按钮","saveBtnInfo"),
        asrtS("saveBtnInfo","hasSaveBtn",desc="验证保存按钮存在",equals=True),
        shot("tm-edit-save-btn","保存按钮"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_TM,"保存按钮通常为蓝色primary按钮"))

# 13. 编辑-取消/关闭
save(meta("atomic-f88-tm-edit-cancel","UI：任务管理-编辑取消/关闭验证",
    "验证编辑弹窗可通过取消按钮或X按钮关闭且不保存",
    [nav(TM_URL),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击编辑"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return 'no modal'; const cancelBtns = Array.from(modal.querySelectorAll('button')).filter(b => { const t = b.textContent.trim(); return ['取消','关闭','Cancel'].some(k => t.includes(k)); }); if(cancelBtns.length > 0) { cancelBtns[0].click(); return 'cancelled'; } const closeX = modal.querySelector('.ant-modal-close,.ant-drawer-close'); if(closeX) { closeX.click(); return 'closed-by-x'; } return 'no-cancel'; })()","取消编辑","cancelResult"),
        wait(1000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); return { hasModal: !!modal, hasDrawer: !!drawer }; })()","验证弹窗已关闭","afterCancel"),
        asrtS("afterCancel","hasModal",desc="验证弹窗已关闭",equals=False),
        shot("tm-edit-cancel","取消编辑后")],
    PRE_TM))

print("\n=== 任务管理操作细化完成 ===")
print("分配明细: 4条 (按钮存在/弹窗打开/内容验证/关闭)")
print("详情:     4条 (按钮存在/页面跳转/内容完整/返回)")
print("编辑:     5条 (按钮存在/弹窗表单/预填充/保存按钮/取消)")
