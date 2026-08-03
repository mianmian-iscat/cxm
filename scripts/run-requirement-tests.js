#!/usr/bin/env node
/**
 * run-requirement-tests.js — 新需求测试执行器
 *
 * 扫描 new-requirement-{prd_id}/ 下所有 eval 用例 JSON，
 * 按优先级排序 + DAG 依赖编排，逐个通过 CDP 执行，
 * 采集截图 + DOM 断言结果，输出 execution-results.json。
 *
 * 用法:
 *   node scripts/run-requirement-tests.js --prd-id <id>
 *   node scripts/run-requirement-tests.js --cases-dir eval/cases/f88-test/new-requirement-xxx
 *   node scripts/run-requirement-tests.js --prd-id xxx --dry-run
 *
 * 环境变量:
 *   WEB_AUTO_CDP_URL  — CDP 地址 (默认 http://127.0.0.1:9222)
 *   CASE_TIMEOUT_MS   — 单用例超时 (默认 60000)
 *   HEADLESS           — 是否无头模式 (默认 false)
 */
'use strict';

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const CASE_TIMEOUT_MS = parseInt(process.env.CASE_TIMEOUT_MS, 10) || 60000;
const WORKSPACE = path.resolve(__dirname, '..');
const CASES_DIR = path.join(WORKSPACE, 'eval', 'cases', 'f88-test');
const ARTIFACTS_DIR = path.join(WORKSPACE, 'artifacts');
const SCREENSHOT_DIR = path.join(ARTIFACTS_DIR, 'screenshots');

// ── CLI 参数 ──
const args = process.argv.slice(2);
let prdId = '';
let casesDir = '';
let dryRun = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--prd-id' && args[i + 1]) prdId = args[++i];
  else if (args[i] === '--cases-dir' && args[i + 1]) casesDir = args[++i];
  else if (args[i] === '--dry-run') dryRun = true;
}

if (!casesDir && prdId) {
  casesDir = path.join(CASES_DIR, `new-requirement-${prdId}`);
}
if (!casesDir) {
  console.error('用法: node run-requirement-tests.js --prd-id <id> | --cases-dir <dir>');
  process.exit(1);
}

// ── 工具函数 ──
function log(msg, level = 'INFO') {
  const ts = new Date().toISOString().substring(11, 19);
  const icons = { OK: '✅', WARN: '⚠️', ERR: '❌', INFO: 'ℹ️', SKIP: '⏭️' };
  console.log(`${icons[level] || 'ℹ️'} [${ts}] ${msg}`);
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

// ── 加载用例 ──
function loadCases(dir) {
  if (!fs.existsSync(dir)) {
    log(`用例目录不存在: ${dir}`, 'ERR');
    process.exit(1);
  }

  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
  const cases = [];

  for (const file of files) {
    try {
      const filePath = path.join(dir, file);
      const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      cases.push({
        id: data.id || file.replace('.json', ''),
        name: data.name || file,
        description: data.description || '',
        priority: data.priority || 'P2',
        category: data.category || 'normal_flow',
        context: data.context || {},
        steps: data.steps || [],
        _expected: data._expected || {},
        _testDesign: data._testDesign || {},
        file: filePath,
        filename: file,
        deps: data.deps || []
      });
    } catch (e) {
      log(`解析用例失败: ${file} — ${e.message}`, 'WARN');
    }
  }

  return cases;
}

// ── 优先级排序 ──
function sortByPriority(cases) {
  const order = { P0: 0, P1: 1, P2: 2, P3: 3 };
  return cases.sort((a, b) => (order[a.priority] ?? 9) - (order[b.priority] ?? 9));
}

// ── DAG 调度 ──
function buildDAGWaves(entries) {
  const idSet = new Set(entries.map(e => e.id));
  const resolved = new Set();
  const remaining = new Map(entries.map(e => [e.id, e]));
  const waves = [];
  let safety = entries.length + 1;

  while (remaining.size > 0 && safety-- > 0) {
    const wave = [];
    for (const [id, e] of remaining) {
      if ((e.deps || []).every(d => resolved.has(d) || !idSet.has(d))) {
        wave.push([id, e]);
      }
    }
    if (wave.length === 0) {
      wave.push(...remaining);
      remaining.clear();
    } else {
      for (const [id] of wave) { resolved.add(id); remaining.delete(id); }
    }
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
      if ((e.deps || []).includes(failedId) || (e.deps || []).some(d => ds.has(d))) {
        ds.add(e.id);
        changed = true;
      }
    }
  }
  return ds;
}

