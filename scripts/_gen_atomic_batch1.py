#!/usr/bin/env python3
"""Batch 1: 原子级用例 - 个人任务中心/审核标准管理/审核节点管理/任务管理"""
import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

def nav(url, desc=None):
    return {"type":"navigate","url":url,"waitUntil":"networkidle","screenshot":True,"description":desc or f"打开页面"}

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
    if desc: s["description"] = desc
    else:
        d = f"断言 {key}"
        if path: d += f".{path}"
        for k,v in kw.items(): d += f" {k}={v}"
        s["description"] = d
    return s

def shot(label, desc=None):
    return {"type":"screenshot","label":label,"description":desc or label}

def sel(label, option, desc=None):
    return {"type":"selectOption","label":label,"option":option,"description":desc or f"选择{label}={option}"}

def fill(placeholder, value, desc=None, react=True):
    return {"type":"fill","selector":f"input[placeholder='{placeholder}']","value":value,"react":react,"description":desc or f"输入{placeholder}={value}"}

def meta(id, name, desc, url, steps, pre="", notes="", risks=None, pri="P1"):
    return {
        "id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": {"urlPattern":"pre-aifashion-xiaoer.alibaba-inc.com","url":url,
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

TH = "(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { headers, count: headers.length }; })()"
MODAL = "(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!m, title: m ? m.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()"
CLOSE_MODAL = "(() => { const c = document.querySelector('.ant-modal-close'); if(c) c.click(); return 'closed'; })()"
def BTN_FIND(texts):
    joined = ",".join("'" + t + "'" for t in texts)
    return f"(() => {{ const btns = Array.from(document.querySelectorAll('a,button')).filter(el => [{joined}].some(t => el.textContent.trim().includes(t))); return btns.map(b => ({{ text: b.textContent.trim(), tag: b.tagName }})); }})()"
TAB_INFO = "(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); const active = document.querySelector('.ant-tabs-tab-active')?.textContent?.trim(); return { tabs, active }; })()"
CARD_INFO = "(() => { const cards = Array.from(document.querySelectorAll('.ant-card,[class*=card]')).map(c => c.textContent.trim().substring(0,100)); return { cards, count: cards.length }; })()"
COUNT = lambda sel: f"(() => {{ const els = document.querySelectorAll('{sel}'); return {{ count: els.length }}; }})()"

# ========== Page 1: 个人任务中心 ==========
PTC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center"
PRE_PTC = "F88预发已登录；个人任务中心有任务数据"

# 1. 审核任务Tab
save(meta("atomic-f88-ptc-audit-tab","UI：个人任务中心-审核任务Tab切换验证",
    "切换到审核任务Tab，验证Tab激活状态和列表渲染",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        asrt("审核任务","验证审核任务Tab存在"),
        click("审核任务","切换到审核任务Tab"),wait(2000),
        eva(TAB_INFO,"获取Tab状态","tabState"),
        asrtS("tabState","active",desc="验证有激活Tab",notEmpty=True),
        eva(COUNT(".ant-tabs-tab"),"统计Tab数量","tabCount"),
        asrtS("tabCount","count",desc="验证Tab数量>0",notEmpty=True),
        shot("ptc-audit-tab","审核任务Tab截图")],
    PRE_PTC,"Tab: 审核任务/抽检任务/埋雷任务"))

# 2. 抽检任务Tab
save(meta("atomic-f88-ptc-inspect-tab","UI：个人任务中心-抽检任务Tab切换验证",
    "切换到抽检任务Tab，验证Tab激活和列表内容变化",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        click("抽检任务","切换到抽检任务Tab"),wait(2000),
        eva(TAB_INFO,"获取Tab状态","tabState"),
        asrtS("tabState","active",desc="验证有激活Tab",notEmpty=True),
        shot("ptc-inspect-tab","抽检任务Tab截图")],
    PRE_PTC,"抽检任务: 对已审核素材进行随机抽检复核"))

# 3. 埋雷任务Tab
save(meta("atomic-f88-ptc-mine-tab","UI：个人任务中心-埋雷任务Tab切换验证",
    "切换到埋雷任务Tab，验证Tab激活和列表内容",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        click("埋雷任务","切换到埋雷任务Tab"),wait(2000),
        eva(TAB_INFO,"获取Tab状态","tabState"),
        asrtS("tabState","active",desc="验证有激活Tab",notEmpty=True),
        shot("ptc-mine-tab","埋雷任务Tab截图")],
    PRE_PTC,"埋雷任务: 混入已知答案的测试素材考核审核员准确率"))

