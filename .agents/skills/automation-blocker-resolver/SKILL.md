---
name: automation-blocker-resolver
description: 分析和修复 UI 自动化测试中的阻塞用例。当用户提到自动化用例阻塞、UI 自动化失败、键盘/焦点/拖拽/缩放等自动化无法执行的场景时触发。提供分类诊断（焦点问题/Mock可解决/状态直操/转人工）和对应修复代码模板，支持 Playwright、Cypress、Selenium 等主流框架。
version: 1.0.0
---

> 📋 测试商家 seller_id 统一维护入口：[test-accounts.md](../yc-protection-qa-workbench/test-accounts.md)（插件根目录）

# UI 自动化阻塞用例分析与修复

## 触发条件

- 用户说"自动化用例阻塞"、"自动化跑不过"、"XX条用例被阻塞"
- 用户给出一批因环境限制无法自动化的用例清单
- 用户问"怎么优化这些阻塞用例"

## 核心方法论：四层分类法

面对一批阻塞用例，按以下顺序逐条分类：

```
第1层：技术可修复  → 改脚本本身（焦点/事件/选择器问题）
第2层：绕过 UI     → 直操状态（调 API/改 store/dispatch action）
第3层：Mock 拦截   → 模拟异常（网络层拦截返回错误响应）
第4层：转人工验证  → 不适合自动化（真实视觉/物理手势/过渡动画）
```

### 分类决策树

```
用例阻塞原因是什么？
├── 键盘事件没触发？ → 第1层：焦点修复
├── UI 交互不稳定？（滑块/拖拽/缩放） → 第2层：状态直操
├── 需要模拟异常？（超时/报错/断网） → 第3层：Mock 拦截
├── 需要真实视觉反馈？（动画/过渡/全屏/手势） → 第4层：转人工
└── 不确定？ → 先试第1层，不行再降级
```

---

## 第1层：焦点与键盘事件修复

### 问题特征

- `page.keyboard.press()` 发出按键但组件没响应
- React/Vue 事件委托绑定在特定容器上，焦点不在容器上则收不到事件
- 快捷键与浏览器默认行为冲突（Ctrl+Z 触发浏览器撤销而非应用撤销）

### 通用修复模式

**原则：所有键盘操作前，必须先让目标容器获得焦点。**

#### Playwright

```typescript
// ❌ 错误写法
await page.keyboard.press('Space');

// ✅ 正确写法
const editor = page.locator('.editor-canvas-container');
await editor.click(); // click 自带 focus
await page.keyboard.press('Space');

// ✅ 更稳健：确认焦点
await editor.click();
await expect(editor).toBeFocused();
await page.keyboard.press('Space');
```

#### Cypress

```javascript
// ❌ 错误写法
cy.get('body').type(' ');

// ✅ 正确写法
cy.get('.editor-canvas-container').focus().type(' ');
```

#### Selenium (Python)

```python
# ❌ 错误写法
driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.SPACE)

# ✅ 正确写法
editor = driver.find_element(By.CSS_SELECTOR, '.editor-canvas-container')
editor.click()  # 获取焦点
editor.send_keys(Keys.SPACE)
```

### 快捷键冲突处理

当 Ctrl+Z / Ctrl+Shift+Z 等快捷键与浏览器冲突时：

```typescript
// Playwright：直接 dispatch 到编辑器容器，绕过浏览器默认行为
const editor = page.locator('.editor-canvas-container');
await editor.click();
await editor.dispatchEvent('keydown', {
  key: 'z',
  code: 'KeyZ',
  ctrlKey: true,
  bubbles: true,
});
```

### builtin_browser MCP 工具（Chrome Extension V2）

当使用 QoderWork 的 `builtin_browser` MCP 工具（`computer` / `form_input` / `javascript_tool`）时，AntD / TBD 的 Drawer、Modal 等组件内部 input 可能不出现在 accessibility tree 中，导致 `form_input` 无法通过 ref 定位。

**问题特征**：
- `read_page` 返回的 accessibility tree 中没有 drawer/modal 内的 input 元素
- `form_input` 报 "element not found" 或无对应 ref
- `nativeInputValueSetter` 设置 DOM value 后 React 状态未更新，表单校验认为字段为空

**修复链路**：

```
1. javascript_tool → element.focus()         // DOM 层聚焦，让 input 获得焦点
2. computer action=type → 逐字符键盘输入     // 触发 React keydown/input 事件链
3. computer action=key Tab → 失焦            // 触发 onBlur，后端查询（如有）
```

**具体代码**：

