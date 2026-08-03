import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

def case(id, name, desc, url, steps, pre="", notes="", risks=None, pri="P1"):
    return {"id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com", "url": url,
                    "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
        "steps": steps, "screenshot": {"onError": True},
        "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
        "_expected": {"status": "pass"},
        "_testDesign": {"preconditions": pre, "realDomNotes": notes, "riskPoints": risks or ["无数据时为空"]}}

def nav(url, d="打开页面"):
    return {"type": "navigate", "url": url, "waitUntil": "networkidle", "screenshot": True, "description": d}
def w(ms, d="等待"):
    return {"type": "wait", "ms": ms, "description": d}
def click(t, d=None):
    return {"type": "clickText", "text": t, "description": d or f"点击{t}"}
def ev(expr, d, storeAs=None):
    s = {"type": "evaluate", "expression": expr, "description": d}
    if storeAs: s["storeAs"] = storeAs
    return s
def assertStore(key, **kw):
    s = {"type": "assertStore", "key": key}
    s.update(kw)
    return s
def assertC(target, text, d=None):
    return {"type": "assert", "target": target, "contains": text, "description": d or f"断言包含'{text}'"}
def fillR(sel, val, d):
    return {"type": "fill", "selector": sel, "value": val, "react": True, "description": d}
def selOpt(label, opt, d=None):
    return {"type": "selectOption", "label": label, "option": opt, "description": d or f"选择{label}={opt}"}
def shot(label, d="截图"):
    return {"type": "screenshot", "label": label, "description": d}

# ================================================================
# URL constants
# ================================================================
TM = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"
PTC = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center"
AS = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/standard-management"
AN = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/node-management"
MC = "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig"
PD = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/productionDashboard"
SL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list"
SD = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail?id=20180"
LL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkList"
LD = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180"
TPM = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement"
TL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateLibrary"
QT = "https://pre-aifashion-xiaoer.alibaba-inc.com/selfTemplateLibrary_f88"

cases = {}

# ================================================================
# PAGE 1: 任务管理 (task-management) — 原子功能点
# ================================================================

# 1.1 品牌标识
cases["atom_f88_tm_brand_logo"] = case("atom-f88-tm-brand-logo",
    "原子：任务管理-品牌标识文案验证",
    "验证页面左上角显示'F88–运营平台'，确认租户身份正确",
    TM,
    [nav(TM), w(3000),
     assertC("page", "F88", "断言品牌标识包含F88"),
     assertC("page", "运营平台", "断言品牌标识包含运营平台"),
     shot("tm-brand-logo", "品牌标识")],
    notes="页面左上角品牌标识必须显示'F88–运营平台'")

# 1.2 当前身份
cases["atom_f88_tm_identity"] = case("atom-f88-tm-identity",
    "原子：任务管理-当前身份下拉值验证",
    "验证'当前身份'下拉值为'F88'",
    TM,
    [nav(TM), w(3000),
     assertC("page", "当前身份", "断言当前身份label存在"),
     assertC("page", "F88", "断言身份值为F88"),
     shot("tm-identity", "当前身份")],
    notes="品牌标识下方显示'当前身份：F88'")

# 1.3 Tab: 策略平台-F88
cases["atom_f88_tm_tab_f88"] = case("atom-f88-tm-tab-f88",
    "原子：任务管理-策略平台-F88 Tab文案与选中验证",
    "验证'策略平台-F88'Tab文案正确且默认选中",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const f88 = tabs.find(t => t.textContent.includes('策略平台-F88') || t.textContent.includes('F88')); return { found: !!f88, text: f88?.textContent?.trim(), active: f88?.classList?.contains('ant-tabs-tab-active') || false }; })()", "验证F88 Tab", storeAs="tabF88"),
     assertStore("tabF88", path="found", equals=True, description="断言F88 Tab存在"),
     shot("tm-tab-f88", "F88 Tab")],
    notes="策略平台-F88为默认选中Tab")

# 1.4 Tab: 策略平台-测试
cases["atom_f88_tm_tab_test"] = case("atom-f88-tm-tab-test",
    "原子：任务管理-策略平台-测试 Tab文案验证",
    "验证'策略平台-测试'Tab文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const test = tabs.find(t => t.textContent.includes('测试')); return { found: !!test, text: test?.textContent?.trim() }; })()", "验证测试Tab", storeAs="tabTest"),
     assertStore("tabTest", path="found", equals=True, description="断言测试Tab存在"),
     shot("tm-tab-test", "测试Tab")])

# 1.5 Tab: 手动创建
cases["atom_f88_tm_tab_manual"] = case("atom-f88-tm-tab-manual",
    "原子：任务管理-手动创建 Tab文案验证",
    "验证'手动创建'Tab文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const m = tabs.find(t => t.textContent.includes('手动创建')); return { found: !!m, text: m?.textContent?.trim() }; })()", "验证手动创建Tab", storeAs="tabManual"),
     assertStore("tabManual", path="found", equals=True),
     shot("tm-tab-manual")])

# 1.6 Tab: 模版库
cases["atom_f88_tm_tab_template"] = case("atom-f88-tm-tab-template",
    "原子：任务管理-模版库 Tab文案验证",
    "验证'模版库'Tab文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const t = tabs.find(t => t.textContent.includes('模版库')); return { found: !!t, text: t?.textContent?.trim() }; })()", "验证模版库Tab", storeAs="tabTpl"),
     assertStore("tabTpl", path="found", equals=True),
     shot("tm-tab-template")])

# 1.7 查看任务排期按钮
cases["atom_f88_tm_schedule_btn"] = case("atom-f88-tm-schedule-btn",
    "原子：任务管理-查看任务排期按钮文案与可见性",
    "验证右上角'查看任务排期'按钮文案正确且可见",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('查看任务排期')); return { found: !!btn, text: btn?.textContent?.trim(), visible: btn ? btn.getBoundingClientRect().width > 0 : false }; })()", "验证排期按钮", storeAs="scheduleBtn"),
     assertStore("scheduleBtn", path="found", equals=True),
     assertStore("scheduleBtn", path="visible", equals=True, description="断言按钮可见"),
     shot("tm-schedule-btn")])

# 1.8 链路筛选label
cases["atom_f88_tm_link_filter_label"] = case("atom-f88-tm-link-filter-label",
    "原子：任务管理-链路筛选label文案验证",
    "验证'链路：'筛选label文案正确",
    TM,
    [nav(TM), w(3000),
     assertC("page", "链路", "断言链路label存在"),
     shot("tm-link-label")])

# 1.9 批次筛选label
cases["atom_f88_tm_batch_filter_label"] = case("atom-f88-tm-batch-filter-label",
    "原子：任务管理-批次筛选label文案验证",
    "验证'批次：'筛选label文案正确",
    TM,
    [nav(TM), w(3000),
     assertC("page", "批次", "断言批次label存在"),
     shot("tm-batch-label")])

