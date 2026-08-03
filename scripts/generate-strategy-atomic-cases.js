#!/usr/bin/env node
/**
 * 生成 F88 策略相关补充原子用例（基于实际页面操作）
 * 策略列表页 + 策略详情页的细粒度功能点
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const STRATEGY_ID = 10704; // 自动化测试-生图三段式

function meta(id, name, desc) {
  return {
    id, name, description: desc,
    businessType: 'f88_material_production', scene: 'f88-test',
    priority: 'P1', category: 'regression',
    context: { urlPattern: 'pre-aifashion-xiaoer.alibaba-inc.com', auth: 'buc' },
    capture: { enabled: true, filter: 'strategy', captureBody: true },
    screenshot: { onError: true },
    contextOptimization: { screenshotExternal: true, maxResponseSizeKb: 100, outputCompact: true },
    _expected: { status: 'pass' },
  };
}

// ============ 策略列表页原子用例 ============

// SL-01: 策略列表页加载 + 表头验证
function sl01_listLoad() {
  return {
    ...meta('atom-sl-01-list-load', '原子：策略列表页加载验证', '验证策略列表页表头、筛选、按钮、表格结构完整'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle', screenshot: true },
      { type: 'wait', ms: 3000 },
      // 表头
      { type: 'assert', target: 'page', contains: '策略名称' },
      { type: 'assert', target: 'page', contains: '策略阶段' },
      { type: 'assert', target: 'page', contains: '环节' },
      { type: 'assert', target: 'page', contains: '创建时间' },
      { type: 'assert', target: 'page', contains: '更新时间' },
      { type: 'assert', target: 'page', contains: '提交人' },
      { type: 'assert', target: 'page', contains: '操作' },
      // 搜索框
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索策略名称\"]'); return { found: !!input, visible: input ? input.offsetHeight > 0 : false }; })()",
        storeAs: 'searchBox' },
      // 新建按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('新建策略')); return { found: !!btn, visible: btn ? btn.offsetHeight > 0 : false }; })()",
        storeAs: 'createBtn' },
      // 筛选
      { type: 'evaluate',
        expression: "(() => { const selects = document.querySelectorAll('.ant-select'); return { selectCount: selects.length, visible: [...selects].filter(s => s.offsetHeight > 0).length }; })()",
        storeAs: 'filters' },
      { type: 'screenshot', label: 'list-loaded' },
    ],
  };
}

// SL-02: 策略列表搜索功能
function sl02_search() {
  return {
    ...meta('atom-sl-02-search', '原子：策略列表搜索功能', '输入关键词搜索策略，验证过滤和清空'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 记录初始行数
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); return { initialCount: [...rows].filter(r => r.querySelectorAll('td').length > 0).length }; })()",
        storeAs: 'beforeSearch' },
      // 搜索
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索策略名称\"]'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '自动化测试'); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true})); input.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', keyCode:13, bubbles:true})); input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', keyCode:13, bubbles:true})); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      // 验证
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const names = dataRows.map(r => r.querySelector('td')?.textContent.trim()).filter(Boolean); const allMatch = names.every(n => n.includes('自动化测试')); return { filteredCount: dataRows.length, allMatch, names: names.slice(0,5) }; })()",
        storeAs: 'afterSearch' },
      { type: 'screenshot', label: 'search-result' },
      // 清空
      { type: 'evaluate',
        expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索策略名称\"]'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, ''); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true})); return { ok: true }; })()" },
      { type: 'wait', ms: 1500 },
    ],
  };
}

// SL-03: 策略阶段筛选
function sl03_stageFilter() {
  return {
    ...meta('atom-sl-03-stage-filter', '原子：策略列表阶段筛选', '选择策略阶段下拉，验证过滤生效'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击策略阶段下拉
      { type: 'evaluate',
        expression: "(() => { const labels = document.querySelectorAll('strong, span, div'); for (const el of labels) { if (el.textContent.trim() === '策略阶段：') { const parent = el.closest('.ant-row') || el.parentElement?.parentElement; if (parent) { const select = parent.querySelector('.ant-select'); if (select) { select.querySelector('.ant-select-selector')?.click(); return { ok: true }; } } } } return { ok: false }; })()" },
      { type: 'wait', ms: 1500 },
      // 查看选项
      { type: 'evaluate',
        expression: "(() => { const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'); const options = []; for (const dd of dropdowns) { const items = dd.querySelectorAll('.ant-select-item'); items.forEach(i => options.push(i.textContent.trim())); } return { options }; })()",
        storeAs: 'stageOptions' },
      // 选择"实验"
      { type: 'evaluate',
        expression: "(() => { const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'); for (const dd of dropdowns) { const items = dd.querySelectorAll('.ant-select-item'); for (const item of items) { if (item.textContent.trim() === '实验') { item.click(); return { ok: true }; } } } return { ok: false }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const stages = dataRows.map(r => r.querySelectorAll('td')[1]?.textContent.trim()); return { count: dataRows.length, allExperiment: stages.every(s => s === '实验'), stages }; })()",
        storeAs: 'filterResult' },
      { type: 'screenshot', label: 'stage-filtered' },
    ],
  };
}

// SL-04: 行操作按钮（打开/复制/删除）
function sl04_rowOps() {
  return {
    ...meta('atom-sl-04-row-ops', '原子：策略列表行操作按钮', '验证每行的打开、复制、删除按钮可见可点击'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const rows = document.querySelectorAll('table tbody tr'); const dataRows = [...rows].filter(r => r.querySelectorAll('td').length > 0); const results = []; for (const row of dataRows.slice(0, 3)) { const ops = row.querySelector('td:last-child'); const btns = ops ? [...ops.querySelectorAll('button')].map(b => ({ text: b.textContent.trim(), visible: b.offsetHeight > 0, disabled: b.disabled })) : []; const name = row.querySelector('td')?.textContent.trim(); results.push({ name: name?.substring(0, 30), buttons: btns }); } return results; })()",
        storeAs: 'rowOperations' },
      { type: 'screenshot', label: 'row-ops' },
    ],
  };
}

// SL-05: 打开策略详情（点击"打开"按钮）
function sl05_openDetail() {
  return {
    ...meta('atom-sl-05-open-detail', '原子：打开策略详情', '点击策略行的打开按钮，验证跳转到详情页'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 找第一行的打开按钮
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const openBtn = [...btns].find(b => b.textContent.trim() === '打开' && b.offsetHeight > 0); if (!openBtn) return { ok: false }; openBtn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 3000 },
      // 验证跳转
      { type: 'evaluate',
        expression: "(() => { const url = window.location.href; return { isDetailPage: url.includes('strategy/detail'), url }; })()",
        storeAs: 'navigation' },
      { type: 'assert', target: 'page', contains: '节点编排' },
      { type: 'screenshot', label: 'detail-opened' },
    ],
  };
}

// ============ 策略详情页补充原子用例 ============

// SD-01: 策略说明 + 适配场景编辑
function sd01_descEdit() {
  return {
    ...meta('atom-sd-01-desc-edit', '原子：策略说明和适配场景编辑', '编辑策略说明和适配场景textarea，验证保存按钮状态变化'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 记录原始值
      { type: 'evaluate',
        expression: "(() => { const ta1 = document.querySelector('textarea[placeholder=\"请输入策略说明\"]'); const ta2 = document.querySelector('textarea[placeholder=\"请输入适配场景或商家画像\"]'); return { desc: ta1?.value, scene: ta2?.value }; })()",
        storeAs: 'original' },
      // 修改策略说明
      { type: 'evaluate',
        expression: "(() => { const ta = document.querySelector('textarea[placeholder=\"请输入策略说明\"]'); if (!ta) return { ok: false }; ta.focus(); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(ta, ta.value + ' 测试验证'); ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, newValue: ta.value }; })()",
        storeAs: 'modifiedDesc' },
      { type: 'wait', ms: 1000 },
      // 验证保存按钮变为可用
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const saveBtn = [...btns].find(b => b.textContent.includes('保 存')); return { found: !!saveBtn, disabled: saveBtn?.disabled }; })()",
        storeAs: 'saveBtnState' },
      { type: 'screenshot', label: 'desc-modified' },
      // 恢复原值
      { type: 'evaluate',
        expression: `(() => { const ta = document.querySelector('textarea[placeholder="请输入策略说明"]'); if (!ta) return { ok: false }; ta.focus(); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(ta, ta.value.replace(' 测试验证', '')); ta.dispatchEvent(new Event('input', {bubbles:true})); ta.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, restored: ta.value }; })()`,
        storeAs: 'restored' },
      { type: 'wait', ms: 500 },
    ],
  };
}

// SD-02: Start节点入参编辑
function sd02_startParams() {
  return {
    ...meta('atom-sd-02-start-params', '原子：Start节点入参编辑', '点击Start节点的edit按钮，验证打开入参配置抽屉'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击Start节点的edit按钮
      { type: 'evaluate',
        expression: "(() => { const nodes = document.querySelectorAll('[class*=startEndNode], [class*=StartEndNode]'); if (nodes.length === 0) { const cards = document.querySelectorAll('.ant-card-body'); for (const card of cards) { const starts = card.querySelectorAll('div'); for (const s of starts) { if (s.textContent.includes('Start') && s.textContent.includes('策略入参')) { const editBtn = s.querySelector('button') || s.parentElement?.querySelector('button'); if (editBtn) { editBtn.click(); return { ok: true }; } } } } return { ok: false, msg: 'start node not found via fallback' }; } const startNode = nodes[0]; const editBtn = startNode.querySelector('button') || startNode.closest('div')?.querySelector('button'); if (editBtn) { editBtn.click(); return { ok: true }; } return { ok: false }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'screenshot', label: 'start-drawer' },
      // 检查抽屉
      { type: 'evaluate',
        expression: "(() => { const drawer = document.querySelector('.ant-drawer-open'); if (!drawer) return { hasDrawer: false }; return { hasDrawer: true, title: drawer.querySelector('.ant-drawer-title')?.textContent, body: drawer.querySelector('.ant-drawer-body')?.innerText.substring(0, 300) }; })()",
        storeAs: 'startDrawer' },
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 1000 },
    ],
  };
}

// SD-03: End节点出参编辑
function sd03_endParams() {
  return {
    ...meta('atom-sd-03-end-params', '原子：End节点出参编辑', '点击End节点的edit按钮，验证打开出参配置抽屉'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击End节点的edit按钮
      { type: 'evaluate',
        expression: "(() => { const nodes = document.querySelectorAll('[class*=startEndNode], [class*=StartEndNode]'); if (nodes.length >= 2) { const endNode = nodes[nodes.length - 1]; const editBtn = endNode.querySelector('button') || endNode.closest('div')?.querySelector('button'); if (editBtn) { editBtn.click(); return { ok: true }; } } const allDivs = document.querySelectorAll('div'); for (const d of allDivs) { if (d.textContent.includes('End') && d.textContent.includes('策略出参')) { const editBtn = d.querySelector('button') || d.parentElement?.querySelector('button'); if (editBtn) { editBtn.click(); return { ok: true }; } } } return { ok: false }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'evaluate',
        expression: "(() => { const drawer = document.querySelector('.ant-drawer-open'); if (!drawer) return { hasDrawer: false }; return { hasDrawer: true, title: drawer.querySelector('.ant-drawer-title')?.textContent, body: drawer.querySelector('.ant-drawer-body')?.innerText.substring(0, 300) }; })()",
        storeAs: 'endDrawer' },
      { type: 'screenshot', label: 'end-drawer' },
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 1000 },
    ],
  };
}

// SD-04: 中间节点排序按钮状态
function sd04_nodeReorder() {
  return {
    ...meta('atom-sd-04-node-reorder', '原子：中间节点排序按钮状态', '验证中间节点的arrow-up/arrow-down/delete/edit按钮状态'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const innerNodes = document.querySelectorAll('[class*=innerNode], [class*=InnerNode]'); const results = []; for (const node of innerNodes) { const name = node.querySelector('strong')?.textContent.trim() || node.textContent.substring(0, 20); const btns = node.querySelectorAll('button'); const upBtn = [...btns].find(b => b.querySelector('img[alt=\"arrow-up\"]')); const downBtn = [...btns].find(b => b.querySelector('img[alt=\"arrow-down\"]')); const delBtn = [...btns].find(b => b.querySelector('img[alt=\"delete\"]')); const editBtn = [...btns].find(b => b.querySelector('img[alt=\"edit\"]')); results.push({ name, upDisabled: upBtn?.disabled, downDisabled: downBtn?.disabled, hasDelete: !!delBtn, hasEdit: !!editBtn }); } return results; })()",
        storeAs: 'nodeReorderState' },
      { type: 'screenshot', label: 'node-buttons' },
    ],
  };
}

// SD-05: 落库配置区域验证
function sd05_storageArea() {
  return {
    ...meta('atom-sd-05-storage-area', '原子：落库配置区域验证', '验证落库配置区域的映射字段数和配置按钮'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const cards = document.querySelectorAll('.ant-card'); for (const card of cards) { const title = card.querySelector('.ant-card-head-title'); if (title && title.textContent.includes('落库配置')) { const body = card.querySelector('.ant-card-body'); const text = body?.innerText || ''; const configBtn = [...body?.querySelectorAll('button') || []].find(b => b.textContent.includes('配 置') || b.textContent.includes('配置')); const mappedMatch = text.match(/已映射\\s*(\\d+)\\s*个字段/); return { found: true, mappedFields: mappedMatch ? parseInt(mappedMatch[1]) : null, hasConfigBtn: !!configBtn, configBtnVisible: configBtn ? configBtn.offsetHeight > 0 : false, bodyText: text.substring(0, 200) }; } } return { found: false }; })()",
        storeAs: 'storageArea' },
      { type: 'screenshot', label: 'storage-area' },
    ],
  };
}

// SD-06: 试运行弹窗
function sd06_trialRun() {
  return {
    ...meta('atom-sd-06-trial-run', '原子：试运行弹窗验证', '点击试运行按钮，验证弹窗内容和表单元素'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 点击试运行
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('试运行') && b.offsetHeight > 0); if (!btn) return { ok: false }; btn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 2000 },
      { type: 'screenshot', label: 'trial-dialog' },
      // 检查弹窗
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer-open'); const target = modal || drawer; if (!target) return { type: 'none' }; const text = target.innerText; const inputs = target.querySelectorAll('input, select, textarea, input[type=file]'); const btns = target.querySelectorAll('button'); return { type: modal ? 'modal' : 'drawer', text: text.substring(0, 400), inputCount: inputs.length, buttonCount: btns.length, hasFileUpload: !!target.querySelector('input[type=file]'), hasSubmit: [...btns].some(b => b.textContent.includes('发起') || b.textContent.includes('运行') || b.textContent.includes('确定')) }; })()",
        storeAs: 'trialDialog' },
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 1000 },
    ],
  };
}

// SD-07: 查看运行结果
function sd07_runResults() {
  return {
    ...meta('atom-sd-07-run-results', '原子：策略查看运行结果', '点击查看运行结果按钮，验证跳转或弹窗展示'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const btns = document.querySelectorAll('button'); const btn = [...btns].find(b => b.textContent.includes('查看运行结果') && b.offsetHeight > 0); if (!btn) return { ok: false }; btn.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 3000 },
      { type: 'evaluate',
        expression: "(() => { const url = window.location.href; const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const text = document.body.innerText; return { url, hasModal: !!modal, hasTaskCards: text.includes('进行中') || text.includes('已完成'), pageSnippet: text.substring(0, 300) }; })()",
        storeAs: 'resultPage' },
      { type: 'screenshot', label: 'run-results' },
    ],
  };
}

// SD-08: 策略名编辑图标
function sd08_nameEdit() {
  return {
    ...meta('atom-sd-08-name-edit', '原子：策略名称编辑图标', '点击策略名旁的编辑图标，验证可修改策略名'),
    steps: [
      { type: 'navigate', url: `${BASE}/strategy/detail/${STRATEGY_ID}`, waitUntil: 'networkidle' },
      { type: 'wait', ms: 3000 },
      // 记录原始名称
      { type: 'evaluate',
        expression: "(() => { const h = document.querySelector('h4'); return { name: h?.textContent.trim() }; })()",
        storeAs: 'originalName' },
      // 点击编辑图标
      { type: 'evaluate',
        expression: "(() => { const h = document.querySelector('h4'); if (!h) return { ok: false }; const editIcon = h.parentElement?.querySelector('img[alt=\"edit\"]'); if (!editIcon) return { ok: false, msg: 'no edit icon' }; editIcon.click(); return { ok: true }; })()" },
      { type: 'wait', ms: 1500 },
      { type: 'screenshot', label: 'name-edit-mode' },
      // 检查是否进入编辑模式
      { type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const input = document.querySelector('input#name'); const inlineInput = document.querySelector('h4 input'); return { hasModal: !!modal, hasInput: !!input, hasInlineInput: !!inlineInput }; })()",
        storeAs: 'editMode' },
      { type: 'pressKey', key: 'Escape' },
      { type: 'wait', ms: 500 },
    ],
  };
}

// ============ 生成所有用例 ============
const generators = [
  sl01_listLoad, sl02_search, sl03_stageFilter, sl04_rowOps, sl05_openDetail,
  sd01_descEdit, sd02_startParams, sd03_endParams, sd04_nodeReorder,
  sd05_storageArea, sd06_trialRun, sd07_runResults, sd08_nameEdit,
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
console.log(`\n共生成 ${count} 个策略补充原子用例到 ${OUT_DIR}`);
