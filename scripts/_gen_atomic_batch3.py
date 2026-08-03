#!/usr/bin/env python3
"""Batch 3: 原子级用例 - 商家信息配置/生产看板/模版包管理"""
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
def fill(placeholder, value, desc=None):
    return {"type":"fill","selector":f"input[placeholder='{placeholder}']","value":value,"react":True,"description":desc or f"输入{placeholder}={value}"}

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

# ========== Page 9: 商家信息配置 ==========
MC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/shopConfig"
PRE_MC = "F88预发已登录；存在商家配置数据"

# 1. 页面加载+文案
save(meta("atomic-f88-mc-page-load","UI：商家信息配置-页面加载与文案完整性",
    "验证页面标题、表格列名(店铺信息/合作供应商/参考竞店/负责买手/视觉偏好/搭配偏好/参考视觉图例/操作)",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        eva(TH,"获取表格列名","headers"),
        asrtS("headers","count",desc="验证列名非空",notEmpty=True),
        eva("(() => { const t = document.body.innerText; const cols = ['店铺信息','合作供应商','参考竞店','负责买手','视觉偏好','搭配偏好','操作']; const found = cols.filter(c => t.includes(c)); return { cols, found, coverage: found.length+'/'+cols.length }; })()","验证列名文案","colCheck"),
        shot("mc-page-load","商家信息配置页面")],
    PRE_MC,"表格列: 店铺信息/合作供应商/参考竞店/负责买手/视觉偏好/搭配偏好/参考视觉图例/操作"))

# 2. 搜索功能
save(meta("atomic-f88-mc-search","UI：商家信息配置-搜索功能验证",
    "使用搜索框搜索商家，验证搜索结果",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        eva("(() => { const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.placeholder && i.placeholder.includes('搜索')); return inputs.map(i => ({ placeholder: i.placeholder })); })()","查找搜索框","searchInputs"),
        fill("请输入","测试商家","输入搜索关键词"),wait(1500),
        click("搜索","点击搜索"),wait(2000),
        shot("mc-search-result","搜索结果")],
    PRE_MC,"搜索框为React受控组件"))

# 3. 重置筛选
save(meta("atomic-f88-mc-reset","UI：商家信息配置-重置筛选验证",
    "点击重置筛选按钮，验证筛选条件清空",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        fill("请输入","测试","输入搜索条件"),wait(1000),
        click("重置筛选","点击重置筛选"),wait(2000),
        eva("(() => { const inputs = Array.from(document.querySelectorAll('input')); const searchInput = inputs.find(i => i.value); return { hasValue: !!searchInput, value: searchInput ? searchInput.value : '' }; })()","验证输入框已清空","resetCheck"),
        shot("mc-reset","重置筛选后")],
    PRE_MC,"重置按钮清空所有筛选条件"))

# 4. 编辑配置
save(meta("atomic-f88-mc-edit","UI：商家信息配置-编辑配置验证",
    "点击编辑按钮，验证编辑弹窗或行内编辑",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no edit btn'; })()","点击编辑","editResult"),
        wait(1500),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); const inlineEdit = document.querySelectorAll('.ant-input:not([disabled])'); return { hasModal: !!modal, hasDrawer: !!drawer, inlineEditCount: inlineEdit.length }; })()","验证编辑形式","editForm"),
        shot("mc-edit","编辑配置"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭编辑")],
    PRE_MC,"编辑可能为行内编辑或弹窗编辑"))

# 5. 批量下载
save(meta("atomic-f88-mc-batch-download","UI：商家信息配置-批量下载功能验证",
    "验证批量下载按钮存在及功能",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a')).filter(el => el.textContent.trim().includes('批量下载')); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找批量下载按钮","dlBtn"),
        asrtS("dlBtn","count",desc="验证批量下载按钮存在",notEmpty=True),
        shot("mc-batch-download","批量下载按钮")],
    PRE_MC,"批量下载为异步任务，需等待下载链接"))

