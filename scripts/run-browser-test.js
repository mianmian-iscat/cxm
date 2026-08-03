#!/usr/bin/env node
/**
 * web-automation 主执行框架
 *
 * 用法：
 *   node run-browser-test.js input.json [output.json]
 *   node run-browser-test.js '{"id":"...","steps":[...]}' [output.json]
 *
 * 输入：符合 schema/input.schema.json 的 JSON
 * 输出：符合 schema/output.schema.json 的 JSON（写文件或打印到 stdout）
 */

'use strict';

// puppeteer-core 自动探测（本地 node_modules > OpenClaw 内置 > 全局）
function resolvePuppeteer() {
  const path = require('path');
  const env = process.env.WEB_AUTO_PUPPETEER_PATH;
  const candidates = [
    ...(env && env !== 'auto' ? [env] : []),
    path.join(__dirname, '..', 'node_modules', 'puppeteer-core'),
    '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core',
    'puppeteer-core',
  ];
  for (const p of candidates) {
    try { require.resolve(p); return require(p); } catch (_) {}
  }
  throw new Error('找不到 puppeteer-core，请在 web-automation/ 目录下运行: npm install');
}
const puppeteer = resolvePuppeteer();
const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ── 轻量自愈引擎（JS 侧，对标 core/self_healing.py 的 5 种高频策略）──
const { SelfHealingLite } = require(path.join(__dirname, 'self-healing-lite.js'));
// shared/browser-cdp 优先；缺失时降级为自包含实现（本地开发副本无 shared 目录）
let capturePageScreenshot, ensureJpegPath;
try {
  const SHARED_CDP = require(path.join(__dirname, '..', '..', 'shared', 'browser-cdp'));
  capturePageScreenshot = SHARED_CDP.capturePageScreenshot;
  ensureJpegPath = SHARED_CDP.ensureJpegPath;
} catch (_) {
  ensureJpegPath = (p) => (/\.(jpe?g)$/i.test(p) ? p : `${p}.jpg`);
  capturePageScreenshot = async (page, filePath) => {
    await page.screenshot({ path: filePath, type: 'jpeg', quality: 70 });
    return filePath;
  };
}

const SCREENSHOT_DIR = process.env.WEB_AUTO_SCREENSHOTS_DIR ||
  path.join(__dirname, '..', 'artifacts', 'screenshots');
const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';

// 跨 step 变量存储（evaluate/apiCall 可通过 storeAs 写入，后续 step 通过 ${store.key} 读取）
const globalStore = {};

// ─────────────────────────────────────────────
// 主入口
// ─────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  if (!args[0]) {
    console.error('Usage: node run-browser-test.js <input.json|JSON string> [output.json]');
    process.exit(1);
  }

  // 读取输入
  let input;
  try {
    const raw = args[0].trim().startsWith('{') ? args[0] : fs.readFileSync(args[0], 'utf8');
    input = JSON.parse(raw);
  } catch (e) {
    console.error('输入解析失败:', e.message);
    process.exit(1);
  }

  const output = await runTest(input);

  // 写输出
  const outJson = JSON.stringify(output, null, 2);
  if (args[1]) {
    fs.writeFileSync(args[1], outJson);
    console.error(`结果已写入: ${args[1]}`);
  } else {
    console.log(outJson);
  }

  process.exit(output.status === 'error' ? 1 : 0);
}