# 4. 任务搜索
save(meta("atomic-f88-ptc-search","UI：个人任务中心-任务搜索功能验证",
    "在任务列表中进行搜索，验证搜索框响应和结果过滤",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const inputs = Array.from(document.querySelectorAll('input')); return inputs.map(i => ({ placeholder: i.placeholder, type: i.type })); })()","探查搜索框","searchInputs"),
        asrtS("searchInputs","placeholder",desc="验证搜索框存在",notEmpty=True),
        fill("请输入","测试","输入搜索关键词"),wait(1500),
        shot("ptc-search-result","搜索结果截图")],
    PRE_PTC,"搜索框为React受控组件，fill必须react:true"))

# 5. 任务列表字段
save(meta("atomic-f88-ptc-list-fields","UI：个人任务中心-任务列表字段完整性验证",
    "验证任务列表展示所有必要字段：任务编号/任务名称/审核类型/日期",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const items = Array.from(document.querySelectorAll('[class*=task],[class*=list] li,[class*=card]')).slice(0,3).map(el => el.textContent.trim().substring(0,150)); return { items, count: items.length }; })()","提取任务条目","taskItems"),
        asrtS("taskItems","count",desc="验证任务列表非空",notEmpty=True),
        eva("(() => { const t = document.body.innerText; const fields = ['任务编号','任务名称','审核类型']; const found = fields.filter(f => t.includes(f)); return { fields, found, coverage: found.length+'/'+fields.length }; })()","验证字段文案","fieldCheck"),
        shot("ptc-list-fields","列表字段截图")],
    PRE_PTC,"任务字段: 任务编号/任务名称/审核类型/日期"))

# 6. 点击任务进入详情
save(meta("atomic-f88-ptc-task-click","UI：个人任务中心-点击任务进入审核详情",
    "点击第一条任务，验证进入审核详情页",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item],[class*=list-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } const links = document.querySelectorAll('a'); for(const a of links) { if(a.textContent.includes('审核') || a.href.includes('detail')) { a.click(); return 'clicked link'; } } return 'no clickable'; })()","点击第一条任务","clickResult"),
        wait(3000),
        shot("ptc-task-detail","审核详情页截图"),
        eva("(() => { return { url: location.href, title: document.title, hasContent: document.body.innerText.length > 100 }; })()","记录详情页信息","detailInfo"),
        asrtS("detailInfo","hasContent",desc="验证详情页有内容",equals=True)],
    PRE_PTC,"点击任务条目进入审核详情页"))

# 7. 空状态
save(meta("atomic-f88-ptc-empty","UI：个人任务中心-空状态展示验证",
    "验证无任务数据时的空状态展示",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const empty = document.querySelector('.ant-empty,[class*=empty],[class*=no-data]'); return { hasEmpty: !!empty, text: empty ? empty.textContent.trim() : null }; })()","检查空状态组件","emptyState"),
        shot("ptc-empty","空状态截图")],
    "F88预发已登录；当前无待处理任务"))

# ========== Page 2: 审核标准管理 ==========
STD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/standard-management"
PRE_STD = "F88预发已登录；存在审核标准数据"

# 1. 页面加载+文案
save(meta("atomic-f88-std-page-load","UI：审核标准管理-页面加载与文案完整性",
    "验证页面标题、表格列名、按钮文案完整",
    STD_URL, [nav(STD_URL,"打开审核标准管理"),wait(),
        asrt("审核标准管理","验证页面标题"),
        eva(TH,"获取表格列名","headers"),
        asrtS("headers","count",desc="验证列名非空",notEmpty=True),
        eva(BTN_FIND(["重置","新增标准"]),"获取按钮","btns"),
        asrt("重置","验证重置按钮"),
        asrt("新增标准","验证新增标准按钮"),
        shot("std-page-load","审核标准管理页面")],
    PRE_STD,"字段: 标准名称/创建人/创建时间/使用次数/状态/操作"))

