/**
 * 探索报名弹窗结构 v3 - 修复坐标点击问题，直接用 evaluate click
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const OUTPUT_DIR = '/root/.openclaw/workspace/skills/web-automation/artifacts/explore-modal3-' + Date.now();
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
  
  // 点击"立即报名"按钮
  const clicked = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const btn = btns.find(b => b.innerText?.trim() === '立即报名');
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log('Clicked apply:', clicked);
  
  await new Promise(r => setTimeout(r, 2000));
  await clearWM(page);
  await shot(page, '01-after-click-apply');

  // 分析弹窗
  const modal = await page.evaluate(() => {
    // 找所有可能的弹窗
    const selectors = [
      '.ant-modal-content',
      '[role="dialog"]',
      '.tbd-modal-content',
      '[class*="Modal"]',
      '[class*="modal"]',
      '[class*="dialog"]',
      '.ant-drawer-content'
    ];
    let m = null;
    for (const sel of selectors) {
      m = document.querySelector(sel);
      if (m && m.offsetParent !== null) break;
      m = null;
    }
    
    if (!m) {
      // 找所有 z-index 较高的元素
      const allEls = Array.from(document.querySelectorAll('*'));
      const highZ = allEls.filter(el => {
        const style = window.getComputedStyle(el);
        return parseInt(style.zIndex) > 100 && el.offsetParent !== null;
      }).slice(0, 5);
      return { 
        found: false, 
        highZElements: highZ.map(el => ({
          tag: el.tagName, 
          className: el.className.slice(0, 80),
          text: el.innerText?.slice(0, 100)
        }))
      };
    }
    
    const inputs = Array.from(m.querySelectorAll('input')).map((el, i) => ({
      i, type: el.type, value: el.value, placeholder: el.placeholder,
      className: el.className.slice(0, 100), name: el.name,
      id: el.id
    }));
    const labels = Array.from(m.querySelectorAll('label, [class*="label"]')).map(el => ({
      text: el.innerText?.trim().slice(0, 50),
      forAttr: el.htmlFor
    })).filter(l => l.text && l.text.length > 0);
    const selects = Array.from(m.querySelectorAll('.ant-select, .tbd-select, [class*="select"]:not(input)')).slice(0, 10).map(el => ({
      text: el.innerText?.trim().slice(0, 60),
      className: el.className.slice(0, 80)
    }));
    const buttons = Array.from(m.querySelectorAll('button')).map(el => ({
      text: el.innerText.trim(), 
      className: el.className.slice(0, 80),
      disabled: el.disabled
    }));
    
    return {
      found: true,
      selector: m.tagName + '.' + m.className.trim().split(' ')[0],
      title: m.querySelector('[class*="title"], .ant-modal-title, .tbd-modal-title')?.innerText?.trim(),
      fullText: m.innerText?.slice(0, 1000),
      inputs, labels, selects, buttons,
      html: m.outerHTML.slice(0, 3000)
    };
  });
  
  console.log('Modal found:', modal.found);
  if (modal.found) {
    console.log('Title:', modal.title);
    console.log('Full text:', modal.fullText);
    console.log('Inputs:', JSON.stringify(modal.inputs, null, 2));
    console.log('Labels:', JSON.stringify(modal.labels, null, 2));
    console.log('Selects:', JSON.stringify(modal.selects, null, 2));
    console.log('Buttons:', JSON.stringify(modal.buttons, null, 2));
  } else {
    console.log('High Z elements:', JSON.stringify(modal.highZElements, null, 2));
    // 打印整个 body 找弹窗
    const bodyInfo = await page.evaluate(() => {
      return document.body.innerHTML.slice(0, 2000);
    });
    console.log('Body snippet:', bodyInfo);
  }
  
  fs.writeFileSync(path.join(OUTPUT_DIR, 'modal.json'), JSON.stringify(modal, null, 2));
  
  browser.disconnect();
  console.log('Done:', OUTPUT_DIR);
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
