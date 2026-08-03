# CDP 网络抓包

通过 CDP Network 域实现 HTTP/HTTPS 请求的捕获、分析、拦截和 Mock。

## 目录

1. [为什么用 CDP 而不是 Puppeteer 事件](#1-为什么用-cdp-而不是-puppeteer-事件)
2. [基础监听模板](#2-基础监听模板)
3. [获取响应 Body](#3-获取响应-body)
4. [请求过滤](#4-请求过滤)
5. [等待特定请求完成](#5-等待特定请求完成)
6. [请求拦截与-mock](#6-请求拦截与-mock)
7. [性能分析](#7-性能分析)
8. [HAR 导出](#8-har-导出)
9. [兼容性边界](#9-兼容性边界)
10. [注意事项](#10-注意事项)

---

## 1. 为什么用 CDP 而不是 Puppeteer 事件

| 特性 | Puppeteer 事件 | CDP Network 域 |
|------|:-----------:|:-----------:|
| request/response 关联 | ❌ 靠 URL 匹配，易错位 | ✅ `requestId` 天然关联 |
| 响应 body 多次读取 | ❌ `response.text()` 只能读一次 | ✅ `getResponseBody` 可重复调用 |
| 请求 body (postData) | ✅ | ✅ |
| 加载耗时 | ❌ | ✅ `timestamp` 精确计时 |
| 请求拦截/Mock | ❌ | ✅ `setRequestInterception` |
| 跨域 iframe 请求 | ❌ 主 frame 才触发 | ⚠️ 需单独 attach CDP session |
| WebSocket 帧 | ❌ | ⚠️ 专用 API，见第9节 |

**结论**：业务测试场景一律使用 CDP Network 域。

---

## 2. 基础监听模板

```javascript
// 移植到新机器后改为 require('puppeteer-core')（需先 npm install）
// 当前服务端路径（OpenClaw 内置）：
const puppeteer = require('/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core');

async function withNetworkCapture(page, callback, options = {}) {
  const {
    filter = () => true,  // 过滤函数，返回 true 则记录
    captureBody = true,   // 是否获取响应 body
  } = options;

  // 创建 CDP session（复用已有 client 或新建）
  const client = await page.target().createCDPSession();
  await client.send('Network.enable');

  const requests = new Map(); // requestId -> request data

  // ① 请求发出时记录
  client.on('Network.requestWillBeSent', (params) => {
    const { requestId, request, timestamp, type, redirectResponse } = params;
    if (!filter(request.url, request.method, type)) return;

    requests.set(requestId, {
      requestId,
      url: request.url,
      method: request.method,
      headers: request.headers,
      postData: request.postData || null,
      type,
      startTime: timestamp,
      // 重定向情况：原请求被重定向时，redirectResponse 里有上一跳的响应
      redirectFrom: redirectResponse?.url || null,
    });
  });

  // ② 响应头到达时记录状态码
  client.on('Network.responseReceived', (params) => {
    const { requestId, response } = params;
    const req = requests.get(requestId);
    if (!req) return;

    req.status = response.status;
    req.statusText = response.statusText;
    req.responseHeaders = response.headers;
    req.mimeType = response.mimeType;
    req.timing = response.timing;
  });

  // ③ 请求加载完成时计算耗时，可选获取 body
  client.on('Network.loadingFinished', async (params) => {
    const { requestId, timestamp, encodedDataLength } = params;
    const req = requests.get(requestId);
    if (!req) return;

    req.endTime = timestamp;
    req.duration = Math.round((timestamp - req.startTime) * 1000); // ms
    req.encodedDataLength = encodedDataLength;

    if (captureBody) {
      try {
        const { body, base64Encoded } = await client.send('Network.getResponseBody', { requestId });
        req.responseBody = base64Encoded
          ? Buffer.from(body, 'base64').toString('utf8')
          : body;
        // 尝试解析 JSON
        try { req.responseJSON = JSON.parse(req.responseBody); } catch(_) {}
      } catch (e) {
        req.responseBodyError = e.message;
      }
    }
  });

  // ④ 请求失败
  client.on('Network.loadingFailed', (params) => {
    const { requestId, errorText, canceled } = params;
    const req = requests.get(requestId);
    if (req) {
      req.error = errorText;
      req.canceled = canceled;
    }
  });

  // 执行业务操作
  await callback(page, client);

  // 返回捕获结果
  return requests;
}
```

### 使用示例

```javascript
const browser = await puppeteer.connect({ browserURL: 'http://127.0.0.1:9222' });
const page = (await browser.pages())[0];

const requests = await withNetworkCapture(
  page,
  async (page) => {
    // 这里放页面操作
    await page.click('#submit-btn');
    await new Promise(r => setTimeout(r, 3000));
  },
  {
    // 只捕获 API 请求，过滤静态资源
    filter: (url) => url.includes('/cobweb/api/'),
    captureBody: true,
  }
);

// 打印结果
for (const [id, req] of requests) {
  const path = new URL(req.url).pathname.split('/').pop();
  console.log(`[${req.status}] ${req.method} ${path} (${req.duration}ms)`);
  if (req.postData) console.log('  Body:', req.postData.substring(0, 200));
  if (req.responseJSON) console.log('  Resp:', JSON.stringify(req.responseJSON).substring(0, 200));
}

browser.disconnect();
```

---

## 3. 获取响应 Body

`getResponseBody` 有两个常见失败场景：

```javascript
async function safeGetResponseBody(client, requestId) {
  try {
    const { body, base64Encoded } = await client.send('Network.getResponseBody', { requestId });
    const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
    return { text, json: tryParse(text) };
  } catch (e) {
    // 失败原因：
    // 1. 请求尚未完成（在 loadingFinished 之前调用）
    // 2. 资源是图片/视频等二进制（通常不需要 body）
    // 3. requestId 已被浏览器回收（操作间隔太长）
    return { text: null, error: e.message };
  }
}

function tryParse(text) {
  try { return JSON.parse(text); } catch(_) { return null; }
}
```

> ⚠️ **必须在 `Network.loadingFinished` 之后调用**，否则必定报错。

---

## 4. 请求过滤

常用过滤模式：

```javascript
// 只看业务 API（排除埋点、静态资源）
const API_FILTER = (url) =>
  url.includes('/cobweb/api/') &&
  !url.includes('mmstat.com') &&
  !url.includes('alilog');

// 只看 POST 请求
const POST_FILTER = (url, method) => method === 'POST';

// 只看慢请求（需在 loadingFinished 后过滤）
const isSlow = (req) => req.duration > 1000;

// 过滤静态资源类型
const STATIC_TYPES = ['Image', 'Font', 'Stylesheet', 'Media'];
const DYNAMIC_FILTER = (url, method, type) => !STATIC_TYPES.includes(type);
```

---

## 5. 等待特定请求完成

```javascript
/**
 * 等待匹配 urlPattern 的请求完成，并返回响应信息（含 body）
 */
function waitForAPI(client, urlPattern, { timeout = 10000, captureBody = true } = {}) {
  return new Promise((resolve, reject) => {
    const pendingRequests = new Map();
    const timer = setTimeout(() => reject(new Error(`等待 ${urlPattern} 超时`)), timeout);

    client.on('Network.requestWillBeSent', (params) => {
      if (params.request.url.includes(urlPattern)) {
        pendingRequests.set(params.requestId, {
          url: params.request.url,
          method: params.request.method,
          postData: params.request.postData,
        });
      }
    });

    client.on('Network.loadingFinished', async (params) => {
      const req = pendingRequests.get(params.requestId);
      if (!req) return;

      if (captureBody) {
        const { text, json } = await safeGetResponseBody(client, params.requestId);
        req.responseBody = text;
        req.responseJSON = json;
      }

      clearTimeout(timer);
      resolve(req);
    });
  });
}

// 使用示例：等待调价接口完成
const [, result] = await Promise.all([
  page.click('#submit-btn'),
  waitForAPI(client, 'adjustPrice.startAdjust', { timeout: 8000 })
]);
console.log('调价接口返回:', result.responseJSON);
```

---

## 6. 请求拦截与 Mock

> ⚠️ `Network.setRequestInterception` 会拦截**所有**请求，放行时必须调用 `continueInterceptedRequest`，否则页面卡死。

### 屏蔽静态资源（加速测试）

```javascript
await client.send('Network.setRequestInterception', {
  patterns: [{ urlPattern: '*', resourceType: 'All' }]
});

const BLOCK_TYPES = new Set(['Image', 'Font', 'Stylesheet', 'Media']);

client.on('Network.requestIntercepted', async ({ interceptionId, resourceType }) => {
  if (BLOCK_TYPES.has(resourceType)) {
    await client.send('Network.abortInterceptedRequest', {
      interceptionId,
      errorCode: 'BlockedByClient'
    });
  } else {
    await client.send('Network.continueInterceptedRequest', { interceptionId });
  }
});
```

### Mock 特定接口返回

```javascript
await client.send('Network.setRequestInterception', {
  patterns: [{ urlPattern: '*/adjustPrice*' }]
});

client.on('Network.requestIntercepted', async ({ interceptionId, request }) => {
  if (request.url.includes('startAdjustdailySellPrice')) {
    // 返回 mock 数据
    const mockBody = JSON.stringify({ code: 'OK', data: { data: 9999 } });
    await client.send('Network.fulfillInterceptedRequest', {
      interceptionId,
      responseCode: 200,
      responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
      body: Buffer.from(mockBody).toString('base64')
    });
  } else {
    await client.send('Network.continueInterceptedRequest', { interceptionId });
  }
});
```

### 注入请求头（模拟不同身份）

```javascript
client.on('Network.requestIntercepted', async ({ interceptionId, request }) => {
  await client.send('Network.continueInterceptedRequest', {
    interceptionId,
    headers: {
      ...request.headers,
      'X-Test-User': 'mock-user-id',
      'Authorization': 'Bearer mock-token'
    }
  });
});
```

---

## 7. 性能分析

```javascript
function analyzePerformance(requests) {
  const entries = Array.from(requests.values())
    .filter(r => r.duration != null)
    .sort((a, b) => a.startTime - b.startTime);

  // 慢请求（> 1s）
  const slow = entries.filter(r => r.duration > 1000);

  // 按类型统计
  const byType = entries.reduce((acc, r) => {
    acc[r.type] = (acc[r.type] || 0) + 1;
    return acc;
  }, {});

  // 总传输量
  const totalBytes = entries.reduce((s, r) => s + (r.encodedDataLength || 0), 0);

  console.log(`\n📊 性能统计（共 ${entries.length} 条请求）`);
  console.log(`  总传输：${(totalBytes / 1024).toFixed(1)} KB`);
  console.log(`  请求类型：${JSON.stringify(byType)}`);

  if (slow.length > 0) {
    console.log(`\n🐢 慢请求 (>1s)：`);
    slow.forEach(r => {
      const path = r.url.replace(/https?:\/\/[^/]+/, '').split('?')[0];
      console.log(`  ${r.duration}ms  [${r.status}]  ${path}`);
    });
  }

  return { entries, slow, byType, totalBytes };
}
```

---

## 8. HAR 导出

```javascript
function exportHAR(requests, outputPath) {
  const entries = Array.from(requests.values())
    .filter(r => r.status)
    .map(req => ({
      startedDateTime: new Date(req.startTime * 1000).toISOString(),
      time: req.duration || 0,
      request: {
        method: req.method,
        url: req.url,
        httpVersion: 'HTTP/2.0',
        headers: Object.entries(req.headers || {}).map(([name, value]) => ({ name, value })),
        queryString: [],
        cookies: [],
        headersSize: -1,
        bodySize: req.postData ? Buffer.byteLength(req.postData) : 0,
        postData: req.postData ? {
          mimeType: req.headers?.['content-type'] || 'application/json',
          text: req.postData
        } : undefined
      },
      response: {
        status: req.status,
        statusText: req.statusText || '',
        httpVersion: 'HTTP/2.0',
        headers: Object.entries(req.responseHeaders || {}).map(([name, value]) => ({ name, value })),
        cookies: [],
        content: {
          size: req.encodedDataLength || 0,
          mimeType: req.mimeType || 'application/octet-stream',
          text: req.responseBody || ''
        },
        redirectURL: '',
        headersSize: -1,
        bodySize: req.encodedDataLength || -1
      },
      cache: {},
      timings: { send: 0, wait: req.timing?.receiveHeadersEnd || 0, receive: 0 }
    }));

  const har = {
    log: {
      version: '1.2',
      creator: { name: 'CDP Network Capture', version: '1.0' },
      entries
    }
  };

  require('fs').writeFileSync(outputPath, JSON.stringify(har, null, 2));
  console.log(`HAR 已导出至：${outputPath}（可导入 Chrome DevTools / Charles）`);
  return outputPath;
}

// 使用
exportHAR(requests, '/root/.openclaw/workspace/captures/session.har');
```

---

## 9. 兼容性边界

| 场景 | CDP Network 支持 | 解决方案 |
|------|:-----------:|---------|
| 普通 XHR / fetch | ✅ | 本文方案直接适用 |
| WebSocket 消息帧 | ❌ | 用 `Network.webSocketFrameReceived` 单独监听 |
| SSE (EventSource) | ⚠️ 部分 | 监听 `Network.eventSourceMessageReceived` |
| Service Worker 缓存 | ❌ | 启动时禁用 SW：`evaluateOnNewDocument` 覆盖 `navigator.serviceWorker` |
| 跨域 iframe 请求 | ⚠️ 需额外处理 | 对每个 iframe target 单独 `createCDPSession` |
| Blob URL / Data URL | ❌ | 在 JS 层 hook `fetch` / `XMLHttpRequest` |
| HTTP/2 Server Push | ❌ | 改用代理层（whistle） |

### WebSocket 专项监听

```javascript
client.on('Network.webSocketCreated', ({ requestId, url }) => {
  console.log('[WS OPEN]', url);
});

client.on('Network.webSocketFrameReceived', ({ requestId, response }) => {
  console.log('[WS RECV]', response.payloadData);
});

client.on('Network.webSocketFrameSent', ({ requestId, response }) => {
  console.log('[WS SEND]', response.payloadData);
});
```

### 跨域 iframe 监听

```javascript
browser.on('targetcreated', async (target) => {
  if (target.type() === 'iframe') {
    const iframeClient = await target.createCDPSession();
    await iframeClient.send('Network.enable');
    iframeClient.on('Network.requestWillBeSent', (params) => {
      if (params.request.url.includes('/api/')) {
        console.log('[IFRAME REQ]', params.request.url);
      }
    });
  }
});
```

---

## 10. 注意事项

1. **`getResponseBody` 必须在 `loadingFinished` 之后调用**，否则报错。
2. **`requestId` 是唯一关联键**，不要用 URL 匹配来关联请求和响应（重复 URL 会混淆）。
3. **Map 内存管理**：长时间运行时，`requests` Map 会持续增长。测试结束后及时 `requests.clear()`。
4. **拦截必须放行**：启用 `setRequestInterception` 后，每个请求都必须调用 `continueInterceptedRequest` 或 `fulfillInterceptedRequest`，否则页面挂起。
5. **CDP session 复用**：如果 SKILL.md 的连接模板已创建了 `client`，直接复用，不要重复 `createCDPSession`。
6. **HTTPS 无需配置**：CDP 抓包自动处理 HTTPS，不需要安装证书。
7. **body 编码**：`fulfillInterceptedRequest` 的 body 必须是 **base64 编码**的字符串。
8. **响应 body 大小**：超大响应（> 10MB）的 body 获取可能超时，加 try/catch 兜底。
