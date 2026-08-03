/**
 * 探索报名弹窗结构（简化版，操作已打开的页面）
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const OUTPUT_DIR = '/root/.openclaw/workspace/skills/web-automation/artifacts/explore-modal2-' + Date.now();
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function shot(page, label) {
  const { data } = await page._client().send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const p = path.join(OUTPUT_DIR, label + '.png');
  fs.writeFileSync(p, Buffer.from(data, 'base64'));
  console.log('Screenshot:', p);
}

async function clearWM(page) {
  await page.evaluate(() => document.querySelectorAll('.wm_div_id, [id^="wm_"]').forEach(el => el.remove()));
}

async function setReact(page, selector, value, index = 0) {
  await page.evaluate((sel, val, idx) => {
    const inputs = Array.from(document.querySelectorAll(sel));
    const input = inputs[idx];
    if (!input) throw new Error('No input: ' + sel + '[' + idx + ']');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, val);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, selector, value, index);
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  const page = pages.find(p => p.url().includes('adPlacement'));
  if (!page) { console.log('No adPlacement page!'); browser.disconnect(); return; }
  
  console.log('Found page:', page.url());
  await clearWM(page);
  await shot(page, '01-current');

  // 打印当前所有 input 框
  const inputs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('input')).map((el, i) => ({
      i, type: el.type, value: el.value, placeholder: el.placeholder,
      className: el.className.slice(0, 60)
    }))
  );
  console.log('Inputs:', JSON.stringify(inputs, null, 2));

  // 先重置
  const resetBtn = await page.$('button[class*="resetBtn"], button[class*="reset"]');
  if (resetBtn) { await resetBtn.click(); await new Promise(r => setTimeout(r, 600)); }

  // 填入供给商品ID（第一个input）
  await setReact(page, "input[type='text']", '1039806673038', 0);
  await new Promise(r => setTimeout(r, 300));
  
  // 检查填入后的值
  const vals = await page.evaluate(() =>
    Array.from(document.querySelectorAll("input[type='text']")).map((el,i) => ({ i, value: el.value, placeholder: el.placeholder }))
  );
  console.log('Values after fill:', JSON.stringify(vals));

  // 点击搜索
  const searchBtnText = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const sb = btns.find(b => b.innerText?.includes('搜'));
    return sb ? { text: sb.innerText, className: sb.className.slice(0,80) } : null;
  });
  console.log('Search button:', JSON.stringify(searchBtnText));
  
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const sb = btns.find(b => b.innerText?.includes('搜'));
    if (sb) sb.click();
  });
  await new Promise(r => setTimeout(r, 3000));
  await clearWM(page);
  await shot(page, '02-search-result');

  // 打印搜索结果
  const tableInfo = await page.evaluate(() => {
    const rows = document.querySelectorAll('[class*="ant-table-row"], tr');
    return { rowCount: rows.length, firstRowText: rows[0]?.innerText?.slice(0, 200) };
  });
  console.log('Table:', JSON.stringify(tableInfo));

  // 找并点击"报名"按钮
  const applyInfo = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    return btns.filter(b => b.innerText?.trim() === '报名' || b.innerText?.trim().includes('报名')).map(b => ({
      text: b.innerText.trim(),
      disabled: b.disabled,
      className: b.className.slice(0, 80),
      rect: b.getBoundingClientRect()
    }));
  });
  console.log('Apply buttons:', JSON.stringify(applyInfo, null, 2));

  if (applyInfo.length > 0 && !applyInfo[0].disabled) {
    const rect = applyInfo[0].rect;
    await page.mouse.click(rect.x + rect.width/2, rect.y + rect.height/2);
    await new Promise(r => setTimeout(r, 2000));
    await clearWM(page);
    await shot(page, '03-modal-opened');

    // 分析弹窗
    const modal = await page.evaluate(() => {
      const m = document.querySelector('.ant-modal-content, [role="dialog"], [class*="Modal"]');
      if (!m) return { found: false, bodyHTML: document.body.innerHTML.slice(0, 500) };
      
      const inputs = Array.from(m.querySelectorAll('input')).map((el, i) => ({
        i, type: el.type, value: el.value, placeholder: el.placeholder,
        className: el.className.slice(0, 100), name: el.name
      }));
      const labels = Array.from(m.querySelectorAll('.ant-form-item-label label, label')).map(el => ({
        text: el.innerText?.trim()
      })).filter(l => l.text);
      const selects = Array.from(m.querySelectorAll('.ant-select-selector')).map(el => ({
        text: el.innerText?.trim().slice(0, 50),
        className: el.className.slice(0, 60)
      }));
      const buttons = Array.from(m.querySelectorAll('button')).map(el => ({
        text: el.innerText.trim(), className: el.className.slice(0, 60)
      }));
      
      return {
        found: true,
        title: m.querySelector('.ant-modal-title, [class*="title"]')?.innerText,
        fullText: m.innerText?.slice(0, 800),
        inputs, labels, selects, buttons
      };
    });
    console.log('Modal:', JSON.stringify(modal, null, 2));
    fs.writeFileSync(path.join(OUTPUT_DIR, 'modal.json'), JSON.stringify(modal, null, 2));
  }

  browser.disconnect();
  console.log('Done:', OUTPUT_DIR);
})().catch(e => { console.error(e.message); process.exit(1); });
