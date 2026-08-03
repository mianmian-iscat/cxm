#!/usr/bin/env python3
"""补充任务管理缺失的原子级用例"""
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
def sel(label, option, desc=None):
    return {"type":"selectOption","label":label,"option":option,"description":desc or f"选择{label}={option}"}
def fill(placeholder, value, desc=None):
    return {"type":"fill","selector":f"input[placeholder='{placeholder}']","value":value,"react":True,"description":desc or f"输入{placeholder}={value}"}

def meta(id, name, desc, steps, pre="", notes="", risks=None, pri="P1"):
    return {
        "id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": {"urlPattern":"pre-aifashion-xiaoer.alibaba-inc.com",
                    "url":"https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other",
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

EXPAND_ALL = "(() => { const arrows = document.querySelectorAll('.ant-tree-switcher:not(.ant-tree-switcher-noop)'); arrows.forEach(a => a.click()); return 'expanded'; })()"
PRE_TM = "F88预发已登录；存在任务管理数据"

# 1. 批次输入框筛选
save(meta("atomic-f88-tm-batch-input","UI：任务管理-批次输入框筛选验证",
    "在批次输入框中输入批次ID进行筛选",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && i.placeholder.includes('请输入')); return inputs.map(i => ({ placeholder: i.placeholder, hasSearchIcon: !!i.closest('.ant-input-affix-wrapper') })); })()","查找批次输入框","batchInputs"),
        asrtS("batchInputs",desc="验证批次输入框存在",notEmpty=True),
        fill("请输入","BT_6356","输入批次ID"),wait(2000),
        shot("tm-batch-filter","批次筛选结果"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TM,"批次输入框带搜索图标，React受控组件"))

# 2. 重置按钮
save(meta("atomic-f88-tm-reset","UI：任务管理-重置按钮验证",
    "点击重置按钮，验证筛选条件清空",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        sel("链路","【zy测试】主图生成链路","选择链路筛选"),wait(2000),
        fill("请输入","BT_6356","输入批次ID"),wait(1000),
        click("重置","点击重置按钮"),wait(2000),
        eva("(() => { const selectText = document.querySelector('.ant-select-selection-item')?.textContent?.trim(); const inputValue = document.querySelector('input[placeholder*=请输入]')?.value; return { selectValue: selectText, inputValue: inputValue || '' }; })()","验证筛选已清空","resetCheck"),
        shot("tm-reset","重置后状态")],
    PRE_TM,"重置清空链路Select和批次Input"))

# 3. 环节级统计(总任务数/完成率/通过率)
save(meta("atomic-f88-tm-stage-stats","UI：任务管理-环节级统计信息验证",
    "验证树形结构中环节级别的统计信息：总任务数/审核完成率/审核通过率",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const t = document.body.innerText; const metrics = ['总任务数','审核完成率','审核通过率']; const found = metrics.filter(m => t.includes(m)); const pctMatch = t.match(/\\d+\\.?\\d*%/g); return { metrics, found, coverage: found.length+'/'+metrics.length, percentages: pctMatch ? pctMatch.slice(0,5) : [] }; })()","验证环节统计文案","stageStats"),
        shot("tm-stage-stats","环节级统计")],
    PRE_TM,"环节行展示: 总任务数 N / 审核完成率 XX% / 审核通过率 XX%"))

# 4. 任务级统计(审核x/y/抽检/埋雷)
save(meta("atomic-f88-tm-task-stats","UI：任务管理-任务级统计信息验证",
    "验证任务行的审核/抽检/埋雷统计信息",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const t = document.body.innerText; const hasAudit = /审核[:：]\\s*\\d+\\/\\d+/.test(t); const hasInspect = t.includes('抽检'); const hasMine = t.includes('埋雷'); return { hasAuditProgress: hasAudit, hasInspect: hasInspect, hasMine: hasMine }; })()","验证任务统计","taskStats"),
        shot("tm-task-stats","任务级统计")],
    PRE_TM,"任务行展示: 审核: x/y / 抽检: - / 埋雷: -"))

# 5. 进度条展示
save(meta("atomic-f88-tm-progress-bar","UI：任务管理-审核进度条展示验证",
    "验证审核进度条正确渲染",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const bars = document.querySelectorAll('.ant-progress,.ant-progress-line,[class*=progress]'); const filled = Array.from(bars).filter(b => { const inner = b.querySelector('.ant-progress-bg,[class*=fill]'); return inner && inner.style.width && parseFloat(inner.style.width) > 0; }); return { totalBars: bars.length, filledBars: filled.length, widths: filled.map(b => b.querySelector('.ant-progress-bg,[class*=fill]')?.style?.width || '0%').slice(0,5) }; })()","验证进度条","progressBars"),
        asrtS("progressBars","totalBars",desc="验证进度条存在",notEmpty=True),
        shot("tm-progress-bar","审核进度条")],
    PRE_TM,"进度条显示审核完成百分比"))

