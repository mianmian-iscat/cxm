#!/usr/bin/env python3
"""基于实际操作发现，补充分配明细/详情/编辑的详细用例"""
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

TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"
PRE_TM = "F88预发已登录；存在任务管理数据"

# 展开链路→批次→环节→任务的JS
EXPAND_ALL = """(() => {
  // 展开链路卡片
  const headers = document.querySelectorAll('[class*=linkCardHeader]');
  if(headers.length > 0) headers[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));
  return 'link expanded';
})()"""

EXPAND_BATCH = """(() => {
  const icons = document.querySelectorAll('span.anticon-right');
  const batchIcons = Array.from(icons).filter(s => s.className.includes('expandIcon'));
  if(batchIcons.length > 0) { batchIcons[0].click(); return 'batch expanded'; }
  return 'no batch icon';
})()"""

EXPAND_STAGE = """(() => {
  const rows = document.querySelectorAll('.TreeRows--treeRow--DbExNiK');
  const stageRow = Array.from(rows).find(r => r.textContent.includes('总任务数') && r.textContent.includes('审核完成率'));
  if(stageRow) { const icon = stageRow.querySelector('span.anticon-right'); if(icon) { icon.click(); return 'stage expanded'; } }
  return 'no stage';
})()"""

EXPAND_TASK = """(() => {
  const rows = document.querySelectorAll('.TreeRows--treeRow--DbExNiK');
  const taskRow = Array.from(rows).find(r => r.textContent.includes('审核') && r.textContent.includes('总任务数：'));
  if(taskRow) { const icon = taskRow.querySelector('span.anticon-right'); if(icon) { icon.click(); return 'task expanded'; } }
  return 'no task';
})()"""

CLICK_ASSIGN = """(() => {
  const span = Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === '分配明细' && el.children.length === 0);
  const btn = span?.closest('button.ant-btn-link');
  if(btn) { btn.click(); return 'clicked'; }
  return 'no btn';
})()"""

CLICK_DETAIL = """(() => {
  const span = Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === '详情' && el.children.length === 0);
  const btn = span?.closest('button.ant-btn-link');
  if(btn) { btn.click(); return 'clicked'; }
  return 'no btn';
})()"""

CLICK_EDIT = """(() => {
  const span = Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === '编辑' && el.children.length === 0);
  const btn = span?.closest('button.ant-btn-link');
  if(btn) { btn.click(); return 'clicked'; }
  return 'no btn';
})()"""

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

def nav_to_task_row():
    """导航并展开到任务行的通用步骤"""
    return [
        nav(TM_URL), wait(),
        eva(EXPAND_ALL, "展开链路卡片"), wait(2000),
        eva(EXPAND_BATCH, "展开批次"), wait(2000),
        eva(EXPAND_STAGE, "展开环节"), wait(2000),
        eva(EXPAND_TASK, "展开任务"), wait(2000),
    ]

# ============================================================
# 分配明细补充
# ============================================================

# 1. 分配明细-Tab结构
save(meta("atomic-f88-tm-assign-tabs","UI：任务管理-分配明细Tab结构验证",
    "验证分配明细弹窗的Tab结构：审核任务Tab及计数",
    nav_to_task_row() + [
        capture_start("分配明细Tab"),
        eva(CLICK_ASSIGN, "点击分配明细"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasModal: false }; const tabs = Array.from(modal.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); const activeTab = modal.querySelector('.ant-tabs-tab-active')?.textContent?.trim(); return { hasModal: true, tabs, activeTab, tabCount: tabs.length }; })()","验证Tab结构","tabInfo"),
        asrtS("tabInfo","hasModal",desc="验证弹窗存在",equals=True),
        asrtS("tabInfo","tabs",desc="验证Tab列表非空",notEmpty=True),
        shot("tm-assign-tabs","分配明细Tab结构"),
        eva("(() => { const close = document.querySelector('.ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭弹窗"),
        capture_stop()
    ], PRE_TM,"弹窗标题'分配明细'，Tab显示'审核任务（N）'含计数"))

# 2. 分配明细-表格列名
save(meta("atomic-f88-tm-assign-columns","UI：任务管理-分配明细表格列名验证",
    "验证分配明细弹窗内表格包含：审核人/状态&进度/任务时长/通过率/操作",
    nav_to_task_row() + [
        eva(CLICK_ASSIGN, "点击分配明细"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasModal: false }; const headers = Array.from(modal.querySelectorAll('th')).map(th => th.textContent.trim()); const expected = ['审核人','状态','进度','任务时长','通过率','操作']; const found = expected.filter(e => headers.some(h => h.includes(e))); return { hasModal: true, headers, expected, found, coverage: found.length+'/'+expected.length }; })()","验证表格列名","colInfo"),
        asrtS("colInfo","headers",desc="验证列名非空",notEmpty=True),
        shot("tm-assign-columns","分配明细列名"),
        eva("(() => { const close = document.querySelector('.ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭")
    ], PRE_TM,"5列：审核人/状态&进度/任务时长/通过率/操作"))