// ─────────────────────────────────────────────
// 核心执行函数（可被其他脚本 require 调用）
// ─────────────────────────────────────────────
async function runTest(input) {
  const startTime = Date.now();
  const output = {
    id: input.id,
    name: input.name,
    status: 'pass',
    startTime: new Date().toISOString(),
    duration: 0,
    steps: [],
    screenshots: [],
    capture: { requests: [] },
  };

  const screenshotDir = input.screenshot?.dir || SCREENSHOT_DIR;
  fs.mkdirSync(screenshotDir, { recursive: true });

  let browser, page, client;
  let pageCreatedByUs = false;  // 标记是否由本次执行创建的 page

  // ── 自愈引擎单例（统计信息跨 step 累计）──
  const healer = new SelfHealingLite();

  try {
    // ── 连接浏览器 ──
    browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
    const pages = await browser.pages();

    // 清理已有的空白 tab（about:blank），防止批量执行时 tab 累积
    for (const p of pages) {
      const url = p.url();
      if (url === 'about:blank' && pages.indexOf(p) > 0) {
        try { await p.close(); } catch (_) {}
      }
    }

    // 始终创建新 page，避免跨用例状态污染和 detached frame 问题
    page = await browser.newPage();
    pageCreatedByUs = true;
    if (input.context?.url) {
      await page.goto(input.context.url, { waitUntil: 'networkidle2', timeout: 30000 });
    }

    // ── 初始化 CDP session ──
    client = await page.target().createCDPSession();

    // 最大化窗口（健壮化：先 restore 到 normal 再 maximize，避免从 minimized/fullscreen 直接 maximize 报错；整体降级不阻断用例）
    try {
      const { windowId } = await client.send('Browser.getWindowForTarget');
      try {
        await client.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } });
        await sleep(150);
      } catch (e) { /* 已是 normal 时忽略 */ }
      await client.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'maximized' } });
      await sleep(300);
      const { bounds } = await client.send('Browser.getWindowBounds', { windowId });
      await page.setViewport({ width: bounds.width, height: bounds.height, deviceScaleFactor: 1 });
    } catch (e) {
      console.warn('窗口最大化失败，降级继续执行:', e.message);
    }

    // ── 启动网络监听 ──
    if (input.capture?.enabled !== false) {
      await startCapture(client, output.capture, input.capture || {});
    }

    // 等待页面渲染
    await sleep(input.context?.waitAfterLoad ?? 2000);

    // ── 执行 steps ──
    let lastAPIResponse = null;
    let lastDBResult = null;

    for (let i = 0; i < input.steps.length; i++) {
      const rawStep = input.steps[i];
      const step = resolveStepVars(rawStep, globalStore);
      const stepStart = Date.now();
      const stepResult = {
        index: i,
        type: step.type,
        description: step.description || '',
        status: 'pass',
        duration: 0,
      };

      // P0-3: step 级重试机制 — step.retry 指定重试次数（默认 0）
      const maxRetries = step.retry || 0;
      const retryDelay = step.retryDelay || 1000;
      let lastError = null;

      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        if (attempt > 0) {
          console.error(`[retry] step${i} ${step.type} 第 ${attempt}/${maxRetries} 次重试...`);
          await sleep(retryDelay);
        }
      try {
        switch (step.type) {
          case 'click':
          case 'clickText':
            await execClick(page, step);
            break;

          case 'selectOption':
            await execSelectOption(page, step);
            break;

          case 'pressKey':
            await execPressKey(page, step);
            break;

          case 'hover':
            await execHover(page, step);
            break;

          case 'upload':
            await execUpload(page, step);
            break;

          case 'evaluate':
            stepResult.evalResult = await execEvaluate(page, step);
            break;

          case 'apiCall':
            stepResult.apiResult = await execApiCall(page, step);
            lastAPIResponse = stepResult.apiResult;
            break;

          case 'dataSetup': {
            // 数据自愈/造数 + 自查闭环：造数 → 自查 → 失败 → 重建 → 再验证（最多 maxRetry 轮）
            const maxRetry = step.maxRetry !== undefined ? step.maxRetry : 2;
            const verifyChecks = step.verifyChecks || ['contract', 'landing', 'safety'];
            let setupOk = false;
            let lastVerify = null;
            for (let attempt = 0; attempt <= maxRetry; attempt++) {
              if (attempt > 0) {
                console.error(`[dataSetup] 🔄 第 ${attempt} 次重建（上轮自查未通过）...`);
                await sleep(2000); // 等待异步落池
              }
              stepResult.setupResult = await execDataSetup(page, step);
              if (step.storeAs) globalStore[step.storeAs] = stepResult.setupResult;
              // 造数后立即自查
              const verifyStep = { sourceKey: step.storeAs || 'setupResult', checks: verifyChecks, identity: step.params && step.params.identity || 'f88' };
              lastVerify = await execPostSetupVerify(page, verifyStep, globalStore);
              if (lastVerify.passed && !lastVerify.blocked) {
                setupOk = true;
                break;
              }
              console.error(`[dataSetup] ⚠ 自查未通过（attempt=${attempt}）: ${lastVerify.failedChecks}/${lastVerify.totalChecks} 项失败`);
            }
            stepResult.verifyResult = lastVerify;
            if (!setupOk && lastVerify && lastVerify.blocked) {
              stepResult.status = 'fail';
              output.status = 'fail';
            }
            break;
          }

          case 'postSetupVerify':
            // 造数自查（独立步骤模式，向后兼容）
            stepResult.verifyResult = await execPostSetupVerify(page, step, globalStore);
            if (stepResult.verifyResult && stepResult.verifyResult.blocked) {
              stepResult.status = 'fail';
              output.status = 'fail';
            }
            break;

          case 'dbQuery':
            stepResult.dbResult = await execDbQuery(step);
            lastDBResult = stepResult.dbResult;
            break;

          case 'assertDbResult':
            stepResult.assertResult = await execAssertDbResult(step, lastDBResult);
            if (!stepResult.assertResult.pass) {
              stepResult.status = 'fail';
              output.status = 'fail';
            }
            break;

          case 'assertStore':
            stepResult.assertResult = await execAssertStore(step, globalStore);
            if (!stepResult.assertResult.pass) {
              stepResult.status = 'fail';
              output.status = 'fail';
            }
            break;

          case 'fill':
            await execFill(page, step);
            break;

          case 'wait':
            await sleep(step.ms);
            break;

          case 'waitForAPI': {
            const req = await waitForAPI(client, step.urlPattern, step.timeout || 10000);
            lastAPIResponse = req;
            if (step.storeAs) {
              globalStore[step.storeAs] = req;
            }
            break;
          }

          case 'screenshot': {
            const p = await takeScreenshot(page, client, `${input.id}-step${i}-${step.label}`, screenshotDir);
            stepResult.screenshotPath = p;
            output.screenshots.push({ stepIndex: i, label: step.label, path: p });
            break;
          }

          case 'assert':
            stepResult.assertResult = await execAssert(page, step, lastAPIResponse);
            if (!stepResult.assertResult.pass) {
              stepResult.status = 'fail';
              output.status = 'fail';
            }
            break;

          case 'navigate': {
            const wu = step.waitUntil === 'networkidle' ? 'networkidle2' : (step.waitUntil || 'networkidle2');
            try {
              if (step.url === 'current' || step.url === 'reload') {
                await page.reload({ waitUntil: wu, timeout: 30000 });
              } else {
                await page.goto(step.url, { waitUntil: wu, timeout: 30000 });
              }
            } catch (navErr) {
              // SPA 重定向可能导致 ERR_ABORTED，降级为 domcontentloaded 重试
              if (navErr.message && navErr.message.includes('ERR_ABORTED')) {
                await new Promise(r => setTimeout(r, 1000));
                try {
                  await page.goto(step.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
                } catch (_) {
                  // 页面已在导航中，忽略
                }
              } else {
                throw navErr;
              }
            }
            break;
          }

          default:
            stepResult.status = 'skip';
            stepResult.error = `未知 step 类型: ${step.type}`;
        }

        // 步骤级别截图
        if (step.screenshot && step.type !== 'screenshot') {
          const p = await takeScreenshot(page, client, `${input.id}-step${i}-after`, screenshotDir);
          stepResult.screenshotPath = p;
          output.screenshots.push({ stepIndex: i, label: `step${i}-after`, path: p });
        }

        // onEachStep 截图
        if (input.screenshot?.onEachStep && step.type !== 'screenshot') {
          const p = await takeScreenshot(page, client, `${input.id}-step${i}`, screenshotDir);
          output.screenshots.push({ stepIndex: i, label: `step${i}`, path: p });
        }

      } catch (e) {
        lastError = e;
        // 如果还有重试机会，跳过自愈直接重试
        if (attempt < maxRetries) continue;
      
        // ── 自愈桥：失败时自动尝试 5 种策略（知识库 / CDP 重定位 / 候选列表 / 文本兖底 / 网络重试）──
        if (input.healing?.enabled !== false) {
          try {
            const healed = await healer.tryHeal(page, step, e);
            if (healed.success) {
              stepResult.status = 'healed';
              stepResult.error = e.message; // 保留原始错误
              stepResult.healing = healed;   // 自愈详情（策略 / 新 selector / 原因）
              stepResult.duration = Date.now() - stepStart;
              output.steps.push(stepResult);
              output.healingStats = healer.getStats();
              console.error(`[heal] step${i} ${step.type} 自愈成功 (${healed.strategy}): ${healed.reason || healed.healedSelector || ''}`);
              continue; // 继续下一步
            }
          } catch (healErr) {
            console.error(`[heal] 自愈逻辑自身异常: ${healErr.message}`);
          }
        }

        stepResult.status = 'error';
        stepResult.error = lastError.message;
        if (maxRetries > 0) stepResult.retries = maxRetries;
        output.status = 'error';
        output.error = { stepIndex: i, message: lastError.message, stack: lastError.stack };
        output.healingStats = healer.getStats();

        // 出错截图
        if (input.screenshot?.onError !== false) {
          try {
            const p = await takeScreenshot(page, client, `${input.id}-error-step${i}`, screenshotDir);
            output.screenshots.push({ stepIndex: -1, label: `error-step${i}`, path: p });
          } catch (_) {}
        }
        break; // 出错停止执行
      }
      } // end retry loop

      stepResult.duration = Date.now() - stepStart;
      output.steps.push(stepResult);
    }

    // ── 执行 post_asserts（基于抓包结果的 API 断言）──
    if (Array.isArray(input.post_asserts) && input.post_asserts.length) {
      for (const pa of input.post_asserts) {
        const paResult = { type: 'post_assert', assertType: pa.type, description: pa.description || '', status: 'pass' };
        if (pa.type === 'apiResponse') {
          let req = null;
          try {
            const re = new RegExp(pa.urlPattern);
            req = [...output.capture.requests].reverse().find(r => re.test(r.url));
          } catch (_) {
            req = [...output.capture.requests].reverse().find(r => r.url.includes(pa.urlPattern));
          }
          if (!req) {
            paResult.status = 'fail';
            paResult.error = `未捕获匹配 API: ${pa.urlPattern}`;
            output.status = 'fail';
          } else {
            const actual = getByPath(req.responseBody, pa.path);
            const pass = JSON.stringify(actual) === JSON.stringify(pa.equals);
            paResult.expected = pa.equals;
            paResult.actual = actual;
            paResult.pass = pass;
            if (!pass) { paResult.status = 'fail'; output.status = 'fail'; }
          }
        } else {
          paResult.status = 'skip';
          paResult.error = `不支持的 post_assert 类型: ${pa.type}`;
        }
        output.steps.push(paResult);
      }
    }

    // 导出 HAR
    if (input.capture?.exportHAR) {
      const harPath = path.join(screenshotDir, `${input.id}.har`);
      exportHAR(output.capture.requests, harPath);
      output.capture.harPath = harPath;
    }

  } catch (e) {
    output.status = 'error';
    output.error = { stepIndex: -1, message: e.message, stack: e.stack };
  } finally {
    // 关闭本次创建的 page，防止批量执行时 tab 累积
    if (pageCreatedByUs && page) {
      try { await page.close(); } catch (_) {}
    }
    if (browser) browser.disconnect();
  }

  output.duration = Date.now() - startTime;
  return output;
}

