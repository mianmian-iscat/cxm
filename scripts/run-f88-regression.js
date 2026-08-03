#!/usr/bin/env node
/**
 * F88 审核页面快速回归脚本
 * 直接用 puppeteer-core 连接 CDP，逐个验证关键检查点
 */
'use strict';
const puppeteer = require('puppeteer-core');

// ── CLI 参数解析 ──
const args = process.argv.slice(2);
let OUTPUT_FILE = '';
let SEQUENTIAL = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out' && args[i + 1]) { OUTPUT_FILE = args[++i]; }
  else if (args[i] === '--sequential') { SEQUENTIAL = true; }
}

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SCREENSHOT_DIR = require('path').join(__dirname, '..', 'artifacts', 'screenshots');
const fs = require('fs');

if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = [];
const CASE_TIMEOUT_MS = parseInt(process.env.CASE_TIMEOUT_MS, 10) || 60000;

// ── DAG 调度工具函数 ──
function buildDAGWaves(entries) {
  const idSet = new Set(entries.map(e => e.id));
  const resolved = new Set();
  const remaining = new Map(entries.map(e => [e.id, e]));
  const waves = [];
  let safety = entries.length + 1;
  while (remaining.size > 0 && safety-- > 0) {
    const wave = [];
    for (const [id, e] of remaining) {
      if ((e.deps || []).every(d => resolved.has(d) || !idSet.has(d))) wave.push([id, e]);
    }
    if (wave.length === 0) { wave.push(...remaining); remaining.clear(); }
    else { for (const [id] of wave) { resolved.add(id); remaining.delete(id); } }
    waves.push(wave);
  }
  return waves;
}

function findAllDownstream(failedId, entries) {
  const ds = new Set();
  let changed = true;
  while (changed) {
    changed = false;
    for (const e of entries) {
      if (ds.has(e.id)) continue;
      if ((e.deps || []).includes(failedId) || (e.deps || []).some(d => ds.has(d))) { ds.add(e.id); changed = true; }
    }
  }
  return ds;
}

function log(tc, step, status, detail) {
  const entry = { tc, step, status, detail, time: new Date().toISOString() };
  results.push(entry);
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`  ${icon} [${tc}] ${step}: ${detail}`);
}

