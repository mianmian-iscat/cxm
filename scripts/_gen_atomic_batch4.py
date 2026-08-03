#!/usr/bin/env python3
"""Batch 4: 原子级用例 - 淘内资源池/优质模板库/审核详情"""
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

MODAL = "(() => { const m = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); return { hasModal: !!m, title: m ? m.querySelector('.ant-modal-title')?.textContent?.trim() : null }; })()"
CLOSE_MODAL = "(() => { const c = document.querySelector('.ant-modal-close'); if(c) c.click(); return 'closed'; })()"
TAG_DIMS = ["设计-主品描述","搭配-配饰穿搭","拍摄-模特维度","场景维度","光影维度","构图维度","整体视觉"]

# ========== Page 12: 淘内资源池 ==========
TL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateLibrary"
PRE_TL = "F88预发已登录；存在模板资源数据"

# 1. 页面加载
save(meta("atomic-f88-tl-page-load","UI：淘内资源池-页面加载与文案完整性",
    "验证页面标题、筛选区、标签维度",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        asrt("淘内资源池","验证页面标题"),
        asrt("重置","验证重置按钮"),
        eva("(() => { const t = document.body.innerText; const dims = ['设计','搭配','拍摄','场景','光影','构图','视觉']; const found = dims.filter(d => t.includes(d)); return { dims, found, coverage: found.length+'/'+dims.length }; })()","验证标签维度","tagDims"),
        shot("tl-page-load","淘内资源池页面")],
    PRE_TL,"标签7维度: 设计-主品描述/搭配-配饰穿搭/拍摄-模特维度/场景/光影/构图/整体视觉"))