// ─────────────────────────────────────────────
// Step 执行器
// ─────────────────────────────────────────────

async function execClick(page, step) {
  if (step.text) {
    if (step.within) {
      // within 模式：在所有匹配的容器内查找文本，用真实鼠标点击（兼容 antd Select dropdown、多 modal 场景）
      await page.waitForSelector(step.within, { timeout: 5000 });
      const pos = await page.evaluate(({ text, within }) => {
        const containers = document.querySelectorAll(within);
        for (const container of containers) {
          const allEls = container.querySelectorAll('*');
          let el = Array.from(allEls).find(e => e.offsetParent !== null && e.innerText?.trim() === text);
          if (!el) {
            const cands = Array.from(allEls).filter(e => e.offsetParent !== null && e.innerText?.trim().includes(text));
            cands.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
            el = cands[0];
          }
          if (el) {
            // 如果元素在 ant-card 内，点击卡片中心而非文本元素
            const card = el.closest('.ant-card-hoverable, .ant-card');
            const target = card || el;
            const r = target.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
        return null;
      }, { text: step.text, within: step.within });
      if (!pos) throw new Error(`在"${step.within}"内找不到文本为"${step.text}"的元素`);
      await page.mouse.click(pos.x, pos.y);
    } else {
      // 普通文本匹配模式
      const clicked = await page.evaluate((text) => {
        const els = Array.from(document.querySelectorAll('button, a, [role="button"], [class*="btn"], span, [class*="nodeItem"], [class*="node-item"], [class*="NodeItem"]'))
          .filter(e => e.offsetParent !== null);
        let el = els.find(e => e.innerText?.trim() === text);
        if (!el) {
          const cands = els.filter(e => e.innerText?.trim().includes(text));
          cands.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
          el = cands[0];
        }
        if (el) { el.click(); return true; }
        return false;
      }, step.text);
      if (!clicked) throw new Error(`找不到文本为"${step.text}"的可点击元素`);
    }
  } else if (step.selector) {
    await page.waitForSelector(step.selector, { timeout: 5000 });
    // 检测元素上下文：是否在抽屉/弹窗内，是否为 Ant Design Select
    const elInfo = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const drawer = el.closest('.ant-drawer:not(.ant-drawer-hidden)');
      const modal = el.closest('.ant-modal:not(.ant-modal-hidden)');
      const isSelectSelector = !!(el.closest('.ant-select') || el.classList.contains('ant-select-selector'));
      const r = el.getBoundingClientRect();
      const inDrawer = !!drawer;
      const inViewport = r.x >= 0 && r.x + r.width / 2 <= window.innerWidth;
      return { inDrawer, inViewport, inModal: !!modal, isSelectSelector, cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
    }, step.selector);
    if (!elInfo) throw new Error(`找不到元素: ${step.selector}`);

    if (elInfo.inDrawer && !elInfo.inViewport) {
      // 抽屉超出视口：修复抽屉位置 + dispatchEvent(mousedown)
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        const drawer = el.closest('.ant-drawer:not(.ant-drawer-hidden)');
        const wrapper = drawer?.querySelector('.ant-drawer-content-wrapper');
        if (wrapper) {
          Array.from(wrapper.classList).filter(c => c.includes('motion')).forEach(c => wrapper.classList.remove(c));
          wrapper.style.transform = `translateX(-${wrapper.getBoundingClientRect().width}px)`;
          wrapper.style.transition = 'none';
        }
        const mask = drawer?.querySelector('.ant-drawer-mask');
        if (mask) mask.style.pointerEvents = 'none';
      }, step.selector);
      await sleep(300);
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      }, step.selector);
    } else if (elInfo.isSelectSelector) {
      // Ant Design Select：使用 dispatchEvent(mousedown) 可靠展开下拉
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      }, step.selector);
    } else {
      // 普通元素：真实鼠标点击
      const pos = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        el.scrollIntoView({ block: 'center', inline: 'center' });
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }, step.selector);
      if (!pos) throw new Error(`找不到元素: ${step.selector}`);
      await page.mouse.click(pos.x, pos.y);
    }
  } else {
    throw new Error('click step 必须提供 text 或 selector');
  }
  await sleep(300);
}

async function execFill(page, step) {
  await page.waitForSelector(step.selector, { timeout: 5000 });
  // 先获取元素坐标，用真实鼠标点击聚焦
  const pos = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, step.selector);
  if (!pos) throw new Error(`找不到元素: ${step.selector}`);
  await page.mouse.click(pos.x, pos.y);
  await sleep(100);
  // 全选并删除已有内容
  await page.keyboard.down('Meta');
  await page.keyboard.press('a');
  await page.keyboard.up('Meta');
  await page.keyboard.press('Backspace');
  await sleep(100);
  // 用键盘输入新值
  await page.keyboard.type(step.value, { delay: 30 });
  await sleep(100);
  // 点击其他区域触发 blur 和校验
  await page.mouse.click(10, 10);
  await sleep(300);
}

async function execAssert(page, step, lastAPIResponse) {
  if (step.target === 'page') {
    const text = await page.evaluate(() => document.body.innerText);
    return {
      expected: step.contains,
      actual: text.includes(step.contains) ? '(包含)' : '(不包含)',
      pass: text.includes(step.contains),
    };
  } else if (step.target === 'api') {
    if (!lastAPIResponse) {
      return { expected: step.contains, actual: '(无 API 响应)', pass: false };
    }
    const body = typeof lastAPIResponse.responseBody === 'string'
      ? lastAPIResponse.responseBody
      : JSON.stringify(lastAPIResponse.responseBody);
    return {
      expected: step.contains,
      actual: body.includes(step.contains) ? '(包含)' : '(不包含)',
      pass: body.includes(step.contains),
    };
  }
  throw new Error(`不支持的 assert target: ${step.target}`);
}

