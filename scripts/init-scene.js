/**
 * init-scene.js — 场景化 Skill 初始化脚本
 *
 * 连接浏览器，探索目标页面结构，自动生成：
 *   - skills/web-automation/scenes/{scene-name}/SKILL.md
 *   - skills/web-automation/scenes/{scene-name}/knowledge/{scene-name}.json
 *   - skills/web-automation/scenes/{scene-name}/references/overview.md
 *   并更新 web-automation/knowledge/index.json
 *
 * 用法：
 *   node scripts/init-scene.js --name <scene-name> --url <target-url> [--skill-desc "描述"]
 *
 * 示例：
 *   node scripts/init-scene.js \
 *     --name my-page-test \
 *     --url "https://example.alibaba-inc.com/some/route" \
 *     --skill-desc "某某页面测试"
 */

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

const SCENES_DIR = path.resolve(__dirname, '../scenes');
const INDEX_PATH = path.resolve(__dirname, '../knowledge/index.json');

// ─── CLI 参数解析 ────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      args[argv[i].slice(2)] = argv[i + 1] || '';
      i++;
    }
  }
  return args;
}

const args  = parseArgs(process.argv.slice(2));
const SCENE = args.name;
const URL   = args.url;
const DESC  = args['skill-desc'] || `${SCENE} 页面自动化测试`;

if (!SCENE || !URL) {
  console.error('Usage: node init-scene.js --name <scene-name> --url <url> [--skill-desc "描述"]');
  process.exit(1);
}

// ─── 主流程 ─────────────────────────────────────────────────────────────────

(async () => {
  console.log(`\n🔍 开始探索页面: ${URL}`);
  console.log(`📦 Skill 名称: ${SCENE}\n`);

  const cdpUrl = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
  const browser = await puppeteer.connect({ browserURL: cdpUrl, defaultViewport: null });
  const pages   = await browser.pages();

  // 找到目标页面，或新开一个
  let page = pages.find(p => p.url().includes(new URL(URL).hostname));
  if (!page) {
    page = await browser.newPage();
    await page.goto(URL, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(2000);
  }

  const client = await page.target().createCDPSession();

  // 最大化 + 清水印
  const { windowId } = await client.send('Browser.getWindowForTarget');
  await client.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'maximized' } });
  await sleep(500);
  await clearWatermarks(page);

  // ─── 探索阶段 ──────────────────────────────────────────────────────────────
  console.log('📡 探索 DOM 结构...');
  const domResult = await exploreDom(page);

  console.log('📡 监听网络请求 (5s)...');
  const apiResult = await captureApis(client, page, 5000);

  console.log('📡 检测坑点...');
  const traps = await detectTraps(page);

  // 截图
  const { data: screenshotData } = await client.send('Page.captureScreenshot', { format: 'png' });
  const shotDir  = process.env.WEB_AUTO_SCREENSHOTS_DIR
    ? require('path').join(process.env.WEB_AUTO_SCREENSHOTS_DIR, today())
    : require('path').join(__dirname, '..', 'artifacts', 'screenshots', today());
  fs.mkdirSync(shotDir, { recursive: true });
  const shotPath = `${shotDir}/init-scene-${SCENE}-${Date.now()}.png`;
  fs.writeFileSync(shotPath, Buffer.from(screenshotData, 'base64'));
  console.log(`📸 截图: ${shotPath}`);

  browser.disconnect();

  // ─── 生成产物 ─────────────────────────────────────────────────────────────
  const skillDir = path.join(SCENES_DIR, SCENE);
  fs.mkdirSync(path.join(skillDir, 'knowledge'),   { recursive: true });
  fs.mkdirSync(path.join(skillDir, 'references'), { recursive: true });
  fs.mkdirSync(path.join(skillDir, 'scripts'),    { recursive: true });

  const urlObj   = new URL(URL);
  const host     = urlObj.hostname;
  const route    = urlObj.pathname;
  const knowledge = buildKnowledge({ domResult, apiResult, traps, url: URL, host, route, scene: SCENE });

  // 写 knowledge JSON
  const knowledgePath = path.join(skillDir, 'knowledge', `${SCENE}.json`);
  fs.writeFileSync(knowledgePath, JSON.stringify(knowledge, null, 2), 'utf8');
  console.log(`✅ knowledge 已生成: ${knowledgePath}`);

  // 写 SKILL.md
  const skillMd = buildSkillMd({ scene: SCENE, desc: DESC, url: URL, knowledge });
  fs.writeFileSync(path.join(skillDir, 'SKILL.md'), skillMd, 'utf8');
  console.log(`✅ SKILL.md 已生成`);

  // 写 references/overview.md
  const overviewMd = buildOverview({ scene: SCENE, url: URL, domResult, traps, apiResult });
  fs.writeFileSync(path.join(skillDir, 'references', 'overview.md'), overviewMd, 'utf8');
  console.log(`✅ references/overview.md 已生成`);

  // 更新全局 index.json
  updateIndex({ scene: SCENE, host, route, desc: DESC, skillDir });
  console.log(`✅ web-automation/knowledge/index.json 已更新`);

  // ─── 摘要 ────────────────────────────────────────────────────────────────
  console.log('\n========== 初始化完成 ==========');
  console.log(`Skill 目录: ${skillDir}`);
  console.log(`字段发现数: ${Object.keys(knowledge.fields || {}).length}`);
  console.log(`API 发现数: ${Object.keys(knowledge.apis || {}).length}`);
  console.log(`坑点预检: ${traps.length} 项`);
  console.log(`\n⚠️  需要你补充的内容（confidence=low 的字段）:`);
  for (const [name, field] of Object.entries(knowledge.fields || {})) {
    if (field.confidence === 'low') {
      console.log(`  - ${name}: ${field.note}`);
    }
  }
  console.log('\n下一步: 执行一次实际测试，knowledge_updater 会自动将 draft → verified');
  console.log(`截图: ${shotPath}`);

})().catch(e => { console.error('Error:', e.message); process.exit(1); });