```javascript
// 步骤1：javascript_tool 定位并 focus input（通过 DOM 选择器，不依赖 a11y tree）
(() => {
  const drawer = document.querySelector('.tbd-drawer, .ant-drawer, .ant-modal');
  const input = drawer.querySelector('input.target-class, input:first-of-type');
  input.focus();
  input.select(); // 如有残留值，全选以便替换
  return 'focused';
})()

// 步骤2：computer action=type 键盘输入（触发完整 React 事件链）
// { action: "type", text: "2213249110271", tabId: <tab_id> }  // seller_id 详见 test-accounts.md

// 步骤3：computer action=key Tab 触发 onBlur 查询
// { action: "key", text: "Tab", tabId: <tab_id> }
```

**验证 React 状态已更新**：
```javascript
// 键盘输入后检查关联字段是否自动填充（如店铺名称）
(() => {
  const drawer = document.querySelector('.tbd-drawer, .ant-drawer');
  const storeName = drawer.querySelector('[class*=storeName], [class*=shopName]');
  return storeName?.textContent; // 如有值说明 React 已响应
})()
```

**关键注意点**：
- 组件库可能是 `tbd-drawer`（TBD）而非 `ant-drawer`（AntD），选择器需适配
- `nativeInputValueSetter` 只改 DOM value，**不触发 React onChange**，此场景下无效
- `computer action=type` 模拟真实键盘事件（keydown → keypress → input → keyup），React 能感知
- 按钮文本可能有空格（如"提 交"而非"提交"），JS 匹配需用 `includes('提') && includes('交')`

### 公共 Helper 模板

```typescript
// tests/helpers/focus-helpers.ts
import { Page } from '@playwright/test';

/**
 * 让目标容器获得焦点，所有键盘操作前必须调用
 */
export async function focusTarget(
  page: Page,
  selector = '.editor-canvas-container'
) {
  const target = page.locator(selector);
  await target.waitFor({ state: 'visible' });
  await target.click();
  await expect(target).toBeFocused();
}

/**
 * 在目标容器内执行键盘操作（自动确保焦点）
 */
export async function safeKeyPress(page: Page, key: string, selector?: string) {
  await focusTarget(page, selector);
  await page.keyboard.press(key);
}
```

---

## 第2层：绕过 UI 直操状态

### 问题特征

- 滑块、拖拽、缩放等 UI 交互自动化不稳定
- click 滑块没触发实际效果
- 需要精确像素级操作（拖拽裁切框 handle）

### 通用修复模式

**原则：跳过 UI 交互层，直接调用组件 API 或修改底层状态。**

#### Playwright — page.evaluate 直操

```typescript
// ❌ 错误写法：拖拽缩放
await page.dragAndDrop('.zoom-handle', '.zoom-end');

// ✅ 正确写法：直接调组件 API
await page.evaluate((zoomLevel) => {
  // 方式1：window 暴露的实例
  (window as any).__editor?.setZoom(zoomLevel);
  
  // 方式2：Redux store
  (window as any).__store?.dispatch({ type: 'SET_ZOOM', payload: zoomLevel });
  
  // 方式3：自定义事件
  document.dispatchEvent(new CustomEvent('editor:zoom', { detail: { level: zoomLevel } }));
}, 2.0); // 缩放到 200%
```

#### 状态验证

```typescript
// 直操后验证渲染结果
const transform = await page.locator('.canvas').evaluate(el => el.style.transform);
expect(transform).toContain('scale(2)');
```

---

## 第3层：Mock / 网络拦截

### 问题特征

- 需要模拟网络超时、API 500、断网、上传失败等异常场景
- 真实模拟异常环境成本高且不可重复

### 通用修复模式

**原则：用网络层拦截替代真实异常模拟，更可控、更可重复。**

#### Playwright — page.route()

```typescript
// 网络超时
await page.route('**/api/save**', async (route) => {
  await new Promise(r => setTimeout(r, 30000)); // 延迟30秒
  await route.continue();
});

// API 500
await page.route('**/api/save**', async (route) => {
  await route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'Internal Server Error' }),
  });
});

// 网络断开
await page.route('**/api/**', async (route) => {
  await route.abort('failed');
});

// 上传失败（仅拦截 POST/PUT）
await page.route('**/api/upload**', async (route) => {
  if (['POST', 'PUT'].includes(route.request().method())) {
    await route.fulfill({ status: 500, body: '{"error":"Upload failed"}' });
  } else {
    await route.continue();
  }
});

// 用例结束后清理
test.afterEach(async ({ page }) => {
  await page.unroute('**/*');
});
```

