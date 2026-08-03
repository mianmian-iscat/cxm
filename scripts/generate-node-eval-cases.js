#!/usr/bin/env node
/**
 * 批量生成 F88 全节点 eval 用例
 * 基于模板匹配用例的结构，为每种节点类型生成独立用例
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');

// 所有节点类型配置（排除推送选款、选片、模板匹配已有）
const NODE_TYPES = [
  { key: 'llm_text', name: 'LLM文本生成', assertField: '模型类型' },
  { key: 'image_gen', name: '生图', assertField: '模型类型' },
  { key: 'map_image', name: 'Map生图', assertField: '输出模式' },
  { key: 'season_tag', name: '季节标签', assertField: '图片URL' },
  { key: 'industry_tag', name: '产业标签', assertField: '图片URL' },
  { key: 'pricing', name: '定价节点', assertField: '图片URL' },
  { key: 'manual_audit', name: '人工审核', assertField: '审核节点' },
  { key: 'style_alloc', name: '款式分配', assertField: '图片URL' },
  { key: 'fabric_tryon', name: '面料上身', assertField: '面料图' },
  { key: 'image_crop', name: '图像裁头', assertField: '输入图片' },
  { key: 'match_score', name: '匹配度打分', assertField: '输入图片' },
  { key: 'caption', name: 'Caption', assertField: '图片URL' },
  { key: 'redesign_prompt', name: '改款prompt推理', assertField: 'Caption' },
  { key: 'video_gen', name: '视频生成', assertField: '模型类型' },
  { key: 'auto_audit', name: '机审', assertField: '算法类型' },
  { key: 'hd_enhance', name: '高清化处理', assertField: '输入图片' },
  { key: 'video_upload', name: '视频上传', assertField: '上传类型' },
];

function generateCase(node) {
  const id = `ui-f88-create-${node.key}-strategy`;
  const name = `UI：F88 新建${node.name}策略（全流程）`;
  return {
    id,
    name,
    description: `从策略列表页新建策略，配置 Start 节点入参 seller_id，添加${node.name}节点，保存策略并刷新验证持久化。`,
    businessType: 'f88_material_production',
    scene: 'f88-test',
    priority: 'P1',
    category: 'regression',
    context: {
      urlPattern: 'pre-aifashion-xiaoer.alibaba-inc.com',
      url: 'https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list',
      waitAfterLoad: 3000,
      auth: 'buc'
    },
    steps: [
      // --- 1. 打开策略列表 ---
      { type: 'navigate', url: 'https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list', waitUntil: 'networkidle', screenshot: true, description: '打开策略列表页' },
      { type: 'wait', ms: 3000, description: '等待策略列表加载' },
      { type: 'assert', target: 'page', contains: '策略列表', description: '验证策略列表页已加载' },
      { type: 'assert', target: 'page', contains: '新建策略', description: '验证存在新建策略入口' },
      { type: 'clickText', text: '新建策略', description: '点击新建策略按钮' },
      { type: 'wait', ms: 3000, description: '等待新建策略弹窗加载' },
      { type: 'assert', target: 'page', contains: '策略', description: '验证弹窗已出现' },
      // --- 2. 填写策略名称（用稳定 id + React native setter） ---
      {
        type: 'evaluate',
        expression: `(() => { const input = document.querySelector('input#name'); if (!input) return { ok: false, reason: 'no input' }; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(input, '自动化测试-${node.name}策略'); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); return { ok: true }; })()`,
        description: '填写策略名称'
      },
      { type: 'wait', ms: 500, description: '等待名称输入生效' },
      // --- 3. 选择环节（通过 input id 定位所属 ant-select 容器） ---
      {
        type: 'evaluate',
        expression: "(() => { const el = document.querySelector('#stageCode'); if (!el) return false; const sel = el.closest('.ant-select'); const target = sel?.querySelector('.ant-select-selector') || sel; if (target) { target.setAttribute('data-testid', 'stage-select'); return true; } return false; })()",
        description: '标记环节 Select 容器'
      },
      { type: 'click', selector: '[data-testid="stage-select"]', description: '打开环节 Select 下拉' },
      { type: 'wait', ms: 1000, description: '等待环节下拉列表展开' },
      { type: 'click', text: '视觉', within: '.ant-select-dropdown:not(.ant-select-dropdown-hidden)', description: '选择环节-视觉' },
      { type: 'wait', ms: 800, description: '等待环节选择生效' },
      // --- 4. 选择生命周期（通过 input id 定位所属 ant-select 容器） ---
      {
        type: 'evaluate',
        expression: "(() => { const el = document.querySelector('#lifeCycleCode'); if (!el) return false; const sel = el.closest('.ant-select'); const target = sel?.querySelector('.ant-select-selector') || sel; if (target) { target.setAttribute('data-testid', 'lifecycle-select'); return true; } return false; })()",
        description: '标记生命周期 Select 容器'
      },
      { type: 'click', selector: '[data-testid="lifecycle-select"]', description: '打开生命周期 Select 下拉' },
      { type: 'wait', ms: 1000, description: '等待生命周期下拉列表展开' },
      { type: 'click', text: '实验', within: '.ant-select-dropdown:not(.ant-select-dropdown-hidden)', description: '选择生命周期-实验' },
      { type: 'wait', ms: 800, description: '等待生命周期选择生效' },
      // --- 5. 点击确定（用 aria-label 定位） ---
      {
        type: 'evaluate',
        expression: "(() => { const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)'); if (!modal) return { ok: false }; const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent.replace(/\\s/g,''))); if (btn) { btn.click(); return { ok: true }; } return { ok: false }; })()",
        description: '点击确定创建策略'
      },
      { type: 'wait', ms: 3000, description: '等待跳转策略详情页' },
      {
        type: 'evaluate',
        expression: "(() => { const url = window.location.href; const match = url.match(/strategy\\/detail\\/(\\d+)/); return match ? { strategyId: match[1], url } : { strategyId: null, url }; })()",
        storeAs: 'newStrategy',
        description: '获取新建策略的ID'
      },
      { type: 'assert', target: 'page', contains: '节点编排', description: '验证节点编排区域已渲染' },
      { type: 'assert', target: 'page', contains: 'Start', description: '验证 Start 节点存在' },
      { type: 'clickText', text: 'Start', description: '点击 Start 节点打开抽屉' },
      { type: 'wait', ms: 2000, description: '等待 Start 抽屉加载' },
      { type: 'clickText', text: '新增字段', description: '点击新增字段按钮' },
      { type: 'wait', ms: 2000, description: '等待字段选择 modal 加载' },
      { type: 'click', text: 'seller_id', within: '.ant-modal:not(.ant-modal-hidden)', description: '选择 seller_id 字段' },
      { type: 'wait', ms: 1500, description: '等待字段添加完成' },
      // --- 8. 新增节点 ---
      { type: 'clickText', text: '新增节点', description: '点击新增节点按钮' },
      { type: 'wait', ms: 2000, description: '等待新增节点弹窗加载' },
      {
        type: 'evaluate',
        expression: `(() => { const modals = document.querySelectorAll('.ant-modal'); for (const m of modals) { if (m.classList.contains('ant-modal-hidden')) continue; const r = m.getBoundingClientRect(); if (r.width < 200) continue; const cards = m.querySelectorAll('.ant-card-hoverable, .ant-card'); for (const card of cards) { const t = card.querySelector('.ant-card-meta-title'); if (t && t.textContent.trim() === '${node.name}') { card.scrollIntoView({ block: 'center' }); card.click(); return { ok: true }; } } } return { ok: false }; })()`,
        description: `点击选择${node.name}节点卡片`
      },
      { type: 'wait', ms: 3000, description: `等待${node.name}节点编辑抽屉加载` },
      { type: 'screenshot', label: `${node.key}-drawer`, description: `截图-${node.name}编辑抽屉` },
      { type: 'assert', target: 'page', contains: node.assertField, description: `验证抽屉中显示${node.assertField}字段` },
      { type: 'clickText', text: '保 存', description: `保存${node.name}节点` },
      { type: 'wait', ms: 2000, description: '等待节点保存' },
      { type: 'assert', target: 'page', contains: node.name, description: `验证编排区已渲染${node.name}节点` },
      { type: 'clickText', text: '保 存', description: '点击保存策略' },
      { type: 'wait', ms: 3000, description: '等待策略保存完成' },
      {
        type: 'evaluate',
        expression: "(() => { const msgs = document.querySelectorAll('.ant-message .ant-message-success, .ant-notification-notice-message'); return Array.from(msgs).map(m => m.textContent.trim()); })()",
        description: '检查保存成功提示'
      },
      { type: 'navigate', url: 'current', waitUntil: 'networkidle', description: '刷新页面验证持久化' },
      { type: 'wait', ms: 3000, description: '等待页面重新加载' },
      { type: 'assert', target: 'page', contains: node.name, description: `刷新后验证${node.name}节点仍存在` },
      { type: 'assert', target: 'page', contains: 'Start', description: '刷新后验证 Start 节点仍存在' },
    ],
    capture: { enabled: true, filter: 'workflow2|strategy', captureBody: true },
    screenshot: { onError: true },
    contextOptimization: { screenshotExternal: true, maxResponseSizeKb: 100, outputCompact: true },
    _expected: { status: 'pass' },
  };
}

// 生成所有用例
let generated = 0;
for (const node of NODE_TYPES) {
  const evalCase = generateCase(node);
  const filename = `ui_f88_create_${node.key}_strategy.json`;
  const filepath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(evalCase, null, 2) + '\n');
  console.log(`✓ ${filename} (${evalCase.steps.length} steps)`);
  generated++;
}

console.log(`\n共生成 ${generated} 个 eval 用例到 ${OUT_DIR}`);
