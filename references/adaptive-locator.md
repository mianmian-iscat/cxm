# 自适应元素定位工具

适用于 UI 频繁变动的业务页面。不依赖 CSS class/id，通过语义特征定位元素。

## 使用场景

- 业务测试页面（穿搭星球前端等），每次迭代 UI 可能变化
- 不确定页面结构时，先 snapshot 再定位
- 中间件配置页面**不需要用这个**，直接用硬编码选择器更可靠

## 工具函数

将以下代码块作为脚本头部引入即可使用。

```javascript
// ========== 自适应元素定位工具 ==========

/**
 * 语义化定位元素，按优先级降级：
 * 1. 文本精确匹配
 * 2. 文本模糊匹配（包含）
 * 3. aria-label
 * 4. role + name 组合
 * 5. CSS 选择器（兜底）
 *
 * @param {Page} page - Puppeteer page 对象
 * @param {Object} options
 * @param {string} [options.text] - 元素文本（精确匹配）
 * @param {string} [options.textContains] - 元素文本（模糊匹配）
 * @param {string} [options.ariaLabel] - aria-label 值
 * @param {string} [options.role] - ARIA role（如 button, textbox）
 * @param {string} [options.selector] - CSS 选择器（兜底）
 * @param {string} [options.tag] - 限定标签名（如 button, input, a）
 * @param {number} [options.timeout=5000] - 最长等待时间 ms
 * @param {boolean} [options.visible=true] - 只匹配可见元素
 * @returns {ElementHandle|null}
 */
async function findElement(page, options) {
  const {
    text, textContains, ariaLabel, role, selector,
    tag = '*', timeout = 5000, visible = true
  } = options;

  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const el = await page.evaluateHandle((opts) => {
      const { text, textContains, ariaLabel, role, tag, visible } = opts;

      function isVisible(el) {
        if (!visible) return true;
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }

      const candidates = Array.from(document.querySelectorAll(tag));

      // 1. 文本精确匹配
      if (text) {
        const found = candidates.find(el =>
          el.innerText?.trim() === text && isVisible(el)
        );
        if (found) return found;
      }

      // 2. 文本模糊匹配
      if (textContains) {
        const found = candidates.find(el =>
          el.innerText?.trim().includes(textContains) && isVisible(el)
        );
        if (found) return found;
      }

      // 3. aria-label
      if (ariaLabel) {
        const found = candidates.find(el =>
          el.getAttribute('aria-label') === ariaLabel && isVisible(el)
        );
        if (found) return found;
      }

      // 4. role + name
      if (role) {
        const found = candidates.find(el =>
          el.getAttribute('role') === role && isVisible(el)
        );
        if (found) return found;
      }

      return null;
    }, { text, textContains, ariaLabel, role, tag, visible });

    // evaluateHandle 返回 JSHandle，检查是否为有效 element
    const isNull = await el.evaluate(e => e === null).catch(() => true);
    if (!isNull) return el.asElement();

    await new Promise(r => setTimeout(r, 300));
  }

  // 全部策略失败，尝试 CSS 选择器兜底
  if (selector) {
    const el = await page.$(selector);
    if (el) return el;
  }

  return null;
}

/**
 * 定位元素，找不到时截图并抛错
 */
async function findElementOrFail(page, options, shotFn) {
  const el = await findElement(page, options);
  if (!el) {
    if (shotFn) await shotFn('element-not-found');
    const desc = options.text || options.textContains || options.ariaLabel || options.selector || 'unknown';
    throw new Error(`找不到元素: "${desc}"`);
  }
  return el;
}

/**
 * 在指定容器内定位元素（如弹窗、抽屉内）
 *
 * @param {Page} page
 * @param {string} containerSelector - 容器选择器
 * @param {Object} options - 同 findElement
 */
async function findInContainer(page, containerSelector, options) {
  const { text, textContains, tag = '*' } = options;

  return await page.evaluateHandle((cSel, opts) => {
    const containers = document.querySelectorAll(cSel);
    for (const container of containers) {
      if (getComputedStyle(container).display === 'none') continue;

      const candidates = Array.from(container.querySelectorAll(opts.tag || '*'));

      if (opts.text) {
        const found = candidates.find(el => el.innerText?.trim() === opts.text);
        if (found) return found;
      }
      if (opts.textContains) {
        const found = candidates.find(el => el.innerText?.trim().includes(opts.textContains));
        if (found) return found;
      }
    }
    return null;
  }, containerSelector, { text, textContains, tag });
}

/**
 * 等待包含指定文本的元素出现
 */
async function waitForText(page, text, timeout = 10000) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const found = await page.evaluate((t) => {
      return document.body.innerText?.includes(t);
    }, text);
    if (found) return true;
    await new Promise(r => setTimeout(r, 300));
  }
  return false;
}

/**
 * 使用 agent-browser snapshot 获取语义化元素列表
 * 需要 agent-browser CLI 已安装且通过 --cdp 连接
 *
 * @param {string} cdpPort - CDP 端口
 * @returns {Object} { refs, snapshot }
 */
async function getAccessibilitySnapshot(cdpPort = '9222') {
  const { execSync } = require('child_process');
  const output = execSync(
    `agent-browser --cdp ${cdpPort} snapshot -i --json`,
    { encoding: 'utf-8', timeout: 15000 }
  );
  const data = JSON.parse(output);
  return data.data || {};
}

/**
 * 从 snapshot refs 中按语义查找元素 ref
 *
 * @param {Object} refs - snapshot 返回的 refs 对象
 * @param {Object} query - { role, name, nameContains }
 * @returns {string|null} ref id（如 "e12"）
 */
function findRef(refs, query) {
  for (const [refId, info] of Object.entries(refs)) {
    if (query.role && info.role !== query.role) continue;
    if (query.name && info.name !== query.name) continue;
    if (query.nameContains && !info.name?.includes(query.nameContains)) continue;
    return refId;
  }
  return null;
}
```

