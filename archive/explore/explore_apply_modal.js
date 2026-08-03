/**
 * 探索广告位报名弹窗结构
 * 搜索商品ID 1039806673038，点击报名按钮，截图并分析弹窗结构
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const OUTPUT_DIR = path.join(__dirname, 'artifacts', 'explore-apply-modal-' + Date.now());
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function screenshot(page, label) {
  const { data } = await page._client().send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const p = path.join(OUTPUT_DIR, label + '.png');
  fs.writeFileSync(p, Buffer.from(data, 'base64'));
  console.log('Screenshot:', p);
}

async function clearWatermark(page) {
  await page.evaluate(() => {
    document.querySelectorAll('.wm_div_id, [id^="wm_"]').forEach(el => el.remove());
  });
}

async function setReactValue(page, selector, value, index = 0) {
  await page.evaluate((sel, val, idx) => {
    const inputs = Array.from(document.querySelectorAll(sel));
    const input = inputs[idx];
    if (!input) throw new Error(`No input found: ${sel}[${idx}]`);
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeInputValueSetter.call(input, val);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, selector, value, index);
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  
  let page = pages.find(p => p.url().includes('pre-xiaoer.alibaba-inc.com'));
  if (!page) {
    page = await browser.newPage();
    await page.goto('https://pre-xiaoer.alibaba-inc.com/bzb/noone/product-batch-registration/adPlacement', { waitUntil: 'networkidle2', timeout: 30000 });
  }

  // 设置视窗
  const client = await page.target().createCDPSession();
  try {
    const { windowId } = await client.send('Browser.getWindowForTarget');
    await client.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'maximized' } });
    await new Promise(r => setTimeout(r, 300));
    const { bounds } = await client.send('Browser.getWindowBounds', { windowId });
    await page.setViewport({ width: bounds.width, height: bounds.height, deviceScaleFactor: 1 });
  } catch(e) { console.log('Window setup:', e.message); }

  await clearWatermark(page);
  await screenshot(page, '01-initial');

  // Step 1: 重置
  const resetBtn = await page.$('button[class*="resetBtn"]');
  if (resetBtn) { await resetBtn.click(); await new Promise(r => setTimeout(r, 500)); }

  // Step 2: 填入商品ID
  await setReactValue(page, "input[type='text']", '1039806673038', 0);
  await new Promise(r => setTimeout(r, 500));
  await screenshot(page, '02-filled-id');

  // 打印输入框当前值
  const inputValues = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("input[type='text']")).map((el, i) => ({
      index: i,
      value: el.value,
      placeholder: el.placeholder,
      className: el.className.slice(0, 80)
    }));
  });
  console.log('Input values after fill:', JSON.stringify(inputValues, null, 2));

  // Step 3: 点击搜索
  const searchBtn = await page.$('button[class*="searchBtn"]');
  if (!searchBtn) {
    // fallback: 找包含"搜 索"文字的按钮
    const btns = await page.$$('button');
    for (const btn of btns) {
      const text = await page.evaluate(el => el.innerText, btn);
      if (text.includes('搜')) { await btn.click(); break; }
    }
  } else {
    await searchBtn.click();
  }
  
  await new Promise(r => setTimeout(r, 3000));
  await clearWatermark(page);
  await screenshot(page, '03-search-result');

  // 获取表格内容
  const tableText = await page.evaluate(() => {
    const table = document.querySelector('.ant-table-wrapper, [class*="tableContainer"]');
    return table ? table.innerText.slice(0, 1000) : '(no table found)';
  });
  console.log('Table content:', tableText);

  // Step 4: 找"报名"按钮并点击
  await clearWatermark(page);
  const applyBtns = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button, a'));
    return btns.filter(el => el.innerText?.includes('报名') && !el.innerText?.includes('取消')).map(el => ({
      text: el.innerText.trim(),
      className: el.className.slice(0, 80),
      rect: el.getBoundingClientRect()
    }));
  });
  console.log('Apply buttons:', JSON.stringify(applyBtns, null, 2));

  // 点击第一个"报名"按钮
  const applyBtn = await page.evaluateHandle(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    return btns.find(el => el.innerText?.trim() === '报名' || el.innerText?.trim() === '立即报名');
  });
  if (applyBtn && applyBtn.asElement()) {
    await applyBtn.asElement().click();
    await new Promise(r => setTimeout(r, 1500));
    await clearWatermark(page);
    await screenshot(page, '04-after-click-apply');

    // 分析弹窗结构
    const modalInfo = await page.evaluate(() => {
      const modal = document.querySelector('.ant-modal, [role="dialog"], [class*="modal"]');
      if (!modal) return { found: false };
      
      const inputs = Array.from(modal.querySelectorAll('input')).map((el, i) => ({
        index: i,
        type: el.type,
        value: el.value,
        placeholder: el.placeholder,
        className: el.className.slice(0, 100),
        name: el.name
      }));
      
      const labels = Array.from(modal.querySelectorAll('label, .ant-form-item-label, [class*="label"]')).map(el => ({
        text: el.innerText?.trim(),
        forAttr: el.htmlFor
      })).filter(l => l.text);
      
      const selects = Array.from(modal.querySelectorAll('.ant-select, [class*="select"]')).map(el => ({
        className: el.className.slice(0, 100),
        innerText: el.innerText?.trim().slice(0, 50)
      }));
      
      const buttons = Array.from(modal.querySelectorAll('button')).map(el => ({
        text: el.innerText?.trim(),
        className: el.className.slice(0, 80)
      }));
      
      return {
        found: true,
        modalText: modal.innerText?.slice(0, 500),
        inputs,
        labels,
        selects,
        buttons,
        outerHTML: modal.outerHTML.slice(0, 2000)
      };
    });
    
    console.log('Modal info:', JSON.stringify(modalInfo, null, 2));
    fs.writeFileSync(path.join(OUTPUT_DIR, 'modal_info.json'), JSON.stringify(modalInfo, null, 2));
  } else {
    console.log('No apply button found!');
    // 截图整个页面看看
    await screenshot(page, '04-no-apply-btn');
  }

  browser.disconnect();
  console.log('Done! Output dir:', OUTPUT_DIR);
})().catch(e => { console.error('Error:', e); process.exit(1); });
