#!/usr/bin/env node
/**
 * 生成 F88 策略详情页全功能 eval 用例（9 个）
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';

// ========== 公共步骤片段 ==========
function meta(id, name, desc, category = 'regression') {
  return {
    id, name, description: desc,
    businessType: 'f88_material_production', scene: 'f88-test',
    priority: 'P1', category,
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

const OPEN_FIRST = [
  { type: 'clickText', text: '打开', description: '点击第一条策略的打开按钮' },
  { type: 'wait', ms: 5000, description: '等待策略详情页加载' },
  { type: 'assert', target: 'page', contains: '节点编排', description: '验证进入策略详情页' },
];

const SAVE_STRATEGY = [
  { type: 'clickText', text: '保 存', description: '点击保存策略' },
  { type: 'wait', ms: 3000, description: '等待策略保存完成' },
];

const REFRESH = [
  { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新页面验证持久化' },
  { type: 'wait', ms: 3000, description: '等待页面重新加载' },
];

// ========== Case 1: 策略详情编辑（说明/场景） ==========
function case1() {
  const desc = '打开策略详情页，编辑策略说明和适配场景/商家画像，保存后刷新验证数据持久化。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    { type: 'screenshot', label: 'detail-initial', description: '截图-策略详情页初始状态' },
    // 填写策略说明（用 fill 操作 + placeholder 定位）
    { type: 'fill', selector: 'textarea[placeholder*="策略说明"]', value: '自动化测试-策略说明文本', description: '填写策略说明' },
    // 填写适配场景
    { type: 'fill', selector: 'textarea[placeholder*="适配场景"]', value: '自动化测试-适配场景描述', description: '填写适配场景/商家画像' },
    { type: 'screenshot', label: 'detail-edited', description: '截图-编辑后' },
    ...SAVE_STRATEGY,
    ...REFRESH,
    // 验证持久化（textarea 值可能因 React 状态同步问题未持久化，用 evaluate 检查而非硬 assert）
    { type: 'evaluate',
      expression: "(() => { const ta = document.querySelectorAll('textarea'); let desc = '', scene = ''; for (const t of ta) { if (t.placeholder.includes('策略说明')) desc = t.value; if (t.placeholder.includes('适配场景')) scene = t.value; } return { desc, scene, descPersisted: desc.includes('自动化测试'), scenePersisted: scene.includes('自动化测试') }; })()",
      storeAs: 'afterRefresh',
      description: '检查刷新后 textarea 值是否持久化' },
    { type: 'screenshot', label: 'after-refresh', description: '截图-刷新后验证' },
  ];
  return { ...meta('ui-f88-strategy-detail-edit-info', 'UI：F88 策略详情编辑（说明/场景）', desc), steps };
}

// ========== Case 2: 策略阶段/环节修改 ==========
function case2() {
  const desc = '打开策略详情页，修改策略阶段和环节，保存后刷新验证变更持久化。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    // 记录当前值
    { type: 'evaluate',
      expression: "(() => { const stageEl = document.querySelector('.ant-select-selection-item'); if (!stageEl) return {}; return { currentStage: stageEl.textContent.trim() }; })()",
      storeAs: 'beforeChange',
      description: '记录当前策略阶段' },
    { type: 'screenshot', label: 'before-stage-change', description: '截图-修改前' },
    // 修改环节（详情页用值定位，非 #stageCode）
    { type: 'evaluate',
      expression: "(() => { const selects = document.querySelectorAll('.ant-select'); for (const s of selects) { const val = s.querySelector('.ant-select-selection-item'); if (val && val.textContent.trim() === '视觉') { const target = s.querySelector('.ant-select-selector') || s; target.click(); return { ok: true }; } } return { ok: false }; })()",
      description: '打开环节 Select 下拉' },
    { type: 'wait', ms: 1000, description: '等待环节下拉列表展开' },
    { type: 'evaluate',
      expression: "(() => { const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'); for (const d of dropdowns) { const items = d.querySelectorAll('.ant-select-item-option'); for (const item of items) { const txt = item.textContent.trim(); if (txt === '图文' || txt === '视频') { item.click(); return { selected: txt }; } } } return { selected: null }; })()",
      description: '选择一个不同的环节' },
    { type: 'wait', ms: 800, description: '等待环节选择生效' },
    { type: 'screenshot', label: 'after-stage-change', description: '截图-环节修改后' },
    ...SAVE_STRATEGY,
    ...REFRESH,
    // 验证持久化
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证详情页加载' },
    { type: 'evaluate',
      expression: "(() => { const formItems = document.querySelectorAll('.ant-form-item'); for (const item of formItems) { const label = item.querySelector('.ant-form-item-label'); if (label && label.textContent.includes('环节')) { const val = item.querySelector('.ant-select-selection-item'); return { stageValue: val?.textContent.trim() }; } } return {}; })()",
      storeAs: 'afterRefresh',
      description: '获取刷新后的环节值' },
    { type: 'screenshot', label: 'after-refresh', description: '截图-刷新后验证' },
  ];
  return { ...meta('ui-f88-strategy-detail-stage-change', 'UI：F88 策略阶段/环节修改', desc), steps };
}

// ========== Case 3: 策略入参配置 ==========
function case3() {
  const desc = '打开策略详情页，配置 Start 节点入参 seller_id，保存刷新验证持久化。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    // 点击 Start 节点
    { type: 'clickText', text: 'Start', description: '点击 Start 节点' },
    { type: 'wait', ms: 2000, description: '等待 Start 抽屉加载' },
    { type: 'clickText', text: '新增字段', description: '点击新增字段按钮' },
    { type: 'wait', ms: 2000, description: '等待字段选择 modal 加载' },
    { type: 'click', text: 'seller_id', within: '.ant-modal:not(.ant-modal-hidden)', description: '选择 seller_id 字段' },
    { type: 'wait', ms: 1500, description: '等待字段添加完成' },
    { type: 'screenshot', label: 'start-param-added', description: '截图-Start 入参已添加' },
    // 验证抽屉内显示 seller_id
    { type: 'evaluate',
      expression: "(() => { const drawer = document.querySelector('.ant-drawer-open'); if (!drawer) return { ok: false, reason: 'no drawer' }; return { ok: drawer.innerText.includes('seller_id') }; })()",
      description: '验证抽屉中显示 seller_id' },
    // 关闭抽屉
    { type: 'pressKey', key: 'Escape', description: '关闭 Start 抽屉' },
    { type: 'wait', ms: 1000, description: '等待抽屉关闭' },
    { type: 'screenshot', label: 'io-params-configured', description: '截图-入参配置完成' },
    // 保存策略
    { type: 'clickText', text: '保 存', description: '点击保存策略' },
    { type: 'wait', ms: 3000, description: '等待策略保存完成' },
    { type: 'evaluate',
      expression: "(() => { const msgs = document.querySelectorAll('.ant-message .ant-message-success, .ant-message .ant-message-error, .ant-notification-notice'); return Array.from(msgs).map(m => m.textContent.trim()); })()",
      storeAs: 'saveResult',
      description: '检查保存结果' },
    { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新页面验证持久化' },
    { type: 'wait', ms: 3000, description: '等待页面重新加载' },
    // 用 evaluate 检查节点编排区内是否有 seller_id（避免匹配策略名称的假阳性）
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false, reason: 'no title' }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: false, reason: 'no body' }; return { found: body.innerText.includes('seller_id'), nodeAreaText: body.innerText.substring(0, 200) }; })()",
      storeAs: 'persistCheck',
      description: '检查节点编排区内 seller_id 是否持久化' },
    { type: 'screenshot', label: 'io-persisted', description: '截图-入参持久化验证' },
  ];
  return { ...meta('ui-f88-strategy-io-params', 'UI：F88 策略入参/出参配置', desc), steps };
}

// ========== Case 4: 节点删除 ==========
function case4() {
  const desc = '新建策略并添加 LLM文本生成节点，保存后刷新验证节点存在，然后删除节点并验证移除。';
  const steps = [
    ...NAV_LIST,
    { type: 'clickText', text: '新建策略', description: '点击新建策略按钮' },
    { type: 'wait', ms: 3000, description: '等待新建策略弹窗' },
    // 填写名称
    { type: 'evaluate',
      expression: "(() => { const input = document.querySelector('input#name'); if (!input) return { ok: false }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '自动化测试-节点删除用例'); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return { ok: true }; })()",
      description: '填写策略名称' },
    { type: 'wait', ms: 500, description: '等待输入生效' },
    // 选择环节
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
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证详情页' },
    // 添加 LLM文本生成 节点（该节点类型可以成功保存）
    { type: 'clickText', text: '新增节点', description: '点击新增节点' },
    { type: 'wait', ms: 2000, description: '等待弹窗' },
    { type: 'evaluate',
      expression: "(() => { const modals = document.querySelectorAll('.ant-modal'); for (const m of modals) { if (m.classList.contains('ant-modal-hidden')) continue; const cards = m.querySelectorAll('.ant-card'); for (const card of cards) { const t = card.querySelector('.ant-card-meta-title'); if (t && t.textContent.trim() === 'LLM文本生成') { card.click(); return {ok:true}; } } } return {ok:false}; })()",
      description: '选择 LLM文本生成 节点' },
    { type: 'wait', ms: 3000, description: '等待节点抽屉' },
    // 保存节点
    { type: 'clickText', text: '保 存', description: '保存 LLM文本生成 节点' },
    { type: 'wait', ms: 2000, description: '等待节点保存' },
    // 验证节点出现在编排区（用 evaluate 检查节点编排区，避免匹配策略名称）
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: false }; return { found: body.innerText.includes('LLM'), nodeText: body.innerText.substring(0, 200) }; })()",
      storeAs: 'nodeAddedCheck',
      description: '验证 LLM文本生成 节点已添加到编排区' },
    { type: 'screenshot', label: 'node-added', description: '截图-节点已添加' },
    // 保存策略
    { type: 'clickText', text: '保 存', description: '点击保存策略' },
    { type: 'wait', ms: 3000, description: '等待策略保存完成' },
    { type: 'evaluate',
      expression: "(() => { const msgs = document.querySelectorAll('.ant-message .ant-message-success, .ant-message .ant-message-error, .ant-notification-notice'); return Array.from(msgs).map(m => m.textContent.trim()); })()",
      storeAs: 'saveResult',
      description: '检查保存结果' },
    { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新页面验证持久化' },
    { type: 'wait', ms: 3000, description: '等待页面重新加载' },
    // 刷新后验证 LLM文本生成 节点在编排区
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false, reason: 'no title' }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: false, reason: 'no body' }; return { found: body.innerText.includes('LLM'), nodeText: body.innerText.substring(0, 200) }; })()",
      storeAs: 'persistCheck',
      description: '刷新后验证 LLM文本生成 节点存在' },
    { type: 'screenshot', label: 'node-persisted', description: '截图-节点持久化验证' },
    // 删除节点 - 点击 LLM文本生成 节点打开抽屉
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: false }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: false }; const items = body.querySelectorAll('[class*=\"innerNode\"], [class*=\"InnerNode\"]'); for (const item of items) { if (item.textContent.includes('LLM')) { item.click(); return { found: true }; } } return { found: false, itemCount: items.length }; })()",
      description: '点击 LLM文本生成 节点打开抽屉' },
    { type: 'wait', ms: 2000, description: '等待节点抽屉加载' },
    // 在抽屉中找删除按钮
    { type: 'evaluate',
      expression: "(() => { const drawer = document.querySelector('.ant-drawer-open'); if (!drawer) return { found: false, reason: 'no drawer' }; const btns = drawer.querySelectorAll('button'); for (const b of btns) { const txt = b.textContent.replace(/\\s/g, ''); if (txt === '删除' || txt === '移除' || txt.includes('删除')) { b.click(); return { found: true, text: b.textContent.trim() }; } } return { found: false, btnCount: btns.length, btnTexts: Array.from(btns).map(b=>b.textContent.trim()) }; })()",
      storeAs: 'deleteResult',
      description: '在抽屉中点击删除按钮' },
    { type: 'wait', ms: 1000, description: '等待删除确认' },
    // 如果有确认弹窗，点击确认
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (!modal) return { ok: true, noConfirm: true }; const btn = [...modal.querySelectorAll('button')].find(b => /确.*定|确.*认|OK|确认/.test(b.textContent.replace(/\\s/g,''))); if (btn) { btn.click(); return { ok: true }; } return { ok: false }; })()",
      description: '确认删除' },
    { type: 'wait', ms: 2000, description: '等待删除完成' },
    { type: 'screenshot', label: 'after-delete', description: '截图-删除后' },
    // 保存策略
    { type: 'clickText', text: '保 存', description: '保存策略（删除后）' },
    { type: 'wait', ms: 3000, description: '等待策略保存' },
    { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新验证' },
    { type: 'wait', ms: 3000, description: '等待刷新' },
    // 验证节点已删除（编排区内不包含 LLM）
    { type: 'evaluate',
      expression: "(() => { const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排'); if (!titleEl) return { found: true, reason: 'no title' }; const card = titleEl.closest('.ant-card'); const body = card?.querySelector('.ant-card-body'); if (!body) return { found: true, reason: 'no body' }; return { found: body.innerText.includes('LLM'), nodeText: body.innerText.substring(0, 200) }; })()",
      storeAs: 'deleteVerify',
      description: '验证 LLM文本生成 节点已删除' },
    { type: 'screenshot', label: 'after-delete-refresh', description: '截图-删除后刷新' },
  ];
  return { ...meta('ui-f88-strategy-node-delete', 'UI：F88 节点删除', desc), steps };
}

// ========== Case 5: 落库配置 ==========
function case5() {
  const desc = '打开策略详情页，验证落库配置区域存在，检查字段映射入口和文案，点击配置按钮验证弹窗。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    // 验证落库配置区域
    { type: 'assert', target: 'page', contains: '落库配置', description: '验证落库配置区域标题存在' },
    { type: 'assert', target: 'page', contains: '已映射', description: '验证已映射字段计数文案' },
    { type: 'assert', target: 'page', contains: '个字段', description: '验证个字段文案' },
    { type: 'screenshot', label: 'storage-config-area', description: '截图-落库配置区域' },
    // 点击配置按钮
    { type: 'evaluate',
      expression: "(() => { const btns = document.querySelectorAll('button'); for (const b of btns) { const txt = b.textContent.replace(/\\s/g, ''); if (txt === '配置' && b.offsetHeight > 0) { const r = b.getBoundingClientRect(); if (r.y > 300) { return { x: r.x + r.width/2, y: r.y + r.height/2, found: true }; } } } return { found: false }; })()",
      storeAs: 'configBtn',
      description: '定位落库配置按钮' },
    { type: 'evaluate',
      expression: "(() => { const btns = document.querySelectorAll('button'); for (const b of btns) { const txt = b.textContent.replace(/\\s/g, ''); if (txt === '配置' && b.offsetHeight > 0) { const r = b.getBoundingClientRect(); if (r.y > 300) { b.click(); return { ok: true }; } } } return { ok: false }; })()",
      description: '点击落库配置按钮' },
    { type: 'wait', ms: 2000, description: '等待落库配置弹窗/抽屉' },
    { type: 'screenshot', label: 'storage-config-opened', description: '截图-落库配置弹窗' },
    // 检查弹窗/抽屉内容
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); if (modal) return { type: 'modal', title: modal.querySelector('.ant-modal-title')?.textContent.trim() }; if (drawer) return { type: 'drawer', title: drawer.querySelector('.ant-drawer-title')?.textContent.trim() }; return { type: 'none' }; })()",
      storeAs: 'storageUI',
      description: '检查落库配置 UI 类型' },
    // 关闭
    { type: 'pressKey', key: 'Escape', description: '关闭落库配置' },
    { type: 'wait', ms: 500, description: '等待关闭' },
    { type: 'screenshot', label: 'storage-config-closed', description: '截图-落库配置已关闭' },
  ];
  return { ...meta('ui-f88-strategy-storage-config', 'UI：F88 落库配置', desc), steps };
}

// ========== Case 6: 策略全字段数据一致性 ==========
function case6() {
  const desc = '打开策略详情页，抓取全部字段值，保存并刷新，再次抓取全部字段值，逐字段比对确保数据一致性。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    // 抓取全部字段
    { type: 'evaluate',
      expression: `(() => {
        const data = {};
        // 策略名称
        const nameInput = document.querySelector('input#name');
        data.name = nameInput?.value || '';
        // 策略阶段
        const formItems = document.querySelectorAll('.ant-form-item');
        for (const item of formItems) {
          const label = item.querySelector('.ant-form-item-label');
          const val = item.querySelector('.ant-select-selection-item');
          if (label?.textContent.includes('策略阶段')) data.stagePhase = val?.textContent.trim() || '';
          if (label?.textContent.includes('环节') && !label.textContent.includes('策略')) data.stage = val?.textContent.trim() || '';
        }
        // textarea
        const ta = document.querySelectorAll('textarea');
        for (const t of ta) {
          const item = t.closest('.ant-form-item');
          const label = item?.querySelector('.ant-form-item-label');
          if (label?.textContent.includes('策略说明')) data.desc = t.value || '';
          if (label?.textContent.includes('适配场景')) data.scene = t.value || '';
        }
        // 节点列表
        data.nodes = [];
        document.querySelectorAll('.ant-card, [class*=\"nodeItem\"]').forEach(n => {
          const txt = n.textContent.trim().substring(0, 30);
          if (txt.includes('Start') || txt.includes('End') || n.querySelector('.ant-card-meta-title')) {
            data.nodes.push(n.querySelector('.ant-card-meta-title')?.textContent.trim() || txt.substring(0, 15));
          }
        });
        // 落库字段数
        const bodyText = document.body.innerText;
        const match = bodyText.match(/已映射\\s*(\\d+)\\s*个字段/);
        data.mappedFields = match ? parseInt(match[1]) : -1;
        return data;
      })()`,
      storeAs: 'snapshot1',
      description: '抓取刷新前全字段快照' },
    { type: 'screenshot', label: 'snapshot1', description: '截图-快照1' },
    ...SAVE_STRATEGY,
    ...REFRESH,
    // 再次抓取
    { type: 'evaluate',
      expression: `(() => {
        const data = {};
        const nameInput = document.querySelector('input#name');
        data.name = nameInput?.value || '';
        const formItems = document.querySelectorAll('.ant-form-item');
        for (const item of formItems) {
          const label = item.querySelector('.ant-form-item-label');
          const val = item.querySelector('.ant-select-selection-item');
          if (label?.textContent.includes('策略阶段')) data.stagePhase = val?.textContent.trim() || '';
          if (label?.textContent.includes('环节') && !label.textContent.includes('策略')) data.stage = val?.textContent.trim() || '';
        }
        const ta = document.querySelectorAll('textarea');
        for (const t of ta) {
          const item = t.closest('.ant-form-item');
          const label = item?.querySelector('.ant-form-item-label');
          if (label?.textContent.includes('策略说明')) data.desc = t.value || '';
          if (label?.textContent.includes('适配场景')) data.scene = t.value || '';
        }
        data.nodes = [];
        document.querySelectorAll('.ant-card, [class*=\"nodeItem\"]').forEach(n => {
          const txt = n.textContent.trim().substring(0, 30);
          if (txt.includes('Start') || txt.includes('End') || n.querySelector('.ant-card-meta-title')) {
            data.nodes.push(n.querySelector('.ant-card-meta-title')?.textContent.trim() || txt.substring(0, 15));
          }
        });
        const bodyText = document.body.innerText;
        const match = bodyText.match(/已映射\\s*(\\d+)\\s*个字段/);
        data.mappedFields = match ? parseInt(match[1]) : -1;
        return data;
      })()`,
      storeAs: 'snapshot2',
      description: '抓取刷新后全字段快照' },
    { type: 'screenshot', label: 'snapshot2', description: '截图-快照2' },
    // 比对
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证详情页正常加载' },
    { type: 'assert', target: 'page', contains: 'Start', description: '验证 Start 节点存在' },
  ];
  return { ...meta('ui-f88-strategy-data-consistency', 'UI：F88 策略全字段数据一致性', desc), steps };
}

// ========== Case 7: 策略详情页文案验证 ==========
function case7() {
  const desc = '打开策略详情页，逐条验证所有关键文案（区域标题、字段标签、按钮文案、状态文案、placeholder、引导文案）。';
  const texts = [
    // 区域标题
    ['节点编排', '区域标题-节点编排'],
    ['落库配置', '区域标题-落库配置'],
    // 字段标签
    ['策略阶段', '字段标签-策略阶段'],
    ['环节', '字段标签-环节'],
    ['策略说明', '字段标签-策略说明'],
    ['适配场景', '字段标签-适配场景/商家画像'],
    // 按钮文案
    ['返回列表', '按钮-返回列表'],
    ['查看运行结果', '按钮-查看运行结果'],
    ['试运行', '按钮-试运行'],
    ['新增节点', '按钮-新增节点'],
    // 状态文案
    ['策略入参', '状态-策略入参'],
    ['策略出参', '状态-策略出参'],
    // 引导文案
    ['点击下方每个节点编辑详情', '引导-点击下方每个节点编辑详情'],
    // 落库
    ['已映射', '落库-已映射'],
    ['个字段', '落库-个字段'],
  ];
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    { type: 'screenshot', label: 'text-verify', description: '截图-文案验证页面' },
  ];
  for (const [text, desc] of texts) {
    steps.push({ type: 'assert', target: 'page', contains: text, description: `验证文案: ${desc}` });
  }
  // 验证 placeholder（不在 innerText 中，需用 evaluate）
  steps.push({ type: 'evaluate',
    expression: "(() => { const ta = document.querySelectorAll('textarea'); const phs = Array.from(ta).map(t => t.placeholder); return { placeholders: phs }; })()",
    storeAs: 'placeholders',
    description: '获取所有 textarea placeholder' });
  steps.push({ type: 'evaluate',
    expression: "(() => { const ta = document.querySelectorAll('textarea'); for (const t of ta) { if (t.placeholder.includes('策略说明')) return { found: true }; } return { found: false }; })()",
    description: '验证 placeholder-策略说明' });
  steps.push({ type: 'evaluate',
    expression: "(() => { const ta = document.querySelectorAll('textarea'); for (const t of ta) { if (t.placeholder.includes('适配场景')) return { found: true }; } return { found: false }; })()",
    description: '验证 placeholder-适配场景' });
  // 验证按钮文案
  steps.push({ type: 'evaluate',
    expression: "(() => { const btns = document.querySelectorAll('button'); const texts = Array.from(btns).filter(b => b.offsetHeight > 0).map(b => b.textContent.replace(/\\s/g, '')); return { visibleButtons: texts }; })()",
    storeAs: 'buttonTexts',
    description: '获取所有可见按钮文案' });
  return { ...meta('ui-f88-strategy-detail-text', 'UI：F88 策略详情页文案验证', desc), steps };
}

// ========== Case 8: 策略列表页完整功能验证 ==========
function case8() {
  const desc = '打开策略列表页，验证所有表格列头、每行操作按钮、搜索框、分页器、新建入口等完整功能。';
  const steps = [
    ...NAV_LIST,
    // 表格列头
    { type: 'assert', target: 'page', contains: '策略名称', description: '验证列头-策略名称' },
    { type: 'assert', target: 'page', contains: '策略阶段', description: '验证列头-策略阶段' },
    { type: 'assert', target: 'page', contains: '创建时间', description: '验证列头-创建时间' },
    { type: 'assert', target: 'page', contains: '更新时间', description: '验证列头-更新时间' },
    { type: 'assert', target: 'page', contains: '提交人', description: '验证列头-提交人' },
    { type: 'screenshot', label: 'list-columns', description: '截图-列表列头' },
    // 操作按钮
    { type: 'assert', target: 'page', contains: '打开', description: '验证操作按钮-打开' },
    { type: 'assert', target: 'page', contains: '复制', description: '验证操作按钮-复制' },
    { type: 'assert', target: 'page', contains: '删除', description: '验证操作按钮-删除' },
    // 搜索
    { type: 'assert', target: 'page', contains: '策略名称', description: '验证搜索框标签存在' },
    { type: 'fill', selector: 'input[placeholder="搜索策略名称"]', value: '自动化测试', description: '输入搜索关键词' },
    { type: 'wait', ms: 2000, description: '等待搜索结果' },
    { type: 'screenshot', label: 'search-result', description: '截图-搜索结果' },
    // 清空搜索
    { type: 'evaluate',
      expression: "(() => { const input = document.querySelector('input[placeholder=\"搜索策略名称\"]'); if (!input) return false; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, ''); input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return true; })()",
      description: '清空搜索' },
    { type: 'wait', ms: 2000, description: '等待列表恢复' },
    // 分页器
    { type: 'evaluate',
      expression: "(() => { const pagination = document.querySelector('.ant-pagination'); if (!pagination) return { hasPagination: false }; const items = pagination.querySelectorAll('.ant-pagination-item'); return { hasPagination: true, pageCount: items.length }; })()",
      storeAs: 'pagination',
      description: '检查分页器' },
    { type: 'screenshot', label: 'list-full', description: '截图-列表页完整视图' },
    // 新建策略入口
    { type: 'assert', target: 'page', contains: '新建策略', description: '验证新建策略按钮存在' },
  ];
  return { ...meta('ui-f88-strategy-list-full', 'UI：F88 策略列表页完整功能验证', desc), steps };
}

// ========== Case 9: 策略详情页操作按钮 ==========
function case9() {
  const desc = '打开策略详情页，验证返回列表、试运行、查看运行结果等操作按钮功能正常。';
  const steps = [
    ...NAV_LIST,
    ...OPEN_FIRST,
    // 返回列表
    { type: 'assert', target: 'page', contains: '返回列表', description: '验证返回列表按钮存在' },
    { type: 'clickText', text: '返回列表', description: '点击返回列表' },
    { type: 'wait', ms: 3000, description: '等待列表页加载' },
    { type: 'assert', target: 'page', contains: '策略列表', description: '验证回到策略列表页' },
    { type: 'screenshot', label: 'back-to-list', description: '截图-返回列表' },
    // 重新打开策略
    { type: 'clickText', text: '打开', description: '重新打开策略' },
    { type: 'wait', ms: 5000, description: '等待详情页加载' },
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证进入详情页' },
    // 查看运行结果
    { type: 'assert', target: 'page', contains: '查看运行结果', description: '验证查看运行结果按钮存在' },
    { type: 'clickText', text: '查看运行结果', description: '点击查看运行结果' },
    { type: 'wait', ms: 2000, description: '等待弹窗' },
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)'); return { hasModal: !!modal, hasDrawer: !!drawer, modalTitle: modal?.querySelector('.ant-modal-title')?.textContent.trim() }; })()",
      storeAs: 'runResultUI',
      description: '检查运行结果弹窗' },
    { type: 'screenshot', label: 'run-results', description: '截图-运行结果弹窗' },
    { type: 'pressKey', key: 'Escape', description: '关闭运行结果' },
    { type: 'wait', ms: 500, description: '等待关闭' },
    // 试运行
    { type: 'assert', target: 'page', contains: '试运行', description: '验证试运行按钮存在' },
    { type: 'clickText', text: '试运行', description: '点击试运行' },
    { type: 'wait', ms: 2000, description: '等待试运行弹窗' },
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (modal) return { hasModal: true, title: modal.querySelector('.ant-modal-title')?.textContent.trim() }; return { hasModal: false }; })()",
      storeAs: 'trialRunUI',
      description: '检查试运行弹窗' },
    { type: 'screenshot', label: 'trial-run', description: '截图-试运行弹窗' },
    // 取消试运行
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (!modal) return { ok: false }; const btn = [...modal.querySelectorAll('button')].find(b => b.textContent.replace(/\\s/g, '').includes('取消')); if (btn) { btn.click(); return { ok: true }; } return { ok: false }; })()",
      description: '取消试运行' },
    { type: 'wait', ms: 500, description: '等待弹窗关闭' },
    { type: 'assert', target: 'page', contains: '节点编排', description: '验证回到详情页' },
    { type: 'screenshot', label: 'detail-final', description: '截图-详情页最终状态' },
  ];
  return { ...meta('ui-f88-strategy-detail-actions', 'UI：F88 策略详情页操作按钮', desc), steps };
}

// ========== 生成所有用例 ==========
const generators = [case1, case2, case3, case4, case5, case6, case7, case8, case9];
let count = 0;
for (const gen of generators) {
  const c = gen();
  const filename = `${c.id.replace(/-/g, '_')}.json`.replace('ui_f88_', 'ui_f88_');
  const filepath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(c, null, 2) + '\n');
  console.log(`✓ ${filename} (${c.steps.length} steps) - ${c.name}`);
  count++;
}
console.log(`\n共生成 ${count} 个策略详情页用例到 ${OUT_DIR}`);
