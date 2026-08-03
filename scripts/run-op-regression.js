#!/usr/bin/env node
/**
 * 原创保护（original_protection / scene: op-test）UI 自动化回归脚本
 *
 * 自包含执行 eval/cases 下全部 9 个原创保护声明式用例，直接用 puppeteer-core
 * 连接 CDP（默认 9222），逐步解释 steps 并输出结构化报告。
 *
 * 用法：
 *   node scripts/run-op-regression.js                       # 跑全部 9 个用例
 *   node scripts/run-op-regression.js signup tort           # 只跑 id/文件名包含关键字的用例
 *   node scripts/run-op-regression.js --out a.json signup   # 指定结果输出路径（多实例并行必备）
 *
 * 多实例并行示例（相同业务、各连独立 CDP 端口，避免结果覆盖）：
 *   node scripts/run-op-regression.js --out artifacts/op-a.json apply_list &
 *   WEB_AUTO_CDP_URL=http://127.0.0.1:9223 node scripts/run-op-regression.js --out artifacts/op-b.json settlement &
 *
 * 覆盖的 step 类型：
 *   navigate / wait / assert / screenshot / click / clickText / fill /
 *   selectOption / uncheckCheckbox / waitForAPI / apiCall / assert(stateTransition)
 *
 * 说明：
 *   - selectOption / uncheckCheckbox / clickText 逻辑移植自 core/_node_bridge.js
 *   - apiCall(mtop) 与 stateTransition 断言属 harness 能力，脚本内做本地降级校验
 *   - post_asserts.apiResponse 通过抓包结果做路径断言
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ── puppeteer-core 解析（本地 node_modules 优先）──
function resolvePuppeteer() {
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

// ── 配置 ──
const CDP_URL   = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const CASES_DIR = path.join(__dirname, '..', 'eval', 'cases', 'op-test');
const SS_DIR    = path.join(__dirname, '..', 'artifacts', 'screenshots', 'op');
const DEFAULT_RESULT_FP = path.join(__dirname, '..', 'artifacts', 'op-regression-results.json');
const SM_DIR    = path.join(__dirname, '..', 'harness', 'state_machines');

// 原创保护页面 UI 回归矩阵（纯 UI 用例）：
// - sku_shelf 已删除；settlement/state_transition 为 API/状态机层逻辑、不走页面 UI，已移出（应走 API/DB 验证）
// 运营端用例(9222): 列表/快审/首发/维权/商品管理/结构验证/筛选联动/白名单
// 商家端用例(9223): signup/维权详情/巡检/首页结构/Tab切换/专利表单/详情时间轴/绑定商品/合同/白名单
// 跨端专项用例：数据一致性/文案规范（需9222+9223均可用）
const OP_CASES = [
  // ── 运营端 (9222) ──
  'regression_op_apply_list.json',          // P0 申请列表页 - 状态筛选+分页一致性
  'normal_op_quick_audit_flow.json',        // P0 快审 Drawer 全链路
  'regression_op_product_search.json',      // P0 商品管理页 - 搜索+分页一致性
  'regression_op_first_publish.json',       // P1 是否首发列
  'regression_op_tort.json',                // P2 维权记录查看 + 数值一致性
  'ui_op_xiaoer_list.json',                // P1 小二端列表页全量结构验证
  'ui_op_quick_audit_drawer.json',          // P1 快审抽屉全量结构验证
  'ui_op_xiaoer_apply_detail.json',        // P1 小二端申请详情Drawer完整结构
  'ui_op_xiaoer_whitelist.json',           // P1 小二端白名单弹窗结构
  'ui_op_xiaoer_filter_action.json',       // P1 小二端筛选联动功能
  'ui_op_xiaoer_first_publish_edit.json',  // P2 小二端首发标签内联编辑
  // ── 商家端 (9223, 需淘宝登录态) ──
  'regression_op_signup.json',              // P1 商家端 - 新增专利申请入口
  'regression_op_tort_detail.json',         // P1 商家端 - 维权记录详情弹层 + 数值一致性
  'regression_op_tort_inspection.json',     // P1 商家端 - 侵权巡检弹层 + 数值一致性
  'ui_op_seller_home.json',                // P1 商家端首页全量结构验证
  'ui_op_seller_tab_switch.json',          // P1 商家端Tab切换验证
  'ui_op_seller_whitelist.json',           // P1 商家端白名单店铺管理
  'ui_op_patent_apply_structure.json',      // P1 专利申请表单结构验证
  'ui_op_patent_apply_full.json',          // P1 专利申请表单全量功能(6角度图+必填校验)
  'ui_op_patent_detail_structure.json',     // P1 专利详情5阶段时间轴+操作入口
  'ui_op_bind_product_structure.json',      // P1 绑定商品弹窗结构验证(Tab切换)
  'ui_op_contract_page.json',              // P2 合同页面结构验证
  // ── 跨端专项用例 ──
  'ui_op_data_consistency.json',           // P0 全平台数据一致性专项(分页/维权/商品管理)
  'ui_op_copy_standards.json',             // P1 全平台文案/空格/tooltips易错点专项
  // ── 已移出（非 UI 层逻辑）──
  // 'regression_op_settlement.json',       // 移出：结算金额计算属 API/DB 层逻辑
  // 'state_op_quick_audit_transition.json',// 移出：状态机流转属 API/状态层逻辑
];

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ─────────────────────────────────────────────
// DAG 调度：拓扑分层 + 级联 SKIP + 上下文传递
// ─────────────────────────────────────────────

/**
 * 将用例列表按 depends_on 分组为执行波次（wave）
 * 同一 wave 内的用例无互相依赖，可并行执行
 */