// Ant Design Select：按 label 定位下拉框，用 page.mouse.click 物理点击展开后选 option
async function execSelectOption(page, step) {
  const pos = await page.evaluate((label) => {
    const selects = Array.from(document.querySelectorAll('.ant-select'));
    let target = null;
    // 策略1：通过 .ant-form-item 父元素中的 .ant-form-item-label 匹配
    for (const sel of selects) {
      const formItem = sel.closest('.ant-form-item');
      const lbl = formItem?.querySelector('.ant-form-item-label')?.textContent || '';
      if (lbl.includes(label)) { target = sel; break; }
    }
    // 策略2：向上遍历找到含 label 文本的祖先容器
    if (!target) {
      for (const sel of selects) {
        let el = sel.parentElement;
        for (let i = 0; i < 5 && el; i++) {
          const lblEl = el.querySelector('.ant-form-item-label, label, [class*=label]');
          if (lblEl && lblEl.textContent.includes(label)) { target = sel; break; }
          el = el.parentElement;
        }
        if (target) break;
      }
    }
    // 策略3：fallback - select 自身文本包含 label
    if (!target) target = selects.find(s => (s.textContent || '').includes(label));
    if (!target) return null;
    const selector = target.querySelector('.ant-select-selector') || target;
    const r = selector.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, step.label);
  if (!pos) throw new Error(`找不到 label 为"${step.label}"的下拉框`);
  // 使用 page.mouse.click 真实鼠标点击，antd Select 的 .click() 不会触发下拉
  await page.mouse.click(pos.x, pos.y);
  await sleep(1000);
  // 在 body 级别查找 antd dropdown（它挂载在 body 下而非 form-item 内）
  const picked = await page.evaluate((option) => {
    const dropdowns = Array.from(document.querySelectorAll('.ant-select-dropdown'));
    const visible = dropdowns.filter(d => d.offsetHeight > 0 && !d.classList.contains('ant-select-dropdown-hidden'));
    for (const dd of visible) {
      const opts = Array.from(dd.querySelectorAll('.ant-select-item-option, .ant-select-item'));
      let el = opts.find(e => e.textContent?.trim() === option);
      if (!el) el = opts.find(e => e.textContent?.trim().includes(option));
      if (el) {
        const r = el.getBoundingClientRect();
        return { found: true, x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    return { found: false };
  }, step.option);
  if (!picked.found) throw new Error(`下拉中找不到选项"${step.option}"`);
  // 用真实鼠标点击选项，antd 才会关闭 dropdown
  await page.mouse.click(picked.x, picked.y);
  await sleep(500);
  // 确保 dropdown 已关闭，否则按 Escape
  const stillOpen = await page.evaluate(() => {
    const dds = Array.from(document.querySelectorAll('.ant-select-dropdown'));
    return dds.some(d => d.offsetHeight > 0 && !d.classList.contains('ant-select-dropdown-hidden'));
  });
  if (stillOpen) {
    await page.keyboard.press('Escape');
    await sleep(300);
  }
}

async function execPressKey(page, step) {
  await page.keyboard.press(step.key);
  await sleep(200);
}

// hover：鼠标移到指定元素上（触发 hover 态 UI，如工具栏、tooltip）
// step: { type:'hover', selector?, text? }
async function execHover(page, step) {
  if (step.selector) {
    await page.waitForSelector(step.selector, { timeout: 5000 });
    await page.hover(step.selector);
  } else if (step.text) {
    const pos = await page.evaluate((text) => {
      const els = Array.from(document.querySelectorAll('*'))
        .filter(e => e.offsetParent !== null && e.innerText?.trim().includes(text));
      els.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
      const el = els[0];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }, step.text);
    if (!pos) throw new Error(`找不到包含文本"${step.text}"的元素`);
    await page.mouse.move(pos.x, pos.y);
  } else {
    throw new Error('hover step 必须提供 selector 或 text');
  }
  await sleep(400);
}

// upload：上传文件到隐藏 input[type=file]（puppeteer uploadFile 无需可见）
// step: { type:'upload', filePath|filePaths, selector? }
async function execUpload(page, step) {
  const files = step.filePaths || (step.filePath ? [step.filePath] : []);
  if (!files.length) throw new Error('upload step 必须提供 filePath 或 filePaths');
  const absFiles = files.map(f => path.isAbsolute(f) ? f : path.resolve(process.cwd(), f));
  for (const f of absFiles) {
    if (!fs.existsSync(f)) throw new Error(`上传文件不存在: ${f}`);
  }
  let handle = null;
  if (step.selector) {
    await page.waitForSelector(step.selector, { timeout: 5000 }).catch(() => {});
    handle = await page.$(step.selector);
  } else {
    const inputs = await page.$$('input[type=file]');
    handle = inputs.length ? inputs[inputs.length - 1] : null;
  }
  if (!handle) throw new Error('找不到文件上传 input[type=file]');
  await handle.uploadFile(...absFiles);
  await sleep(800);
}

// evaluate：在页面上下文中执行 JS，可读取/操作页面状态
// step: { type:'evaluate', expression|script, storeAs? }
async function execEvaluate(page, step) {
  const script = step.expression || step.script;
  if (!script) throw new Error('evaluate step 必须提供 expression 或 script');
  // 确保 IIFE 的返回值被外层函数 return
  let fnBody = script;
  if (!fnBody.trimStart().startsWith('return')) {
    fnBody = 'return ' + fnBody;
  }
  const result = await page.evaluate(new Function(fnBody));
  if (step.storeAs) {
    globalStore[step.storeAs] = result;
  }
  return { result };
}

// apiCall：在页面上下文中调用 MTOP/fetch API
// step: { type:'apiCall', api, v?, data?, method?, body?, timeout?, storeAs?, expectStatus? }
async function execApiCall(page, step) {
  const timeout = step.timeout || 10000;
  const result = await page.evaluate((api, v, data, method, body) => {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`apiCall 超时: ${api}`)), 10000);
      if (window.lib && window.lib.mtop && window.lib.mtop.request) {
        window.lib.mtop.request({
          api,
          v: v || '1.0',
          data: data || {},
          needLogin: true,
          type: method === 'POST' ? 'POST' : 'GET'
        }).then(res => { clearTimeout(timer); resolve(res); })
          .catch(err => { clearTimeout(timer); reject(err); });
      } else if (window.fetch) {
        const url = api;
        const opts = { method: method || 'GET', credentials: 'include' };
        if (body) opts.body = typeof body === 'string' ? body : JSON.stringify(body);
        fetch(url, opts)
          .then(r => {
            // P0-4: 捕获 HTTP 状态码
            const status = r.status;
            return r.text().then(t => {
              let parsed; try { parsed = JSON.parse(t); } catch(e) { parsed = t; }
              return { __httpStatus: status, __body: parsed };
            });
          })
          .then(res => { clearTimeout(timer); resolve(res); })
          .catch(err => { clearTimeout(timer); reject(err); });
      } else {
        clearTimeout(timer);
        reject(new Error('页面既无 lib.mtop 也无 fetch'));
      }
    });
  }, step.api, step.v, step.data, step.method, step.body);

  // P0-4: 解包 HTTP 状态码，非 2xx 时附加警告
  let finalResult = result;
  let httpWarning = null;
  if (result && typeof result === 'object' && '__httpStatus' in result) {
    const httpStatus = result.__httpStatus;
    finalResult = result.__body;
    if (httpStatus >= 400) {
      httpWarning = `HTTP ${httpStatus} — API 返回错误状态码`;
      // 如果响应体是 HTML 错误页，提取关键信息
      if (typeof finalResult === 'string' && finalResult.includes('<title>')) {
        const titleMatch = finalResult.match(/<title>([^<]+)<\/title>/);
        httpWarning += titleMatch ? ` (${titleMatch[1].trim()})` : '';
      }
    }
  }

  if (step.storeAs) {
    globalStore[step.storeAs] = finalResult;
    if (httpWarning) globalStore[step.storeAs + '__httpWarning'] = httpWarning;
  }
  if (httpWarning) {
    console.error(`[apiCall] ⚠ ${step.api}: ${httpWarning}`);
  }
  return finalResult;
}