# 2. 新增标准弹窗
save(meta("atomic-f88-std-add","UI：审核标准管理-新增标准弹窗验证",
    "点击新增标准，验证弹窗出现及表单字段",
    STD_URL, [nav(STD_URL,"打开审核标准管理"),wait(),
        click("新增标准","点击新增标准"),wait(1500),
        eva(MODAL,"验证弹窗","addModal"),
        asrtS("addModal","hasModal",desc="验证弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { fields: [] }; const inputs = Array.from(m.querySelectorAll('input,textarea,select')).map(i => ({ placeholder: i.placeholder || '', type: i.type, label: i.closest('.ant-form-item')?.querySelector('label')?.textContent?.trim() || '' })); return { fields: inputs }; })()","探查表单字段","formFields"),
        shot("std-add-modal","新增标准弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_STD,"新增标准弹窗含表单字段"))

# 3. 编辑标准
save(meta("atomic-f88-std-edit","UI：审核标准管理-编辑标准验证",
    "点击第一条标准的编辑按钮，验证编辑弹窗",
    STD_URL, [nav(STD_URL,"打开审核标准管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no edit btn'; })()","点击编辑","editResult"),
        wait(1500),
        eva(MODAL,"验证编辑弹窗","editModal"),
        asrtS("editModal","hasModal",desc="验证编辑弹窗出现",equals=True),
        shot("std-edit-modal","编辑标准弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_STD,"编辑弹窗应预填当前标准数据"))

# 4. 启用/禁用切换
save(meta("atomic-f88-std-toggle","UI：审核标准管理-启用禁用切换验证",
    "找到启用/禁用按钮，验证Switch或按钮切换",
    STD_URL, [nav(STD_URL,"打开审核标准管理"),wait(),
        eva("(() => { const switches = Array.from(document.querySelectorAll('.ant-switch')); const toggleBtns = Array.from(document.querySelectorAll('a,button')).filter(el => { const t = el.textContent.trim(); return t.includes('启用') || t.includes('禁用'); }); return { switchCount: switches.length, toggleBtns: toggleBtns.map(b => b.textContent.trim()), total: switches.length + toggleBtns.length }; })()","查找启用禁用控件","toggleInfo"),
        asrtS("toggleInfo","total",desc="验证启用禁用控件存在",notEmpty=True),
        shot("std-toggle","启用禁用控件截图")],
    PRE_STD,"启用/禁用可能为Switch组件或文字按钮"))

# 5. 删除确认
save(meta("atomic-f88-std-delete","UI：审核标准管理-删除确认弹窗验证",
    "点击删除按钮，验证确认弹窗出现",
    STD_URL, [nav(STD_URL,"打开审核标准管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '删除'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no delete btn'; })()","点击删除","delResult"),
        wait(1500),
        eva("(() => { const pop = document.querySelector('.ant-popover,.ant-popconfirm,.ant-modal-confirm'); const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasPopconfirm: !!pop, hasModal: !!modal, text: (pop || modal)?.textContent?.trim()?.substring(0,100) || null }; })()","验证确认弹窗","confirmDlg"),
        shot("std-delete-confirm","删除确认弹窗"),
        eva("(() => { const cancel = document.querySelector('.ant-popover .ant-btn:not(.ant-btn-primary),.ant-modal-confirm .ant-btn:not(.ant-btn-primary),.ant-popconfirm .ant-btn:not(.ant-btn-primary)'); if(cancel) { cancel.click(); return 'cancelled'; } const close = document.querySelector('.ant-modal-close'); if(close) { close.click(); return 'closed'; } return 'no cancel'; })()","取消删除")],
    PRE_STD,"删除需确认弹窗，防止误操作",["P0"]))

# ========== Page 3: 审核节点管理 ==========
NODE_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/node-management"
PRE_NODE = "F88预发已登录；存在审核节点数据"

# 1. 页面加载+文案
save(meta("atomic-f88-node-page-load","UI：审核节点管理-页面加载与文案完整性",
    "验证页面标题、表格列名、新增节点按钮",
    NODE_URL, [nav(NODE_URL,"打开审核节点管理"),wait(),
        asrt("审核节点管理","验证页面标题"),
        eva(TH,"获取表格列名","headers"),
        asrtS("headers","count",desc="验证列名非空",notEmpty=True),
        asrt("新增节点","验证新增节点按钮"),
        shot("node-page-load","审核节点管理页面")],
    PRE_NODE,"字段: 节点名称/审核标准/人效预估/难度预估/分配方式/审核人/检查设置"))

# 2. 新增节点
save(meta("atomic-f88-node-add","UI：审核节点管理-新增节点弹窗验证",
    "点击新增节点，验证弹窗及表单字段",
    NODE_URL, [nav(NODE_URL,"打开审核节点管理"),wait(),
        click("新增节点","点击新增节点"),wait(1500),
        eva(MODAL,"验证弹窗","addModal"),
        asrtS("addModal","hasModal",desc="验证弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { fields: [] }; const inputs = Array.from(m.querySelectorAll('input,textarea,select')).map(i => ({ placeholder: i.placeholder || '', type: i.type, label: i.closest('.ant-form-item')?.querySelector('label')?.textContent?.trim() || '' })); return { fields: inputs }; })()","探查表单字段","formFields"),
        shot("node-add-modal","新增节点弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_NODE,"新增节点弹窗含节点名称/类型/负责人等字段"))

# 3. 编辑节点
save(meta("atomic-f88-node-edit","UI：审核节点管理-编辑节点验证",
    "点击编辑按钮，验证编辑弹窗及预填数据",
    NODE_URL, [nav(NODE_URL,"打开审核节点管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no edit btn'; })()","点击编辑","editResult"),
        wait(1500),
        eva(MODAL,"验证编辑弹窗","editModal"),
        asrtS("editModal","hasModal",desc="验证编辑弹窗出现",equals=True),
        shot("node-edit-modal","编辑节点弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_NODE,"编辑弹窗应预填当前节点数据"))

# 4. 关联审核标准
save(meta("atomic-f88-node-std-link","UI：审核节点管理-关联审核标准字段验证",
    "验证节点关联的审核标准字段正确展示",
    NODE_URL, [nav(NODE_URL,"打开审核节点管理"),wait(),
        eva("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const hasStdCol = headers.some(h => h.includes('标准') || h.includes('审核标准')); const rows = Array.from(document.querySelectorAll('tbody tr')).slice(0,3).map(tr => { const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim()); return { cells }; }); return { headers, hasStdCol, rows }; })()","探查关联标准字段","stdLink"),
        asrtS("stdLink","hasStdCol",desc="验证存在审核标准列",equals=True),
        shot("node-std-link","关联标准字段截图")],
    PRE_NODE,"节点需关联审核标准"))

# 5. 排序功能
save(meta("atomic-f88-node-sort","UI：审核节点管理-排序功能验证",
    "验证节点排序控件存在及拖拽排序",
    NODE_URL, [nav(NODE_URL,"打开审核节点管理"),wait(),
        eva("(() => { const sortIcons = document.querySelectorAll('[class*=sort],[class*=drag],[class*=handle]'); const sortBtns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim().includes('排序')); return { sortIcons: sortIcons.length, sortBtns: sortBtns.length }; })()","查找排序控件","sortControls"),
        shot("node-sort","排序控件截图")],
    PRE_NODE,"排序: 初审→复审→终审"))

# ========== Page 4: 任务管理 ==========
TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"
PRE_TM = "F88预发已登录；存在任务管理数据"

# 1. 批量导出
save(meta("atomic-f88-tm-export","UI：任务管理-批量导出功能验证",
    "验证批量导出按钮存在及导出流程",
    TM_URL, [nav(TM_URL,"打开任务管理"),wait(),
        eva(BTN_FIND(["导出","批量导出","Excel"]),"查找导出按钮","exportBtns"),
        shot("tm-export","导出按钮截图")],
    PRE_TM,"批量导出为Excel格式"))

# 2. 重试失败任务
save(meta("atomic-f88-tm-retry","UI：任务管理-重试失败任务验证",
    "找到失败任务的重试按钮并验证",
    TM_URL, [nav(TM_URL,"打开任务管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim().includes('重试')); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找重试按钮","retryBtns"),
        shot("tm-retry","重试按钮截图")],
    PRE_TM,"重试仅对失败任务可用"))

# 3. 表格结构
save(meta("atomic-f88-tm-table","UI：任务管理-表格列名完整性验证",
    "验证任务管理表格包含所有必要列",
    TM_URL, [nav(TM_URL,"打开任务管理"),wait(),
        eva(TH,"获取表格列名","headers"),
        asrtS("headers","count",desc="验证列名非空",notEmpty=True),
        eva("(() => { const t = document.body.innerText; const cols = ['任务ID','商家名称','审核状态','审核人','提交时间']; const found = cols.filter(c => t.includes(c)); return { cols, found, coverage: found.length+'/'+cols.length }; })()","验证列名文案","colCheck"),
        shot("tm-table","表格结构截图")],
    PRE_TM,"列: 任务ID/商家名称/审核状态/审核人/提交时间/审核时间/操作"))

print("\n=== Batch 1 完成 ===")