function buildDAGWaves(caseEntries) {
  const idMap = new Map(caseEntries.map(([id]) => [id, true]));
  const resolved = new Set();
  const remaining = new Map(caseEntries);
  const waves = [];
  let safety = caseEntries.length + 1;

  while (remaining.size > 0 && safety-- > 0) {
    const wave = [];
    for (const [id, entry] of remaining) {
      const deps = entry.data.depends_on || [];
      const allDepsOk = deps.every((d) => resolved.has(d) || !idMap.has(d));
      if (allDepsOk) wave.push([id, entry]);
    }
    if (wave.length === 0) {
      console.log('  ⚠️ 检测到循环依赖，剩余用例强制顺序执行:');
      for (const [id] of remaining) {
        console.log(`     ${id}`);
        wave.push([id, remaining.get(id)]);
      }
      remaining.clear();
    } else {
      for (const [id] of wave) { resolved.add(id); remaining.delete(id); }
    }
    waves.push(wave);
  }
  return waves;
}

/**
 * 查找某个失败用例的所有直接/间接下游用例（级联 SKIP）
 */
function findAllDownstream(failedId, caseEntries) {
  const downstream = new Set();
  let changed = true;
  while (changed) {
    changed = false;
    for (const [id, entry] of caseEntries) {
      if (downstream.has(id)) continue;
      const deps = entry.data.depends_on || [];
      if (deps.includes(failedId) || deps.some((d) => downstream.has(d))) {
        downstream.add(id);
        changed = true;
      }
    }
  }
  return downstream;
}

/**
 * 递归插值：将步骤中的 {{varName}} 替换为 sharedContext 中的值
 */
function interpolateValue(val, ctx) {
  if (typeof val === 'string') {
    return val.replace(/\{\{(\w+)\}\}/g, (_, name) => {
      return ctx[name] !== undefined ? String(ctx[name]) : `{{${name}}}`;
    });
  }
  if (Array.isArray(val)) return val.map((v) => interpolateValue(v, ctx));
  if (val && typeof val === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(val)) out[k] = interpolateValue(v, ctx);
    return out;
  }
  return val;
}

function tryParseJSON(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch (_) { return text; }
}

// 支持 "a|b|c" 的多关键词包含匹配
function urlMatches(url, pattern) {
  if (!url || !pattern) return false;
  return String(pattern).split('|').some((p) => p.trim() && url.includes(p.trim()));
}

function getByPath(obj, dotPath) {
  return dotPath.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function getByJsonPath(obj, jsonPath) {
  // 仅支持简单 $.a.b.c
  const clean = jsonPath.replace(/^\$\.?/, '');
  return clean ? getByPath(obj, clean) : obj;
}

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  try {
    await page.evaluate(() => document.querySelectorAll('.wm_div_id').forEach((w) => w.remove()));
  } catch (_) {}
  // 截图加 20s 超时保护：部分重弹层(多图)下 captureScreenshot 会命中默认 protocolTimeout(180s) 长时间卡死
  try {
    await Promise.race([
      page.screenshot({ path: fp, type: 'jpeg', quality: 70 }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('screenshot timeout 20s')), 20000)),
    ]);
  } catch (e) {
    console.log(`    ⚠️ 截图跳过(${name}): ${e.message}`);
    return null;
  }
  return fp;
}

// ─────────────────────────────────────────────
// 抓包：记录所有完成的请求（url/status/body），供 waitForAPI 与 post_asserts 使用
// ─────────────────────────────────────────────
async function startCapture(client) {
  const store = new Map();   // requestId -> req
  const finished = [];       // 完成的请求（含 responseBody）
  await client.send('Network.enable');
  try { await client.send('Network.setCacheDisabled', { cacheDisabled: true }); } catch (_) {}

  client.on('Network.requestWillBeSent', ({ requestId, request }) => {
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
    try {
      const { body, base64Encoded } = await client.send('Network.getResponseBody', { requestId });
      const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
      req.responseBody = tryParseJSON(text);
    } catch (_) { req.responseBody = null; }
    req.finishedAt = Date.now();
    finished.push(req);
  });

  return { finished };
}

// 等待某个接口完成（优先返回最近一条匹配；轮询直到超时）
async function waitForAPI(capture, urlPattern, timeout = 10000, since = 0) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const matched = capture.finished
      .filter((r) => urlMatches(r.url, urlPattern) && r.finishedAt >= since)
      .sort((a, b) => b.finishedAt - a.finishedAt);
    if (matched.length) return matched[0];
    await sleep(300);
  }
  throw new Error(`等待接口超时: ${urlPattern}`);
}

// ─────────────────────────────────────────────
// Step 执行器
// ─────────────────────────────────────────────
async function execClick(page, step) {
  if (step.text) {
    const clicked = await page.evaluate((text) => {
      const el = Array.from(document.querySelectorAll('button, a, [role="button"], [class*="btn"], span, td'))
        .find((e) => e.innerText && e.innerText.trim() === text && e.offsetParent !== null);
      if (el) { el.click(); return true; }
      // 兜底：包含匹配
      const el2 = Array.from(document.querySelectorAll('button, a, [role="button"], [class*="btn"], span, td'))
        .find((e) => e.innerText && e.innerText.trim().includes(text) && e.offsetParent !== null);
      if (el2) { el2.click(); return true; }
      return false;
    }, step.text);
    if (!clicked) throw new Error(`找不到文本为"${step.text}"的可点击元素`);
  } else if (step.selector) {
    await page.waitForSelector(step.selector, { timeout: 5000 });
    await page.click(step.selector);
  } else {
    throw new Error('click step 必须提供 text 或 selector');
  }
  await sleep(400);
}

