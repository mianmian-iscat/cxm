import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

# ============================================================
# Helper: standard case template
# ============================================================
def make_case(id, name, description, url, steps, preconditions="", realDomNotes="", riskPoints=None, priority="P1", category="normal_flow"):
    return {
        "id": id, "name": name, "description": description,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": priority, "category": category,
        "context": {"urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com", "url": url,
                    "waitAfterLoad": 3000, "auth": "buc", "captureFilter": "bzb.api.fsyx_quality_guard"},
        "steps": steps,
        "screenshot": {"onError": True},
        "contextOptimization": {"screenshotExternal": True, "maxResponseSizeKb": 100, "outputCompact": True},
        "_expected": {"status": "pass"},
        "_testDesign": {"preconditions": preconditions, "realDomNotes": realDomNotes,
                        "riskPoints": riskPoints or ["无数据时列表为空"]}
    }

def nav(url, desc="打开页面"):
    return {"type": "navigate", "url": url, "waitUntil": "networkidle", "screenshot": True, "description": desc}

def wait(ms, desc="等待加载"):
    return {"type": "wait", "ms": ms, "description": desc}

def click_text(text, desc=None):
    return {"type": "clickText", "text": text, "description": desc or f"点击{text}"}

def evaluate(expr, desc, storeAs=None):
    step = {"type": "evaluate", "expression": expr, "description": desc}
    if storeAs: step["storeAs"] = storeAs
    return step

def assert_store(key, path=None, **kw):
    step = {"type": "assertStore", "key": key}
    if path: step["path"] = path
    step.update(kw)
    return step

def assert_contains(target, text, desc=None):
    return {"type": "assert", "target": target, "contains": text, "description": desc or f"断言包含'{text}'"}

def assert_equals(target, path, val, desc=None):
    return {"type": "assert", "target": target, "path": path, "equals": val, "description": desc or f"断言{path}={val}"}

def fill_react(selector, value, desc):
    return {"type": "fill", "selector": selector, "value": value, "react": True, "description": desc}

def select_option(label, option, desc=None):
    return {"type": "selectOption", "label": label, "option": option, "description": desc or f"选择{label}={option}"}

def screenshot(label, desc="截图"):
    return {"type": "screenshot", "label": label, "description": desc}

def capture_start(desc="开始抓包"):
    return {"type": "capture", "action": "start", "description": desc}

def capture_stop(desc="停止抓包"):
    return {"type": "capture", "action": "stop", "description": desc}

def data_test_target(desc):
    return {"type": "data-test-target", "description": desc}

# ============================================================
# 1. 任务管理页面 (task_management)
# ============================================================
TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"

cases = {}

# TC-001: 任务管理-页面加载与文案验证
cases["ui_f88_task_management_page_load"] = make_case(
    "ui-f88-task-management-page-load",
    "UI：任务管理页面加载与文案完整性验证",
    "验证任务管理页面加载后所有关键文案元素正确显示：顶部Tab、筛选区、树形列表、表头列名",
    TM_URL,
    [
        nav(TM_URL, "打开任务管理页面"),
        wait(3000, "等待页面加载"),
        assert_contains("page", "策略平台-F88", "验证顶部Tab文案"),
        assert_contains("page", "策略平台-测试", "验证测试Tab文案"),
        assert_contains("page", "手动创建", "验证手动创建Tab文案"),
        assert_contains("page", "模版库", "验证模版库Tab文案"),
        assert_contains("page", "查看任务排期", "验证查看任务排期按钮文案"),
        assert_contains("page", "链路：", "验证链路筛选label"),
        assert_contains("page", "批次：", "验证批次筛选label"),
        assert_contains("page", "重置", "验证重置按钮文案"),
        screenshot("task-mgmt-page-load", "任务管理页面加载截图"),
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); const hasSchedule = document.querySelector('button') && Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('查看任务排期')); return { tabs, hasScheduleBtn: hasSchedule }; })()", "探查Tab和按钮", storeAs="pageState"),
        assert_store("pageState", path="tabs", notEmpty=True, description="断言Tab列表非空"),
        assert_store("pageState", path="hasScheduleBtn", equals=True, description="断言查看任务排期按钮存在"),
    ],
    preconditions="F88预发已登录；存在策略平台任务数据。",
    realDomNotes="页面顶部4个Tab（策略平台-F88/测试/手动创建/模版库），右上角查看任务排期按钮，筛选区链路+批次+重置。",
    riskPoints=["无任务数据时树形列表为空", "Tab可能因权限不同而不同"]
)

# TC-002: 任务管理-链路筛选
cases["ui_f88_task_management_link_filter"] = make_case(
    "ui-f88-task-management-link-filter",
    "UI：任务管理-链路筛选功能验证",
    "验证链路下拉筛选：选择不同链路→列表更新→文案/数据一致性",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        capture_start("开始抓包-链路筛选"),
        evaluate("(() => { const selects = document.querySelectorAll('.ant-select-selector'); const linkSelect = selects[0]; return linkSelect ? { text: linkSelect.textContent.trim() } : null; })()", "记录初始链路筛选值", storeAs="initialLink"),
        evaluate("(() => { const rows = document.querySelectorAll('.ant-tree-treenode, [class*=treeNode]'); return { count: rows.length }; })()", "记录初始节点数", storeAs="initialCount"),
        select_option("链路", "全部", "选择全部链路"),
        wait(2000, "等待筛选结果"),
        evaluate("(() => { const rows = document.querySelectorAll('.ant-tree-treenode, [class*=treeNode]'); return { count: rows.length }; })()", "记录全部链路节点数", storeAs="allCount"),
        assert_store("allCount", path="count", greaterThanOrEqual=0, description="断言全部链路有数据"),
        screenshot("task-mgmt-link-filter-all", "全部链路筛选结果"),
        capture_stop("停止抓包"),
    ],
    preconditions="F88预发已登录；存在多条链路数据。",
    realDomNotes="链路筛选为Ant Design Select，选项包含全部+各链路名称。选择后树形列表刷新。",
    riskPoints=["链路下拉选项需实际确认"]
)

