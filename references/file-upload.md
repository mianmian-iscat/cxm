# 文件上传操作

## 标准文件上传（有 input[type="file"]）

```javascript
const fileInput = await page.$('input[type="file"]');
await fileInput.uploadFile('/path/to/file.jpg');
await new Promise(r => setTimeout(r, 3000)); // 等待上传
```

## 非标准文件上传（无 input[type="file"]）

许多现代组件库（如千牛素材选择器）**没有标准的 `input[type="file"]`**。点击上传按钮后由组件库动态创建文件选择器。

### 方案：page.waitForFileChooser()

```javascript
// 必须在点击前注册 waitForFileChooser
const [fileChooser] = await Promise.all([
  page.waitForFileChooser({ timeout: 8000 }),
  // 同时点击触发上传的按钮
  frame.evaluate(() => {
    document.querySelector('button.upload')?.click();
  })
]);

// 选择文件
await fileChooser.accept(['/path/to/image.jpg']);
await new Promise(r => setTimeout(r, 5000)); // 等上传到 CDN
```

### 关键点

1. **`waitForFileChooser` 必须在 click 之前注册**，用 `Promise.all` 并行
2. 如果上传按钮在 iframe 内，点击用 `frame.evaluate`，但 `waitForFileChooser` 始终在 `page` 上注册
3. 等待时间要足够（上传到 CDN 通常需要 5-8 秒）

## 遮挡清除

上传按钮经常被通知面板、浮窗等遮挡。操作前必须检测并清除：

```javascript
await page.evaluate(() => {
  const btn = document.querySelector('.upload-button');
  if (!btn) return;
  const r = btn.getBoundingClientRect();
  let topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
  let attempts = 0;
  while (topEl && !btn.contains(topEl) && topEl !== btn && attempts < 10) {
    topEl.style.display = 'none';
    topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    attempts++;
  }
});
```

## 图片校验规则（常见）

| 约束 | 常见值 |
|------|--------|
| 宽高比 | 3:4 |
| 最小尺寸 | 750×1000px |
| 格式 | JPG / PNG |
| 文件大小 | < 5MB |
| 数量 | 1-9 张 |