// dataSetup：数据自愈/造数 — 自动补齐缺失的前置测试数据
// step: { type:'dataSetup', kind, params?, storeAs? }
// 目前支持的 kind：
//   - f88-audit-task：创建 F88 审核任务（生成 xlsx → 上传 → 调创建 API），产出“待审核”数据
async function execDataSetup(page, step) {
  const kind = step.kind;
  if (kind === 'f88-audit-task') {
    const result = await setupF88AuditTask(page, step.params || {});
    if (step.storeAs) globalStore[step.storeAs] = result;
    return result;
  }
  throw new Error(`dataSetup 不支持的 kind: ${kind}（目前仅支持 f88-audit-task）`);
}

// F88 审核任务造数：绕过前端 4 步向导，通过 API 直接创建审核任务
// 流程：生成 xlsx（Python/openpyxl）→ 浏览器内上传得 OSS URL → 调创建 API（带 X-AFD-Emp-Identity header）
// 参考：审核数据构造 skill（POST /api/afd/review/task/main/create）
async function setupF88AuditTask(page, params) {
  const identity = params.identity || 'f88';
  const questionType = params.questionType || 4; // 4=首图审核
  const taskName = params.taskName || `AutoDataPrep_${Date.now()}`;

  // 1) 生成 xlsx 数据文件（Node 侧，Python/openpyxl）→ base64
  const xlsxBase64 = generateAuditXlsxBase64(params);

  // 2) 浏览器内上传 → OSS URL（复用已登录 session）
  const ossUrl = await page.evaluate((b64) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const file = new File([blob], 'audit_data.xlsx', { type: blob.type });
    const fd = new FormData();
    fd.append('file', file);
    return fetch('/api/file/upload', { method: 'POST', credentials: 'include', body: fd })
      .then(r => r.json())
      .then(d => (d && d.data) ? d.data : Promise.reject(new Error('文件上传失败: ' + JSON.stringify(d).slice(0, 200))));
  }, xlsxBase64);

  // 3) 自动探测 nodeId / standardIds（失败时回退默认值）
  const nodeId = params.nodeId || (await detectReviewNodeId(page, identity, questionType)) || 169;
  const standardIds = params.standardIds || (await detectReviewStandardIds(page, identity)) || [140];

  // 4) 构建创建 payload 并调用创建 API
  // 后端要求数据文件至少 4 行（B0001: 数据文件格式不正确，至少需要4行数据）
  const rows = Math.max(4, params.rows || 4);
  const participant = params.participant || { userId: '421225', userName: '宗育', count: rows };
  const payload = {
    taskName,
    nodeId,
    dataFileUrl: ossUrl,
    standardIds,
    priority: params.priority || 0,
    expectedDeliveryTime: params.expectedDeliveryTime || defaultDeliveryTime(),
    difficulty: params.difficulty || 2,
    efficiency: params.efficiency || 500,
    allocation: {
      roles: params.roles || ['reviewer'],
      requiredTagIds: [],
      participants: [participant],
      allocationMethod: params.allocationMethod || 2,
    },
    inspectionConfig: { enabled: false, participantUserIds: [], distributionType: 1, sampleSourceUserIds: [], ratio: 0, maxCountPerUser: 0, perPersonCount: 0 },
    buryConfig: { enabled: false, ratio: 0, maxCountPerUser: 0, perPersonCount: 0 },
    distributionLogic: params.distributionLogic || 1,
  };

  // 调用创建 API（封装为函数以便分配数量不匹配时自愈重试）
  const callCreate = (pl) => page.evaluate((p, ident) => {
    return fetch('/api/afd/review/task/main/create', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-AFD-Emp-Identity': ident },
      body: JSON.stringify(p),
    }).then(r => r.json()).catch(e => ({ success: false, message: e.message }));
  }, pl, identity);

  let created = await callCreate(payload);
  // 造数自愈：后端可能对数据行去重/过滤（如重复图片），导致实际子任务数 < 上传行数。
  // 此时从错误信息中提取“实际分配数量(N)”，用 N 修正 participant.count 后重试。
  const mismatch = created && created.success === false
    ? JSON.stringify(created).match(/实际分配数量\((\d+)\)/)
    : null;
  if (mismatch) {
    const actualCount = parseInt(mismatch[1], 10);
    console.error(`[dataSetup] ⚠ 分配数量不匹配（rows=${rows}, 后端实际=${actualCount}），自愈重试...`);
    payload.allocation.participants[0].count = actualCount;
    created = await callCreate(payload);
  }

  const taskId = created && (created.data !== undefined ? created.data : created.taskId);
  if (!created || created.success === false || taskId === undefined || taskId === null) {
    throw new Error(`创建审核任务失败: ${JSON.stringify(created).slice(0, 300)}`);
  }
  console.error(`[dataSetup] ✅ 已创建 F88 审核任务 taskId=${taskId}（rows=${rows}, nodeId=${nodeId}, 上传文件=${ossUrl.slice(0, 60)}...）`);
  return { created: true, taskId, ossUrl, nodeId, standardIds, taskName };
}

// 生成首图审核 xlsx 数据文件（questionType=4，11 列）→ base64
// 列：img_url_list（单个 URL 字符串，非 JSON 数组）+ img_url_reference_1~6 + tao_cate + seller_id + shop_name + extra_info
function generateAuditXlsxBase64(params) {
  const os = require('os');
  // 后端要求至少 4 行数据，默认生成 4 行
  const rows = Math.max(4, params.rows || 4);
  // 临时目录：优先用工作区 .cache（沙箱/普通环境均可写），避免 os.tmpdir() 在受限环境不可写
  const tmpDir = path.join(__dirname, '..', '.cache', 'datasetup');
  try { fs.mkdirSync(tmpDir, { recursive: true }); } catch (_) {}
  const stamp = Date.now();
  const cfg = {
    output: path.join(tmpDir, `f88-audit-${stamp}.xlsx`),
    rows,
    imgUrl: params.imgUrl || 'https://img.alicdn.com/imgextra/i1/test/O1CN01mock001_800x800.jpg',
    taoCate: params.taoCate || '女装',
    sellerId: String(params.sellerId || '2219662018344'),
    shopName: params.shopName || '测试商家A',
  };
  const py = [
    'import json, sys, os.path, openpyxl',
    'cfg = json.load(open(sys.argv[1]))',
    'wb = openpyxl.Workbook(); ws = wb.active',
    "hdr = ['img_url_list'] + ['img_url_reference_%d' % i for i in range(1, 7)] + ['tao_cate', 'seller_id', 'shop_name', 'extra_info']",
    'ws.append(hdr)',
    'base, ext = os.path.splitext(cfg["imgUrl"])',
    'for i in range(cfg["rows"]):',
    '    url = "%s_%d%s" % (base, i + 1, ext)',
    '    ws.append([url] + [""] * 6 + [cfg["taoCate"], cfg["sellerId"], cfg["shopName"], "auto-dataSetup"])',
    'wb.save(cfg["output"])',
  ].join('\n');
  const pyFile = path.join(tmpDir, `f88-gen-xlsx-${stamp}.py`);
  const cfgFile = path.join(tmpDir, `f88-xlsx-cfg-${stamp}.json`);
  fs.writeFileSync(pyFile, py, 'utf8');
  fs.writeFileSync(cfgFile, JSON.stringify(cfg), 'utf8');
  try {
    execSync(`python3 "${pyFile}" "${cfgFile}"`, { encoding: 'utf8', timeout: 30000 });
  } catch (e) {
    throw new Error(`造数 xlsx 生成失败: ${e.message}`);
  } finally {
    try { fs.unlinkSync(pyFile); fs.unlinkSync(cfgFile); } catch (_) {}
  }
  const buf = fs.readFileSync(cfg.output);
  try { fs.unlinkSync(cfg.output); } catch (_) {}
  return buf.toString('base64');
}