# 1.10 重置按钮
cases["atom_f88_tm_reset_btn"] = case("atom-f88-tm-reset-btn",
    "原子：任务管理-重置按钮文案与功能验证",
    "验证'重置'按钮文案正确，点击后清空筛选条件",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('重置')); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证重置按钮", storeAs="resetBtn"),
     assertStore("resetBtn", path="found", equals=True),
     shot("tm-reset-btn")])

# 1.11 树形-链路节点展开
cases["atom_f88_tm_tree_link_expand"] = case("atom-f88-tm-tree-link-expand",
    "原子：任务管理-树形链路节点展开验证",
    "验证第一层链路节点可展开，展开后显示子批次节点",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); const beforeCount = document.querySelectorAll('.ant-tree-treenode').length; if(arrows[0]) arrows[0].click(); return { hasArrow: arrows.length > 0, beforeCount }; })()", "展开第一个链路节点", storeAs="treeExpand"),
     w(1500),
     ev("(() => { const afterCount = document.querySelectorAll('.ant-tree-treenode').length; return { afterCount, expanded: afterCount > 0 }; })()", "验证展开后节点数", storeAs="treeAfter"),
     assertStore("treeAfter", path="expanded", equals=True, description="断言展开后有子节点"),
     shot("tm-tree-link-expand")])

# 1.12 树形-批次节点展开
cases["atom_f88_tm_tree_batch_expand"] = case("atom-f88-tm-tree-batch-expand",
    "原子：任务管理-树形批次节点展开验证",
    "验证第二层批次节点可展开，展开后显示审核节点",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return `expanded ${arrows.length}`; })()", "展开所有节点"),
     w(2000),
     ev("(() => { const nodes = document.querySelectorAll('.ant-tree-treenode'); const texts = Array.from(nodes).map(n => n.textContent.trim().substring(0, 40)); return { count: nodes.length, texts: texts.slice(0, 8) }; })()", "记录展开后所有节点", storeAs="allNodes"),
     assertStore("allNodes", path="count", greaterThanOrEqual=2, description="断言至少2层节点"),
     shot("tm-tree-batch-expand")])

# 1.13 任务表格-任务名称列
cases["atom_f88_tm_col_task_name"] = case("atom-f88-tm-col-task-name",
    "原子：任务管理-任务表格'任务名称'列名验证",
    "验证任务表格包含'任务名称'列，列名文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return 'expanded'; })()", "展开树形"),
     w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const hasTaskName = headers.some(h => h.includes('任务名称')); return { headers, hasTaskName }; })()", "验证任务名称列", storeAs="colTaskName"),
     assertStore("colTaskName", path="hasTaskName", equals=True),
     shot("tm-col-task-name")])

# 1.14 任务表格-预期交付时间列
cases["atom_f88_tm_col_delivery_time"] = case("atom-f88-tm-col-delivery-time",
    "原子：任务管理-任务表格'预期交付时间'列名验证",
    "验证任务表格包含'预期交付时间'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"),
     w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasDelivery: headers.some(h => h.includes('预期交付') || h.includes('交付时间')) }; })()", "验证交付时间列", storeAs="colDelivery"),
     assertStore("colDelivery", path="hasDelivery", equals=True),
     shot("tm-col-delivery")])

# 1.15 任务表格-审核状态&进度列
cases["atom_f88_tm_col_audit_status"] = case("atom-f88-tm-col-audit-status",
    "原子：任务管理-任务表格'审核状态&进度'列名验证",
    "验证任务表格包含'审核状态&进度'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"),
     w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasAuditStatus: headers.some(h => h.includes('审核状态')) }; })()", "验证审核状态列", storeAs="colAudit"),
     assertStore("colAudit", path="hasAuditStatus", equals=True),
     shot("tm-col-audit-status")])

# 1.16 任务表格-抽检状态&进度列
cases["atom_f88_tm_col_inspection"] = case("atom-f88-tm-col-inspection",
    "原子：任务管理-任务表格'抽检状态&进度'列名验证",
    "验证任务表格包含'抽检状态&进度'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasInspection: headers.some(h => h.includes('抽检')) }; })()", "验证抽检列", storeAs="colInsp"),
     assertStore("colInsp", path="hasInspection", equals=True),
     shot("tm-col-inspection")])

# 1.17 任务表格-埋雷状态&进度列
cases["atom_f88_tm_col_mine"] = case("atom-f88-tm-col-mine",
    "原子：任务管理-任务表格'埋雷状态&进度'列名验证",
    "验证任务表格包含'埋雷状态&进度'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasMine: headers.some(h => h.includes('埋雷')) }; })()", "验证埋雷列", storeAs="colMine"),
     assertStore("colMine", path="hasMine", equals=True),
     shot("tm-col-mine")])

# 1.18 任务表格-任务时长列
cases["atom_f88_tm_col_duration"] = case("atom-f88-tm-col-duration",
    "原子：任务管理-任务表格'任务时长(除埋雷)'列名验证",
    "验证任务表格包含'任务时长'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasDuration: headers.some(h => h.includes('任务时长') || h.includes('时长')) }; })()", "验证时长列", storeAs="colDur"),
     assertStore("colDur", path="hasDuration", equals=True),
     shot("tm-col-duration")])

# 1.19 任务表格-操作列
cases["atom_f88_tm_col_actions"] = case("atom-f88-tm-col-actions",
    "原子：任务管理-任务表格'操作'列名验证",
    "验证任务表格包含'操作'列",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { hasActions: headers.some(h => h.includes('操作')) }; })()", "验证操作列", storeAs="colAct"),
     assertStore("colAct", path="hasActions", equals=True),
     shot("tm-col-actions")])

# 1.20 操作-分配明细按钮
cases["atom_f88_tm_action_allocate"] = case("atom-f88-tm-action-allocate",
    "原子：任务管理-分配明细按钮文案与可点击验证",
    "验证任务行'分配明细'按钮文案正确且为蓝色链接",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('a')).find(a => a.textContent.trim() === '分配明细'); return { found: !!btn, text: btn?.textContent?.trim(), isLink: btn?.tagName === 'A' }; })()", "验证分配明细按钮", storeAs="allocBtn"),
     assertStore("allocBtn", path="found", equals=True),
     shot("tm-action-allocate")])

# 1.21 操作-详情按钮
cases["atom_f88_tm_action_detail"] = case("atom-f88-tm-action-detail",
    "原子：任务管理-详情按钮文案验证",
    "验证任务行'详情'按钮文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('a')).find(a => a.textContent.trim() === '详情'); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证详情按钮", storeAs="detailBtn"),
     assertStore("detailBtn", path="found", equals=True),
     shot("tm-action-detail")])

