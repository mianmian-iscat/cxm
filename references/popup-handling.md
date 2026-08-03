# 弹窗处理

## 通用弹窗关闭函数

页面加载后可能有多个弹窗遮挡内容（引导、通知、AI 助手、客服浮窗等）。操作前必须先关闭：

```javascript
async function closeAllPopups(page) {
  for (let round = 0; round < 5; round++) {
    await page.evaluate(() => {
      // 1. 点击所有"关闭"类按钮
      const closeTexts = ['关闭', '×', '✕', '我知道了', '知道了', '不再提示',
                          '关 闭', 'Close', '下一个', '完成'];
      Array.from(document.querySelectorAll('button, span, a, div')).forEach(btn => {
        const text = btn.innerText?.trim();
        if (text && closeTexts.includes(text) && btn.offsetParent !== null) {
          const rect = btn.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) btn.click();
        }
      });

      // 2. aria-label="Close"
      document.querySelectorAll('[aria-label="Close"], [aria-label="close"]')
        .forEach(el => { if (el.offsetParent) el.click(); });

      // 3. Dialog 关闭按钮（@alifd/next 组件）
      document.querySelectorAll('.next-dialog-close')
        .forEach(c => c.click());

      // 4. 右下角"重要消息"通知面板
      document.querySelectorAll(
        '[class*="notify_bg"], [class*="notify_body"], [class*="notify_container"]'
      ).forEach(el => el.style.display = 'none');

      // 5. 右下角 fixed 浮窗（客服/反馈等）
      Array.from(document.querySelectorAll('div')).forEach(el => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (style.position === 'fixed' && rect.right > 1100 &&
            rect.bottom > 800 && rect.width < 200) {
          el.style.display = 'none';
        }
      });

      // 6. 移除引导/水印
      document.querySelectorAll(
        '[class*="guide"], [class*="tour"], [class*="onboard"]'
      ).forEach(el => el.remove());
      document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
    });
    await new Promise(r => setTimeout(r, 500));
  }
}
```

## 遮挡检测与清除

操作按钮前，检测按钮是否被其他元素覆盖：

```javascript
async function clearOverlay(page, selector) {
  return await page.evaluate((sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return { ok: false, reason: 'not found' };
    const r = btn.getBoundingClientRect();
    let topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    let cleared = 0;
    while (topEl && !btn.contains(topEl) && topEl !== btn && cleared < 10) {
      topEl.style.display = 'none';
      cleared++;
      topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    }
    return { ok: true, cleared };
  }, selector);
}
```

## overlay / Dialog 强制清除

某些场景需要强制移除所有 overlay（如刷新页面后残留弹窗）：

```javascript
await page.evaluate(() => {
  document.querySelectorAll(
    '.next-overlay-wrapper, .next-dialog, .wind-slide-panel-wrapper'
  ).forEach(e => e.remove());
});
```

## 多步引导弹窗

某些页面有多步引导（Step 1 → Step 2 → ... → 完成），需要循环点击"下一个"直到关闭：

```javascript
for (let i = 0; i < 10; i++) {
  const clicked = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button, span'))
      .find(el => ['下一个', '关闭', '完成', '知道了'].includes(el.innerText?.trim())
                   && el.offsetParent);
    if (btn) { btn.click(); return true; }
    return false;
  });
  if (!clicked) break;
  await new Promise(r => setTimeout(r, 600));
}
```