# 6. 分配明细
save(meta("atomic-f88-tm-assign-detail","UI：任务管理-分配明细操作验证",
    "点击分配明细链接，验证跳转/弹窗",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '分配明细'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击分配明细","clickResult"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); const urlChanged = location.href.includes('assign') || location.href.includes('detail'); return { hasModal: !!modal, hasDrawer: !!drawer, urlChanged }; })()","验证分配明细响应","assignResult"),
        shot("tm-assign-detail","分配明细"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_TM,"分配明细展示审核员分配情况"))

# 7. 详情
save(meta("atomic-f88-tm-detail","UI：任务管理-详情操作验证",
    "点击详情链接，验证进入任务详情页",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '详情'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击详情","clickResult"),
        wait(2000),
        eva("(() => { return { url: location.href, hasContent: document.body.innerText.length > 100 }; })()","验证详情页","detailResult"),
        asrtS("detailResult","hasContent",desc="验证详情页有内容",equals=True),
        shot("tm-detail","任务详情")],
    PRE_TM,"详情页展示任务完整信息"))

# 8. 编辑
save(meta("atomic-f88-tm-edit","UI：任务管理-编辑操作验证",
    "点击编辑链接，验证编辑弹窗/页面",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击编辑","clickResult"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); return { hasModal: !!modal, hasDrawer: !!drawer }; })()","验证编辑入口","editForm"),
        shot("tm-edit","编辑任务"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_TM,"编辑可能为弹窗或页面跳转"))

# 9. 下载
save(meta("atomic-f88-tm-download","UI：任务管理-下载操作验证",
    "点击下载链接，验证下载触发",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '下载'); return { count: btns.length }; })()","查找下载按钮","dlBtns"),
        asrtS("dlBtns","count",desc="验证下载按钮存在",notEmpty=True),
        shot("tm-download","下载按钮")],
    PRE_TM,"下载任务相关数据"))

# 10. 删除
save(meta("atomic-f88-tm-delete","UI：任务管理-删除操作验证",
    "点击删除链接，验证确认弹窗",
    [nav("https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management?sourceTab=other"),wait(),
        eva(EXPAND_ALL,"展开所有节点"),wait(2000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '删除'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no btn'; })()","点击删除","clickResult"),
        wait(1500),
        eva("(() => { const pop = document.querySelector('.ant-popover,.ant-popconfirm,.ant-modal-confirm'); const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasPopconfirm: !!pop, hasModal: !!modal, text: (pop || modal)?.textContent?.trim()?.substring(0,100) || null }; })()","验证确认弹窗","confirmDlg"),
        shot("tm-delete-confirm","删除确认弹窗"),
        eva("(() => { const cancel = document.querySelector('.ant-popover .ant-btn:not(.ant-btn-primary),.ant-popconfirm .ant-btn:not(.ant-btn-primary)'); if(cancel) { cancel.click(); return 'cancelled'; } return 'no cancel'; })()","取消删除")],
    PRE_TM,"删除需确认弹窗",["P0"]))

# 11. 修正表格列名用例 - 更新为实际列名
with open(os.path.join(BASE, "atomic_f88_tm-table.json"), 'r') as f:
    table_case = json.load(f)

# 修正列名验证为截图中的实际列名
for step in table_case['steps']:
    if step.get('type') == 'evaluate' and '任务ID' in step.get('expression',''):
        step['expression'] = "(() => { const t = document.body.innerText; const cols = ['预期交付时间','审核状态','抽检状态','埋雷状态','任务时长','操作']; const found = cols.filter(c => t.includes(c)); return { cols, found, coverage: found.length+'/'+cols.length }; })()"
        step['description'] = "验证实际列名文案"
        break

table_case['_testDesign']['realDomNotes'] = "实际列: 任务名称/预期交付时间/审核状态&进度/抽检状态&进度/埋雷状态&进度/任务时长(除埋雷)/操作"
with open(os.path.join(BASE, "atomic_f88_tm-table.json"), 'w') as f:
    json.dump(table_case, f, ensure_ascii=False, indent=2)
print(f"  ✓ atomic_f88_tm-table.json (修正列名为实际截图列名)")

print("\n=== 任务管理补充完成 ===")