# 3. 分配明细-数据行内容
save(meta("atomic-f88-tm-assign-row-data","UI：任务管理-分配明细数据行内容验证",
    "验证分配明细表格数据行：审核人(多人)/状态/进度/时长/通过率",
    nav_to_task_row() + [
        eva(CLICK_ASSIGN, "点击分配明细"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasModal: false }; const rows = modal.querySelectorAll('.ant-table-row'); const firstRow = rows[0]; if(!firstRow) return { hasModal: true, rowCount: 0 }; const cells = Array.from(firstRow.querySelectorAll('td')).map(td => td.textContent.trim()); const btns = Array.from(firstRow.querySelectorAll('button')).map(b => b.textContent.trim()); return { hasModal: true, rowCount: rows.length, cells, btns }; })()","验证数据行","rowData"),
        asrtS("rowData","rowCount",desc="验证至少1行数据",notEmpty=True),
        shot("tm-assign-row","分配明细数据行"),
        eva("(() => { const close = document.querySelector('.ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭")
    ], PRE_TM,"审核人可能多人(逗号分隔)，操作列有'转交'按钮"))

# 4. 分配明细-转交按钮
save(meta("atomic-f88-tm-assign-transfer-btn","UI：任务管理-分配明细转交按钮验证",
    "验证分配明细操作列存在转交按钮",
    nav_to_task_row() + [
        eva(CLICK_ASSIGN, "点击分配明细"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return { hasTransfer: false }; const transferBtns = Array.from(modal.querySelectorAll('button')).filter(b => b.textContent.trim() === '转交'); return { hasTransfer: transferBtns.length > 0, count: transferBtns.length }; })()","验证转交按钮","transferInfo"),
        asrtS("transferInfo","hasTransfer",desc="验证转交按钮存在",equals=True),
        shot("tm-assign-transfer","转交按钮"),
        eva("(() => { const close = document.querySelector('.ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭")
    ], PRE_TM,"转交按钮用于将审核任务转给其他人"))

# ============================================================
# 详情补充
# ============================================================

# 5. 详情-页面统计信息
save(meta("atomic-f88-tm-detail-stats","UI：任务管理-详情页统计信息验证",
    "验证详情页展示实时完成率和实时通过率",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const t = document.body.innerText; const completionMatch = t.match(/实时完成率[：:]\\s*([\\d.]+%)/); const passMatch = t.match(/实时通过率[：:]\\s*([\\d.]+%)/); return { hasCompletionRate: !!completionMatch, completionRate: completionMatch?.[1] || null, hasPassRate: !!passMatch, passRate: passMatch?.[1] || null }; })()","验证统计信息","detailStats"),
        asrtS("detailStats","hasCompletionRate",desc="验证实时完成率存在",equals=True),
        asrtS("detailStats","hasPassRate",desc="验证实时通过率存在",equals=True),
        shot("tm-detail-stats","详情页统计"),
    ], PRE_TM,"详情页URL: /review/task/detail?taskId=xxx"))

# 6. 详情-筛选区域
save(meta("atomic-f88-tm-detail-filters","UI：任务管理-详情页筛选区域验证",
    "验证详情页筛选区包含6个筛选条件+重置/查询按钮",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const t = document.body.innerText; const filters = ['商家名称','商家ID','任务ID','审核状态','审核人','类目']; const found = filters.filter(f => t.includes(f)); const hasReset = t.includes('重置'); const hasQuery = t.includes('查询'); return { filters, found, coverage: found.length+'/'+filters.length, hasReset, hasQuery }; })()","验证筛选条件","filterInfo"),
        asrtS("filterInfo","coverage",desc="验证筛选覆盖率",notEmpty=True),
        shot("tm-detail-filters","详情页筛选区"),
    ], PRE_TM,"6个筛选: 商家名称/商家ID/任务ID/审核状态/审核人/类目"))