// ── 步骤执行器 ──
async function executeStep(page, step, caseId, screenshotDir) {
  const result = { type: step.type, description: step.description || '', status: 'pass', index: 0 };

  try {
    switch (step.type) {
      case 'navigate': {
        const url = step.url;
        if (!url) throw new Error('navigate 步骤缺少 url');
        await page.goto(url, {
          waitUntil: step.waitUntil || 'networkidle2',
          timeout: 30000
        });
        if (step.screenshot) {
          const fp = path.join(screenshotDir, `${caseId}-nav.jpg`);
          await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
          result.screenshot = fp;
        }
        break;
      }

      case 'wait': {
        await new Promise(r => setTimeout(r, step.ms || 1000));
        break;
      }

      case 'click': {
        const selector = step.selector;
        if (!selector) throw new Error('click 步骤缺少 selector');
        await page.waitForSelector(selector, { timeout: 5000 });
        await page.click(selector);
        break;
      }

      case 'clickText': {
        const text = step.text;
        if (!text) throw new Error('clickText 步骤缺少 text');
        const clicked = await page.evaluate((txt) => {
          const els = Array.from(document.querySelectorAll('button, a, [role=button], span, div'));
          const el = els.find(e => e.textContent.trim() === txt && e.offsetHeight > 0);
          if (el) { el.click(); return true; }
          return false;
        }, text);
        if (!clicked) throw new Error(`未找到可点击元素: "${text}"`);
        break;
      }

      case 'type': {
        const selector = step.selector;
        if (!selector) throw new Error('type 步骤缺少 selector');
        await page.waitForSelector(selector, { timeout: 5000 });
        if (step.clear) {
          await page.click(selector, { clickCount: 3 });
        }
        await page.type(selector, step.text || step.value || '', { delay: 50 });
        break;
      }

      case 'evaluate': {
        const expression = step.expression;
        if (!expression) throw new Error('evaluate 步骤缺少 expression');
        const evalResult = await page.evaluate(expression);
        if (step.storeAs) {
          result.storedValue = evalResult;
        }
        // 如果表达式返回 { pass: false }，标记失败
        if (evalResult && typeof evalResult === 'object' && evalResult.pass === false) {
          throw new Error(`evaluate 断言失败: ${JSON.stringify(evalResult)}`);
        }
        break;
      }

      case 'assert': {
        const bodyText = await page.evaluate(() => document.body.innerText);
        if (step.contains) {
          const found = bodyText.includes(step.contains);
          if (!found) {
            throw new Error(`页面不包含 "${step.contains}"`);
          }
        }
        if (step.notContains) {
          const found = !bodyText.includes(step.notContains);
          if (!found) {
            throw new Error(`页面不应包含 "${step.notContains}" 但包含`);
          }
        }
        if (step.urlIncludes) {
          const currentUrl = page.url();
          if (!currentUrl.includes(step.urlIncludes)) {
            throw new Error(`URL 不包含 "${step.urlIncludes}", 当前: ${currentUrl}`);
          }
        }
        break;
      }

      case 'screenshot': {
        const label = step.label || caseId;
        const fp = path.join(screenshotDir, `${label}.jpg`);
        await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
        result.screenshot = fp;
        break;
      }

      case 'waitForSelector': {
        if (!step.selector) throw new Error('waitForSelector 缺少 selector');
        await page.waitForSelector(step.selector, { timeout: step.timeout || 10000 });
        break;
      }

      case 'scroll': {
        await page.evaluate((y) => window.scrollBy(0, y), step.y || 300);
        await new Promise(r => setTimeout(r, 500));
        break;
      }

      case 'hover': {
        const selector = step.selector;
        if (!selector) throw new Error('hover 步骤缺少 selector');
        await page.hover(selector);
        break;
      }

      case 'select': {
        // Ant Design Select: 必须用 mouse.click 触发
        const selector = step.selector || '.ant-select';
        const optionText = step.option || step.value;
        await page.click(selector);
        await new Promise(r => setTimeout(r, 800));
        if (optionText) {
          const clicked = await page.evaluate((txt) => {
            const items = document.querySelectorAll('.ant-select-dropdown .ant-select-item');
            for (const item of items) {
              if (item.textContent.trim().includes(txt)) { item.click(); return true; }
            }
            return false;
          }, optionText);
          if (!clicked) throw new Error(`未找到下拉选项: "${optionText}"`);
        }
        break;
      }

      case 'pressKey': {
        const key = step.key || 'Enter';
        await page.keyboard.press(key);
        break;
      }

      default:
        log(`未知步骤类型: ${step.type}，跳过`, 'WARN');
        result.status = 'skip';
    }
  } catch (e) {
    result.status = 'fail';
    result.error = e.message;
    // 失败时自动截图
    try {
      const fp = path.join(screenshotDir, `${caseId}-error-${Date.now()}.jpg`);
      await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
      result.errorScreenshot = fp;
    } catch (_) {}
  }

  return result;
}