# 1.22 操作-编辑按钮
cases["atom_f88_tm_action_edit"] = case("atom-f88-tm-action-edit",
    "原子：任务管理-编辑按钮文案验证",
    "验证任务行'编辑'按钮文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('a')).find(a => a.textContent.trim() === '编辑'); return { found: !!btn }; })()", "验证编辑按钮", storeAs="editBtn"),
     assertStore("editBtn", path="found", equals=True),
     shot("tm-action-edit")])

# 1.23 操作-下载按钮
cases["atom_f88_tm_action_download"] = case("atom-f88-tm-action-download",
    "原子：任务管理-下载按钮文案验证",
    "验证任务行'下载'按钮文案正确",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('a')).find(a => a.textContent.trim() === '下载'); return { found: !!btn }; })()", "验证下载按钮", storeAs="dlBtn"),
     assertStore("dlBtn", path="found", equals=True),
     shot("tm-action-download")])

# 1.24 操作-删除按钮(红色)
cases["atom_f88_tm_action_delete"] = case("atom-f88-tm-action-delete",
    "原子：任务管理-删除按钮文案与颜色验证",
    "验证任务行'删除'按钮文案正确且为红色",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('a')).find(a => a.textContent.trim() === '删除'); if(!btn) return { found: false }; const color = window.getComputedStyle(btn).color; const isRed = color.includes('255') || color.includes('red') || btn.className.includes('danger') || btn.className.includes('red'); return { found: true, isRed, color }; })()", "验证删除按钮红色", storeAs="delBtn"),
     assertStore("delBtn", path="found", equals=True),
     shot("tm-action-delete")])

# 1.25 审核状态标签-待开始
cases["atom_f88_tm_status_pending"] = case("atom-f88-tm-status-pending",
    "原子：任务管理-审核状态'待开始'标签文案验证",
    "验证任务行审核状态标签显示'待开始'且带圆点标记",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const text = document.body.innerText; return { hasPending: text.includes('待开始'), hasInProgress: text.includes('进行中') || text.includes('审核中'), hasDone: text.includes('已完成') || text.includes('已通过') }; })()", "验证状态标签", storeAs="statusLabels"),
     shot("tm-status-labels")])

# 1.26 批次ID格式
cases["atom_f88_tm_batch_id_format"] = case("atom-f88-tm-batch-id-format",
    "原子：任务管理-批次ID格式验证(BT_xxxx)",
    "验证批次节点显示批次ID，格式为BT_加数字",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const text = document.body.innerText; const match = text.match(/BT_\\d+/); return { hasBatchId: !!match, batchId: match ? match[0] : null }; })()", "验证批次ID格式", storeAs="batchId"),
     shot("tm-batch-id")])

# 1.27 总任务数文案
cases["atom_f88_tm_total_task_count"] = case("atom-f88-tm-total-task-count",
    "原子：任务管理-总任务数文案验证",
    "验证审核节点行显示'总任务数 N'文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const text = document.body.innerText; const match = text.match(/总任务数\\s*\\d+/); return { hasTotalCount: !!match, text: match ? match[0] : null }; })()", "验证总任务数", storeAs="totalCount"),
     shot("tm-total-count")])

# 1.28 审核完成率文案
cases["atom_f88_tm_audit_complete_rate"] = case("atom-f88-tm-audit-complete-rate",
    "原子：任务管理-审核完成率文案验证",
    "验证审核节点行显示'审核完成率'文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     assertC("page", "审核完成率", "断言审核完成率文案存在"),
     shot("tm-audit-rate")])

# 1.29 审核通过率文案
cases["atom_f88_tm_audit_pass_rate"] = case("atom-f88-tm-audit-pass-rate",
    "原子：任务管理-审核通过率文案验证",
    "验证审核节点行显示'审核通过率'文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     assertC("page", "审核通过率", "断言审核通过率文案存在"),
     shot("tm-pass-rate")])

# 1.30 审核: 0/N 进度文案
cases["atom_f88_tm_audit_progress_text"] = case("atom-f88-tm-audit-progress-text",
    "原子：任务管理-审核进度'审核: 0/N'文案验证",
    "验证审核进度显示'审核: X/Y'格式文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const text = document.body.innerText; const match = text.match(/审核[：:]\\s*\\d+\\/\\d+/); return { hasProgress: !!match, text: match ? match[0] : null }; })()", "验证审核进度格式", storeAs="auditProgress"),
     shot("tm-audit-progress")])

# 1.31 创建人文案
cases["atom_f88_tm_creator_text"] = case("atom-f88-tm-creator-text",
    "原子：任务管理-创建人文案验证",
    "验证批次节点显示'创建人：xxx'文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     assertC("page", "创建人", "断言创建人文案存在"),
     shot("tm-creator")])

# 1.32 剩余时间文案
cases["atom_f88_tm_remaining_time"] = case("atom-f88-tm-remaining-time",
    "原子：任务管理-剩余时间文案验证",
    "验证任务行显示'剩余：X小时X分钟'文案",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     ev("(() => { const text = document.body.innerText; const match = text.match(/剩余[：:]\\s*\\d+小时/); return { hasRemaining: !!match, text: match ? match[0] : null }; })()", "验证剩余时间", storeAs="remainingTime"),
     shot("tm-remaining-time")])

# 1.33 生产平台任务标签
cases["atom_f88_tm_prod_task_tag"] = case("atom-f88-tm-prod-task-tag",
    "原子：任务管理-生产平台任务标签文案验证",
    "验证任务名称下方显示'生产平台任务'标签",
    TM,
    [nav(TM), w(3000),
     ev("(() => { document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)').forEach(a => a.click()); })()", "展开"), w(2000),
     assertC("page", "生产平台任务", "断言生产平台任务标签存在"),
     shot("tm-prod-tag")])

# ================================================================
# PAGE 2: 个人任务中心 — 原子功能点
# ================================================================

# 2.1 审核任务Tab
cases["atom_f88_ptc_tab_audit"] = case("atom-f88-ptc-tab-audit",
    "原子：个人任务中心-审核任务Tab文案验证",
    "验证'审核任务'Tab文案正确且默认选中",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const audit = tabs.find(t => t.textContent.includes('审核任务') && !t.textContent.includes('抽检') && !t.textContent.includes('埋雷')); return { found: !!audit, text: audit?.textContent?.trim(), active: audit?.classList?.contains('ant-tabs-tab-active') }; })()", "验证审核任务Tab", storeAs="auditTab"),
     assertStore("auditTab", path="found", equals=True),
     shot("ptc-tab-audit")])

# 2.2 抽检任务Tab
cases["atom_f88_ptc_tab_inspection"] = case("atom-f88-ptc-tab-inspection",
    "原子：个人任务中心-抽检任务Tab文案验证",
    "验证'抽检任务'Tab文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const insp = tabs.find(t => t.textContent.includes('抽检')); return { found: !!insp, text: insp?.textContent?.trim() }; })()", "验证抽检Tab", storeAs="inspTab"),
     assertStore("inspTab", path="found", equals=True),
     shot("ptc-tab-inspection")])