// 探测审核节点 ID（best-effort，失败返回 null 回退默认值）
async function detectReviewNodeId(page, identity, questionType) {
  try {
    const res = await page.evaluate((ident) => {
      return fetch('/api/afd/review/node/list', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-AFD-Emp-Identity': ident },
        body: JSON.stringify({}),
      }).then(r => r.json()).catch(() => null);
    }, identity);
    let nodes = res && (res.data || res.list);
    nodes = Array.isArray(nodes) ? nodes : (nodes && (nodes.list || nodes.records)) || [];
    const node = nodes.find(n => n.questionType === questionType) || nodes[0];
    return node ? (node.id || node.nodeId) : null;
  } catch (_) { return null; }
}

// 探测审核标准 ID（best-effort，失败返回 null 回退默认值）
async function detectReviewStandardIds(page, identity) {
  try {
    const res = await page.evaluate((ident) => {
      return fetch('/api/afd/review/standard/list', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-AFD-Emp-Identity': ident },
        body: JSON.stringify({}),
      }).then(r => r.json()).catch(() => null);
    }, identity);
    let stds = res && (res.data || res.list);
    stds = Array.isArray(stds) ? stds : (stds && (stds.list || stds.records)) || [];
    const first = stds[0];
    return first ? [first.id || first.standardId] : null;
  } catch (_) { return null; }
}