async function screenshot(page, name) {
  const fp = require('path').join(SCREENSHOT_DIR, `regression-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  return fp;
}

async function waitForPage(page, ms = 3000) {
  await new Promise(r => setTimeout(r, ms));
}

// Ant Design SubMenu 展开：点击 .ant-menu-submenu-title
async function expandSubMenu(page, menuText) {
  const expanded = await page.evaluate((text) => {
    const titles = document.querySelectorAll('.ant-menu-submenu-title');
    for (const title of titles) {
      if (title.textContent.trim().includes(text)) { title.click(); return true; }
    }
    return false;
  }, menuText);
  await waitForPage(page, 1500);
  return expanded;
}

// Ant Design MenuItem 点击：点击 .ant-menu-item .ant-menu-title-content
async function clickMenuItem(page, itemText) {
  const clicked = await page.evaluate((text) => {
    const items = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
    for (const item of items) {
      if (item.textContent.trim() === text) { item.click(); return true; }
    }
    return false;
  }, itemText);
  await waitForPage(page, 3000);
  return clicked;
}

// ── TC01: 个人任务中心 ──
async function tc01(browser) {
  console.log('\n═══ TC01: 个人任务中心 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 租户验证
    const bodyText = await page.evaluate(() => document.body.innerText);
    log('TC01', '租户-F88', bodyText.includes('F88') ? 'PASS' : 'FAIL',
      bodyText.includes('F88') ? '页面包含F88标识' : '页面缺少F88标识');
    log('TC01', '租户-运营平台', bodyText.includes('运营平台') ? 'PASS' : 'FAIL',
      bodyText.includes('运营平台') ? '包含运营平台字样' : '缺少运营平台字样');

    // Tab 验证
    log('TC01', 'Tab-审核任务', bodyText.includes('审核任务') ? 'PASS' : 'FAIL', '审核任务Tab');
    log('TC01', 'Tab-抽检任务', bodyText.includes('抽检任务') ? 'PASS' : 'FAIL', '抽检任务Tab');
    log('TC01', 'Tab-埋雷任务', bodyText.includes('埋雷任务') ? 'PASS' : 'FAIL', '埋雷任务Tab');

    // 左侧导航验证
    log('TC01', '导航-审核管理', bodyText.includes('审核管理') ? 'PASS' : 'FAIL', '左侧导航审核管理');
    log('TC01', '导航-商家管理', bodyText.includes('商家管理') ? 'PASS' : 'FAIL', '左侧导航商家管理');

    // 搜索框
    const searchInput = await page.$('input[placeholder*="请输入"]');
    log('TC01', '搜索框存在', searchInput ? 'PASS' : 'FAIL', searchInput ? '搜索输入框存在' : '搜索输入框不存在');

    // 列表字段
    log('TC01', '字段-任务名称', bodyText.includes('任务名称') ? 'PASS' : 'FAIL', '任务名称字段');
    log('TC01', '字段-优先级', bodyText.includes('优先级') ? 'PASS' : 'FAIL', '优先级字段');

    await screenshot(page, 'tc01-task-center');
    log('TC01', '截图', 'PASS', 'tc01截图已保存');
  } catch (e) {
    log('TC01', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC02: 审核标准管理 ──
async function tc02(browser) {
  console.log('\n═══ TC02: 审核标准管理 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 展开审核管理子菜单
    const auditExpanded = await expandSubMenu(page, '审核管理');
    log('TC02', '展开审核管理', auditExpanded ? 'PASS' : 'FAIL', auditExpanded ? '成功展开' : '未找到');

    // 点击审核标准管理
    const standardMgmt = await clickMenuItem(page, '审核标准管理');
    log('TC02', '点击审核标准管理', standardMgmt ? 'PASS' : 'FAIL', standardMgmt ? '成功导航' : '未找到菜单项');
    await waitForPage(page);

    const bodyText = await page.evaluate(() => document.body.innerText);
    log('TC02', '页面加载', bodyText.length > 100 ? 'PASS' : 'FAIL', `页面内容长度: ${bodyText.length}`);
    log('TC02', 'URL', 'PASS', `当前URL: ${page.url()}`);
    log('TC02', '字段-标准名称', bodyText.includes('标准名称') ? 'PASS' : 'FAIL', '标准名称字段');
    log('TC02', '字段-创建人', bodyText.includes('创建人') ? 'PASS' : 'FAIL', '创建人字段');

    await screenshot(page, 'tc02-audit-standard');
    log('TC02', '截图', 'PASS', 'tc02截图已保存');
  } catch (e) {
    log('TC02', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC03: 审核节点管理 ──
async function tc03(browser) {
  console.log('\n═══ TC03: 审核节点管理 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 展开审核管理子菜单
    await expandSubMenu(page, '审核管理');

    const nodeMgmt = await clickMenuItem(page, '审核节点管理');
    log('TC03', '点击审核节点管理', nodeMgmt ? 'PASS' : 'FAIL', nodeMgmt ? '成功导航' : '未找到菜单项');
    await waitForPage(page);

    const bodyText = await page.evaluate(() => document.body.innerText);
    log('TC03', '页面加载', bodyText.length > 100 ? 'PASS' : 'FAIL', `页面内容长度: ${bodyText.length}`);
    log('TC03', 'URL', 'PASS', `当前URL: ${page.url()}`);
    log('TC03', '字段-节点名称', bodyText.includes('节点名称') ? 'PASS' : 'FAIL', '节点名称字段');
    log('TC03', '字段-审核标准', bodyText.includes('审核标准') ? 'PASS' : 'FAIL', '审核标准字段');
    log('TC03', '字段-分配方式', bodyText.includes('分配方式') ? 'PASS' : 'FAIL', '分配方式字段');

    await screenshot(page, 'tc03-audit-node');
    log('TC03', '截图', 'PASS', 'tc03截图已保存');
  } catch (e) {
    log('TC03', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC04: 任务管理 ──
async function tc04(browser) {
  console.log('\n═══ TC04: 任务管理 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 展开审核管理子菜单
    await expandSubMenu(page, '审核管理');

    const taskMgmt = await clickMenuItem(page, '任务管理');
    log('TC04', '点击任务管理', taskMgmt ? 'PASS' : 'FAIL', taskMgmt ? '成功导航' : '未找到菜单项');
    await waitForPage(page);

    const bodyText = await page.evaluate(() => document.body.innerText);
    log('TC04', '页面加载', bodyText.length > 100 ? 'PASS' : 'FAIL', `页面内容长度: ${bodyText.length}`);
    log('TC04', 'URL', 'PASS', `当前URL: ${page.url()}`);
    log('TC04', '字段-链路', bodyText.includes('链路') ? 'PASS' : 'FAIL', '链路筛选字段');
    log('TC04', '字段-批次', bodyText.includes('批次') ? 'PASS' : 'FAIL', '批次筛选字段');
    log('TC04', '列表有数据', bodyText.includes('主图生成链路') || bodyText.includes('视频审核') ? 'PASS' : 'FAIL', '任务列表包含链路数据');

    await screenshot(page, 'tc04-task-management');
    log('TC04', '截图', 'PASS', 'tc04截图已保存');
  } catch (e) {
    log('TC04', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC05: Tab切换 + 任务搜索 ──
async function tc05(browser) {
  console.log('\n═══ TC05: Tab切换 + 任务搜索 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 切换到抽检任务Tab
    const spotCheck = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '抽检任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC05', '切换到抽检任务', spotCheck ? 'PASS' : 'FAIL', spotCheck ? '成功切换' : '未找到Tab');
    await waitForPage(page, 2000);
    await screenshot(page, 'tc05-spot-check');

    // 切换到埋雷任务Tab
    const landmine = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '埋雷任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC05', '切换到埋雷任务', landmine ? 'PASS' : 'FAIL', landmine ? '成功切换' : '未找到Tab');
    await waitForPage(page, 2000);
    await screenshot(page, 'tc05-landmine');

    // 切回审核任务
    const audit = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '审核任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC05', '切回审核任务', audit ? 'PASS' : 'FAIL', audit ? '成功切换' : '未找到Tab');
    await waitForPage(page, 1000);

    // 搜索测试
    const searchInput = await page.$('input[placeholder*="请输入"]');
    if (searchInput) {
      await searchInput.click({ clickCount: 3 });
      await searchInput.type('首图审核');
      await waitForPage(page, 2000);
      const bodyText = await page.evaluate(() => document.body.innerText);
      log('TC05', '搜索-首图审核', bodyText.includes('首图审核') ? 'PASS' : 'FAIL',
        bodyText.includes('首图审核') ? '搜索结果包含首图审核' : '搜索结果未包含首图审核');
      await screenshot(page, 'tc05-search');
    } else {
      log('TC05', '搜索框', 'FAIL', '搜索输入框不存在');
    }
  } catch (e) {
    log('TC05', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC06: 任务大厅 4个来源Tab ──
async function tc06(browser) {
  console.log('\n═══ TC06: 任务大厅-4个来源Tab ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/task-management`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    const bodyText = await page.evaluate(() => document.body.innerText);
    log('TC06', 'Tab-策略平台-F88', bodyText.includes('策略平台-F88') ? 'PASS' : 'FAIL', '策略平台-F88来源Tab');
    log('TC06', 'Tab-策略平台-测试', bodyText.includes('策略平台') && bodyText.includes('测试') ? 'PASS' : 'FAIL', '策略平台-测试来源Tab');
    log('TC06', 'Tab-手动创建', bodyText.includes('手动创建') ? 'PASS' : 'FAIL', '手动创建来源Tab');
    log('TC06', 'Tab-模版库', bodyText.includes('模版库') ? 'PASS' : 'FAIL', '模版库来源Tab');

    // 切换每个tab
    const tabs = ['策略平台-测试', '手动创建', '模版库', '策略平台-F88'];
    for (const tab of tabs) {
      const clicked = await page.evaluate((text) => {
        const els = [...document.querySelectorAll('span, a, div, [role="tab"]')];
        const el = els.find(e => e.textContent.trim() === text || e.textContent.includes(text));
        if (el && el.offsetHeight > 0) { el.click(); return true; }
        return false;
      }, tab);
      log('TC06', `切换-${tab}`, clicked ? 'PASS' : 'FAIL', clicked ? `已切换到${tab}` : `未找到${tab}`);
      await waitForPage(page, 2000);
    }

    await screenshot(page, 'tc06-task-hall-tabs');
    log('TC06', '截图', 'PASS', 'tc06截图已保存');
  } catch (e) {
    log('TC06', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC07: 审核详情页-工具栏按钮 ──
async function tc07(browser) {
  console.log('\n═══ TC07: 审核详情页-工具栏按钮 ═══');
  const page = await browser.newPage();
  try {
    // 先进入个人任务中心找一个有数据的任务
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 查找第一个"查看详情"链接
    const detailHref = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a'));
      const dl = links.find(a => a.href.includes('task/detail') || a.textContent.includes('查看详情'));
      return dl ? dl.href : null;
    });

    if (!detailHref) {
      log('TC07', '找任务', 'WARN', '未找到有数据的审核任务，跳过');
      await page.close();
      return;
    }
    log('TC07', '找任务', 'PASS', `找到任务详情: ${detailHref}`);

    // 进入详情
    await page.goto(detailHref, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);
    await screenshot(page, 'tc07-audit-detail');

    // 检测工具栏按钮（图片审核9个 + 视频审核3个）
    const toolbarButtons = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button, [class*="toolbar"] button, [class*="action"] button'));
      const imageBtns = ['编辑', '下载', '替换', '裁剪', '局部修改', '高清化', '负反馈', '复位', '复制'];
      const videoBtns = ['剪辑', '下载', '替换'];
      const allExpected = [...new Set([...imageBtns, ...videoBtns])];
      const found = btns.filter(b => allExpected.some(k => b.innerText.includes(k)));
      return {
        totalButtons: btns.length,
        foundToolbarButtons: found.map(b => b.innerText.trim()),
        hasToolbar: found.length > 0
      };
    });

    log('TC07', '工具栏存在', toolbarButtons.hasToolbar ? 'PASS' : 'FAIL',
      `工具栏按钮: ${toolbarButtons.foundToolbarButtons.join(', ') || '未找到'}`);
    log('TC07', '按钮数量', toolbarButtons.totalButtons > 0 ? 'PASS' : 'FAIL',
      `总按钮数: ${toolbarButtons.totalButtons}`);

    // 尝试hover每个按钮查看tooltip
    if (toolbarButtons.foundToolbarButtons.length > 0) {
      for (const btnText of toolbarButtons.foundToolbarButtons) {
        const hoverResult = await page.evaluate((text) => {
          const btns = Array.from(document.querySelectorAll('button'));
          const btn = btns.find(b => b.innerText.includes(text));
          if (btn && btn.offsetHeight > 0) {
            btn.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
            btn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
            return true;
          }
          return false;
        }, btnText);
        await waitForPage(page, 500);
        log('TC07', `hover-${btnText}`, hoverResult ? 'PASS' : 'FAIL', hoverResult ? `${btnText}可hover` : `${btnText}不可hover`);
      }
    }

    await screenshot(page, 'tc07-toolbar-hover');
  } catch (e) {
    log('TC07', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC08: 审核操作-通过/驳回 ──
async function tc08(browser) {
  console.log('\n═══ TC08: 审核操作-通过/驳回 ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 记录操作前的进度/通过率
    const beforeStats = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('.ant-table-row, tr[data-row-key]'));
      const row = rows[0];
      if (!row) return null;
      const cells = row.querySelectorAll('td');
      const progressCell = Array.from(cells).find(c => /进行|完成|待开始|\d\/\d/.test(c.innerText));
      const passRateCell = Array.from(cells).find(c => /%|通过/.test(c.innerText));
      return {
        progressText: progressCell?.innerText?.trim() || '',
        passRateText: passRateCell?.innerText?.trim() || ''
      };
    });

    if (!beforeStats) {
      log('TC08', '获取任务', 'WARN', '未找到审核任务，跳过');
      await page.close();
      return;
    }
    log('TC08', '操作前进度', 'PASS', `进度: ${beforeStats.progressText}, 通过率: ${beforeStats.passRateText}`);

    // 进入详情
    const detailHref = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a'));
      const dl = links.find(a => a.href.includes('task/detail') || a.textContent.includes('查看详情'));
      return dl ? dl.href : null;
    });

    if (!detailHref) {
      log('TC08', '进入详情', 'WARN', '未找到任务详情链接');
      await page.close();
      return;
    }

    await page.goto(detailHref, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 查找通过/驳回按钮
    const btnInfo = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const passBtn = btns.find(b => b.innerText.includes('通过'));
      const rejectBtn = btns.find(b => b.innerText.includes('驳回') || b.innerText.includes('不通过'));
      return {
        hasPass: !!passBtn,
        hasReject: !!rejectBtn,
        passText: passBtn?.innerText?.trim(),
        rejectText: rejectBtn?.innerText?.trim()
      };
    });

    log('TC08', '通过按钮', btnInfo.hasPass ? 'PASS' : 'FAIL',
      btnInfo.hasPass ? `通过按钮: ${btnInfo.passText}` : '未找到通过按钮');
    log('TC08', '驳回按钮', btnInfo.hasReject ? 'PASS' : 'FAIL',
      btnInfo.hasReject ? `驳回按钮: ${btnInfo.rejectText}` : '未找到驳回按钮');

    // 点击通过
    if (btnInfo.hasPass) {
      const clickResult = await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const passBtn = btns.find(b => b.innerText.includes('通过'));
        if (passBtn) { passBtn.click(); return true; }
        return false;
      });
      log('TC08', '点击通过', clickResult ? 'PASS' : 'FAIL', clickResult ? '已点击通过' : '点击失败');
      await waitForPage(page, 2000);
      await screenshot(page, 'tc08-pass-clicked');

      // 确认弹窗
      const confirmResult = await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('.ant-modal button, .ant-popconfirm button, button'));
        const confirmBtn = btns.find(b => /确定|确认/.test(b.innerText) && b.offsetHeight > 0);
        if (confirmBtn) { confirmBtn.click(); return true; }
        return false;
      });
      log('TC08', '确认通过', confirmResult ? 'PASS' : 'FAIL', confirmResult ? '已确认' : '未找到确认按钮');
      await waitForPage(page, 3000);
      await screenshot(page, 'tc08-pass-confirmed');
    }

    // 返回个人任务中心查看进度/通过率变化
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    const afterStats = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('.ant-table-row, tr[data-row-key]'));
      const row = rows[0];
      if (!row) return null;
      const cells = row.querySelectorAll('td');
      const progressCell = Array.from(cells).find(c => /进行|完成|待开始|\d\/\d/.test(c.innerText));
      const passRateCell = Array.from(cells).find(c => /%|通过/.test(c.innerText));
      return {
        progressText: progressCell?.innerText?.trim() || '',
        passRateText: passRateCell?.innerText?.trim() || ''
      };
    });

    if (afterStats) {
      log('TC08', '操作后进度', 'PASS', `进度: ${afterStats.progressText}, 通过率: ${afterStats.passRateText}`);
      const progressChanged = beforeStats.progressText !== afterStats.progressText;
      log('TC08', '进度更新', progressChanged ? 'PASS' : 'WARN',
        progressChanged ? `进度从"${beforeStats.progressText}"变为"${afterStats.progressText}"` : '进度未变化');
    } else {
      log('TC08', '操作后数据', 'FAIL', '无法读取操作后数据');
    }

    await screenshot(page, 'tc08-after-pass');
  } catch (e) {
    log('TC08', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC09: 抽检任务 / 埋雷任务Tab ──
async function tc09(browser) {
  console.log('\n═══ TC09: 抽检任务/埋雷任务Tab ═══');
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE_URL}/review/personal-task-center`, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForPage(page);

    // 抽检任务
    const spotCheck = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '抽检任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC09', '切换抽检任务', spotCheck ? 'PASS' : 'FAIL', spotCheck ? '成功' : '未找到');
    await waitForPage(page, 2000);

    const spotBody = await page.evaluate(() => document.body.innerText);
    log('TC09', '抽检页面', spotBody.includes('抽检任务') ? 'PASS' : 'FAIL', '抽检任务Tab内容');
    await screenshot(page, 'tc09-spot-check');

    // 埋雷任务
    const landmine = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '埋雷任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC09', '切换埋雷任务', landmine ? 'PASS' : 'FAIL', landmine ? '成功' : '未找到');
    await waitForPage(page, 2000);

    const lmBody = await page.evaluate(() => document.body.innerText);
    log('TC09', '埋雷页面', lmBody.includes('埋雷任务') ? 'PASS' : 'FAIL', '埋雷任务Tab内容');
    await screenshot(page, 'tc09-landmine');

    // 切回审核任务
    const audit = await page.evaluate(() => {
      const items = [...document.querySelectorAll('span, a, div, [role="tab"]')];
      const el = items.find(e => e.textContent.trim() === '审核任务');
      if (el) { el.click(); return true; }
      return false;
    });
    log('TC09', '切回审核任务', audit ? 'PASS' : 'FAIL', audit ? '成功' : '未找到');
    await waitForPage(page, 1000);
  } catch (e) {
    log('TC09', '异常', 'FAIL', e.message);
  }
  await page.close();
}

// ── TC 注册表：ID → {fn, deps, produces, name} ──
const TC_REGISTRY = [
  { id: 'TC01', fn: tc01, deps: [],              name: '个人任务中心' },
  { id: 'TC02', fn: tc02, deps: [],              name: '审核标准管理' },
  { id: 'TC03', fn: tc03, deps: [],              name: '审核节点管理' },
  { id: 'TC04', fn: tc04, deps: [],              name: '任务管理' },
  { id: 'TC05', fn: tc05, deps: [],              name: 'Tab切换+搜索' },
  { id: 'TC06', fn: tc06, deps: [],              name: '任务大厅4来源Tab' },
  { id: 'TC07', fn: tc07, deps: [],              name: '审核详情页工具栏' },
  { id: 'TC08', fn: tc08, deps: ['TC07'],        name: '审核操作-通过/驳回' },
  { id: 'TC09', fn: tc09, deps: [],              name: '抽检/埋雷任务Tab' },
];

// 包装 TC 函数：捕获异常 + 判定 pass/fail
async function wrapTC(regEntry, browser) {
  const beforeLen = results.length;
  try {
    await regEntry.fn(browser);
  } catch (e) {
    log(regEntry.id, '异常', 'FAIL', e.message);
  }
  const tcLogs = results.slice(beforeLen);
  const hasFail = tcLogs.some(r => r.status === 'FAIL');
  return { tc: regEntry.id, name: regEntry.name, status: hasFail ? 'fail' : 'pass', logs: tcLogs };
}

// ── 主入口（DAG 调度） ──
async function main() {
  console.log('🔗 连接 CDP:', CDP_URL);
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  console.log('✅ 已连接 Chrome\n');

  // DAG 分层
  const waves = buildDAGWaves(TC_REGISTRY);
  console.log('📐 DAG 执行计划:');
  waves.forEach((wave, i) => {
    const ids = wave.map(([id]) => id).join(', ');
    const mode = wave.length > 1 ? '并行' : '串行';
    console.log(`   Wave ${i + 1} [${mode}]: ${ids}`);
  });
  console.log('');

  const tcResults = {};  // TC01 → {status, ...}
  const skipped = new Map(); // TC id → skip reason

  for (let wi = 0; wi < waves.length; wi++) {
    const wave = waves[wi];
    const runnable = wave.filter(([id]) => !skipped.has(id));
    const toSkip = wave.filter(([id]) => skipped.has(id));

    // 记录级联 SKIP
    for (const [id, entry] of toSkip) {
      tcResults[id] = { tc: id, name: entry.name, status: 'skip', skipReason: skipped.get(id) };
      console.log(`\n⏭️  [SKIP] ${entry.name}: ${skipped.get(id)}`);
      log(id, 'SKIP', 'WARN', skipped.get(id));
    }

    if (runnable.length === 0) continue;

    // 同 wave：--sequential 模式串行，否则并行
    let waveResults;
    if (SEQUENTIAL && runnable.length > 1) {
      waveResults = [];
      for (const [id, entry] of runnable) {
        console.log(`\n▶️  [Wave ${wi + 1}] 执行: ${entry.name}`);
        try {
          const result = await Promise.race([
            wrapTC(entry, browser),
            new Promise((_, rej) => setTimeout(() => rej(new Error(`执行超时 ${CASE_TIMEOUT_MS}ms`)), CASE_TIMEOUT_MS)),
          ]);
          waveResults.push({ id, entry, result });
        } catch (e) {
          log(id, '超时', 'FAIL', e.message);
          waveResults.push({ id, entry, result: { tc: id, name: entry.name, status: 'fail', error: e.message } });
        }
      }
    } else {
      const promises = runnable.map(async ([id, entry]) => {
        console.log(`\n▶️  [Wave ${wi + 1}] 执行: ${entry.name}`);
        try {
          const result = await Promise.race([
            wrapTC(entry, browser),
            new Promise((_, rej) => setTimeout(() => rej(new Error(`执行超时 ${CASE_TIMEOUT_MS}ms`)), CASE_TIMEOUT_MS)),
          ]);
          return { id, entry, result };
        } catch (e) {
          log(id, '超时', 'FAIL', e.message);
          return { id, entry, result: { tc: id, name: entry.name, status: 'fail', error: e.message } };
        }
      });
      waveResults = await Promise.all(promises);
    }

    for (const { id, entry, result } of waveResults) {
      tcResults[id] = result;
      if (result.status !== 'pass') {
        const downstream = findAllDownstream(id, TC_REGISTRY);
        for (const dsId of downstream) {
          if (!skipped.has(dsId)) skipped.set(dsId, `因 ${entry.name} FAIL 而 SKIP`);
        }
      }
    }
  }

  // 汇总
  console.log('\n═══════════════════════════════');
  console.log('📊 回归结果汇总（DAG 调度）');
  console.log('═══════════════════════════════');
  const allTCs = TC_REGISTRY.map(e => tcResults[e.id]);
  const pass = allTCs.filter(r => r.status === 'pass').length;
  const fail = allTCs.filter(r => r.status === 'fail').length;
  const skip = allTCs.filter(r => r.status === 'skip').length;
  console.log(`TC: ${allTCs.length} 个 | ✅ pass: ${pass} | ❌ fail: ${fail} | ⏭️ skip: ${skip}`);
  allTCs.forEach(r => {
    const icon = r.status === 'pass' ? '✅' : r.status === 'skip' ? '⏭️' : '❌';
    const reason = r.skipReason ? ` (${r.skipReason})` : '';
    console.log(`  ${icon} ${r.tc} ${r.name} (${r.status})${reason}`);
  });

  const logPass = results.filter(r => r.status === 'PASS').length;
  const logFail = results.filter(r => r.status === 'FAIL').length;
  console.log(`\n断言总计: ${results.length} 项 | ✅ PASS: ${logPass} | ❌ FAIL: ${logFail}`);
  console.log(`通过率: ${(logPass / results.length * 100).toFixed(1)}%`);

  if (logFail > 0) {
    console.log('\n❌ 失败项:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  ${r.tc} > ${r.step}: ${r.detail}`);
    });
  }

  // 写结果到文件
  const outputPath = OUTPUT_FILE
    ? require('path').resolve(OUTPUT_FILE)
    : require('path').join(__dirname, '..', 'artifacts', 'regression-results.json');
  fs.writeFileSync(outputPath, JSON.stringify({
    summary: { tc: allTCs.length, pass, fail, skip, assertions: results.length, logPass, logFail },
    tcResults: allTCs,
    results,
  }, null, 2));
  console.log(`\n📁 结果已保存: ${outputPath}`);
}

main().catch(e => { console.error('❌ 回归执行失败:', e.message); process.exit(1); });