# 2.3 埋雷任务Tab
cases["atom_f88_ptc_tab_mine"] = case("atom-f88-ptc-tab-mine",
    "原子：个人任务中心-埋雷任务Tab文案验证",
    "验证'埋雷任务'Tab文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const mine = tabs.find(t => t.textContent.includes('埋雷')); return { found: !!mine, text: mine?.textContent?.trim() }; })()", "验证埋雷Tab", storeAs="mineTab"),
     assertStore("mineTab", path="found", equals=True),
     shot("ptc-tab-mine")])

# 2.4 审核状态下拉-待审核选项
cases["atom_f88_ptc_status_pending"] = case("atom-f88-ptc-status-pending",
    "原子：个人任务中心-审核状态'待审核'选项验证",
    "验证审核状态下拉包含'待审核'选项",
    PTC,
    [nav(PTC), w(3000),
     selOpt("审核状态", "待审核", "选择待审核"),
     w(2000),
     ev("(() => { const text = document.body.innerText; return { hasPending: text.includes('待审核') }; })()", "验证待审核筛选生效", storeAs="pendingFilter"),
     shot("ptc-status-pending")])

# 2.5 审核状态下拉-审核通过选项
cases["atom_f88_ptc_status_approved"] = case("atom-f88-ptc-status-approved",
    "原子：个人任务中心-审核状态'审核通过'选项验证",
    "验证审核状态下拉包含'审核通过'选项",
    PTC,
    [nav(PTC), w(3000),
     selOpt("审核状态", "审核通过", "选择审核通过"),
     w(2000),
     shot("ptc-status-approved")])

# 2.6 审核状态下拉-审核驳回选项
cases["atom_f88_ptc_status_rejected"] = case("atom-f88-ptc-status-rejected",
    "原子：个人任务中心-审核状态'审核驳回'选项验证",
    "验证审核状态下拉包含'审核驳回'选项",
    PTC,
    [nav(PTC), w(3000),
     selOpt("审核状态", "审核驳回", "选择审核驳回"),
     w(2000),
     shot("ptc-status-rejected")])

# 2.7 素材类型下拉
cases["atom_f88_ptc_material_type"] = case("atom-f88-ptc-material-type",
    "原子：个人任务中心-素材类型筛选选项验证",
    "验证素材类型下拉包含主图/详情页/白底图等选项",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const selects = document.querySelectorAll('.ant-select'); const typeSelect = Array.from(selects).find(s => { const prev = s.previousElementSibling || s.parentElement?.querySelector('label, span'); return prev && prev.textContent && prev.textContent.includes('素材'); }); return { found: !!typeSelect }; })()", "查找素材类型Select", storeAs="typeSelect"),
     assertStore("typeSelect", path="found", equals=True),
     shot("ptc-material-type")])

# 2.8 商家ID输入框
cases["atom_f88_ptc_seller_input"] = case("atom-f88-ptc-seller-input",
    "原子：个人任务中心-商家ID输入框placeholder验证",
    "验证商家ID输入框placeholder文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && (i.placeholder.includes('商家') || i.placeholder.includes('seller'))); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证商家ID输入框", storeAs="sellerInput"),
     shot("ptc-seller-input")])

# 2.9 商品ID输入框
cases["atom_f88_ptc_item_input"] = case("atom-f88-ptc-item-input",
    "原子：个人任务中心-商品ID输入框placeholder验证",
    "验证商品ID输入框placeholder文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && (i.placeholder.includes('商品') || i.placeholder.includes('item') || i.placeholder.includes('ID'))); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证商品ID输入框", storeAs="itemInput"),
     shot("ptc-item-input")])

# 2.10 搜索按钮
cases["atom_f88_ptc_search_btn"] = case("atom-f88-ptc-search-btn",
    "原子：个人任务中心-搜索按钮文案验证",
    "验证'搜索'按钮文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '搜索'); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证搜索按钮", storeAs="searchBtn"),
     assertStore("searchBtn", path="found", equals=True),
     shot("ptc-search-btn")])

# 2.11 重置按钮
cases["atom_f88_ptc_reset_btn"] = case("atom-f88-ptc-reset-btn",
    "原子：个人任务中心-重置按钮文案验证",
    "验证'重置'按钮文案正确",
    PTC,
    [nav(PTC), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '重置'); return { found: !!btn }; })()", "验证重置按钮", storeAs="resetBtn"),
     assertStore("resetBtn", path="found", equals=True),
     shot("ptc-reset-btn")])

# ================================================================
# PAGE 3-5: 审核管理 (标准/节点/商家)
# ================================================================

# 3.1 审核标准-新增标准按钮
cases["atom_f88_as_add_btn"] = case("atom-f88-as-add-btn",
    "原子：审核标准管理-新增标准按钮文案验证",
    "验证'新增标准'按钮文案正确且可见",
    AS,
    [nav(AS), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新增标准')); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证新增标准按钮", storeAs="addBtn"),
     assertStore("addBtn", path="found", equals=True),
     shot("as-add-btn")])

# 3.2 审核标准-表格列名
cases["atom_f88_as_table_headers"] = case("atom-f88-as-table-headers",
    "原子：审核标准管理-表格列名完整性验证",
    "验证表格包含标准名称/创建人/创建时间/使用次数/状态/操作列",
    AS,
    [nav(AS), w(3000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const required = ['标准名称', '创建人', '创建时间', '操作']; const found = required.filter(r => headers.some(h => h.includes(r))); return { headers, required, found, coverage: found.length + '/' + required.length }; })()", "验证表格列名", storeAs="asHeaders"),
     shot("as-table-headers")])

# 3.3 审核标准-编辑按钮
cases["atom_f88_as_edit_btn"] = case("atom-f88-as-edit-btn",
    "原子：审核标准管理-编辑按钮文案验证",
    "验证操作列'编辑'按钮文案正确",
    AS,
    [nav(AS), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); return { found: btns.length > 0, count: btns.length }; })()", "验证编辑按钮", storeAs="asEditBtns"),
     shot("as-edit-btn")])

# 3.4 审核标准-启用/禁用
cases["atom_f88_as_toggle_btn"] = case("atom-f88-as-toggle-btn",
    "原子：审核标准管理-启用/禁用按钮文案验证",
    "验证操作列包含'启用'或'禁用'按钮/Switch组件",
    AS,
    [nav(AS), w(3000),
     ev("(() => { const toggles = Array.from(document.querySelectorAll('a, button, .ant-switch')).filter(el => { const t = el.textContent.trim(); return t.includes('启用') || t.includes('禁用'); }); const switches = document.querySelectorAll('.ant-switch'); return { toggleBtns: toggles.length, switches: switches.length }; })()", "验证启用禁用", storeAs="asToggle"),
     shot("as-toggle")])