// ── 执行单个用例 ──
async function executeCase(browser, testCase, screenshotDir) {
  const startTime = Date.now();
  const stepResults = [];
  let status = 'pass';
  let error = null;

  const page = await browser.newPage();

  try {
    // 设置 viewport
    await page.setViewport({ width: 1440, height: 900 });

    // 注入登录态 cookie（如果 context 指定）
    if (testCase.context.url) {
      // 先导航到目标页面
      log(`  → ${testCase.name}`, 'INFO');
    }

    // 逐步执行
    for (let i = 0; i < testCase.steps.length; i++) {
      const step = testCase.steps[i];
      const result = await executeStep(page, step, testCase.id, screenshotDir);
      result.index = i + 1;
      stepResults.push(result);

      if (result.status === 'fail') {
        status = 'fail';
        error = { message: `Step ${i + 1} (${step.type}): ${result.error}` };
        log(`    Step ${i + 1}/${testCase.steps.length} FAIL: ${result.error}`, 'ERR');

        // 失败自愈：检测弹窗并关闭
        try {
          const modalClosed = await page.evaluate(() => {
            const closeBtns = document.querySelectorAll(
              '.ant-modal-close, .ant-drawer-close, .ant-popover-close'
            );
            let closed = false;
            closeBtns.forEach(btn => {
              if (btn.offsetHeight > 0) { btn.click(); closed = true; }
            });
            return closed;
          });
          if (modalClosed) {
            log('    自愈: 已关闭弹窗，重试步骤', 'WARN');
            await new Promise(r => setTimeout(r, 1000));
            const retryResult = await executeStep(page, step, testCase.id + '-retry', screenshotDir);
            if (retryResult.status === 'pass') {
              stepResults[stepResults.length - 1] = retryResult;
              stepResults[stepResults.length - 1].index = i + 1;
              status = 'pass';
              error = null;
              log(`    自愈成功: Step ${i + 1} PASS`, 'OK');
            }
          }
        } catch (_) {}

        if (status === 'fail') break;
      }
    }
  } catch (e) {
    status = 'error';
    error = { message: e.message, stack: e.stack };
    log(`  用例异常: ${e.message}`, 'ERR');
  } finally {
    await page.close().catch(() => {});
  }

  const duration = Date.now() - startTime;
  return {
    id: testCase.id,
    name: testCase.name,
    description: testCase.description,
    priority: testCase.priority,
    file: testCase.file,
    filename: testCase.filename,
    status,
    duration,
    steps: stepResults,
    error,
    stepCount: testCase.steps.length,
    passSteps: stepResults.filter(s => s.status === 'pass').length,
    failSteps: stepResults.filter(s => s.status === 'fail').length
  };
}