// ─── DOM 探索 ─────────────────────────────────────────────────────────────────

async function exploreDom(page) {
  return await page.evaluate(() => {
    const result = { inputs: [], buttons: [], iframes: [], pageTitle: '', mainText: '' };

    result.pageTitle = document.title || '';
    result.mainText  = document.body.innerText.slice(0, 300);

    // inputs / textarea / select
    const inputEls = Array.from(document.querySelectorAll('input, textarea, select'));
    const inputGroups = {};
    for (const el of inputEls) {
      if (el.offsetParent === null) continue;
      const key = [el.tagName, el.type || '', el.placeholder || '', el.className.slice(0, 40)].join('|');
      if (!inputGroups[key]) {
        inputGroups[key] = { count: 0, el };
      }
      inputGroups[key].count++;
    }
    for (const { count, el } of Object.values(inputGroups)) {
      const rect = el.getBoundingClientRect();
      result.inputs.push({
        tag:         el.tagName.toLowerCase(),
        type:        el.type || null,
        placeholder: el.placeholder || null,
        id:          el.id || null,
        name:        el.name || null,
        className:   el.className.slice(0, 60),
        isReact:     !!el._reactFiber || !!el.__reactFiber || !!el._reactInternals,
        count,
        rect:        { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width) },
      });
    }

    // buttons
    const btnEls = Array.from(document.querySelectorAll('button, [role="button"], a[class*="btn"]'));
    const btnTexts = new Set();
    for (const el of btnEls) {
      if (el.offsetParent === null) continue;
      const text = el.innerText?.trim().slice(0, 30);
      if (!text || btnTexts.has(text)) continue;
      btnTexts.add(text);
      result.buttons.push({
        text,
        tag:       el.tagName.toLowerCase(),
        className: el.className.slice(0, 60),
        disabled:  el.disabled || el.getAttribute('aria-disabled') === 'true',
      });
    }

    // iframes
    for (const fr of document.querySelectorAll('iframe')) {
      result.iframes.push({ src: fr.src?.slice(0, 100) || '', id: fr.id || '' });
    }

    return result;
  });
}


// ─── API 监听 ─────────────────────────────────────────────────────────────────

async function captureApis(client, page, durationMs) {
  const apis = {};
  await client.send('Network.enable');

  client.on('Network.responseReceived', (e) => {
    const url = e.response?.url || '';
    // 只记录 XHR/fetch，排除静态资源
    if (e.type !== 'XHR' && e.type !== 'Fetch') return;
    const urlKey = url.split('?')[0].slice(-80); // 取路径后80字符作 key
    if (!apis[urlKey]) {
      apis[urlKey] = { url: url.slice(0, 120), method: e.response?.mimeType || '', count: 0 };
    }
    apis[urlKey].count++;
  });

  // 触发一次滚动来激活懒加载请求
  await page.evaluate(() => window.scrollBy(0, 300));
  await sleep(durationMs);

  return Object.values(apis).slice(0, 20); // 最多返回 20 个
}