async function execClickText(page, step) {
  const selector = step.selector || 'button, a, [role="button"], [class*="btn"], span';
  const clicked = await page.evaluate((txt, sel) => {
    const els = [...document.querySelectorAll(sel)];
    let el = els.find((e) => e.innerText && e.innerText.trim() === txt && e.offsetParent !== null);
    if (!el) el = els.find((e) => e.innerText && e.innerText.trim().includes(txt) && e.offsetParent !== null);
    if (el) {
      // 先滚入视口中心：部分 TBD/React 按钮在视口外或被浮层(如 AI 气泡)遮挡时 click 不触发
      el.scrollIntoView({ block: 'center', inline: 'center' });
      // 派发 hover 事件：部分行内操作按钮的 React onClick 在 pointer 交互后才绑定/激活
      const rr = el.getBoundingClientRect();
      const ev = { bubbles: true, cancelable: true, view: window, clientX: rr.x + rr.width / 2, clientY: rr.y + rr.height / 2 };
      ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointermove', 'mousemove'].forEach((t) => {
        const E = t.startsWith('pointer') ? PointerEvent : MouseEvent;
        try { el.dispatchEvent(new E(t, ev)); } catch (_) {}
      });
      el.click();
      return true;
    }
    return false;
  }, step.text, selector);
  if (!clicked) throw new Error(`clickText: 找不到文本为 '${step.text}' 的可见元素`);
  await sleep(400);
}

async function execFill(page, step) {
  const index = step.selectorIndex || 0;
  await page.waitForSelector(step.selector, { timeout: 5000 });
  const info = await page.evaluate((selector, value, idx) => {
    const els = [...document.querySelectorAll(selector)].filter((el) => el.offsetParent !== null);
    const el = els[idx];
    if (!el) return { ok: false, count: els.length };
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('focus', { bubbles: true }));
    el.dispatchEvent(new InputEvent('input', { bubbles: true, data: value }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
    return { ok: true, value: el.value };
  }, step.selector, step.value, index);
  if (!info || !info.ok) {
    throw new Error(`填写失败：selector='${step.selector}' index=${index}，找到 ${info ? info.count : '?'} 个可见元素`);
  }
  await sleep(300);
}

// selectOption：移植自 _node_bridge.js（label→formily-item→selector 坐标 + mouse.click）
async function execSelectOption(page, step) {
  const labelText = step.label;
  const optionText = step.option;
  const labelClass = step.labelClass || 'tbd-formily-item-label';

  await page.evaluate(() => document.querySelectorAll('.wm_div_id').forEach((w) => w.remove()));

  const coords = await page.evaluate((lText, lClass) => {
    const norm = (s) => (s || '').trim().replace(/[:：]\s*$/, '').trim();
    // label 候选（按特异性优先级）：表单标签类 → fieldLabel(CSS-Modules) → 通用 label/span/div
    const sels = [
      '.' + lClass,
      '.ant-form-item-label label',
      'label',
      '[class*="fieldLabel"]',
      '[class*="Label"]',
      '[class*="label"]',
      'span',
      'div',
    ];
    let label = null;
    for (const s of sels) {
      const cands = [...document.querySelectorAll(s)];
      // 用自身文本节点精确匹配，避免命中父容器长文本或「专利申请状态」这类超集
      label = cands.find((el) => {
        const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
        return norm(own) === lText || norm(el.innerText) === lText;
      });
      if (label) break;
    }
    if (!label) return { err: 'label not found: ' + lText };
    // 从 label 向上找含 select 控件的容器
    let item = label, sel = null;
    for (let i = 0; i < 6 && item; i++) {
      sel = item.querySelector && item.querySelector('.tbd-select-selector, .ant-select-selector, .tbd-select, .ant-select, select');
      if (sel) break;
      item = item.parentElement;
    }
    if (!sel) return { err: 'select control not found near label: ' + lText };
    let r = sel.getBoundingClientRect();
    if (!r.width) { sel.scrollIntoView({ block: 'nearest', behavior: 'instant' }); r = sel.getBoundingClientRect(); }
    if (!r.width) return { err: 'selector zero width' };
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, labelText, labelClass);
  if (coords.err) throw new Error('selectOption: ' + coords.err);

  await page.mouse.click(coords.x, coords.y);
  await sleep(600);

  const opt = await page.evaluate((oText) => {
    const optEls = [...document.querySelectorAll(
      '.tbd-select-item-option-content, .ant-select-item-option-content, .ant-select-item-option, option'
    )].filter((el) => el.innerText && el.innerText.includes(oText));
    if (optEls.length) {
      const el = optEls[0];
      el.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      const r = el.getBoundingClientRect();
      if (r.width) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.textContent.includes(oText) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP),
    });
    let node;
    while ((node = walker.nextNode())) {
      let el = node.parentElement;
      while (el && el !== document.body) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.width < 600) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        el = el.parentElement;
      }
    }
    return null;
  }, optionText);
  if (!opt) throw new Error('selectOption: option not found: ' + optionText);

  await page.mouse.click(opt.x, opt.y);
  await sleep(400);
}

async function execUncheckCheckbox(page, step) {
  const unchecked = await page.evaluate((lText, firstChecked) => {
    let cb;
    if (firstChecked) {
      cb = [...document.querySelectorAll('input[type="checkbox"]')].find((i) => i.checked && !i.disabled);
    } else {
      cb = [...document.querySelectorAll('input[type="checkbox"]')].find((i) => {
        const wrap = i.closest('label, .tbd-checkbox-wrapper, .ant-checkbox-wrapper') || i.parentElement;
        return wrap && wrap.innerText && wrap.innerText.includes(lText) && i.checked;
      });
    }
    if (!cb) return false;
    cb.click();
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }, step.labelText || '', step.firstChecked || false);
  // 未找到已勾选项不视为错误（可能默认已是取消态）
  await sleep(400);
  return unchecked;
}