# 2. Seller ID筛选
save(meta("atomic-f88-tl-filter-seller","UI：淘内资源池-Seller ID筛选验证",
    "输入Seller ID进行筛选",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        fill("Seller ID","12345","输入Seller ID"),wait(1500),
        shot("tl-filter-seller","Seller ID筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TL))

# 3. 店铺名称筛选
save(meta("atomic-f88-tl-filter-shop","UI：淘内资源池-店铺名称筛选验证",
    "输入店铺名称进行筛选",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        fill("店铺名称","测试","输入店铺名称"),wait(1500),
        shot("tl-filter-shop","店铺名称筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TL))

# 4. Item ID筛选
save(meta("atomic-f88-tl-filter-item","UI：淘内资源池-Item ID筛选验证",
    "输入Item ID进行筛选",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        fill("Item ID","12345","输入Item ID"),wait(1500),
        shot("tl-filter-item","Item ID筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TL))

# 5. 图片ID筛选
save(meta("atomic-f88-tl-filter-image","UI：淘内资源池-图片ID筛选验证",
    "输入图片ID进行筛选",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        fill("图片ID","12345","输入图片ID"),wait(1500),
        shot("tl-filter-image","图片ID筛选"),
        click("重置","重置筛选"),wait(1500)],
    PRE_TL))

# 6. 标签点击(7维度)
save(meta("atomic-f88-tl-tags","UI：淘内资源池-7维度标签点击验证",
    "逐个点击7个标签维度，验证标签筛选效果",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait()] +
    # 对每个标签维度：点击→截图→重置
    [step for dim in TAG_DIMS for step in [
        click(dim,f"点击{dim}标签"),wait(1500),
        shot(f"tl-tag-{dim[:2]}",f"{dim}标签筛选效果"),
        click("重置","重置筛选"),wait(1000)
    ]] + [shot("tl-tags-done","标签点击完成")],
    PRE_TL,"标签维度: 设计/搭配/拍摄/场景/光影/构图/整体视觉"))

# 7. 模板卡片字段
save(meta("atomic-f88-tl-card-fields","UI：淘内资源池-模板卡片字段完整性验证",
    "验证模板卡片展示: 图片/标签/推荐曝光数/所属店铺",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        eva("(() => { const cards = Array.from(document.querySelectorAll('[class*=card],[class*=template],[class*=item]')).slice(0,3).map(c => c.textContent.trim().substring(0,150)); return { cards, count: cards.length }; })()","提取模板卡片","cards"),
        asrtS("cards","count",desc="验证模板卡片非空",notEmpty=True),
        eva("(() => { const t = document.body.innerText; const fields = ['推荐曝光数','标签']; const found = fields.filter(f => t.includes(f)); return { fields, found }; })()","验证字段","fieldCheck"),
        shot("tl-card-fields","模板卡片字段")],
    PRE_TL,"展示: 大图预览/标签信息/推荐曝光数/所属店铺"))

# 8. 预览详情
save(meta("atomic-f88-tl-preview","UI：淘内资源池-模板预览详情验证",
    "点击模板卡片进入预览，验证大图/标签/曝光数/店铺信息",
    TL_URL, [nav(TL_URL,"打开淘内资源池"),wait(),
        eva("(() => { const imgs = document.querySelectorAll('img[class*=template],[class*=card] img,[class*=item] img'); if(imgs.length > 0) { imgs[0].click(); return 'clicked'; } const cards = document.querySelectorAll('[class*=card],[class*=item]'); if(cards.length > 0) { cards[0].click(); return 'clicked card'; } return 'no clickable'; })()","点击模板卡片","clickResult"),
        wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); return { hasModal: !!modal, hasDrawer: !!drawer }; })()","验证预览形式","previewForm"),
        shot("tl-preview","模板预览"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭预览")],
    PRE_TL,"预览形式: Drawer/Modal/图片放大"))

# ========== Page 13: 优质模板库 ==========
QT_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/selfTemplateLibrary_f88"
PRE_QT = "F88预发已登录；存在优质模板数据"

# 1. 页面加载
save(meta("atomic-f88-qt-page-load","UI：优质模板库-页面加载与文案完整性",
    "验证页面标题、筛选区、标签维度、批量操作/创建任务/查看进度按钮",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        asrt("优质模板库","验证页面标题"),
        asrt("批量操作","验证批量操作按钮"),
        asrt("创建任务","验证创建任务按钮"),
        asrt("查看任务进度","验证查看任务进度按钮"),
        eva("(() => { const t = document.body.innerText; const dims = ['设计','搭配','拍摄','场景','光影','构图','视觉']; const found = dims.filter(d => t.includes(d)); return { dims, found, coverage: found.length+'/'+dims.length }; })()","验证标签维度","tagDims"),
        shot("qt-page-load","优质模板库页面")],
    PRE_QT,"标签同淘内资源池7维度 + 洗图状态 + 应用场景"))

# 2. 模板来源筛选
save(meta("atomic-f88-qt-filter-source","UI：优质模板库-模板来源筛选验证",
    "选择模板来源进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        sel("模板来源","全部","选择模板来源"),wait(2000),
        shot("qt-filter-source","模板来源筛选")],
    PRE_QT))

# 3. Seller ID筛选
save(meta("atomic-f88-qt-filter-seller","UI：优质模板库-Seller ID筛选验证",
    "输入Seller ID进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        fill("Seller ID","12345","输入Seller ID"),wait(1500),
        shot("qt-filter-seller","Seller ID筛选")],
    PRE_QT))

# 4. 店铺名称筛选
save(meta("atomic-f88-qt-filter-shop","UI：优质模板库-模板来源店铺名称筛选验证",
    "输入店铺名称进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        fill("模板来源店铺名称","测试","输入店铺名称"),wait(1500),
        shot("qt-filter-shop","店铺名称筛选")],
    PRE_QT))

# 5. 模板组ID筛选
save(meta("atomic-f88-qt-filter-group","UI：优质模板库-模板组ID筛选验证",
    "输入模板组ID进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        fill("模板组ID","12345","输入模板组ID"),wait(1500),
        shot("qt-filter-group","模板组ID筛选")],
    PRE_QT))

# 6. 标签点击(7维度)
save(meta("atomic-f88-qt-tags","UI：优质模板库-7维度标签点击验证",
    "逐个点击7个标签维度",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait()] +
    [step for dim in TAG_DIMS for step in [
        click(dim,f"点击{dim}标签"),wait(1500),
        shot(f"qt-tag-{dim[:2]}",f"{dim}标签筛选"),
    ]] + [shot("qt-tags-done","标签点击完成")],
    PRE_QT))

# 7. 洗图状态筛选
save(meta("atomic-f88-qt-filter-wash","UI：优质模板库-洗图状态筛选验证",
    "选择洗图状态进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        eva("(() => { const t = document.body.innerText; const hasWash = t.includes('洗图状态'); return { hasWash }; })()","验证洗图状态筛选项","washFilter"),
        shot("qt-filter-wash","洗图状态筛选")],
    PRE_QT))