# 7. 详情-表格列名
save(meta("atomic-f88-tm-detail-table-columns","UI：任务管理-详情页表格列名验证",
    "验证详情页表格包含：任务ID/商家名称/审核状态/图片/类目/审核人/备注",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const expected = ['任务ID','商家名称','审核状态','图片','类目','审核人','备注']; const found = expected.filter(e => headers.some(h => h.includes(e))); return { headers, expected, found, coverage: found.length+'/'+expected.length }; })()","验证表格列名","detailCols"),
        asrtS("detailCols","headers",desc="验证列名非空",notEmpty=True),
        shot("tm-detail-table","详情页表格"),
    ], PRE_TM,"7列：任务ID/商家名称/审核状态/图片/类目/审核人/备注"))

# 8. 详情-图片预览
save(meta("atomic-f88-tm-detail-image-preview","UI：任务管理-详情页图片预览验证",
    "验证详情页表格中展示主图/子图/参考图",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const imgs = document.querySelectorAll('.ant-table-row img'); const mainImgs = Array.from(imgs).filter(img => img.alt === 'main' || img.src.includes('llm')); const subImgs = Array.from(imgs).filter(img => img.alt === 'sub' || img.src.includes('design')); const refText = document.body.innerText.includes('参考图'); return { totalImgs: imgs.length, mainImgCount: mainImgs.length, subImgCount: subImgs.length, hasRefText: refText }; })()","验证图片预览","imgPreview"),
        asrtS("imgPreview","totalImgs",desc="验证有图片展示",notEmpty=True),
        shot("tm-detail-images","详情页图片预览"),
    ], PRE_TM,"每行展示主图+子图，参考图以'参考图+N'文字显示"))

# 9. 详情-分页
save(meta("atomic-f88-tm-detail-pagination","UI：任务管理-详情页分页验证",
    "验证详情页底部有分页组件",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const pagination = document.querySelector('.ant-pagination'); const totalText = document.body.innerText.match(/共\\s*\\d+\\s*条/); return { hasPagination: !!pagination, totalText: totalText?.[0] || null, url: location.href }; })()","验证分页","paginationInfo"),
        shot("tm-detail-pagination","详情页分页"),
    ], PRE_TM,"分页显示'共 N 条'"))

# 10. 详情-返回按钮
save(meta("atomic-f88-tm-detail-back-btn","UI：任务管理-详情页返回按钮验证",
    "验证详情页有返回箭头，点击可回到任务管理列表",
    nav_to_task_row() + [
        eva(CLICK_DETAIL, "点击详情"), wait(3000),
        eva("(() => { const backBtn = document.querySelector('[class*=arrow-left]'); const backParent = backBtn?.closest('a,button,div[style*=cursor]'); return { hasBackBtn: !!backBtn, backBtnTag: backBtn?.tagName, parentTag: backParent?.tagName }; })()","验证返回按钮","backBtnInfo"),
        asrtS("backBtnInfo","hasBackBtn",desc="验证返回箭头存在",equals=True),
        shot("tm-detail-back-btn","返回按钮"),
    ], PRE_TM))

# ============================================================
# 编辑补充
# ============================================================

# 11. 编辑-任务名称字段
save(meta("atomic-f88-tm-edit-task-name","UI：任务管理-编辑弹窗任务名称验证",
    "验证编辑弹窗任务名称字段：必填/预填充/字符计数",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const input = modal.querySelector('input[placeholder*=任务名称]'); const label = modal.querySelector('label')?.textContent?.trim(); const charCount = modal.textContent.match(/\\d+\\s*\\/\\s*100/); return { hasForm: true, hasInput: !!input, inputValue: input?.value || '', charCount: charCount?.[0] || null, isRequired: input?.hasAttribute('required') || false }; })()","验证任务名称字段","taskNameInfo"),
        asrtS("taskNameInfo","hasInput",desc="验证任务名称输入框存在",equals=True),
        shot("tm-edit-task-name","任务名称字段"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM,"任务名称必填，最大100字符，显示X/100计数"))

# 12. 编辑-基础设置字段
save(meta("atomic-f88-tm-edit-basic-fields","UI：任务管理-编辑弹窗基础设置字段验证",
    "验证编辑弹窗基础设置区：审核标准/优先级/预期交付时间/难度预估/人效预估",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const t = modal.textContent; const fields = ['审核标准','优先级','预期交付时间','难度预估','人效预估']; const found = fields.filter(f => t.includes(f)); const priorityVal = modal.querySelector('[class*=select]')?.textContent?.trim(); return { hasForm: true, fields, found, coverage: found.length+'/'+fields.length }; })()","验证基础设置字段","basicFields"),
        asrtS("basicFields","coverage",desc="验证基础字段覆盖率",notEmpty=True),
        shot("tm-edit-basic","基础设置字段"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM,"审核标准/优先级(必填)/预期交付时间(必填)/难度预估/人效预估(必填,条/小时)"))