// ─── 坑点预检 ─────────────────────────────────────────────────────────────────

async function detectTraps(page) {
  return await page.evaluate(() => {
    const traps = [];

    // 水印
    if (document.querySelectorAll('.wm_div_id, [class*="watermark"]').length > 0)
      traps.push({ trap: 'watermark', desc: '页面有水印层（.wm_div_id），操作前需清除' });

    // 引导弹窗
    const tourBtns = Array.from(document.querySelectorAll('button')).filter(b =>
      ['下一个', '关闭', 'Next', 'Close'].includes(b.innerText?.trim())
    );
    if (tourBtns.length > 0)
      traps.push({ trap: 'guideTour', desc: `发现引导弹窗按钮（${tourBtns.map(b => b.innerText.trim()).join('/')}），进入页面后需先关闭` });

    // React 受控 input
    const reactInputs = Array.from(document.querySelectorAll('input, textarea')).filter(el =>
      el._reactFiber || el.__reactFiber || el._reactInternals
    );
    if (reactInputs.length > 0)
      traps.push({ trap: 'reactInput', desc: `发现 ${reactInputs.length} 个 React 受控 input，填值必须用 native setter + dispatchEvent` });

    // iframe 嵌套
    if (document.querySelectorAll('iframe').length > 0) {
      const srcs = Array.from(document.querySelectorAll('iframe')).map(f => f.src?.slice(0, 60)).join(', ');
      traps.push({ trap: 'iframe', desc: `页面含 iframe（${srcs}），跨 frame 操作需单独获取 frame 引用` });
    }

    // 通知面板
    if (document.querySelectorAll('[class*="notify_bg"], [class*="notify_body"]').length > 0)
      traps.push({ trap: 'notifyPanel', desc: '有通知面板（notify_bg），可能遮挡操作元素' });

    // 弹窗/overlay
    const overlays = document.querySelectorAll('.next-overlay-wrapper, [class*="overlay"]');
    if (overlays.length > 0)
      traps.push({ trap: 'overlay', desc: `发现 ${overlays.length} 个 overlay 元素，操作前需清除残留` });

    return traps;
  });
}


// ─── knowledge JSON 构建 ───────────────────────────────────────────────────────

function buildKnowledge({ domResult, apiResult, traps, url, host, route, scene }) {
  const fields = {};
  const seen   = {};

  for (const inp of domResult.inputs) {
    const rawName = inp.placeholder || inp.id || inp.name || `${inp.tag}_field`;

    // 如果有多个相同 placeholder 的 input，标记为 low confidence
    const isAmbiguous = inp.count > 1;
    const fieldName   = isAmbiguous ? `${rawName}（共${inp.count}个，需确认各字段含义）` : rawName;

    // 防止重名
    const key = seen[rawName] !== undefined ? `${rawName}_${seen[rawName]++}` : rawName;
    seen[rawName] = (seen[rawName] || 0) + 1;

    fields[key] = {
      type:       inp.tag === 'select' ? 'selectOption' : 'fill',
      tag:        inp.tag,
      selector:   inp.placeholder
        ? `${inp.tag}[placeholder=${JSON.stringify(inp.placeholder)}]`
        : (inp.id ? `#${inp.id}` : inp.tag),
      selectorIndex: isAmbiguous ? 0 : undefined,
      isReact:    inp.isReact || undefined,
      confidence: isAmbiguous ? 'low' : 'high',
      note:       isAmbiguous ? `共 ${inp.count} 个相同 placeholder 的输入框，需用 selectorIndex 区分各字段含义` : undefined,
    };
    // 去掉 undefined 字段
    for (const k of Object.keys(fields[key])) {
      if (fields[key][k] === undefined) delete fields[key][k];
    }
  }

  const actions = {};
  for (const btn of domResult.buttons) {
    if (['搜索', '查询', 'Search'].includes(btn.text)) {
      actions[btn.text] = { type: 'clickText', text: btn.text, waitAfter: 3000 };
    } else if (['重置', '清空', 'Reset'].includes(btn.text)) {
      actions[btn.text] = { type: 'clickText', text: btn.text, waitAfter: 600 };
    } else {
      actions[btn.text] = { type: 'clickText', text: btn.text };
    }
  }

  const apis = {};
  for (const api of apiResult) {
    const name = api.url.split('/').pop() || 'unknown';
    apis[name] = {
      urlKeyword: name,
      url:        api.url,
      count:      api.count,
      confidence: 'low',
      note:       '自动发现，需人工确认请求/响应字段含义',
    };
  }

  const knownIssues = traps.map(t => t.desc);

  return {
    id:          scene,
    description: `${scene} 页面自动探索结果`,
    lastUpdated: today(),
    pageUrl:     url,
    urlPattern:  host,
    urlRoute:    route,
    _meta: {
      initStatus:  'draft',
      exploredAt:  today(),
      exploredUrl: url,
      staleFields: [],
    },
    fields,
    actions,
    apis,
    knownIssues,
    assertHints: {},
  };
}