# 6. 表格结构
save(meta("atomic-f88-mc-table","UI：商家信息配置-表格结构验证",
    "验证商家配置表格结构完整",
    MC_URL, [nav(MC_URL,"打开商家信息配置"),wait(),
        eva("(() => { const table = document.querySelector('table,.ant-table'); const rows = document.querySelectorAll('tbody tr'); return { hasTable: !!table, rowCount: rows.length }; })()","验证表格结构","tableInfo"),
        asrtS("tableInfo","hasTable",desc="验证表格存在",equals=True),
        asrtS("tableInfo","rowCount",desc="验证表格有数据行",notEmpty=True),
        shot("mc-table","表格结构")],
    PRE_MC))

# ========== Page 10: 生产看板 ==========
PD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/productionDashboard"
PRE_PD = "F88预发已登录；存在生产数据"

# 1. 页面加载
save(meta("atomic-f88-pd-page-load","UI：生产看板-页面加载与标题验证",
    "验证生产看板页面加载和标题",
    PD_URL, [nav(PD_URL,"打开生产看板"),wait(),
        asrt("生产看板","验证页面标题"),
        shot("pd-page-load","生产看板页面")],
    PRE_PD))

# 2. 推送进度4指标
save(meta("atomic-f88-pd-push-metrics","UI：生产看板-整体推送进度4项指标验证",
    "验证总任务数/生产中/已推送/未推送4项指标展示",
    PD_URL, [nav(PD_URL,"打开生产看板"),wait(),
        eva("(() => { const t = document.body.innerText; const metrics = ['总任务数','生产中','已推送','未推送']; const found = metrics.filter(m => t.includes(m)); return { metrics, found, missing: metrics.filter(m => !t.includes(m)), coverage: found.length+'/'+metrics.length }; })()","验证4项指标","pushMetrics"),
        shot("pd-push-metrics","推送进度指标")],
    PRE_PD,"指标: 总任务数/生产中/已推送/未推送"))

# 3. 链路生产进度表格
save(meta("atomic-f88-pd-link-progress","UI：生产看板-链路生产进度表格验证",
    "验证链路生产进度表格展示",
    PD_URL, [nav(PD_URL,"打开生产看板"),wait(),
        eva("(() => { const tables = document.querySelectorAll('table,.ant-table'); const rows = Array.from(document.querySelectorAll('tbody tr')).slice(0,5).map(tr => ({ text: tr.textContent.trim().substring(0,100) })); return { tableCount: tables.length, sampleRows: rows }; })()","验证进度表格","progressTable"),
        asrtS("progressTable","tableCount",desc="验证进度表格存在",notEmpty=True),
        shot("pd-link-progress","链路生产进度")],
    PRE_PD,"按链路展示批次/状态/进度条"))

# 4. 任务展开
save(meta("atomic-f88-pd-task-expand","UI：生产看板-任务展开功能验证",
    "验证看板中任务可展开查看详情",
    PD_URL, [nav(PD_URL,"打开生产看板"),wait(),
        eva("(() => { const expandIcons = document.querySelectorAll('.ant-table-row-expand-icon,[class*=expand]'); return { count: expandIcons.length }; })()","查找展开控件","expandControls"),
        shot("pd-task-expand","任务展开控件")],
    PRE_PD))

# 5. 任务下载
save(meta("atomic-f88-pd-task-download","UI：生产看板-任务下载功能验证",
    "验证看板中任务下载按钮",
    PD_URL, [nav(PD_URL,"打开生产看板"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim().includes('下载')); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找下载按钮","dlBtns"),
        shot("pd-task-download","任务下载按钮")],
    PRE_PD))

# ========== Page 11: 模版包管理 ==========
TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement"
PRE_TM = "F88预发已登录；存在模版包数据"

# 1. 页面加载
save(meta("atomic-f88-tmgmt-page-load","UI：模版包管理-页面加载与文案完整性",
    "验证页面标题、店铺卡片列表、筛选区、按钮",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        asrt("模版包管理","验证页面标题"),
        asrt("重置","验证重置按钮"),
        asrt("新建模板包","验证新建按钮"),
        eva("(() => { const cards = Array.from(document.querySelectorAll('[class*=card],[class*=shop]')).slice(0,5).map(c => c.textContent.trim().substring(0,100)); return { cards, count: cards.length }; })()","提取店铺卡片","shopCards"),
        asrtS("shopCards","count",desc="验证店铺卡片非空",notEmpty=True),
        shot("tmgmt-page-load","模版包管理页面")],
    PRE_TM,"店铺卡片列表布局(非ant-table)，每卡片: 店铺名称/店铺ID/买手/模板包数量/使用状态"))