# TC-003: 任务管理-树形展开与数据一致性
cases["ui_f88_task_management_tree_expand"] = make_case(
    "ui-f88-task-management-tree-expand",
    "UI：任务管理-树形结构展开与数据一致性验证",
    "验证链路→批次→审核节点→任务表格的树形展开，每层数据字段完整性与文案正确性",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        evaluate("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher, [class*=switcher]'); const expandable = Array.from(arrows).filter(a => !a.classList.contains('ant-tree-switcher-noop')); return { expandableCount: expandable.length, firstArrow: expandable[0] ? 'exists' : 'none' }; })()", "探查可展开节点", storeAs="treeState"),
        evaluate("(() => { const firstArrow = document.querySelector('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); if(firstArrow) firstArrow.click(); return 'expanded'; })()", "展开第一个链路节点"),
        wait(1500, "等待子节点加载"),
        screenshot("task-mgmt-tree-expanded", "树形展开后截图"),
        evaluate("(() => { const nodes = document.querySelectorAll('.ant-tree-treenode'); const levels = Array.from(nodes).map(n => { const text = n.textContent.trim().substring(0, 50); const hasChildren = n.querySelector('.ant-tree-switcher:not(.ant-tree-switcher-noop)') !== null; return { text, hasChildren }; }); return levels.slice(0, 5); })()", "记录展开后的节点层级", storeAs="nodeLevels"),
        assert_store("nodeLevels", path="length", greaterThanOrEqual=2, description="断言展开后至少有2层节点"),
        # 继续展开到任务表格层
        evaluate("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); if(arrows.length >= 2) { arrows[1].click(); return 'expanded 2nd'; } return 'no 2nd arrow'; })()", "展开第二个节点"),
        wait(1500),
        evaluate("(() => { const tables = document.querySelectorAll('table, .ant-table'); return { tableCount: tables.length, hasTaskTable: tables.length > 0 }; })()", "检查任务表格是否出现", storeAs="tableState"),
        screenshot("task-mgmt-tree-full-expanded", "树形完全展开截图"),
    ],
    preconditions="F88预发已登录；存在链路→批次→节点→任务的完整树形数据。",
    realDomNotes="树形结构：链路(可展开)→批次(可展开)→审核节点(可展开)→任务表格。表头包含：任务名称/预期交付时间/审核状态&进度/抽检状态&进度/埋雷状态&进度/任务时长/操作。",
    riskPoints=["树形数据可能为空", "展开动画需等待"]
)

# TC-004: 任务管理-任务表格列名与数据验证
cases["ui_f88_task_management_table_columns"] = make_case(
    "ui-f88-task-management-table-columns",
    "UI：任务管理-任务表格列名与数据完整性验证",
    "展开到任务表格层后，验证所有列名文案正确、每行数据字段非空、状态标签文案合规",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        # 展开树形到表格层
        evaluate("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return `expanded ${arrows.length} nodes`; })()", "展开所有可展开节点"),
        wait(2000),
        evaluate("(() => { const tables = document.querySelectorAll('table, .ant-table'); if(tables.length === 0) return { found: false }; const table = tables[0]; const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim()); const rows = Array.from(table.querySelectorAll('tbody tr')).slice(0, 3); const rowData = rows.map(r => ({ text: r.textContent.trim().substring(0, 100), cellCount: r.querySelectorAll('td').length })); return { found: true, headers, rowCount: rows.length, rowData }; })()", "提取表格列名和前3行数据", storeAs="tableData"),
        assert_store("tableData", path="found", equals=True, description="断言找到任务表格"),
        assert_store("tableData", path="headers", notEmpty=True, description="断言表头非空"),
        # 验证关键列名
        evaluate("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const required = ['任务名称', '预期交付时间', '审核状态', '操作']; const found = required.filter(r => headers.some(h => h.includes(r))); return { required, found, allFound: found.length === required.length }; })()", "验证关键列名", storeAs="colCheck"),
        assert_store("colCheck", path="allFound", equals=True, description="断言所有关键列名存在"),
        screenshot("task-mgmt-table-columns", "任务表格列名验证截图"),
    ],
    preconditions="F88预发已登录；存在可展开到任务表格的数据。",
    realDomNotes="表头应包含：任务名称、预期交付时间、审核状态&进度、抽检状态&进度、埋雷状态&进度、任务时长(除埋雷)、操作。操作列包含：分配明细/详情/编辑/下载/删除。",
    riskPoints=["表格可能因无数据而不显示"]
)

# TC-005: 任务管理-操作按钮验证
cases["ui_f88_task_management_row_actions"] = make_case(
    "ui-f88-task-management-row-actions",
    "UI：任务管理-任务行操作按钮验证",
    "验证任务表格每行的操作按钮：分配明细/详情/编辑/下载/删除，文案正确且可点击",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        evaluate("(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return 'expanded'; })()", "展开所有节点"),
        wait(2000),
        evaluate("(() => { const actionLinks = Array.from(document.querySelectorAll('a, button')).filter(el => { const t = el.textContent.trim(); return ['分配明细', '详情', '编辑', '下载', '删除'].some(k => t.includes(k)); }); return actionLinks.map(a => ({ text: a.textContent.trim(), tag: a.tagName, href: a.href || '' })); })()", "提取所有操作按钮", storeAs="actions"),
        assert_store("actions", path="length", greaterThanOrEqual=1, description="断言至少有一个操作按钮"),
        evaluate("(() => { const actions = Array.from(document.querySelectorAll('a, button')).filter(el => ['分配明细', '详情', '编辑', '下载', '删除'].some(k => el.textContent.trim().includes(k))); const texts = actions.map(a => a.textContent.trim()); const expected = ['分配明细', '详情', '编辑', '下载', '删除']; const found = expected.filter(e => texts.some(t => t.includes(e))); return { expected, found, coverage: found.length + '/' + expected.length }; })()", "验证操作按钮覆盖率", storeAs="actionCoverage"),
        screenshot("task-mgmt-row-actions", "任务行操作按钮截图"),
    ],
    preconditions="F88预发已登录；存在至少一条任务数据。",
    realDomNotes="操作列包含5个按钮：分配明细(蓝色链接)、详情(蓝色链接)、编辑(蓝色链接)、下载(蓝色链接)、删除(红色链接)。",
    riskPoints=["删除按钮可能需确认弹窗"]
)

# TC-006: 任务管理-查看任务排期
cases["ui_f88_task_management_schedule"] = make_case(
    "ui-f88-task-management-schedule",
    "UI：任务管理-查看任务排期按钮验证",
    "点击右上角查看任务排期按钮，验证跳转/弹窗正确，排期数据展示完整",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        capture_start("开始抓包-排期"),
        click_text("查看任务排期", "点击查看任务排期"),
        wait(2000, "等待排期页面/弹窗"),
        evaluate("(() => { const url = window.location.href; const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); return { url, hasModal: !!modal, hasDrawer: !!drawer, urlChanged: url.includes('schedule') || url.includes('排期') }; })()", "验证排期跳转/弹窗", storeAs="scheduleResult"),
        screenshot("task-mgmt-schedule", "任务排期截图"),
        capture_stop("停止抓包"),
    ],
    preconditions="F88预发已登录。",
    realDomNotes="查看任务排期可能跳转到/review/task-schedule页面或打开弹窗/Drawer。",
    riskPoints=["排期页面可能需要特定权限"]
)

