#!/usr/bin/env node
/**
 * _node_bridge.js — Python ↔ Chrome CDP 通信桥
 *
 * 协议：JSON-Lines（每行一个 JSON）
 *   stdin  ← Python 发来的命令：{ id, cmd, params }
 *   stdout → 回复给 Python：{ id, result } 或 { id, error }
 *   stdout → CDP 事件推送：{ event, params }
 *
 * 支持的 cmd：
 *   connect         连接浏览器，定位目标 tab（支持 launchNew 启动独立实例）
 *   launchChrome    启动独立 Chrome 实例，返回 CDP URL
 *   disconnect      断开（不关闭浏览器，独立实例会终止）
 *   enableNetwork   启用 Network 域 + 开始事件转发
 *   enableRuntime   启用 Runtime 域
 *   cdp             透传任意 CDP 命令
 *   evaluate        在页面执行 JS（支持 expression/clickText/fillSelector）
 *   selectOption    通用下拉选择（ant-select/tbd-select），按 labelText + optionText 定位
 *   uncheckByLabel  取消勾选 checkbox（按 label 文字或 firstChecked=true）
 *   clickText       按文字点击任意可见元素
 *   setFixedViewport / maximizeWindow  固定窗口 1458×784 + 同步 viewport
 *   dismissModals   关闭常见遮挡弹窗
 *   screenshot      截图（已清水印），返回 base64 JPEG（medium 质量）
 *   getResponseBody 获取响应体
 */

'use strict';

const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');

// ── 运行环境检测 ──────────────────────────────────────────────────────────────
// 三种运行环境：cloudcli / sandbox / local
// 可通过 WEB_AUTO_RUNTIME 环境变量强制指定，否则自动探测

const RUNTIME_PATHS = {
  cloudcli: {
    puppeteer: path.join(os.homedir(), '.aone-cloud-cli/plugins/browser/node_modules/puppeteer-core'),
    portFile: path.join(os.homedir(), '.aone-cloud-cli/browser-data/DevToolsActivePort'),
    defaultPort: null, // 必须从 portFile 读取，无固定端口
  },
  sandbox: {
    puppeteer: '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core',
    portFile: null,
    defaultPort: 9222,
  },
  local: {
    puppeteer: path.join(__dirname, '..', 'node_modules', 'puppeteer-core'),
    portFile: null,
    defaultPort: 9222,
  },
  agentbay: {
    puppeteer: null,  // 由 WEB_AUTO_PUPPETEER_PATH 或 fallback 解析
    portFile: null,
    defaultPort: null,
    wsEndpoint: process.env.WEB_AUTO_CDP_WS_URL || null,  // WebSocket 端点
  },
};

function detectRuntime() {
  const explicit = process.env.WEB_AUTO_RUNTIME;
  if (explicit && RUNTIME_PATHS[explicit]) return explicit;

  // AgentBay: WebSocket CDP 端点存在
  if (process.env.WEB_AUTO_CDP_WS_URL) return 'agentbay';

  // CloudCLI: portFile 存在 + puppeteer 可用
  try {
    if (fs.existsSync(RUNTIME_PATHS.cloudcli.portFile)) {
      require.resolve(RUNTIME_PATHS.cloudcli.puppeteer);
      return 'cloudcli';
    }
  } catch (_) {}

  // Sandbox: OpenClaw 内置 puppeteer 存在
  try {
    require.resolve(RUNTIME_PATHS.sandbox.puppeteer);
    return 'sandbox';
  } catch (_) {}

  return 'local';
}

const RUNTIME = detectRuntime();

/**
 * puppeteer-core 路径解析（按当前运行环境选择）
 * 可通过 WEB_AUTO_PUPPETEER_PATH 环境变量强制覆盖
 */
function resolvePuppeteer() {
  const envPath = process.env.WEB_AUTO_PUPPETEER_PATH;
  if (envPath && envPath !== 'auto') {
    try { return require(envPath); } catch (_) {}
  }

  // 按当前 runtime 优先，其余作为 fallback
  const primary = RUNTIME_PATHS[RUNTIME].puppeteer;
  const fallbacks = [
    path.join(__dirname, '..', 'node_modules', 'puppeteer-core'),
    RUNTIME_PATHS.sandbox.puppeteer,
    RUNTIME_PATHS.cloudcli.puppeteer,
    'puppeteer-core',
  ].filter(p => p !== primary);

  const candidates = [primary, ...fallbacks];
  for (const p of candidates) {
    try { require.resolve(p); return require(p); } catch (_) {}
  }
  throw new Error(
    `找不到 puppeteer-core（当前环境: ${RUNTIME}）。\n` +
    '请在 web-automation/ 目录下运行: npm install\n' +
    '或设置环境变量: WEB_AUTO_PUPPETEER_PATH=<puppeteer-core 路径>'
  );
}

const puppeteer = resolvePuppeteer();

const SHARED_CDP = require(path.join(__dirname, 'shared_cdp'));
const {
  setFixedViewport,
  dismissKnownModals,
  captureScreenshotBase64,
  VIEWPORT_WIDTH,
  VIEWPORT_HEIGHT,
} = SHARED_CDP;