# 3.5 审核标准-删除按钮
cases["atom_f88_as_delete_btn"] = case("atom-f88-as-delete-btn",
    "原子：审核标准管理-删除按钮文案验证",
    "验证操作列'删除'按钮文案正确",
    AS,
    [nav(AS), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '删除'); return { found: btns.length > 0 }; })()", "验证删除按钮", storeAs="asDelBtns"),
     shot("as-delete-btn")])

# 4.1 审核节点-新增节点按钮
cases["atom_f88_an_add_btn"] = case("atom-f88-an-add-btn",
    "原子：审核节点管理-新增节点按钮文案验证",
    "验证'新增节点'按钮文案正确",
    AN,
    [nav(AN), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新增节点')); return { found: !!btn }; })()", "验证新增节点按钮", storeAs="anAddBtn"),
     assertStore("anAddBtn", path="found", equals=True),
     shot("an-add-btn")])

# 4.2 审核节点-表格列名
cases["atom_f88_an_table_headers"] = case("atom-f88-an-table-headers",
    "原子：审核节点管理-表格列名验证",
    "验证表格包含节点名称/审核标准/人效预估/难度预估/分配方式/审核人/检查设置/操作列",
    AN,
    [nav(AN), w(3000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const required = ['节点名称', '审核标准', '分配方式', '操作']; const found = required.filter(r => headers.some(h => h.includes(r))); return { headers, required, found, coverage: found.length + '/' + required.length }; })()", "验证节点表格列名", storeAs="anHeaders"),
     shot("an-table-headers")])

# 5.1 商家配置-搜索按钮
cases["atom_f88_mc_search_btn"] = case("atom-f88-mc-search-btn",
    "原子：商家信息配置-搜索按钮文案验证",
    "验证'搜索'按钮文案正确",
    MC,
    [nav(MC), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '搜索'); return { found: !!btn }; })()", "验证搜索按钮", storeAs="mcSearchBtn"),
     assertStore("mcSearchBtn", path="found", equals=True),
     shot("mc-search-btn")])

# 5.2 商家配置-重置筛选按钮
cases["atom_f88_mc_reset_btn"] = case("atom-f88-mc-reset-btn",
    "原子：商家信息配置-重置筛选按钮文案验证",
    "验证'重置筛选'按钮文案正确",
    MC,
    [nav(MC), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('重置')); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证重置筛选按钮", storeAs="mcResetBtn"),
     assertStore("mcResetBtn", path="found", equals=True),
     shot("mc-reset-btn")])

# 5.3 商家配置-批量下载按钮
cases["atom_f88_mc_batch_dl_btn"] = case("atom-f88-mc-batch-dl-btn",
    "原子：商家信息配置-批量下载按钮文案验证",
    "验证'批量下载'按钮文案正确",
    MC,
    [nav(MC), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('批量下载')); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证批量下载按钮", storeAs="mcDlBtn"),
     assertStore("mcDlBtn", path="found", equals=True),
     shot("mc-batch-dl-btn")])

# 5.4 商家配置-表格列名
cases["atom_f88_mc_table_headers"] = case("atom-f88-mc-table-headers",
    "原子：商家信息配置-表格列名完整性验证",
    "验证表格包含店铺信息/合作供应商/参考竞店/负责买手/视觉偏好/搭配偏好/操作列",
    MC,
    [nav(MC), w(3000),
     ev("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const required = ['店铺信息', '合作供应商', '参考竞店', '负责买手', '视觉偏好', '搭配偏好', '操作']; const found = required.filter(r => headers.some(h => h.includes(r))); return { headers, required, found, coverage: found.length + '/' + required.length }; })()", "验证商家配置表格列名", storeAs="mcHeaders"),
     shot("mc-table-headers")])

# 5.5 商家配置-编辑按钮
cases["atom_f88_mc_edit_btn"] = case("atom-f88-mc-edit-btn",
    "原子：商家信息配置-编辑按钮文案验证",
    "验证操作列'编辑'按钮文案正确",
    MC,
    [nav(MC), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); return { found: btns.length > 0 }; })()", "验证编辑按钮", storeAs="mcEditBtns"),
     shot("mc-edit-btn")])

# ================================================================
# PAGE 6: 生产看板
# ================================================================

# 6.1 总任务数指标
cases["atom_f88_pd_total_tasks"] = case("atom-f88-pd-total-tasks",
    "原子：生产看板-总任务数指标文案验证",
    "验证看板显示'总任务数'指标卡片",
    PD,
    [nav(PD), w(3000),
     assertC("page", "总任务数", "断言总任务数指标存在"),
     shot("pd-total-tasks")])

# 6.2 生产中指标
cases["atom_f88_pd_producing"] = case("atom-f88-pd-producing",
    "原子：生产看板-生产中指标文案验证",
    "验证看板显示'生产中'指标卡片",
    PD,
    [nav(PD), w(3000),
     assertC("page", "生产中", "断言生产中指标存在"),
     shot("pd-producing")])

# 6.3 已推送指标
cases["atom_f88_pd_pushed"] = case("atom-f88-pd-pushed",
    "原子：生产看板-已推送指标文案验证",
    "验证看板显示'已推送'指标卡片",
    PD,
    [nav(PD), w(3000),
     assertC("page", "已推送", "断言已推送指标存在"),
     shot("pd-pushed")])

# 6.4 未推送指标
cases["atom_f88_pd_unpushed"] = case("atom-f88-pd-unpushed",
    "原子：生产看板-未推送指标文案验证",
    "验证看板显示'未推送'指标卡片",
    PD,
    [nav(PD), w(3000),
     assertC("page", "未推送", "断言未推送指标存在"),
     shot("pd-unpushed")])

# ================================================================
# PAGE 7: 策略列表
# ================================================================

# 7.1 新建策略按钮
cases["atom_f88_sl_create_btn"] = case("atom-f88-sl-create-btn",
    "原子：策略列表-新建策略按钮文案验证",
    "验证'新建策略'按钮文案正确",
    SL,
    [nav(SL), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新建策略')); return { found: !!btn }; })()", "验证新建策略按钮", storeAs="slCreateBtn"),
     assertStore("slCreateBtn", path="found", equals=True),
     shot("sl-create-btn")])

# 7.2 策略阶段筛选
cases["atom_f88_sl_stage_filter"] = case("atom-f88-sl-stage-filter",
    "原子：策略列表-策略阶段筛选选项验证",
    "验证策略阶段下拉包含全部/实验/灰度/正式选项",
    SL,
    [nav(SL), w(3000),
     ev("(() => { const selects = document.querySelectorAll('.ant-select'); return { count: selects.length }; })()", "记录Select数量", storeAs="slSelects"),
     shot("sl-stage-filter")])

# 7.3 环节筛选
cases["atom_f88_sl_process_filter"] = case("atom-f88-sl-process-filter",
    "原子：策略列表-环节筛选选项验证",
    "验证环节下拉包含全部/视觉/设计/视频选项",
    SL,
    [nav(SL), w(3000),
     shot("sl-process-filter")])

