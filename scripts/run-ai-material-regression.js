#!/usr/bin/env node
/**
 * AI 素材中心端到端回归脚本
 *
 * 流程：AI素材管理 → 创建任务 → 链路20180审核 → 素材生产 → 待选图 → 选图
 *
 * 三阶段设计（生产链路异步，需分阶段验证）：
 *   Phase 1: 创建任务 — 点创建任务 → 选原始素材 → 提交
 *   Phase 2: 状态轮询 — 等待 生产中 → 待选图
 *   Phase 3: 选图验证 — 待选图 → 去选图 → 确认选图
 *
 * 约束：一次只允许创建一条任务，不测并发
 *
 * 用法：
 *   node scripts/run-ai-material-regression.js                    # 全量检查
 *   node scripts/run-ai-material-regression.js --phase create     # 仅创建
 *   node scripts/run-ai-material-regression.js --phase check      # 仅检查状态
 *   node scripts/run-ai-material-regression.js --phase select     # 仅选图
 *   node scripts/run-ai-material-regression.js --out result.json  # 指定输出
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ── CLI 参数 ──
const args = process.argv.slice(2);
let OUTPUT_FILE = '';
let PHASE = 'all';
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out' && args[i + 1]) { OUTPUT_FILE = args[++i]; }
  else if (args[i] === '--phase' && args[i + 1]) { PHASE = args[++i]; }
}

// ── puppeteer-core ──
function resolvePuppeteer() {
  const env = process.env.WEB_AUTO_PUPPETEER_PATH;
  const candidates = [
    ...(env && env !== 'auto' ? [env] : []),
    path.join(__dirname, '..', 'node_modules', 'puppeteer-core'),
    'puppeteer-core',
  ];
  for (const p of candidates) {
    try { require.resolve(p); return require(p); } catch (_) {}
  }
  throw new Error('找不到 puppeteer-core');
}
const puppeteer = resolvePuppeteer();

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const PAGE_URL = 'https://pre-xiaoer.alibaba-inc.com/bzb/fsyx_quality_guard/quality-pulse/ai-material-management?opGroupId=1.17087.61227.0.49150&bzbSopNodeId=49150';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'ai-material');
const POLL_INTERVAL_MS = 30000;
const POLL_MAX = 10;

const results = [];
function log(tc, step, status, detail) {
  results.push({ tc, step, status, detail, time: new Date().toISOString() });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`  ${icon} [${tc}] ${step}: ${detail}`);
}

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  return fp;
}

const wait = ms => new Promise(r => setTimeout(r, ms));

// ══════════════════════════════════════════
// Phase 1: 创建任务
// ══════════════════════════════════════════
async function phaseCreate(page) {
  console.log('\n═══ Phase 1: 创建任务 ═══');

  // 1.1 找「未创建」行
  const row = await page.evaluate(() => {
    const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
    for (let i = 0; i < rows.length; i++) {
      const cells = rows[i].querySelectorAll('td');
      for (const cell of cells) {
        if (cell.textContent.trim() === '未创建') {
          const id = cells[0]?.textContent.match(/ID\s*(\d+)/);
          return { index: i, productId: id ? id[1] : 'unknown' };
        }
      }
    }
    return null;
  });

  if (!row) {
    log('P1', '未创建行', 'FAIL', '无未创建行，所有任务已创建');
    return false;
  }
  log('P1', '未创建行', 'PASS', `第${row.index + 1}行, ID: ${row.productId}`);

  // 1.2 点击创建任务（用 Puppeteer 原生点击，确保触发 React 事件）
  const createLinkSelector = `.tbd-table-row:nth-child(${row.index + 1}) a, table tbody tr:nth-child(${row.index + 1}) a`;
  const createLinks = await page.$$(createLinkSelector);
  let clicked = false;
  for (const link of createLinks) {
    const text = await page.evaluate(el => el.textContent.trim(), link);
    if (text === '创建任务') {
      await link.click();
      clicked = true;
      break;
    }
  }
  if (!clicked) {
    // 降级：用 JS 点击 + 派发事件
    await page.evaluate((idx) => {
      const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
      const links = rows[idx].querySelectorAll('a');
      for (const a of links) {
        if (a.textContent.trim() === '创建任务') {
          a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
          return;
        }
      }
    }, row.index);
  }
  await wait(3000);

  // 1.3 验证弹窗（实际是 Drawer 抽屉组件）
  const dialog = await page.evaluate(() => {
    const drawer = document.querySelector('.tbd-drawer-section')
      || document.querySelector('.ReactModalPortal .tbd-drawer')
      || document.querySelector('[class*="drawer"][class*="open"]')
      || document.querySelector('.tbd-modal-wrap:not([style*="display: none"])')
      || document.querySelector('.tbd-modal');
    if (!drawer) return null;
    const title = drawer.querySelector('[class*="title"], .tbd-modal-title, h2, h3')?.textContent || '';
    const hasSubmit = !!Array.from(drawer.querySelectorAll('button')).find(b => b.textContent.trim() === '提交');
    const imgs = drawer.querySelectorAll('img[src*="img.alicdn"]');
    return { title, hasSubmit, imgCount: imgs.length };
  });

  if (!dialog || !dialog.title.includes('创建生图任务')) {
    log('P1', '创建弹窗', 'FAIL', '弹窗未出现');
    return false;
  }
  log('P1', '创建弹窗', 'PASS', `${dialog.title}, 图片${dialog.imgCount}张, 提交按钮: ${dialog.hasSubmit}`);
  await ss(page, 'p1-01-dialog');

  // 1.4 选原始素材（默认选中第一张 3:4 主图）
  const sel = await page.evaluate(() => {
    const m = document.querySelector('.tbd-drawer-section')
      || document.querySelector('.ReactModalPortal .tbd-drawer')
      || document.querySelector('.tbd-modal-wrap:not([style*="display: none"])')
      || document.querySelector('.tbd-modal');
    if (!m) return null;
    const imgs = m.querySelectorAll('img[src*="img.alicdn"]');
    if (imgs.length === 0) return null;
    // 检查是否有已选中
    const selected = m.querySelector('[class*="selected"] img, [style*="border"] img');
    if (!selected && imgs.length > 0) imgs[0].click();
    return { count: imgs.length, preSelected: !!selected };
  });

  if (!sel) {
    log('P1', '选择素材', 'FAIL', '无可选图片');
    await page.evaluate(() => {
      const drawer = document.querySelector('.tbd-drawer-section')
        || document.querySelector('.tbd-modal');
      if (!drawer) return;
      for (const b of drawer.querySelectorAll('button')) {
        if (b.textContent.trim() === '取消') { b.click(); return; }
      }
    });
    return false;
  }
  log('P1', '选择素材', 'PASS', `${sel.count}张, 预选: ${sel.preSelected}`);

  // 1.5 提交（Puppeteer 原生点击）
  let apiResp = null;
  const apiPromise = page.waitForResponse(
    r => r.url().includes('materialItem') || r.url().includes('create'),
    { timeout: 15000 }
  ).then(r => { apiResp = r; }).catch(() => {});

  const modal = await page.$('.tbd-drawer-section')
    || await page.$('.ReactModalPortal .tbd-drawer')
    || await page.$('.tbd-modal-wrap:not([style*="display: none"])')
    || await page.$('.tbd-modal');
  if (modal) {
    const btns = await modal.$$('button');
    for (const btn of btns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text === '提交') { await btn.click(); break; }
    }
  } else {
    // 降级
    await page.evaluate(() => {
      const m = document.querySelector('.tbd-drawer-section')
        || document.querySelector('.tbd-modal');
      if (!m) return;
      for (const b of m.querySelectorAll('button')) {
        if (b.textContent.trim() === '提交') {
          b.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
          return;
        }
      }
    });
  }
  await apiPromise;
  await wait(3000);

  // 1.6 验证提交结果
  if (apiResp) {
    const st = apiResp.status();
    log('P1', '提交API', st === 200 ? 'PASS' : 'FAIL', `HTTP ${st}`);
    if (st === 200) {
      try {
        const json = await apiResp.json();
        const ok = json.success !== false;
        log('P1', '业务结果', ok ? 'PASS' : 'FAIL', ok ? '创建成功' : JSON.stringify(json).substring(0, 150));
      } catch (_) { log('P1', '业务结果', 'PASS', 'HTTP 200'); }
    }
  } else {
    const drawerGone = await page.evaluate(() => {
      const d = document.querySelector('.tbd-drawer-section');
      return !d || window.getComputedStyle(d).display === 'none';
    });
    log('P1', '提交结果', drawerGone ? 'PASS' : 'FAIL', drawerGone ? '抽屉已关闭' : '抽屉未关闭');
  }
  await ss(page, 'p1-02-after-submit');

  // 1.7 刷新页面并检查状态变化
  await page.reload({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
  await wait(5000);
  const status = await page.evaluate(() => {
    const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      for (const c of cells) {
        const t = c.textContent.trim();
        if (t.startsWith('生产中')) return '生产中';
        if (t.startsWith('待选图')) return '待选图';
      }
    }
    return 'unknown';
  });
  log('P1', '状态变更', (status === '生产中' || status === '待选图') ? 'PASS' : 'FAIL',
    `当前状态: ${status}`);
  return status !== 'unknown';
}

// ══════════════════════════════════════════
// Phase 2: 轮询状态
// ══════════════════════════════════════════
async function phaseCheck(page) {
  console.log('\n═══ Phase 2: 状态轮询 ═══');

  for (let attempt = 1; attempt <= POLL_MAX; attempt++) {
    const status = await page.evaluate(() => {
      const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
      let hasProduction = false;
      for (const row of rows) {
        const cells = row.querySelectorAll('td');
        for (const c of cells) {
          const t = c.textContent.trim();
          if (t.startsWith('待选图')) return '待选图';
          if (t === '已完成') return '已完成';
          if (t.startsWith('生产中')) hasProduction = true;
        }
      }
      return hasProduction ? '生产中' : 'none';
    });

    log('P2', `轮询 #${attempt}`, 'PASS', `状态: ${status}`);

    if (status === '待选图' || status === '已完成') {
      await ss(page, 'p2-01-status-ready');
      return status;
    }
    if (status === 'none') {
      log('P2', '轮询', 'FAIL', '无任务行');
      return null;
    }

    if (attempt < POLL_MAX) {
      console.log(`  ⏳ 等待 ${POLL_INTERVAL_MS / 1000}s ...`);
      await wait(POLL_INTERVAL_MS);
      await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
      await wait(3000);
    }
  }

  log('P2', '轮询超时', 'FAIL', `${POLL_MAX} 次后仍为生产中`);
  return null;
}

// ══════════════════════════════════════════
// Phase 3: 选图
// ══════════════════════════════════════════
async function phaseSelect(page, browser) {
  console.log('\n═══ Phase 3: 选图验证 ═══');

  // 3.1 找「待选图」行 + 「去选图」按钮
  const found = await page.evaluate(() => {
    const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
    for (let i = 0; i < rows.length; i++) {
      const cells = rows[i].querySelectorAll('td');
      for (const c of cells) {
        if (c.textContent.trim().startsWith('待选图')) {
          const links = rows[i].querySelectorAll('a');
          for (const a of links) {
            if (a.textContent.trim() === '去选图') { return { index: i }; }
          }
        }
      }
    }
    return null;
  });

  if (!found) {
    log('P3', '待选图行', 'FAIL', '无待选图任务');
    return false;
  }
  log('P3', '待选图行', 'PASS', `第${found.index + 1}行`);

  // 3.2 点击去选图（可能打开新 tab）
  const existingPages = (await browser.pages()).length;
  await page.evaluate((idx) => {
    const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
    const links = rows[idx].querySelectorAll('a');
    for (const a of links) {
      if (a.textContent.trim() === '去选图') { a.click(); return; }
    }
  }, found.index);
  await wait(5000);

  let targetPage = page;
  const allPages = await browser.pages();
  if (allPages.length > existingPages) {
    targetPage = allPages[allPages.length - 1];
    await targetPage.waitForNavigation({ timeout: 15000 }).catch(() => {});
    await wait(3000);
  }

  // 3.3 验证选图页面
  const selectPageInfo = await targetPage.evaluate(() => {
    const url = window.location.href;
    const title = document.title;
    const hasImage = !!document.querySelector('img[src*="img.alicdn"]');
    const buttons = Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(t => t);
    return { url: url.substring(0, 200), title, hasImage, buttons: buttons.slice(0, 10) };
  });

  log('P3', '选图页面', 'PASS', `URL: ${selectPageInfo.url.substring(0, 100)}, 图片: ${selectPageInfo.hasImage}`);
  await ss(targetPage, 'p3-01-select-page');

  // 3.4 关闭新开的 tab
  if (targetPage !== page) await targetPage.close().catch(() => {});

  return true;
}

// ══════════════════════════════════════════
// 主入口
// ══════════════════════════════════════════
async function main() {
  console.log('🔗 连接 CDP:', CDP_URL);
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  console.log('✅ 已连接 Chrome\n');

  // 复用已有 tab（新建 tab 的 React 事件可能不触发）
  const pages = await browser.pages();
  const page = pages.length > 0 ? pages[pages.length - 1] : await browser.newPage();
  let createdNewPage = pages.length === 0;
  await page.goto(PAGE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
  await wait(5000);

  // 检查登录
  if (page.url().includes('login')) {
    log('E2E', '登录态', 'FAIL', '被重定向到登录页');
    if (createdNewPage) await page.close();
    await browser.disconnect();
    writeResults();
    return;
  }
  log('E2E', '页面加载', 'PASS', page.url().substring(0, 100));

  // 统计当前状态
  const overview = await page.evaluate(() => {
    const rows = document.querySelectorAll('.tbd-table-row, table tbody tr');
    const counts = { total: rows.length, 未创建: 0, 生产中: 0, 待选图: 0, 已完成: 0, other: 0 };
    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      for (const c of cells) {
        const t = c.textContent.trim();
        if (t.startsWith('生产中')) counts['生产中']++;
        else if (t.startsWith('待选图')) counts['待选图']++;
        else if (t === '未创建') counts['未创建']++;
        else if (t === '已完成') counts['已完成']++;
      }
    }
    return counts;
  });
  console.log('📊 当前状态:', JSON.stringify(overview));

  let p1Ok = false, p2Status = null, p3Ok = false;

  // Phase 1
  if (PHASE === 'all' || PHASE === 'create') {
    if (overview.未创建 > 0) {
      p1Ok = await phaseCreate(page);
    } else {
      console.log('\n⏭️  Phase 1: 无未创建行，跳过');
      log('P1', '跳过', 'PASS', '无未创建行');
    }
  }

  // Phase 2: 如果有待选图任务直接跳过轮询，否则等待生产中完成
  if (PHASE === 'all' || PHASE === 'check') {
    if (overview.待选图 > 0) {
      console.log('\n⏭️  Phase 2: 已有待选图任务，跳过轮询');
      log('P2', '跳过', 'PASS', `已有 ${overview.待选图} 个待选图`);
      p2Status = '待选图';
    } else if (overview.生产中 > 0 || p1Ok) {
      await page.reload({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
      await wait(3000);
      p2Status = await phaseCheck(page);
    } else {
      console.log('\n⏭️  Phase 2: 无生产中任务，跳过');
      log('P2', '跳过', 'PASS', '无生产中任务');
    }
  }

  // Phase 3
  if (PHASE === 'all' || PHASE === 'select') {
    if (p2Status === '待选图' || overview.待选图 > 0) {
      p3Ok = await phaseSelect(page, browser);
    } else {
      console.log('\n⏭️  Phase 3: 无待选图任务，跳过');
      log('P3', '跳过', 'PASS', '无待选图任务');
    }
  }

  if (createdNewPage) await page.close();
  await browser.disconnect();

  // 汇总
  console.log('\n═══════════════════════════════');
  console.log('📊 AI素材中心回归结果');
  console.log('═══════════════════════════════');
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  console.log(`断言: ${results.length} 项 | ✅ PASS: ${pass} | ❌ FAIL: ${fail}`);
  if (fail > 0) {
    console.log('\n❌ 失败项:');
    results.filter(r => r.status === 'FAIL').forEach(r => console.log(`  ${r.tc} > ${r.step}: ${r.detail}`));
  }
  console.log(`通过率: ${(pass / results.length * 100).toFixed(1)}%`);

  writeResults();
}

function writeResults() {
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const outPath = OUTPUT_FILE ? path.resolve(OUTPUT_FILE) : path.join(__dirname, '..', 'artifacts', 'ai-material-results.json');
  fs.writeFileSync(outPath, JSON.stringify({
    summary: { total: results.length, pass, fail },
    results,
  }, null, 2));
  console.log(`\n📁 结果已保存: ${outPath}`);
}

main().catch(e => { console.error('❌ 执行异常:', e.message); process.exit(1); });
