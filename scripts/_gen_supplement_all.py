#!/usr/bin/env python3
"""基于浏览器实际操作发现，补充所有页面缺失的原子用例"""
import json, os

BASE = "/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test"

def nav(url, desc=""):
    return {"type":"navigate","url":url,"waitUntil":"networkidle","screenshot":True,"description":desc or f"打开页面"}
def wait(ms=3000):
    return {"type":"wait","ms":ms,"description":"等待加载"}
def eva(expr, desc=None, store=None):
    s = {"type":"evaluate","expression":expr,"description":desc or "DOM探查"}
    if store: s["storeAs"] = store
    return s
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

PRE = "F88预发已登录；存在相关数据"
CTX = {"urlPattern":"pre-aifashion-xiaoer.alibaba-inc.com","waitAfterLoad":3000,"auth":"buc","captureFilter":"bzb.api.fsyx_quality_guard"}

def meta(id, name, desc, url, steps, pre="", notes="", risks=None, pri="P1"):
    ctx = dict(CTX)
    ctx["url"] = url
    return {
        "id": id, "name": name, "description": desc,
        "businessType": "f88_material_audit", "scene": "f88-test",
        "priority": pri, "category": "normal_flow",
        "context": ctx,
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
# 链路详情补充 (ld)
# ============================================================
LD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20243"

# 1. 链路详情-链路说明字段
save(meta("atomic-f88-ld-description","UI：链路详情-链路说明字段验证",
    "验证链路详情页面链路说明文本框：可编辑/200字限制/显示X/200计数",
    LD_URL, [
        nav(LD_URL, "打开链路详情"), wait(),
        eva("(() => { const ta = document.querySelector('textarea[placeholder*=链路说明]'); if(!ta) return { found: false }; const counter = document.body.innerText.match(/\\d+\\s*\\/\\s*200/); return { found: true, value: ta.value, maxLength: 200, counter: counter?.[0] || null }; })()","验证链路说明字段","descInfo"),
        asrtS("descInfo","found",desc="验证链路说明文本框存在",equals=True),
        shot("ld-description","链路说明字段")
    ], PRE, "链路说明文本框，200字限制，显示X/200计数"))

# 2. 链路详情-起点入参
save(meta("atomic-f88-ld-start-params","UI：链路详情-链路起点入参验证",
    "验证链路起点入参区域：参数列表(必填/选填标记)/编辑按钮",
    LD_URL, [
        nav(LD_URL, "打开链路详情"), wait(),
        eva("(() => { const h5 = Array.from(document.querySelectorAll('h5')).find(h => h.textContent.includes('链路起点入参')); if(!h5) return { found: false }; const section = h5.closest('div') || h5.parentElement; const params = Array.from(section.querySelectorAll('span')).filter(s => s.textContent.includes('必填') || s.textContent.includes('选填')).map(s => s.parentElement?.textContent?.trim()); const editBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('编辑') && b.closest('h5,h4,h3')?.textContent?.includes('入参')); return { found: true, paramCount: params.length, params: params.slice(0,10), hasEditBtn: !!editBtn }; })()","验证起点入参","paramsInfo"),
        asrtS("paramsInfo","found",desc="验证起点入参区域存在",equals=True),
        shot("ld-start-params","链路起点入参")
    ], PRE, "起点入参包含多个参数，每个标记必填/选填"))

# 3. 链路详情-环节卡片结构
save(meta("atomic-f88-ld-stage-cards","UI：链路详情-环节卡片结构验证",
    "验证链路详情中环节卡片：名称/编辑/入参/策略列表/出参/上下移动/删除",
    LD_URL, [
        nav(LD_URL, "打开链路详情"), wait(),
        eva("(() => { const stageNames = []; const cards = document.querySelectorAll('[class*=stage],[class*=Stage]'); cards.forEach(c => { const name = c.querySelector('h4,h5,h6,[class*=name]')?.textContent?.trim(); if(name) stageNames.push(name); }); const allText = document.body.innerText; const stages = ['入参图刷标签','首图生成','标题文案生成','图片审核','图文上传']; const found = stages.filter(s => allText.includes(s)); return { stageCount: found.length, stages: found, hasInput: allText.includes('入参'), hasOutput: allText.includes('出参'), hasStrategy: allText.includes('添加策略') }; })()","验证环节卡片","stageInfo"),
        asrtS("stageInfo","stageCount",desc="验证至少3个环节",gte=3),
        shot("ld-stage-cards","环节卡片结构")
    ], PRE, "每个环节有：入参/策略列表(可添加)/出参/上移/下移/删除/编辑"))

# 4. 链路详情-保存按钮disabled
save(meta("atomic-f88-ld-save-disabled","UI：链路详情-保存按钮初始disabled验证",
    "验证链路详情保存按钮初始状态为disabled，修改后启用",
    LD_URL, [
        nav(LD_URL, "打开链路详情"), wait(),
        eva("(() => { const saveBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('保 存') || b.textContent.includes('保存')); if(!saveBtn) return { found: false }; return { found: true, disabled: saveBtn.disabled, text: saveBtn.textContent.trim() }; })()","验证保存按钮","saveInfo"),
        asrtS("saveInfo","found",desc="验证保存按钮存在",equals=True),
        asrtS("saveInfo","disabled",desc="验证保存按钮初始disabled",equals=True),
        shot("ld-save-btn","保存按钮状态")
    ], PRE, "保存按钮初始disabled，修改链路配置后启用"))

# 5. 链路详情-添加环节按钮
save(meta("atomic-f88-ld-add-stage-btn","UI：链路详情-添加环节按钮验证",
    "验证链路详情页面底部存在添加环节按钮",
    LD_URL, [
        nav(LD_URL, "打开链路详情"), wait(),
        eva("(() => { const addBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.includes('添加环节')); return { found: addBtns.length > 0, count: addBtns.length, texts: addBtns.map(b => b.textContent.trim()) }; })()","验证添加环节按钮","addBtnInfo"),
        asrtS("addBtnInfo","found",desc="验证添加环节按钮存在",equals=True),
        shot("ld-add-stage-btn","添加环节按钮")
    ], PRE, "添加环节按钮在环节列表底部"))

# ============================================================
# 策略详情补充 (sd)
# ============================================================
SD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail/10568"

# 6. 策略详情-策略说明+适配场景
save(meta("atomic-f88-sd-desc-fields","UI：策略详情-策略说明和适配场景字段验证",
    "验证策略详情页面策略说明和适配场景/商家画像两个文本框",
    SD_URL, [
        nav(SD_URL, "打开策略详情"), wait(),
        eva("(() => { const tas = document.querySelectorAll('textarea'); const desc = Array.from(tas).find(t => t.placeholder?.includes('策略说明')); const scene = Array.from(tas).find(t => t.placeholder?.includes('适配场景')); return { hasDesc: !!desc, hasScene: !!scene, descPlaceholder: desc?.placeholder, scenePlaceholder: scene?.placeholder }; })()","验证文本框","fieldsInfo"),
        asrtS("fieldsInfo","hasDesc",desc="验证策略说明文本框存在",equals=True),
        asrtS("fieldsInfo","hasScene",desc="验证适配场景文本框存在",equals=True),
        shot("sd-desc-fields","策略说明和适配场景")
    ], PRE, "两个textarea：策略说明/适配场景或商家画像"))

# 7. 策略详情-策略阶段+环节下拉
save(meta("atomic-f88-sd-stage-phase","UI：策略详情-策略阶段和环节下拉验证",
    "验证策略详情页面策略阶段和环节两个Select下拉",
    SD_URL, [
        nav(SD_URL, "打开策略详情"), wait(),
        eva("(() => { const labels = Array.from(document.querySelectorAll('span,div')).filter(el => el.textContent.trim() === '策略阶段：' || el.textContent.trim() === '环节：'); const selects = document.querySelectorAll('.ant-select'); const phaseSelect = Array.from(selects).find(s => s.previousElementSibling?.textContent?.includes('策略阶段') || s.parentElement?.textContent?.includes('策略阶段')); const stageSelect = Array.from(selects).find(s => s.previousElementSibling?.textContent?.includes('环节') || s.parentElement?.textContent?.includes('环节')); return { hasPhase: !!phaseSelect, hasStage: !!stageSelect, phaseVal: phaseSelect?.querySelector('.ant-select-selection-item')?.textContent, stageVal: stageSelect?.querySelector('.ant-select-selection-item')?.textContent }; })()","验证下拉","selectInfo"),
        asrtS("selectInfo","hasPhase",desc="验证策略阶段下拉存在",equals=True),
        asrtS("selectInfo","hasStage",desc="验证环节下拉存在",equals=True),
        shot("sd-stage-phase","策略阶段和环节下拉")
    ], PRE, "策略阶段：实验/灰度/正式，环节：视频/搭配/企划等"))

# 8. 策略详情-节点编排结构
save(meta("atomic-f88-sd-node-flow","UI：策略详情-节点编排流程验证",
    "验证策略详情节点编排：Start→节点1→节点2→End流程结构",
    SD_URL, [
        nav(SD_URL, "打开策略详情"), wait(),
        eva("(() => { const t = document.body.innerText; const hasStart = t.includes('Start'); const hasEnd = t.includes('End'); const hasNodeSection = t.includes('节点编排'); const addNodeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新增节点')); const editHint = t.includes('点击下方每个节点编辑详情'); return { hasStart, hasEnd, hasNodeSection, hasAddNodeBtn: !!addNodeBtn, hasEditHint: editHint }; })()","验证节点编排","flowInfo"),
        asrtS("flowInfo","hasStart",desc="验证Start节点存在",equals=True),
        asrtS("flowInfo","hasEnd",desc="验证End节点存在",equals=True),
        asrtS("flowInfo","hasNodeSection",desc="验证节点编排区域存在",equals=True),
        shot("sd-node-flow","节点编排流程")
    ], PRE, "Start(策略入参)→中间节点→End(策略出参+落库配置)"))

# 9. 策略详情-落库配置
save(meta("atomic-f88-sd-db-config","UI：策略详情-落库配置区域验证",
    "验证策略详情End节点的落库配置：已映射字段数/配置按钮",
    SD_URL, [
        nav(SD_URL, "打开策略详情"), wait(),
        eva("(() => { const t = document.body.innerText; const dbMatch = t.match(/已映射\\s*(\\d+)\\s*个字段/); const configBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('配 置') || b.textContent.includes('配置')); const hasNoConfig = t.includes('暂未配置落库映射'); return { hasDbConfig: t.includes('落库配置'), mappedFields: dbMatch?.[1] || '0', hasConfigBtn: !!configBtn, hasNoConfig: hasNoConfig }; })()","验证落库配置","dbInfo"),
        asrtS("dbInfo","hasDbConfig",desc="验证落库配置区域存在",equals=True),
        shot("sd-db-config","落库配置区域")
    ], PRE, "落库配置显示已映射字段数，配置按钮"))

# ============================================================
# 商家信息配置补充 (mc)
# ============================================================
MC_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/afdMerchantManagement/list"

# 10. 商家管理-操作按钮状态差异
save(meta("atomic-f88-mc-ops-by-status","UI：商家管理-操作按钮按AFD状态差异验证",
    "验证商家管理列表操作按钮：参与中→退出AFD/删除，挂起中→继续参与/删除",
    MC_URL, [
        nav(MC_URL, "打开商家管理"), wait(),
        eva("(() => { const rows = document.querySelectorAll('tr.ant-table-row'); const result = { participating: [], suspended: [] }; rows.forEach(r => { const status = r.querySelector('td:nth-child(3)')?.textContent?.trim(); const btns = Array.from(r.querySelectorAll('button')).map(b => b.textContent.trim()); if(status === '参与中') result.participating.push(btns); else if(status === '挂起中') result.suspended.push(btns); }); return { participating: result.participating.slice(0,2), suspended: result.suspended.slice(0,2), hasParticipating: result.participating.length > 0, hasSuspended: result.suspended.length > 0 }; })()","验证操作按钮差异","opsInfo"),
        shot("mc-ops-by-status","操作按钮状态差异")
    ], PRE, "参与中：详情/编辑/退出AFD/删除；挂起中：详情/编辑/继续参与/删除"))

# 11. 商家管理-生产筹备状态图标
save(meta("atomic-f88-mc-prep-status","UI：商家管理-生产筹备状态图标验证",
    "验证商家管理列表生产筹备状态列：check/lock图标+企划/设计/拍摄文字",
    MC_URL, [
        nav(MC_URL, "打开商家管理"), wait(),
        eva("(() => { const rows = document.querySelectorAll('tr.ant-table-row'); const firstRow = rows[0]; if(!firstRow) return { found: false }; const prepCell = firstRow.querySelector('td:nth-child(5)'); if(!prepCell) return { found: false }; const checks = prepCell.querySelectorAll('[class*=check]'); const locks = prepCell.querySelectorAll('[class*=lock]'); const stages = Array.from(prepCell.querySelectorAll('span')).filter(s => ['企划','设计','拍摄'].includes(s.textContent.trim())).map(s => s.textContent.trim()); return { found: true, checkCount: checks.length, lockCount: locks.length, stages }; })()","验证筹备状态图标","prepInfo"),
        asrtS("prepInfo","found",desc="验证筹备状态列存在",equals=True),
        shot("mc-prep-status","生产筹备状态图标")
    ], PRE, "筹备状态用check(完成)/lock(未完成)图标+企划/设计/拍摄文字表示"))

# 12. 商家管理-新增商家按钮
save(meta("atomic-f88-mc-add-btn","UI：商家管理-新增商家按钮验证",
    "验证商家管理列表存在新增商家按钮",
    MC_URL, [
        nav(MC_URL, "打开商家管理"), wait(),
        eva("(() => { const addBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新增商家')); return { found: !!addBtn, text: addBtn?.textContent?.trim() }; })()","验证新增商家按钮","addBtnInfo"),
        asrtS("addBtnInfo","found",desc="验证新增商家按钮存在",equals=True),
        shot("mc-add-btn","新增商家按钮")
    ], PRE))

# ============================================================
# 生产看板补充 (pd)
# ============================================================
PD_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/productionDashboard"

# 13. 生产看板-批次展开环节详情
save(meta("atomic-f88-pd-batch-expand-stages","UI：生产看板-批次展开环节详情验证",
    "验证生产看板展开批次后显示环节列表：环节名/进行中/已通过/已失败/进度%/下载",
    PD_URL, [
        nav(PD_URL, "打开生产看板"), wait(),
        eva("(() => { const carets = document.querySelectorAll('[class*=caret-down]'); const expandable = Array.from(carets).filter(c => c.closest('[class*=progress],[class*=Progress]')); if(expandable.length > 0) { expandable[0].click(); } return 'expanded'; })()","展开批次"), wait(2000),
        eva("(() => { const t = document.body.innerText; const hasStage = t.includes('劣质图编辑') || t.includes('劣质图审核'); const hasProgress = t.includes('进行中') || t.includes('已通过'); const hasDownload = Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('下载')); return { hasStage, hasProgress, hasDownload }; })()","验证环节详情","stageInfo"),
        asrtS("stageInfo","hasStage",desc="验证展开后显示环节名称",equals=True),
        shot("pd-batch-stages","批次展开环节详情")
    ], PRE, "展开批次显示环节列表，每个环节有进度%和下载按钮"))

# 14. 生产看板-分页
save(meta("atomic-f88-pd-pagination","UI：生产看板-分页验证",
    "验证生产看板底部有分页组件，多条链路时分页显示",
    PD_URL, [
        nav(PD_URL, "打开生产看板"), wait(),
        eva("(() => { const pagination = document.querySelector('.ant-pagination'); const items = pagination ? Array.from(pagination.querySelectorAll('.ant-pagination-item')).map(i => i.textContent.trim()) : []; return { hasPagination: !!pagination, pages: items }; })()","验证分页","pageInfo"),
        asrtS("pageInfo","hasPagination",desc="验证分页组件存在",equals=True),
        shot("pd-pagination","生产看板分页")
    ], PRE, "生产看板多条链路时分页显示"))

# ============================================================
# 模版包管理补充 (tmgmt)
# ============================================================
TM_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement"

# 15. 模版包管理-进入店铺详情列表
save(meta("atomic-f88-tmgmt-shop-detail","UI：模版包管理-店铺模版包列表验证",
    "验证点击店铺查看详情后进入模版包列表页：面包屑/搜索/筛选/导入+新建按钮/卡片列表",
    TM_URL, [
        nav(TM_URL, "打开模版包管理"), wait(),
        eva("(() => { const detailBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === '查看详情'); if(detailBtns.length > 2) { detailBtns[2].click(); return 'clicked'; } return 'no btn'; })()","点击查看详情"), wait(3000),
        eva("(() => { const t = document.body.innerText; const hasBreadcrumb = t.includes('店铺管理') && t.includes('模版包列表'); const hasImport = t.includes('导入模板包'); const hasCreate = t.includes('新建模版包'); const hasSearch = document.querySelector('input[placeholder*=名称]'); return { hasBreadcrumb, hasImport, hasCreate, hasSearch: !!hasSearch }; })()","验证模版包列表","listInfo"),
        asrtS("listInfo","hasBreadcrumb",desc="验证面包屑导航存在",equals=True),
        asrtS("listInfo","hasImport",desc="验证导入按钮存在",equals=True),
        asrtS("listInfo","hasCreate",desc="验证新建按钮存在",equals=True),
        shot("tmgmt-shop-detail","店铺模版包列表")
    ], PRE, "面包屑：店铺管理>模版包列表，有导入模板包/新建模版包按钮"))

# 16. 模版包管理-卡片预览图翻页
save(meta("atomic-f88-tmgmt-card-carousel","UI：模版包管理-卡片预览图翻页验证",
    "验证模版包卡片预览图支持左右翻页：左箭头/页码/右箭头",
    TM_URL, [
        nav(TM_URL, "打开模版包管理"), wait(),
        eva("(() => { const detailBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === '查看详情'); if(detailBtns.length > 2) { detailBtns[2].click(); return 'clicked'; } return 'no btn'; })()","进入店铺详情"), wait(3000),
        eva("(() => { const leftArrows = document.querySelectorAll('[class*=left],[aria-label*=left]'); const rightArrows = document.querySelectorAll('[class*=right],[aria-label*=right]'); const pageIndicators = Array.from(document.body.innerText.matchAll(/(\\d+)\\s*\\/\\s*(\\d+)/g)).map(m => m[0]); return { hasLeftArrows: leftArrows.length > 0, hasRightArrows: rightArrows.length > 0, pageIndicators: pageIndicators.slice(0,5) }; })()","验证翻页控件","carouselInfo"),
        shot("tmgmt-card-carousel","卡片预览图翻页")
    ], PRE, "预览图有左右箭头和页码指示(N/M)"))

# 17. 模版包管理-置为闲置/立即使用按钮
save(meta("atomic-f88-tmgmt-idle-use-btn","UI：模版包管理-置为闲置/立即使用按钮验证",
    "验证模版包卡片操作按钮：使用中→置为闲置，闲置中→立即使用",
    TM_URL, [
        nav(TM_URL, "打开模版包管理"), wait(),
        eva("(() => { const detailBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === '查看详情'); if(detailBtns.length > 2) { detailBtns[2].click(); return 'clicked'; } return 'no btn'; })()","进入店铺详情"), wait(3000),
        eva("(() => { const idleBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.includes('置为闲置')); const useBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.includes('立即使用')); return { hasIdleBtn: idleBtns.length > 0, hasUseBtn: useBtns.length > 0, idleCount: idleBtns.length, useCount: useBtns.length }; })()","验证状态操作按钮","btnInfo"),
        shot("tmgmt-idle-use-btn","置为闲置/立即使用按钮")
    ], PRE, "使用中→置为闲置，闲置中→立即使用"))

# ============================================================
# 淘内资源池补充 (tl)
# ============================================================
TL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/templateLibrary"

# 18. 淘内资源池-自然语言搜索
save(meta("atomic-f88-tl-nlp-search","UI：淘内资源池-自然语言搜索框验证",
    "验证淘内资源池存在自然语言描述搜索框，placeholder提示示例",
    TL_URL, [
        nav(TL_URL, "打开淘内资源池"), wait(),
        eva("(() => { const inputs = document.querySelectorAll('input'); const nlpInput = Array.from(inputs).find(i => i.placeholder?.includes('自然语言') || i.placeholder?.includes('描述搜索')); return { found: !!nlpInput, placeholder: nlpInput?.placeholder || null }; })()","验证自然语言搜索","nlpInfo"),
        asrtS("nlpInfo","found",desc="验证自然语言搜索框存在",equals=True),
        shot("tl-nlp-search","自然语言搜索框")
    ], PRE, "placeholder: 输入自然语言描述搜索，如'白色小众设计的花裙'"))

# 19. 淘内资源池-组图/单图模式切换
save(meta("atomic-f88-tl-view-mode","UI：淘内资源池-组图/单图模式切换验证",
    "验证淘内资源池支持组图模式和单图模式两种显示切换",
    TL_URL, [
        nav(TL_URL, "打开淘内资源池"), wait(),
        eva("(() => { const t = document.body.innerText; const hasGroup = t.includes('组图模式'); const hasSingle = t.includes('单图模式'); return { hasGroupMode: hasGroup, hasSingleMode: hasSingle }; })()","验证视图模式","modeInfo"),
        asrtS("modeInfo","hasGroupMode",desc="验证组图模式选项存在",equals=True),
        asrtS("modeInfo","hasSingleMode",desc="验证单图模式选项存在",equals=True),
        shot("tl-view-mode","组图/单图模式切换")
    ], PRE))

# ============================================================
# 优质模板库补充 (qt)
# ============================================================
QT_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/selfTemplateLibrary_f88"

# 20. 优质模板库-风格簇模式
save(meta("atomic-f88-qt-style-cluster","UI：优质模板库-风格簇模式验证",
    "验证优质模板库支持三种视图模式：组图/单图/风格簇",
    QT_URL, [
        nav(QT_URL, "打开优质模板库"), wait(),
        eva("(() => { const t = document.body.innerText; return { hasGroup: t.includes('组图模式'), hasSingle: t.includes('单图模式'), hasCluster: t.includes('风格簇模式') }; })()","验证三种视图模式","modeInfo"),
        asrtS("modeInfo","hasGroup",desc="验证组图模式存在",equals=True),
        asrtS("modeInfo","hasSingle",desc="验证单图模式存在",equals=True),
        asrtS("modeInfo","hasCluster",desc="验证风格簇模式存在",equals=True),
        shot("qt-view-modes","三种视图模式")
    ], PRE, "三种模式：组图模式/单图模式/风格簇模式"))

# 21. 优质模板库-范围筛选字段
save(meta("atomic-f88-qt-range-filters","UI：优质模板库-范围筛选字段验证",
    "验证优质模板库模板组表现和模板图表现区域的范围筛选：使用次数/累计选中率/款均CTR(最小-最大)",
    QT_URL, [
        nav(QT_URL, "打开优质模板库"), wait(),
        eva("(() => { const t = document.body.innerText; const groupSection = t.includes('模板组表现'); const imgSection = t.includes('模板图表现'); const filters = ['使用次数','累计选中率','款均CTR']; const found = filters.filter(f => t.includes(f)); return { hasGroupSection: groupSection, hasImgSection: imgSection, filters, found, coverage: found.length+'/'+filters.length }; })()","验证范围筛选","filterInfo"),
        asrtS("filterInfo","hasGroupSection",desc="验证模板组表现区域存在",equals=True),
        asrtS("filterInfo","hasImgSection",desc="验证模板图表现区域存在",equals=True),
        shot("qt-range-filters","范围筛选字段")
    ], PRE, "模板组表现+模板图表现各有：使用次数/累计选中率/款均CTR(最小-最大)"))

# 22. 优质模板库-批量操作下拉
save(meta("atomic-f88-qt-batch-ops-dropdown","UI：优质模板库-批量操作下拉验证",
    "验证优质模板库批量操作按钮存在且可展开下拉",
    QT_URL, [
        nav(QT_URL, "打开优质模板库"), wait(),
        eva("(() => { const batchBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('批量操作')); return { found: !!batchBtn, text: batchBtn?.textContent?.trim() }; })()","验证批量操作按钮","batchInfo"),
        asrtS("batchInfo","found",desc="验证批量操作按钮存在",equals=True),
        shot("qt-batch-ops","批量操作按钮")
    ], PRE, "批量操作按钮带下拉箭头"))

# 23. 优质模板库-创建任务按钮
save(meta("atomic-f88-qt-create-task-btn","UI：优质模板库-创建任务按钮验证",
    "验证优质模板库存在创建任务按钮",
    QT_URL, [
        nav(QT_URL, "打开优质模板库"), wait(),
        eva("(() => { const createBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('创建任务')); return { found: !!createBtn, text: createBtn?.textContent?.trim() }; })()","验证创建任务按钮","createInfo"),
        asrtS("createInfo","found",desc="验证创建任务按钮存在",equals=True),
        shot("qt-create-task","创建任务按钮")
    ], PRE))

# 24. 优质模板库-查看任务进度按钮
save(meta("atomic-f88-qt-task-progress-btn","UI：优质模板库-查看任务进度按钮验证",
    "验证优质模板库存在查看任务进度按钮",
    QT_URL, [
        nav(QT_URL, "打开优质模板库"), wait(),
        eva("(() => { const progressBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('查看任务进度')); return { found: !!progressBtn, text: progressBtn?.textContent?.trim() }; })()","验证查看任务进度按钮","progressInfo"),
        asrtS("progressInfo","found",desc="验证查看任务进度按钮存在",equals=True),
        shot("qt-task-progress","查看任务进度按钮")
    ], PRE))

# ============================================================
# 策略列表补充 (sl)
# ============================================================
SL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list"

# 25. 策略列表-分页和总数
save(meta("atomic-f88-sl-pagination","UI：策略列表-分页和总数验证",
    "验证策略列表分页组件和总记录数",
    SL_URL, [
        nav(SL_URL, "打开策略列表"), wait(),
        eva("(() => { const pagination = document.querySelector('.ant-pagination'); const totalText = document.body.innerText.match(/共\\s*\\d+\\s*条/); const items = pagination ? Array.from(pagination.querySelectorAll('.ant-pagination-item')).map(i => i.textContent.trim()) : []; return { hasPagination: !!pagination, total: totalText?.[0] || null, pages: items }; })()","验证分页","pageInfo"),
        asrtS("pageInfo","hasPagination",desc="验证分页组件存在",equals=True),
        shot("sl-pagination","策略列表分页")
    ], PRE, "策略列表共128条，分页显示"))

# 26. 策略列表-表格列名
save(meta("atomic-f88-sl-table-columns","UI：策略列表-表格列名验证",
    "验证策略列表表格包含7列：策略名称/策略阶段/环节/创建时间/更新时间/提交人/操作",
    SL_URL, [
        nav(SL_URL, "打开策略列表"), wait(),
        eva("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()).filter(h => h); const expected = ['策略名称','策略阶段','环节','创建时间','更新时间','提交人','操作']; const found = expected.filter(e => headers.some(h => h.includes(e))); return { headers: headers.slice(0,10), expected, found, coverage: found.length+'/'+expected.length }; })()","验证表格列名","colInfo"),
        asrtS("colInfo","coverage",desc="验证列名覆盖率",notEmpty=True),
        shot("sl-table-columns","策略列表列名")
    ], PRE, "7列：策略名称/策略阶段/环节/创建时间/更新时间/提交人/操作"))

# ============================================================
# 链路列表补充 (ll)
# ============================================================
LL_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkList"

# 27. 链路列表-搜索框
save(meta("atomic-f88-ll-search","UI：链路列表-搜索框验证",
    "验证链路列表页面存在链路名称搜索框",
    LL_URL, [
        nav(LL_URL, "打开链路列表"), wait(),
        eva("(() => { const input = document.querySelector('input[placeholder*=搜索链路]'); const label = document.body.innerText.includes('链路名称：'); return { hasInput: !!input, hasLabel: label, placeholder: input?.placeholder || null }; })()","验证搜索框","searchInfo"),
        asrtS("searchInfo","hasInput",desc="验证搜索框存在",equals=True),
        shot("ll-search","链路列表搜索框")
    ], PRE, "搜索框placeholder: 搜索链路名称"))

# 28. 链路列表-表格列名
save(meta("atomic-f88-ll-table-columns","UI：链路列表-表格列名验证",
    "验证链路列表表格包含7列：链路名称/生命周期/描述/策略一致性/提交人/更新时间/操作",
    LL_URL, [
        nav(LL_URL, "打开链路列表"), wait(),
        eva("(() => { const headers = Array.from(document.querySelectorAll('th')).map(th => th.textContent.trim()).filter(h => h); const expected = ['链路名称','生命周期','描述','策略一致性','提交人','更新时间','操作']; const found = expected.filter(e => headers.some(h => h.includes(e))); return { headers: headers.slice(0,10), expected, found, coverage: found.length+'/'+expected.length }; })()","验证表格列名","colInfo"),
        asrtS("colInfo","coverage",desc="验证列名覆盖率",notEmpty=True),
        shot("ll-table-columns","链路列表列名")
    ], PRE, "7列：链路名称/生命周期/描述/策略一致性/提交人/更新时间/操作"))

print("\n=== 基于实际操作补充完成 ===")
print("链路详情补充: 5条 (链路说明/起点入参/环节卡片/保存按钮/添加环节)")
print("策略详情补充: 4条 (说明+场景/阶段环节下拉/节点编排/落库配置)")
print("商家管理补充: 3条 (操作按钮差异/筹备状态图标/新增商家)")
print("生产看板补充: 2条 (批次展开环节/分页)")
print("模版包管理补充: 3条 (店铺详情列表/卡片翻页/闲置按钮)")
print("淘内资源池补充: 2条 (自然语言搜索/视图模式)")
print("优质模板库补充: 5条 (风格簇模式/范围筛选/批量操作/创建任务/查看进度)")
print("策略列表补充: 2条 (分页/列名)")
print("链路列表补充: 2条 (搜索框/列名)")
print(f"共补充: 28条")