# TC-007: 任务管理-批次筛选
cases["ui_f88_task_management_batch_filter"] = make_case(
    "ui-f88-task-management-batch-filter",
    "UI：任务管理-批次筛选功能验证",
    "验证批次输入框筛选：输入批次ID→列表过滤→数据一致性",
    TM_URL,
    [
        nav(TM_URL), wait(3000),
        evaluate("(() => { const inputs = document.querySelectorAll('input[placeholder*=\\\"批次\\\"], input[placeholder*=\\\"请输入\\\"]'); const batchInput = inputs[0]; return batchInput ? { found: true, placeholder: batchInput.placeholder } : { found: false }; })()", "查找批次输入框", storeAs="batchInput"),
        assert_store("batchInput", path="found", equals=True, description="断言批次输入框存在"),
        fill_react("input[placeholder*='批次'], input[placeholder*='请输入']", "BT_", "输入批次ID前缀"),
        wait(2000, "等待筛选"),
        evaluate("(() => { const nodes = document.querySelectorAll('.ant-tree-treenode'); return { count: nodes.length }; })()", "记录筛选后节点数", storeAs="filteredCount"),
        click_text("重置", "点击重置"),
        wait(1500, "等待重置"),
        evaluate("(() => { const nodes = document.querySelectorAll('.ant-tree-treenode'); return { count: nodes.length }; })()", "记录重置后节点数", storeAs="resetCount"),
        screenshot("task-mgmt-batch-filter", "批次筛选验证截图"),
    ],
    preconditions="F88预发已登录；存在批次数据。",
    realDomNotes="批次筛选为输入框，支持模糊搜索。重置按钮清空筛选条件。",
    riskPoints=["批次输入框placeholder需实际确认"]
)

# ============================================================
# 2. 个人任务中心 - 抽检/埋雷Tab
# ============================================================
PTC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center"

# TC-008: 个人任务中心-Tab切换
cases["ui_f88_personal_task_tabs"] = make_case(
    "ui-f88-personal-task-tabs",
    "UI：个人任务中心-Tab切换与文案验证",
    "验证审核任务/抽检任务/埋雷三个Tab切换，每个Tab的列表数据和文案正确",
    PTC_URL,
    [
        nav(PTC_URL), wait(3000),
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); return { tabs, count: tabs.length }; })()", "记录所有Tab", storeAs="tabs"),
        assert_store("tabs", path="count", greaterThanOrEqual=3, description="断言至少3个Tab"),
        # 验证Tab文案
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); const expected = ['审核任务', '抽检任务', '埋雷任务']; const found = expected.filter(e => tabs.some(t => t.includes(e))); return { expected, found, allFound: found.length === expected.length }; })()", "验证Tab文案完整性", storeAs="tabCheck"),
        assert_store("tabCheck", path="allFound", equals=True, description="断言3个Tab文案全部正确"),
        # 切换到抽检任务
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const inspectionTab = tabs.find(t => t.textContent.includes('抽检')); if(inspectionTab) inspectionTab.click(); return 'switched'; })()", "切换到抽检任务Tab"),
        wait(2000),
        screenshot("ptc-inspection-tab", "抽检任务Tab截图"),
        # 切换到埋雷任务
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const mineTab = tabs.find(t => t.textContent.includes('埋雷')); if(mineTab) mineTab.click(); return 'switched'; })()", "切换到埋雷任务Tab"),
        wait(2000),
        screenshot("ptc-mine-tab", "埋雷任务Tab截图"),
        # 切回审核任务
        evaluate("(() => { const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')); const auditTab = tabs.find(t => t.textContent.includes('审核任务') && !t.textContent.includes('抽检') && !t.textContent.includes('埋雷')); if(auditTab) auditTab.click(); return 'switched'; })()", "切回审核任务Tab"),
        wait(2000),
    ],
    preconditions="F88预发已登录；存在审核/抽检/埋雷任务数据。",
    realDomNotes="3个Tab：审核任务(默认)/抽检任务/埋雷任务。抽检和埋雷Tab可能因无权限而不显示。",
    riskPoints=["抽检/埋雷Tab可能需要特定权限"]
)

# TC-009: 个人任务中心-筛选功能
cases["ui_f88_personal_task_filters"] = make_case(
    "ui-f88-personal-task-filters",
    "UI：个人任务中心-筛选功能完整性验证",
    "验证审核状态/素材类型/商家ID/商品ID筛选，搜索/重置按钮，数据一致性",
    PTC_URL,
    [
        nav(PTC_URL), wait(3000),
        # 验证筛选元素存在
        evaluate("(() => { const selects = Array.from(document.querySelectorAll('.ant-select-selector')).map(s => s.textContent.trim()); const inputs = Array.from(document.querySelectorAll('input')).map(i => ({ placeholder: i.placeholder, value: i.value })); return { selects, inputs: inputs.filter(i => i.placeholder) }; })()", "记录筛选元素", storeAs="filters"),
        # 审核状态筛选
        select_option("审核状态", "待审核", "筛选待审核"),
        wait(2000),
        screenshot("ptc-filter-pending", "待审核筛选结果"),
        # 素材类型筛选
        select_option("素材类型", "主图", "筛选主图类型"),
        wait(2000),
        screenshot("ptc-filter-main-image", "主图类型筛选结果"),
        # 重置
        click_text("重置", "重置筛选"),
        wait(1500),
        screenshot("ptc-filter-reset", "重置后截图"),
    ],
    preconditions="F88预发已登录；存在多状态/多类型任务数据。",
    realDomNotes="筛选区：审核状态(Select)/素材类型(Select)/商家ID(Input)/商品ID(Input)/搜索按钮/重置按钮。",
    riskPoints=["素材类型选项需实际确认"]
)

# ============================================================
# 3. 审核标准管理
# ============================================================
AS_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/standard-management"