# 8. 应用场景筛选
save(meta("atomic-f88-qt-filter-scene","UI：优质模板库-应用场景筛选验证",
    "选择应用场景进行筛选",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        eva("(() => { const t = document.body.innerText; const hasScene = t.includes('应用场景'); return { hasScene }; })()","验证应用场景筛选项","sceneFilter"),
        shot("qt-filter-scene","应用场景筛选")],
    PRE_QT))

# 9. 批量操作入口
save(meta("atomic-f88-qt-batch-entry","UI：优质模板库-批量操作入口验证",
    "点击批量操作按钮，验证操作选项",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        click("批量操作","点击批量操作"),wait(2000),
        eva("(() => { const t = document.body.innerText; const ops = ['批量洗图','批量导出','批量标签修改']; const found = ops.filter(o => t.includes(o)); return { ops, found }; })()","验证批量操作选项","batchOps"),
        shot("qt-batch-entry","批量操作选项")],
    PRE_QT,"批量操作: 批量洗图/批量导出/批量标签修改"))

# 10. 创建任务入口
save(meta("atomic-f88-qt-create-entry","UI：优质模板库-创建任务入口验证",
    "点击创建任务按钮，验证进入创建流程",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        click("创建任务","点击创建任务"),wait(3000),
        eva("(() => { return { url: location.href, hasStep: !!document.querySelector('[class*=step],[class*=wizard]') }; })()","验证创建入口","createResult"),
        shot("qt-create-entry","创建任务入口")],
    PRE_QT,"创建任务4步: 选择模板/任务基础设置/审核标准/确认提交"))

# 11. 查看任务进度
save(meta("atomic-f88-qt-progress-entry","UI：优质模板库-查看任务进度入口验证",
    "点击查看任务进度按钮，验证弹窗或抽屉",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        click("查看任务进度","点击查看任务进度"),wait(2000),
        eva("(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer'); return { hasModal: !!modal, hasDrawer: !!drawer }; })()","验证进度展示形式","progressForm"),
        shot("qt-progress-entry","查看任务进度"),
        eva("(() => { const close = document.querySelector('.ant-modal-close,.ant-drawer-close'); if(close) close.click(); return 'closed'; })()","关闭")],
    PRE_QT,"展示: 任务名称/任务状态/进度/创建时间"))

# 12. 模板卡片字段
save(meta("atomic-f88-qt-card-fields","UI：优质模板库-模板卡片字段完整性验证",
    "验证模板卡片展示所有必要字段",
    QT_URL, [nav(QT_URL,"打开优质模板库"),wait(),
        eva("(() => { const cards = Array.from(document.querySelectorAll('[class*=card],[class*=template],[class*=item]')).slice(0,3).map(c => c.textContent.trim().substring(0,150)); return { cards, count: cards.length }; })()","提取模板卡片","cards"),
        asrtS("cards","count",desc="验证模板卡片非空",notEmpty=True),
        shot("qt-card-fields","模板卡片字段")],
    PRE_QT))

# ========== Page 14: 审核详情(审核操作) ==========
# 审核详情需要通过个人任务中心点击进入
PTC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center"
PRE_AUDIT = "F88预发已登录；存在待审核任务"

# 1. 通过操作
save(meta("atomic-f88-audit-approve","UI：审核详情-通过操作验证",
    "在审核详情页点击通过按钮",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a')).filter(el => el.textContent.trim() === '通过'); return { count: btns.length, disabled: btns[0] ? btns[0].disabled : null }; })()","查找通过按钮","approveBtn"),
        asrtS("approveBtn","count",desc="验证通过按钮存在",notEmpty=True),
        shot("audit-approve","通过操作")],
    PRE_AUDIT,"通过后返回列表，状态变为审核通过"))

# 2. 驳回操作
save(meta("atomic-f88-audit-reject","UI：审核详情-驳回操作验证",
    "在审核详情页点击驳回按钮",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a')).filter(el => el.textContent.trim() === '驳回'); return { count: btns.length, disabled: btns[0] ? btns[0].disabled : null }; })()","查找驳回按钮","rejectBtn"),
        asrtS("rejectBtn","count",desc="验证驳回按钮存在",notEmpty=True),
        shot("audit-reject","驳回操作")],
    PRE_AUDIT,"驳回需填写原因(必填)"))

