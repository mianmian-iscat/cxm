# iframe 操作指南

## 查找 iframe

```javascript
// 按 URL 关键词查找
const frame = page.frames().find(f => f.url().includes('关键词'));

// 按 iframe 元素属性查找
const iframeHandle = await page.$('iframe#myFrame');
const frame = await iframeHandle.contentFrame();
```

## iframe 内执行 JS

```javascript
const result = await frame.evaluate(() => {
  // 在 iframe 上下文内执行
  return document.querySelector('.target')?.innerText;
});
```

## iframe 内点击元素

iframe 内的元素坐标是相对于 iframe 的，但 `page.mouse` 使用的是页面坐标。需要加上 iframe 的偏移：

```javascript
// 获取目标元素在 iframe 内的坐标
const targetRect = await frame.evaluate(() => {
  const el = document.querySelector('.target');
  const r = el.getBoundingClientRect();
  return { x: r.x + r.width/2, y: r.y + r.height/2 };
});

// 获取 iframe 在页面中的偏移
const iframeRect = await page.evaluate(() => {
  const iframe = document.querySelector('iframe[src*="关键词"]');
  const r = iframe.getBoundingClientRect();
  return { x: r.x, y: r.y };
});

// 页面坐标 = iframe 偏移 + 元素在 iframe 内的坐标
await page.mouse.click(iframeRect.x + targetRect.x, iframeRect.y + targetRect.y);
```

## hover 后点击（隐藏 checkbox 场景）

某些组件的 checkbox 仅在 hover 时才可见（宽高为 0）。必须先 hover 再 click：

```javascript
await page.mouse.move(pageX, pageY);
await new Promise(r => setTimeout(r, 800)); // 等 hover 状态生效
await page.mouse.click(pageX, pageY);
await new Promise(r => setTimeout(r, 2000));
```

## iframe detach 处理

某些操作完成后（如登录成功、裁剪确认），iframe 会被销毁（detach）。

**症状**：`Attempted to use detached Frame 'XXXXX'`

**处理方式**：
1. 在可能导致 detach 的操作前，提前获取需要的数据
2. 操作后不再使用原 frame 引用
3. 用 try/catch 包裹，捕获 detach 错误

```javascript
try {
  await frame.evaluate(() => {
    document.querySelector('button.confirm')?.click();
  });
} catch(e) {
  if (e.message.includes('detached')) {
    console.log('iframe 已关闭（正常行为）');
  } else {
    throw e;
  }
}
// 之后只操作 page，不再操作 frame
await new Promise(r => setTimeout(r, 5000));
```