async function execAssert(page, step, lastApi) {
  // 状态机断言（harness 能力，本地读 YAML 降级校验）
  if (step.assertion === 'stateTransition' || step.assertion === 'stateTransitionInvalid') {
    return assertStateTransition(step);
  }
  // 元素可见性断言
  if (step.assertion === 'elementVisible' || (step.target === 'element' && step.selector)) {
    const visible = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      // 不能用 offsetParent 判定：fixed 定位的 drawer/modal 其 offsetParent 恒为 null
      const r = el.getBoundingClientRect();
      const st = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
    }, step.selector);
    return { kind: 'elementVisible', selector: step.selector, expected: 'visible', pass: visible };
  }
  // 文本包含断言（pageContainsText / target=page）
  if (step.assertion === 'pageContainsText' || step.target === 'page') {
    const needle = step.text || step.contains;
    const text = await page.evaluate(() => document.body.innerText);
    const pass = text.includes(needle);
    return { kind: 'pageContains', expected: needle, actual: pass ? '(包含)' : '(不包含)', pass };
  }
  // API 响应文本断言
  if (step.target === 'api') {
    if (!lastApi) return { kind: 'api', expected: step.contains, actual: '(无 API 响应)', pass: false };
    const body = typeof lastApi.responseBody === 'string' ? lastApi.responseBody : JSON.stringify(lastApi.responseBody);
    const pass = body.includes(step.contains);
    return { kind: 'api', expected: step.contains, actual: pass ? '(包含)' : '(不包含)', pass };
  }
  // 页面数值一致性断言（统计概览 vs 列表）
  if (step.assertion === 'pageConsistency' || step.target === 'pageConsistency') {
    const check = await page.evaluate((script) => {
      try { return new Function(script)(); } catch (e) { return { pass: false, message: 'script error: ' + e.message }; }
    }, step.script);
    return { kind: 'pageConsistency', expected: step.expected || '一致性成立', actual: check.message || JSON.stringify(check).slice(0, 120), pass: !!check.pass };
  }
  // 维权记录弹层一致性（内置）：概览统计(疑似侵权共计/待发起/维权中/成功/失败) vs 下方维权记录列表状态数量
  // 商家端(9223)与运营端(9222)弹层同构，运营端无分桶文字统计时对应 overview 字段为 undefined 自动跳过
  if (step.assertion === 'tortConsistency') {
    const check = await page.evaluate(() => {
      const body = document.body.innerText;
      const overview = {};
      const m1 = body.match(/疑似侵权共计\s*(\d+)\s*例/);
      const m2 = body.match(/待发起维权\s*:?\s*(\d+)\s*例/);
      const m3 = body.match(/维权中\s*:?\s*(\d+)\s*例/);
      const m4 = body.match(/维权成功\s*:?\s*(\d+)\s*例/);
      const m5 = body.match(/维权失败\s*:?\s*(\d+)\s*例/);
      if (m1) overview.total = +m1[1];
      if (m2) overview.pending = +m2[1];
      if (m3) overview.ing = +m3[1];
      if (m4) overview.success = +m4[1];
      if (m5) overview.fail = +m5[1];
      const hdr = [...document.querySelectorAll('th,div,span')].find((e) => {
        const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
        return own === '维权记录';
      });
      let tbl = null;
      if (hdr) { let p = hdr.parentElement; for (let i = 0; i < 15 && p; i++) { if (p.querySelector('tbody')) { tbl = p; break; } p = p.parentElement; } }
      const allRows = tbl ? [...tbl.querySelectorAll('tbody tr')] : [];
      const rows = allRows.filter((r) => /4\d{8}/.test(r.innerText || ''));
      const list = { total: rows.length, pending: 0, ing: 0, success: 0, fail: 0 };
      rows.forEach((r) => {
        const t = r.innerText || '';
        if (/维权中/.test(t) && !/维权成功|维权失败/.test(t)) list.ing++;
        else if (/维权成功/.test(t)) list.success++;
        else if (/维权失败/.test(t)) list.fail++;
        else if (/待维权|待发起/.test(t)) list.pending++;
      });
      const sumStatus = list.pending + list.ing + list.success + list.fail;
      const emptyData = /暂无数据/.test(body) && list.total === 0;
      const issues = [];
      if (!emptyData) {
        if (overview.total !== undefined && overview.total !== list.total) issues.push('疑似侵权共计(' + overview.total + ')≠列表总条数(' + list.total + ')');
        if (overview.pending !== undefined && overview.pending !== list.pending) issues.push('待发起维权(' + overview.pending + ')≠列表待维权(' + list.pending + ')');
        if (overview.ing !== undefined && overview.ing !== list.ing) issues.push('维权中(' + overview.ing + ')≠列表维权中(' + list.ing + ')');
        if (overview.success !== undefined && overview.success !== list.success) issues.push('维权成功(' + overview.success + ')≠列表维权成功(' + list.success + ')');
        if (overview.fail !== undefined && overview.fail !== list.fail) issues.push('维权失败(' + overview.fail + ')≠列表维权失败(' + list.fail + ')');
        if (overview.total !== undefined && overview.total !== sumStatus) issues.push('疑似侵权共计(' + overview.total + ')≠各状态合计(' + sumStatus + ')');
      }
      const skipMsg = '列表暂无数据（' + (overview.total || 0) + '例疑似侵权尚未生成维权记录），条数一致性校验跳过';
      return { pass: issues.length === 0, overview, list, emptyData, message: emptyData ? skipMsg : (issues.length === 0 ? '一致性成立: overview=' + JSON.stringify(overview) + ' list=' + JSON.stringify(list) : '不一致: ' + issues.join('; ')) };
    });
    return { kind: 'tortConsistency', expected: step.expected || '维权弹层统计 vs 列表一致', actual: check.message, pass: !!check.pass };
  }
  // 列表页分页一致性（内置）：分页总数(共X条/总共N个) vs 每页条数(X条/页) vs 主表实际数据行数
  // 校验规则：当前页数据行数 应等于 min(pageSize, total)；无分页标记时跳过
  if (step.assertion === 'paginationConsistency') {
    const check = await page.evaluate(() => {
      const body = document.body.innerText;
      // 总数：兼容「共 X 条」「总共 N 个」「总共 N 个 SKC」
      const mTotal = body.match(/共\s*(\d+)\s*条/) || body.match(/总共\s*(\d+)\s*个/);
      const mSize = body.match(/(\d+)\s*条\s*\/\s*页/);
      const total = mTotal ? +mTotal[1] : undefined;
      const pageSize = mSize ? +mSize[1] : undefined;
      // 主数据表：取可见的、tbody 数据行数最多的表格
      const tables = [...document.querySelectorAll('table')].filter((t) => {
        const r = t.getBoundingClientRect();
        return r.width > 200 && r.height > 40;
      });
      let best = null;
      let bestRows = -1;
      tables.forEach((t) => {
        const trs = [...t.querySelectorAll('tbody tr')].filter((tr) => {
          const txt = (tr.innerText || '').trim();
          return txt && !/暂无数据|No Data/i.test(txt) && tr.querySelectorAll('td').length > 0;
        });
        if (trs.length > bestRows) { bestRows = trs.length; best = t; }
      });
      const emptyData = /暂无数据|No Data/i.test(body) && bestRows <= 0;
      const rowCount = bestRows < 0 ? 0 : bestRows;
      const issues = [];
      if (total === undefined) {
        return { pass: true, total, pageSize, rowCount, message: '未发现分页总数标记，分页一致性校验跳过' };
      }
      if (emptyData) {
        return { pass: true, total, pageSize, rowCount, message: '列表暂无数据（总数标记=' + total + '），分页一致性校验跳过' };
      }
      const expectRows = pageSize !== undefined ? Math.min(pageSize, total) : total;
      if (rowCount !== expectRows) issues.push('当前页数据行数(' + rowCount + ')≠期望行数(' + expectRows + ' = min(每页' + (pageSize === undefined ? '?' : pageSize) + ', 共' + total + '))');
      return { pass: issues.length === 0, total, pageSize, rowCount, message: issues.length === 0 ? '一致性成立: 共' + total + '条, 每页' + (pageSize === undefined ? '(未标注)' : pageSize) + ', 当前页' + rowCount + '行' : '不一致: ' + issues.join('; ') };
    });
    return { kind: 'paginationConsistency', expected: step.expected || '分页总数 vs 每页条数 vs 实际行数一致', actual: check.message, pass: !!check.pass };
  }
  throw new Error(`不支持的 assert: ${JSON.stringify(step).slice(0, 120)}`);
}