/**
 * CDP 地址解析（按当前运行环境选择策略）
 * - cloudcli: 必须从 DevToolsActivePort 读取动态端口
 * - sandbox:  固定 9222
 * - local:    优先 DevToolsActivePort，回退 9222
 * 可通过 WEB_AUTO_CDP_URL 环境变量强制覆盖
 */
function resolveCdpUrl() {
  if (process.env.WEB_AUTO_CDP_URL) return process.env.WEB_AUTO_CDP_URL;

  // agentbay: WebSocket 端点由 connect 命令直接处理，不走此函数
  if (RUNTIME === 'agentbay') {
    return process.env.WEB_AUTO_CDP_WS_URL || '';
  }

  const config = RUNTIME_PATHS[RUNTIME];

  // sandbox 环境固定端口，无需读文件
  if (RUNTIME === 'sandbox') {
    return `http://127.0.0.1:${config.defaultPort}`;
  }

  // cloudcli / local: 尝试从 portFile 读取动态端口
  const portFiles = [
    config.portFile,
    path.join(os.homedir(), '.config/chrome-debug/DevToolsActivePort'),
    '/tmp/chrome-debug/DevToolsActivePort',
  ].filter(Boolean);

  for (const f of portFiles) {
    try {
      const port = fs.readFileSync(f, 'utf8').split('\n')[0].trim();
      if (port && /^\d+$/.test(port)) return `http://127.0.0.1:${port}`;
    } catch (_) {}
  }

  if (RUNTIME === 'cloudcli') {
    throw new Error(
      'CloudCLI 环境下未找到 DevToolsActivePort 文件，浏览器可能未启动。\n' +
      '请确认 CloudCLI 浏览器插件已运行。'
    );
  }
  return 'http://127.0.0.1:9222';
}

// ── 全局状态 ──
let browser = null;
let page = null;
let cdpClient = null;  // CDP session
let launchedChrome = null;  // 由 launchChrome 启动的 Chrome 子进程
const responseBodyCache = new Map();  // requestId -> body string

// ── stdin 读取（JSON-Lines）──
const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', async (line) => {
  line = line.trim();
  if (!line) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (e) {
    return;
  }

  const { id, cmd, params } = msg;

  try {
    const result = await dispatch(cmd, params || {});
    send({ id, result: result ?? {} });
  } catch (e) {
    send({ id, error: e.message });
  }
});

rl.on('close', () => {
  cleanup();
  process.exit(0);
});

process.on('SIGTERM', () => { cleanup(); process.exit(0); });
process.on('SIGINT',  () => { cleanup(); process.exit(0); });

// ── 端口工具 ──

/**
 * 检查端口是否真正空闲（通过尝试 bind 验证）。
 * 避免 Chrome 静默跳端口导致实际端口与预期不符。
 */