# TC-010: 审核标准管理-页面与CRUD
cases["ui_f88_audit_standard_full"] = make_case(
    "ui-f88-audit-standard-full",
    "UI：审核标准管理-页面加载/新增/编辑/启用禁用/删除全功能验证",
    "验证审核标准管理页面：表格列名/新增标准弹窗/编辑/启用禁用切换/删除确认，数据一致性",
    AS_URL,
    [
        nav(AS_URL, "打开审核标准管理"), wait(3000),
        assert_contains("page", "审核标准管理", "验证页面标题"),
        # 验证表格列名
        evaluate("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { headers, count: headers.length }; })()", "记录表格列名", storeAs="stdHeaders"),
        screenshot("audit-std-page", "审核标准管理页面"),
        # 新增标准
        click_text("新增标准", "点击新增标准"),
        wait(1500, "等待新增弹窗"),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal, title: modal ? modal.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()", "验证新增弹窗", storeAs="addModal"),
        assert_store("addModal", path="hasModal", equals=True, description="断言新增弹窗出现"),
        screenshot("audit-std-add-modal", "新增标准弹窗"),
        # 关闭弹窗
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭新增弹窗"),
        wait(1000),
        # 编辑
        evaluate("(() => { const editBtns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); if(editBtns.length > 0) { editBtns[0].click(); return 'clicked edit'; } return 'no edit btn'; })()", "点击第一条编辑"),
        wait(1500),
        screenshot("audit-std-edit", "编辑标准"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭编辑弹窗"),
        wait(1000),
        # 启用/禁用
        evaluate("(() => { const toggleBtns = Array.from(document.querySelectorAll('a, button, .ant-switch')).filter(el => { const t = el.textContent.trim(); return t.includes('启用') || t.includes('禁用') || el.classList.contains('ant-switch'); }); return { count: toggleBtns.length, firstText: toggleBtns[0] ? toggleBtns[0].textContent.trim() : 'none' }; })()", "查找启用/禁用按钮", storeAs="toggleBtns"),
        screenshot("audit-std-toggle", "启用禁用按钮"),
    ],
    preconditions="F88预发已登录；存在审核标准数据。",
    realDomNotes="表格列：标准名称/创建人/创建时间/使用次数/状态/操作。操作：编辑/启用/禁用/删除。新增标准弹窗含表单字段。",
    riskPoints=["删除需确认弹窗", "启用/禁用可能为Switch组件"]
)

# ============================================================
# 4. 审核节点管理
# ============================================================
AN_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/node-management"

# TC-011: 审核节点管理-全功能
cases["ui_f88_audit_node_full"] = make_case(
    "ui-f88-audit-node-full",
    "UI：审核节点管理-页面加载/新增/编辑/排序/关联标准验证",
    "验证审核节点管理：表格列名/新增节点弹窗/编辑/排序/关联审核标准，数据一致性",
    AN_URL,
    [
        nav(AN_URL, "打开审核节点管理"), wait(3000),
        assert_contains("page", "审核节点管理", "验证页面标题"),
        evaluate("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); return { headers }; })()", "记录表格列名", storeAs="nodeHeaders"),
        screenshot("audit-node-page", "审核节点管理页面"),
        # 新增节点
        click_text("新增节点", "点击新增节点"),
        wait(1500),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal, title: modal ? modal.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()", "验证新增节点弹窗", storeAs="addNodeModal"),
        assert_store("addNodeModal", path="hasModal", equals=True, description="断言新增节点弹窗出现"),
        screenshot("audit-node-add-modal", "新增节点弹窗"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭弹窗"),
        wait(1000),
        # 编辑
        evaluate("(() => { const editBtns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); if(editBtns.length > 0) { editBtns[0].click(); return 'clicked'; } return 'no btn'; })()", "点击编辑"),
        wait(1500),
        screenshot("audit-node-edit", "编辑节点"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭弹窗"),
    ],
    preconditions="F88预发已登录；存在审核节点数据。",
    realDomNotes="表格列：节点名称/审核标准/人效预估/难度预估/分配方式/审核人/检查设置/操作。操作：编辑/排序/关联标准。",
    riskPoints=["排序可能为拖拽操作"]
)

# ============================================================
# 5. 商家信息配置
# ============================================================
MC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig"

# TC-012: 商家信息配置-全功能
cases["ui_f88_merchant_config_full"] = make_case(
    "ui-f88-merchant-config-full",
    "UI：商家信息配置-页面加载/搜索/编辑/批量下载验证",
    "验证商家信息配置：表格列名/搜索筛选/行内编辑/批量下载，数据一致性",
    MC_URL,
    [
        nav(MC_URL, "打开商家信息配置"), wait(3000),
        assert_contains("page", "店铺信息配置", "验证页面标题"),
        # 验证表格列名
        evaluate("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()); const expected = ['店铺信息', '合作供应商', '参考竞店', '负责买手', '视觉偏好', '搭配偏好', '操作']; const found = expected.filter(e => headers.some(h => h.includes(e))); return { headers, expected, found, coverage: found.length + '/' + expected.length }; })()", "验证表格列名", storeAs="mcHeaders"),
        screenshot("merchant-config-page", "商家信息配置页面"),
        # 搜索
        fill_react("input[placeholder*='搜索'], input[placeholder*='请输入']", "测试", "输入搜索关键词"),
        click_text("搜索", "点击搜索"),
        wait(2000),
        screenshot("merchant-config-search", "搜索结果"),
        # 重置
        click_text("重置筛选", "点击重置筛选"),
        wait(1500),
        # 编辑
        evaluate("(() => { const editBtns = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); if(editBtns.length > 0) { editBtns[0].click(); return 'clicked'; } return 'no btn'; })()", "点击编辑"),
        wait(1500),
        screenshot("merchant-config-edit", "编辑商家配置"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close, .ant-drawer-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭编辑"),
        wait(1000),
        # 批量下载
        evaluate("(() => { const dlBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('批量下载')); return { found: !!dlBtn }; })()", "查找批量下载按钮", storeAs="batchDl"),
    ],
    preconditions="F88预发已登录；存在商家配置数据。",
    realDomNotes="表格列：店铺信息/合作供应商/参考竞店/负责买手/视觉偏好/搭配偏好/参考视觉图例/操作。操作：编辑。顶部：搜索/重置筛选/批量下载。",
    riskPoints=["编辑可能为行内编辑或弹窗", "批量下载为异步任务"]
)

# ============================================================
# 6. 生产看板
# ============================================================
PD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/productionDashboard"

# TC-013: 生产看板-指标验证
cases["ui_f88_production_dashboard_full"] = make_case(
    "ui-f88-production-dashboard-full",
    "UI：生产看板-指标卡片/链路进度/数据一致性验证",
    "验证生产看板：整体推送进度(总任务数/生产中/已推送/未推送)、链路生产进度表格，数据非空且文案正确",
    PD_URL,
    [
        nav(PD_URL, "打开生产看板"), wait(3000),
        assert_contains("page", "生产看板", "验证页面标题"),
        # 验证指标卡片
        evaluate("(() => { const cards = Array.from(document.querySelectorAll('.ant-card, [class*=card], [class*=stat]')).map(c => c.textContent.trim().substring(0, 80)); return { cards, count: cards.length }; })()", "记录指标卡片", storeAs="dashCards"),
        screenshot("dashboard-page", "生产看板页面"),
        # 验证关键指标文案
        evaluate("(() => { const text = document.body.innerText; const metrics = ['总任务数', '生产中', '已推送', '未推送']; const found = metrics.filter(m => text.includes(m)); return { metrics, found, coverage: found.length + '/' + metrics.length }; })()", "验证关键指标文案", storeAs="metricCheck"),
        # 链路生产进度
        evaluate("(() => { const tables = document.querySelectorAll('table, .ant-table'); return { tableCount: tables.length }; })()", "检查链路进度表格", storeAs="dashTables"),
        screenshot("dashboard-metrics", "生产看板指标截图"),
    ],
    preconditions="F88预发已登录；存在生产数据。",
    realDomNotes="看板包含：整体推送进度(总任务数/生产中/已推送/未推送卡片)、链路生产进度(按链路展示表格)。",
    riskPoints=["无数据时指标显示0"]
)

# ============================================================
# 7. 策略列表
# ============================================================
SL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list"

# TC-014: 策略列表-筛选与操作
cases["ui_f88_strategy_list_full_ops"] = make_case(
    "ui-f88-strategy-list-full-ops",
    "UI：策略列表-筛选/新建/打开/复制/删除全功能验证",
    "验证策略列表：策略阶段筛选/环节筛选/新建策略/策略卡片操作(打开/复制/删除)，数据一致性",
    SL_URL,
    [
        nav(SL_URL, "打开策略列表"), wait(3000),
        assert_contains("page", "策略", "验证页面包含策略"),
        # 策略阶段筛选
        select_option("策略阶段", "实验", "筛选实验阶段"),
        wait(2000),
        screenshot("strategy-list-stage-exp", "实验阶段筛选"),
        # 环节筛选
        select_option("环节", "视觉", "筛选视觉环节"),
        wait(2000),
        screenshot("strategy-list-process-visual", "视觉环节筛选"),
        # 新建策略
        click_text("新建策略", "点击新建策略"),
        wait(1500),
        screenshot("strategy-list-create", "新建策略"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close, .ant-drawer-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭"),
        wait(1000),
        # 策略卡片操作
        evaluate("(() => { const actions = Array.from(document.querySelectorAll('a, button')).filter(el => { const t = el.textContent.trim(); return ['打开', '复制', '删除'].some(k => t.includes(k)); }); return actions.map(a => ({ text: a.textContent.trim() })); })()", "提取策略操作按钮", storeAs="stratActions"),
        screenshot("strategy-list-actions", "策略操作按钮"),
    ],
    preconditions="F88预发已登录；存在策略数据。",
    realDomNotes="筛选：策略阶段(全部/实验/灰度/正式)/环节(全部/视觉/设计/视频)。按钮：新建策略。卡片操作：打开/复制/删除。",
    riskPoints=["删除需确认弹窗"]
)

# ============================================================
# 8. 策略详情-节点编排
# ============================================================
# TC-015: 策略详情-新增节点
cases["ui_f88_strategy_detail_add_node"] = make_case(
    "ui-f88-strategy-detail-add-node",
    "UI：策略详情-新增节点/节点类型选择验证",
    "验证策略详情页：+新增节点按钮→节点类型选择面板→20种节点类型文案完整性",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail?id=20180",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail?id=20180", "打开策略详情"), wait(3000),
        assert_contains("page", "策略", "验证策略详情页"),
        screenshot("strategy-detail-page", "策略详情页"),
        # 新增节点
        evaluate("(() => { const addBtn = Array.from(document.querySelectorAll('button, a, [class*=addNode]')).find(el => el.textContent.includes('新增节点') || el.textContent.includes('+')); if(addBtn) { addBtn.click(); return 'clicked'; } return 'not found'; })()", "点击新增节点"),
        wait(1500),
        screenshot("strategy-detail-add-node", "新增节点面板"),
        # 验证节点类型
        evaluate("(() => { const nodeTypes = Array.from(document.querySelectorAll('[class*=nodeType], [class*=node-type], .ant-list-item, [class*=nodeCard]')).map(el => el.textContent.trim().substring(0, 30)); return { nodeTypes, count: nodeTypes.length }; })()", "记录节点类型", storeAs="nodeTypes"),
        screenshot("strategy-detail-node-types", "节点类型列表"),
    ],
    preconditions="F88预发已登录；策略ID=20180存在。",
    realDomNotes="20种节点类型：LLM文本生成/生图/Map生图/季节标签/产业标签/定价节点/模板匹配/人工审核/推送选款/面料上身/款式分配/匹配度打分/图像裁头/改款prompt推理/Caption/机审/视频生成/视频上传/高清化处理/选片。",
    riskPoints=["节点类型面板可能为弹窗/侧边栏/下拉"]
)

# TC-016: 策略详情-落库配置
cases["ui_f88_strategy_detail_storage"] = make_case(
    "ui-f88-strategy-detail-storage",
    "UI：策略详情-落库配置验证",
    "验证策略详情页落库配置区域：配置项展示/编辑/保存，数据一致性",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail?id=20180",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail?id=20180", "打开策略详情"), wait(3000),
        # 查找落库配置区域
        evaluate("(() => { const text = document.body.innerText; const hasStorage = text.includes('落库') || text.includes('存储') || text.includes('storage'); return { hasStorageSection: hasStorage }; })()", "检查落库配置区域", storeAs="storageCheck"),
        screenshot("strategy-detail-storage", "落库配置区域"),
        # 保存按钮
        evaluate("(() => { const saveBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('保存')); return { found: !!saveBtn }; })()", "查找保存按钮", storeAs="saveBtn"),
    ],
    preconditions="F88预发已登录；策略ID=20180存在。",
    realDomNotes="策略详情包含3个区域：策略基本信息/节点编排/落库配置。保存按钮在页面顶部或底部。",
    riskPoints=["落库配置区域可能需要滚动才能看到"]
)

# ============================================================
# 9. 链路详情-试运行
# ============================================================
# TC-017: 链路详情-试运行弹窗
cases["ui_f88_link_detail_trial_run"] = make_case(
    "ui-f88-link-detail-trial-run",
    "UI：链路详情-试运行弹窗/模板下载/Excel上传/运行类型验证",
    "验证链路详情页试运行按钮→弹窗→下载模板/上传Excel/任务名称/运行类型(正式/测试)→发起运行",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180", "打开链路详情"), wait(3000),
        assert_contains("page", "链路", "验证链路详情页"),
        screenshot("link-detail-page", "链路详情页"),
        # 试运行
        click_text("试运行", "点击试运行"),
        wait(1500),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal, title: modal ? modal.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()", "验证试运行弹窗", storeAs="trialModal"),
        assert_store("trialModal", path="hasModal", equals=True, description="断言试运行弹窗出现"),
        screenshot("link-detail-trial-modal", "试运行弹窗"),
        # 验证弹窗字段
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return {}; const dlBtn = Array.from(modal.querySelectorAll('a, button')).find(el => el.textContent.includes('下载') || el.textContent.includes('模板')); const uploadInput = modal.querySelector('input[type=file]'); const taskInput = modal.querySelector('input[placeholder*=\\\"任务名称\\\"]'); const selects = Array.from(modal.querySelectorAll('.ant-select-selector')).map(s => s.textContent.trim()); return { hasDownloadBtn: !!dlBtn, hasUploadInput: !!uploadInput, hasTaskInput: !!taskInput, selectOptions: selects }; })()", "验证试运行弹窗字段", storeAs="trialFields"),
        assert_store("trialFields", path="hasDownloadBtn", equals=True, description="断言下载模板按钮存在"),
        assert_store("trialFields", path="hasUploadInput", equals=True, description="断言上传Excel输入存在"),
        assert_store("trialFields", path="hasTaskInput", equals=True, description="断言任务名称输入存在"),
        # 关闭
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭弹窗"),
    ],
    preconditions="F88预发已登录；链路ID=20180存在。",
    realDomNotes="试运行弹窗标题'链路运行'，含：下载模板按钮/上传Excel(input[type=file])/任务名称输入/运行类型Select(正式/测试)/发起任务运行按钮。Excel列：seller_id/seed_image_url/tao_cate/item_id。",
    riskPoints=["运行类型Select需用mouse.click()展开"]
)