// 读取状态机 YAML 的 from/to 边（极简解析，无需 yaml 依赖）
let _smCache = null;
function loadStateMachineEdges(smPath) {
  if (_smCache) return _smCache;
  const abs = path.isAbsolute(smPath) ? smPath : path.join(__dirname, '..', smPath);
  const fp = fs.existsSync(abs) ? abs : path.join(SM_DIR, path.basename(smPath));
  const lines = fs.readFileSync(fp, 'utf8').split('\n');
  const edges = [];
  let cur = {};
  for (const raw of lines) {
    const line = raw.trim();
    const mFrom = line.match(/^-?\s*from:\s*(\w+)/);
    const mTo = line.match(/^to:\s*(\w+)/);
    if (mFrom) { if (cur.from && cur.to) edges.push(cur); cur = { from: mFrom[1] }; }
    else if (mTo) { cur.to = mTo[1]; }
  }
  if (cur.from && cur.to) edges.push(cur);
  _smCache = edges;
  return edges;
}

function assertStateTransition(step) {
  const edges = loadStateMachineEdges(step.stateMachine);
  const exists = edges.some((e) => e.from === step.from && e.to === step.to);
  const shouldExist = step.assertion === 'stateTransition';
  const pass = shouldExist ? exists : !exists;
  return {
    kind: step.assertion,
    from: step.from,
    to: step.to,
    edgeExistsInYaml: exists,
    expected: shouldExist ? '合法转换' : '非法转换',
    pass,
    note: pass ? '' : `YAML 中 ${step.from}->${step.to} 边${exists ? '存在' : '不存在'}，与预期不符（可能为文档-实现偏差）`,
  };
}

