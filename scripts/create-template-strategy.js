#!/usr/bin/env node
/**
 * 新建模板匹配策略（独立脚本）
 *
 * 流程：策略列表 → 新建策略弹窗 → 填写名称/选环节 → 进入策略详情 → 新增"模板匹配"节点 → 保存
 *
 * 用法：
 *   node scripts/create-template-strategy.js [策略名称]
 *
 * 前置：Chrome --remote-debugging-port=9222 已启动且已登录 F88 预发
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'template-strategy');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const TS = String(Date.now()).slice(-6);
const STRATEGY_NAME = process.argv[2] || `模板匹配策略_${TS}`;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${name}.jpg`);
  return fp;
}

/**
 * 点击含指定文本的按钮/元素（精确匹配优先，模糊匹配兜底）
 */
async function clickTextBtn(page, text) {
  const clicked = await page.evaluate((t) => {
    const els = [...document.querySelectorAll('button, a, span, div')];
    // 精确匹配
    for (const el of els) {
      const txt = el.textContent.trim().replace(/\s+/g, '');
      const target = t.replace(/\s+/g, '');
      if (txt === target && el.offsetHeight > 0) { el.click(); return el.tagName + ': ' + el.textContent.trim(); }
    }
    // 模糊匹配（元素文本 < 30 字符）
    for (const el of els) {
      const txt = el.textContent.replace(/\s+/g, '');
      const target = t.replace(/\s+/g, '');
      if (txt.includes(target) && el.offsetHeight > 0 && el.textContent.length < 30) { el.click(); return el.tagName + '(p): ' + el.textContent.trim(); }
    }
    return null;
  }, text);
  if (clicked) console.log(`  ✅ 点击: ${clicked}`);
  else console.log(`  ❌ 未找到: "${text}"`);
  return !!clicked;
}

/**
 * Ant Design Select 下拉选择（placeholder 定位 + mouse.click 触发）
 */
async function antSelect(page, placeholderText, optionText) {
  const box = await page.evaluate((ph) => {
    const sels = document.querySelectorAll('.ant-select');
    for (const s of sels) {
      const p = s.querySelector('.ant-select-selection-placeholder, .ant-select-selection-item');
      if (p && p.textContent.includes(ph)) {
        const r = s.querySelector('.ant-select-selector').getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  }, placeholderText);
  if (!box) {
    console.log(`  ❌ Select "${placeholderText}" 未找到`);
    return false;
  }
  await page.mouse.click(box.x, box.y);
  await sleep(800);

  const selected = await page.evaluate((target) => {
    const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
    for (const dd of dds) {
      const items = dd.querySelectorAll('.ant-select-item-option');
      for (const item of items) {
        if (item.textContent.trim() === target) { item.click(); return item.textContent.trim(); }
      }
      for (const item of items) {
        if (item.textContent.includes(target)) { item.click(); return item.textContent.trim(); }
      }
    }
    return null;
  }, optionText);
  console.log(`  Select "${placeholderText}" → ${selected || '未选到'}`);
  await sleep(500);
  return !!selected;
}

/**
 * 在抽屉内选择 ant-select 下拉（按 label 定位）
 */
async function drawerSelect(page, label, optionText) {
  const pos = await page.evaluate((lbl) => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (!drawer) return null;
    const items = [...drawer.querySelectorAll('.ant-form-item')];
    for (const item of items) {
      const l = item.querySelector('.ant-form-item-label')?.textContent?.trim() || '';
      if (l === lbl) {
        const sel = item.querySelector('.ant-select .ant-select-selector');
        if (sel) {
          const r = sel.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
    }
    return null;
  }, label);
  if (!pos) { console.log(`    ❌ drawerSelect "${label}" 未找到`); return false; }
  await page.mouse.click(pos.x, pos.y);
  await sleep(1000);

  const selected = await page.evaluate((target) => {
    const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
    for (const dd of dds) {
      const items = [...dd.querySelectorAll('.ant-select-item-option, .ant-select-item')];
      for (const item of items) {
        if (item.textContent.trim() === target) {
          const r = item.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: target };
        }
      }
      for (const item of items) {
        if (item.textContent.includes(target)) {
          const r = item.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: item.textContent.trim() };
        }
      }
    }
    return null;
  }, optionText);
  if (selected) {
    await page.mouse.click(selected.x, selected.y);
    console.log(`    ✅ ${label} → ${selected.text}`);
    await sleep(500);
    return true;
  }
  console.log(`    ❌ ${label} 选项 "${optionText}" 未找到`);
  await page.keyboard.press('Escape');
  await sleep(300);
  return false;
}

/**
 * 在抽屉内点击列表项选择（ant-list-item 结构）
 */
async function drawerListItem(page, label, optionText) {
  const pos = await page.evaluate((lbl, opt) => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (!drawer) return null;
    const items = [...drawer.querySelectorAll('.ant-form-item')];
    for (const item of items) {
      const l = item.querySelector('.ant-form-item-label')?.textContent?.trim() || '';
      if (l === lbl) {
        const listItems = [...item.querySelectorAll('.ant-list-item')];
        for (const li of listItems) {
          if (li.textContent.trim() === opt || li.textContent.trim().includes(opt)) {
            const rect = li.getBoundingClientRect();
            if (rect.height > 0) return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
          }
        }
      }
    }
    return null;
  }, label, optionText);
  if (pos) {
    await page.mouse.click(pos.x, pos.y);
    console.log(`    ✅ ${label} → ${optionText}`);
    await sleep(300);
    return true;
  }
  console.log(`    ❌ ${label} 列表项 "${optionText}" 未找到`);
  return false;
}

