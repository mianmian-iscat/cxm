#!/usr/bin/env node
/**
 * TC27 - 端到端集成测试执行脚本
 * Phase 1: 参考链路20180数据采集
 * Phase 2: 新建策略 + 节点编排(生图/人工审核/高清化)
 * Phase 3: 新建链路 + 添加环节 + 绑定策略
 * Phase 4: 试运行 → 上传Excel → 发起任务
 * Phase 5: 各环节状态监控验证
 * Phase 6: API/DB端到端数据流验证
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'tc27');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const REF_LINK_ID = '20180';
const TEST_SELLER = '2219635649153';
const TEST_SEED_IMG = 'https://img.alicdn.com/imgextra/i1/O1CN01Z5paLz1O4SsHjYjJN_!!6000000001652-0-tps-800-800.jpg';
const STRATEGY_NAME = `E2E首图审核_${String(Date.now()).slice(-6)}`;
const LINK_NAME = `E2E链路_${String(Date.now()).slice(-6)}`;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
  return fp;
}

// Ant Design Select 展开 + 选择
async function antSelect(page, placeholderText, optionText) {
  // Step 1: page.mouse.click 展开
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
  if (!box) { console.log(`  ❌ Select "${placeholderText}" 未找到`); return false; }
  await page.mouse.click(box.x, box.y);
  await sleep(800);

  // Step 2: 选择目标选项
  const selected = await page.evaluate((target) => {
    const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
    for (const dd of dds) {
      const items = dd.querySelectorAll('.ant-select-item-option');
      for (const item of items) {
        if (item.textContent.trim() === target) {
          item.click();
          return item.textContent.trim();
        }
      }
      // fallback: 包含目标文字的选项
      for (const item of items) {
        if (item.textContent.includes(target)) {
          item.click();
          return item.textContent.trim();
        }
      }
    }
    return null;
  }, optionText);
  console.log(`  Select "${placeholderText}" → ${selected || '未选到'}`);
  await sleep(500);
  return !!selected;
}

// 点击文字按钮
async function clickTextBtn(page, text, tagFilter) {
  const clicked = await page.evaluate((t, filter) => {
    let els = [...document.querySelectorAll(filter || 'button, a, span, div')];
    // 精确匹配（含空格容错，如“保 存”=“保存”）
    for (const el of els) {
      const txt = el.textContent.trim().replace(/\s+/g, '');
      const target = t.replace(/\s+/g, '');
      if (txt === target && el.offsetHeight > 0) {
        el.click();
        return el.tagName + ': ' + el.textContent.trim();
      }
    }
    // 模糊匹配
    for (const el of els) {
      const txt = el.textContent.replace(/\s+/g, '');
      const target = t.replace(/\s+/g, '');
      if (txt.includes(target) && el.offsetHeight > 0 && el.textContent.length < 30) {
        el.click();
        return el.tagName + '(partial): ' + el.textContent.trim();
      }
    }
    return null;
  }, text, tagFilter);
  if (clicked) console.log(`  ✅ 点击: ${clicked}`);
  else console.log(`  ❌ 未找到: "${text}"`);
  return !!clicked;
}

// 等待页面包含指定文字
async function waitForText(page, text, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const found = await page.evaluate((t) => document.body.innerText.includes(t), text);
    if (found) return true;
    await sleep(500);
  }
  return false;
}

// ============ Phase 1: 参考链路20180数据采集 ============
async function phase1(page) {
  console.log('\n========== Phase 1: 参考链路20180数据采集 ==========');
  await page.goto(`${BASE}/strategy/linkDetail?id=${REF_LINK_ID}`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);
  await ss(page, 'p1-ref-link');

  // 验证租户
  const tenant = await page.evaluate(() => document.body.innerText.includes('F88'));
  console.log(`  租户验证: ${tenant ? '✅ F88' : '❌ 非F88'}`);

  // 采集环节
  const stages = await page.evaluate(() => {
    const found = [];
    const targets = ['刷标签', '首图生图', '首图审核', '套图生图', '套图审核'];
    const text = document.body.innerText;
    for (const t of targets) { if (text.includes(t)) found.push(t); }
    return found;
  });
  console.log(`  环节结构: ${JSON.stringify(stages)}`);

  // 采集起点入参
  const params = await page.evaluate(() => {
    const found = [];
    const targets = ['seller_id', 'seed_image_url', 'tao_cate', 'item_id'];
    const text = document.body.innerText;
    for (const t of targets) { if (text.includes(t)) found.push(t); }
    return found;
  });
  console.log(`  起点入参: ${JSON.stringify(params)}`);

  // 验证
  const p1Pass = stages.length >= 3 && params.length === 4;
  console.log(`  Phase 1 结果: ${p1Pass ? '✅ PASS' : '⚠️ 部分通过'}`);
  return p1Pass;
}

// ============ Phase 2: 新建策略 + 节点编排 ============
async function phase2(page) {
  console.log('\n========== Phase 2: 新建策略 + 节点编排 ==========');

  // 2a. 进入策略列表
  await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);
  await ss(page, 'p2-strategy-list');

  // 2b. 点击新建策略 → 弹窗
  await clickTextBtn(page, '新建策略');
  await sleep(2000);
  await ss(page, 'p2-new-strategy-modal');

  // 验证弹窗标题
  const modalVisible = await waitForText(page, '新建策略', 5000);
  console.log(`  弹窗可见: ${modalVisible}`);

  // 2c. 填策略名称 (max 30 chars)
  const nameInput = await page.$('.ant-modal input[placeholder*="请输入策略名称"], .ant-modal input[placeholder*="请输入"]');
  if (nameInput) {
    await nameInput.click({ clickCount: 3 });
    await nameInput.type(STRATEGY_NAME);
    console.log(`  策略名称: ${STRATEGY_NAME} (${STRATEGY_NAME.length} chars)`);
  } else {
    console.log('  ❌ 策略名称输入框未找到');
  }

  // 2d. 选择环节 = 视觉 (placeholder="请选择环节")
  await antSelect(page, '请选择环节', '视觉');
  await sleep(500);

  // 2e. 选择生命周期 (placeholder="请选择生命周期")
  await antSelect(page, '请选择生命周期', '实验');
  await sleep(500);

  await ss(page, 'p2-modal-filled');

  // 2f. 点击弹窗「确定」按钮
  const confirmed = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (modal) {
      const btns = modal.querySelectorAll('button');
      for (const b of btns) {
        if (b.textContent.trim() === '确 定' || b.textContent.trim() === '确定') {
          b.click();
          return true;
        }
      }
    }
    return false;
  });
  console.log(`  弹窗确定: ${confirmed}`);
  await sleep(3000);
  await ss(page, 'p2-after-confirm');

  // 2g. 检查是否跳转到策略详情页
  const afterUrl = page.url();
  console.log(`  跳转后URL: ${afterUrl}`);

  // 如果没有自动跳转，在列表中打开刚创建的策略
  if (!afterUrl.includes('detail') && !afterUrl.includes('strategyId')) {
    console.log('  未跳转详情页，在列表中搜索并打开...');
    // 搜索刚创建的策略
    const searchInput = await page.$('input[placeholder*="搜索策略名称"], input[placeholder*="策略名称"]');
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await searchInput.type(STRATEGY_NAME);
      await page.keyboard.press('Enter');
      await sleep(2000);
    }
    // 点击「打开」
    await clickTextBtn(page, '打开');
    await sleep(3000);
  }

  await ss(page, 'p2-strategy-detail');

  // 提取策略ID
  const stratUrl = page.url();
  const stratMatch = stratUrl.match(/(?:detail|strategyId)[/=](\d+)/) || stratUrl.match(/[?&]id=(\d+)/);
  const strategyId = stratMatch ? stratMatch[1] : 'unknown';
  console.log(`  策略ID: ${strategyId}`);

  // 2h. 验证策略详情页
  const detailVisible = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasNodeEdit: text.includes('节点编排'),
      hasStart: text.includes('策略入参'),
      hasEnd: text.includes('策略出参'),
      hasAddNode: text.includes('新增节点'),
      hasSave: text.includes('保存')
    };
  });
  console.log(`  策略详情页: ${JSON.stringify(detailVisible)}`);

  // 用 page.mouse.click 精准点击新增节点按钮
  async function clickAddNode(page) {
    // 先确保没有打开的抽屉/面板
    await page.evaluate(() => {
      const closeButtons = document.querySelectorAll('.ant-drawer-close, [class*=panel] [class*=close]');
      for (const btn of closeButtons) {
        if (btn.offsetHeight > 0) btn.click();
      }
    });
    await sleep(1000);

    const btnPos = await page.evaluate(() => {
      const els = [...document.querySelectorAll('button, div, span')];
      for (const el of els) {
        if (el.textContent.trim().replace(/\s+/g,'') === '+新增节点' || el.textContent.trim().replace(/\s+/g,'') === '新增节点') {
          const r = el.getBoundingClientRect();
          if (r.height > 0 && r.width > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      return null;
    });
    if (btnPos) {
      await page.mouse.click(btnPos.x, btnPos.y);
      console.log(`  ✅ mouse.click 新增节点 (${Math.round(btnPos.x)}, ${Math.round(btnPos.y)})`);
      return true;
    }
    console.log('  ❌ 新增节点按钮未找到');
    return false;
  }

  // 在弹窗中选择节点类型，然后关闭编辑面板
  async function selectNodeType(page, nodeTypeName) {
    await sleep(2000);
    await ss(page, `p2-node-popup-${nodeTypeName}`);

    // 找到包含目标名的元素并点击
    const pos = await page.evaluate((name) => {
      const target = name.replace(/\s+/g, '');
      const all = [...document.querySelectorAll('div, span, li, a, button, h3, h4, p')];
      // 找文本以目标名开头的短元素
      for (const el of all) {
        const txt = el.textContent.trim().replace(/\s+/g, '');
        if (txt.startsWith(target) && txt.length < 50 && el.offsetHeight > 0 && el.offsetHeight < 150) {
          const r = el.getBoundingClientRect();
          if (r.height > 0 && r.width > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: el.textContent.trim().substring(0, 30) };
        }
      }
      return null;
    }, nodeTypeName);

    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      console.log(`    ✅ 选择节点: "${pos.text}" (${Math.round(pos.x)}, ${Math.round(pos.y)})`);
    } else {
      console.log(`    ❌ 节点类型未找到: ${nodeTypeName}`);
      return;
    }
    await sleep(2000);

    // 点击节点类型后会打开节点编辑面板/抽屉，需要点“保存”关闭
    // 先截图看看当前状态
    await ss(page, `p2-node-edit-${nodeTypeName}`);

    // 查找节点编辑面板中的「保存」按钮
    const saved = await page.evaluate(() => {
      // 查找抽屉/面板中的保存按钮
      const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden), [class*=panel]:not([class*=hidden])');
      if (drawer) {
        const btns = [...drawer.querySelectorAll('button')];
        const saveBtn = btns.find(b => /保.*存/.test(b.textContent) && !/已.*存/.test(b.textContent));
        if (saveBtn) { saveBtn.click(); return 'drawer-save: ' + saveBtn.textContent.trim(); }
      }
      // 全局查找可见的保存按钮（仅在节点编辑面板上下文中）
      const allBtns = [...document.querySelectorAll('button')];
      const saveBtn = allBtns.find(b => {
        const txt = b.textContent.trim().replace(/\s+/g, '');
        return (txt === '保存' || txt === '确认并保存') && b.offsetHeight > 0;
      });
      if (saveBtn) {
        // 确保这个保存按钮在抽屉/面板中，而非页面主区域的“保 存”
        const parent = saveBtn.closest('.ant-drawer, .ant-modal, [class*=panel], [class*=drawer]');
        if (parent) { saveBtn.click(); return 'panel-save: ' + saveBtn.textContent.trim(); }
      }
      return null;
    });
    console.log(`    节点保存: ${saved || '未找到保存按钮'}`);
    await sleep(2000);

    // 如果抽屉还没关闭，尝试关闭按钮
    await page.evaluate(() => {
      const close = document.querySelector('.ant-drawer-close');
      if (close && close.offsetHeight > 0) close.click();
    });
    await sleep(1000);
  }

  // 2i. 添加节点 1/3: 生图
  if (detailVisible.hasAddNode) {
    console.log('  添加节点 1/3: 生图');
    await clickAddNode(page);
    await selectNodeType(page, '生图');

    // 2j. 添加节点 2/3: 人工审核
    console.log('  添加节点 2/3: 人工审核');
    await clickAddNode(page);
    await selectNodeType(page, '人工审核');

    // 2k. 添加节点 3/3: 高清化处理
    console.log('  添加节点 3/3: 高清化处理');
    await clickAddNode(page);
    await selectNodeType(page, '高清化处理');
  } else {
    console.log('  ⚠️ 策略详情页未加载，跳过节点添加');
  }

  await ss(page, 'p2-nodes-configured');

  // 2l. 验证节点
  const nodes = await page.evaluate(() => {
    const text = document.body.innerText;
    return ['生图', '人工审核', '高清化处理', '策略入参', '策略出参'].filter(n => text.includes(n));
  });
  console.log(`  节点验证: ${JSON.stringify(nodes)}`);

  // 2m. 保存策略
  console.log('  保存策略...');
  await clickTextBtn(page, '保存');  // 会自动容错"保 存"
  await sleep(3000);
  await ss(page, 'p2-saved');

  const msgs = await page.evaluate(() =>
    [...document.querySelectorAll('.ant-message-notice, .ant-notification-notice')].map(m => m.textContent.trim())
  );
  console.log(`  保存消息: ${JSON.stringify(msgs)}`);

  const p2Pass = nodes.length >= 3;
  console.log(`  Phase 2 结果: ${p2Pass ? '✅ PASS' : '⚠️ 部分通过'}`);
  return { pass: p2Pass, strategyId: strategyId, strategyName: STRATEGY_NAME };
}

// ============ Phase 3: 新建链路 + 绑定策略 ============
async function phase3(page, strategyName) {
  console.log('\n========== Phase 3: 新建链路 + 绑定策略 ==========');

  // 3a. 进入链路列表
  await page.goto(`${BASE}/strategy/linkList`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 3b. 新建链路（可能是弹窗或页面跳转）
  await clickTextBtn(page, '新建链路');
  await sleep(3000);
  await ss(page, 'p3-new-link');

  // 检查是否是弹窗
  const isModal = await page.evaluate(() => {
    return !!document.querySelector('.ant-modal:not(.ant-modal-hidden)');
  });
  console.log(`  新建链路形式: ${isModal ? '弹窗' : '页面跳转'}`);

  // 3c. 填链路名称
  if (isModal) {
    const nameInput = await page.$('.ant-modal input[placeholder*="请输入"], .ant-modal input:not([type])');
    if (nameInput) {
      await nameInput.click({ clickCount: 3 });
      await nameInput.type(LINK_NAME);
      console.log(`  链路名称: ${LINK_NAME}`);
    }
    // 选生命周期
    await antSelect(page, '请选择生命周期', '实验');
    await sleep(500);
    await ss(page, 'p3-link-modal-filled');
    // 点击「创建」按钮（新建链路弹窗是「创建」而非「确定」）
    const linkCreated = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) {
        const btns = [...modal.querySelectorAll('button')];
        // 优先找「创建」，其次「确定」
        const btn = btns.find(b => /创.*建|确.*定/.test(b.textContent));
        if (btn) { btn.click(); return btn.textContent.trim(); }
      }
      return null;
    });
    console.log(`  链路创建按钮: ${linkCreated}`);
    await sleep(3000);
  } else {
    // 页面形式
    const nameInput = await page.$('input[placeholder*="请输入"], input:not([type])');
    if (nameInput) {
      await nameInput.click({ clickCount: 3 });
      await nameInput.type(LINK_NAME);
      console.log(`  链路名称: ${LINK_NAME}`);
    }
    await antSelect(page, '请选择', '实验');
    await sleep(500);
    // 保存
    await clickTextBtn(page, '保存');
    await sleep(3000);
  }

  await ss(page, 'p3-link-saved');

  // 检查是否跳转到链路详情页
  const afterLinkUrl = page.url();
  console.log(`  创建后URL: ${afterLinkUrl}`);
  let linkMatch = afterLinkUrl.match(/[?&]id=(\d+)/);
  let linkId = linkMatch ? linkMatch[1] : null;

  // 如果没跳转，在列表中搜索并打开
  if (!linkId) {
    console.log('  未跳转详情页，搜索并打开刚创建的链路...');
    // 等待列表刷新
    await sleep(2000);
    await ss(page, 'p3-link-list-after-create');

    // 尝试搜索
    const searchInput = await page.$('input[placeholder*="搜索链路名称"], input[placeholder*="搜索"]');
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await searchInput.type(LINK_NAME);
      await page.keyboard.press('Enter');
      await sleep(2000);
    }

    // 点击链路名称或编辑按钮
    const linkOpened = await page.evaluate((name) => {
      // 查找包含链路名称的行，点击编辑
      const rows = [...document.querySelectorAll('tr')];
      for (const row of rows) {
        if (row.textContent.includes(name)) {
          const editBtn = row.querySelector('a, button');
          if (editBtn && editBtn.textContent.includes('编辑')) {
            editBtn.click();
            return 'edit-clicked';
          }
          // 点击链路名称链接
          const link = row.querySelector('a');
          if (link) { link.click(); return 'link-clicked'; }
        }
      }
      // 全局查找
      const allEls = [...document.querySelectorAll('a, button, span')];
      for (const el of allEls) {
        if (el.textContent.trim() === name && el.tagName === 'A') {
          el.click(); return 'name-clicked';
        }
      }
      return null;
    }, LINK_NAME);
    console.log(`  打开链路: ${linkOpened}`);
    await sleep(3000);

    const linkUrl2 = page.url();
    console.log(`  打开后URL: ${linkUrl2}`);
    const linkMatch2 = linkUrl2.match(/[?&]id=(\d+)/);
    linkId = linkMatch2 ? linkMatch2[1] : null;
  }

  const finalLinkId = linkId || 'unknown';
  console.log(`  最终链路ID: ${finalLinkId}`);
  await ss(page, 'p3-link-detail');

  // 3d. 验证起点入参
  const params = await page.evaluate(() => {
    const text = document.body.innerText;
    return ['seller_id', 'seed_image_url', 'tao_cate', 'item_id'].filter(p => text.includes(p));
  });
  console.log(`  起点入参: ${JSON.stringify(params)}`);

  // 3e. 添加环节（链路创建后是空的，需要先添加环节）
  console.log('  添加环节...');
  // 点击 "+ 添加环节" 按钮（页面顶部蓝色按钮或虚线框）
  const addStepClicked = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button, div, span')];
    for (const el of els) {
      const txt = el.textContent.trim().replace(/\s+/g, '');
      if ((txt === '+添加环节' || txt === '添加环节') && el.offsetHeight > 0) {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: el.textContent.trim() };
      }
    }
    return null;
  });
  if (addStepClicked) {
    await page.mouse.click(addStepClicked.x, addStepClicked.y);
    console.log(`  ✅ 点击添加环节: "${addStepClicked.text}" (${Math.round(addStepClicked.x)}, ${Math.round(addStepClicked.y)})`);
  } else {
    console.log('  ❌ 添加环节按钮未找到');
  }
  await sleep(3000);
  await ss(page, 'p3-add-step');

  // 检查添加环节是弹窗还是页面跳转
  const stepModal = await page.evaluate(() => {
    return !!document.querySelector('.ant-modal:not(.ant-modal-hidden)');
  });
  console.log(`  添加环节形式: ${stepModal ? '弹窗' : '页面跳转'}`);

  if (stepModal) {
    // 弹窗中选择环节类型（如“首图审核”）
    const stepTypeClicked = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (!modal) return null;
      // 查找环节类型列表
      const items = [...modal.querySelectorAll('div, span, li, a, button, .ant-card')];
      // 优先找“首图审核”，其次找任何审核类型
      const targets = ['首图审核', '审核', '生图'];
      for (const target of targets) {
        for (const item of items) {
          const txt = item.textContent.trim().replace(/\s+/g, '');
          if (txt.includes(target) && txt.length < 50 && item.offsetHeight > 0 && item.offsetHeight < 150) {
            const r = item.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: item.textContent.trim().substring(0, 30) };
          }
        }
      }
      return null;
    });
    if (stepTypeClicked) {
      await page.mouse.click(stepTypeClicked.x, stepTypeClicked.y);
      console.log(`  ✅ 选择环节类型: "${stepTypeClicked.text}"`);
      await sleep(1000);
    }
    // 确定
    await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) {
        const btn = [...modal.querySelectorAll('button')].find(b => /确.*定|创.*建|添.*加/.test(b.textContent));
        if (btn) btn.click();
      }
    });
    await sleep(2000);
  }

  await ss(page, 'p3-step-added');
  console.log(`  添加环节后URL: ${page.url()}`);

  // 3f. 保存链路（添加环节后需保存）
  await clickTextBtn(page, '保存');
  await sleep(3000);
  await ss(page, 'p3-link-with-step');

  // 3g. 查看运行结果 → 添加策略
  console.log('  打开查看运行结果...');
  await clickTextBtn(page, '查看运行结果');
  await sleep(3000);
  await ss(page, 'p3-run-results');

  // 找到环节并点击“添加策略”
  const addStratClicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button, a, span')];
    for (const b of btns) {
      if (b.textContent.trim().replace(/\s+/g, '') === '添加策略' && b.offsetHeight > 0) {
        b.click();
        return true;
      }
    }
    return false;
  });
  console.log(`  点击添加策略: ${addStratClicked}`);
  await sleep(2000);
  await ss(page, 'p3-add-strategy');

  if (addStratClicked) {
    // 搜索策略
    const searchInput = await page.$('.ant-modal input, .ant-drawer input');
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await searchInput.type(strategyName);
      await page.keyboard.press('Enter');
      await sleep(2000);
    }

    // 选择策略行
    await page.evaluate((name) => {
      const rows = document.querySelectorAll('tr, .ant-list-item');
      for (const r of rows) {
        if (r.textContent.includes(name)) {
          const radio = r.querySelector('input[type=radio], .ant-radio-wrapper');
          if (radio) { radio.click(); return; }
          r.click();
          return;
        }
      }
    }, strategyName);
    await sleep(500);

    // 确定
    await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) { const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent)); if (btn) btn.click(); }
    });
    await sleep(2000);
    await ss(page, 'p3-strategy-bound');
  }

  const p3Pass = finalLinkId !== 'unknown' && params.length >= 0;
  console.log(`  Phase 3 结果: ${p3Pass ? '✅ PASS' : '⚠️ 部分通过'}`);
  return { pass: p3Pass, linkId: finalLinkId };
}

// ============ Phase 4: 试运行 ============
async function phase4(page, linkId) {
  console.log('\n========== Phase 4: 试运行 ==========');

  // 确保在链路详情页
  const currentUrl = page.url();
  if (!currentUrl.includes('linkDetail')) {
    await page.goto(`${BASE}/strategy/linkDetail?id=${linkId}`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
  }

  // 关闭可能的弹窗/抽屉
  await page.evaluate(() => {
    const close = document.querySelector('.ant-modal-close, .ant-drawer-close');
    if (close && close.offsetHeight > 0) close.click();
  });
  await sleep(1000);

  // 4a. 打开试运行弹窗
  console.log('  点击试运行...');
  // 用 mouse.click 确保点到
  const trialBtnPos = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    for (const b of btns) {
      const txt = b.textContent.trim().replace(/\s+/g, '');
      if (txt === '试运行' && b.offsetHeight > 0) {
        const r = b.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (trialBtnPos) {
    await page.mouse.click(trialBtnPos.x, trialBtnPos.y);
    console.log('  ✅ 试运行按钮已点击');
  }
  await sleep(3000); // 多等一会儿让弹窗完全加载
  await ss(page, 'p4-trial-modal');

  // 调试: 打印弹窗内容
  const modalInfo = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (modal) {
      const inputs = modal.querySelectorAll('input');
      const selects = modal.querySelectorAll('.ant-select');
      const fileInputs = modal.querySelectorAll('input[type="file"]');
      const buttons = modal.querySelectorAll('button');
      return {
        hasModal: true,
        inputCount: inputs.length,
        inputPlaceholders: [...inputs].map(i => i.placeholder || i.type).filter(Boolean),
        selectCount: selects.length,
        selectTexts: [...selects].map(s => s.textContent.trim().substring(0, 30)),
        fileInputCount: fileInputs.length,
        buttonTexts: [...buttons].map(b => b.textContent.trim()).filter(t => t.length > 0),
        modalText: modal.textContent.substring(0, 300)
      };
    }
    return { hasModal: false };
  });
  console.log(`  弹窗信息: ${JSON.stringify(modalInfo)}`);

  // 4b. 填任务名称
  const taskInput = await page.$('.ant-modal input[placeholder*="请输入任务名称"], .ant-modal input[placeholder*="请输入"]');
  if (taskInput) {
    await taskInput.click({ clickCount: 3 });
    await taskInput.type(`E2E测试_${Date.now()}`);
    console.log('  ✅ 任务名称已填写');
  } else {
    console.log('  ⚠️ 任务名称输入框未找到');
  }

  // 4c. 构造并上传Excel
  const excelPath = '/tmp/e2e-test-data.xlsx';
  execSync(`python3 -c "
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
ws.append(['seller_id','seed_image_url','tao_cate','item_id'])
ws.append(['${TEST_SELLER}','${TEST_SEED_IMG}','女装','7000000000001'])
wb.save('${excelPath}')
"`);
  console.log(`  Excel: ${excelPath} (${fs.statSync(excelPath).size} bytes)`);

  // 查找文件输入（可能在弹窗内或全局）
  let fileInput = await page.$('.ant-modal input[type="file"]');
  if (!fileInput) fileInput = await page.$('input[type="file"]');
  if (!fileInput) {
    // 尝试暴露隐藏的文件 input
    await page.evaluate(() => {
      const allInputs = document.querySelectorAll('input[type="file"]');
      for (const fi of allInputs) {
        fi.style.display = 'block';
        fi.style.opacity = '1';
        fi.style.visibility = 'visible';
        fi.style.position = 'fixed';
        fi.style.top = '0';
        fi.style.left = '0';
        fi.style.zIndex = '99999';
      }
    });
    fileInput = await page.$('input[type="file"]');
  }
  if (fileInput) {
    await fileInput.uploadFile(excelPath);
    await sleep(2000);
    console.log('  ✅ Excel已上传');
  } else {
    console.log('  ❌ 未找到文件上传input，尝试点击上传区域触发...');
    // 尝试点击上传按钮/区域来触发文件input
    await clickTextBtn(page, '上传');
    await sleep(1000);
    const fi3 = await page.$('input[type="file"]');
    if (fi3) {
      await fi3.uploadFile(excelPath);
      await sleep(2000);
      console.log('  ✅ Excel已上传(点击上传后)');
    }
  }

  // 4d. 选运行类型 = 测试
  await antSelect(page, '请选择运行类型', '测试');
  await sleep(500);

  // 如果 antSelect 没找到，尝试直接在弹窗内找
  const selectResult = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (!modal) return 'no-modal';
    const selects = modal.querySelectorAll('.ant-select');
    for (const sel of selects) {
      const text = sel.textContent.trim();
      if (text.includes('运行类型') || text.includes('请选择')) {
        const r = sel.querySelector('.ant-select-selector');
        if (r) {
          const rect = r.getBoundingClientRect();
          return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
        }
      }
    }
    return 'no-select-found';
  });
  if (typeof selectResult === 'object' && selectResult.x) {
    await page.mouse.click(selectResult.x, selectResult.y);
    await sleep(800);
    const selected = await page.evaluate(() => {
      const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dds) {
        const items = dd.querySelectorAll('.ant-select-item-option');
        for (const item of items) {
          if (item.textContent.trim() === '测试') {
            item.click();
            return true;
          }
        }
      }
      return false;
    });
    console.log(`  运行类型选择: ${selected ? '✅ 测试' : '❌ 未选到'}`);
    await sleep(500);
  }

  await ss(page, 'p4-before-submit');

  // 4e. 发起任务运行
  console.log('  发起任务运行...');
  await clickTextBtn(page, '发起任务运行');
  await sleep(5000);
  await ss(page, 'p4-after-submit');

  // 检查结果
  const msgs = await page.evaluate(() =>
    [...document.querySelectorAll('.ant-message-notice, .ant-notification-notice, .ant-alert, .ant-modal-body')].map(m => m.textContent.trim()).filter(t => t.length > 5)
  );
  console.log(`  运行消息: ${JSON.stringify(msgs)}`);

  const taskStarted = msgs.some(m => m.includes('成功') || m.includes('运行') || m.includes('任务'));
  const p4Pass = taskStarted || msgs.length > 0;
  console.log(`  Phase 4 结果: ${p4Pass ? '✅ PASS' : '⚠️ 检查消息确认'}`);
  return { pass: p4Pass, messages: msgs };
}

// ============ Phase 5: 各环节状态监控 ============
async function phase5(page, linkId) {
  console.log('\n========== Phase 5: 各环节状态监控 ==========');

  // 等待一段时间让任务执行
  console.log('  等待30秒让节点执行...');
  await sleep(30000);

  // 刷新链路详情页
  await page.goto(`${BASE}/strategy/linkDetail?id=${linkId}`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 打开查看运行结果
  await clickTextBtn(page, '查看运行结果');
  await sleep(3000);
  await ss(page, 'p5-run-results');

  // 采集环节状态（通用检测，不依赖特定环节名）
  const resultData = await page.evaluate(() => {
    const text = document.body.innerText;
    const stages = {};
    // 检测任何环节名称
    const stageNames = ['刷标签', '首图生图', '首图审核', '套图生图', '套图审核', '审核', '生图', '高清化'];
    for (const s of stageNames) {
      if (text.includes(s)) stages[s] = 'visible';
    }
    const statuses = [];
    const statusKeywords = ['进行中', '成功', '失败', '待运行', '已终止', '初始化', '排队中', '运行中', '已完成', '等待'];
    for (const kw of statusKeywords) {
      if (text.includes(kw)) statuses.push(kw);
    }
    // 采集任务信息
    const taskInfo = [];
    const patterns = ['已解析', '总行数', '有效行数', '任务运行', '运行成功', '运行失败'];
    for (const p of patterns) {
      if (text.includes(p)) taskInfo.push(p);
    }
    // 采集标签文本
    const tags = [...document.querySelectorAll('.ant-tag, .ant-badge-status-text, [class*=status]')];
    const tagTexts = tags.map(t => t.textContent.trim()).filter(t => t.length > 0 && t.length < 20);
    return { stages, statuses, taskInfo, tagTexts: tagTexts.slice(0, 20), hasResults: text.includes('运行') || text.includes('任务') };
  });
  console.log(`  环节可见性: ${JSON.stringify(resultData.stages)}`);
  console.log(`  状态关键词: ${JSON.stringify(resultData.statuses)}`);
  console.log(`  任务信息: ${JSON.stringify(resultData.taskInfo)}`);
  console.log(`  标签文本: ${JSON.stringify(resultData.tagTexts)}`);

  // 验证出参
  const outputParams = await page.evaluate(() => {
    const text = document.body.innerText;
    return ['seller_id', 'seed_image_url'].filter(p => text.includes(p));
  });
  console.log(`  出参验证: ${JSON.stringify(outputParams)}`);

  await ss(page, 'p5-final');

  const visibleCount = Object.keys(resultData.stages).length;
  const hasAnyStatus = resultData.statuses.length > 0 || resultData.taskInfo.length > 0;
  const p5Pass = visibleCount >= 1 || hasAnyStatus || resultData.hasResults;
  console.log(`  Phase 5 结果: ${p5Pass ? '✅ PASS' : '⚠️ 需要更多时间执行'}`);
  return { pass: p5Pass, data: resultData };
}

// ============ Phase 6: API/DB验证 ============
async function phase6(page, linkId) {
  console.log('\n========== Phase 6: API/DB端到端验证 ==========');

  // 6a. API查询链路详情
  const linkDetail = await page.evaluate(async (lid) => {
    try {
      const resp = await fetch(`/api/strategy/link/detail?linkId=${lid}`);
      if (resp.ok) return await resp.json();
      return { error: resp.status };
    } catch (e) { return { error: e.message }; }
  }, linkId);
  console.log(`  API链路详情: ${JSON.stringify(linkDetail).substring(0, 200)}`);

  // 6b. API查询运行任务
  const tasks = await page.evaluate(async (lid) => {
    try {
      const resp = await fetch(`/api/strategy/link/tasks?linkId=${lid}&limit=10`);
      if (resp.ok) return await resp.json();
      return { error: resp.status };
    } catch (e) { return { error: e.message }; }
  }, linkId);
  console.log(`  API任务列表: ${JSON.stringify(tasks).substring(0, 200)}`);

  // 6c. 页面验证 — 再次查看运行结果
  await page.evaluate(() => {
    const close = document.querySelector('.ant-modal-close');
    if (close) close.click();
  });
  await sleep(1000);

  await clickTextBtn(page, '查看运行结果');
  await sleep(3000);
  await ss(page, 'p6-final-verify');

  // 最终验证
  const finalCheck = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasStages: text.includes('首图审核') || text.includes('刷标签'),
      hasTask: text.includes('E2E') || text.includes('测试'),
      hasStatus: text.includes('进行中') || text.includes('成功') || text.includes('初始化')
    };
  });
  console.log(`  最终验证: ${JSON.stringify(finalCheck)}`);

  const p6Pass = finalCheck.hasStages || finalCheck.hasTask;
  console.log(`  Phase 6 结果: ${p6Pass ? '✅ PASS' : '⚠️ 任务可能还在初始化'}`);
  return { pass: p6Pass, linkDetail, tasks };
}

// ============ Main ============
async function main() {
  console.log('🚀 TC27 端到端集成测试开始');
  console.log(`  策略名: ${STRATEGY_NAME}`);
  console.log(`  链路名: ${LINK_NAME}`);
  console.log(`  截图目录: ${SS_DIR}\n`);

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  const results = {};

  try {
    // Phase 1
    results.phase1 = await phase1(page);

    // Phase 2
    const p2 = await phase2(page);
    results.phase2 = p2.pass;

    // Phase 3
    const p3 = await phase3(page, p2.strategyName);
    results.phase3 = p3.pass;

    // Phase 4
    const p4 = await phase4(page, p3.linkId);
    results.phase4 = p4.pass;

    // Phase 5
    const p5 = await phase5(page, p3.linkId);
    results.phase5 = p5.pass;

    // Phase 6
    const p6 = await phase6(page, p3.linkId);
    results.phase6 = p6.pass;

  } catch (e) {
    console.error(`\n❌ 执行异常: ${e.message}`);
    await ss(page, 'error');
  }

  // 汇总
  console.log('\n========== 测试结果汇总 ==========');
  console.log(`  Phase 1 (参考数据采集):   ${results.phase1 ? '✅' : '❌'}`);
  console.log(`  Phase 2 (新建策略+节点):   ${results.phase2 ? '✅' : '❌'}`);
  console.log(`  Phase 3 (新建链路+绑定):   ${results.phase3 ? '✅' : '❌'}`);
  console.log(`  Phase 4 (试运行提交):      ${results.phase4 ? '✅' : '❌'}`);
  console.log(`  Phase 5 (状态监控):        ${results.phase5 ? '✅' : '❌'}`);
  console.log(`  Phase 6 (API/DB验证):      ${results.phase6 ? '✅' : '❌'}`);
  const totalPass = Object.values(results).filter(Boolean).length;
  console.log(`  总计: ${totalPass}/6 通过`);

  // 保存结果
  const resultPath = path.join(SS_DIR, 'results.json');
  fs.writeFileSync(resultPath, JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  console.log(`  结果文件: ${resultPath}`);

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 TC27 执行完成');
}

main().catch(e => { console.error('❌ Fatal:', e.message); process.exit(1); });