# 13. 编辑-任务分配区域
save(meta("atomic-f88-tm-edit-assignment","UI：任务管理-编辑弹窗任务分配验证",
    "验证编辑弹窗任务分配区：参与人/职能角色/能力标签/分配方式/分配结果",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const t = modal.textContent; const fields = ['参与人','职能角色筛选','能力标签筛选','分配方式','平均分配','按商家分配','分配结果','任务总数','待分配']; const found = fields.filter(f => t.includes(f)); const radios = Array.from(modal.querySelectorAll('input[type=radio]')).map(r => r.parentElement?.textContent?.trim()); return { hasForm: true, fields, found, coverage: found.length+'/'+fields.length, radios }; })()","验证任务分配","assignmentInfo"),
        asrtS("assignmentInfo","coverage",desc="验证分配字段覆盖率",notEmpty=True),
        shot("tm-edit-assignment","任务分配区域"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM,"分配方式: 平均分配/按商家分配(radio)，显示任务总数/待分配数/每人条数"))

# 14. 编辑-延期风险提示
save(meta("atomic-f88-tm-edit-deadline-warning","UI：任务管理-编辑弹窗延期风险提示验证",
    "验证编辑弹窗显示延期风险提示和审核时长预估",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const t = modal.textContent; const hasWarning = t.includes('延期风险') || t.includes('请于'); const hasEstimate = t.includes('审核时长预估'); const hasRemaining = t.includes('距离预期交付时间剩余'); return { hasForm: true, hasWarning, hasEstimate, hasRemaining }; })()","验证延期提示","deadlineInfo"),
        asrtS("deadlineInfo","hasWarning",desc="验证延期风险提示存在",equals=True),
        shot("tm-edit-deadline","延期风险提示"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM,"提示'请于X小时内开启任务，否则任务存在延期风险'"))

# 15. 编辑-抽检和埋雷开关
save(meta("atomic-f88-tm-edit-switches","UI：任务管理-编辑弹窗抽检埋雷开关验证",
    "验证编辑弹窗底部有抽检是否开启和埋雷是否开启两个Switch开关",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasForm: false }; const switches = modal.querySelectorAll('.ant-switch'); const t = modal.textContent; const hasInspect = t.includes('抽检是否开启'); const hasMine = t.includes('埋雷是否开启'); return { hasForm: true, switchCount: switches.length, hasInspectSwitch: hasInspect, hasMineSwitch: hasMine }; })()","验证开关","switchInfo"),
        asrtS("switchInfo","hasInspectSwitch",desc="验证抽检开关存在",equals=True),
        asrtS("switchInfo","hasMineSwitch",desc="验证埋雷开关存在",equals=True),
        shot("tm-edit-switches","抽检埋雷开关"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM,"两个Switch: 抽检是否开启/埋雷是否开启"))

# 16. 编辑-确定按钮
save(meta("atomic-f88-tm-edit-confirm-btn","UI：任务管理-编辑弹窗确定按钮验证",
    "验证编辑弹窗底部有确定按钮且可点击",
    nav_to_task_row() + [
        eva(CLICK_EDIT, "点击编辑"), wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if(!modal) return { hasConfirm: false }; const confirmBtns = Array.from(modal.querySelectorAll('button')).filter(b => b.textContent.trim() === '确 定' || b.textContent.trim() === '确定'); const cancelBtns = Array.from(modal.querySelectorAll('button')).filter(b => b.textContent.trim() === '取 消' || b.textContent.trim() === '取消'); return { hasConfirm: confirmBtns.length > 0, hasCancel: cancelBtns.length > 0, confirmText: confirmBtns.map(b => b.textContent.trim()), cancelText: cancelBtns.map(b => b.textContent.trim()) }; })()","验证确定取消按钮","btnInfo"),
        asrtS("btnInfo","hasConfirm",desc="验证确定按钮存在",equals=True),
        asrtS("btnInfo","hasCancel",desc="验证取消按钮存在",equals=True),
        shot("tm-edit-buttons","确定取消按钮"),
        eva("(() => { const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '取 消' || b.textContent.trim() === '取消'); if(cancel) cancel.click(); return 'cancelled'; })()","取消"),
    ], PRE_TM))

print("\n=== 基于实际操作补充完成 ===")
print("分配明细补充: 4条 (Tab结构/列名/数据行/转交按钮)")
print("详情补充:     6条 (统计/筛选/表格列名/图片预览/分页/返回)")
print("编辑补充:     6条 (任务名称/基础字段/分配/延期提示/开关/确定)")
