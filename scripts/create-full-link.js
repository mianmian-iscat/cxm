#!/usr/bin/env node
/**
 * 参照链路20180结构创建完整链路
 * 结构: 刷标签 → 首图生图 → 首图审核 → 套图生图 → 套图审核
 * 入参: seller_id, seed_image_url, tao_cate, item_id
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'full-link');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const TS = String(Date.now()).slice(-6);

// 5个策略（对应5个环节）
const STRATEGIES = [
  { name: `刷标签策略_${TS}`, env: '视觉', nodes: ['季节标签', '产业标签'] },
  { name: `首图生图策略_${TS}`, env: '视觉', nodes: ['生图', '高清化处理'] },
  { name: `首图审核策略_${TS}`, env: '视觉', nodes: ['人工审核'] },
  { name: `套图生图策略_${TS}`, env: '视觉', nodes: ['Map生图', '高清化处理'] },
  { name: `套图审核策略_${TS}`, env: '视觉', nodes: ['人工审核', '选片'] },
];
const LINK_NAME = `完整主图链路_${TS}`;

const STAGES = ['刷标签', '首图生图', '首图审核', '套图生图', '套图审核'];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${name}.jpg`);
  return fp;
}

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
  if (!box) return false;
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

async function clickTextBtn(page, text) {
  const clicked = await page.evaluate((t) => {
    let els = [...document.querySelectorAll('button, a, span, div')];
    for (const el of els) {
      const txt = el.textContent.trim().replace(/\s+/g, '');
      const target = t.replace(/\s+/g, '');
      if (txt === target && el.offsetHeight > 0) { el.click(); return el.tagName + ': ' + el.textContent.trim(); }
    }
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

// 点击新增节点 → 选择类型 → 保存编辑抽屉
async function addNode(page, nodeTypeName) {
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

  // 选择节点类型（startsWith 匹配）
  const pos = await page.evaluate((name) => {
    const target = name.replace(/\s+/g, '');
    const all = [...document.querySelectorAll('div, span, li, a, button, h3, h4, p')];
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
    console.log(`    ✅ 选择: "${pos.text}"`);
  } else {
    console.log(`    ❌ 节点类型未找到: ${nodeTypeName}`);
    return false;
  }
  await sleep(2000);

  // 保存编辑抽屉
  const saved = await page.evaluate(() => {
    const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
    if (drawer) {
      const btns = [...drawer.querySelectorAll('button')];
      const saveBtn = btns.find(b => /保.*存/.test(b.textContent));
      if (saveBtn) { saveBtn.click(); return true; }
    }
    return false;
  });
  if (saved) console.log(`    ✅ 抽屉保存`);
  await sleep(1500);

  // 关闭抽屉
  await page.evaluate(() => {
    const close = document.querySelector('.ant-drawer-close');
    if (close && close.offsetHeight > 0) close.click();
  });
  await sleep(1000);
  return true;
}

// ============ 创建策略 ============
async function createStrategy(page, cfg) {
  console.log(`\n  --- 创建策略: ${cfg.name} ---`);
  
  // 进入策略列表
  await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 新建策略弹窗
  await clickTextBtn(page, '新建策略');
  await sleep(2000);

  // 填名称
  const nameInput = await page.$('.ant-modal input[placeholder*="请输入策略名称"], .ant-modal input[placeholder*="请输入"]');
  if (nameInput) {
    await nameInput.click({ clickCount: 3 });
    await nameInput.type(cfg.name);
  }

  // 选环节
  await antSelect(page, '请选择环节', cfg.env);
  await sleep(300);
  // 选生命周期
  await antSelect(page, '请选择生命周期', '实验');
  await sleep(300);

  // 确定
  await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (modal) {
      const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent));
      if (btn) btn.click();
    }
  });
  await sleep(3000);

  // 提取策略ID
  const url = page.url();
  const idMatch = url.match(/(?:detail|strategyId)[/=](\d+)/) || url.match(/[?&]id=(\d+)/);
  const strategyId = idMatch ? idMatch[1] : 'unknown';
  console.log(`  策略ID: ${strategyId}`);

  // 添加节点
  for (const nodeType of cfg.nodes) {
    console.log(`  添加节点: ${nodeType}`);
    await addNode(page, nodeType);
  }

  // 保存策略
  await clickTextBtn(page, '保存');
  await sleep(2000);

  const msgs = await page.evaluate(() =>
    [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
  );
  console.log(`  保存消息: ${JSON.stringify(msgs)}`);

  return { id: strategyId, name: cfg.name };
}

// ============ 创建链路 ============
async function createLink(page) {
  console.log(`\n  --- 创建链路: ${LINK_NAME} ---`);
  
  await page.goto(`${BASE}/strategy/linkList`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  await clickTextBtn(page, '新建链路');
  await sleep(2000);

  // 弹窗填名称
  const nameInput = await page.$('.ant-modal input[placeholder*="请输入"], .ant-modal input:not([type])');
  if (nameInput) {
    await nameInput.click({ clickCount: 3 });
    await nameInput.type(LINK_NAME);
  }
  await antSelect(page, '请选择生命周期', '实验');
  await sleep(300);

  // 点击「创建」
  await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
    if (modal) {
      const btn = [...modal.querySelectorAll('button')].find(b => /创.*建|确.*定/.test(b.textContent));
      if (btn) btn.click();
    }
  });
  await sleep(3000);

  const url = page.url();
  const idMatch = url.match(/[?&]id=(\d+)/);
  const linkId = idMatch ? idMatch[1] : 'unknown';
  console.log(`  链路ID: ${linkId}`);
  await ss(page, 'link-created');
  return linkId;
}

// ============ 添加环节 ============
async function addStages(page, linkId) {
  console.log(`\n  --- 添加环节 ---`);
  
  for (let i = 0; i < STAGES.length; i++) {
    const stageName = STAGES[i];
    console.log(`  添加环节 ${i + 1}/${STAGES.length}: ${stageName}`);

    // 点击 "+ 添加环节"
    const btnPos = await page.evaluate(() => {
      const els = [...document.querySelectorAll('button, div, span')];
      for (const el of els) {
        const t = el.textContent.trim().replace(/\s+/g, '');
        if (t === '+添加环节' || t === '添加环节') {
          const r = el.getBoundingClientRect();
          if (r.height > 0 && r.width > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      return null;
    });
    if (btnPos) {
      await page.mouse.click(btnPos.x, btnPos.y);
      console.log(`    ✅ 点击添加环节`);
    }
    await sleep(3000);
    await ss(page, `stage-${i + 1}-after-click`);

    // 检查是否是弹窗/页面
    const stageResult = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) return { type: 'modal', text: modal.textContent.substring(0, 200) };
      const drawer = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
      if (drawer) return { type: 'drawer', text: drawer.textContent.substring(0, 200) };
      return { type: 'page', url: location.href };
    });
    console.log(`    形式: ${JSON.stringify(stageResult)}`);

    if (stageResult.type === 'modal') {
      // 弹窗中选择环节类型
      const stageClicked = await page.evaluate((name) => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return null;
        const items = [...modal.querySelectorAll('div, span, li, a, button, .ant-card')];
        for (const item of items) {
          const txt = item.textContent.trim().replace(/\s+/g, '');
          if (txt.includes(name.replace(/\s+/g, '')) && item.offsetHeight > 0 && item.offsetHeight < 150) {
            const r = item.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
        return null;
      }, stageName);
      if (stageClicked) {
        await page.mouse.click(stageClicked.x, stageClicked.y);
        console.log(`    ✅ 选择环节: ${stageName}`);
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
    } else if (stageResult.type === 'page') {
      // 页面跳转 — 可能需要配置后返回
      // 检查是否有环节选择下拉
      await antSelect(page, '请选择', stageName);
      await sleep(500);
      await clickTextBtn(page, '保存');
      await sleep(2000);
      // 返回链路详情页
      if (!page.url().includes(`linkDetail?id=${linkId}`)) {
        await page.goto(`${BASE}/strategy/linkDetail?id=${linkId}`, { waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(3000);
      }
    }
    await ss(page, `stage-${i + 1}-added`);
  }

  // 保存链路
  await clickTextBtn(page, '保存');
  await sleep(3000);
  await ss(page, 'all-stages-added');
}

// ============ 绑定策略 ============
async function bindStrategies(page, linkId, strategies) {
  console.log(`\n  --- 绑定策略 ---`);

  // 打开查看运行结果
  await clickTextBtn(page, '查看运行结果');
  await sleep(3000);
  await ss(page, 'run-results-before-bind');

  // 打印弹窗/页面内容帮助定位
  const resultInfo = await page.evaluate(() => {
    const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden), .ant-drawer:not(.ant-drawer-hidden)');
    if (modal) return modal.textContent.substring(0, 500);
    return document.body.innerText.substring(0, 500);
  });
  console.log(`  运行结果内容: ${resultInfo.substring(0, 200)}`);

  // 对每个环节尝试添加策略
  for (let i = 0; i < strategies.length; i++) {
    const strat = strategies[i];
    console.log(`  绑定策略 ${i + 1}: ${strat.name}`);

    // 点击 "添加策略"
    const addClicked = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button, a, span')];
      for (const b of btns) {
        if (b.textContent.trim().replace(/\s+/g, '') === '添加策略' && b.offsetHeight > 0) {
          b.click();
          return true;
        }
      }
      return false;
    });
    if (!addClicked) {
      console.log(`    ⚠️ 添加策略按钮未找到，可能没有更多环节`);
      break;
    }
    await sleep(2000);

    // 搜索策略
    const searchInput = await page.$('.ant-modal input, .ant-drawer input');
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await searchInput.type(strat.name);
      await page.keyboard.press('Enter');
      await sleep(2000);
    }

    // 选择策略行
    await page.evaluate((name) => {
      const rows = document.querySelectorAll('tr, .ant-list-item, .ant-radio-wrapper');
      for (const r of rows) {
        if (r.textContent.includes(name)) {
          const radio = r.querySelector('input[type=radio], .ant-radio-wrapper, .ant-radio');
          if (radio) { radio.click(); return; }
          r.click();
          return;
        }
      }
    }, strat.name);
    await sleep(500);

    // 确定
    await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (modal) {
        const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent));
        if (btn) btn.click();
      }
    });
    await sleep(2000);
    console.log(`    ✅ 已绑定`);
  }
  await ss(page, 'strategies-bound');
}

// ============ 试运行 ============
async function trialRun(page, linkId) {
  console.log(`\n  --- 试运行 ---`);

  // 关闭弹窗
  await page.evaluate(() => {
    const close = document.querySelector('.ant-modal-close, .ant-drawer-close');
    if (close && close.offsetHeight > 0) close.click();
  });
  await sleep(1000);

  // 点击试运行
  const trialBtnPos = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    for (const b of btns) {
      if (b.textContent.trim().replace(/\s+/g, '') === '试运行' && b.offsetHeight > 0) {
        const r = b.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (trialBtnPos) {
    await page.mouse.click(trialBtnPos.x, trialBtnPos.y);
    console.log('  ✅ 试运行');
  }
  await sleep(3000);
  await ss(page, 'trial-modal');

  // 填任务名称
  const taskInput = await page.$('.ant-modal input[placeholder*="任务名称"], .ant-modal input[placeholder*="请输入"]');
  if (taskInput) {
    await taskInput.click({ clickCount: 3 });
    await taskInput.type(`完整链路测试_${TS}`);
    console.log('  ✅ 任务名称');
  }

  // 上传Excel
  const excelPath = '/tmp/full-link-test.xlsx';
  execSync(`python3 -c "
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
ws.append(['seller_id','seed_image_url','tao_cate','item_id'])
ws.append(['2219635649153','https://img.alicdn.com/imgextra/i1/O1CN01Z5paLz1O4SsHjYjJN_!!6000000001652-0-tps-800-800.jpg','女装','7000000000001'])
wb.save('${excelPath}')
"`);

  let fileInput = await page.$('input[type="file"]');
  if (!fileInput) {
    await page.evaluate(() => {
      document.querySelectorAll('input[type="file"]').forEach(fi => {
        fi.style.display = 'block'; fi.style.opacity = '1'; fi.style.visibility = 'visible';
        fi.style.position = 'fixed'; fi.style.top = '0'; fi.style.left = '0'; fi.style.zIndex = '99999';
      });
    });
    fileInput = await page.$('input[type="file"]');
  }
  if (fileInput) {
    await fileInput.uploadFile(excelPath);
    await sleep(2000);
    console.log('  ✅ Excel已上传');
  }

  // 选运行类型 = 测试
  await antSelect(page, '请选择运行类型', '测试');
  await sleep(500);

  // 发起运行
  await clickTextBtn(page, '发起任务运行');
  await sleep(5000);
  await ss(page, 'trial-submitted');

  const msgs = await page.evaluate(() =>
    [...document.querySelectorAll('.ant-message-notice, .ant-modal-body')].map(m => m.textContent.trim()).filter(t => t.length > 5)
  );
  console.log(`  运行消息: ${JSON.stringify(msgs)}`);
  return msgs;
}

// ============ Main ============
async function main() {
  console.log('🚀 创建完整链路');
  console.log(`  链路名: ${LINK_NAME}`);
  console.log(`  策略: ${STRATEGIES.map(s => s.name).join(', ')}\n`);

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  try {
    // Step 1: 创建5个策略
    console.log('========== Step 1: 创建策略 ==========');
    const strategies = [];
    for (const cfg of STRATEGIES) {
      const s = await createStrategy(page, cfg);
      strategies.push(s);
    }
    console.log(`  策略汇总: ${strategies.map(s => `${s.name}(id=${s.id})`).join(', ')}`);

    // Step 2: 创建链路
    console.log('\n========== Step 2: 创建链路 ==========');
    const linkId = await createLink(page);
    
    // Step 3: 添加环节
    console.log('\n========== Step 3: 添加环节 ==========');
    await addStages(page, linkId);

    // Step 4: 绑定策略
    console.log('\n========== Step 4: 绑定策略 ==========');
    await bindStrategies(page, linkId, strategies);

    // Step 5: 试运行
    console.log('\n========== Step 5: 试运行 ==========');
    const msgs = await trialRun(page, linkId);

    // 汇总
    console.log('\n========== 汇总 ==========');
    console.log(`  链路ID: ${linkId}`);
    console.log(`  链路URL: ${BASE}/strategy/linkDetail?id=${linkId}`);
    console.log(`  策略: ${strategies.length}个`);
    console.log(`  环节: ${STAGES.length}个`);
    console.log(`  试运行: ${msgs.length > 0 ? '已提交' : '待确认'}`);

    // 保存结果
    const resultPath = path.join(SS_DIR, 'result.json');
    fs.writeFileSync(resultPath, JSON.stringify({
      ts: new Date().toISOString(),
      linkId, linkName: LINK_NAME, strategies, stages: STAGES, messages: msgs
    }, null, 2));
    console.log(`  结果: ${resultPath}`);

  } catch (e) {
    console.error(`\n❌ 异常: ${e.message}`);
    await ss(page, 'error');
  }

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('❌ Fatal:', e.message); process.exit(1); });