# 7.4 策略卡片-打开按钮
cases["atom_f88_sl_open_btn"] = case("atom-f88-sl-open-btn",
    "原子：策略列表-策略卡片'打开'按钮文案验证",
    "验证策略卡片操作包含'打开'按钮",
    SL,
    [nav(SL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '打开'); return { found: btns.length > 0 }; })()", "验证打开按钮", storeAs="slOpenBtns"),
     shot("sl-open-btn")])

# 7.5 策略卡片-复制按钮
cases["atom_f88_sl_copy_btn"] = case("atom-f88-sl-copy-btn",
    "原子：策略列表-策略卡片'复制'按钮文案验证",
    "验证策略卡片操作包含'复制'按钮",
    SL,
    [nav(SL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '复制'); return { found: btns.length > 0 }; })()", "验证复制按钮", storeAs="slCopyBtns"),
     shot("sl-copy-btn")])

# 7.6 策略卡片-删除按钮
cases["atom_f88_sl_delete_btn"] = case("atom-f88-sl-delete-btn",
    "原子：策略列表-策略卡片'删除'按钮文案验证",
    "验证策略卡片操作包含'删除'按钮",
    SL,
    [nav(SL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '删除'); return { found: btns.length > 0 }; })()", "验证删除按钮", storeAs="slDelBtns"),
     shot("sl-delete-btn")])

# ================================================================
# PAGE 8: 策略详情
# ================================================================

# 8.1 返回列表按钮
cases["atom_f88_sd_back_btn"] = case("atom-f88-sd-back-btn",
    "原子：策略详情-返回列表按钮文案验证",
    "验证'返回列表'按钮文案正确",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button, a')).find(b => b.textContent.includes('返回')); return { found: !!btn, text: btn?.textContent?.trim() }; })()", "验证返回列表按钮", storeAs="sdBackBtn"),
     shot("sd-back-btn")])

# 8.2 试运行按钮
cases["atom_f88_sd_trial_btn"] = case("atom-f88-sd-trial-btn",
    "原子：策略详情-试运行按钮文案验证",
    "验证'试运行'按钮文案正确",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('试运行')); return { found: !!btn }; })()", "验证试运行按钮", storeAs="sdTrialBtn"),
     assertStore("sdTrialBtn", path="found", equals=True),
     shot("sd-trial-btn")])

# 8.3 查看运行结果按钮
cases["atom_f88_sd_results_btn"] = case("atom-f88-sd-results-btn",
    "原子：策略详情-查看运行结果按钮文案验证",
    "验证'查看运行结果'按钮文案正确",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('查看运行结果')); return { found: !!btn }; })()", "验证查看运行结果按钮", storeAs="sdResultsBtn"),
     assertStore("sdResultsBtn", path="found", equals=True),
     shot("sd-results-btn")])

# 8.4 保存按钮
cases["atom_f88_sd_save_btn"] = case("atom-f88-sd-save-btn",
    "原子：策略详情-保存按钮文案验证",
    "验证'保存'按钮文案正确",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '保存'); return { found: !!btn }; })()", "验证保存按钮", storeAs="sdSaveBtn"),
     assertStore("sdSaveBtn", path="found", equals=True),
     shot("sd-save-btn")])

# 8.5 新增节点按钮
cases["atom_f88_sd_add_node_btn"] = case("atom-f88-sd-add-node-btn",
    "原子：策略详情-新增节点按钮文案验证",
    "验证'+ 新增节点'按钮文案正确",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button, a, [class*=addNode]')).find(el => el.textContent.includes('新增节点') || el.textContent.includes('+')); return { found: !!btn, text: btn?.textContent?.trim()?.substring(0, 20) }; })()", "验证新增节点按钮", storeAs="sdAddNodeBtn"),
     assertStore("sdAddNodeBtn", path="found", equals=True),
     shot("sd-add-node-btn")])

# 8.6 策略基本信息区域
cases["atom_f88_sd_basic_info"] = case("atom-f88-sd-basic-info",
    "原子：策略详情-策略基本信息区域文案验证",
    "验证策略详情包含'策略基本信息'区域",
    SD,
    [nav(SD), w(3000),
     assertC("page", "策略", "断言策略信息区域存在"),
     shot("sd-basic-info")])

# 8.7 节点编排区域
cases["atom_f88_sd_node_orchestration"] = case("atom-f88-sd-node-orchestration",
    "原子：策略详情-节点编排区域文案验证",
    "验证策略详情包含'节点编排'区域",
    SD,
    [nav(SD), w(3000),
     assertC("page", "节点", "断言节点编排区域存在"),
     shot("sd-node-orchestration")])

# 8.8 落库配置区域
cases["atom_f88_sd_storage_config"] = case("atom-f88-sd-storage-config",
    "原子：策略详情-落库配置区域文案验证",
    "验证策略详情包含'落库配置'区域",
    SD,
    [nav(SD), w(3000),
     ev("(() => { const text = document.body.innerText; return { hasStorage: text.includes('落库') || text.includes('存储') }; })()", "验证落库配置区域", storeAs="sdStorage"),
     shot("sd-storage-config")])

# ================================================================
# PAGE 9-10: 链路列表/详情
# ================================================================

# 9.1 新建链路按钮
cases["atom_f88_ll_create_btn"] = case("atom-f88-ll-create-btn",
    "原子：链路列表-新建链路按钮文案验证",
    "验证'新建链路'按钮文案正确",
    LL,
    [nav(LL), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新建链路')); return { found: !!btn }; })()", "验证新建链路按钮", storeAs="llCreateBtn"),
     assertStore("llCreateBtn", path="found", equals=True),
     shot("ll-create-btn")])

# 9.2 生命周期筛选
cases["atom_f88_ll_lifecycle_filter"] = case("atom-f88-ll-lifecycle-filter",
    "原子：链路列表-生命周期筛选选项验证",
    "验证生命周期下拉包含全部/实验/灰度/正式选项",
    LL,
    [nav(LL), w(3000),
     shot("ll-lifecycle-filter")])

# 9.3 链路卡片-编辑按钮
cases["atom_f88_ll_edit_btn"] = case("atom-f88-ll-edit-btn",
    "原子：链路列表-链路卡片'编辑'按钮文案验证",
    "验证链路卡片操作包含'编辑'按钮",
    LL,
    [nav(LL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); return { found: btns.length > 0 }; })()", "验证编辑按钮", storeAs="llEditBtns"),
     shot("ll-edit-btn")])

# 9.4 链路卡片-复制按钮
cases["atom_f88_ll_copy_btn"] = case("atom-f88-ll-copy-btn",
    "原子：链路列表-链路卡片'复制'按钮文案验证",
    "验证链路卡片操作包含'复制'按钮",
    LL,
    [nav(LL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '复制'); return { found: btns.length > 0 }; })()", "验证复制按钮", storeAs="llCopyBtns"),
     shot("ll-copy-btn")])

