# React 受控组件表单填写

## 问题

React 受控组件（controlled component）通过 state 管理 value。直接设置 `el.value = 'xxx'` 不会触发 React 的 onChange，导致表单值不生效。

`page.type()` 在某些 React 输入框上**会卡死**，不要使用。

## 解决方案：Native Setter + 事件触发

### input 元素

```javascript
await page.evaluate((value) => {
  const el = document.querySelector('input#myInput');
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
  ).set;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '要填入的值');
```

### textarea 元素

```javascript
await page.evaluate((value) => {
  const el = document.querySelector('textarea#description');
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, 'value'
  ).set;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '要填入的内容');
```

### 模拟 Enter 键触发搜索

某些搜索框需要按 Enter 才触发搜索，但 `page.keyboard.press('Enter')` 可能不生效。用事件模拟：

```javascript
await page.evaluate(() => {
  const input = document.querySelector('input[placeholder*="搜索"]');
  input.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', keyCode: 13, bubbles: true
  }));
});
```

## 注意事项

1. **不要用 `page.type()`** — 在 React 组件上可能卡死
2. **setter 选择** — input 用 `HTMLInputElement.prototype`，textarea 用 `HTMLTextAreaElement.prototype`
3. **事件顺序** — 先 `input` 再 `change`，两个都要触发
4. **focus 先行** — 某些组件需要先 `el.focus()` 才能写入