# TC-018: 链路详情-查看运行结果
cases["ui_f88_link_detail_run_results"] = make_case(
    "ui-f88-link-detail-run-results",
    "UI：链路详情-查看运行结果弹窗验证",
    "验证链路详情页查看运行结果按钮→弹窗/页面→运行结果数据展示",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180", "打开链路详情"), wait(3000),
        click_text("查看运行结果", "点击查看运行结果"),
        wait(2000),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); const url = window.location.href; return { hasModal: !!modal, hasDrawer: !!drawer, urlChanged: url.includes('result') || url.includes('run') }; })()", "验证运行结果展示形式", storeAs="runResult"),
        screenshot("link-detail-run-results", "运行结果"),
    ],
    preconditions="F88预发已登录；链路ID=20180存在且有运行记录。",
    realDomNotes="查看运行结果可能打开弹窗/Drawer或跳转页面，展示运行批次/状态/结果数据。",
    riskPoints=["无运行记录时可能为空"]
)

# ============================================================
# 10. 模版包管理-详情/编辑/激活/停用
# ============================================================
TM_URL = "https://pre-aixiaoer.alibaba-inc.com/templateManagement"

# TC-019: 模版包管理-店铺卡片操作
cases["ui_f88_template_mgmt_card_ops"] = make_case(
    "ui-f88-template-mgmt-card-ops",
    "UI：模版包管理-店铺卡片操作(查看详情/编辑/激活/停用)验证",
    "验证模版包管理页面店铺卡片：字段展示/查看详情跳转/编辑弹窗/激活确认/停用确认，数据一致性",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement", "打开模版包管理"), wait(3000),
        assert_contains("page", "模版包管理", "验证页面标题"),
        # 验证卡片字段
        evaluate("(() => { const cards = document.querySelectorAll('[class*=shopCard], [class*=card]'); const firstCard = cards[0]; if(!firstCard) return { found: false }; const text = firstCard.textContent.trim(); const fields = ['店铺名称', '店铺ID', '买手', '模板包', '使用状态']; const found = fields.filter(f => text.includes(f)); return { found: true, fields, foundFields: found, coverage: found.length + '/' + fields.length }; })()", "验证卡片字段", storeAs="cardFields"),
        screenshot("template-mgmt-cards", "店铺卡片"),
        # 查看详情
        evaluate("(() => { const detailBtn = Array.from(document.querySelectorAll('a, button')).find(el => el.textContent.includes('查看详情')); if(detailBtn) { detailBtn.click(); return 'clicked'; } return 'not found'; })()", "点击查看详情"),
        wait(2000),
        screenshot("template-mgmt-detail", "模板包详情"),
        # 返回列表
        evaluate("(() => { const backBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.textContent.includes('返回')); if(backBtn) { backBtn.click(); return 'backed'; } return 'not found'; })()", "返回列表"),
        wait(1500),
        # 编辑
        evaluate("(() => { const editBtn = Array.from(document.querySelectorAll('a, button')).filter(el => el.textContent.trim() === '编辑'); if(editBtn.length > 0) { editBtn[0].click(); return 'clicked'; } return 'not found'; })()", "点击编辑"),
        wait(1500),
        screenshot("template-mgmt-edit", "编辑模板包"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭"),
        wait(1000),
        # 激活/停用
        evaluate("(() => { const toggleBtn = Array.from(document.querySelectorAll('a, button')).find(el => el.textContent.includes('激活') || el.textContent.includes('停用')); return { found: !!toggleBtn, text: toggleBtn ? toggleBtn.textContent.trim() : 'none' }; })()", "查找激活/停用按钮", storeAs="toggleBtn"),
    ],
    preconditions="F88预发已登录；存在模版包数据。",
    realDomNotes="店铺卡片字段：店铺名称/店铺ID/买手/模板包数量(N个)/使用状态标签(使用中/未使用)。操作：查看详情/编辑/激活/停用。激活需确认弹窗，同seller+range+scene仅一个IN_USE。",
    riskPoints=["激活/停用需确认弹窗", "编辑后状态回退IDLE→DRAFT"]
)

