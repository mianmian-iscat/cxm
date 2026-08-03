#!/usr/bin/env node
/**
 * 探查 F88 策略平台所有节点类型及其表单字段
 *
 * 产出：/tmp/node-type-report.json —— 每种节点的表单字段清单
 *
 * 用法：node scripts/explore-node-types.js
 * 前置：Chrome --remote-debugging-port=9222 已启动且已登录 F88 预发
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'explore-nodes');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const TS = String(Date.now()).slice(-6);

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  screenshot: ${name}.jpg`);
  return fp;
}

// 获取可见的大 modal（按标题匹配）
function getModalSelector(title) {
  return `(() => {
    const modals = document.querySelectorAll('.ant-modal');
    for (const m of modals) {
      if (m.classList.contains('ant-modal-hidden')) continue;
      const r = m.getBoundingClientRect();
      if (r.width < 200) continue;
      ${title ? `const t = m.querySelector('.ant-modal-title'); if (!t || !t.textContent.includes('${title}')) continue;` : ''}
      return m;
    }
    return null;
  })()`;
}
const GET_NEW_STRATEGY_MODAL = getModalSelector('新建策略');
const GET_ANY_LARGE_MODAL = getModalSelector('');

async function main() {
  console.log('=== F88 节点类型探查 ===\n');

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  console.log(`  浏览器页面数: ${pages.length}`);
  for (const p of pages) {
    console.log(`    ${p.url().substring(0, 80)}`);
  }

  // 找到 F88 页面
  let page = pages.find(p => p.url().includes('pre-aifashion-xiaoer'));
  if (!page) page = pages[0];
  console.log(`  使用页面: ${page.url().substring(0, 80)}`);

  // 激活页面到前台（确保鼠标/键盘事件发到正确页面）
  await page.bringToFront();
  await sleep(1000);

  const report = { timestamp: new Date().toISOString(), nodeTypes: [] };

  // ── 1. 导航到策略列表 ──
  console.log('\n[1] 导航到策略列表');

  // 直接通过侧边栏导航
  await page.evaluate(() => {
    const items = document.querySelectorAll('.ant-menu-submenu-title');
    for (const item of items) {
      if (item.textContent.includes('策略平台')) { item.click(); break; }
    }
  });
  await sleep(1000);
  await page.evaluate(() => {
    const items = document.querySelectorAll('.ant-menu-item');
    for (const item of items) {
      if (item.textContent.trim() === '策略列表') { item.click(); break; }
    }
  });
  await sleep(4000);
  console.log(`  当前URL: ${page.url()}`);

  // 验证有新建策略按钮
  const hasButton = await page.evaluate(() => {
    return [...document.querySelectorAll('button')].some(b => b.textContent.includes('新建策略'));
  });
  console.log(`  有新建策略按钮: ${hasButton}`);
  await ss(page, '01-strategy-list');

  if (!hasButton) {
    console.log('  不在策略列表页，尝试直接导航...');
    await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(4000);
    await ss(page, '01-strategy-list');
  }

  // ── 2. 新建策略 ──
  console.log('\n[2] 新建策略');

  // 点击 "+ 新建策略" 按钮
  const btnPos = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const b of btns) {
      if (b.textContent.includes('新建策略') && b.offsetHeight > 0) {
        const r = b.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (!btnPos) { console.log('  找不到新建策略按钮'); process.exit(1); }
  await page.mouse.click(btnPos.x, btnPos.y);
  await sleep(2500);

  // 等待可见 modal
  const modalReady = await page.evaluate((code) => {
    const m = eval(code);
    if (!m) return { found: false };
    const r = m.getBoundingClientRect();
    return { found: true, w: r.width, h: r.height };
  }, GET_NEW_STRATEGY_MODAL);
  console.log(`  modal状态: ${JSON.stringify(modalReady)}`);
  if (!modalReady.found) { console.log('  modal未打开'); await ss(page, '02-no-modal'); process.exit(1); }

  // 填写名称：用鼠标点击 + 键盘输入
  const namePos = await page.evaluate((code) => {
    const m = eval(code);
    if (!m) return null;
    const input = m.querySelector('input');
    if (!input) return null;
    const r = input.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, GET_NEW_STRATEGY_MODAL);
  if (namePos) {
    await page.mouse.click(namePos.x, namePos.y);
    await sleep(200);
    await page.keyboard.type(`节点探查_${TS}`, { delay: 30 });
    console.log(`  名称已输入`);
  }
  await sleep(500);

  // 选择环节
  async function selectOption(labelText) {
    const info = await page.evaluate((code, label) => {
      const m = eval(code);
      if (!m) return { ok: false, reason: 'no modal' };
      const items = m.querySelectorAll('.ant-form-item');
      for (const item of items) {
        const lbl = item.querySelector('.ant-form-item-label');
        if (lbl && lbl.textContent.includes(label)) {
          const sel = item.querySelector('.ant-select');
          if (sel) {
            const r = sel.getBoundingClientRect();
            return { ok: true, x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
      }
      return { ok: false, reason: 'not found' };
    }, GET_NEW_STRATEGY_MODAL, labelText);

    if (!info.ok) { console.log(`  ${labelText}: ${info.reason}`); return null; }

    await page.mouse.click(info.x, info.y);
    await sleep(1200);

    const opt = await page.evaluate(() => {
      const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dds) {
        const items = dd.querySelectorAll('.ant-select-item-option');
        if (items.length > 0) {
          const r = items[0].getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: items[0].textContent.trim() };
        }
      }
      return null;
    });

    if (opt) {
      await page.mouse.click(opt.x, opt.y);
      console.log(`  ${labelText} → ${opt.text}`);
      await sleep(1500);
      // 确保下拉关闭
      const open = await page.evaluate(() =>
        !!document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'));
      if (open) { await page.mouse.click(50, 50); await sleep(500); }
      return opt.text;
    } else {
      console.log(`  ${labelText}: 无下拉选项`);
      // 关闭下拉
      await page.mouse.click(50, 50);
      await sleep(500);
      return null;
    }
  }

  await selectOption('环节');
  await sleep(500);
  await selectOption('生命周期');
  await sleep(500);
  await ss(page, '03-form-filled');

  // 点击确定
  const confirmClicked = await page.evaluate((code) => {
    const m = eval(code);
    if (!m) return false;
    const btns = m.querySelectorAll('button');
    for (const b of btns) {
      if (/确.*定/.test(b.textContent) && !b.disabled) { b.click(); return true; }
    }
    return false;
  }, GET_NEW_STRATEGY_MODAL);
  console.log(`  确定点击: ${confirmClicked}`);
  await sleep(4000);

  // 获取策略ID
  const strategyId = await page.evaluate(() => {
    const m = window.location.href.match(/strategy\/detail\/(\d+)/);
    return m ? m[1] : null;
  });
  console.log(`  策略ID: ${strategyId}`);
  await ss(page, '04-strategy-detail');

  if (!strategyId) {
    console.log('  策略创建失败，无法继续');
    browser.disconnect();
    process.exit(1);
  }

  // ── 3. 新增节点 → 收集所有节点类型 ──
  console.log('\n[3] 收集节点类型列表');

  // 点击 "+ 新增节点" 按钮
  const addNodePos = await page.evaluate(() => {
    const els = document.querySelectorAll('button, span, div, a');
    for (const el of els) {
      const txt = el.textContent.replace(/\s+/g, '');
      if ((txt === '新增节点' || txt === '+新增节点') && el.offsetHeight > 0) {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return null;
  });
  if (!addNodePos) { console.log('  找不到新增节点按钮'); process.exit(1); }
  await page.mouse.click(addNodePos.x, addNodePos.y);
  await sleep(3000);
  await ss(page, '05-node-type-library');

  // 滚动收集所有节点卡片
  const allNodeTypes = await page.evaluate(async () => {
    const results = [];
    const seen = new Set();

    // 找包含卡片的可见 modal
    let container = null;
    const modals = document.querySelectorAll('.ant-modal');
    for (const m of modals) {
      if (m.classList.contains('ant-modal-hidden')) continue;
      const r = m.getBoundingClientRect();
      if (r.width < 200) continue;
      const cards = m.querySelectorAll('.ant-card, [class*="card"]');
      if (cards.length > 3) {
        container = m.querySelector('.ant-modal-body') || m;
        break;
      }
    }
    if (!container) return { error: 'no card modal', modals: modals.length };

    for (let i = 0; i < 15; i++) {
      const cards = container.querySelectorAll('.ant-card, [class*="card"], [class*="Card"]');
      for (const card of cards) {
        const titleEl = card.querySelector('.ant-card-meta-title, [class*="title"], [class*="Title"]');
        const descEl = card.querySelector('.ant-card-meta-description, [class*="desc"], [class*="Desc"]');
        if (titleEl) {
          const title = titleEl.textContent.trim();
          if (title && !seen.has(title) && title.length < 20) {
            seen.add(title);
            results.push({ title, description: descEl ? descEl.textContent.trim() : '' });
          }
        }
      }
      container.scrollTop += 300;
      await new Promise(r => setTimeout(r, 300));
    }
    return { nodes: results, cardsFound: container.querySelectorAll('.ant-card, [class*="card"]').length };
  });

  if (allNodeTypes.error) {
    console.log(`  错误: ${JSON.stringify(allNodeTypes)}`);
    // 截图帮助诊断
    await ss(page, '05-debug-modal');
    browser.disconnect();
    process.exit(1);
  }

  const nodes = allNodeTypes.nodes || [];
  console.log(`  发现 ${nodes.length} 种节点:`);
  nodes.forEach((n, i) => console.log(`    ${i + 1}. ${n.title} - ${n.description}`));

  // 排除节点
  const EXCLUDE = ['推送选款', '选片'];
  const nodeTypes = nodes.filter(n => !EXCLUDE.includes(n.title));

  // ── 4. 逐个探查表单 ──
  console.log(`\n[4] 探查 ${nodeTypes.length} 个节点`);

  for (let i = 0; i < nodeTypes.length; i++) {
    const nt = nodeTypes[i];
    console.log(`\n  [${i + 1}/${nodeTypes.length}] ${nt.title}`);

    // 确保弹窗打开
    const modalVisible = await page.evaluate(() => {
      const modals = document.querySelectorAll('.ant-modal');
      for (const m of modals) {
        if (m.classList.contains('ant-modal-hidden')) continue;
        const r = m.getBoundingClientRect();
        if (r.width > 200) {
          const cards = m.querySelectorAll('.ant-card, [class*="card"]');
          if (cards.length > 3) return true;
        }
      }
      return false;
    });

    if (!modalVisible) {
      console.log('    重新打开弹窗...');
      const pos = await page.evaluate(() => {
        const els = document.querySelectorAll('button, span, div, a');
        for (const el of els) {
          const txt = el.textContent.replace(/\s+/g, '');
          if ((txt === '新增节点' || txt === '+新增节点') && el.offsetHeight > 0) {
            const r = el.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
        return null;
      });
      if (pos) { await page.mouse.click(pos.x, pos.y); await sleep(3000); }
    }

    // 点击节点卡片（真实鼠标点击）
    const cardPos = await page.evaluate((title) => {
      const modals = document.querySelectorAll('.ant-modal');
      for (const m of modals) {
        if (m.classList.contains('ant-modal-hidden')) continue;
        const cards = m.querySelectorAll('.ant-card-hoverable, .ant-card');
        for (const card of cards) {
          const t = card.querySelector('.ant-card-meta-title');
          if (t && t.textContent.trim() === title) {
            const r = card.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
      }
      return null;
    }, nt.title);

    if (!cardPos) { console.log('    跳过: 找不到卡片'); continue; }
    await page.mouse.click(cardPos.x, cardPos.y);
    await sleep(3000);

    // 截图抽屉
    await ss(page, `node-${String(i + 1).padStart(2, '0')}-${nt.title}`);

    // 提取表单字段
    const formInfo = await page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return { fields: [], sections: [], drawerOpen: false };

      const fields = [];
      const formItems = drawer.querySelectorAll('.ant-form-item');
      for (const item of formItems) {
        const labelEl = item.querySelector('.ant-form-item-label label, .ant-form-item-label');
        const label = labelEl ? labelEl.textContent.trim() : '';
        let type = 'unknown';
        if (item.querySelector('.ant-select')) type = 'select';
        else if (item.querySelector('textarea')) type = 'textarea';
        else if (item.querySelector('.ant-input-number')) type = 'number';
        else if (item.querySelector('input[type="text"], input:not([type])')) type = 'input';
        else if (item.querySelector('.ant-switch')) type = 'switch';
        else if (item.querySelector('.ant-radio-group')) type = 'radio';
        else if (item.querySelector('.ant-checkbox-group')) type = 'checkbox';
        else if (item.querySelector('.ant-slider')) type = 'slider';
        fields.push({ label, type });
      }

      const sections = [];
      drawer.querySelectorAll('h3, h4, .ant-divider-inner-text').forEach(t => {
        sections.push(t.textContent.trim());
      });

      return { fields, sections, drawerOpen: true };
    });

    const nodeReport = {
      title: nt.title,
      description: nt.description,
      fields: formInfo.fields,
      sections: formInfo.sections,
      drawerOpen: formInfo.drawerOpen,
    };
    report.nodeTypes.push(nodeReport);

    console.log(`    抽屉: ${formInfo.drawerOpen ? '打开' : '未打开'}, 字段: ${formInfo.fields.length}`);
    formInfo.fields.forEach(f => console.log(`      - ${f.label} (${f.type})`));

    // 关闭抽屉
    await page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return;
      const closeBtn = drawer.querySelector('.ant-drawer-close');
      if (closeBtn) closeBtn.click();
    });
    await sleep(1500);
  }

  // ── 5. 报告 ──
  const reportPath = '/tmp/node-type-report.json';
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\n报告已写入: ${reportPath}`);
  console.log(`共探查 ${report.nodeTypes.length} 种节点`);

  browser.disconnect();
  console.log('\n=== 探查完成 ===');
}

main().catch(e => { console.error('探查失败:', e); process.exit(1); });