// 默认预期交付时间：当前+24h，格式 yyyy-MM-dd HH:mm:ss
function defaultDeliveryTime() {
  const d = new Date(Date.now() + 24 * 3600 * 1000);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// ─────────────────────────────────────────────────────────────
// postSetupVerify：造数自查 — 在 dataSetup 后验证数据是否真正可用
// step: { type:'postSetupVerify', sourceKey?, checks?, identity?, storeAs? }
// 5 维度自查：PRD合规 / 代码契约 / 历史存量 / 可用性 / 安全性
// ─────────────────────────────────────────────────────────────
async function execPostSetupVerify(page, step, store) {
  const identity = step.identity || 'f88';
  // 从 store 中获取造数结果（默认取最近一次 dataSetup 的结果）
  const sourceKey = step.sourceKey || 'setupResult';
  const setupData = store[sourceKey] || store['dataSetup'] || {};

  if (!setupData || !setupData.taskId) {
    console.error('[postSetupVerify] ⚠ 无造数结果可验证，跳过');
    return { passed: true, skipped: true, message: '无造数结果' };
  }

  const taskId = setupData.taskId;
  const checks = step.checks || ['contract', 'landing', 'safety'];
  const results = [];
  let blocked = false;

  console.error(`[postSetupVerify] 🔍 开始自查 taskId=${taskId}，维度: ${checks.join(', ')}`);

  // ── 维度 1: PRD 合规性（字段完备性） ──
  if (checks.includes('prd')) {
    const requiredFields = ['taskId', 'ossUrl', 'nodeId', 'taskName'];
    const missing = requiredFields.filter(f => setupData[f] === undefined || setupData[f] === null);
    const item = {
      dimension: 'prd_compliance',
      check: '字段完备性',
      passed: missing.length === 0,
      severity: 'block',
      message: missing.length === 0 ? '必填字段完整' : `缺失: ${missing.join(', ')}`,
    };
    results.push(item);
    if (!item.passed) blocked = true;
  }

  // ── 维度 2: 代码契约（API 回查确认创建成功） ──
  if (checks.includes('contract')) {
    try {
      const detail = await page.evaluate((tid, ident) => {
        return fetch(`/api/afd/review/task/main/detail?taskId=${tid}&identity=${ident}`, {
          credentials: 'include',
          headers: { 'X-AFD-Emp-Identity': ident },
        }).then(r => r.json()).catch(e => ({ success: false, message: e.message }));
      }, taskId, identity);

      const contractOk = detail && detail.success !== false && detail.data;
      const item = {
        dimension: 'code_contract',
        check: 'API 契约回查',
        passed: !!contractOk,
        severity: 'block',
        message: contractOk ? `任务详情可查，状态=${detail.data && detail.data.status}` : `API 回查失败: ${JSON.stringify(detail).slice(0, 150)}`,
        detail: detail && detail.data ? { status: detail.data.status, taskName: detail.data.taskName } : {},
      };
      results.push(item);
      if (!item.passed) blocked = true;
    } catch (e) {
      results.push({ dimension: 'code_contract', check: 'API 契约回查', passed: false, severity: 'warn', message: `异常: ${e.message}` });
    }
  }

  // ── 维度 3: 历史存量（状态窗口） ──
  if (checks.includes('state')) {
    try {
      const detail = await page.evaluate((tid, ident) => {
        return fetch(`/api/afd/review/task/main/detail?taskId=${tid}&identity=${ident}`, {
          credentials: 'include',
          headers: { 'X-AFD-Emp-Identity': ident },
        }).then(r => r.json()).catch(() => null);
      }, taskId, identity);

      const status = detail && detail.data ? detail.data.status : undefined;
      // 待审核(0)/审核中(1) 是有效状态，已完成(2)/已删除(-1) 则不可用
      const validStates = [0, 1, '0', '1'];
      const stateOk = status !== undefined && validStates.includes(status);
      const item = {
        dimension: 'history_conflict',
        check: '状态窗口',
        passed: stateOk,
        severity: 'block',
        message: stateOk ? `状态=${status}，在有效窗口内` : `状态=${status}，不在有效窗口[0,1]内（可能已审完或已删除）`,
      };
      results.push(item);
      if (!item.passed) blocked = true;
    } catch (e) {
      results.push({ dimension: 'history_conflict', check: '状态窗口', passed: false, severity: 'warn', message: `异常: ${e.message}` });
    }
  }

  // ── 维度 4: 可用性（DB 落池 + 子任务数确认） ──
  if (checks.includes('landing')) {
    try {
      const subInfo = await page.evaluate((tid, ident) => {
        return fetch(`/api/afd/review/task/sub/list?mainTaskId=${tid}&pageNo=1&pageSize=10&identity=${ident}`, {
          credentials: 'include',
          headers: { 'X-AFD-Emp-Identity': ident },
        }).then(r => r.json()).catch(() => null);
      }, taskId, identity);

      const subList = subInfo && (subInfo.data || subInfo.list);
      const subCount = Array.isArray(subList) ? subList.length : (subList && subList.total) || 0;
      const landingOk = subCount > 0;
      const item = {
        dimension: 'usability',
        check: 'DB 落池确认',
        passed: landingOk,
        severity: 'block',
        message: landingOk ? `子任务已落池，数量=${subCount}` : '子任务未落池（可能异步延迟，建议等待后重试）',
        detail: { subCount },
      };
      results.push(item);
      if (!item.passed) blocked = true;
    } catch (e) {
      results.push({ dimension: 'usability', check: 'DB 落池确认', passed: false, severity: 'warn', message: `异常: ${e.message}` });
    }
  }

  // ── 维度 5: 安全性（环境正确 + 可追溯） ──
  if (checks.includes('safety')) {
    // 环境检查：当前页面 URL 应包含 pre- 标识
    const pageUrl = page.url();
    const envOk = pageUrl.includes('pre-') || pageUrl.includes('pre.') || pageUrl.includes('localhost');
    const traceOk = !!(setupData.taskId && setupData.taskName && setupData.ossUrl);
    const item = {
      dimension: 'safety',
      check: '环境+追溯',
      passed: envOk && traceOk,
      severity: envOk ? 'warn' : 'block',
      message: envOk
        ? (traceOk ? '环境正确（预发），追溯字段完整' : `追溯字段不完整`)
        : `环境异常！当前 URL 非预发: ${pageUrl.slice(0, 80)}`,
    };
    results.push(item);
    if (!item.passed && !envOk) blocked = true;
  }

  // ── 汇总 ──
  const passed = results.every(r => r.passed);
  const summary = {
    passed,
    blocked,
    taskId,
    totalChecks: results.length,
    passedChecks: results.filter(r => r.passed).length,
    failedChecks: results.filter(r => !r.passed).length,
    items: results,
    timestamp: new Date().toISOString(),
  };

  const icon = blocked ? '❌' : passed ? '✅' : '⚠️';
  console.error(`[postSetupVerify] ${icon} 自查完成: ${summary.passedChecks}/${summary.totalChecks} 通过${blocked ? '，存在阻断项' : ''}`);

  if (step.storeAs) store[step.storeAs] = summary;
  return summary;
}

// dbQuery：通过 dms-alibaba CLI 执行 SQL
// step: { type:'dbQuery', sql, dbGroup?, dbName?, storeAs? }
async function execDbQuery(step) {
  const sql = step.sql;
  if (!sql) throw new Error('dbQuery step 必须提供 sql');
  const dbGroup = step.dbGroup || process.env.DMS_GROUP || 'scenario';
  const dbName = step.dbName || process.env.DMS_DB || 'prod';
  const cliPath = process.env.DMS_CLI_PATH || '/Users/caoxuemei/dms-alibaba/bin/dms-alibaba';
  const escapedSql = sql.replace(/"/g, '\\"');
  const cmd = `"${cliPath}" sql run "${dbGroup}" --db "${dbName}" --sql "${escapedSql}"`;
  let stdout, stderr;
  try {
    stdout = execSync(cmd, { encoding: 'utf8', timeout: 60000 });
  } catch (e) {
    throw new Error(`dbQuery 执行失败: ${e.message}${e.stderr ? '\n' + e.stderr : ''}`);
  }
  let rows = [];
  let success = false;
  let rowCount = 0;
  // 优先从 dms-alibaba 输出的 JSON 结果文件读取结构化数据
  const jsonPathMatch = stdout.match(/结果\(json\):\s*(.+)/);
  if (jsonPathMatch) {
    const jsonPath = jsonPathMatch[1].trim();
    try {
      const fs = require('fs');
      const jsonData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
      rows = Array.isArray(jsonData) ? jsonData : (jsonData.rows || jsonData.data || [jsonData]);
    } catch (_) {
      rows = stdout.split('\n').filter(Boolean);
    }
  } else {
    try {
      const parsed = JSON.parse(stdout);
      rows = parsed.rows || parsed.data || parsed;
    } catch (_) {
      rows = stdout.split('\n').filter(Boolean);
    }
  }
  // 提取成功/失败状态和行数
  const successMatch = stdout.match(/成功:\s*(\d+)\s*行/);
  const failMatch = stdout.match(/失败:/);
  if (successMatch) { success = true; rowCount = parseInt(successMatch[1]); }
  if (failMatch) { success = false; }
  const result = { sql, rows, rawOutput: stdout, success, rowCount };
  if (step.storeAs) {
    globalStore[step.storeAs] = result;
  }
  return result;
}

// assertDbResult：断言 dbQuery 结果
// step: { type:'assertDbResult', condition?, expectations? }
async function execAssertDbResult(step, lastResult) {
  if (!lastResult) return { pass: false, message: '没有前置 dbQuery 结果' };
  const rows = lastResult.rows || [];
  const firstRow = rows[0] || {};

  // 简单 condition 表达式
  if (step.condition) {
    const cond = step.condition;
    if (cond.includes('rowCount')) {
      const match = cond.match(/rowCount\s*(==|>|<|>=|<=)\s*(\d+)/);
      if (match) {
        const op = match[1];
        const expected = parseInt(match[2], 10);
        const actual = rows.length;
        const ok = op === '==' ? actual === expected : op === '>' ? actual > expected : op === '<' ? actual < expected : op === '>=' ? actual >= expected : actual <= expected;
        return { pass: ok, message: ok ? 'ok' : `rowCount ${actual} ${op} ${expected} 不成立` };
      }
    }
    // rows[0].field == value
    const match = cond.match(/rows\[(\d+)\]\.(\w+)\s*==\s*(.+)/);
    if (match) {
      const idx = parseInt(match[1], 10);
      const field = match[2];
      let expected = match[3].trim();
      if ((expected.startsWith('"') && expected.endsWith('"')) || (expected.startsWith("'") && expected.endsWith("'"))) {
        expected = expected.slice(1, -1);
      } else {
        expected = Number.isNaN(Number(expected)) ? expected : Number(expected);
      }
      const actual = getByPath(rows[idx], field);
      return { pass: String(actual) === String(expected), message: `rows[${idx}].${field}=${actual}, expected=${expected}` };
    }
  }

  // expectations 数组
  if (Array.isArray(step.expectations)) {
    for (const exp of step.expectations) {
      const actual = getByPath(firstRow, exp.field);
      if (actual === undefined) return { pass: false, message: `字段 ${exp.field} 不存在` };
      if (exp.equals !== undefined && String(actual) !== String(exp.equals)) {
        return { pass: false, message: `${exp.field}: ${actual} != ${exp.equals}` };
      }
      if (exp.contains && !String(actual).includes(exp.contains)) {
        return { pass: false, message: `${exp.field}: ${actual} 不包含 ${exp.contains}` };
      }
      if (exp.notEmpty && (!actual || String(actual).trim() === '')) {
        return { pass: false, message: `${exp.field} 为空` };
      }
    }
    return { pass: true, message: '所有 DB 断言通过' };
  }

  return { pass: false, message: 'assertDbResult 缺少有效断言条件' };
}

// assertStore：断言 globalStore 中的变量
// step: { type:'assertStore', key, path?, equals?, notEquals?, contains?, notEmpty? }
async function execAssertStore(step, store) {
  // P0-2: 增强 undefined 诊断 — 先检查 store key 是否存在
  if (!(step.key in store)) {
    const availableKeys = Object.keys(store).slice(0, 10).join(', ');
    return { pass: false, message: `store key "${step.key}" 不存在（前置步骤未执行或未 storeAs）。当前可用 keys: [${availableKeys || '空'}]` };
  }
  const value = step.path ? getByPath(store[step.key], step.path) : store[step.key];
  // 如果 path 解析后为 undefined，给出路径诊断
  if (value === undefined && step.path) {
    const parentObj = store[step.key];
    const availablePaths = parentObj && typeof parentObj === 'object' ? Object.keys(parentObj).slice(0, 8).join(', ') : typeof parentObj;
    return { pass: false, message: `store.${step.key}.${step.path}=undefined（路径不存在）。store.${step.key} 可用字段: [${availablePaths}]` };
  }
  if (step.equals !== undefined && String(value) !== String(step.equals)) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, expected=${step.equals}` };
  }
  if (step.notEquals !== undefined && String(value) === String(step.notEquals)) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, should not equal ${step.notEquals}` };
  }
  if (step.contains && !String(value).includes(step.contains)) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value} 不包含 ${step.contains}` };
  }
  if (step.notEmpty && (!value || String(value).trim() === '')) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''} 为空` };
  }
  if (step.gte !== undefined && (Number(value) < Number(step.gte))) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, expected >= ${step.gte}` };
  }
  if (step.lte !== undefined && (Number(value) > Number(step.lte))) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, expected <= ${step.lte}` };
  }
  if (step.gt !== undefined && (Number(value) <= Number(step.gt))) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, expected > ${step.gt}` };
  }
  if (step.lt !== undefined && (Number(value) >= Number(step.lt))) {
    return { pass: false, message: `store.${step.key}${step.path ? '.' + step.path : ''}=${value}, expected < ${step.lt}` };
  }
  return { pass: true, message: 'store 断言通过' };
}

// 按点分路径取值：如 data.success / data.data.batchType
function getByPath(obj, pathStr) {
  if (!obj || !pathStr) return undefined;
  return pathStr.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

// 解析 step 中的 ${store.key}、${store.key.path} 或 ${key} 变量
function resolveStepVars(step, store) {
  const resolved = { ...step };
  // expression/script 字段：用 JSON.stringify 保持对象结构
  const jsFields = ['expression', 'script'];
  // 其他字段：用 String() 转字符串
  const strFields = [
    'value', 'selector', 'text', 'contains', 'api', 'url', 'label', 'option',
    'filePath', 'body', 'sql'
  ];
  for (const key of [...jsFields, ...strFields]) {
    if (typeof resolved[key] !== 'string') continue;
    const isJs = jsFields.includes(key);
    // 先替换 ${store.xxx} 格式
    resolved[key] = resolved[key].replace(/\$\{store\.([^}]+)\}/g, (_, path) => {
      const v = getByPath(store, path);
      if (v === undefined) return '';
      if (isJs && typeof v === 'object') return JSON.stringify(v);
      return String(v);
    });
    // 再替换 ${xxx} 格式（直接引用 store key，无 store. 前缀）
    resolved[key] = resolved[key].replace(/\$\{([^}]+)\}/g, (_, name) => {
      const v = getByPath(store, name);
      if (v === undefined) return '${' + name + '}';  // 保持原样（可能是模板字面量）
      if (isJs && typeof v === 'object') return JSON.stringify(v);
      return String(v);
    });
  }
  if (resolved.data && typeof resolved.data === 'object') {
    resolved.data = JSON.parse(JSON.stringify(resolved.data).replace(/\$\{store\.([^}]+)\}/g, (_, path) => {
      const v = getByPath(store, path);
      return v === undefined ? '' : String(v);
    }));
  }
  return resolved;
}

// ─────────────────────────────────────────────
// 网络抓包
// ─────────────────────────────────────────────

async function startCapture(client, captureOutput, config) {
  await client.send('Network.enable');
  const store = new Map();
  const filter = config.filter || null;
  const matchFilter = (url) => {
    if (!filter) return true;
    try { return new RegExp(filter).test(url); } catch (_) { return url.includes(filter); }
  };

  client.on('Network.requestWillBeSent', ({ requestId, request }) => {
    if (!matchFilter(request.url)) return;
    store.set(requestId, {
      method: request.method,
      url: request.url,
      requestBody: tryParseJSON(request.postData),
      startTime: Date.now(),
    });
  });

  client.on('Network.responseReceived', ({ requestId, response }) => {
    const req = store.get(requestId);
    if (req) req.status = response.status;
  });

  client.on('Network.loadingFinished', async ({ requestId }) => {
    const req = store.get(requestId);
    if (!req) return;
    req.duration = Date.now() - req.startTime;

    if (config.captureBody !== false) {
      try {
        const { body, base64Encoded } = await client.send('Network.getResponseBody', { requestId });
        const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
        req.responseBody = tryParseJSON(text);
      } catch (_) {
        req.responseBody = null;
      }
    }

    captureOutput.requests.push({
      method: req.method,
      url: req.url,
      status: req.status || 0,
      duration: req.duration,
      requestBody: req.requestBody,
      responseBody: req.responseBody,
    });
  });
}

function waitForAPI(client, urlPattern, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`等待接口超时: ${urlPattern}`)), timeout);
    const pending = new Map();

    client.on('Network.requestWillBeSent', ({ requestId, request }) => {
      if (request.url.includes(urlPattern)) {
        pending.set(requestId, { url: request.url, requestBody: tryParseJSON(request.postData) });
      }
    });

    client.on('Network.loadingFinished', async ({ requestId }) => {
      const req = pending.get(requestId);
      if (!req) return;
      try {
        const { body, base64Encoded } = await client.send('Network.getResponseBody', { requestId });
        const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
        req.responseBody = tryParseJSON(text);
      } catch (_) {}
      clearTimeout(timer);
      resolve(req);
    });
  });
}

// ─────────────────────────────────────────────
// 截图（1458×784 JPEG medium，见 shared/browser-cdp）
// ─────────────────────────────────────────────

async function takeScreenshot(page, client, name, dir) {
  const filePath = ensureJpegPath(path.join(dir, name));
  return capturePageScreenshot(page, filePath);
}

// ─────────────────────────────────────────────
// HAR 导出
// ─────────────────────────────────────────────

function exportHAR(requests, outputPath) {
  const entries = requests.map(req => ({
    startedDateTime: new Date().toISOString(),
    time: req.duration || 0,
    request: {
      method: req.method,
      url: req.url,
      httpVersion: 'HTTP/2.0',
      headers: [],
      queryString: [],
      cookies: [],
      headersSize: -1,
      bodySize: req.requestBody ? JSON.stringify(req.requestBody).length : 0,
      postData: req.requestBody ? {
        mimeType: 'application/json',
        text: typeof req.requestBody === 'string' ? req.requestBody : JSON.stringify(req.requestBody),
      } : undefined,
    },
    response: {
      status: req.status,
      statusText: '',
      httpVersion: 'HTTP/2.0',
      headers: [],
      cookies: [],
      content: {
        size: 0,
        mimeType: 'application/json',
        text: typeof req.responseBody === 'string' ? req.responseBody : JSON.stringify(req.responseBody),
      },
      redirectURL: '',
      headersSize: -1,
      bodySize: -1,
    },
    cache: {},
    timings: { send: 0, wait: req.duration || 0, receive: 0 },
  }));

  fs.writeFileSync(outputPath, JSON.stringify({
    log: { version: '1.2', creator: { name: 'web-automation', version: '1.0' }, entries },
  }, null, 2));
}

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function tryParseJSON(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch (_) { return text; }
}

// ─────────────────────────────────────────────
// 导出（供其他脚本 require）
// ─────────────────────────────────────────────
module.exports = { runTest, takeScreenshot, startCapture, waitForAPI };

// CLI 入口
if (require.main === module) main();