// ─────────────────────────────────────────────
// post_asserts.apiResponse 校验
// ─────────────────────────────────────────────
function runPostAsserts(capture, postAsserts) {
  const results = [];
  for (const pa of postAsserts || []) {
    if (pa.type !== 'apiResponse') { results.push({ ...pa, pass: false, note: '不支持的 post_assert 类型' }); continue; }
    const req = capture.finished.filter((r) => urlMatches(r.url, pa.urlPattern)).sort((a, b) => b.finishedAt - a.finishedAt)[0];
    if (!req) { results.push({ desc: pa.description, urlPattern: pa.urlPattern, pass: false, note: '未捕获到匹配请求' }); continue; }
    const body = req.responseBody;
    let value;
    if (pa.jsonPath) value = getByJsonPath(body, pa.jsonPath);
    else if (pa.path) value = getByPath(body, pa.path);
    else value = body;

    let pass;
    if (pa.equals !== undefined) pass = value === pa.equals;
    else if (pa.notNull) pass = value != null;
    else if (pa.condition === 'notEmpty') pass = value != null && (Array.isArray(value) ? value.length > 0 : String(value).length > 0);
    else pass = value != null;

    results.push({ desc: pa.description, urlPattern: pa.urlPattern, expected: pa.equals ?? pa.condition ?? (pa.notNull ? 'notNull' : 'exists'), actual: JSON.stringify(value)?.slice(0, 80), pass });
  }
  return results;
}

// ─────────────────────────────────────────────
// 单用例执行
// ─────────────────────────────────────────────
async function runCase(browser, caseFile, sharedContext = {}) {
  const input = JSON.parse(fs.readFileSync(path.join(CASES_DIR, caseFile), 'utf8'));
  const ctx = sharedContext;
  const out = {
    file: caseFile,
    id: input.id,
    name: input.name,
    priority: input.priority,
    status: 'pass',
    steps: [],
    postAsserts: [],
    screenshots: [],
    apiCount: 0,
  };
  console.log(`\n═══ [${input.priority}] ${input.name} ═══`);
  console.log(`    ${caseFile}`);

  let page;
  const pages = await browser.pages();
  if (input.context && input.context.urlPattern) {
    page = pages.find((p) => p.url().includes(input.context.urlPattern));
  }
  if (!page && input.context && input.context.url) {
    page = await browser.newPage();
    await page.goto(input.context.url, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
  }
  if (!page) page = pages[0] || (await browser.newPage());

  const client = await page.target().createCDPSession();
  const capture = await startCapture(client);
  await sleep((input.context && input.context.waitAfterLoad) || 2000);

  let lastApi = null;
  for (let i = 0; i < input.steps.length; i++) {
    const step = interpolateValue(input.steps[i], ctx);
    const sr = { index: i, type: step.type, description: step.description || '', status: 'pass' };
    const stepSince = Date.now();
    try {
      switch (step.type) {
        case 'navigate':
          await page.goto(step.url, { waitUntil: step.waitUntil === 'networkidle' ? 'networkidle2' : (step.waitUntil || 'networkidle2'), timeout: 30000 });
          break;
        case 'wait':
          await sleep(step.ms);
          break;
        case 'click':
          await execClick(page, step);
          break;
        case 'clickText':
          await execClickText(page, step);
          break;
        case 'fill':
          await execFill(page, step);
          break;
        case 'selectOption':
          await execSelectOption(page, step);
          break;
        case 'uncheckCheckbox':
          sr.unchecked = await execUncheckCheckbox(page, step);
          break;
        case 'waitForAPI':
          lastApi = await waitForAPI(capture, step.urlPattern, step.timeout || 10000, stepSince - 8000);
          sr.matchedUrl = lastApi.url;
          sr.matchedStatus = lastApi.status;
          break;
        case 'screenshot': {
          const p = await ss(page, `${input.id}-step${i}-${step.label || step.name || ''}`);
          sr.screenshotPath = p;
          out.screenshots.push({ stepIndex: i, path: p });
          break;
        }
        case 'assert': {
          sr.assertResult = await execAssert(page, step, lastApi);
          if (!sr.assertResult.pass) { sr.status = 'fail'; out.status = out.status === 'error' ? 'error' : 'fail'; }
          break;
        }
        case 'apiCall':
          // mtop 调用属 harness 能力，标记跳过
          sr.status = 'skip';
          sr.note = `apiCall(${step.method}:${step.api}) 需 Python harness 执行`;
          break;
        default:
          sr.status = 'skip';
          sr.note = `未知 step 类型: ${step.type}`;
      }
      const icon = sr.status === 'pass' ? '✅' : sr.status === 'fail' ? '❌' : '⚠️';
      const detail = (sr.assertResult && /Consistency$/.test(sr.assertResult.kind || '')) ? ` → ${sr.assertResult.actual}` : '';
      console.log(`  ${icon} [${i}] ${step.type} - ${sr.description}${detail}`);
    } catch (e) {
      sr.status = 'error';
      sr.error = e.message;
      out.status = 'error';
      out.error = { stepIndex: i, message: e.message };
      console.log(`  💥 [${i}] ${step.type} - ${sr.description} → ${e.message}`);
      try { const p = await ss(page, `${input.id}-error-step${i}`); out.screenshots.push({ stepIndex: -1, path: p }); } catch (_) {}
      break; // 与 harness 一致：出错停止
    }
    out.steps.push(sr);
  }

  // post_asserts
  if (input.post_asserts && input.post_asserts.length) {
    out.postAsserts = runPostAsserts(capture, input.post_asserts);
    for (const pa of out.postAsserts) {
      const icon = pa.pass ? '✅' : '❌';
      console.log(`  ${icon} [post] ${pa.desc || pa.urlPattern}`);
      if (!pa.pass && out.status === 'pass') out.status = 'fail';
    }
  }

  out.apiCount = capture.finished.length;
  try { await client.detach(); } catch (_) {}
  return out;
}

// ─────────────────────────────────────────────
// 主入口
// ─────────────────────────────────────────────
// 解析命令行参数：分离 --out <path> 与用例过滤关键字
function parseArgs(argv) {
  const filters = [];
  let out = DEFAULT_RESULT_FP;
  let sequential = false;
  let validateOnly = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out' || a === '-o') {
      out = argv[++i];
    } else if (a.startsWith('--out=')) {
      out = a.slice('--out='.length);
    } else if (a === '--sequential' || a === '-s') {
      sequential = true;
    } else if (a === '--validate' || a === '-v') {
      validateOnly = true;
    } else {
      filters.push(a);
    }
  }
  if (out && !path.isAbsolute(out)) out = path.join(__dirname, '..', out);
  return { filters, out, sequential, validateOnly };
}