/**
 * 新增节点：点击"+ 新增节点" → 选择节点类型 → 填充抽屉表单 → 保存 → 关闭抽屉
 * @param {object} opts - 可选的抽屉表单配置 { mode, dataSource, stage, scene, sortDim, targetCount }
 */
async function addNode(page, nodeTypeName, opts = {}) {
  console.log(`  添加节点: ${nodeTypeName}`);

  // 点击 "+ 新增节点"
  const btnPos = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button, div, span')];
    for (const el of els) {
      const t = el.textContent.trim().replace(/\s+/g, '');
      if (t === '+新增节点' || t === '新增节点') {
        const r = el.getBoundingClientRect();
        if (r.height > 0 && r.width > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (!btnPos) { console.log(`    ❌ +新增节点未找到`); return false; }
  await page.mouse.click(btnPos.x, btnPos.y);
  await sleep(2000);
  await ss(page, `node-dialog-${nodeTypeName}`);

  // 选择节点类型（多重策略：精确文本 → ant-card 标题 → TreeWalker 文本节点）
  const pos = await page.evaluate((name) => {
    const target = name.replace(/\s+/g, '');
    // 策略1：查找 ant-card-meta-title 精确匹配
    const titles = document.querySelectorAll('.ant-card-meta-title');
    for (const t of titles) {
      if (t.textContent.trim().replace(/\s+/g, '') === target) {
        const card = t.closest('.ant-card');
        if (card && card.offsetHeight > 0) {
          return { x: Math.round(card.getBoundingClientRect().x + card.getBoundingClientRect().width / 2), y: Math.round(card.getBoundingClientRect().y + card.getBoundingClientRect().height / 2), text: t.textContent.trim(), strategy: 'card-title' };
        }
      }
    }
    // 策略2：查找 ant-card 包含目标文本
    const cards = document.querySelectorAll('.ant-card.ant-card-hoverable');
    for (const card of cards) {
      const titleEl = card.querySelector('.ant-card-meta-title, h3, h4, strong');
      if (titleEl && titleEl.textContent.trim().replace(/\s+/g, '').includes(target)) {
        const br = card.getBoundingClientRect();
        return { x: Math.round(br.x + br.width / 2), y: Math.round(br.y + br.height / 2), text: titleEl.textContent.trim(), strategy: 'card-hoverable' };
      }
    }
    // 策略3：TreeWalker 查找文本节点
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent.trim();
      if (text === target) {
        const parent = walker.currentNode.parentElement;
        if (parent && parent.offsetHeight > 0 && parent.offsetHeight < 100) {
          const br = parent.getBoundingClientRect();
          return { x: Math.round(br.x + br.width / 2), y: Math.round(br.y + br.height / 2), text, strategy: 'textNode' };
        }
      }
    }
    return null;
  }, nodeTypeName);

  if (pos) {
    await page.mouse.click(pos.x, pos.y);
    console.log(`    ✅ 选择: "${pos.text}"`);
  } else {
    console.log(`    ❌ 节点类型未找到: ${nodeTypeName}`);
    await ss(page, `node-type-not-found-${nodeTypeName}`);
    return false;
  }
  await sleep(3000);
  await ss(page, `node-selected-${nodeTypeName}`);

  // 填充模板匹配节点特有的必填字段
  if (nodeTypeName === '模板匹配') {
    const mode = opts.mode || '规则匹配';
    await drawerSelect(page, '匹配模式', mode);
    await sleep(1500);  // 等待联动字段渲染

    if (mode === '规则匹配') {
      await drawerSelect(page, '数据来源', opts.dataSource || '模板包');
      await drawerSelect(page, '应用环节', opts.stage || '视觉');
      await drawerSelect(page, '应用场景', opts.scene || '主图素材');
      await drawerListItem(page, '排序维度', opts.sortDim || '类目');
      // 目标匹配数量默认值 4，一般无需修改
    }
    await ss(page, `node-form-filled-${nodeTypeName}`);
  }

  // 保存编辑抽屉（mouse.click 坐标点击）
  const savePos = await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (!drawer) return null;
    const btns = [...drawer.querySelectorAll('button')];
    const saveBtn = btns.find(b => /保.*存/.test(b.textContent));
    if (!saveBtn) return null;
    const r = saveBtn.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  if (savePos) {
    await page.mouse.click(savePos.x, savePos.y);
    console.log(`    ✅ 抽屉保存`);
    await sleep(2000);
  }

  // 检查是否仍有表单错误
  const errors = await page.evaluate(() => {
    const errs = document.querySelectorAll('.ant-form-item-explain-error');
    return [...errs].filter(e => e.offsetHeight > 0).map(e => e.textContent.trim());
  });
  if (errors.length > 0) {
    console.log(`    ⚠️ 表单错误: ${JSON.stringify(errors)}`);
  }

  // 关闭抽屉
  await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (drawer) {
      const close = drawer.querySelector('.ant-drawer-close');
      if (close && close.offsetHeight > 0) close.click();
    }
  });
  await sleep(1000);
  await ss(page, `node-added-${nodeTypeName}`);
  return errors.length === 0;
}