// ── 主入口 ──
async function main() {
  ensureDir(SCREENSHOT_DIR);
  ensureDir(ARTIFACTS_DIR);

  log(`新需求测试执行器`);
  log(`用例目录: ${casesDir}`);
  log(`CDP: ${CDP_URL}`);
  log(`超时: ${CASE_TIMEOUT_MS}ms`);

  // 1. 加载用例
  const cases = loadCases(casesDir);
  if (cases.length === 0) {
    log('未找到用例文件', 'ERR');
    process.exit(1);
  }

  log(`加载 ${cases.length} 个用例`);

  // 2. 排序 + DAG
  const sorted = sortByPriority(cases);
  const waves = buildDAGWaves(sorted);

  console.log('\n📐 执行计划:');
  waves.forEach((wave, i) => {
    const ids = wave.map(([, e]) => `${e.id}(${e.priority})`).join(', ');
    console.log(`   Wave ${i + 1}: ${ids}`);
  });
  console.log('');

  if (dryRun) {
    log('[DRY-RUN] 跳过实际执行', 'WARN');
    const dryResults = sorted.map(c => ({
      id: c.id, name: c.name, priority: c.priority,
      status: 'skip', file: c.file, steps: [], duration: 0
    }));
    console.log(JSON.stringify({ cases: dryResults, summary: {
      total: dryResults.length, pass: 0, fail: 0, skip: dryResults.length, error: 0,
      time: new Date().toISOString()
    }}, null, 2));
    return;
  }

  // 3. 连接 CDP
  log(`连接 CDP: ${CDP_URL}`);
  let browser;
  try {
    browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
    log('已连接 Chrome', 'OK');
  } catch (e) {
    log(`无法连接 CDP: ${e.message}`, 'ERR');
    log('请先启动 Chrome: open -a "Google Chrome" --args --remote-debugging-port=9222', 'ERR');
    process.exit(1);
  }

  // 4. 按 Wave 执行
  const allResults = {};
  const skipped = new Map();
  const caseResults = [];

  for (let wi = 0; wi < waves.length; wi++) {
    const wave = waves[wi];
    const runnable = wave.filter(([id]) => !skipped.has(id));
    const toSkip = wave.filter(([id]) => skipped.has(id));

    // 记录级联 SKIP
    for (const [id, entry] of toSkip) {
      allResults[id] = {
        id, name: entry.name, priority: entry.priority, file: entry.file,
        status: 'skip', skipReason: skipped.get(id), duration: 0, steps: []
      };
      log(`⏭️ SKIP ${entry.name}: ${skipped.get(id)}`, 'SKIP');
    }

    if (runnable.length === 0) continue;

    // 同 wave 并行
    const promises = runnable.map(async ([id, entry]) => {
      log(`▶️ [Wave ${wi + 1}] ${entry.name} (${entry.priority})`);
      try {
        const result = await Promise.race([
          executeCase(browser, entry, SCREENSHOT_DIR),
          new Promise((_, rej) => setTimeout(() => rej(new Error(`超时 ${CASE_TIMEOUT_MS}ms`)), CASE_TIMEOUT_MS))
        ]);
        return { id, entry, result };
      } catch (e) {
        log(`超时/异常: ${entry.name} — ${e.message}`, 'ERR');
        return {
          id, entry,
          result: {
            id, name: entry.name, priority: entry.priority, file: entry.file,
            status: 'error', error: { message: e.message }, duration: CASE_TIMEOUT_MS, steps: []
          }
        };
      }
    });

    const waveResults = await Promise.all(promises);

    for (const { id, entry, result } of waveResults) {
      allResults[id] = result;
      caseResults.push(result);

      const icon = result.status === 'pass' ? '✅' : result.status === 'skip' ? '⏭️' : '❌';
      log(`${icon} ${entry.name}: ${result.status} (${(result.duration / 1000).toFixed(1)}s)`);

      // 失败则级联跳过下游
      if (result.status !== 'pass') {
        const downstream = findAllDownstream(id, sorted);
        for (const dsId of downstream) {
          if (!skipped.has(dsId)) {
            skipped.set(dsId, `因 ${entry.name} ${result.status.toUpperCase()} 而 SKIP`);
          }
        }
      }
    }
  }

  // 5. 汇总结果
  const totalCases = Object.keys(allResults).length;
  const passCount = caseResults.filter(r => r.status === 'pass').length;
  const failCount = caseResults.filter(r => r.status === 'fail').length;
  const errorCount = caseResults.filter(r => r.status === 'error').length;
  const skipCount = caseResults.filter(r => r.status === 'skip').length +
                    Object.values(allResults).filter(r => r.status === 'skip').length;

  const output = {
    prd_id: prdId || path.basename(casesDir),
    executed_at: new Date().toISOString(),
    cases_dir: casesDir,
    cdp_url: CDP_URL,
    summary: {
      total: totalCases,
      pass: passCount,
      fail: failCount,
      error: errorCount,
      skip: skipCount,
      passRate: totalCases > 0 ? ((passCount / totalCases) * 100).toFixed(1) + '%' : '0%',
      time: new Date().toISOString()
    },
    cases: Object.values(allResults)
  };

  // 写入结果文件
  const outputPath = path.join(ARTIFACTS_DIR, `execution-results-${prdId || Date.now()}.json`);
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
  log(`结果已保存: ${outputPath}`, 'OK');

  // 同时输出标准格式供 promote_to_regression 消费
  const promotePath = path.join(ARTIFACTS_DIR, 'execution-results.json');
  fs.writeFileSync(promotePath, JSON.stringify(output, null, 2));

  // 打印汇总
  console.log('\n═══════════════════════════════════');
  console.log('📊 新需求测试执行结果');
  console.log('═══════════════════════════════════');
  console.log(`用例: ${totalCases} | ✅ pass: ${passCount} | ❌ fail: ${failCount} | 💥 error: ${errorCount} | ⏭️ skip: ${skipCount}`);
  console.log(`通过率: ${output.summary.passRate}`);

  if (failCount > 0 || errorCount > 0) {
    console.log('\n❌ 失败/异常用例:');
    caseResults.filter(r => r.status !== 'pass' && r.status !== 'skip').forEach(r => {
      console.log(`  ${r.id}: ${r.error?.message || 'unknown'}`);
    });
  }

  console.log(`\n📁 结果: ${outputPath}`);
  console.log('═══════════════════════════════════\n');

  // 退出码
  if (failCount > 0 || errorCount > 0) process.exit(1);
}

main().catch(e => {
  console.error('❌ 执行异常:', e.message);
  process.exit(1);
});
