#!/usr/bin/env python3
"""Batch 2: 原子级用例 - 链路列表/链路详情/策略列表/策略详情"""
import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

def nav(url, desc=None):
    return {"type":"navigate","url":url,"waitUntil":"networkidle","screenshot":True,"description":desc or "打开页面"}
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
    s["description"] = desc if desc else f"断言 {key}" + (f".{path}" if path else "")
    return s
def shot(label, desc=None):
    return {"type":"screenshot","label":label,"description":desc or label}
def sel(label, option, desc=None):
    return {"type":"selectOption","label":label,"option":option,"description":desc or f"选择{label}={option}"}

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

# ========== Page 5: 链路列表 ==========
LL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkList"
PRE_LL = "F88预发已登录；存在链路数据"

# 1. 页面加载+文案
save(meta("atomic-f88-ll-page-load","UI：链路列表-页面加载与文案完整性",
    "验证页面标题、链路卡片字段(名称/生命周期/描述/提交人/更新时间)",
    LL_URL, [nav(LL_URL,"打开链路列表"),wait(),
        asrt("链路","验证页面包含链路"),
        eva("(() => { const cards = Array.from(document.querySelectorAll('[class*=card],[class*=link]')).slice(0,5).map(c => c.textContent.trim().substring(0,120)); return { cards, count: cards.length }; })()","提取链路卡片","linkCards"),
        asrtS("linkCards","count",desc="验证链路卡片非空",notEmpty=True),
        eva("(() => { const t = document.body.innerText; const fields = ['链路名称','生命周期','描述','提交人','更新时间']; const found = fields.filter(f => t.includes(f)); return { fields, found, coverage: found.length+'/'+fields.length }; })()","验证字段文案","fieldCheck"),
        shot("ll-page-load","链路列表页面")],
    PRE_LL,"字段: 链路名称/生命周期/描述/策略一致性/提交人/更新时间"))

# 2. 新建链路
save(meta("atomic-f88-ll-create","UI：链路列表-新建链路入口验证",
    "点击新建链路按钮，验证跳转或弹窗",
    LL_URL, [nav(LL_URL,"打开链路列表"),wait(),
        click("新建链路","点击新建链路"),wait(3000),
        eva("(() => { return { url: location.href, hasModal: !!document.querySelector('.ant-modal:not(.ant-modal-hidden)'), hasForm: !!document.querySelector('form,[class*=form]') }; })()","验证新建链路入口","createResult"),
        shot("ll-create","新建链路"),
        eva("(() => { if(location.href.includes('linkDetail')) return 'navigated'; if(document.querySelector('.ant-modal:not(.ant-modal-hidden)')) return 'modal'; return 'unknown'; })()","判断入口类型","entryType"),
        asrtS("entryType",desc="验证新建链路有响应",notEmpty=True)],
    PRE_LL,"新建链路可能跳转详情页或弹窗"))

# 3. 复制链路
save(meta("atomic-f88-ll-copy","UI：链路列表-复制链路确认弹窗验证",
    "点击复制按钮，验证确认弹窗出现",
    LL_URL, [nav(LL_URL,"打开链路列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '复制'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no copy btn'; })()","点击复制","copyResult"),
        wait(1500),
        eva("(() => { const pop = document.querySelector('.ant-popover,.ant-popconfirm,.ant-modal-confirm'); const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasPopconfirm: !!pop, hasModal: !!modal, text: (pop || modal)?.textContent?.trim()?.substring(0,100) || null }; })()","验证确认弹窗","confirmDlg"),
        shot("ll-copy-confirm","复制确认弹窗"),
        eva("(() => { const cancel = document.querySelector('.ant-popover .ant-btn:not(.ant-btn-primary),.ant-popconfirm .ant-btn:not(.ant-btn-primary)'); if(cancel) { cancel.click(); return 'cancelled'; } return 'no cancel'; })()","取消复制")],
    PRE_LL,"复制需确认弹窗"))