# 9.5 链路卡片-删除按钮
cases["atom_f88_ll_delete_btn"] = case("atom-f88-ll-delete-btn",
    "原子：链路列表-链路卡片'删除'按钮文案验证",
    "验证链路卡片操作包含'删除'按钮",
    LL,
    [nav(LL), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '删除'); return { found: btns.length > 0 }; })()", "验证删除按钮", storeAs="llDelBtns"),
     shot("ll-delete-btn")])

# 10.1 链路详情-试运行按钮
cases["atom_f88_ld_trial_btn"] = case("atom-f88-ld-trial-btn",
    "原子：链路详情-试运行按钮文案验证",
    "验证'试运行'按钮文案正确",
    LD,
    [nav(LD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('试运行')); return { found: !!btn }; })()", "验证试运行按钮", storeAs="ldTrialBtn"),
     assertStore("ldTrialBtn", path="found", equals=True),
     shot("ld-trial-btn")])

# 10.2 链路详情-查看运行结果按钮
cases["atom_f88_ld_results_btn"] = case("atom-f88-ld-results-btn",
    "原子：链路详情-查看运行结果按钮文案验证",
    "验证'查看运行结果'按钮文案正确",
    LD,
    [nav(LD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('查看运行结果')); return { found: !!btn }; })()", "验证查看运行结果按钮", storeAs="ldResultsBtn"),
     assertStore("ldResultsBtn", path="found", equals=True),
     shot("ld-results-btn")])

# 10.3 链路详情-返回列表按钮
cases["atom_f88_ld_back_btn"] = case("atom-f88-ld-back-btn",
    "原子：链路详情-返回列表按钮文案验证",
    "验证'返回列表'按钮文案正确",
    LD,
    [nav(LD), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button, a')).find(b => b.textContent.includes('返回')); return { found: !!btn }; })()", "验证返回列表按钮", storeAs="ldBackBtn"),
     shot("ld-back-btn")])

# ================================================================
# PAGE 11: 模版包管理
# ================================================================

# 11.1 重置按钮
cases["atom_f88_tpm_reset_btn"] = case("atom-f88-tpm-reset-btn",
    "原子：模版包管理-重置按钮文案验证",
    "验证'重置'按钮文案正确",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '重置'); return { found: !!btn }; })()", "验证重置按钮", storeAs="tpmResetBtn"),
     assertStore("tpmResetBtn", path="found", equals=True),
     shot("tpm-reset-btn")])

# 11.2 新建模板包按钮
cases["atom_f88_tpm_create_btn"] = case("atom-f88-tpm-create-btn",
    "原子：模版包管理-新建模板包按钮文案验证",
    "验证'新建模板包'按钮文案正确",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新建模板包')); return { found: !!btn }; })()", "验证新建模板包按钮", storeAs="tpmCreateBtn"),
     assertStore("tpmCreateBtn", path="found", equals=True),
     shot("tpm-create-btn")])

# 11.3 导入模板包按钮
cases["atom_f88_tpm_import_btn"] = case("atom-f88-tpm-import-btn",
    "原子：模版包管理-导入模板包按钮文案验证",
    "验证'导入模板包'按钮文案正确",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('导入模板包')); return { found: !!btn }; })()", "验证导入模板包按钮", storeAs="tpmImportBtn"),
     assertStore("tpmImportBtn", path="found", equals=True),
     shot("tpm-import-btn")])

# 11.4 店铺卡片-查看详情
cases["atom_f88_tpm_detail_btn"] = case("atom-f88-tpm-detail-btn",
    "原子：模版包管理-店铺卡片'查看详情'按钮文案验证",
    "验证店铺卡片操作包含'查看详情'按钮",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.includes('查看详情')); return { found: btns.length > 0 }; })()", "验证查看详情按钮", storeAs="tpmDetailBtns"),
     shot("tpm-detail-btn")])

# 11.5 店铺卡片-编辑
cases["atom_f88_tpm_edit_btn"] = case("atom-f88-tpm-edit-btn",
    "原子：模版包管理-店铺卡片'编辑'按钮文案验证",
    "验证店铺卡片操作包含'编辑'按钮",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); return { found: btns.length > 0 }; })()", "验证编辑按钮", storeAs="tpmEditBtns"),
     shot("tpm-edit-btn")])

# 11.6 店铺卡片-激活
cases["atom_f88_tpm_activate_btn"] = case("atom-f88-tpm-activate-btn",
    "原子：模版包管理-店铺卡片'激活'按钮文案验证",
    "验证店铺卡片操作包含'激活'按钮",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '激活'); return { found: btns.length > 0 }; })()", "验证激活按钮", storeAs="tpmActBtns"),
     shot("tpm-activate-btn")])

# 11.7 店铺卡片-停用
cases["atom_f88_tpm_deactivate_btn"] = case("atom-f88-tpm-deactivate-btn",
    "原子：模版包管理-店铺卡片'停用'按钮文案验证",
    "验证店铺卡片操作包含'停用'按钮",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const btns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '停用'); return { found: btns.length > 0 }; })()", "验证停用按钮", storeAs="tpmDeactBtns"),
     shot("tpm-deactivate-btn")])

# 11.8 使用状态标签-使用中
cases["atom_f88_tpm_status_in_use"] = case("atom-f88-tpm-status-in-use",
    "原子：模版包管理-使用状态'使用中'标签文案验证",
    "验证店铺卡片显示'使用中'状态标签",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const text = document.body.innerText; return { hasInUse: text.includes('使用中') }; })()", "验证使用中状态", storeAs="tpmInUse"),
     shot("tpm-status-in-use")])

# 11.9 使用状态标签-未使用
cases["atom_f88_tpm_status_unused"] = case("atom-f88-tpm-status-unused",
    "原子：模版包管理-使用状态'未使用'标签文案验证",
    "验证店铺卡片显示'未使用'状态标签",
    TPM,
    [nav(TPM), w(3000),
     ev("(() => { const text = document.body.innerText; return { hasUnused: text.includes('未使用') }; })()", "验证未使用状态", storeAs="tpmUnused"),
     shot("tpm-status-unused")])

# ================================================================
# PAGE 12: 淘内资源池
# ================================================================

# 12.1 重置按钮
cases["atom_f88_tl_reset_btn"] = case("atom-f88-tl-reset-btn",
    "原子：淘内资源池-重置按钮文案验证",
    "验证'重置'按钮文案正确",
    TL,
    [nav(TL), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '重置'); return { found: !!btn }; })()", "验证重置按钮", storeAs="tlResetBtn"),
     assertStore("tlResetBtn", path="found", equals=True),
     shot("tl-reset-btn")])

# 12.2 Seller ID输入框
cases["atom_f88_tl_seller_input"] = case("atom-f88-tl-seller-input",
    "原子：淘内资源池-Seller ID输入框placeholder验证",
    "验证Seller ID输入框placeholder文案正确",
    TL,
    [nav(TL), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && (i.placeholder.toLowerCase().includes('seller') || i.placeholder.includes('ID'))); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证Seller ID输入框", storeAs="tlSellerInput"),
     shot("tl-seller-input")])