#### Cypress — cy.intercept()

```javascript
cy.intercept('POST', '/api/save', { statusCode: 500, body: { error: 'fail' } });
cy.intercept('GET', '/api/data', { delay: 30000 }); // 超时
cy.intercept('GET', '/api/**', { forceNetworkErroring: true }); // 断网
```

#### Selenium (Python) — selenium-wire / mitmproxy

```python
from seleniumwire import webdriver

driver = webdriver.Chrome()

def interceptor(request):
    if '/api/save' in request.path:
        request.abort()  # 断网

driver.request_interceptor = interceptor
```

---

## 第4层：转人工验证

### 判断标准

以下场景自动化投入产出比低，建议直接标记为人工验证：

- **全屏模式**：requestFullscreen 需要真实用户手势
- **精确拖拽**：裁切框 handle 需要像素级精度拖拽
- **播放观察**：播放头跟随/循环播放/播放范围需要实时观察动画
- **面板过渡**：loading 动画/上传进度条需要观察过渡过程
- **视觉一致性**：颜色/动画流畅度/视觉对齐等主观判断

### 输出格式

转为人工验证时，生成 check list：

```markdown
### 人工验证清单（XX条）
- [ ] 全屏模式：点击全屏按钮 → 验证全屏渲染、ESC退出
- [ ] 拖拽裁切：拖拽四角/四边 handle → 验证裁切区域实时更新
- [ ] 播放观察：触发播放 → 观察播放头平滑移动、循环无缝
```

---

## 三层组合验证策略（替代人工视觉确认）

当用例被标记为"需人工确认"时，优先尝试以下三层验证：

### 第1层：API 验证数据正确性

**原则：API 返回正确 = 业务逻辑正确 = 90% 的 UI 应该对。**

```typescript
// 验证 API 数据，替代 UI 展示断言
const response = await page.evaluate(() => {
  return (window as any).__store?.getState()?.taskList;
});
expect(response.failedCount).toBeGreaterThan(0); // API 数据正确
```

适用场景：数据展示类（失败数、状态、列表筛选结果）

### 第2层：DOM 属性验证渲染状态

**原则：class / style / aria-* / data-* 属性 = UI 状态正确。**

```typescript
// 验证 DOM 状态，替代视觉观察
await expect(panel).toHaveAttribute('aria-expanded', 'true');     // 展开
await expect(element).toHaveClass(/ant-collapse-content-active/); // 折叠面板
await expect(cell).toHaveAttribute('data-status', 'error');       // 错误状态

// 验证 CSS 属性，替代颜色判断
const color = await element.evaluate(el => getComputedStyle(el).color);
expect(color).toBe('rgb(245, 34, 45)'); // Ant Design 红色

// 轮询验证动态过程，替代"观察播放/加载过程"
for (let i = 0; i < 10; i++) {
  const time = await page.locator('.playhead-time').textContent();
  times.push(time);
  await page.waitForTimeout(300);
}
expect(times[9]).not.toBe(times[0]); // 时间在变化
```

适用场景：展开/折叠、loading 状态、进度条、播放进度、颜色渲染

### 第3层：截图对比兜底

**原则：仅在关键节点使用，首次通过生成基线，后续自动对比。**

```typescript
// Playwright 截图对比
await expect(page).toHaveScreenshot('editor-fullscreen.png', {
  maxDiffPixelRatio: 0.01, // 允许1%像素差异
});

// 局部截图
await expect(page.locator('.canvas-area')).toHaveScreenshot('crop-overlay.png');
```

适用场景：视觉效果验证（全屏、裁切框、布局变化）

### 决策优先级

```
能用 API 验证？ → 第1层（最稳定、最快）
不能用 API 但能读 DOM？ → 第2层（稳定、较快）
DOM 也读不了？ → 第3层（截图对比，较慢但自动化）
三层都不行？ → 才考虑转人工（极少数情况）
```

---

## 执行流程

### 输入

用户提供阻塞用例列表（表格/文字/截图均可），包含：用例名称 + 阻塞原因描述。

### 步骤

1. **逐条分类**：按决策树将每条用例归入四层之一
2. **输出分类表**：

```markdown
| 用例 | 原阻塞原因 | 分层 | 修复方案 |
|------|-----------|------|---------|
| XX   | 键盘没响应 | 第1层 | focusTarget() |
| YY   | 需要模拟超时 | 第3层 | page.route() |
```

3. **生成修复代码**：按分层输出具体代码修改方案（before/after 对照）
4. **提取公共 helper**：识别可复用的工具函数，抽到 `tests/helpers/` 目录
5. **人工验证清单**：第4层用例输出 check list
6. **给出执行优先级和工时估算**