/**
 * 配置 Start 节点入参：添加 seller_id
 * 流程：点击 Start 节点 → 抽屉 → 新增字段 → modal 选 seller_id → 关闭 modal → 关闭抽屉
 */
async function configureStartNodeParams(page) {
  // 点击 Start 节点打开抽屉
  const startPos = await page.evaluate(() => {
    const nodes = document.querySelectorAll('[class*=Node]');
    for (const node of nodes) {
      if (node.textContent.trim().includes('Start')) {
        const r = node.getBoundingClientRect();
        if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (!startPos) {
    console.log('  ❌ Start 节点未找到');
    return false;
  }
  await page.mouse.click(startPos.x, startPos.y);
  console.log('  ✅ 点击 Start 节点');
  await sleep(2000);

  // 点击"新增字段"按钮
  const addFieldPos = await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (!drawer) return null;
    const btns = [...drawer.querySelectorAll('button')];
    for (const btn of btns) {
      const t = btn.textContent.trim().replace(/\s+/g, '');
      if (t === '+新增字段' || t === '新增字段' || t.includes('新增字段')) {
        const r = btn.getBoundingClientRect();
        if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (!addFieldPos) {
    console.log('  ❌ 新增字段按钮未找到');
    // 关闭抽屉
    await page.evaluate(() => {
      const close = document.querySelector('.ant-drawer-close');
      if (close && close.offsetHeight > 0) close.click();
    });
    await sleep(1000);
    return false;
  }
  await page.mouse.click(addFieldPos.x, addFieldPos.y);
  console.log('  ✅ 点击新增字段');
  await sleep(2000);

  // 在 modal 中选择 seller_id（动态查找）
  const sellerPos = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (!modal) return null;
    const items = [...modal.querySelectorAll('.ant-list-item, tr, .ant-table-row, [class*=item]')];
    for (const item of items) {
      if (item.textContent.includes('seller_id')) {
        const r = item.getBoundingClientRect();
        if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    // 兜底：找包含 seller_id 的任意元素
    const all = [...modal.querySelectorAll('div, span, td, p, li')];
    for (const el of all) {
      if (el.textContent.trim() === 'seller_id' || (el.textContent.includes('seller_id') && el.textContent.length < 30)) {
        const r = el.getBoundingClientRect();
        if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (sellerPos) {
    await page.mouse.click(sellerPos.x, sellerPos.y);
    console.log('  ✅ 选择 seller_id');
  } else {
    console.log('  ⚠️ 动态查找 seller_id 失败，尝试坐标点击');
    await page.mouse.click(547, 175);
  }
  await sleep(1500);

  // 检查 modal 是否还显示，若是则关闭
  const modalStillOpen = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    return modal && modal.offsetHeight > 0;
  });
  if (modalStillOpen) {
    // 尝试找确认/关闭按钮
    const modalCloseBtn = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (!modal) return null;
      const btns = [...modal.querySelectorAll('button')];
      // 优先找确定/确认/添加
      for (const btn of btns) {
        const t = btn.textContent.trim();
        if (/确.*定|确.*认|添.*加|保.*存/.test(t)) {
          const r = btn.getBoundingClientRect();
          if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      // 兜底关闭按钮
      const closeIcon = modal.querySelector('.ant-modal-close');
      if (closeIcon) {
        const r = closeIcon.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
      return null;
    });
    if (modalCloseBtn) {
      await page.mouse.click(modalCloseBtn.x, modalCloseBtn.y);
      console.log('  ✅ 关闭字段选择 modal');
    } else {
      await page.keyboard.press('Escape');
      console.log('  ✅ Escape 关闭 modal');
    }
    await sleep(1000);
  }

  // 验证 seller_id 已配置
  const paramCheck = await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (!drawer) return { configured: false };
    const text = drawer.textContent;
    return {
      configured: text.includes('seller_id'),
      snippet: text.substring(0, 300)
    };
  });
  console.log(`  ${paramCheck.configured ? '✅' : '⚠️'} seller_id 配置状态: ${paramCheck.configured ? '已配置' : '未确认'}`);

  // 关闭 Start 抽屉
  await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer-open') || document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (drawer) {
      const close = drawer.querySelector('.ant-drawer-close');
      if (close && close.offsetHeight > 0) close.click();
    }
  });
  console.log('  ✅ 关闭 Start 抽屉');
  await sleep(1500);
  return paramCheck.configured;
}

// ============ 主流程 ============
async function main() {
  console.log('🚀 新建模板匹配策略');
  console.log(`  策略名: ${STRATEGY_NAME}\n`);

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();
  const result = { ts: new Date().toISOString(), strategyName: STRATEGY_NAME };

  try {
    // ── Step 1: 打开策略列表 ──
    console.log('=== Step 1: 策略列表 ===');
    await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    await ss(page, '01-strategy-list');

    // 验证页面
    const pageText = await page.evaluate(() => document.body.innerText.substring(0, 500));
    if (!pageText.includes('策略')) {
      console.log('  ❌ 策略列表页未加载，可能需要登录');
      result.status = 'fail';
      result.error = '页面未加载（可能需要登录）';
      return;
    }
    console.log('  ✅ 策略列表页已加载');

    // ── Step 2: 点击新建策略 ──
    console.log('\n=== Step 2: 新建策略弹窗 ===');
    await clickTextBtn(page, '新建策略');
    await sleep(2000);
    await ss(page, '02-new-strategy-modal');

    // ── Step 3: 填写策略名称 ──
    console.log('\n=== Step 3: 填写策略信息 ===');
    const nameInput = await page.$('.ant-modal input[placeholder*="请输入策略名称"], .ant-modal input[placeholder*="请输入"], .ant-modal input:not([type])');
    if (nameInput) {
      await nameInput.click({ clickCount: 3 });
      await nameInput.type(STRATEGY_NAME);
      console.log(`  ✅ 策略名称: ${STRATEGY_NAME}`);
    } else {
      console.log('  ⚠️ 名称输入框未找到，尝试用坐标定位');
    }

    // 选环节（默认"视觉"）
    await antSelect(page, '请选择环节', '视觉');
    await sleep(300);

    // 选生命周期（默认"实验"）
    await antSelect(page, '请选择生命周期', '实验');
    await sleep(300);

    await ss(page, '03-strategy-info-filled');

    // 确定
    await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) {
        const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent));
        if (btn) btn.click();
      }
    });
    await sleep(3000);
    await ss(page, '04-after-modal-confirm');

    // ── Step 4: 提取策略 ID ──
    console.log('\n=== Step 4: 策略详情 ===');
    const url = page.url();
    const idMatch = url.match(/(?:detail|strategyId)[/=](\d+)/) || url.match(/[?&]id=(\d+)/);
    const strategyId = idMatch ? idMatch[1] : 'unknown';
    result.strategyId = strategyId;
    result.url = url;
    console.log(`  策略ID: ${strategyId}`);
    console.log(`  URL: ${url}`);

    // 验证详情页
    const detailText = await page.evaluate(() => document.body.innerText.substring(0, 500));
    const hasNodeSection = detailText.includes('节点') || detailText.includes('编排');
    console.log(`  ${hasNodeSection ? '✅' : '⚠️'} 节点编排区域: ${hasNodeSection ? '已渲染' : '未找到'}`);
    await ss(page, '05-strategy-detail');

    // ── Step 4.5: 配置策略入参 seller_id ──
    console.log('\n=== Step 4.5: 配置 Start 节点入参 (seller_id) ===');
    await configureStartNodeParams(page);
    await ss(page, '05-start-node-params');

    // ── Step 5: 添加模板匹配节点 ──
    console.log('\n=== Step 5: 添加模板匹配节点 ===');
    const nodeAdded = await addNode(page, '模板匹配');
    result.templateMatchNode = nodeAdded;
    if (nodeAdded) {
      console.log('  ✅ 模板匹配节点已添加');
    } else {
      console.log('  ❌ 模板匹配节点添加失败');
    }
    await ss(page, '06-after-add-node');

    // ── Step 6: 验证节点编排 ──
    console.log('\n=== Step 6: 验证节点编排 ===');
    const nodeCheck = await page.evaluate(() => {
      const nodes = document.querySelectorAll('[class*=Node]');
      const nodeTexts = [...nodes].map(n => n.textContent.trim().substring(0, 50)).filter(t => t.length > 2 && t.length < 60);
      return {
        count: nodeTexts.length,
        texts: nodeTexts
      };
    });
    console.log(`  节点数: ${nodeCheck.count}`);
    console.log(`  节点内容: ${JSON.stringify(nodeCheck.texts)}`);
    const hasTemplateMatch = nodeCheck.texts.some(t => t.includes('模板匹配'));
    console.log(`  ${hasTemplateMatch ? '✅' : '⚠️'} 模板匹配节点: ${hasTemplateMatch ? '已渲染' : '未确认'}`);
    result.nodeCheck = nodeCheck;
    await ss(page, '07-node-verification');

    // ── Step 7: 保存策略 ──
    console.log('\n=== Step 7: 保存策略 ===');
    const stratSavePos = await page.evaluate(() => {
      const els = [...document.querySelectorAll('button')];
      for (const el of els) {
        const t = el.textContent.trim().replace(/\s+/g, '');
        if (t === '保存' && el.offsetHeight > 0) {
          const r = el.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      return null;
    });
    if (stratSavePos) {
      await page.mouse.click(stratSavePos.x, stratSavePos.y);
      console.log('  ✅ 策略保存已点击');
    } else {
      await clickTextBtn(page, '保存');
    }
    await sleep(4000);

    const msgs = await page.evaluate(() =>
      [...document.querySelectorAll('.ant-message-notice, .ant-message-success')]
        .map(m => m.textContent.trim())
        .filter(t => t.length > 0)
    );
    console.log(`  保存消息: ${JSON.stringify(msgs)}`);
    result.saveMessages = msgs;
    result.status = msgs.some(m => m.includes('成功') || m.includes('保存')) ? 'pass' : 'unknown';

    // ── Step 8: 刷新验证节点持久化 ──
    console.log('\n=== Step 8: 刷新验证 ===');
    await page.reload({ waitUntil: 'networkidle2' });
    await sleep(3000);
    const finalCheck = await page.evaluate(() => {
      const nodes = document.querySelectorAll('[class*=Node]');
      const nodeTexts = [...nodes].map(n => n.textContent.trim().substring(0, 50)).filter(t => t.length > 2 && t.length < 60);
      const hasTmpl = nodeTexts.some(t => t.includes('模板匹配'));
      const bodyText = document.body.innerText;
      return { nodeTexts, hasTmpl, bodyHasTmpl: bodyText.includes('模板匹配') };
    });
    console.log(`  刷新后节点: ${JSON.stringify(finalCheck.nodeTexts)}`);
    console.log(`  含模板匹配: ${finalCheck.hasTmpl || finalCheck.bodyHasTmpl ? '✅' : '❌'}`);
    if (finalCheck.hasTmpl || finalCheck.bodyHasTmpl) result.status = 'pass';
    await ss(page, '09-final-verified');

    // ── 汇总 ──
    console.log('\n========== 汇总 ==========');
    console.log(`  策略名: ${STRATEGY_NAME}`);
    console.log(`  策略ID: ${strategyId}`);
    console.log(`  URL: ${url}`);
    console.log(`  模板匹配节点: ${nodeAdded ? '✅ 已添加' : '❌ 失败'}`);
    console.log(`  节点编排: ${nodeCheck.count} 个节点`);
    console.log(`  保存: ${result.status}`);

  } catch (e) {
    console.error(`\n❌ 异常: ${e.message}`);
    result.status = 'error';
    result.error = e.message;
    await ss(page, 'error');
  }

  // 保存结果
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const resultPath = path.join(SS_DIR, 'result.json');
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2));
  console.log(`  结果: ${resultPath}`);

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('❌ Fatal:', e.message); process.exit(1); });