const CASE_TIMEOUT_MS = parseInt(process.env.CASE_TIMEOUT_MS, 10) || 60000;

const VALID_STEP_TYPES = new Set([
  'navigate', 'wait', 'click', 'clickText', 'fill', 'selectOption', 'uncheckCheckbox',
  'waitForAPI', 'screenshot', 'assert', 'hover', 'pressKey', 'upload',
  'evaluate', 'apiCall', 'dbQuery', 'assertDbResult', 'assertStore', 'pageConsistency',
]);

function validateCases(cases) {
  let totalErrors = 0;
  let totalWarnings = 0;
  const caseIds = new Set();

  for (const file of cases) {
    const fp = path.join(CASES_DIR, file);
    const errors = [];
    const warnings = [];

    // 1. 文件存在性
    if (!fs.existsSync(fp)) {
      console.log(`✗ ${file}: 文件不存在`);
      totalErrors++;
      continue;
    }

    // 2. JSON 语法
    let data;
    try {
      data = JSON.parse(fs.readFileSync(fp, 'utf8'));
    } catch (e) {
      console.log(`✗ ${file}: JSON 语法错误 - ${e.message}`);
      totalErrors++;
      continue;
    }

    // 3. 必填字段
    if (!data.id) errors.push('缺少 id');
    if (!data.name) errors.push('缺少 name');
    if (!Array.isArray(data.steps) || data.steps.length === 0) errors.push('steps 为空或不是数组');

    // 4. id 唯一性
    if (data.id) {
      if (caseIds.has(data.id)) errors.push(`id "${data.id}" 重复`);
      caseIds.add(data.id);
    }

    // 5. steps 结构校验
    if (Array.isArray(data.steps)) {
      data.steps.forEach((step, i) => {
        if (!step.type) { errors.push(`steps[${i}]: 缺少 type`); return; }
        if (!VALID_STEP_TYPES.has(step.type)) warnings.push(`steps[${i}]: 未知类型 "${step.type}"`);
        if (step.type === 'navigate' && !step.url && step.url !== 'current') errors.push(`steps[${i}]: navigate 缺少 url`);
        if (step.type === 'wait' && step.ms === undefined) errors.push(`steps[${i}]: wait 缺少 ms`);
        if (step.type === 'fill' && !step.selector) errors.push(`steps[${i}]: fill 缺少 selector`);
        if (step.type === 'assert' && !step.target && !step.assertion && !step.script) errors.push(`steps[${i}]: assert 缺少 target/assertion/script`);
        if (step.type === 'assert' && step.target === 'page' && !step.contains) errors.push(`steps[${i}]: assert page 缺少 contains`);
      });
    }

    // 6. context 校验
    if (data.context) {
      if (!data.context.url && !data.context.urlPattern) warnings.push('context 无 url 和 urlPattern');
    }

    // 7. post_asserts 校验
    if (data.post_asserts && Array.isArray(data.post_asserts)) {
      data.post_asserts.forEach((pa, i) => {
        if (!pa.urlPattern) errors.push(`post_asserts[${i}]: 缺少 urlPattern`);
      });
    }

    // 输出
    if (errors.length === 0 && warnings.length === 0) {
      console.log(`✓ ${file} (${data.steps.length} steps)`);
    } else {
      errors.forEach(e => console.log(`✗ ${file}: ${e}`));
      warnings.forEach(w => console.log(`⚠ ${file}: ${w}`));
      totalErrors += errors.length;
      totalWarnings += warnings.length;
    }
  }

  console.log(`\n校验完成: ${cases.length} 个用例 | ${totalErrors} 错误 | ${totalWarnings} 警告`);
  return totalErrors === 0;
}

