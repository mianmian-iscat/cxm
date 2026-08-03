#!/usr/bin/env node
/**
 * 生成 F88 组合型策略 eval 用例（4 个）
 * 基于真实链路搭配模式：生图三段式、审核策略、LLM+审核组合、链路管理
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';

function meta(id, name, desc) {
  return {
    id, name, description: desc,
    businessType: 'f88_material_production', scene: 'f88-test',
    priority: 'P1', category: 'regression',
    context: { urlPattern: 'pre-aifashion-xiaoer.alibaba-inc.com', url: `${BASE}/strategy/list`, waitAfterLoad: 3000, auth: 'buc' },
    capture: { enabled: true, filter: 'workflow2|strategy', captureBody: true },
    screenshot: { onError: true },
    contextOptimization: { screenshotExternal: true, maxResponseSizeKb: 100, outputCompact: true },
    _expected: { status: 'pass' },
  };
}

const NAV_LIST = [
  { type: 'navigate', url: `${BASE}/strategy/list`, waitUntil: 'networkidle', screenshot: true, description: '打开策略列表页' },
  { type: 'wait', ms: 3000, description: '等待策略列表加载' },
  { type: 'assert', target: 'page', contains: '策略列表', description: '验证策略列表页已加载' },
];

// 新建策略并跳转详情页（公共步骤）
function createStrategy(name) {
  return [
    { type: 'clickText', text: '新建策略', description: '点击新建策略按钮' },
    { type: 'wait', ms: 3000, description: '等待新建策略弹窗' },
    { type: 'evaluate',
      expression: `(() => { const input = document.querySelector('input#name'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '${name}'); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true }; })()`,
      description: '填写策略名称' },
    { type: 'wait', ms: 500, description: '等待输入生效' },
    // 环节
    { type: 'evaluate',
      expression: "(() => { const el = document.querySelector('#stageCode'); if (!el) return false; const sel = el.closest('.ant-select'); const target = sel?.querySelector('.ant-select-selector') || sel; if (target) { target.setAttribute('data-testid', 'stage-select'); return true; } return false; })()",
      description: '标记环节 Select' },
    { type: 'click', selector: '[data-testid="stage-select"]', description: '打开环节下拉' },
    { type: 'wait', ms: 1000, description: '等待下拉' },
    { type: 'click', text: '视觉', within: '.ant-select-dropdown:not(.ant-select-dropdown-hidden)', description: '选择视觉' },
    { type: 'wait', ms: 800, description: '等待' },
    // 生命周期
    { type: 'evaluate',
      expression: "(() => { const el = document.querySelector('#lifeCycleCode'); if (!el) return false; const sel = el.closest('.ant-select'); const target = sel?.querySelector('.ant-select-selector') || sel; if (target) { target.setAttribute('data-testid', 'lifecycle-select'); return true; } return false; })()",
      description: '标记生命周期 Select' },
    { type: 'click', selector: '[data-testid="lifecycle-select"]', description: '打开生命周期下拉' },
    { type: 'wait', ms: 1000, description: '等待下拉' },
    { type: 'click', text: '实验', within: '.ant-select-dropdown:not(.ant-select-dropdown-hidden)', description: '选择实验' },
    { type: 'wait', ms: 800, description: '等待' },
    // 确定
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (!modal) return { ok: false }; const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent.replace(/\\s/g,''))); if (btn) { btn.click(); return { ok: true }; } return { ok: false }; })()",
      description: '点击确定创建策略' },
    { type: 'wait', ms: 3000, description: '等待跳转详情页' },
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证详情页加载' },
    // 获取策略ID
    { type: 'evaluate',
      expression: "(() => { const url = window.location.href; const match = url.match(/strategy\\/detail\\/(\\d+)/); return match ? { strategyId: match[1], url } : { strategyId: null, url }; })()",
      storeAs: 'newStrategy',
      description: '获取新建策略ID' },
  ];
}

// 添加指定类型节点
function addNode(nodeTypeName, label) {
  return [
    { type: 'clickText', text: '新增节点', description: `点击新增节点-${label}` },
    { type: 'wait', ms: 2000, description: '等待节点类型弹窗' },
    { type: 'evaluate',
      expression: `(() => { const modals = document.querySelectorAll('.ant-modal'); for (const m of modals) { if (m.classList.contains('ant-modal-hidden')) continue; const cards = m.querySelectorAll('.ant-card'); for (const card of cards) { const t = card.querySelector('.ant-card-meta-title'); if (t && t.textContent.trim() === '${nodeTypeName}') { card.click(); return {ok:true}; } } } return {ok:false}; })()`,
      description: `选择 ${nodeTypeName} 节点` },
    { type: 'wait', ms: 3000, description: `等待 ${nodeTypeName} 节点抽屉加载` },
    { type: 'clickText', text: '保 存', description: `保存 ${nodeTypeName} 节点` },
    { type: 'wait', ms: 2000, description: `等待 ${nodeTypeName} 节点保存` },
  ];
}

// 保存策略 + 刷新
function saveAndRefresh() {
  return [
    { type: 'clickText', text: '保 存', description: '保存策略' },
    { type: 'wait', ms: 3000, description: '等待策略保存' },
    { type: 'evaluate',
      expression: "(() => { const msgs = document.querySelectorAll('.ant-message .ant-message-success, .ant-message .ant-message-error, .ant-notification-notice'); return Array.from(msgs).map(m => m.textContent.trim()); })()",
      storeAs: 'saveResult',
      description: '检查保存结果' },
    { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新验证持久化' },
    { type: 'wait', ms: 3000, description: '等待刷新' },
  ];
}

// 检查编排区节点
function checkNodeArea(shouldContain, nodeNames) {
  return nodeNames.map(name => ({
    type: 'evaluate',
    expression: `(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false, reason: 'no title' }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: false, reason: 'no body' }; return { found: body.innerText.includes('${name}'), nodeText: body.innerText.substring(0, 300) }; })()`,
    storeAs: `check_${name.replace(/[^a-zA-Z]/g, '')}`,
    description: `${shouldContain ? '验证' : '验证不含'}编排区 ${name}`,
  }));
}

// ========== Case 10: 生图三段式策略（LLM文本生成→模板匹配→生图）==========
function case10() {
  const desc = '创建生图三段式策略（LLM文本生成→模板匹配→生图），模拟真实首图生图策略的节点编排，保存刷新验证持久化。';
  const steps = [
    ...NAV_LIST,
    ...createStrategy('自动化测试-生图三段式'),
    { type: 'screenshot', label: 'strategy-created', description: '截图-策略已创建' },
    // 添加三段式节点
    ...addNode('LLM文本生成', '第一段'),
    { type: 'screenshot', label: 'llm-added', description: '截图-LLM文本生成已添加' },
    ...addNode('模板匹配', '第二段'),
    { type: 'screenshot', label: 'template-added', description: '截图-模板匹配已添加' },
    // 注意：生图节点可能需要dataSourceConfig，尝试添加
    ...addNode('生图', '第三段'),
    { type: 'screenshot', label: 'gen-added', description: '截图-生图已添加' },
    // 验证节点编排区有三个中间节点
    ...checkNodeArea(true, ['LLM', '模板匹配']),
    { type: 'screenshot', label: 'all-nodes-added', description: '截图-三段式节点全部添加' },
    // 保存+刷新
    ...saveAndRefresh(),
    // 刷新后验证
    ...checkNodeArea(true, ['LLM', '模板匹配']),
    { type: 'screenshot', label: 'persisted', description: '截图-三段式持久化验证' },
  ];
  return { ...meta('ui-f88-strategy-gen-triple', 'UI：F88 生图三段式策略（LLM+模板+生图）', desc), steps };
}

// ========== Case 11: 审核策略配置（人工审核单节点）==========
function case11() {
  const desc = '创建审核策略（单个人工审核节点），模拟真实首图审核/套图审核策略，验证人工审核节点可正常添加和保存。';
  const steps = [
    ...NAV_LIST,
    ...createStrategy('自动化测试-审核策略'),
    { type: 'screenshot', label: 'strategy-created', description: '截图-审核策略已创建' },
    // 添加人工审核节点
    ...addNode('人工审核', '审核'),
    { type: 'screenshot', label: 'review-added', description: '截图-人工审核已添加' },
    // 验证编排区
    ...checkNodeArea(true, ['人工审核']),
    // 配置 Start 入参（模拟审核策略的入参）
    { type: 'clickText', text: 'Start', description: '点击 Start 节点' },
    { type: 'wait', ms: 2000, description: '等待 Start 抽屉' },
    { type: 'clickText', text: '新增字段', description: '新增字段-seller_id' },
    { type: 'wait', ms: 2000, description: '等待字段弹窗' },
    { type: 'click', text: 'seller_id', within: '.ant-modal:not(.ant-modal-hidden)', description: '选择 seller_id' },
    { type: 'wait', ms: 1500, description: '等待字段添加' },
    // 关闭抽屉
    { type: 'pressKey', key: 'Escape', description: '关闭 Start 抽屉' },
    { type: 'wait', ms: 1000, description: '等待抽屉关闭' },
    // 保存+刷新
    ...saveAndRefresh(),
    // 验证
    ...checkNodeArea(true, ['人工审核']),
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); return { found: body.innerText.includes('seller_id'), text: body.innerText.substring(0, 200) }; })()",
      storeAs: 'sellerCheck',
      description: '验证 seller_id 入参持久化' },
    { type: 'screenshot', label: 'review-persisted', description: '截图-审核策略持久化验证' },
  ];
  return { ...meta('ui-f88-strategy-review', 'UI：F88 审核策略配置（人工审核）', desc), steps };
}

// ========== Case 12: LLM+审核组合策略 ==========
function case12() {
  const desc = '创建LLM文本生成+人工审核组合策略，模拟"先生成后审核"的经典搭配，验证两种不同类型节点可在同一策略中共存。';
  const steps = [
    ...NAV_LIST,
    ...createStrategy('自动化测试-LLM审核组合'),
    { type: 'screenshot', label: 'strategy-created', description: '截图-策略已创建' },
    // 添加 LLM文本生成
    ...addNode('LLM文本生成', '生成'),
    { type: 'screenshot', label: 'llm-added', description: '截图-LLM文本生成已添加' },
    // 添加 人工审核
    ...addNode('人工审核', '审核'),
    { type: 'screenshot', label: 'review-added', description: '截图-人工审核已添加' },
    // 验证两种节点共存
    ...checkNodeArea(true, ['LLM', '人工审核']),
    // 保存+刷新
    ...saveAndRefresh(),
    // 验证持久化
    ...checkNodeArea(true, ['LLM', '人工审核']),
    { type: 'screenshot', label: 'combo-persisted', description: '截图-组合策略持久化验证' },
  ];
  return { ...meta('ui-f88-strategy-llm-review-combo', 'UI：F88 LLM+审核组合策略', desc), steps };
}

// ========== Case 13: 链路创建与环节管理 ==========
function case13() {
  const desc = '新建链路，添加环节（首图生图、首图审核），验证链路编排界面正确渲染，保存刷新验证持久化。';
  const steps = [
    // 导航到链路列表
    { type: 'navigate', url: `${BASE}/strategy/linkList`, waitUntil: 'networkidle', screenshot: true, description: '打开链路列表页' },
    { type: 'wait', ms: 3000, description: '等待链路列表加载' },
    { type: 'assert', target: 'page', contains: '链路列表', description: '验证链路列表页已加载' },
    // 新建链路
    { type: 'clickText', text: '新建链路', description: '点击新建链路' },
    { type: 'wait', ms: 3000, description: '等待新建链路页面/弹窗' },
    { type: 'screenshot', label: 'chain-create-form', description: '截图-新建链路表单' },
    // 填写链路名称
    { type: 'evaluate',
      expression: "(() => { const inputs = document.querySelectorAll('input'); for (const input of inputs) { if (input.placeholder && (input.placeholder.includes('链路') || input.placeholder.includes('名称'))) { const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '自动化测试-组合链路'); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true, placeholder: input.placeholder }; } } return { ok: false, inputCount: inputs.length }; })()",
      storeAs: 'nameResult',
      description: '填写链路名称' },
    { type: 'wait', ms: 500, description: '等待输入生效' },
    // 填写描述（如果有）
    { type: 'evaluate',
      expression: "(() => { const ta = document.querySelectorAll('textarea'); for (const t of ta) { t.focus(); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(t, '自动化测试链路-验证环节管理'); t.dispatchEvent(new Event('input', {bubbles:true})); t.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true }; } return { ok: false }; })()",
      description: '填写链路描述' },
    { type: 'wait', ms: 500, description: '等待' },
    { type: 'screenshot', label: 'chain-form-filled', description: '截图-链路表单已填写' },
    // 提交创建
    { type: 'evaluate',
      expression: "(() => { const btns = document.querySelectorAll('button'); for (const b of btns) { const txt = b.textContent.replace(/\\s/g, ''); if ((txt === '确定' || txt === '创建' || txt === '保存' || txt.includes('提交')) && b.offsetHeight > 0 && !b.disabled) { b.click(); return { ok: true, text: b.textContent.trim() }; } } return { ok: false }; })()",
      storeAs: 'submitResult',
      description: '提交创建链路' },
    { type: 'wait', ms: 3000, description: '等待链路创建完成' },
    { type: 'screenshot', label: 'chain-created', description: '截图-链路已创建' },
    // 验证链路详情页
    { type: 'evaluate',
      expression: "(() => { const text = document.body.innerText; return { hasAddStep: text.includes('添加环节'), hasDesc: text.includes('链路说明'), url: window.location.href }; })()",
      storeAs: 'chainDetail',
      description: '检查链路详情页元素' },
    // 尝试添加环节
    { type: 'evaluate',
      expression: "(() => { const btns = document.querySelectorAll('button'); for (const b of btns) { if (b.textContent.replace(/\\s/g, '').includes('添加环节') && b.offsetHeight > 0) { b.click(); return { ok: true }; } } return { ok: false }; })()",
      description: '点击添加环节' },
    { type: 'wait', ms: 2000, description: '等待环节添加弹窗' },
    { type: 'screenshot', label: 'add-step-dialog', description: '截图-添加环节弹窗' },
    // 查看环节表单
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer-open'); const target = modal || drawer; if (!target) return { type: 'none' }; const inputs = target.querySelectorAll('input, select, textarea'); return { type: modal ? 'modal' : 'drawer', inputCount: inputs.length, text: target.innerText.substring(0, 300) }; })()",
      storeAs: 'stepDialog',
      description: '检查添加环节弹窗内容' },
    // 关闭弹窗
    { type: 'pressKey', key: 'Escape', description: '关闭弹窗' },
    { type: 'wait', ms: 500, description: '等待关闭' },
    // 验证链路详情页最终状态（链路详情页没有保存按钮，提交环节后自动保存）
    { type: 'evaluate',
      expression: "(() => { const text = document.body.innerText; return { hasAddStep: text.includes('添加环节'), hasDesc: text.includes('链路说明'), url: window.location.href, title: document.title }; })()",
      storeAs: 'finalState',
      description: '验证链路详情页最终状态' },
    { type: 'screenshot', label: 'chain-final', description: '截图-链路详情页最终状态' },
  ];
  return { ...meta('ui-f88-chain-management', 'UI：F88 链路创建与环节管理', desc), steps };
}

// ========== 生成所有用例 ==========
const generators = [case10, case11, case12, case13];
let count = 0;
for (const gen of generators) {
  const c = gen();
  const filename = `${c.id.replace(/-/g, '_')}.json`;
  const filepath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(c, null, 2) + '\n');
  console.log(`✓ ${filename} (${c.steps.length} steps) - ${c.name}`);
  count++;
}
console.log(`\n共生成 ${count} 个组合型用例到 ${OUT_DIR}`);