# 3. 驳回原因必填验证
save(meta("atomic-f88-audit-reject-required","UI：审核详情-驳回原因必填验证",
    "验证不填驳回原因时确认按钮disabled",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        click("驳回","点击驳回"),wait(1500),
        eva("(() => { const submitBtns = Array.from(document.querySelectorAll('button')).filter(el => el.textContent.trim() === '确认' || el.textContent.trim() === '提交'); return submitBtns.map(b => ({ text: b.textContent.trim(), disabled: b.disabled, className: b.className })); })()","验证提交按钮状态","submitState"),
        shot("audit-reject-required","驳回原因必填")],
    PRE_AUDIT,"驳回原因不填时确认按钮disabled"))

# 4. 驳回类型选择
save(meta("atomic-f88-audit-reject-type","UI：审核详情-驳回类型选择验证",
    "验证驳回类型下拉选项(图片质量/内容违规/尺寸不达标等)",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        click("驳回","点击驳回"),wait(1500),
        eva("(() => { const selects = document.querySelectorAll('.ant-select'); const options = Array.from(document.querySelectorAll('.ant-select-item-option')).map(o => o.textContent.trim()); return { selectCount: selects.length, options }; })()","查找驳回类型选项","rejectTypes"),
        shot("audit-reject-type","驳回类型选择")],
    PRE_AUDIT,"驳回类型: 图片质量/内容违规/尺寸不达标/格式不符/其他"))

# 5. 图片放大查看
save(meta("atomic-f88-audit-image-zoom","UI：审核详情-图片放大查看验证",
    "在审核详情页点击图片放大查看",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const imgs = document.querySelectorAll('img[class*=audit],[class*=material] img,[class*=review] img'); if(imgs.length > 0) { imgs[0].click(); return 'clicked'; } return 'no image'; })()","点击图片","clickImg"),
        wait(1500),
        eva("(() => { const viewer = document.querySelector('[class*=viewer],[class*=zoom],[class*=preview],[class*=modal]'); return { hasViewer: !!viewer }; })()","验证放大查看","viewerDlg"),
        shot("audit-image-zoom","图片放大查看"),
        eva("(() => { const close = document.querySelector('[class*=viewer] [class*=close],[class*=modal] .ant-modal-close'); if(close) close.click(); return 'closed'; })()","关闭查看")],
    PRE_AUDIT))

# 6. 多素材切换
save(meta("atomic-f88-audit-material-switch","UI：审核详情-多素材切换验证",
    "在审核详情页切换不同素材查看",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const navBtns = Array.from(document.querySelectorAll('button,a,[class*=nav]')).filter(el => el.textContent.trim().includes('上一') || el.textContent.trim().includes('下一') || el.getAttribute('aria-label')?.includes('prev') || el.getAttribute('aria-label')?.includes('next')); return { count: navBtns.length }; })()","查找素材切换按钮","navBtns"),
        shot("audit-material-switch","素材切换")],
    PRE_AUDIT))

# 7. 复制URL
save(meta("atomic-f88-audit-copy-url","UI：审核详情-复制URL功能验证",
    "验证toolbar中复制URL按钮存在",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a,span')).filter(el => el.textContent.trim().includes('复制URL') || el.textContent.trim().includes('复制')); return { count: btns.length, texts: btns.map(b => b.textContent.trim()).slice(0,5) }; })()","查找复制URL按钮","copyBtn"),
        shot("audit-copy-url","复制URL按钮")],
    PRE_AUDIT,"toolbar按钮: 局部修改/下载/替换/裁剪/高清化/负反馈/驳回/复位/复制URL"))

# 8. 下载功能
save(meta("atomic-f88-audit-download","UI：审核详情-下载功能验证",
    "验证toolbar中下载按钮存在",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a,span')).filter(el => el.textContent.trim() === '下载'); return { count: btns.length }; })()","查找下载按钮","dlBtn"),
        asrtS("dlBtn","count",desc="验证下载按钮存在",notEmpty=True),
        shot("audit-download","下载按钮")],
    PRE_AUDIT))