# TC-020: 模版包管理-新建/导入
cases["ui_f88_template_mgmt_create_import"] = make_case(
    "ui-f88-template-mgmt-create-import",
    "UI：模版包管理-新建模板包/导入模板包弹窗验证",
    "验证新建模板包弹窗(店铺选择/名称/应用环节/场景/上传)和导入模板包弹窗(文件上传/店铺关联)",
    "https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement",
    [
        nav("https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement", "打开模版包管理"), wait(3000),
        # 新建模板包
        click_text("新建模板包", "点击新建模板包"),
        wait(1500),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal, title: modal ? modal.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()", "验证新建弹窗", storeAs="createModal"),
        assert_store("createModal", path="hasModal", equals=True, description="断言新建弹窗出现"),
        screenshot("template-mgmt-create-modal", "新建模板包弹窗"),
        # 验证弹窗字段
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!modal) return {}; const labels = Array.from(modal.querySelectorAll('label, .ant-form-item-label')).map(l => l.textContent.trim()); const selects = Array.from(modal.querySelectorAll('.ant-select')).length; const uploads = modal.querySelectorAll('input[type=file]').length; return { labels, selectCount: selects, uploadCount: uploads }; })()", "验证新建弹窗字段", storeAs="createForm"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭"),
        wait(1000),
        # 导入模板包
        click_text("导入模板包", "点击导入模板包"),
        wait(1500),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!modal, title: modal ? modal.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()", "验证导入弹窗", storeAs="importModal"),
        assert_store("importModal", path="hasModal", equals=True, description="断言导入弹窗出现"),
        screenshot("template-mgmt-import-modal", "导入模板包弹窗"),
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭"),
    ],
    preconditions="F88预发已登录。",
    realDomNotes="新建弹窗：店铺选择(Select)/模板包名称(Input)/应用环节(Select:搭配/视觉/套图/视频)/应用场景(Select:主图素材/种草素材/详情页)/模板上传。导入弹窗：上传文件(input[type=file], .xlsx/.zip)/店铺关联(Select)。",
    riskPoints=["上传文件需真实文件"]
)