### 优先级建议模板

```
P0 — 技术可修复（改动最小，半天可完成）
P1 — Mock 拦截（一次投入长期受益，1-2天）
P2 — 状态直操（需了解组件 API，1天）
P3 — 转人工验证（整理 check list，0.5天）
```

---

## 工具集封装

所有修复模式已封装为单一可复用模块：**playwright-automation-kit.ts**（21 个类别、50+ 函数）。

### Part A: UI 自动化操作（12 类）

| # | 类别 | 核心函数 | 用途 |
|---|------|---------|------|
| 1 | 焦点与键盘 | `focusTarget()`, `safeKeyPress()`, `dispatchKeyEvent()` | 键盘事件不触发、快捷键冲突 |
| 2 | 文件上传 | `uploadFile()`, `uploadMultipleFiles()` | 绕过系统文件选择对话框 |
| 3 | 网络拦截 | `mockApiResponse()`, `mockTimeout()`, `mockNetworkError()`, `mockServerError()`, `mockUploadFail()` | Mock 各种异常网络环境 |
| 4 | 状态直操 | `modifyState()`, `readState()`, `stateOps.*` | 绕过 UI 直接修改前端 store/状态 |
| 5 | DOM 验证 | `expectHasClass()`, `expectCss()`, `expectAria()`, `expectSize()` | 验证渲染状态替代视觉观察 |
| 6 | 进度轮询 | `pollProgress()`, `pollUntil()`, `expectProgressIncreasing()` | 验证动态过程（播放/加载/上传） |
| 7 | 截图对比 | `snapshotCompare()`, `snapshotAt()` | 关键节点视觉回归兜底 |
| 8 | 故障注入 | `injectFailureOnNthCall()`, `mockStagedProgress()` | 模拟失败后重试/恢复场景 |
| 9 | URL 导航 | `navigateWithParams()`, `expectUrlHasParam()`, `navigateWithoutParams()` | 绕过 Ant Select 等 UI 交互 |
| 10 | 全屏 | `enterFullscreen()`, `exitFullscreen()`, `setViewportFullscreen()` | 绕过 user gesture 限制 |
| 11 | 拖拽 | `preciseDrag()`, `dragByOffset()` | 精确像素级拖拽操作 |
| 12 | 等待策略 | `waitForVisible()`, `waitForHidden()`, `waitForRequest()`, `waitForResponse()`, `waitForCondition()` | 各种异步等待场景 |

### Part B: 异常处理与容错（9 类）

| # | 类别 | 核心函数 | 用途 |
|---|------|---------|------|
| 13 | 自动重试 | `retryAction()`, `safeClick()`, `safeType()` | 操作失败自动重试，支持指数退避 |
| 14 | 元素降级 | `findElementWithFallback()`, `assertIfVisible()` | 主选择器失败时自动切换备选 |
| 15 | 超时兜底 | `withTimeout()`, `waitForWithFallback()` | 超时不抛异常，走降级逻辑 |
| 16 | 状态回滚 | `withRollback()`, `withPageRefreshOnFailure()` | 操作失败后自动恢复原状 |
| 17 | 截图取证 | `withErrorCapture()`, `setupCrashRecovery()` | 异常自动截图保存现场 |
| 18 | 日志记录 | `logger.*`, `withLogging()` | 操作级日志（开始/成功/失败/耗时） |
| 19 | 断言容错 | `softAssert()`, `softWaitFor()`, `softAssertText()`, `reportSoftAssertions()` | 软断言不中断测试，统一汇报 |
| 20 | 网络监听 | `setupNetworkErrorListener()`, `setupPageErrorListener()` | 自动收集 4xx/5xx/JS 异常 |
| 21 | 清理管理 | `registerCleanup()`, `runCleanups()`, `safeAfterEach()` | 测试后自动清理（mock/数据/路由） |

使用方式：
```typescript
import { focusTarget, safeClick, retryAction, logger, ... } from './playwright-automation-kit';
```

---

## 注意事项

- **先分类再动手**：不要一上来就改代码，先把所有阻塞用例全部分完类再批量修复
- **公共 helper 先行**：修复前先抽 helper，后续用例统一调用
- **每修完一层跑一次回归**：确认修复生效且没引入新问题
- **第4层不要硬做**：如果评估后发现某条自动化成本 > 人工成本 × 3，果断转人工
- **三层组合验证优先**：API 验证数据 → DOM 验证渲染状态 → 截图对比兜底，尽量不转人工