function isPortFree(port, host = '127.0.0.1') {
  const net = require('net');
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

/**
 * 从 startPort 开始向上查找第一个空闲端口。
 * 最多尝试 maxAttempts 个端口。
 */
async function findAvailablePort(startPort, maxAttempts = 20) {
  for (let i = 0; i < maxAttempts; i++) {
    const candidate = startPort + i;
    if (await isPortFree(candidate)) return candidate;
  }
  throw new Error(`从端口 ${startPort} 开始连续 ${maxAttempts} 个端口均被占用`);
}

// ── 命令分发 ──
async function dispatch(cmd, params) {
  switch (cmd) {

    case 'launchChrome': {
      // 启动独立的 Chrome 实例，返回 CDP URL
      let port = params.port || 0;  // 0 = 让 Chrome 自动分配

      // 如果指定了端口，验证其空闲；被占用则自动寻找下一个空闲端口
      if (port > 0) {
        const requestedPort = port;
        port = await findAvailablePort(requestedPort);
        if (port !== requestedPort) {
          console.error(
            `[launchChrome] 端口 ${requestedPort} 已被占用，自动切换到空闲端口 ${port}`
          );
        }
      }

      const userDataDir = params.userDataDir || fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-iso-'));
      const chromeArgs = [
        `--remote-debugging-port=${port}`,
        `--user-data-dir=${userDataDir}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-timer-throttling',
        '--disable-renderer-backgrounding',
        '--disable-features=WebAuthenticationVirtualAuthenticator',
      ];
      if (params.headless) {
        chromeArgs.push('--headless=new');
      }
      if (params.windowSize) {
        chromeArgs.push(`--window-size=${params.windowSize}`);
      } else {
        chromeArgs.push('--window-size=1458,900');
      }
      if (params.extraArgs) {
        chromeArgs.push(...params.extraArgs);
      }

      // 探测 Chrome 可执行文件路径
      const chromeBin = params.chromeBin
        || process.env.WEB_AUTO_CHROME_BIN
        || (process.platform === 'darwin'
          ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
          : process.platform === 'win32'
            ? path.join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe')
            : 'google-chrome');

      const { spawn } = require('child_process');
      const chromeProc = spawn(chromeBin, chromeArgs, {
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      // 等待 Chrome 启动并获取实际端口
      const actualPort = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Chrome 启动超时（10s）')), 10000);
        let output = '';
        const onData = (data) => {
          output += data.toString();
          // Chrome 输出 DevTools listening on ws://127.0.0.1:PORT/devtools/browser/...
          const m = output.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/);
          if (m) {
            clearTimeout(timeout);
            chromeProc.stderr.removeListener('data', onData);
            chromeProc.stdout.removeListener('data', onData);
            resolve(parseInt(m[1], 10));
          }
        };
        chromeProc.stderr.on('data', onData);
        chromeProc.stdout.on('data', onData);
      });

      // 端口漂移检测：如果实际端口与预期不符，发出警告
      if (port > 0 && actualPort !== port) {
        console.error(
          `[launchChrome] 警告: 预期端口 ${port}，Chrome 实际使用了 ${actualPort}（端口漂移）`
        );
      }

      launchedChrome = chromeProc;
      const cdpUrl = `http://127.0.0.1:${actualPort}`;
      return { cdpUrl, port: actualPort, requestedPort: params.port || 0, pid: chromeProc.pid, userDataDir };
    }

    case 'connect': {
      // 支持 params.launchNew: 先启动独立 Chrome 再连接
      // 支持 params.wsEndpoint: 通过 WebSocket 连接云端浏览器
      let cdpUrl;
      const wsUrl = params.wsEndpoint || process.env.WEB_AUTO_CDP_WS_URL;

      if (wsUrl) {
        // 云端沙箱：WebSocket CDP 端点（wss:// 或 ws://）
        browser = await puppeteer.connect({
          browserWSEndpoint: wsUrl,
          defaultViewport: null,
        });
        cdpUrl = wsUrl;
      } else if (params.launchNew) {
        const launchResult = await dispatch('launchChrome', params.launchOptions || {});
        cdpUrl = launchResult.cdpUrl;
        browser = await puppeteer.connect({
          browserURL: cdpUrl,
          defaultViewport: null,
        });
      } else {
        cdpUrl = params.cdpUrl || resolveCdpUrl();
        browser = await puppeteer.connect({
          browserURL: cdpUrl,
          defaultViewport: null,
        });
      }

      const pages = await browser.pages();

      if (params.urlPattern) {
        page = pages.find(p => p.url().includes(params.urlPattern));
      }
      if (!page && params.url) {
        page = await browser.newPage();
        await page.goto(params.url, { waitUntil: 'networkidle2', timeout: 30000 });
      }
      if (!page) {
        page = pages[0];
      }

      cdpClient = await page.target().createCDPSession();
      return {
        url: page.url(),
        tabCount: pages.length,
        runtime: RUNTIME,
        cdpUrl,
        wsEndpoint: !!wsUrl,
        isolated: !!launchedChrome,
        pid: launchedChrome ? launchedChrome.pid : null,
      };
    }

    case 'disconnect': {
      cleanup();
      return {};
    }

    case 'enableNetwork': {
      await cdpClient.send('Network.enable');
      // 禁用缓存：避免 transferSize=0 的 disk cache 命中导致 requestWillBeSent 不触发
      await cdpClient.send('Network.setCacheDisabled', { cacheDisabled: true });

      // 将 CDP 网络事件转发给 Python
      const NETWORK_EVENTS = [
        'Network.requestWillBeSent',
        'Network.responseReceived',
        'Network.loadingFinished',
        'Network.loadingFailed',
        'Network.webSocketCreated',
        'Network.webSocketFrameReceived',
        'Network.webSocketFrameSent',
      ];

      for (const evt of NETWORK_EVENTS) {
        cdpClient.on(evt, async (evtParams) => {
          // 可选 URL 过滤
          if (params.urlFilter) {
            const url = evtParams?.request?.url || evtParams?.response?.url || evtParams?.url || '';
            if (url && !url.includes(params.urlFilter)) return;
          }
          // loadingFinished 时提前获取并缓存 body
          if (evt === 'Network.loadingFinished') {
            const rid = evtParams.requestId;
            try {
              const { body, base64Encoded } = await cdpClient.send('Network.getResponseBody', { requestId: rid });
              const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
              responseBodyCache.set(rid, text);
              evtParams._cachedBody = text;
            } catch(e) {
              evtParams._cachedBody = null;
            }
          }
          send({ event: evt, params: evtParams });
        });
      }
      return {};
    }

    case 'enableRuntime': {
      await cdpClient.send('Runtime.enable');
      cdpClient.on('Runtime.consoleAPICalled', (evtParams) => {
        send({ event: 'Runtime.consoleAPICalled', params: evtParams });
      });
      return {};
    }

    case 'cdp': {
      const result = await cdpClient.send(params.method, params.params || {});
      return result;
    }

    case 'evaluate': {
      // 支持 expression （任意 JS 表达式）和 clickText （按文字点击）
      if (params.clickText !== undefined) {
        // 专用：按文字点击元素
        const clicked = await page.evaluate((text) => {
          const el = Array.from(document.querySelectorAll(
            'button, a, [role="button"], [class*="btn"]'
          )).find(e => e.innerText && e.innerText.trim() === text && e.offsetParent !== null);
          if (el) { el.click(); return true; }
          return false;
        }, params.clickText);
        return { value: clicked };
      } else if (params.fillSelector !== undefined) {
        // 专用：填写表单（React native setter）
        const filled = await page.evaluate((selector, value) => {
          const el = document.querySelector(selector);
          if (!el) return false;
          const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
          setter.call(el, value);
          el.dispatchEvent(new Event('focus', { bubbles: true }));
          el.dispatchEvent(new InputEvent('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          el.dispatchEvent(new Event('blur', { bubbles: true }));
          return true;
        }, params.fillSelector, params.fillValue);
        return { value: filled };
      } else {
        // 通用模式：执行任意 JS 表达式
        const fn = new Function('return (' + params.expression + ')');
        const result = await page.evaluate(fn);
        return { value: result };
      }
    }

    case 'selectOption': {
      /**
       * 通用下拉选择：支持 ant-select / tbd-select / native <select>
       * params:
       *   labelText       - 表单 label 文字（用于定位字段），如 "买手"
       *   placeholderText - 当没有独立 label 时，使用 placeholder 文字定位（如 "类目"）
       *   optionText      - 选项文字（支持模糊包含匹配），如 "奕心"
       *   labelClass      - label 的 CSS class（默认 tbd-formily-item-label）
       *   multiple        - 是否多选（默认 false）
       */
      const { labelText, placeholderText, optionText, labelClass = 'tbd-formily-item-label', multiple = false } = params;

      // 1. 清水印
      await page.evaluate(() => {
        document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
      });

      // 2. 定位 label → formily-item → select-selector 并获取坐标
      const selectorCoords = await page.evaluate((lText, lClass) => {
        // 找 label
        const labels = [...document.querySelectorAll('.' + lClass + ', .ant-form-item-label label')];
        const label = labels.find(l => l.innerText?.trim() === lText);
        if (!label) return { err: 'label not found: ' + lText };

        // 向上找 formily-item，再找 control
        let item = label.parentElement;
        for (let i = 0; i < 6; i++) {
          const cls = item.className?.toString() || '';
          if (cls.includes('formily-item') || cls.includes('form-item') || cls.includes('ant-form-item')) break;
          if (!item.parentElement) break;
          item = item.parentElement;
        }

        // 找 selector（tbd-select-selector 或 ant-select-selector）
        const sel = item.querySelector('.tbd-select-selector, .ant-select-selector, select');
        if (!sel) return { err: 'selector not found in item', itemClass: item.className?.toString()?.slice(0,60) };

        // 优先不滚动（sticky header 里尔3已可见），若坐标为空再尝试 nearest
        let r = sel.getBoundingClientRect();
        if (!r.width) {
          sel.scrollIntoView({ block: 'nearest', behavior: 'instant' });
          r = sel.getBoundingClientRect();
        }
        if (!r.width) return { err: 'selector has zero width (off-screen?)' };
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height };
      }, labelText, labelClass);

      if (selectorCoords.err) throw new Error('selectOption: ' + selectorCoords.err);

      // 3. 点击打开下拉
      await page.mouse.click(selectorCoords.x, selectorCoords.y);
      await sleep(600);  // 等待下拉渲染

      // 4. 在渲染出的选项里找匹配项（用 TreeWalker 找文本节点）
      const optCoords = await page.evaluate((oText) => {
        // 优先找专用 option 类
        const optEls = [...document.querySelectorAll(
          '.tbd-select-item-option-content, .ant-select-item-option-content, .ant-select-item-option, option'
        )].filter(el => el.innerText?.includes(oText));

        if (optEls.length) {
          const el = optEls[0];
          el.scrollIntoView({ block: 'nearest', behavior: 'instant' });
          const r = el.getBoundingClientRect();
          if (r.width) return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: el.innerText.trim() };
        }

        // 降级：TreeWalker 找文本节点
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
          acceptNode: n => n.textContent.includes(oText) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
        });
        let node;
        while ((node = walker.nextNode())) {
          let el = node.parentElement;
          while (el && el !== document.body) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.width < 600) {
              return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: el.innerText.trim().slice(0, 30), fallback: true };
            }
            el = el.parentElement;
          }
        }
        return null;
      }, optionText);

      if (!optCoords) throw new Error('selectOption: option not found: ' + optionText);

      // 5. 点击选项：优先 mouse.click（保持下拉打开状态）
      await page.mouse.click(optCoords.x, optCoords.y);
      await sleep(300);

      // 6. 验证选中值
      const selectedValue = await page.evaluate((lText, lClass) => {
        const labels = [...document.querySelectorAll('.' + lClass + ', .ant-form-item-label label')];
        const label = labels.find(l => l.innerText?.trim() === lText);
        let item = label?.parentElement;
        for (let i = 0; i < 6; i++) {
          const cls = item?.className?.toString() || '';
          if (cls.includes('formily-item') || cls.includes('form-item') || cls.includes('ant-form-item')) break;
          item = item?.parentElement;
        }
        const sel = item?.querySelector('.tbd-select-selector, .ant-select-selector');
        return sel?.innerText?.trim() || null;
      }, labelText, labelClass);

      return { selected: selectedValue, optionText: optCoords.text || optionText };
    }

    case 'uncheckByLabel': {
      /**
       * 取消勾选 checkbox（按 label 文字或直接取消第一个非 disabled 的勾选项）
       * params:
       *   labelText  - 包含此文字的 label（可选）
       *   firstChecked - true 时直接取消第一个 checked 的 checkbox
       */
      const unchecked = await page.evaluate((lText, firstChecked) => {
        let cb;
        if (firstChecked) {
          cb = [...document.querySelectorAll('input[type="checkbox"]')].find(i => i.checked && !i.disabled);
        } else {
          cb = [...document.querySelectorAll('input[type="checkbox"]')].find(i => {
            const wrapper = i.closest('label, .tbd-checkbox-wrapper, .ant-checkbox-wrapper') || i.parentElement;
            return wrapper?.innerText?.includes(lText) && i.checked;
          });
        }
        if (!cb) return false;
        cb.click();
        cb.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }, params.labelText, params.firstChecked);
      return { unchecked };
    }

    case 'clickText': {
      /**
       * 按文字点击任意可见元素（比 evaluate.clickText 更健壮，支持自定义 selector 范围）
       * params:
       *   text     - 要匹配的文字（精确 trim 匹配）
       *   selector - 可选，限制搜索范围（默认 button,a,[role="button"],[class*="btn"],span）
       */
      const { text, selector = 'button, a, [role="button"], [class*="btn"], span' } = params;
      const clicked = await page.evaluate((txt, sel) => {
        const el = [...document.querySelectorAll(sel)].find(
          e => e.innerText?.trim() === txt && e.offsetParent !== null
        );
        if (el) { el.click(); return true; }
        return false;
      }, text, selector);
      return { clicked };
    }

    case 'setFixedViewport':
    case 'maximizeWindow': {
      const bounds = await setFixedViewport(page, cdpClient);
      return bounds;
    }

    case 'disableWebAuthn': {
      // 注入脚本阻止页面调用 navigator.credentials.get()，
      // 防止 macOS 弹出“没有可用的通行密钥”原生弹窗
      const expression = `
        (function() {
          try {
            const originalGet = navigator.credentials && navigator.credentials.get;
            if (navigator.credentials && navigator.credentials.get) {
              navigator.credentials.get = function() {
                return Promise.reject(new DOMException('WebAuthn disabled', 'NotAllowedError'));
              };
            }
          } catch(e) {}
        })();
      `;
      await cdpClient.send('Page.addScriptToEvaluateOnNewDocument', { source: expression });
      // 对当前已加载的页面也立即生效
      try { await page.evaluate(expression); } catch (_) {}
      return { disabled: true };
    }

    case 'dismissModals': {
      const result = await dismissKnownModals(page, {
        maxRounds: params.maxRounds ?? 5,
      });
      return result;
    }

    case 'screenshot': {
      await page.evaluate(() => {
        document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
      });
      await sleep(200);
      const data = await captureScreenshotBase64(cdpClient);
      return { data, format: 'jpeg', width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT };
    }

    case 'checkLogin': {
      /**
       * 检测当前页面是否处于登录态。
       * 策略（优先级递减）：
       *   1. 当前 URL 是否是已知登录页（login.alibaba-inc.com / login.taobao.com）
       *   2. 查 knowledge/index.json 中注册的 auth.type（根据目标页 host 匹配）
       *   3. 根据页面内容猜测（垆选）
       * 返回：{ isLoginPage, loginType: 'buc'|'taobao'|'none', currentUrl, source: 'redirect'|'knowledge'|'heuristic' }
       */
      const url = page.url();

      // 1. 已知登录页判断（URL 直接是登录页）
      const isBucLoginUrl    = url.includes('login.alibaba-inc.com');
      const isTaobaoLoginUrl = url.includes('login.taobao.com');
      if (isBucLoginUrl || isTaobaoLoginUrl) {
        return {
          isLoginPage: true,
          loginType: isBucLoginUrl ? 'buc' : 'taobao',
          currentUrl: url,
          source: 'redirect',
        };
      }

      // 2. 查 knowledge/index.json 获取目标页的已知 auth.type
      //    注意：这里判断的是目标页本身（非登录页），用于在 connect() 后判断是否属于需要登录的系统
      try {
        const fs = require('fs');
        const indexPath = require('path').join(__dirname, '../../knowledge/index.json');
        const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
        const matched = index.entries.find(e => url.includes(e.host));
        if (matched && matched.auth) {
          // 命中 knowledge，但当前页面并非登录页，返回登录类型供上层参考
          return {
            isLoginPage: false,  // 当前页本身不是登录页
            loginType: matched.auth.type,
            currentUrl: url,
            source: 'knowledge',
            knowledgeId: matched.id,
          };
        }
      } catch (_) {}

      // 3. 垆选猜测（未命中 knowledge 时）
      const pageText = await page.evaluate(() => document.body?.innerText || '').catch(() => '');
      const hasBucForm    = pageText.includes('工号') || pageText.includes('Employee ID');
      const hasTaobaoForm = !!(await page.evaluate(() =>
        document.querySelector('#fm-login-id') || document.querySelector('.login-form')
      ).catch(() => null));

      return {
        isLoginPage: hasBucForm || hasTaobaoForm,
        loginType: hasBucForm ? 'buc' : hasTaobaoForm ? 'taobao' : 'none',
        currentUrl: url,
        source: 'heuristic',
      };
    }

    case 'taobaoLogin': {
      /**
       * 使用账号密码登录淘宝。仅适用于淘宝登录页（#fm-login-id 存在）。
       * BUC 登录禁止调用此命令。
       * params: { username, password }
       */
      const { username, password } = params;
      if (!username || !password) throw new Error('taobaoLogin: username 和 password 不能为空');

      // 等待登录表单出现
      await page.waitForSelector('#fm-login-id', { timeout: 10000 }).catch(() => {
        throw new Error('taobaoLogin: 未找到淘宝登录表单 (#fm-login-id)');
      });

      // 填写账号密码（React native setter）
      await page.evaluate((u, p) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        const uEl = document.querySelector('#fm-login-id');
        const pEl = document.querySelector('#fm-login-password');
        if (!uEl || !pEl) throw new Error('找不到账号或密码输入框');
        setter.call(uEl, u);
        uEl.dispatchEvent(new InputEvent('input', { bubbles: true }));
        uEl.dispatchEvent(new Event('change', { bubbles: true }));
        setter.call(pEl, p);
        pEl.dispatchEvent(new InputEvent('input', { bubbles: true }));
        pEl.dispatchEvent(new Event('change', { bubbles: true }));
      }, username, password);
      await sleep(500);

      // 点登录按钮
      await page.evaluate(() => {
        const btn = document.querySelector('button[type="submit"]') ||
                    document.querySelector('.login-submit') ||
                    document.querySelector('[class*="login"][class*="btn"]');
        if (!btn) throw new Error('找不到登录提交按钮');
        btn.click();
      });

      // 等待跳转（最多 30s）
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
      const finalUrl = page.url();
      const stillOnLogin = finalUrl.includes('login.taobao.com') || finalUrl.includes('login.alibaba-inc.com');
      if (stillOnLogin) throw new Error('taobaoLogin: 登录后仍在登录页，可能账号密码错误或需要验证码');

      return { loggedIn: true, finalUrl };
    }

    case 'navigate': {
      /**
       * 导航到指定 URL，并转发 Page 加载事件给 Python。
       * params:
       *   url  - 目标 URL
       *
       * 执行后 Python 侧可通过监听 Page.loadEventFired / Page.domContentEventFired 判断加载完成。
       */
      const { url } = params;

      // 确保 Page 域已 enable，并注册一次性事件转发（避免重复注册）
      if (!dispatch._pageEventsEnabled) {
        await cdpClient.send('Page.enable');
        for (const evt of ['Page.loadEventFired', 'Page.domContentEventFired', 'Page.frameNavigated']) {
          cdpClient.on(evt, (evtParams) => {
            send({ event: evt, params: evtParams });
          });
        }
        dispatch._pageEventsEnabled = true;
      }

      await cdpClient.send('Page.navigate', { url, transitionType: 'typed' });
      return { navigating: true, url };
    }

    case 'getResponseBody': {
      const { body, base64Encoded } = await cdpClient.send(
        'Network.getResponseBody',
        { requestId: params.requestId }
      );
      let text = body;
      if (base64Encoded) {
        text = Buffer.from(body, 'base64').toString('utf8');
      }
      return { body: text };
    }

    // ── CDP 底层能力（解决自动化环境限制）────────────────────────────────────

    case 'cdpDrag': {
      /**
       * CDP 原生级精确拖拽，解决裁切 trim 等需要拖拽 handle 的场景。
       * params:
       *   fromX, fromY  - 拖拽起点坐标
       *   toX, toY      - 拖拽终点坐标
       *   steps         - 插值步数（默认 10，越多越平滑）
       *   button        - 鼠标按键（默认 left）
       */
      const { fromX, fromY, toX, toY, steps = 10, button = 'left' } = params;

      // 清水印
      await page.evaluate(() => {
        document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
      });

      await cdpClient.send('Input.dispatchMouseEvent', {
        type: 'mousePressed', x: fromX, y: fromY, button, clickCount: 1,
      });

      for (let i = 1; i <= steps; i++) {
        const x = fromX + (toX - fromX) * i / steps;
        const y = fromY + (toY - fromY) * i / steps;
        await cdpClient.send('Input.dispatchMouseEvent', {
          type: 'mouseMoved', x, y, button,
        });
        await sleep(15);
      }

      await cdpClient.send('Input.dispatchMouseEvent', {
        type: 'mouseReleased', x: toX, y: toY, button,
      });

      return { dragged: true, fromX, fromY, toX, toY, steps };
    }

    case 'cdpKeyEvent': {
      /**
       * CDP 原生级键盘事件，解决 Space 播放、快捷键冲突、焦点状态等场景。
       * 绕过 React dispatchEvent 和浏览器快捷键拦截。
       * params:
       *   key          - 按键名（'Space' / 'Home' / 'z' 等）
       *   code         - 按键码（'Space' / 'Home' / 'KeyZ' 等）
       *   keyCode      - windowsVirtualKeyCode（Space=32, Home=36, Z=90 等）
       *   modifiers    - 修饰键位掩码：Alt=1, Ctrl=2, Meta=4, Shift=8
       *   type         - 事件类型（默认依次发 keyDown + keyUp）
       *   text         - 可选，keyDown 时输入的文本字符
       *   preventDefault - 可选，是否先注入 preventDefault 拦截器
       */
      const {
        key, code, keyCode,
        modifiers = 0,
        type = 'both',
        text = '',
        preventDefault = false,
      } = params;

      // 先注入 preventDefault 拦截器（解决快捷键被浏览器吞掉的问题）
      if (preventDefault) {
        await page.evaluate((k, mod) => {
          const handler = (e) => {
            if (e.key === k &&
                e.ctrlKey === !!(mod & 2) &&
                e.shiftKey === !!(mod & 8) &&
                e.altKey === !!(mod & 1)) {
              e.preventDefault();
              e.stopPropagation();
            }
          };
          window.addEventListener('keydown', handler, true);
          setTimeout(() => window.removeEventListener('keydown', handler, true), 2000);
        }, key, modifiers);
      }

      const baseParams = { key, code, windowsVirtualKeyCode: keyCode, modifiers };

      if (type === 'keyDown' || type === 'both') {
        await cdpClient.send('Input.dispatchKeyEvent', {
          ...baseParams, type: 'keyDown',
          ...(text ? { text } : {}),
        });
      }
      if (type === 'both') await sleep(30);
      if (type === 'keyUp' || type === 'both') {
        await cdpClient.send('Input.dispatchKeyEvent', {
          ...baseParams, type: 'keyUp',
        });
      }

      return { sent: true, key, code, modifiers, type };
    }

    case 'cdpMouseWheel': {
      /**
       * CDP 原生级鼠标滚轮，支持带修饰键（Ctrl+滚轮 = 缩放）。
       * params:
       *   x, y         - 鼠标位置
       *   deltaX       - 水平滚动量（默认 0）
       *   deltaY       - 垂直滚动量（负=向上/放大，正=向下/缩小）
       *   modifiers    - 修饰键位掩码：Ctrl=2
       */
      const { x = 500, y = 400, deltaX = 0, deltaY = -120, modifiers = 0 } = params;

      await cdpClient.send('Input.dispatchMouseEvent', {
        type: 'mouseWheel', x, y, deltaX, deltaY, modifiers,
      });

      return { scrolled: true, x, y, deltaX, deltaY, modifiers };
    }

    case 'emulateFullscreen': {
      /**
       * 通过 CDP Emulation 域模拟全屏，绕过 requestFullscreen 需要用户手势的限制。
       * params:
       *   width, height - 全屏尺寸（默认从 window.screen 获取）
       */
      let { width, height } = params;
      if (!width || !height) {
        const screenInfo = await page.evaluate(() => ({
          w: window.screen.width, h: window.screen.height
        }));
        width = width || screenInfo.w;
        height = height || screenInfo.h;
      }

      await cdpClient.send('Emulation.setDeviceMetricsOverride', {
        width, height, deviceScaleFactor: 1, mobile: false,
        screenOrientation: { type: 'landscapePrimary', angle: 0 },
      });

      // 覆盖 requestFullscreen API，避免后续调用报错
      await page.evaluate(() => {
        Element.prototype.requestFullscreen = function() {
          document.dispatchEvent(new Event('fullscreenchange'));
          return Promise.resolve();
        };
        Object.defineProperty(document, 'fullscreenElement', {
          get: () => document.documentElement,
          configurable: true,
        });
      });

      return { fullscreen: true, width, height };
    }

    case 'startScreencast': {
      /**
       * 启动 CDP 实时截屏流，用于播放过程观察、过渡动画监控。
       * 帧数据通过 screencastFrame 事件推送给 Python。
       * params:
       *   format  - jpeg（默认）或 png
       *   quality - JPEG 质量（默认 60）
       */
      const { format = 'jpeg', quality = 60 } = params;

      await cdpClient.send('Page.startScreencast', {
        format, quality, maxWidth: VIEWPORT_WIDTH, maxHeight: VIEWPORT_HEIGHT,
      });

      // 自动 ack 每一帧，并转发给 Python
      cdpClient.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
        await cdpClient.send('Page.screencastFrameAck', { sessionId });
        send({ event: 'Page.screencastFrame', params: { data, metadata } });
      });

      return { screencastStarted: true, format, quality };
    }

    case 'stopScreencast': {
      await cdpClient.send('Page.stopScreencast');
      return { screencastStopped: true };
    }

    case 'setFocus': {
      /**
       * 通过 CDP DOM.focus 强制设置焦点，解决编辑器容器需要焦点才能响应快捷键的问题。
       * params:
       *   selector - CSS 选择器（定位需要获得焦点的元素）
       */
      const { selector } = params;

      // 先通过 evaluate 找到 nodeId
      const { root } = await cdpClient.send('DOM.getDocument');
      const { nodeId } = await cdpClient.send('DOM.querySelector', {
        nodeId: root.nodeId, selector,
      });

      if (!nodeId) throw new Error(`setFocus: 找不到元素: ${selector}`);

      await cdpClient.send('DOM.focus', { nodeId });

      // 补充：确保 tabIndex 允许聚焦
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el && el.tabIndex < 0) el.tabIndex = -1;
      }, selector);

      return { focused: true, selector };
    }

    case 'mockNetwork': {
      /**
       * 网络异常模拟 + API Mock，通过 CDP Network + Fetch 域实现。
       * params:
       *   mode         - 'offline' | 'throttle' | 'mock' | 'reset'
       *   offline      - 是否断网
       *   latency      - 延迟 ms
       *   downloadKbps - 下载限速 KB/s
       *   uploadKbps   - 上传限速 KB/s
       *   urlPattern   - mock 匹配的 URL 关键词
       *   mockStatus   - mock 响应状态码
       *   mockBody     - mock 响应体（字符串或对象）
       */
      const {
        mode = 'reset',
        offline = false,
        latency = 0,
        downloadKbps = -1,
        uploadKbps = -1,
        urlPattern = '',
        mockStatus = 500,
        mockBody = '{"error":"mocked"}',
      } = params;

      if (mode === 'reset') {
        // 恢复网络
        await cdpClient.send('Network.emulateNetworkConditions', {
          offline: false, latency: 0,
          downloadThroughput: -1, uploadThroughput: -1,
        });
        try { await cdpClient.send('Fetch.disable'); } catch (_) {}
        return { mode: 'reset' };
      }

      if (mode === 'offline' || mode === 'throttle') {
        await cdpClient.send('Network.emulateNetworkConditions', {
          offline: mode === 'offline' ? true : offline,
          latency,
          downloadThroughput: downloadKbps >= 0 ? downloadKbps * 1024 / 8 : -1,
          uploadThroughput: uploadKbps >= 0 ? uploadKbps * 1024 / 8 : -1,
        });
        return { mode, offline, latency, downloadKbps, uploadKbps };
      }

      if (mode === 'mock') {
        if (!urlPattern) throw new Error('mockNetwork: mock 模式必须提供 urlPattern');

        await cdpClient.send('Fetch.enable', {
          patterns: [{ urlPattern: `*${urlPattern}*`, requestStage: 'Request' }],
        });

        const bodyStr = typeof mockBody === 'string' ? mockBody : JSON.stringify(mockBody);
        const bodyBase64 = Buffer.from(bodyStr).toString('base64');

        // 注册拦截处理器（注意：如果多次调用 mockNetwork，会累积处理器）
        const handlerKey = '_fetchMockHandler_' + urlPattern;
        if (dispatch[handlerKey]) {
          // 移除旧的处理器避免重复
          cdpClient.removeAllListeners
            ? cdpClient.removeAllListeners('Fetch.requestPaused')
            : null;
        }

        cdpClient.on('Fetch.requestPaused', async ({ requestId, request }) => {
          if (request.url.includes(urlPattern)) {
            await cdpClient.send('Fetch.fulfillRequest', {
              requestId,
              responseCode: mockStatus,
              responseHeaders: [
                { name: 'Content-Type', value: 'application/json' },
              ],
              body: bodyBase64,
            });
          } else {
            await cdpClient.send('Fetch.continueRequest', { requestId });
          }
        });
        dispatch[handlerKey] = true;

        return { mode: 'mock', urlPattern, mockStatus, mockBody: bodyStr.slice(0, 200) };
      }

      throw new Error(`mockNetwork: 未知 mode: ${mode}`);
    }

    case 'observeTransitions': {
      /**
       * 注入 MutationObserver 监控 DOM 过渡状态变化（面板关闭、loading、上传进度等）。
       * params:
       *   action    - 'start' | 'stop' | 'query'
       *   selector  - 可选，限定观察范围（默认 document.body）
       */
      const { action = 'start', selector } = params;

      if (action === 'start') {
        await page.evaluate((sel) => {
          window.__webAutoTransitionLog = [];
          const target = sel ? document.querySelector(sel) : document.body;
          if (!target) throw new Error('observeTransitions: target not found: ' + sel);

          window.__webAutoTransitionObserver = new MutationObserver((mutations) => {
            mutations.forEach(m => {
              window.__webAutoTransitionLog.push({
                type: m.type,
                attribute: m.attributeName,
                element: m.target.className?.toString?.()?.slice(0, 100) || m.target.tagName,
                oldValue: m.oldValue?.slice?.(0, 100),
                time: Date.now(),
              });
            });
          });

          window.__webAutoTransitionObserver.observe(target, {
            attributes: true, subtree: true, attributeOldValue: true,
            attributeFilter: ['class', 'style', 'hidden', 'aria-hidden'],
            childList: true,
          });
        }, selector);

        return { observing: true, selector: selector || 'body' };
      }

      if (action === 'stop') {
        await page.evaluate(() => {
          if (window.__webAutoTransitionObserver) {
            window.__webAutoTransitionObserver.disconnect();
          }
        });
        return { observing: false };
      }

      if (action === 'query') {
        const log = await page.evaluate(() => window.__webAutoTransitionLog || []);
        return { transitions: log, count: log.length };
      }

      throw new Error(`observeTransitions: 未知 action: ${action}`);
    }

    default:
      throw new Error(`未知命令: ${cmd}`);
  }
}

// ── 工具 ──

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function cleanup() {
  try { if (browser) browser.disconnect(); } catch (_) {}
  browser = null;
  page = null;
  cdpClient = null;
  // 如果是本进程启动的独立 Chrome，终止它
  if (launchedChrome) {
    try { launchedChrome.kill('SIGTERM'); } catch (_) {}
    launchedChrome = null;
  }
}