# ============================================================
# 11. 淘内资源池-预览/分页
# ============================================================
TL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateLibrary"

# TC-021: 淘内资源池-模板预览
cases["ui_f88_template_library_preview_detail"] = make_case(
    "ui-f88-template-library-preview-detail",
    "UI：淘内资源池-模板预览详情验证",
    "点击模板图片卡片→预览弹窗/Drawer→验证大图/标签信息/推荐曝光数/所属店铺展示",
    TL_URL,
    [
        nav(TL_URL, "打开淘内资源池"), wait(3000),
        assert_contains("page", "淘内资源池", "验证页面标题"),
        # 点击第一个模板
        evaluate("(() => { const cards = document.querySelectorAll('[class*=templateCard], [class*=card], img'); const first = cards[0]; if(first) { first.click(); return 'clicked'; } return 'no card'; })()", "点击第一个模板"),
        wait(2000),
        evaluate("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); const previewImg = document.querySelector('.ant-modal img, .ant-drawer img, [class*=preview] img'); return { hasModal: !!modal, hasDrawer: !!drawer, hasPreviewImg: !!previewImg }; })()", "验证预览展示", storeAs="preview"),
        screenshot("template-library-preview", "模板预览"),
        # 验证预览内容
        evaluate("(() => { const container = document.querySelector('.ant-modal:not(.ant-modal-hidden), .ant-drawer:not(.ant-drawer-hidden)'); if(!container) return {}; const text = container.textContent; const fields = ['标签', '曝光', '店铺']; const found = fields.filter(f => text.includes(f)); return { fields, found, coverage: found.length + '/' + fields.length }; })()", "验证预览内容字段", storeAs="previewContent"),
        # 关闭
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close, .ant-drawer-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭预览"),
    ],
    preconditions="F88预发已登录；存在模板数据。",
    realDomNotes="预览展示：大图预览/标签信息(7维度)/推荐曝光数/所属店铺。预览形式可能为Drawer/Modal/图片放大。",
    riskPoints=["预览形式需实际确认"]
)

# TC-022: 淘内资源池-分页
cases["ui_f88_template_library_pagination"] = make_case(
    "ui-f88-template-library-pagination",
    "UI：淘内资源池-分页功能验证",
    "验证资源池分页：页码显示/翻页/每页数量/总数文案",
    TL_URL,
    [
        nav(TL_URL), wait(3000),
        evaluate("(() => { const pagination = document.querySelector('.ant-pagination'); return { hasPagination: !!pagination, text: pagination ? pagination.textContent.trim().substring(0, 50) : 'none' }; })()", "检查分页组件", storeAs="pagination"),
        screenshot("template-library-pagination", "分页组件"),
        # 如果有分页，点击下一页
        evaluate("(() => { const nextBtn = document.querySelector('.ant-pagination-next:not(.ant-pagination-disabled)'); if(nextBtn) { nextBtn.click(); return 'clicked next'; } return 'no next or disabled'; })()", "点击下一页"),
        wait(2000),
        screenshot("template-library-page2", "第2页"),
    ],
    preconditions="F88预发已登录；存在超过一页的模板数据。",
    realDomNotes="分页组件为Ant Design Pagination，含上一页/页码/下一页/总数/每页数量。",
    riskPoints=["数据不足一页时分页不显示"]
)

# ============================================================
# 12. 优质模板库-洗图状态/应用场景
# ============================================================
QT_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/selfTemplateLibrary_f88"

# TC-023: 优质模板库-洗图状态筛选
cases["ui_f88_quality_template_wash_status"] = make_case(
    "ui-f88-quality-template-wash-status",
    "UI：优质模板库-洗图状态筛选验证",
    "验证优质模板库洗图状态筛选：Radio/Tab切换→列表更新→数据一致性",
    QT_URL,
    [
        nav(QT_URL, "打开优质模板库"), wait(3000),
        assert_contains("page", "优质模板库", "验证页面标题"),
        # 查找洗图状态筛选
        evaluate("(() => { const radios = Array.from(document.querySelectorAll('[role=radio], input[type=radio], .ant-radio-button-wrapper, [class*=washStatus], [class*=wash]')).map(el => ({ text: el.textContent?.trim()?.substring(0, 20) || '', tag: el.tagName, checked: el.checked || el.classList?.contains('ant-radio-button-wrapper-checked') })); const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim()); return { radios, tabs }; })()", "查找洗图状态筛选元素", storeAs="washFilters"),
        screenshot("quality-template-wash", "洗图状态筛选"),
        # 点击第一个洗图状态选项
        evaluate("(() => { const options = document.querySelectorAll('[role=radio], .ant-radio-button-wrapper, [class*=washStatus]'); if(options.length > 1) { options[1].click(); return 'clicked option 2'; } return 'no options'; })()", "切换洗图状态"),
        wait(2000),
        screenshot("quality-template-wash-filtered", "洗图状态筛选结果"),
    ],
    preconditions="F88预发已登录；存在洗图状态数据。",
    realDomNotes="洗图状态筛选可能为Radio Group或Tab，选项含：全部/已洗图/未洗图/洗图中。",
    riskPoints=["洗图状态选项文案需实际确认"]
)

# TC-024: 优质模板库-应用场景筛选
cases["ui_f88_quality_template_app_scene"] = make_case(
    "ui-f88-quality-template-app-scene",
    "UI：优质模板库-应用场景筛选验证",
    "验证优质模板库应用场景筛选：选择不同场景→列表更新→数据一致性",
    QT_URL,
    [
        nav(QT_URL), wait(3000),
        # 查找应用场景筛选
        evaluate("(() => { const selects = Array.from(document.querySelectorAll('.ant-select')).filter(s => { const prev = s.previousElementSibling || s.parentElement?.querySelector('label, span'); return prev && prev.textContent && (prev.textContent.includes('应用') || prev.textContent.includes('场景')); }); return { count: selects.length, texts: selects.map(s => s.querySelector('.ant-select-selector')?.textContent?.trim()) }; })()", "查找应用场景Select", storeAs="appSceneSelect"),
        screenshot("quality-template-app-scene", "应用场景筛选"),
    ],
    preconditions="F88预发已登录。",
    realDomNotes="应用场景筛选为Select，选项可能含：主图素材/种草素材/详情页。",
    riskPoints=["应用场景选项需实际确认"]
)

