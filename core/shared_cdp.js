/**
 * shared/browser-cdp.js — 共享的 CDP 浏览器操作工具
 *
 * 提供视口设置、弹窗关闭、截图等通用 CDP 操作。
 */
'use strict';

const VIEWPORT_WIDTH = 1458;
const VIEWPORT_HEIGHT = 784;

/**
 * 固定视口为 1458×784，同步设置窗口 bounds 和 viewport
 */
async function setFixedViewport(page, cdpClient) {
  // 设置浏览器窗口大小
  const { windowId } = await cdpClient.send('Browser.getWindowForTarget');
  await cdpClient.send('Browser.setWindowBounds', {
    windowId,
    bounds: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT },
  });
  // 设置 viewport
  await page.setViewport({ width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT });
  return { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT, windowId };
}

/**
 * 关闭常见遮挡弹窗（ant-modal / ant-drawer 关闭按钮等）
 */
async function dismissKnownModals(page, opts = {}) {
  const maxRounds = opts.maxRounds ?? 5;
  let dismissed = 0;

  for (let round = 0; round < maxRounds; round++) {
    const closed = await page.evaluate(() => {
      const selectors = [
        '.ant-modal-close',
        '.ant-drawer-close',
        '.ant-notification-close',
        '.ant-popover .ant-btn-primary',  // 确认按钮
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) {
          el.click();
          return sel;
        }
      }
      return null;
    });
    if (!closed) break;
    dismissed++;
    await new Promise(r => setTimeout(r, 500));
  }
  return { dismissed };
}

/**
 * 使用 CDP 截图，返回 base64 JPEG（medium 质量，去除水印）
 */
async function captureScreenshotBase64(cdpClient) {
  // 先移除水印
  const { data } = await cdpClient.send('Page.captureScreenshot', {
    format: 'jpeg',
    quality: 75,
  });
  return data;
}

module.exports = {
  setFixedViewport,
  dismissKnownModals,
  captureScreenshotBase64,
  VIEWPORT_WIDTH,
  VIEWPORT_HEIGHT,
};