async function main() {
  const { filters, out: resultFp, sequential, validateOnly } = parseArgs(process.argv.slice(2));
  const cases = filters.length
    ? OP_CASES.filter((f) => filters.some((k) => f.includes(k)))
    : OP_CASES;

  // --validate 模式：仅校验用例文件，不连接浏览器
  if (validateOnly) {
    console.log('🔍 用例校验模式（--validate）\n');
    const ok = validateCases(cases);
    process.exit(ok ? 0 : 1);
  }

  console.log('🔗 连接 CDP:', CDP_URL);
  console.log('📄 结果输出:', resultFp);
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null, protocolTimeout: 60000 });
  console.log(`✅ 已连接 Chrome，待执行用例: ${cases.length}\n`);

  // 加载用例并构建 (id, {file, data}) 映射
  const caseEntries = cases.map((file) => {
    const data = JSON.parse(fs.readFileSync(path.join(CASES_DIR, file), 'utf8'));
    return [data.id, { file, data }];
  });
  const caseFileMap = new Map(caseEntries.map(([id, e]) => [id, e.file]));

  // DAG 分层：wave = 同层可并行的用例组
  const waves = buildDAGWaves(caseEntries);
  console.log('📐 DAG 执行计划:');
  waves.forEach((wave, i) => {
    const ids = wave.map(([id]) => id).join(', ');
    const mode = wave.length > 1 ? '并行' : '串行';
    console.log(`   Wave ${i + 1} [${mode}]: ${ids}`);
  });
  console.log('');

  const sharedContext = {};  // {caseId: {varName: value}}
  const allResults = [];     // [{file, id, name, status, skipReason, ...}]
  const skipped = new Map(); // caseId -> skipReason

  for (let wi = 0; wi < waves.length; wi++) {
    const wave = waves[wi];
    const runnable = wave.filter(([id]) => !skipped.has(id));
    const toSkip = wave.filter(([id]) => skipped.has(id));

    // 记录级联 SKIP 的用例
    for (const [id, entry] of toSkip) {
      const result = {
        file: entry.file,
        id: entry.data.id,
        name: entry.data.name,
        priority: entry.data.priority,
        status: 'skip',
        skipReason: skipped.get(id),
        steps: [],
        postAsserts: [],
        screenshots: [],
        apiCount: 0,
      };
      allResults.push(result);
      console.log(`\n⏭️  [SKIP] ${entry.data.name}`);
      console.log(`   原因: ${skipped.get(id)}`);
    }

    if (runnable.length === 0) continue;

    // 构建单个用例的执行函数
    const runOne = async ([id, entry]) => {
      const consumes = entry.data.consumes || {};
      const ctx = {};
      for (const [localVar, ref] of Object.entries(consumes)) {
        const [srcCaseId, srcVar] = ref.split('.');
        if (sharedContext[srcCaseId] && sharedContext[srcCaseId][srcVar] !== undefined) {
          ctx[localVar] = sharedContext[srcCaseId][srcVar];
        }
      }
      console.log(`\n▶️  [Wave ${wi + 1}] 执行: ${entry.data.name}`);
      try {
        const result = await Promise.race([
          runCase(browser, entry.file, ctx),
          new Promise((_, rej) => setTimeout(() => rej(new Error(`用例执行超时 ${CASE_TIMEOUT_MS}ms`)), CASE_TIMEOUT_MS)),
        ]);
        return { id, entry, result };
      } catch (e) {
        return {
          id, entry,
          result: {
            file: entry.file, id: entry.data.id, name: entry.data.name,
            priority: entry.data.priority, status: 'error',
            error: { message: e.message }, steps: [], postAsserts: [], screenshots: [], apiCount: 0,
          },
        };
      }
    };

    // sequential 模式逐个串行，否则同 wave 内并行
    const waveResults = sequential
      ? await (async () => { const out = []; for (const item of runnable) out.push(await runOne(item)); return out; })()
      : await Promise.all(runnable.map(runOne));

    // 处理 wave 结果：写 produces + 标记下游 SKIP
    for (const { id, entry, result } of waveResults) {
      allResults.push(result);

      if (result.status === 'pass') {
        const produces = entry.data.produces || {};
        if (Object.keys(produces).length > 0) {
          sharedContext[id] = {};
          for (const [varName, valueOrPath] of Object.entries(produces)) {
            if (typeof valueOrPath === 'string' && valueOrPath.startsWith('$.')) {
              sharedContext[id][varName] = getByPath(result, valueOrPath.slice(2));
            } else {
              sharedContext[id][varName] = valueOrPath;
            }
          }
          console.log(`  📤 ${id} produces:`, JSON.stringify(sharedContext[id]));
        }
      } else {
        // FAIL/ERROR → 级联 SKIP 所有直接/间接下游
        const downstream = findAllDownstream(id, caseEntries);
        for (const dsId of downstream) {
          if (!skipped.has(dsId)) {
            skipped.set(dsId, `因 ${entry.data.name} ${result.status === 'fail' ? 'FAIL' : 'ERROR'} 而 SKIP`);
          }
        }
      }
    }
  }

  // 恢复原始用例顺序输出
  const orderedResults = [];
  for (const [id, entry] of caseEntries) {
    const r = allResults.find((r) => r.id === id || r.file === entry.file);
    if (r) orderedResults.push(r);
  }

  browser.disconnect();

  // 汇总
  console.log('\n═══════════════════════════════');
  console.log('📊 原创保护 UI 回归结果汇总（DAG 调度）');
  console.log('═══════════════════════════════');
  const pass = orderedResults.filter((r) => r.status === 'pass').length;
  const fail = orderedResults.filter((r) => r.status === 'fail').length;
  const skip = orderedResults.filter((r) => r.status === 'skip').length;
  const err = orderedResults.filter((r) => r.status === 'error').length;
  console.log(`总计: ${orderedResults.length} 个用例 | ✅ pass: ${pass} | ❌ fail: ${fail} | ⏭️ skip: ${skip} | 💥 error: ${err}`);
  orderedResults.forEach((r) => {
    const icon = r.status === 'pass' ? '✅' : r.status === 'fail' ? '❌' : r.status === 'skip' ? '⏭️' : '💥';
    const reason = r.skipReason ? ` (${r.skipReason})` : '';
    console.log(`  ${icon} ${r.name || r.file} (${r.status})${reason}`);
  });

  if (!fs.existsSync(path.dirname(resultFp))) fs.mkdirSync(path.dirname(resultFp), { recursive: true });
  fs.writeFileSync(resultFp, JSON.stringify({
    summary: { total: orderedResults.length, pass, fail, skip, error: err, cdpUrl: CDP_URL, time: new Date().toISOString() },
    results: orderedResults,
  }, null, 2));
  console.log(`\n📁 结果已保存: ${resultFp}`);

  process.exit(err > 0 ? 1 : 0);
}

main().catch((e) => { console.error('❌ 执行失败:', e.message); process.exit(1); });