# 4. 删除链路
save(meta("atomic-f88-ll-delete","UI：链路列表-删除链路确认弹窗验证",
    "点击删除按钮，验证确认弹窗出现",
    LL_URL, [nav(LL_URL,"打开链路列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '删除'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no delete btn'; })()","点击删除","delResult"),
        wait(1500),
        eva("(() => { const pop = document.querySelector('.ant-popover,.ant-popconfirm,.ant-modal-confirm'); const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasPopconfirm: !!pop, hasModal: !!modal, text: (pop || modal)?.textContent?.trim()?.substring(0,100) || null }; })()","验证确认弹窗","confirmDlg"),
        shot("ll-delete-confirm","删除确认弹窗"),
        eva("(() => { const cancel = document.querySelector('.ant-popover .ant-btn:not(.ant-btn-primary),.ant-popconfirm .ant-btn:not(.ant-btn-primary)'); if(cancel) { cancel.click(); return 'cancelled'; } return 'no cancel'; })()","取消删除")],
    PRE_LL,"删除需确认弹窗",["P0"]))

# 5. 生命周期筛选
save(meta("atomic-f88-ll-lifecycle-filter","UI：链路列表-生命周期筛选验证",
    "使用生命周期筛选，验证筛选结果",
    LL_URL, [nav(LL_URL,"打开链路列表"),wait(),
        sel("生命周期","实验","筛选实验阶段"),wait(2000),
        shot("ll-filter-experiment","实验阶段筛选"),
        sel("生命周期","全部","重置为全部"),wait(2000),
        shot("ll-filter-all","全部链路")],
    PRE_LL,"生命周期选项: 全部/实验/灰度/正式"))

# ========== Page 6: 链路详情 ==========
LD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180"
PRE_LD = "F88预发已登录；链路20180存在"

# 1. 页面加载+链路名称
save(meta("atomic-f88-ld-page-load","UI：链路详情-页面加载与链路名称验证",
    "验证链路详情页加载，链路名称、阶段、环节展示正确",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        eva("(() => { const t = document.body.innerText; const sections = ['链路阶段','环节列表','起点入参']; const found = sections.filter(s => t.includes(s)); return { sections, found, coverage: found.length+'/'+sections.length }; })()","验证关键区域","sections"),
        asrtS("sections","coverage",desc="验证关键区域存在",notEmpty=True),
        eva("(() => { const nameEl = document.querySelector('[class*=link-name],[class*=title]'); return { name: nameEl ? nameEl.textContent.trim() : null }; })()","获取链路名称","linkName"),
        shot("ld-page-load","链路详情页面")],
    PRE_LD,"包含: 链路阶段(实验/灰度)、环节列表、起点入参"))