## 使用示例

### 基础用法：按文本找按钮

```javascript
const btn = await findElementOrFail(page, {
  text: '提交订单',
  tag: 'button'
}, shot);
await btn.click();
```

### 弹窗内定位

```javascript
const confirmBtn = await findInContainer(
  page,
  '.next-overlay-wrapper',  // 弹窗容器
  { text: '确定', tag: 'button' }
);
```

### 模糊匹配

```javascript
// 文本可能是 "提交(3)" 或 "提交订单"
const btn = await findElement(page, {
  textContains: '提交',
  tag: 'button'
});
```

### 结合 agent-browser snapshot

```javascript
const { refs } = await getAccessibilitySnapshot();

// 找到 role=button, name 包含"提交"的元素
const ref = findRef(refs, { role: 'button', nameContains: '提交' });
if (ref) {
  const { execSync } = require('child_process');
  execSync(`agent-browser --cdp 9222 click @${ref}`);
}
```

### 带重试的完整流程

```javascript
// 点击按钮 → 等待弹窗 → 确认
const submitBtn = await findElementOrFail(page, { text: '提交', tag: 'button' }, shot);
await submitBtn.click();

const appeared = await waitForText(page, '确认提交');
if (!appeared) throw new Error('确认弹窗未出现');

const confirmBtn = await findInContainer(page, '.next-overlay-wrapper', { text: '确定', tag: 'button' });
await confirmBtn.asElement()?.click();
```

## 选择策略指引

| 页面特点 | 推荐方式 |
|---------|---------|
| 中间件配置（TPP/Skyline） | 直接用 CSS 选择器，不需要本工具 |
| 业务页面，按钮文案稳定 | `findElement({ text: '...' })` |
| 业务页面，结构不确定 | `getAccessibilitySnapshot()` + `findRef()` |
| 完全未知的页面 | snapshot → AI 分析 → 手动决策 |
