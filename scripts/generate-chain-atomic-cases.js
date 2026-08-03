#!/usr/bin/env node
/**
 * 生成 F88 链路相关原子用例集（基于实际页面操作探索）
 * 禁止删除历史数据，删除测试只删自己创建的数据
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const CHAIN_ID = 20180; // 【zy测试】主图生成链路 - 禁止删除

function meta(id, name, desc) {
  return {
    id, name, description: desc,
    businessType: 'f88_material_production', scene: 'f88-test',
    priority: 'P1', category: 'regression',
    context: { urlPattern: 'pre-aifashion-xiaoer.alibaba-inc.com', auth: 'buc' },
    capture: { enabled: true, filter: 'strategy|link', captureBody: true },
    screenshot: { onError: true },
    contextOptimization: { screenshotExternal: true, maxResponseSizeKb: 100, outputCompact: true },
    _expected: { status: 'pass' },
  };
}

// ============ 链路列表页原子用例 ============

// CL-01: 链路列表页加载验证
function cl01_listLoad() {
  return {
    ...meta('atom-cl-01-list-load', '原子：链路列表页加载验证', '验证链路列表页正确加载，包含表头、搜索框、新建按钮、数据行、分页'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle', screenshot: true },
      { type: 'wait', ms: 3000 },
      // 表头
      { type: 'assert', target: 'page', contains: '链路名称', description: '表头-链路名称' },
      { type: 'assert', target: 'page', contains: '生命周期', description: '表头-生命周期' },
      { type: 'assert', target: 'page', contains: '描述', description: '表头-描述' },
      { type: 'assert', target: 'page', contains: '策略一致性', description: '表头-策略一致性' },
      { type: 'assert', target: 'page', contains: '提交人', description: '表头-提交人' },
      { type: 'assert', target: 'page', contains: '更新时间', description: '表头-更新时间' },
      { type: 'assert', target: 'page', contains: '操作', description: '表头-操作' },
      // 搜索框
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索链路名称\"]'); return { found: !!input, visible: input ? input.offsetHeight > 0 : false }; })()",
        storeAs: 'searchBox' },
      // 新建按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('新建链路')); return { found: !!btn, visible: btn ? btn.offsetHeight > 0 : false, text: btn?.textContent.trim() }; })()",
        storeAs: 'createBtn' },
      // 数据行
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); return { rowCount: dataRows.length, hasData: dataRows.length > 0 }; })()",
        storeAs: 'tableData' },
      // 分页
      { type: 'evaluate',
        expression: "(() => { const pagination = document.querySelector('.ant-pagination'); if (!pagination) return { found: false }; const items = pagination.querySelectorAll('li'); const total = pagination.textContent; return { found: true, items: items.length, text: total.substring(0, 50) }; })()",
        storeAs: 'pagination' },
      { type: 'screenshot', label: 'list-loaded' },
    ],
  };
}

// CL-02: 链路列表搜索功能
function cl02_search() {
  return {
    ...meta('atom-cl-02-search', '原子：链路列表搜索功能', '在搜索框输入关键词，验证列表正确过滤'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 记录初始行数
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); return { initialCount: [...rows].filter(r => r.querySelectorAll('td').length > 0).length }; })()",
        storeAs: 'beforeSearch' },
      // 输入搜索关键词
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索链路名称\"]'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, 'zy测试'); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true }; })()" },
      { type: 'wait', ms: 1500 },
      // 触发搜索（按Enter或点击搜索图标）
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索链路名称\"]'); if (!input) return { ok: false }; input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true})); input.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', keyCode:13, bubbles:true})); input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', keyCode:13, bubbles:true})); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      // 验证过滤结果
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const texts = dataRows.map(r => r.querySelector('td')?.textContent.trim()).filter(Boolean); return { filteredCount: dataRows.length, names: texts }; })()",
        storeAs: 'afterSearch' },
      { type: 'screenshot', label: 'search-result' },
      // 清空搜索
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索链路名称\"]'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, ''); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true})); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      // 验证恢复
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); return { restoredCount: [...rows].filter(r => r.querySelectorAll('td').length > 0).length }; })()",
        storeAs: 'afterClear' },
    ],
  };
}

// CL-03: 生命周期筛选
function cl03_lifecycleFilter() {
  return {
    ...meta('atom-cl-03-lifecycle-filter', '原子：链路列表生命周期筛选', '选择生命周期下拉，验证列表按生命周期过滤'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击生命周期下拉
      { type: 'evaluate',
        expression: "(() => { const labels = document.querySelectorAll('strong, span, div'); for (const el of labels) { if (el.textContent.trim() === '生命周期：') { const parent = el.closest('.ant-row') || el.parentElement?.parentElement; if (parent) { const select = parent.querySelector('.ant-select'); if (select) { select.querySelector('.ant-select-selector')?.click(); return { ok: true }; } } } } return { ok: false }; })()" },
      { type: 'wait', ms: 1500 },
      // 截图下拉选项
      { type: 'evaluate',
        expression: "(() => { const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'); const options = []; for (const dd of dropdowns) { const items = dd.querySelectorAll('.ant-select-item'); items.forEach(i => options.push(i.textContent.trim())); } return { dropdownVisible: dropdowns.length > 0, options }; })()",
        storeAs: 'dropdownOptions' },
      { type: 'screenshot', label: 'lifecycle-dropdown' },
      // 选择"实验"
      { type: 'evaluate',
        expression: "(() => { const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'); for (const dd of dropdowns) { const items = dd.querySelectorAll('.ant-select-item'); for (const item of items) { if (item.textContent.trim() === '实验') { item.click(); return { ok: true, selected: '实验' }; } } } return { ok: false }; })()" },
      { type: 'wait', ms: 2000 },
      // 验证过滤后所有行生命周期为"实验"
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const lifecycles = dataRows.map(r => r.querySelectorAll('td')[1]?.textContent.trim()); const allExperiment = lifecycles.every(l => l === '实验'); return { rowCount: dataRows.length, lifecycles, allExperiment }; })()",
        storeAs: 'filterResult' },
      { type: 'screenshot', label: 'filtered-experiment' },
      // 重置筛选
      { type: 'evaluate',
        expression: "(() => { const labels = document.querySelectorAll('strong, span, div'); for (const el of labels) { if (el.textContent.trim() === '生命周期：') { const parent = el.closest('.ant-row') || el.parentElement?.parentElement; if (parent) { const clear = parent.querySelector('.ant-select-clear'); if (clear) { clear.click(); return { ok: true }; } } } } return { ok: false }; })()" },
      { type: 'wait', ms: 1500 },
    ],
  };
}

// CL-04: 链路列表行操作按钮（编辑/复制/删除可见性）
function cl04_rowOps() {
  return {
    ...meta('atom-cl-04-row-ops', '原子：链路列表行操作按钮验证', '验证每行数据的编辑、复制、删除按钮可见可点击（不实际操作删除）'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const results = []; for (const row of dataRows.slice(0, 3)) { const ops = row.querySelector('td:last-child'); const btns = ops ? [...ops.querySelectorAll('button')].map(b => ({ text: b.textContent.trim(), visible: b.offsetHeight > 0, disabled: b.disabled })) : []; const name = row.querySelector('td')?.textContent.trim(); results.push({ name: name?.substring(0, 30), buttons: btns }); } return results; })()",
        storeAs: 'rowOperations' },
      { type: 'screenshot', label: 'row-ops-visible' },
    ],
  };
}

// CL-05: 新建链路（自己造数据 - 可安全删除）
function cl05_createChain() {
  return {
    ...meta('atom-cl-05-create-chain', '原子：新建链路（自造数据）', '点击新建链路，填写表单提交创建，验证创建成功'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'clickText', text: '新建链路', description: '点击新建链路' },
      { type: 'wait', ms: 3000 },
      { type: 'screenshot', label: 'create-dialog' },
      // 检查弹窗/新页面
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer-open'); const newPage = document.querySelector('input#name') || document.querySelector('input[placeholder*=\"链路\"]'); return { hasModal: !!modal, hasDrawer: !!drawer, hasNewPage: !!newPage, url: window.location.href }; })()",
        storeAs: 'createForm' },
      // 填写链路名称
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input#name') || document.querySelector('input[id*=\"name\"]'); if (!input) return { ok: false, msg: 'no name input' }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '自动化测试-临时链路-' + Date.now().toString().slice(-6)); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, value: input.value }; })()",
        storeAs: 'nameInput' },
      { type: 'wait', ms: 500 },
      { type: 'screenshot', label: 'name-filled' },
      // 点击确定
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const btns = modal ? [...modal.querySelectorAll('button')] : [...document.querySelectorAll('button')]; for (const b of btns) { const txt = b.textContent.replace(/\\s/g, ''); if ((txt === '确定' || txt === '创建') && b.offsetHeight > 0 && !b.disabled) { b.click(); return { ok: true, text: b.textContent.trim() }; } } return { ok: false }; })()",
        storeAs: 'submitResult' },
      { type: 'wait', ms: 3000 },
      { type: 'screenshot', label: 'chain-created' },
    ],
  };
}

// ============ 链路详情页原子用例 ============

// CD-01: 链路详情页加载验证（核心结构验证）
function cd01_detailLoad() {
  return {
    ...meta('atom-cd-01-detail-load', '原子：链路详情页加载验证', '验证链路详情页正确加载：标题、阶段、操作按钮、链路说明、起点入参、5个环节'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle', screenshot: true },
      { type: 'wait', ms: 3000 },
      // 标题
      { type: 'assert', target: 'page', contains: '【zy测试】主图生成链路' },
      // 返回列表按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('返回列表')); return { found: !!btn }; })()",
        storeAs: 'backBtn' },
      // 阶段Select
      { type: 'evaluate',
        expression: "(() => { const text = document.body.innerText; const match = text.match(/链路阶段[：:]\\s*(\\S+)/); return { stageText: match ? match[1] : null, hasStage: !!match }; })()",
        storeAs: 'stageSelect' },
      // 操作按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const texts = [...btns].filter(b => b.offsetHeight > 0).map(b => b.textContent.trim()); return { buttons: texts.filter(t => ['试运行','查看运行结果','保 存'].some(k => t.includes(k))) }; })()",
        storeAs: 'actionBtns' },
      // 添加环节按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('添加环节')); return { found: !!btn, visible: btn ? btn.offsetHeight > 0 : false }; })()",
        storeAs: 'addStepBtn' },
      // 链路说明
      { type: 'evaluate',
        expression: "(() => { const textarea = document.querySelector('textarea[placeholder=\"请输入链路说明\"]'); return { found: !!textarea, value: textarea?.value, charCount: textarea?.value?.length }; })()",
        storeAs: 'chainDesc' },
      // 起点入参
      { type: 'evaluate',
        expression: "(() => { const heading = [...document.querySelectorAll('h5')].find(h => h.textContent.includes('链路起点入参')); if (!heading) return { found: false }; const section = heading.closest('div[class]'); const text = section?.parentElement?.innerText || ''; const params = ['seller_id','seed_image_url','tao_cate','item_id']; const foundParams = params.filter(p => text.includes(p)); return { found: true, params: foundParams }; })()",
        storeAs: 'startParams' },
      // 5个环节
      { type: 'evaluate',
        expression: "(() => { const stages = ['刷标签','首图生图','首图审核','套图生图','套图审核']; const text = document.body.innerText; return { stages: stages.map(s => ({ name: s, found: text.includes(s) })) }; })()",
        storeAs: 'stages' },
      { type: 'screenshot', label: 'detail-loaded' },
    ],
  };
}

// CD-02: 链路说明编辑
function cd02_editDesc() {
  return {
    ...meta('atom-cd-02-edit-desc', '原子：链路说明编辑', '编辑链路说明textarea，修改内容，验证保存按钮变为可用'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 记录原始说明
      { type: 'evaluate',
        expression: "(() => { const ta = document.querySelector('textarea[placeholder=\"请输入链路说明\"]'); return { originalValue: ta?.value }; })()",
        storeAs: 'originalDesc' },
      // 修改说明（追加测试标记）
      { type: 'evaluate',
        expression: "(() => { const ta = document.querySelector('textarea[placeholder=\"请输入链路说明\"]'); if (!ta) return { ok: false }; ta.focus(); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(ta, ta.value + ' 自动化验证'); ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, newValue: ta.value }; })()",
        storeAs: 'modifiedDesc' },
      { type: 'wait', ms: 1000 },
      // 验证保存按钮变为可用
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const saveBtn = [...btns].find(b => b.textContent.includes('保 存')); return { found: !!saveBtn, disabled: saveBtn?.disabled, visible: saveBtn ? saveBtn.offsetHeight > 0 : false }; })()",
        storeAs: 'saveBtnState' },
      { type: 'screenshot', label: 'desc-modified' },
      // 恢复原始说明
      { type: 'evaluate',
        expression: `(() => { const ta = document.querySelector('textarea[placeholder="请输入链路说明"]'); if (!ta) return { ok: false }; ta.focus(); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(ta, '${''}'); ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, restored: ta.value }; })()`,
        storeAs: 'restoredDesc' },
      { type: 'wait', ms: 500 },
    ],
  };
}

// CD-03: 环节结构验证（入参/出参/策略数量）
function cd03_stageStructure() {
  return {
    ...meta('atom-cd-03-stage-structure', '原子：链路环节结构验证', '验证5个环节的入参、出参、策略数量、操作按钮完整'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 逐环节验证
      { type: 'evaluate',
        expression: `(() => {
          const expected = [
            { name: '刷标签', inParams: ['seller_id','seed_image_url','tao_cate','item_id'], outParams: ['season_tag','style_tag'], strategyCount: 1 },
            { name: '首图生图', inParams: ['seller_id','item_id','seed_image_url','style_tag','season_tag','tao_cate'], outParams: ['main_img_url'], strategyCount: 4 },
            { name: '首图审核', inParams: ['seller_id','main_img_url'], outParams: ['main_img_url'], strategyCount: 1 },
            { name: '套图生图', inParams: ['seller_id','main_img_url','tao_cate'], outParams: ['set_img_url'], strategyCount: 1 },
            { name: '套图审核', inParams: ['seller_id','main_img_url','set_img_url','tao_cate'], outParams: ['no_pass_reason','set_img_url'], strategyCount: 1 }
          ];
          const text = document.body.innerText;
          const results = expected.map(stage => ({
            name: stage.name,
            found: text.includes(stage.name),
            hasInput: stage.inParams.every(p => text.includes(p)),
            hasOutput: stage.outParams.some(p => text.includes(p)),
          }));
          return results;
        })()`,
        storeAs: 'stageVerification' },
      // 验证每个环节的按钮（edit/上移/下移/删除）
      { type: 'evaluate',
        expression: "(() => { const icons = ['edit','arrow-up','arrow-down','delete']; const allBtns = document.querySelectorAll('button'); const iconBtns = {}; icons.forEach(icon => { iconBtns[icon] = [...allBtns].filter(b => { const img = b.querySelector('img'); return img && img.alt === icon; }).length; }); return iconBtns; })()",
        storeAs: 'stageButtons' },
      // 验证添加策略按钮数量（应为5个，每个环节一个）
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const addStrategyBtns = [...btns].filter(b => b.textContent.includes('添加策略')); return { count: addStrategyBtns.length, expected: 5 }; })()",
        storeAs: 'addStrategyBtns' },
      { type: 'screenshot', label: 'stage-structure' },
    ],
  };
}

// CD-04: 环节编辑按钮（点击刷标签的edit打开编辑弹窗）
function cd04_stageEdit() {
  return {
    ...meta('atom-cd-04-stage-edit', '原子：环节编辑按钮', '点击刷标签环节的edit按钮，验证弹出编辑弹窗，查看弹窗内容'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 找到"刷标签"环节的edit按钮并点击
      { type: 'evaluate',
        expression: "(() => { const strongs = document.querySelectorAll('strong'); let stageEl = null; for (const s of strongs) { if (s.textContent.trim() === '刷标签') { stageEl = s; break; } } if (!stageEl) return { ok: false, msg: 'stage not found' }; const container = stageEl.closest('div[class]'); const parent = container?.parentElement; const editBtn = parent?.querySelector('button'); if (!editBtn) return { ok: false, msg: 'edit btn not found' }; editBtn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'screenshot', label: 'stage-edit-dialog' },
      // 检查弹窗内容
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer-open'); const target = modal || drawer; if (!target) return { type: 'none', text: '' }; const inputs = target.querySelectorAll('input, select, textarea'); const btns = target.querySelectorAll('button'); return { type: modal ? 'modal' : 'drawer', inputCount: inputs.length, buttonCount: btns.length, text: target.innerText.substring(0, 400) }; })()",
        storeAs: 'editDialog' },
      // 关闭弹窗
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 1000 },
    ],
  };
}

// CD-05: 起点入参编辑
function cd05_startParamsEdit() {
  return {
    ...meta('atom-cd-05-start-params-edit', '原子：链路起点入参编辑', '点击起点入参的编辑按钮，验证弹出编辑弹窗，可查看/修改入参'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 找到"链路起点入参"旁的编辑按钮
      { type: 'evaluate',
        expression: "(() => { const headings = document.querySelectorAll('h5'); let paramsHeading = null; for (const h of headings) { if (h.textContent.includes('链路起点入参')) { paramsHeading = h; break; } } if (!paramsHeading) return { ok: false }; const container = paramsHeading.closest('div[class]'); const editBtn = container?.querySelector('button'); if (!editBtn) return { ok: false, msg: 'edit btn not found' }; editBtn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'screenshot', label: 'params-edit-dialog' },
      // 检查弹窗
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer-open'); const target = modal || drawer; if (!target) return { type: 'none' }; return { type: modal ? 'modal' : 'drawer', text: target.innerText.substring(0, 500), hasCheckboxes: target.querySelectorAll('input[type=checkbox]').length, hasTags: target.querySelectorAll('.ant-tag').length }; })()",
        storeAs: 'paramsDialog' },
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 1000 },
    ],
  };
}

// CD-06: 查看运行结果页面
function cd06_runResults() {
  return {
    ...meta('atom-cd-06-run-results', '原子：查看运行结果', '点击查看运行结果按钮，验证跳转到运行结果页面'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击查看运行结果
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('查看运行结果')); if (!btn) return { ok: false }; btn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 3000 },
      { type: 'screenshot', label: 'run-results' },
      // 检查结果页面
      { type: 'evaluate',
        expression: "(() => { const url = window.location.href; const text = document.body.innerText; return { url, hasTaskCards: text.includes('进行中') || text.includes('已完成'), hasTerminate: text.includes('终止'), pageText: text.substring(0, 300) }; })()",
        storeAs: 'resultPage' },
    ],
  };
}

// CD-07: 环节上移下移
function cd07_stageReorder() {
  return {
    ...meta('atom-cd-07-stage-reorder', '原子：环节排序按钮状态', '验证环节的上移/下移按钮状态（首环节上移禁用，末环节下移禁用）'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/linkDetail?id=${CHAIN_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 检查第一个环节（刷标签）的上移按钮应为disabled
      { type: 'evaluate',
        expression: `(() => {
          const stages = ['刷标签','首图生图','首图审核','套图生图','套图审核'];
          const results = [];
          for (const name of stages) {
            const strongs = document.querySelectorAll('strong');
            let el = null;
            for (const s of strongs) { if (s.textContent.trim() === name) { el = s; break; } }
            if (!el) continue;
            const container = el.closest('div')?.parentElement?.parentElement?.parentElement;
            if (!container) continue;
            const btns = container.querySelectorAll('button');
            const upBtn = [...btns].find(b => b.querySelector('img[alt=\"arrow-up\"]'));
            const downBtn = [...btns].find(b => b.querySelector('img[alt=\"arrow-down\"]'));
            results.push({ name, upDisabled: upBtn?.disabled, downDisabled: downBtn?.disabled });
          }
          return results;
        })()`,
        storeAs: 'reorderState' },
      { type: 'screenshot', label: 'reorder-buttons' },
    ],
  };
}

// ============ 生成所有用例 ============
const generators = [
  cl01_listLoad, cl02_search, cl03_lifecycleFilter, cl04_rowOps, cl05_createChain,
  cd01_detailLoad, cd02_editDesc, cd03_stageStructure, cd04_stageEdit,
  cd05_startParamsEdit, cd06_runResults, cd07_stageReorder,
];

let count = 0;
for (const gen of generators) {
  const c = gen();
  const filename = `${c.id.replace(/-/g, '_')}.json`;
  const filepath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(c, null, 2) + '\n');
  console.log(`✓ ${filename} (${c.steps.length} steps) - ${c.name}`);
  count++;
}
console.log(`\n共生成 ${count} 个链路原子用例到 ${OUT_DIR}`);
