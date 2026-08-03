# 截图规范

## 为什么必须用 CDP 截图

`page.screenshot()` 在 viewport 与实际窗口大小不匹配时，只截取左上角局部区域（如 800×600），而非全屏 1280×1024。

**必须用 CDP `Page.captureScreenshot`**。

## CDP 截图模板

```javascript
const fs = require('fs');

async function screenshot(page, name, client) {
  // 清水印
  await page.evaluate(() => {
    document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
  });
  await new Promise(r => setTimeout(r, 200));
  
  const path = `/root/.openclaw/workspace/screenshots/${name}.png`;
  const { data } = await client.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false
  });
  fs.writeFileSync(path, Buffer.from(data, 'base64'));
  console.log(`📸 ${path}`);
  return path;
}
```

## 初始化 CDP client

```javascript
const client = await page.target().createCDPSession();
// client 在整个脚本生命周期内保持，最后再 detach
```

## 截图规范

| 项目 | 要求 |
|------|------|
| 保存目录 | `/root/.openclaw/workspace/screenshots/`（必须在 workspace 内，`/tmp` 无法渲染） |
| 命名格式 | `{操作名}-{步骤序号}-{描述}.png` |
| 截图时机 | 操作前（初始状态）→ 操作中（弹窗/表单）→ 操作后（最终确认） |
| 水印清除 | 截图前执行 `.wm_div_id` 移除 |
| 弹窗清除 | 截图前关闭通知面板（`notify_bg` / `notify_body`） |

## 滚动后截图

需要截取页面下方内容时，先滚动目标元素到可视区域：

```javascript
await page.evaluate(() => {
  const el = document.querySelector('目标选择器');
  if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
});
await new Promise(r => setTimeout(r, 1000));
await screenshot(page, 'scrolled-view', client);
```

## 验证截图尺寸

```bash
identify /root/.openclaw/workspace/screenshots/xxx.png
# 期望输出: xxx.png PNG 1280x1024 ...
```