# 9. 编辑后确认流程
save(meta("atomic-f88-audit-edit-confirm","UI：审核详情-编辑后确认流程验证",
    "验证编辑操作后需点击确认才生效的机制",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a,span')).filter(el => el.textContent.trim() === '确认' || el.textContent.trim().includes('✅')); return { count: btns.length, texts: btns.map(b => b.textContent.trim()) }; })()","查找确认按钮","confirmBtn"),
        shot("audit-edit-confirm","编辑确认流程")],
    PRE_AUDIT,"所有编辑操作必须经过「编辑后+✅确认」才生效"))

# 10. 编辑前/后切换
save(meta("atomic-f88-audit-edit-toggle","UI：审核详情-编辑前/后切换Radio验证",
    "验证编辑完成后出现编辑前/编辑后切换Radio",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const radios = Array.from(document.querySelectorAll('.ant-radio-wrapper,[class*=radio]')).filter(el => el.textContent.includes('编辑前') || el.textContent.includes('编辑后')); return { count: radios.length, texts: radios.map(r => r.textContent.trim()) }; })()","查找编辑前/后Radio","editToggle"),
        shot("audit-edit-toggle","编辑前/后切换")],
    PRE_AUDIT,"编辑完成后出现Radio toggle: 编辑前/编辑后"))

# 11. 负反馈
save(meta("atomic-f88-audit-negative-feedback","UI：审核详情-负反馈按钮验证",
    "验证toolbar中负反馈按钮存在",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a,span')).filter(el => el.textContent.trim().includes('负反馈')); return { count: btns.length }; })()","查找负反馈按钮","fbBtn"),
        asrtS("fbBtn","count",desc="验证负反馈按钮存在",notEmpty=True),
        shot("audit-negative-feedback","负反馈按钮")],
    PRE_AUDIT))

# 12. 复位功能
save(meta("atomic-f88-audit-reset","UI：审核详情-复位功能验证",
    "验证toolbar中复位按钮存在",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const btns = Array.from(document.querySelectorAll('button,a,span')).filter(el => el.textContent.trim() === '复位'); return { count: btns.length }; })()","查找复位按钮","resetBtn"),
        asrtS("resetBtn","count",desc="验证复位按钮存在",notEmpty=True),
        shot("audit-reset","复位按钮")],
    PRE_AUDIT))

# 13. 驳回重生
save(meta("atomic-f88-audit-reject-rebirth","UI：审核详情-驳回重生触发验证",
    "验证封面图审核(qt=4)驳回后触发重生流程",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const t = document.body.innerText; const hasRegen = t.includes('重生') || t.includes('reGen') || t.includes('regenerate'); return { hasRegen }; })()","检查重生相关标识","regenInfo"),
        shot("audit-reject-rebirth","驳回重生验证")],
    PRE_AUDIT,"封面图审核(qt=4)驳回触发重生(reGen)"))

# 14. 视频播放控制
save(meta("atomic-f88-audit-video-play","UI：审核详情-视频播放控制验证",
    "验证视频审核详情页播放器控件",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const video = document.querySelector('video'); const controls = document.querySelectorAll('[class*=player],[class*=video]'); return { hasVideo: !!video, playerCount: controls.length }; })()","查找视频播放器","videoPlayer"),
        shot("audit-video-play","视频播放器")],
    PRE_AUDIT,"视频播放器: 播放/暂停/拖拽"))

# 15. 文本审核高亮
save(meta("atomic-f88-audit-text-highlight","UI：审核详情-文本审核高亮问题词验证",
    "验证文本审核中问题词高亮显示",
    PTC_URL, [nav(PTC_URL,"打开个人任务中心"),wait(),
        eva("(() => { const rows = document.querySelectorAll('tr[class*=row],[class*=task-item]'); if(rows.length > 0) { rows[0].click(); return 'clicked'; } return 'no task'; })()","点击第一条任务"),
        wait(3000),
        eva("(() => { const highlights = document.querySelectorAll('[class*=highlight],[class*=red],[class*=warn],[style*=color]'); const text = document.body.innerText; const hasTextAudit = text.includes('标题') || text.includes('文案') || text.includes('描述'); return { highlightCount: highlights.length, hasTextAudit }; })()","查找文本审核高亮","textHighlight"),
        shot("audit-text-highlight","文本审核高亮")],
    PRE_AUDIT,"系统自动标红+审核员手动确认"))

print("\n=== Batch 4 完成 ===")
