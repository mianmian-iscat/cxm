#!/usr/bin/env node
/**
 * 探索任务创建流程 + 触发【zy测试】主图生成链路生成测试数据
 * 然后进入审核详情页执行 tc06-tc11 操作级回归
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = 'http://127.0.0.1:9222';
const BASE_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ss(page, name) {
  const fp = path.join(SS_DIR, `regression-detail-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
  return fp;
}

const results = [];
function log(tc, step, status, detail) {
  results.push({ tc, step, status, detail });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`  ${icon} [${tc}] ${step}: ${detail}`);
}

// ── 第一步：探索任务管理页面，点击新建任务 ──
async function exploreTaskCreation(browser) {
  console.log('\n═══ Step 1: 探索任务创建流程 ═══');
  const page = await browser.newPage();

  // 导航到任务管理
  await page.goto(`${BASE_URL}/review/task-management?sourceTab=other`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 先通过 Ant Design 菜单导航
  await page.evaluate(() => {
    const titles = document.querySelectorAll('.ant-menu-submenu-title');
    for (const t of titles) {
      if (t.textContent.trim().includes('审核管理')) { t.click(); break; }
    }
  });
  await sleep(1500);
  await page.evaluate(() => {
    const items = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
    for (const item of items) {
      if (item.textContent.trim() === '任务管理') { item.click(); break; }
    }
  });
  await sleep(3000);

  await ss(page, 'step1-task-mgmt');

  // 查找"新建任务"按钮
  const newTaskBtn = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button, a, span, div')];
    const el = btns.find(e => e.textContent.trim().includes('新建任务'));
    if (el) {
      return { found: true, tag: el.tagName, text: el.textContent.trim(), class: el.className?.substring(0, 80) };
    }
    return { found: false };
  });
  console.log('  新建任务按钮:', JSON.stringify(newTaskBtn));

  if (newTaskBtn.found) {
    // 点击新建任务
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button, a, span')];
      const el = btns.find(e => e.textContent.trim().includes('新建任务'));
      if (el) el.click();
    });
    await sleep(3000);
    await ss(page, 'step1-new-task-dialog');

    // 查看弹出的对话框/表单内容
    const dialogContent = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal, .ant-drawer, [class*=dialog], [class*=modal]');
      if (modal) return modal.innerText.substring(0, 1000);
      // 可能跳转到了新页面
      return 'NO_MODAL_FOUND. Current URL: ' + window.location.href + '. Body: ' + document.body.innerText.substring(0, 500);
    });
    console.log('  新建任务表单:', dialogContent.substring(0, 500));

    // 查看当前URL（可能跳转了）
    console.log('  当前URL:', page.url());
  }

  // 也看看个人任务中心现有的待审核任务
  await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 获取任务列表中的"开始任务"按钮信息
  const tasks = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('tr, [class*=row], [class*=task]')];
    const taskList = [];
    for (const row of rows) {
      const text = row.innerText;
      if (text.includes('开始任务') || text.includes('查看详情')) {
        const nameEl = row.querySelector('[class*=name], [class*=title], td:first-child');
        taskList.push({
          name: nameEl ? nameEl.innerText.substring(0, 80) : text.substring(0, 80),
          hasStart: text.includes('开始任务'),
          hasDetail: text.includes('查看详情'),
        });
      }
    }
    return taskList;
  });
  console.log('  现有任务:', JSON.stringify(tasks, null, 2));

  await ss(page, 'step1-task-center');
  await page.close();
}

async function main() {
  console.log('🔗 连接 CDP:', CDP_URL);
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  console.log('✅ 已连接 Chrome\n');

  await exploreTaskCreation(browser);
  await browser.disconnect();
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });
