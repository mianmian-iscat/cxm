/**
 * 探索 SKU维度报名 Tab 的结构
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const OUTPUT_DIR = '/root/.openclaw/workspace/skills/web-automation/artifacts/explore-sku-tab-' + Date.now();
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function shot(page, label) {
  const { data } = await page._client().send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(path.join(OUTPUT_DIR, label + '.png'), Buffer.from(data, 'base64'));
  console.log('Screenshot:', label);
}

async function clearWM(page) {
  await page.evaluate(() => document.querySelectorAll('.wm_div_id, [id^="wm_"]').forEach(el => el.remove()));
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  const page = pages.find(p => p.url().includes('adPlacement'));
  if (!page) { console.log('No adPlacement page!'); browser.disconnect(); return; }

  await clearWM(page);
  await shot(page, '00-before');

  // 检查弹窗是否还在
  const modalVisible = await page.evaluate(() => {
    const m = document.querySelector('.tbd-modal-content, .ant-modal-content, [role="dialog"]');
    return m && m.offsetParent !== null ? m.innerText?.slice(0, 200) : null;
  });
  console.log('Modal visible:', modalVisible);

  if (!modalVisible) {
    // 弹窗关闭了，需要重新打开
    console.log('Modal closed, reopening...');
    const clicked = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.innerText?.trim() === '立即报名');
      if (btn) { btn.click(); return true; }
      return false;
    });
    console.log('Re-clicked:', clicked);
    await new Promise(r => setTimeout(r, 2000));
    await clearWM(page);
    await shot(page, '01-modal-reopened');
  }

  // 点击"SKU维度报名" Tab
  const tabClicked = await page.evaluate(() => {
    // 找弹窗内的 tabs
    const tabs = Array.from(document.querySelectorAll('.tbd-tabs-tab, .ant-tabs-tab, [role="tab"]'));
    console.log('Tabs found:', tabs.length, tabs.map(t => t.innerText?.trim()));
    const skuTab = tabs.find(t => t.innerText?.includes('SKU维度'));
    if (skuTab) { skuTab.click(); return skuTab.innerText?.trim(); }
    return null;
  });
  console.log('SKU tab clicked:', tabClicked);
  await new Promise(r => setTimeout(r, 1000));
  await clearWM(page);
  await shot(page, '02-sku-tab');

  // 分析 SKU 维度 Tab 内容
  const skuTabContent = await page.evaluate(() => {
    const m = document.querySelector('.tbd-modal-content, .ant-modal-content, [role="dialog"]');
    if (!m) return { found: false };
    
    const inputs = Array.from(m.querySelectorAll('input')).map((el, i) => ({
      i, type: el.type, value: el.value, placeholder: el.placeholder,
      className: el.className.slice(0, 100), id: el.id
    }));
    
    const tables = Array.from(m.querySelectorAll('table, [class*="table"]')).slice(0, 3).map(el => ({
      className: el.className.slice(0, 80),
      text: el.innerText?.slice(0, 300)
    }));
    
    const fullText = m.innerText?.slice(0, 1500);
    
    return { found: true, fullText, inputs, tables };
  });
  
  console.log('SKU tab content:', JSON.stringify(skuTabContent, null, 2));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'sku_tab.json'), JSON.stringify(skuTabContent, null, 2));

  browser.disconnect();
  console.log('Done:', OUTPUT_DIR);
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