# 2. 店铺名称筛选
save(meta("atomic-f88-tmgmt-filter-shop-name","UI：模版包管理-店铺名称筛选验证",
    "输入店铺名称进行筛选",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        fill("店铺名称","测试","输入店铺名称"),wait(1500),
        shot("tmgmt-filter-shop-name","店铺名称筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TM,"店铺名称为React受控Input"))

# 3. 店铺ID筛选
save(meta("atomic-f88-tmgmt-filter-shop-id","UI：模版包管理-店铺ID筛选验证",
    "输入店铺ID进行筛选",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        fill("店铺ID","12345","输入店铺ID"),wait(1500),
        shot("tmgmt-filter-shop-id","店铺ID筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TM,"店铺ID为React受控Input"))

# 4. 买手名称筛选
save(meta("atomic-f88-tmgmt-filter-buyer","UI：模版包管理-买手名称筛选验证",
    "输入买手名称进行筛选",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        fill("买手名称","测试","输入买手名称"),wait(1500),
        shot("tmgmt-filter-buyer","买手名称筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TM,"买手名称为React受控Input"))

# 5. 使用状态筛选
save(meta("atomic-f88-tmgmt-filter-status","UI：模版包管理-使用状态筛选验证(AntD Select)",
    "选择使用状态进行筛选",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        sel("使用状态","使用中","筛选使用中"),wait(2000),
        shot("tmgmt-filter-status","使用状态筛选"),
        sel("使用状态","全部","重置"),wait(1500)],
    PRE_TM,"使用状态AntD Select: 全部/使用中/未使用"))

# 6. 新建模板包弹窗
save(meta("atomic-f88-tmgmt-create-modal","UI：模版包管理-新建模板包弹窗验证",
    "点击新建模板包按钮，验证弹窗及表单字段",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        click("新建模板包","点击新建模板包"),wait(2000),
        eva(MODAL,"验证弹窗","createModal"),
        asrtS("createModal","hasModal",desc="验证新建弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if(!m) return { fields: [] }; const inputs = Array.from(m.querySelectorAll('input,select,textarea')).map(i => ({ placeholder: i.placeholder || '', type: i.type, label: i.closest('.ant-form-item')?.querySelector('label')?.textContent?.trim() || '' })); return { fields: inputs }; })()","探查表单字段","formFields"),
        shot("tmgmt-create-modal","新建模板包弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_TM,"新建弹窗: 店铺选择/模板包名称/应用环节/应用场景/模板上传"))

# 7. 导入模板包弹窗
save(meta("atomic-f88-tmgmt-import-modal","UI：模版包管理-导入模板包弹窗验证",
    "点击导入模板包按钮，验证弹窗及文件上传控件",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        click("导入模板包","点击导入模板包"),wait(2000),
        eva(MODAL,"验证弹窗","importModal"),
        asrtS("importModal","hasModal",desc="验证导入弹窗出现",equals=True),
        eva("(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const fileInput = m ? m.querySelector('input[type=file]') : null; return { hasFileInput: !!fileInput, accept: fileInput ? fileInput.accept : null }; })()","验证文件上传","fileUpload"),
        shot("tmgmt-import-modal","导入模板包弹窗"),
        eva(CLOSE_MODAL,"关闭弹窗"),wait(1000)],
    PRE_TM,"导入弹窗: 上传文件(.xlsx/.zip)/店铺关联"))

# 8. 编辑模板包
save(meta("atomic-f88-tmgmt-edit","UI：模版包管理-编辑模板包入口验证",
    "通过卡片操作点击编辑，验证编辑弹窗",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '编辑'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no edit btn'; })()","点击编辑","editResult"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); return { hasModal: !!modal, hasDrawer: !!drawer }; })()","验证编辑入口","editForm"),
        shot("tmgmt-edit","编辑模板包"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_TM,"编辑后触发IDLE→DRAFT状态回退(风险点#20)"))

# 9. 激活/停用
save(meta("atomic-f88-tmgmt-toggle","UI：模版包管理-激活停用入口验证",
    "验证卡片操作区域激活/停用按钮存在",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => { const t = el.textContent.trim(); return t === '激活' || t === '停用'; }); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找激活/停用按钮","toggleBtns"),
        shot("tmgmt-toggle","激活停用按钮")],
    PRE_TM,"激活需检查同seller+range+scene仅一个IN_USE(风险点#15)"))

# 10. 卡片操作菜单
save(meta("atomic-f88-tmgmt-card-menu","UI：模版包管理-卡片操作菜单完整性验证",
    "验证店铺卡片包含查看详情/编辑/激活/停用操作",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        eva("(() => { const actions = Array.from(document.querySelectorAll('a,button')).filter(el => { const t = el.textContent.trim(); return ['查看详情','编辑','激活','停用'].some(k => t.includes(k)); }); return { actions: actions.map(a => a.textContent.trim()), count: actions.length }; })()","提取卡片操作","cardOps"),
        asrtS("cardOps","count",desc="验证卡片操作按钮存在",notEmpty=True),
        shot("tmgmt-card-menu","卡片操作菜单")],
    PRE_TM,"操作: 查看详情/编辑/激活/停用"))

# 11. 详情页模板列表
save(meta("atomic-f88-tmgmt-detail-list","UI：模版包管理-详情页模板列表验证",
    "点击查看详情，验证模板列表展示",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        click("查看详情","点击查看详情"),wait(3000),
        eva("(() => { return { url: location.href, hasTable: !!document.querySelector('table,.ant-table') }; })()","验证详情页","detailInfo"),
        eva(TH,"获取模板列表列名","detailHeaders"),
        shot("tmgmt-detail-list","详情页模板列表")],
    PRE_TM,"详情页列: 模板名称/模板预览/状态/创建时间/操作"))

# 12. 详情页预览
save(meta("atomic-f88-tmgmt-detail-preview","UI：模版包管理-详情页模板预览验证",
    "在详情页点击模板预览，验证图片预览功能",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        click("查看详情","点击查看详情"),wait(3000),
        eva("(() => { const previewBtns = Array.from(document.querySelectorAll('a,button,img')).filter(el => el.textContent?.trim() === '预览' || el.closest('[class*=preview]')); if(previewBtns.length > 0) { previewBtns[0].click(); return 'clicked'; } return 'no preview'; })()","点击预览","previewResult"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const viewer = document.querySelector('[class*=viewer],[class*=preview],[class*=gallery]'); return { hasModal: !!modal, hasViewer: !!viewer }; })()","验证预览功能","previewDlg"),
        shot("tmgmt-detail-preview","模板预览"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,[class*=close]'); if(close) close.click(); return 'closed'; })()","关闭预览")],
    PRE_TM,"模板图片预览，支持放大查看"))

# 13. 详情页停用
save(meta("atomic-f88-tmgmt-detail-deactivate","UI：模版包管理-详情页停用模板验证",
    "在详情页点击停用按钮，验证确认弹窗",
    TM_URL, [nav(TM_URL,"打开模版包管理"),wait(),
        click("查看详情","点击查看详情"),wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('a,button')).filter(el => el.textContent.trim() === '停用'); if(btns.length > 0) { btns[0].click(); return 'clicked'; } return 'no deactivate btn'; })()","点击停用","deactResult"),
        wait(1500),
        eva("(() => { const pop = document.querySelector('.ant-popover,.ant-popconfirm,.ant-modal-confirm'); return { hasConfirm: !!pop, text: pop?.textContent?.trim()?.substring(0,100) || null }; })()","验证确认弹窗","confirmDlg"),
        shot("tmgmt-detail-deactivate","停用确认"),
        eva("(() => { const cancel = document.querySelector('.ant-popover .ant-btn:not(.ant-btn-primary),.ant-popconfirm .ant-btn:not(.ant-btn-primary)'); if(cancel) { cancel.click(); return 'cancelled'; } return 'no cancel'; })()","取消停用")],
    PRE_TM))

print("\n=== Batch 3 完成 ===")