// ─── SKILL.md 模板 ─────────────────────────────────────────────────────────────

function buildSkillMd({ scene, desc, url, knowledge }) {
  const lowFields = Object.entries(knowledge.fields || {})
    .filter(([, v]) => v.confidence === 'low')
    .map(([k]) => `- \`${k}\`（需确认含义和 selectorIndex）`)
    .join('\n') || '- 无';

  return `---
name: web-automation/${scene}
description: ${desc}。（自动生成 draft，首次执行后升级为 verified）
parent: web-automation
---

# ${scene}

> ⚠️ 本 Skill 由 \`init-scene.js\` 自动生成，状态为 **draft**。
> 首次实际执行成功后，knowledge_updater 会自动将状态升级为 **verified**。

## 环境信息

| 项目 | 值 |
|------|---|
| 页面 URL | \`${url}\` |
| Knowledge ID | \`${scene}\` |
| 认证 | 阿里内网 SSO |

## 待人工补充

以下字段为 \`confidence: low\`，需要你确认含义后更新 knowledge：

${lowFields}

## 操作动线

> 探索阶段仅发现了页面结构，业务操作动线需要你补充。

## 参考文档

| 文档 | 说明 |
|------|------|
| \`knowledge/${scene}.json\` | 自动探索的页面结构（draft）|
| \`references/overview.md\` | 页面概述（自动生成）|
`;
}


// ─── overview.md 模板 ──────────────────────────────────────────────────────────

function buildOverview({ scene, url, domResult, traps, apiResult }) {
  const btnList  = domResult.buttons.map(b => `- \`${b.text}\``).join('\n') || '- 未发现';
  const trapList = traps.map(t => `- **${t.trap}**: ${t.desc}`).join('\n') || '- 未发现坑点';
  const apiList  = apiResult.map(a => `- \`${a.url.slice(-80)}\`（出现 ${a.count} 次）`).join('\n') || '- 未捕获';

  return `# ${scene} 页面概述

> 由 \`init-scene.js\` 自动生成于 ${today()}

## 页面 URL

\`${url}\`

## 页面标题

${domResult.pageTitle || '（未获取）'}

## 发现的操作按钮

${btnList}

## 发现的 API 请求

${apiList}

## 坑点预检

${trapList}

## 备注

> 此文件为自动生成的原始探索结果，供人工补充参考。
> 结构化内容请查看 \`knowledge/${scene}.json\`。
`;
}


// ─── 更新全局 index.json ──────────────────────────────────────────────────────

function updateIndex({ scene, host, route, desc, skillDir }) {
  let index = { entries: [] };
  if (fs.existsSync(INDEX_PATH)) {
    index = JSON.parse(fs.readFileSync(INDEX_PATH, 'utf8'));
  }

  // 已存在则跳过
  const exists = index.entries.some(e => e.id === scene);
  if (!exists) {
    index.entries.push({
      id:    scene,
      platform: scene,
      description: desc,
      host,
      route,
      skill: `web-automation/${scene}`,
      file:  `skills/web-automation/scenes/${scene}/knowledge/${scene}.json`,
      covers: [],
    });
    fs.writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2), 'utf8');
  }
}


// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function today()   { return new Date().toISOString().slice(0, 10); }

async function clearWatermarks(page) {
  await page.evaluate(() => {
    document.querySelectorAll('.wm_div_id, [class*="watermark"]').forEach(el => el.remove());
  });
}
