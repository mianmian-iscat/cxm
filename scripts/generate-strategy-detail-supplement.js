#!/usr/bin/env node
/**
 * 生成 F88 策略详情页补充原子用例（基于浏览器实际操作发现）
 * 9 个补充用例，覆盖已有 9 个用例未涉及的交互点
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

const OPEN_FIRST = [
  { type: 'clickText', text: '打开', description: '点击第一条策略的打开按钮' },
  { type: 'wait', ms: 5000, description: '等待策略详情页加载' },
  { type: 'assert', target: 'page', contains: '节点编排', description: '验证进入策略详情页' },
];

// ========== SD-10: 节点类型弹窗完整验证 ==========
function sd10() {
  const desc = '打开策略详情页，点击新增节点，验证弹窗中显示全部20种节点类型及其描述文案。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    { type: 'clickText', text: '新增节点', description: '点击新增节点按钮' },
    { type: 'wait', ms: 2000, description: '等待节点类型弹窗' },
    // 验证弹窗标题
    { type: 'evaluate',
      expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (!modal) return { hasModal: false }; const title = modal.querySelector('.ant-modal-title'); return { hasModal: true, title: title?.textContent.trim() }; })()",
      storeAs: 'modalInfo',
      description: '验证节点类型弹窗标题' },
    // 验证所有20种节点类型
    { type: 'evaluate',
      expression: `(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { count: 0 };
        const cards = modal.querySelectorAll('.ant-card');
        const types = [];
        for (const card of cards) {
          const title = card.querySelector('.ant-card-meta-title');
          const desc = card.querySelector('.ant-card-meta-description');
          if (title) types.push({ name: title.textContent.trim(), desc: desc?.textContent.trim() || '' });
        }
        return { count: types.length, types: types.map(t => t.name) };
      })()`,
      storeAs: 'nodeTypes',
      description: '获取所有节点类型' },
    { type: 'screenshot', label: 'node-types-modal', description: '截图-节点类型弹窗' },
    // 逐个验证关键节点类型存在
    { type: 'evaluate',
      expression: `(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { ok: false };
        const text = modal.innerText;
        const required = ['LLM文本生成', '生图', 'Map生图', '季节标签', '产业标签', '模板匹配', '人工审核', 'Caption', '机审', '高清化处理'];
        const found = required.filter(r => text.includes(r));
        const missing = required.filter(r => !text.includes(r));
        return { found: found.length, total: required.length, missing };
      })()`,
      description: '验证关键节点类型存在' },
    // 关闭弹窗
    { type: 'pressKey', key: 'Escape', description: '关闭节点类型弹窗' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-node-types-modal', 'UI：策略详情-节点类型弹窗完整验证', desc), steps };
}

// ========== SD-11: 节点编辑器抽屉全字段验证 ==========
function sd11() {
  const desc = '打开含LLM文本生成节点的策略，点击节点edit按钮，验证编辑器抽屉包含模型类型、User Prompt、输出格式、字符数限制等全字段。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击 LLM文本生成 节点的 edit 按钮
    { type: 'evaluate',
      expression: `(() => {
        const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排');
        if (!titleEl) return { ok: false, reason: 'no title' };
        const card = titleEl.closest('.ant-card');
        const body = card?.querySelector('.ant-card-body');
        if (!body) return { ok: false, reason: 'no body' };
        const items = body.querySelectorAll('[class*="innerNode"], [class*="InnerNode"]');
        for (const item of items) {
          if (item.textContent.includes('LLM')) {
            const editBtn = item.querySelector('button');
            if (editBtn) { editBtn.click(); return { ok: true }; }
          }
        }
        return { ok: false, itemCount: items.length };
      })()`,
      description: '点击LLM文本生成节点打开编辑抽屉' },
    { type: 'wait', ms: 2000, description: '等待节点编辑抽屉加载' },
    // 验证抽屉内容
    { type: 'evaluate',
      expression: `(() => {
        const drawer = document.querySelector('.ant-drawer-open');
        if (!drawer) return { hasDrawer: false };
        const text = drawer.innerText;
        const checks = {
          hasTitle: text.includes('节点编辑'),
          hasNodeType: text.includes('LLM文本生成'),
          hasModelType: text.includes('模型类型'),
          hasUserPrompt: text.includes('User Prompt'),
          hasImageInput: text.includes('输入图片/视频') || text.includes('添加图片'),
          hasOutputFormat: text.includes('输出格式'),
          hasPlainText: text.includes('纯文本'),
          hasJSON: text.includes('JSON'),
          hasMinChars: text.includes('最小字符数'),
          hasMaxChars: text.includes('最大字符数'),
          hasRunTest: text.includes('运行测试'),
          hasSaveBtn: text.includes('保') && text.includes('存'),
          hasCancelBtn: text.includes('取') && text.includes('消'),
        };
        return { hasDrawer: true, checks, passCount: Object.values(checks).filter(Boolean).length };
      })()`,
      storeAs: 'drawerChecks',
      description: '验证LLM节点编辑抽屉全字段' },
    { type: 'screenshot', label: 'llm-node-drawer', description: '截图-LLM节点编辑抽屉' },
    // 关闭抽屉
    { type: 'pressKey', key: 'Escape', description: '关闭抽屉' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-node-editor-drawer', 'UI：策略详情-节点编辑器抽屉全字段', desc), steps };
}

// ========== SD-12: Start 入参抽屉完整验证 ==========
function sd12() {
  const desc = '打开策略详情页，点击Start节点edit按钮，验证入参抽屉包含新增字段按钮、字段列表、必填/选填radio。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击 Start 节点 edit 按钮
    { type: 'evaluate',
      expression: `(() => {
        const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排');
        if (!titleEl) return { ok: false };
        const card = titleEl.closest('.ant-card');
        const body = card?.querySelector('.ant-card-body');
        if (!body) return { ok: false };
        const startNodes = body.querySelectorAll('[class*="startEndNode"]');
        for (const n of startNodes) {
          if (n.textContent.includes('Start')) {
            const btn = n.querySelector('button');
            if (btn) { btn.click(); return { ok: true }; }
          }
        }
        return { ok: false };
      })()`,
      description: '点击Start节点edit按钮' },
    { type: 'wait', ms: 2000, description: '等待Start抽屉加载' },
    // 验证抽屉内容
    { type: 'evaluate',
      expression: `(() => {
        const drawer = document.querySelector('.ant-drawer-open');
        if (!drawer) return { hasDrawer: false };
        const text = drawer.innerText;
        const hasNewField = text.includes('新增字段');
        const hasInputField = text.includes('输入字段');
        const hasRequired = text.includes('必填');
        const hasOptional = text.includes('选填');
        return { hasDrawer: true, hasNewField, hasInputField, hasRequired, hasOptional };
      })()`,
      storeAs: 'startDrawer',
      description: '验证Start入参抽屉内容' },
    { type: 'screenshot', label: 'start-drawer', description: '截图-Start入参抽屉' },
    // 关闭
    { type: 'pressKey', key: 'Escape', description: '关闭抽屉' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-start-drawer', 'UI：策略详情-Start入参抽屉完整验证', desc), steps };
}

// ========== SD-13: End 出参抽屉验证 ==========
function sd13() {
  const desc = '打开策略详情页，点击End节点edit按钮，验证出参抽屉包含新增字段按钮和空状态提示。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击 End 节点 edit 按钮
    { type: 'evaluate',
      expression: `(() => {
        const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排');
        if (!titleEl) return { ok: false };
        const card = titleEl.closest('.ant-card');
        const body = card?.querySelector('.ant-card-body');
        if (!body) return { ok: false };
        const startNodes = body.querySelectorAll('[class*="startEndNode"]');
        for (const n of startNodes) {
          if (n.textContent.includes('End')) {
            const btn = n.querySelector('button');
            if (btn) { btn.click(); return { ok: true }; }
          }
        }
        return { ok: false };
      })()`,
      description: '点击End节点edit按钮' },
    { type: 'wait', ms: 2000, description: '等待End抽屉加载' },
    { type: 'evaluate',
      expression: `(() => {
        const drawer = document.querySelector('.ant-drawer-open');
        if (!drawer) return { hasDrawer: false };
        const text = drawer.innerText;
        return {
          hasDrawer: true,
          hasNewField: text.includes('新增字段'),
          hasOutputField: text.includes('输出字段'),
          hasEmptyHint: text.includes('暂无') || text.includes('暂无字段'),
        };
      })()`,
      storeAs: 'endDrawer',
      description: '验证End出参抽屉内容' },
    { type: 'screenshot', label: 'end-drawer', description: '截图-End出参抽屉' },
    { type: 'pressKey', key: 'Escape', description: '关闭抽屉' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-end-drawer', 'UI：策略详情-End出参抽屉验证', desc), steps };
}

// ========== SD-14: 落库配置弹窗树结构验证 ==========
function sd14() {
  const desc = '打开策略详情页，点击落库配置按钮，验证弹窗包含目标变量树结构（设计/视觉/套图分类）和建立映射按钮。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击落库配置按钮
    { type: 'evaluate',
      expression: `(() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
          const txt = b.textContent.replace(/\\s/g, '');
          if (txt === '配置' && b.offsetHeight > 0) {
            const r = b.getBoundingClientRect();
            if (r.y > 300) { b.click(); return { ok: true }; }
          }
        }
        return { ok: false };
      })()`,
      description: '点击落库配置按钮' },
    { type: 'wait', ms: 3000, description: '等待落库配置弹窗加载' },
    // 验证弹窗结构
    { type: 'evaluate',
      expression: `(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { hasModal: false };
        const text = modal.innerText;
        const checks = {
          hasTitle: text.includes('落库配置'),
          hasPendingFields: text.includes('待落库字段'),
          hasTargetVars: text.includes('目标变量'),
          hasSearchBox: !!modal.querySelector('input[placeholder*="查询"]'),
          hasConfirmBtn: text.includes('确认配置'),
          hasCancelBtn: text.includes('取') && text.includes('消'),
        };
        // 检查树分类
        const expandBtns = modal.querySelectorAll('button[aria-expanded], button[class*="expanded"]');
        const categories = [];
        for (const b of expandBtns) {
          const txt = b.textContent.trim();
          if (txt) categories.push(txt.substring(0, 30));
        }
        return { hasModal: true, checks, categories };
      })()`,
      storeAs: 'storageModal',
      description: '验证落库配置弹窗结构' },
    { type: 'screenshot', label: 'storage-tree-modal', description: '截图-落库配置树结构' },
    // 关闭
    { type: 'pressKey', key: 'Escape', description: '关闭落库配置' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-storage-tree', 'UI：策略详情-落库配置树结构验证', desc), steps };
}

// ========== SD-15: 试运行弹窗 Tabs 验证 ==========
function sd15() {
  const desc = '打开策略详情页，点击试运行按钮，验证弹窗包含单次运行和批量运行两个Tab，单次运行Tab显示入参输入框。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    { type: 'clickText', text: '试运行', description: '点击试运行按钮' },
    { type: 'wait', ms: 2000, description: '等待试运行弹窗' },
    // 验证 Tabs
    { type: 'evaluate',
      expression: `(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { hasModal: false };
        const text = modal.innerText;
        const tabs = modal.querySelectorAll('.ant-tabs-tab');
        const tabTexts = Array.from(tabs).map(t => t.textContent.trim());
        const activeTab = modal.querySelector('.ant-tabs-tab-active');
        const inputFields = modal.querySelectorAll('input:not([type="hidden"])');
        const runBtn = modal.querySelector('button[disabled]');
        return {
          hasModal: true,
          hasTitle: text.includes('策略试运行') || text.includes('试运行'),
          tabs: tabTexts,
          activeTab: activeTab?.textContent.trim(),
          inputCount: inputFields.length,
          hasRunBtn: !!modal.querySelector('button'),
          runBtnDisabled: !!runBtn,
          hasSellerId: text.includes('seller_id'),
        };
      })()`,
      storeAs: 'trialRunModal',
      description: '验证试运行弹窗Tabs和字段' },
    { type: 'screenshot', label: 'trial-run-tabs', description: '截图-试运行弹窗Tabs' },
    // 切换到批量运行Tab
    { type: 'evaluate',
      expression: `(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { ok: false };
        const tabs = modal.querySelectorAll('.ant-tabs-tab');
        for (const tab of tabs) {
          if (tab.textContent.trim() === '批量运行') {
            tab.click();
            return { ok: true, clicked: '批量运行' };
          }
        }
        return { ok: false, tabCount: tabs.length };
      })()`,
      description: '切换到批量运行Tab' },
    { type: 'wait', ms: 1000, description: '等待Tab切换' },
    { type: 'screenshot', label: 'trial-run-batch', description: '截图-批量运行Tab' },
    // 关闭
    { type: 'pressKey', key: 'Escape', description: '关闭试运行' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-trial-run-tabs', 'UI：策略详情-试运行弹窗Tabs验证', desc), steps };
}

// ========== SD-16: 节点操作按钮验证 ==========
function sd16() {
  const desc = '打开含中间节点的策略，验证每个中间节点显示上移、下移、删除、编辑四个操作按钮，首尾节点无箭头。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 获取节点编排区所有节点和操作按钮
    { type: 'evaluate',
      expression: `(() => {
        const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排');
        if (!titleEl) return { ok: false };
        const card = titleEl.closest('.ant-card');
        const body = card?.querySelector('.ant-card-body');
        if (!body) return { ok: false };

        const result = { startNode: null, endNode: null, middleNodes: [] };

        // Start/End nodes
        const startEndNodes = body.querySelectorAll('[class*="startEndNode"]');
        for (const n of startEndNodes) {
          if (n.textContent.includes('Start')) {
            const btns = n.querySelectorAll('button');
            result.startNode = { name: 'Start', btnCount: btns.length, btnTexts: Array.from(btns).map(b => b.textContent.trim()) };
          }
          if (n.textContent.includes('End')) {
            const btns = n.querySelectorAll('button');
            result.endNode = { name: 'End', btnCount: btns.length, btnTexts: Array.from(btns).map(b => b.textContent.trim()) };
          }
        }

        // Middle nodes (innerNode)
        const middleItems = body.querySelectorAll('[class*="innerNode"], [class*="InnerNode"]');
        for (const item of middleItems) {
          const btns = item.querySelectorAll('button');
          const btnTexts = Array.from(btns).map(b => b.textContent.trim());
          const hasArrowUp = btnTexts.some(t => t.includes('arrow-up') || t === '');
          const hasArrowDown = btnTexts.some(t => t.includes('arrow-down'));
          const hasDelete = btnTexts.some(t => t.includes('delete'));
          const hasEdit = btnTexts.some(t => t.includes('edit'));
          result.middleNodes.push({
            name: item.querySelector('strong')?.textContent.trim() || 'unknown',
            btnCount: btns.length,
            hasArrowUp, hasArrowDown, hasDelete, hasEdit,
          });
        }
        return result;
      })()`,
      storeAs: 'nodeOperations',
      description: '验证节点操作按钮结构' },
    { type: 'screenshot', label: 'node-operations', description: '截图-节点操作按钮' },
    // 验证中间节点有四个操作按钮
    { type: 'evaluate',
      expression: `(() => {
        const titleEl = [...document.querySelectorAll('.ant-card-head-title')].find(e => e.textContent.trim() === '节点编排');
        if (!titleEl) return { ok: false };
        const card = titleEl.closest('.ant-card');
        const body = card?.querySelector('.ant-card-body');
        if (!body) return { ok: false };
        const middleItems = body.querySelectorAll('[class*="innerNode"], [class*="InnerNode"]');
        const allHaveFourBtns = Array.from(middleItems).every(item => item.querySelectorAll('button').length >= 4);
        return { middleNodeCount: middleItems.length, allHaveFourBtns };
      })()`,
      description: '验证中间节点都有4个操作按钮' },
  ];
  return { ...meta('ui-f88-sd-node-operations', 'UI：策略详情-节点操作按钮验证', desc), steps };
}

// ========== SD-17: 策略阶段下拉选项验证 ==========
function sd17() {
  const desc = '打开策略详情页，展开策略阶段下拉，验证包含实验/灰度/量产三个选项。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击策略阶段下拉
    { type: 'evaluate',
      expression: `(() => {
        const selects = document.querySelectorAll('.ant-select');
        for (const s of selects) {
          const val = s.querySelector('.ant-select-selection-item');
          if (val && (val.textContent.trim() === '实验' || val.textContent.trim() === '灰度' || val.textContent.trim() === '量产')) {
            const parent = s.closest('[class*="strong"]') || s.parentElement;
            const label = parent?.previousElementSibling?.textContent || '';
            if (label.includes('策略阶段') || !label) {
              const target = s.querySelector('.ant-select-selector') || s;
              target.click();
              return { ok: true, currentValue: val.textContent.trim() };
            }
          }
        }
        return { ok: false };
      })()`,
      description: '打开策略阶段下拉' },
    { type: 'wait', ms: 1000, description: '等待下拉展开' },
    // 获取下拉选项
    { type: 'evaluate',
      expression: `(() => {
        const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
        for (const d of dropdowns) {
          const items = d.querySelectorAll('.ant-select-item-option');
          if (items.length > 0) {
            return { options: Array.from(items).map(i => i.textContent.trim()) };
          }
        }
        return { options: [] };
      })()`,
      storeAs: 'stageOptions',
      description: '获取策略阶段选项列表' },
    { type: 'screenshot', label: 'stage-dropdown', description: '截图-策略阶段下拉' },
    // 关闭下拉
    { type: 'pressKey', key: 'Escape', description: '关闭下拉' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-stage-dropdown', 'UI：策略详情-策略阶段下拉选项验证', desc), steps };
}

// ========== SD-18: 环节下拉选项验证 ==========
function sd18() {
  const desc = '打开策略详情页，展开环节下拉，验证包含企划/设计/搭配/视觉/套图等全部9个选项。';
  const steps = [
    ...NAV_LIST, ...OPEN_FIRST,
    // 点击环节下拉
    { type: 'evaluate',
      expression: `(() => {
        const selects = document.querySelectorAll('.ant-select');
        const allValues = [];
        for (const s of selects) {
          const val = s.querySelector('.ant-select-selection-item');
          if (val) allValues.push({ value: val.textContent.trim(), select: s });
        }
        // 环节 Select 是第二个有值的 ant-select（第一个是策略阶段）
        const stepOptions = ['视觉', '设计', '企划', '搭配', '套图', '款式分配', '信息补充', '面料上身', '视频'];
        for (const item of allValues) {
          if (stepOptions.includes(item.value)) {
            const target = item.select.querySelector('.ant-select-selector') || item.select;
            target.click();
            return { ok: true, currentValue: item.value };
          }
        }
        return { ok: false, allValues: allValues.map(v => v.value) };
      })()`,
      description: '打开环节下拉' },
    { type: 'wait', ms: 1000, description: '等待下拉展开' },
    // 获取选项列表
    { type: 'evaluate',
      expression: `(() => {
        const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
        for (const d of dropdowns) {
          const items = d.querySelectorAll('.ant-select-item-option');
          if (items.length >= 5) {
            return { options: Array.from(items).map(i => i.textContent.trim()), count: items.length };
          }
        }
        return { options: [], count: 0 };
      })()`,
      storeAs: 'stepOptions',
      description: '获取环节选项列表' },
    { type: 'screenshot', label: 'step-dropdown', description: '截图-环节下拉' },
    // 关闭
    { type: 'pressKey', key: 'Escape', description: '关闭下拉' },
    { type: 'wait', ms: 500, description: '等待关闭' },
  ];
  return { ...meta('ui-f88-sd-step-dropdown', 'UI：策略详情-环节下拉选项验证', desc), steps };
}

// ========== 生成所有用例 ==========
const generators = [sd10, sd11, sd12, sd13, sd14, sd15, sd16, sd17, sd18];
let count = 0;
for (const gen of generators) {
  const c = gen();
  const filename = `${c.id.replace(/-/g, '_')}.json`;
  const filepath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(c, null, 2) + '\n');
  console.log(`✓ ${filename} (${c.steps.length} steps) - ${c.name}`);
  count++;
}
console.log(`\n共生成 ${count} 个策略详情补充用例到 ${OUT_DIR}`);