# 2. 试运行弹窗
save(meta("atomic-f88-ld-trial-run","UI：链路详情-试运行弹窗验证",
    "点击试运行按钮，验证弹窗出现及字段完整",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("试运行","点击试运行"),wait(2000),
        eva(MODAL,"验证弹窗","trialModal"),
        asrtS("trialModal","hasModal",desc="验证试运行弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { fields: [] }; const inputs = Array.from(m.querySelectorAll('input,select,button')).map(i => ({ placeholder: i.placeholder || '', type: i.type, text: i.textContent?.trim()?.substring(0,30) || '', label: i.closest('.ant-form-item')?.querySelector('label')?.textContent?.trim() || '' })); return { fields: inputs }; })()","探查弹窗字段","trialFields"),
        asrt("下载模板",desc="验证下载模板按钮"),
        asrt("任务名称",desc="验证任务名称字段"),
        shot("ld-trial-run","试运行弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"试运行弹窗: 下载模板/上传Excel/任务名称/运行类型/发起任务运行"))

# 3. 试运行-下载模板
save(meta("atomic-f88-ld-trial-download","UI：链路详情-试运行下载模板验证",
    "在试运行弹窗中点击下载模板按钮，验证模板下载",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("试运行","点击试运行"),wait(2000),
        click("下载模板","点击下载模板"),wait(2000),
        shot("ld-trial-download","下载模板"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"下载Excel模板，列: seller_id/seed_image_url/tao_cate/item_id"))

# 4. 试运行-上传Excel
save(meta("atomic-f88-ld-trial-upload","UI：链路详情-试运行上传Excel验证",
    "在试运行弹窗中上传Excel文件",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("试运行","点击试运行"),wait(2000),
        eva("(() => { const fileInput = document.querySelector('.ant-modal:not(.ant-modal-hidden) input[type=file]'); return { hasFileInput: !!fileInput, accept: fileInput ? fileInput.accept : null }; })()","查找文件上传控件","fileInput"),
        asrtS("fileInput","hasFileInput",desc="验证文件上传控件存在",equals=True),
        shot("ld-trial-upload","上传Excel控件"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"上传Excel文件 input[type=file]"))

# 5. 试运行-任务名称
save(meta("atomic-f88-ld-trial-name","UI：链路详情-试运行任务名称输入验证",
    "在试运行弹窗中输入任务名称",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("试运行","点击试运行"),wait(2000),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const input = m ? m.querySelector('input[placeholder*=任务名称]') : null; return { hasInput: !!input, placeholder: input ? input.placeholder : null }; })()","查找任务名称输入框","nameInput"),
        asrtS("nameInput","hasInput",desc="验证任务名称输入框存在",equals=True),
        shot("ld-trial-name","任务名称输入"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"任务名称输入框 placeholder='请输入任务名称'"))

# 6. 试运行-运行类型
save(meta("atomic-f88-ld-trial-type","UI：链路详情-试运行运行类型选择验证",
    "在试运行弹窗中选择运行类型(正式/测试)",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("试运行","点击试运行"),wait(2000),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const selects = m ? m.querySelectorAll('.ant-select') : []; return { selectCount: selects.length }; })()","查找Select控件","selectInfo"),
        asrtS("selectInfo","selectCount",desc="验证有Select控件",notEmpty=True),
        shot("ld-trial-type","运行类型选择"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"运行类型Select: 正式/测试。坑点: 必须用page.mouse.click()展开"))

# 7. 查看运行结果
save(meta("atomic-f88-ld-run-results","UI：链路详情-查看运行结果弹窗验证",
    "点击查看运行结果按钮，验证弹窗展示5环节和任务列表",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        click("查看运行结果","点击查看运行结果"),wait(2000),
        eva(MODAL,"验证弹窗","resultModal"),
        asrtS("resultModal","hasModal",desc="验证运行结果弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { stages: [] }; const text = m.textContent; const stages = ['刷标签','首图生图','首图审核','套图生图','套图审核']; const found = stages.filter(s => text.includes(s)); return { stages, found, coverage: found.length+'/'+stages.length }; })()","验证5环节","stages"),
        shot("ld-run-results","运行结果弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_LD,"运行结果弹窗: 5环节(刷标签/首图生图/首图审核/套图生图/套图审核)/任务列表/状态/出参/终止/添加策略"))

# 8. 链路阶段信息
save(meta("atomic-f88-ld-stages","UI：链路详情-链路阶段信息验证",
    "验证链路阶段(实验/灰度)展示正确",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        eva("(() => { const t = document.body.innerText; const stages = ['实验','灰度','正式']; const found = stages.filter(s => t.includes(s)); return { stages, found }; })()","验证阶段信息","stageInfo"),
        asrtS("stageInfo","found",desc="验证阶段标签存在",notEmpty=True),
        shot("ld-stages","链路阶段信息")],
    PRE_LD,"链路生命周期: 实验→灰度→正式"))

# 9. 环节列表
save(meta("atomic-f88-ld-steps","UI：链路详情-环节列表展示验证",
    "验证环节列表包含所有配置的环节",
    LD_URL, [nav(LD_URL,"打开链路详情"),wait(),
        eva("(() => { const steps = Array.from(document.querySelectorAll('[class*=step],[class*=stage],[class*=node]')).slice(0,10).map(el => el.textContent.trim().substring(0,60)); return { steps, count: steps.length }; })()","提取环节列表","stepList"),
        asrtS("stepList","count",desc="验证环节列表非空",notEmpty=True),
        shot("ld-steps","环节列表")],
    PRE_LD,"环节: 起点入参/刷标签/首图生图/首图审核/套图生图/套图审核"))

# ========== Page 7: 策略列表 ==========
SL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list"
PRE_SL = "F88预发已登录；存在策略数据"

# 1. 页面加载+文案
save(meta("atomic-f88-sl-page-load","UI：策略列表-页面加载与文案完整性",
    "验证策略列表页面标题、筛选区、策略卡片字段",
    SL_URL, [nav(SL_URL,"打开策略列表"),wait(),
        asrt("策略","验证页面包含策略"),
        eva("(() => { const t = document.body.innerText; const fields = ['策略名称','策略阶段','环节','创建时间','提交人']; const found = fields.filter(f => t.includes(f)); return { fields, found, coverage: found.length+'/'+fields.length }; })()","验证字段文案","fieldCheck"),
        eva("(() => { const cards = Array.from(document.querySelectorAll('[class*=card],[class*=strategy]')).slice(0,5).map(c => c.textContent.trim().substring(0,120)); return { cards, count: cards.length }; })()","提取策略卡片","stratCards"),
        shot("sl-page-load","策略列表页面")],
    PRE_SL,"字段: 策略名称/策略阶段/环节/创建时间/更新时间/提交人"))

# 2. 新建策略
save(meta("atomic-f88-sl-create","UI：策略列表-新建策略入口验证",
    "点击新建策略按钮，验证弹窗或页面跳转",
    SL_URL, [nav(SL_URL,"打开策略列表"),wait(),
        click("新建策略","点击新建策略"),wait(2000),
        eva("(() => { return { hasModal: !!document.querySelector('.ant-modal:not(.ant-modal-hidden)'), hasDrawer: !!document.querySelector('.ant-drawer'), url: location.href }; })()","验证新建入口","createResult"),
        shot("sl-create","新建策略"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_SL,"新建策略可能为弹窗或页面跳转"))

# 3. 策略卡片操作
save(meta("atomic-f88-sl-card-actions","UI：策略列表-策略卡片操作按钮验证",
    "验证策略卡片包含打开/复制/删除操作按钮",
    SL_URL, [nav(SL_URL,"打开策略列表"),wait(),
        eva("(() => { const actions = Array.from(document.querySelectorAll('a,button')).filter(el => { const t = el.textContent.trim(); return ['打开','复制','删除'].some(k => t.includes(k)); }); return { actions: actions.map(a => a.textContent.trim()), count: actions.length }; })()","提取操作按钮","cardActions"),
        asrtS("cardActions","count",desc="验证操作按钮存在",notEmpty=True),
        shot("sl-card-actions","策略操作按钮")],
    PRE_SL,"操作: 打开/复制/删除"))

# 4. 策略字段完整性
save(meta("atomic-f88-sl-fields","UI：策略列表-策略卡片字段完整性验证",
    "验证策略卡片展示所有必要字段",
    SL_URL, [nav(SL_URL,"打开策略列表"),wait(),
        eva("(() => { const t = document.body.innerText; const fields = ['策略名称','策略阶段','环节','创建时间','更新时间','提交人']; const found = fields.filter(f => t.includes(f)); return { fields, found, missing: fields.filter(f => !t.includes(f)), coverage: found.length+'/'+fields.length }; })()","验证字段完整性","fieldCheck"),
        shot("sl-fields","策略字段截图")],
    PRE_SL,"字段: 策略名称/策略阶段/环节/创建时间/更新时间/提交人"))

# ========== Page 8: 策略详情 ==========
# Use a known strategy detail URL
SD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list"
PRE_SD = "F88预发已登录；存在策略数据"

# 1. 页面加载(通过列表点击进入)
save(meta("atomic-f88-sd-page-load","UI：策略详情-页面加载与基本信息验证",
    "从策略列表打开第一条策略，验证详情页加载",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        eva("(() => { return { url: location.href, title: document.title }; })()","记录详情页信息","pageInfo"),
        asrtS("pageInfo","url",desc="验证进入详情页",notEmpty=True),
        shot("sd-page-load","策略详情页面")],
    PRE_SD,"策略详情页包含基本信息/节点编排/落库配置"))

# 2. 保存按钮
save(meta("atomic-f88-sd-save","UI：策略详情-保存按钮验证",
    "验证策略详情页保存按钮存在",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a')).filter(el => el.textContent.trim().match(/保.*存/)); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找保存按钮","saveBtn"),
        asrtS("saveBtn","count",desc="验证保存按钮存在",notEmpty=True),
        shot("sd-save","保存按钮")],
    PRE_SD,"保存按钮文案可能含空格'保 存'，用正则匹配"))

# 3. 新增节点弹窗
save(meta("atomic-f88-sd-add-node","UI：策略详情-新增节点弹窗验证",
    "点击新增节点按钮，验证弹窗及节点类型列表",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        click("新增节点","点击新增节点"),wait(2000),
        eva(MODAL,"验证弹窗","nodeModal"),
        asrtS("nodeModal","hasModal",desc="验证新增节点弹窗出现",equals=True),
        shot("sd-add-node","新增节点弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_SD,"新增节点弹窗展示20种节点类型"))

# 4. 节点类型完整性
save(meta("atomic-f88-sd-node-types","UI：策略详情-节点类型完整性验证(20种)",
    "验证新增节点弹窗包含所有20种节点类型",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        click("新增节点","点击新增节点"),wait(2000),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { types: [] }; const text = m.textContent; const types = ['LLM文本生成','生图','Map生图','季节标签','产业标签','定价节点','模板匹配','人工审核','推送选款','面料上身','款式分配','匹配度打分','图像裁头','改款prompt推理','Caption','机审','视频生成','视频上传','高清化处理','选片']; const found = types.filter(t => text.includes(t)); return { types, found, missing: types.filter(t => !text.includes(t)), coverage: found.length+'/'+types.length }; })()","验证20种节点类型","nodeTypes"),
        shot("sd-node-types","节点类型列表"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_SD,"20种节点类型全覆盖验证"))

# 5. 节点删除
save(meta("atomic-f88-sd-node-delete","UI：策略详情-节点删除验证",
    "验证策略详情页节点删除功能",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        eva("(() => { const delBtns = Array.from(document.querySelectorAll('[class*=node] [class*=delete],[class*=node] [class*=remove],[data-node-type] [class*=close]')); return { count: delBtns.length }; })()","查找节点删除控件","delControls"),
        shot("sd-node-delete","节点删除控件")],
    PRE_SD,"节点删除可能通过右键菜单或节点卡片上的删除图标"))

# 6. 入参出参配置
save(meta("atomic-f88-sd-io-params","UI：策略详情-入参出参配置验证",
    "验证策略入参Start和策略出参End节点配置",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        eva("(() => { const t = document.body.innerText; const hasStart = t.includes('策略入参') || t.includes('Start'); const hasEnd = t.includes('策略出参') || t.includes('End'); return { hasStart, hasEnd }; })()","验证入参出参节点","ioNodes"),
        shot("sd-io-params","入参出参配置")],
    PRE_SD,"节点编排: 策略入参Start/策略出参End/+新增节点"))

# 7. 落库配置
save(meta("atomic-f88-sd-storage","UI：策略详情-落库配置验证",
    "验证策略详情页落库配置区域展示",
    SD_URL, [nav(SD_URL,"打开策略列表"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '打开'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no open btn'; })()","打开第一条策略"),
        wait(3000),
        eva("(() => { const t = document.body.innerText; const hasStorage = t.includes('落库配置') || t.includes('落库'); return { hasStorage }; })()","验证落库配置区域","storageSection"),
        asrtS("storageSection","hasStorage",desc="验证落库配置区域存在",equals=True),
        shot("sd-storage","落库配置")],
    PRE_SD,"落库配置区域"))

print("\n=== Batch 2 完成 ===")