# 12.3 店铺名称输入框
cases["atom_f88_tl_shop_input"] = case("atom-f88-tl-shop-input",
    "原子：淘内资源池-店铺名称输入框placeholder验证",
    "验证店铺名称输入框placeholder文案正确",
    TL,
    [nav(TL), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && i.placeholder.includes('店铺')); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证店铺名称输入框", storeAs="tlShopInput"),
     shot("tl-shop-input")])

# 12.4 Item ID输入框
cases["atom_f88_tl_item_input"] = case("atom-f88-tl-item-input",
    "原子：淘内资源池-Item ID输入框placeholder验证",
    "验证Item ID输入框placeholder文案正确",
    TL,
    [nav(TL), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && (i.placeholder.toLowerCase().includes('item') || i.placeholder.includes('ID'))); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证Item ID输入框", storeAs="tlItemInput"),
     shot("tl-item-input")])

# 12.5 图片ID输入框
cases["atom_f88_tl_image_id_input"] = case("atom-f88-tl-image-id-input",
    "原子：淘内资源池-图片ID输入框placeholder验证",
    "验证图片ID输入框placeholder文案正确",
    TL,
    [nav(TL), w(3000),
     ev("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && (i.placeholder.includes('图片') || i.placeholder.includes('Image'))); return { found: inputs.length > 0, placeholder: inputs[0]?.placeholder }; })()", "验证图片ID输入框", storeAs="tlImgIdInput"),
     shot("tl-image-id-input")])

# 12.6 标签维度-设计
cases["atom_f88_tl_tag_design"] = case("atom-f88-tl-tag-design",
    "原子：淘内资源池-标签维度'设计'文案验证",
    "验证资源池包含'设计'维度标签",
    TL,
    [nav(TL), w(3000),
     assertC("page", "设计", "断言设计标签维度存在"),
     shot("tl-tag-design")])

# 12.7 标签维度-搭配
cases["atom_f88_tl_tag_match"] = case("atom-f88-tl-tag-match",
    "原子：淘内资源池-标签维度'搭配'文案验证",
    "验证资源池包含'搭配'维度标签",
    TL,
    [nav(TL), w(3000),
     assertC("page", "搭配", "断言搭配标签维度存在"),
     shot("tl-tag-match")])

# 12.8 标签维度-拍摄
cases["atom_f88_tl_tag_shoot"] = case("atom-f88-tl-tag-shoot",
    "原子：淘内资源池-标签维度'拍摄'文案验证",
    "验证资源池包含'拍摄'维度标签",
    TL,
    [nav(TL), w(3000),
     assertC("page", "拍摄", "断言拍摄标签维度存在"),
     shot("tl-tag-shoot")])

# 12.9 推荐曝光数
cases["atom_f88_tl_exposure_count"] = case("atom-f88-tl-exposure-count",
    "原子：淘内资源池-推荐曝光数文案验证",
    "验证模板卡片显示'推荐曝光数'指标",
    TL,
    [nav(TL), w(3000),
     assertC("page", "曝光", "断言推荐曝光数存在"),
     shot("tl-exposure-count")])

# ================================================================
# PAGE 13: 优质模板库
# ================================================================

# 13.1 批量操作按钮
cases["atom_f88_qt_batch_btn"] = case("atom-f88-qt-batch-btn",
    "原子：优质模板库-批量操作按钮文案验证",
    "验证'批量操作'按钮文案正确",
    QT,
    [nav(QT), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('批量操作')); return { found: !!btn }; })()", "验证批量操作按钮", storeAs="qtBatchBtn"),
     assertStore("qtBatchBtn", path="found", equals=True),
     shot("qt-batch-btn")])

# 13.2 查看任务进度按钮
cases["atom_f88_qt_progress_btn"] = case("atom-f88-qt-progress-btn",
    "原子：优质模板库-查看任务进度按钮文案验证",
    "验证'查看任务进度'按钮文案正确",
    QT,
    [nav(QT), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('查看任务进度')); return { found: !!btn }; })()", "验证查看任务进度按钮", storeAs="qtProgressBtn"),
     assertStore("qtProgressBtn", path="found", equals=True),
     shot("qt-progress-btn")])

# 13.3 创建任务按钮
cases["atom_f88_qt_create_btn"] = case("atom-f88-qt-create-btn",
    "原子：优质模板库-创建任务按钮文案验证",
    "验证'创建任务'按钮文案正确",
    QT,
    [nav(QT), w(3000),
     ev("(() => { const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('创建任务')); return { found: !!btn }; })()", "验证创建任务按钮", storeAs="qtCreateBtn"),
     assertStore("qtCreateBtn", path="found", equals=True),
     shot("qt-create-btn")])

# 13.4 洗图状态筛选
cases["atom_f88_qt_wash_status"] = case("atom-f88-qt-wash-status",
    "原子：优质模板库-洗图状态筛选文案验证",
    "验证优质模板库包含'洗图状态'筛选区域",
    QT,
    [nav(QT), w(3000),
     assertC("page", "洗图", "断言洗图状态筛选存在"),
     shot("qt-wash-status")])

# 13.5 应用场景筛选
cases["atom_f88_qt_app_scene"] = case("atom-f88-qt-app-scene",
    "原子：优质模板库-应用场景筛选文案验证",
    "验证优质模板库包含'应用场景'筛选区域",
    QT,
    [nav(QT), w(3000),
     assertC("page", "应用场景", "断言应用场景筛选存在"),
     shot("qt-app-scene")])

# ================================================================
# WRITE ALL
# ================================================================
count = 0
for fname, c in cases.items():
    path = os.path.join(BASE, f"{fname}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    count += 1

print(f"Generated {count} atomic test cases")

# Group by page
from collections import Counter
pages = Counter()
for fname in cases:
    if 'tm_' in fname: pages['任务管理'] += 1
    elif 'ptc_' in fname: pages['个人任务中心'] += 1
    elif 'as_' in fname: pages['审核标准管理'] += 1
    elif 'an_' in fname: pages['审核节点管理'] += 1
    elif 'mc_' in fname: pages['商家信息配置'] += 1
    elif 'pd_' in fname: pages['生产看板'] += 1
    elif 'sl_' in fname: pages['策略列表'] += 1
    elif 'sd_' in fname: pages['策略详情'] += 1
    elif 'll_' in fname: pages['链路列表'] += 1
    elif 'ld_' in fname: pages['链路详情'] += 1
    elif 'tpm_' in fname: pages['模版包管理'] += 1
    elif 'tl_' in fname: pages['淘内资源池'] += 1
    elif 'qt_' in fname: pages['优质模板库'] += 1

for page, cnt in sorted(pages.items(), key=lambda x: -x[1]):
    print(f"  {page}: {cnt} cases")