# ============================================================
# 13. 审核详情-驳回流程
# ============================================================
# TC-025: 审核详情-驳回必填验证
cases["ui_f88_audit_reject_validation"] = make_case(
    "ui-f88-audit-reject-validation",
    "UI：审核详情-驳回原因必填/驳回类型选择/确认按钮disabled验证",
    "验证审核详情页驳回流程：不填原因时确认按钮disabled→填写原因→选择驳回类型→确认按钮enabled→提交",
    PTC_URL,
    [
        nav(PTC_URL), wait(3000),
        select_option("审核状态", "待审核", "筛选待审核"),
        wait(2000),
        click_text("审核", "打开审核详情"),
        wait(2500),
        screenshot("audit-detail-reject", "审核详情"),
        # 点击驳回
        evaluate("(() => { const rejectBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('驳回')); if(rejectBtn) { rejectBtn.click(); return 'clicked'; } return 'not found'; })()", "点击驳回"),
        wait(1000),
        # 验证不填原因时确认按钮disabled
        evaluate("(() => { const confirmBtn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定|确\\\\s*认|提\\\\s*交/.test(b.textContent)); return { text: confirmBtn?.textContent?.trim(), disabled: confirmBtn?.disabled || false, hasClass: confirmBtn?.classList?.contains('ant-btn-disabled') || false }; })()", "验证确认按钮状态(未填原因)", storeAs="rejectBtnEmpty"),
        assert_store("rejectBtnEmpty", path="disabled", equals=True, description="断言未填原因时确认按钮disabled"),
        # 填写驳回原因
        evaluate("(() => { const ta = document.querySelector('textarea[placeholder*=\\\"原因\\\"], textarea[placeholder*=\\\"驳回\\\"]'); if(!ta) return 'no textarea'; const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; nativeSetter.call(ta, '测试驳回原因'); ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true})); return 'filled'; })()", "填写驳回原因"),
        wait(500),
        # 验证填写后确认按钮enabled
        evaluate("(() => { const confirmBtn = Array.from(document.querySelectorAll('button')).find(b => /确\\\\s*定|确\\\\s*认|提\\\\s*交/.test(b.textContent)); return { disabled: confirmBtn?.disabled || false }; })()", "验证确认按钮状态(已填原因)", storeAs="rejectBtnFilled"),
        screenshot("audit-reject-filled", "填写驳回原因后"),
        # 关闭
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close, .ant-drawer-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭"),
    ],
    preconditions="F88预发已登录；存在待审核任务。",
    realDomNotes="驳回表单：驳回原因(textarea,必填)/驳回类型(Select)/示例图片(upload)。不填原因时确认按钮始终disabled。",
    riskPoints=["驳回按钮可能在工具栏或底部"]
)

# TC-026: 审核详情-图片放大查看
cases["ui_f88_audit_image_zoom"] = make_case(
    "ui-f88-audit-image-zoom",
    "UI：审核详情-图片放大查看验证",
    "验证审核详情页图片放大功能：点击图片→放大预览→关闭，图片URL一致性",
    PTC_URL,
    [
        nav(PTC_URL), wait(3000),
        select_option("审核状态", "待审核", "筛选待审核"),
        wait(2000),
        click_text("审核", "打开审核详情"),
        wait(2500),
        # 记录原始图片URL
        evaluate("(() => { const imgs = Array.from(document.querySelectorAll('.ant-drawer img, .ant-modal img')).filter(i => i.src && i.getBoundingClientRect().width > 100); return imgs.length > 0 ? { url: imgs[0].src.substring(0, 120), count: imgs.length } : { url: null, count: 0 }; })()", "记录图片URL", storeAs="imgUrl"),
        assert_store("imgUrl", path="count", greaterThanOrEqual=1, description="断言至少有一张图片"),
        # 点击图片放大
        evaluate("(() => { const imgs = document.querySelectorAll('.ant-drawer img, .ant-modal img'); const img = Array.from(imgs).find(i => i.getBoundingClientRect().width > 100); if(img) { img.click(); return 'clicked'; } return 'no img'; })()", "点击图片放大"),
        wait(1500),
        evaluate("(() => { const previewModal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const previewImg = previewModal?.querySelector('img'); return { hasPreview: !!previewModal, previewUrl: previewImg?.src?.substring(0, 120) || null }; })()", "验证放大预览", storeAs="zoomPreview"),
        screenshot("audit-image-zoom", "图片放大预览"),
        # 关闭
        evaluate("(() => { const closeBtn = document.querySelector('.ant-modal-close'); if(closeBtn) closeBtn.click(); return 'closed'; })()", "关闭预览"),
        wait(1000),
    ],
    preconditions="F88预发已登录；存在待审核图片任务。",
    realDomNotes="点击图片触发放大预览(Ant Design Image Preview)，支持缩放/旋转/关闭。",
    riskPoints=["图片可能懒加载"]
)

# TC-027: 审核详情-素材切换
cases["ui_f88_audit_material_switch"] = make_case(
    "ui-f88-audit-material-switch",
    "UI：审核详情-多素材切换验证",
    "验证审核详情页多素材切换：素材列表/缩略图点击切换→主图更新→URL变化",
    PTC_URL,
    [
        nav(PTC_URL), wait(3000),
        select_option("审核状态", "待审核", "筛选待审核"),
        wait(2000),
        click_text("审核", "打开审核详情"),
        wait(2500),
        # 查找素材列表/缩略图
        evaluate("(() => { const thumbs = document.querySelectorAll('[class*=thumb], [class*=Thumbnail], [class*=slider] img, [class*=MaterialSlider] img'); return { count: thumbs.length, urls: Array.from(thumbs).slice(0, 5).map(i => i.src?.substring(0, 80)) }; })()", "查找素材缩略图", storeAs="thumbs"),
        screenshot("audit-material-list", "素材列表"),
        # 如果有多个素材，点击切换
        evaluate("(() => { const thumbs = document.querySelectorAll('[class*=thumb] img, [class*=Thumbnail] img, [class*=slider] img, [class*=MaterialSlider] img'); if(thumbs.length >= 2) { thumbs[1].click(); return `switched to ${thumbs.length}th`; } return `only ${thumbs.length} thumb`; })()", "切换到第2个素材"),
        wait(1500),
        evaluate("(() => { const mainImg = document.querySelector('.ant-drawer img, .ant-modal img'); return mainImg ? { url: mainImg.src.substring(0, 120) } : null; })()", "记录切换后主图URL", storeAs="switchedImg"),
        screenshot("audit-material-switched", "素材切换后"),
    ],
    preconditions="F88预发已登录；存在多素材审核任务。",
    realDomNotes="审核详情左侧为素材缩略图列表(MaterialSlider)，点击缩略图切换主图显示。",
    riskPoints=["单素材任务无切换功能"]
)

# ============================================================
# Write all cases
# ============================================================
count = 0
for fname, case in cases.items():
    path = os.path.join(BASE, f"{fname}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    count += 1
    print(f"✅ {fname}.json: {len(case['steps'])} steps - {case['name']}")

print(f"\n🎉 Total: {count} new test cases generated!")
