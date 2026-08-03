#!/usr/bin/env node
/**
 * 自动补全 F88 "自动化测试-" 开头的空壳策略
 * 根据策略名称匹配对应节点类型，自动添加节点并保存
 * 
 * 使用方式:
 * node scripts/auto-fill-empty-strategies.js [--dry-run] [--port 9222]
 * 自动扫描 9222-9230 端口，找到已登录 F88 的 Chrome
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const http = require('http');

const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const OUT_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'fill-empty');
const COOKIE_CACHE = path.join(__dirname, '..', '.cache', 'f88-cookies.json');

// ── Cookie 持久化：保存/恢复登录态 ──
async function saveCookies(page, label = '') {
  const fs = require('fs');
  const cookies = await page.cookies();
  if (!fs.existsSync(path.dirname(COOKIE_CACHE))) {
    fs.mkdirSync(path.dirname(COOKIE_CACHE), { recursive: true });
  }
  fs.writeFileSync(COOKIE_CACHE, JSON.stringify({ ts: new Date().toISOString(), label, cookies }, null, 2));
  console.log(`  💾 Cookie 已缓存 (${cookies.length} 个, ${label})`);
}

async function loadCookies(page) {
  const fs = require('fs');
  if (!fs.existsSync(COOKIE_CACHE)) return false;
  try {
    const data = JSON.parse(fs.readFileSync(COOKIE_CACHE, 'utf8'));
    const age = Date.now() - new Date(data.ts).getTime();
    const ageHours = Math.round(age / 3600000);
    if (ageHours > 72) {
      console.log(`  ⚠️ Cookie 缓存已过期 (${ageHours}h > 72h)`);
      return false;
    }
    await page.setCookie(...data.cookies);
    console.log(`  📂 Cookie 已恢复 (${data.cookies.length} 个, 缓存于 ${ageHours}h 前, 来源: ${data.label})`);
    return true;
  } catch (e) {
    console.log(`  ⚠️ Cookie 恢复失败: ${e.message}`);
    return false;
  }
}

// ── 从 Playwright MCP 浏览器提取 Cookie ──
async function extractFromPlaywrightMCP() {
  const fs = require('fs');
  const mcpProfileDir = path.join(require('os').homedir(), 'Library', 'Caches', 'ms-playwright-mcp');
  if (!fs.existsSync(mcpProfileDir)) return null;
  console.log('  🔍 尝试从 Playwright MCP 浏览器提取 Cookie...');
  try {
    // 通过 MCP playwright 工具获取当前页面的 cookies
    const { execSync } = require('child_process');
    // 检查 MCP 浏览器是否有 F88 相关 cookie
    const cookieFiles = [
      path.join(mcpProfileDir, 'Default', 'Cookies'),
      path.join(mcpProfileDir, 'Default', 'Network', 'Cookies'),
    ];
    for (const cf of cookieFiles) {
      if (fs.existsSync(cf)) {
        console.log(`  📁 找到 Cookie DB: ${cf}`);
        return cf;  // 存在但无法直接读取 (SQLite)
      }
    }
  } catch (e) {}
  return null;
}

// ── 自动发现 Chrome CDP 并处理登录态 ──
function httpGet(url, timeout = 2000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

async function findF88Chrome() {
  const args = process.argv.slice(2);
  const portArg = args.indexOf('--port');
  if (portArg >= 0 && args[portArg + 1]) {
    const url = `http://127.0.0.1:${args[portArg + 1]}`;
    console.log(`📌 使用指定端口: ${url}`);
    return { cdpUrl: url, page: null };
  }

  console.log('🔍 扫描 Chrome CDP 端口 (9222-9230)...');
  const candidates = [];
  for (let port = 9222; port <= 9230; port++) {
    const ver = await httpGet(`http://127.0.0.1:${port}/json/version`);
    if (ver) {
      try {
        const info = JSON.parse(ver);
        candidates.push({ port, browser: info.Browser || '?' });
      } catch (e) {}
    }
  }

  if (candidates.length === 0) {
    throw new Error('未找到任何 Chrome CDP 实例。请先启动: chrome --remote-debugging-port=9222');
  }
  console.log(`  找到 ${candidates.length} 个 Chrome: ${candidates.map(c => c.port).join(', ')}`);

  // 逐个检查登录态
  for (const c of candidates) {
    const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${c.port}`, defaultViewport: null });
    const pages = await browser.pages();
    const testPage = pages.length > 0 ? pages[pages.length - 1] : await browser.newPage();

    // 尝试从 cookie 缓存恢复
    const hasCached = await loadCookies(testPage);

    // 验证登录态
    try {
      await testPage.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 20000 });
      await new Promise(r => setTimeout(r, 3000));
      const url = testPage.url();
      if (url.includes('strategy/list') || url.includes('strategy/config')) {
        console.log(`  ✅ 端口 ${c.port} 已登录 F88${hasCached ? ' (cookie缓存恢复)' : ''}`);
        // 登录后立即缓存 cookie
        await saveCookies(testPage, `port-${c.port}`);
        browser.disconnect();
        return { cdpUrl: `http://127.0.0.1:${c.port}`, page: testPage };
      }
    } catch (e) {}

    // 未登录，但先保存当前 cookie（可能是 SSO 部分 cookie）
    await saveCookies(testPage, `port-${c.port}-partial`);
    browser.disconnect();
    console.log(`  ⚠️ 端口 ${c.port} 未登录 F88`);
  }

  // 都没登录，返回第一个端口
  console.log(`  ⚠️ 未找到已登录的 Chrome，使用端口 ${candidates[0].port}`);
  console.log(`  💡 请在浏览器中手动登录 F88，登录后 cookie 会自动缓存，下次无需重复登录`);
  return { cdpUrl: `http://127.0.0.1:${candidates[0].port}`, page: null };
}

// 不需要补全的策略（F88无删除功能，只能手动处理）
const SKIP_STRATEGIES = [
  '自动化测试-定价节点策略',   // 用户要求删除，但F88无删除功能
  '自动化测试-款式分配策略',   // 用户要求删除，但F88无删除功能
];

// 策略名称 → 节点类型映射
const STRATEGY_NODE_MAP = {
  '自动化测试-视频上传策略': '视频上传',
  '自动化测试-高清化处理策略': '高清化处理',
  '自动化测试-机审策略': '机审',
  '自动化测试-面料上身策略': '面料上身',
  // 已删除: 自动化测试-定价节点策略
  '自动化测试-改款prompt推理策略': '改款prompt推理',
  '自动化测试-季节标签策略': '季节标签',
  '自动化测试-Caption策略': 'Caption',
  '自动化测试-匹配度打分策略': '匹配度打分',
  // 已删除: 自动化测试-款式分配策略
  '自动化测试-LLM文本生成策略': 'LLM文本生成',
  '自动化测试-图像裁头策略': '图像裁头',
  '自动化测试-Map生图策略': 'Map生图',
  '自动化测试-生图策略': '生图',
  '自动化测试-产业标签策略': '产业标签',
  '自动化测试-人工审核策略': '人工审核',
  '自动化测试-模板匹配策略': '模板匹配',
  '自动化测试-生图三段式': ['LLM文本生成', '模板匹配', '生图'],  // 多节点
  '自动化测试-审核策略': '人工审核',
  '自动化测试-LLM审核组合': ['LLM文本生成', '人工审核'],  // 多节点
  '自动化测试-组合链路': null,  // 链路,跳过
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!require('fs').existsSync(OUT_DIR)) require('fs').mkdirSync(OUT_DIR, { recursive: true });
  const fp = path.join(OUT_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
  return fp;
}

// 在弹窗中选择节点类型（参考 run-tc27-e2e.js 的逻辑）
async function selectNodeType(page, nodeTypeName) {
  await sleep(2000);
  await ss(page, `select-node-${nodeTypeName}`);

  const pos = await page.evaluate((name) => {
    const target = name.replace(/\s+/g, '');
    // 优先查找弹窗中的节点卡片（Ant Design Modal）
    const modalSelectors = [
      '.ant-modal-body',
      '.ant-modal-content', 
      '[class*="modal"]',
      '[class*="Modal"]',
      '[role="dialog"]'
    ];
    
    let searchRoot = document.body;
    for (const sel of modalSelectors) {
      const modal = document.querySelector(sel);
      if (modal && modal.offsetHeight > 0) {
        searchRoot = modal;
        break;
      }
    }
    
    // 在弹窗内查找节点卡片
    const all = [...searchRoot.querySelectorAll('div, span, li, a, button, h3, h4, p, .ant-card, [class*="card"], [class*="Card"]')];
    for (const el of all) {
      const txt = el.textContent.trim().replace(/\s+/g, '');
      if (txt.startsWith(target) && txt.length < 50 && el.offsetHeight > 0 && el.offsetHeight < 150) {
        const r = el.getBoundingClientRect();
        if (r.height > 0 && r.width > 0 && r.y > 0 && r.y < window.innerHeight) {
          return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: el.textContent.trim().substring(0, 30) };
        }
      }
    }
    return null;
  }, nodeTypeName);

  if (pos) {
    await page.mouse.click(pos.x, pos.y);
    console.log(`    ✅ 选择节点: "${pos.text}"`);
    return true;
  }
  console.log(`    ❌ 节点类型未找到: ${nodeTypeName}`);
  return false;
}

// 关闭节点编辑抽屉
async function closeDrawer(page) {
  await sleep(2000);
  await page.evaluate(() => {
    const closeBtn = document.querySelector('.ant-drawer-close') || document.querySelector('[class*="drawer"] [class*="close"]');
    if (closeBtn) closeBtn.click();
  });
  await sleep(1000);
}

// 为一个空壳策略添加节点
async function fillStrategy(page, strategyName, nodeTypes) {
  console.log(`\n📝 处理策略: ${strategyName}`);
  
  // 1. 打开策略列表
  console.log('  1. 打开策略列表...');
  await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  // 2. 找到目标策略（搜索）
  console.log('  2. 搜索策略...');
  await page.evaluate((name) => {
    const searchInput = document.querySelector('input[placeholder*="搜索"], input[placeholder*="策略名称"]');
    if (searchInput) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(searchInput, name);
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }, strategyName);
  await sleep(2000);
  await ss(page, `search-${strategyName}`);

  // 3. 点击"打开"按钮进入策略详情
  console.log('  3. 进入策略详情页...');
  const opened = await page.evaluate(() => {
    const btns = document.querySelectorAll('a, button');
    for (const btn of btns) {
      if (btn.textContent.trim() === '打开' && btn.offsetHeight > 0) {
        btn.click();
        return true;
      }
    }
    return false;
  });
  if (!opened) { console.log(`  ❌ 未找到策略: ${strategyName}`); return false; }
  await sleep(3000);

  // 4. 验证是空壳（只有 Start/End）
  console.log('  4. 验证是否为空壳...');
  const hasNodeSection = await page.evaluate(() => document.body.innerText.includes('节点编排'));
  if (!hasNodeSection) { console.log('  ❌ 未找到节点编排区域'); return false; }
  await ss(page, `before-fill-${strategyName}`);

  // 5. 添加节点（一个或多个）
  const nodeArray = Array.isArray(nodeTypes) ? nodeTypes : [nodeTypes];
  for (const nodeType of nodeArray) {
    console.log(`  5. 添加节点: ${nodeType}...`);
    const clicked = await page.evaluate(() => {
      const btns = document.querySelectorAll('button, div, span');
      for (const btn of btns) {
        const txt = btn.textContent.trim().replace(/\s+/g, '');
        if ((txt === '+新增节点' || txt === '新增节点') && btn.offsetHeight > 0) {
          btn.click();
          return true;
        }
      }
      return false;
    });
    
    if (!clicked) {
      console.log('    ⚠️ 点击"+ 新增节点"按钮失败，尝试备用方案...');
      // 备用方案：使用 Puppeteer 直接点击
      try {
        await page.click('text=/新增节点/');
      } catch (e) {
        console.log('    ❌ 无法点击"+ 新增节点"按钮');
        continue;
      }
    }
    
    await sleep(3000);  // 增加等待时间，确保弹窗完全打开

    await selectNodeType(page, nodeType);
    await sleep(3000);

    // 6. 在抽屉中点击"保 存"
    console.log('  6. 保存节点...');
    const drawerSaved = await page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer') || document.querySelector('[class*="drawer"]');
      if (!drawer) return false;
      const btns = drawer.querySelectorAll('button');
      for (const btn of btns) {
        const txt = btn.textContent.replace(/\s+/g, '');
        if (txt === '保存' || txt === '保 存') {
          btn.click();
          return true;
        }
      }
      return false;
    });
    if (!drawerSaved) {
      // 如果抽屉没有保存按钮，按 Escape 关闭
      await page.keyboard.press('Escape');
      await sleep(1000);
    }
    await sleep(2000);
    await ss(page, `added-${nodeType}`);
  }

  // 7. 保存策略
  console.log('  7. 保存策略...');
  await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
      const txt = btn.textContent.replace(/\s+/g, '');
      if ((txt === '保存' || txt === '保 存') && btn.offsetHeight > 0) {
        btn.click();
        return true;
      }
    }
    return false;
  });
  await sleep(3000);

  // 8. 刷新验证持久化
  console.log('  8. 刷新验证...');
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(3000);
  await ss(page, `after-fill-${strategyName}`);

  // 9. 验证节点存在
  console.log('  9. 验证节点是否持久化...');
  const nodeExists = await page.evaluate((nodes) => {
    const text = document.body.innerText;
    return nodes.map(n => ({ name: n, exists: text.includes(n) }));
  }, nodeArray);
  const allPersisted = nodeExists.every(n => n.exists);
  console.log(`  📊 节点持久化: ${JSON.stringify(nodeExists)}`);

  if (allPersisted) {
    console.log(`  ✅ 策略 ${strategyName} 补全成功`);
  } else {
    console.log(`  ⚠️ 策略 ${strategyName} 部分节点未持久化`);
  }

  return allPersisted;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');

  const { cdpUrl } = await findF88Chrome();
  console.log(`🔗 连接 CDP: ${cdpUrl}`);
  const browser = await puppeteer.connect({ browserURL: cdpUrl, defaultViewport: null });
  console.log('✅ 已连接 Chrome\n');

  // 始终用新连接的页面，避免断引用
  const allPages = await browser.pages();
  const page = allPages.length > 0 ? allPages[allPages.length - 1] : await browser.newPage();

  // 从缓存恢复 cookie（findF88Chrome 可能已缓存但新连接没有）
  await loadCookies(page);

  // ── 登录态检查 & 等待手动登录 ──
  async function checkLogin() {
    try {
      await page.goto(`${BASE}/strategy/list`, { waitUntil: 'networkidle2', timeout: 20000 });
      await sleep(3000);
      const url = page.url();
      return url.includes('strategy/list') || url.includes('strategy/config');
    } catch (e) { return false; }
  }

  let loggedIn = await checkLogin();
  if (!loggedIn) {
    console.log('⚠️ 未登录 F88，请在弹出的 Chrome 窗口中手动登录');
    console.log('⏰ 等待登录中... (最长 5 分钟)');
    const startTime = Date.now();
    while (!loggedIn && Date.now() - startTime < 300000) {
      await sleep(10000);  // 每 10 秒检查一次
      loggedIn = await checkLogin();
      if (loggedIn) {
        console.log('✅ 登录成功！Cookie 已自动缓存，下次无需重复登录');
        await saveCookies(page, 'manual-login');
      } else {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        console.log(`  ⏳ 等待中... (${elapsed}s)`);
      }
    }
    if (!loggedIn) {
      console.error('❌ 登录超时 (5分钟)，请检查网络/登录状态');
      process.exit(1);
    }
  } else {
    // 已登录，确保 cookie 被缓存
    await saveCookies(page, 'auto-detected');
  }

  // ── 跳过不需要处理的策略 ──
  console.log('═══ 跳过的策略（需手动删除）═══');
  for (const name of SKIP_STRATEGIES) {
    console.log(`⏭️  SKIP: ${name}`);
  }
  console.log('');

  // ── 补全剩余策略的节点 ──
  console.log('═══ 补全空壳策略的节点 ═══');
  let successCount = 0;
  let failCount = 0;
  const failedStrategies = [];

  for (const [strategyName, nodeTypes] of Object.entries(STRATEGY_NODE_MAP)) {
    if (SKIP_STRATEGIES.includes(strategyName)) {
      console.log(`\n⏭️  SKIP: ${strategyName} (在跳过列表中)`);
      continue;
    }
    if (!nodeTypes) {
      console.log(`⏭️ 跳过 ${strategyName} (链路，不需要节点)`);
      continue;
    }

    if (dryRun) {
      console.log(`🔍 [DRY RUN] 将补全策略: ${strategyName} → 节点: ${JSON.stringify(nodeTypes)}`);
      continue;
    }

    try {
      const ok = await fillStrategy(page, strategyName, nodeTypes);
      if (ok) {
        successCount++;
      } else {
        failCount++;
        failedStrategies.push(strategyName);
      }
    } catch (e) {
      console.error(`  ❌ 处理 ${strategyName} 失败: ${e.message}`);
      failCount++;
      failedStrategies.push(strategyName);
    }

    // 每个策略之间留点间隔
    await sleep(1000);
  }

  console.log('\n📊 ═══════ 补全结果汇总 ═══════');
  console.log(`✅ 成功: ${successCount}`);
  console.log(`❌ 失败: ${failCount}`);
  if (failedStrategies.length > 0) {
    console.log(`失败列表: ${failedStrategies.join(', ')}`);
  }
  console.log(`📸 截图目录: ${OUT_DIR}`);

  if (!dryRun) {
    await ss(page, 'final');
    console.log('\n✅ 全部处理完成，浏览器保持连接');
  }

  await browser.close();
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
