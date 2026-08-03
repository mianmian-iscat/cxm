# CDP API 速查

本 skill 中直接使用的 Chrome DevTools Protocol API。

## 获取 CDP Session

```javascript
const client = await page.target().createCDPSession();
// 用完后释放
await client.detach();
```

## Browser 域

### 获取窗口 ID
```javascript
const { windowId } = await client.send('Browser.getWindowForTarget');
```

### 最大化窗口
```javascript
await client.send('Browser.setWindowBounds', {
  windowId,
  bounds: { windowState: 'maximized' }
});
```

### 获取窗口大小
```javascript
const { bounds } = await client.send('Browser.getWindowBounds', { windowId });
// bounds: { left, top, width, height, windowState }
```

## Page 域

### 全屏截图（推荐）
```javascript
const { data } = await client.send('Page.captureScreenshot', {
  format: 'png',           // 'png' | 'jpeg' | 'webp'
  captureBeyondViewport: false  // 只截可视区域
});
// data 是 base64 编码
require('fs').writeFileSync(path, Buffer.from(data, 'base64'));
```

## Input 域

### 底层鼠标事件（绕过遮挡问题）
```javascript
// 鼠标按下
await client.send('Input.dispatchMouseEvent', {
  type: 'mousePressed',
  x: 500, y: 300,
  button: 'left',
  clickCount: 1
});
// 鼠标释放
await client.send('Input.dispatchMouseEvent', {
  type: 'mouseReleased',
  x: 500, y: 300,
  button: 'left',
  clickCount: 1
});
```

## Puppeteer 高级 API

| API | 用途 | 注意事项 |
|-----|------|----------|
| `page.frames()` | 获取所有 iframe | 按 URL 关键词 find |
| `page.waitForFileChooser()` | 拦截原生文件选择器 | 必须在触发 click 前注册 |
| `page.mouse.move(x, y)` | 移动鼠标（触发 hover） | hover-only 的 UI 元素必须先 move |
| `page.mouse.click(x, y)` | 鼠标点击 | 坐标是页面绝对坐标 |
| `frame.evaluate(fn)` | 在 iframe 内执行 JS | frame detach 后不可调用 |
| `page.setViewport({w, h})` | 设置视口大小 | 配合 Browser.setWindowBounds |
