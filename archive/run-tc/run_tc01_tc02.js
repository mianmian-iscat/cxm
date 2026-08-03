/**
 * 执行 TC01 和 TC02 测试用例
 * TC01: 搜索平台商品ID 1039806673038
 * TC02: 搜索商品标题 "测试商品请不要拍"
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const TS = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const OUTPUT_DIR = '/root/.openclaw/workspace/skills/web-automation/artifacts/xiaoer-adplacement-tc01-tc02-' + TS;
fs.mkdirSync(OUTPUT_DIR + '/screenshots', { recursive: true });

const results = { tc01: {}, tc02: {} };
const capturedRequests = [];

async function shot(page, label) {
  const { data } = await page._client().send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const p = path.join(OUTPUT_DIR, 'screenshots', label + '.png');
  fs.writeFileSync(p, Buffer.from(data, 'base64'));
  return p;
}

async function clearWM(page) {
  await page.evaluate(() => document.querySelectorAll('.wm_div_id, [id^="wm_"]').forEach(el => el.remove()));
}

async function setReact(page, selector, value) {
  await page.evaluate((sel, val) => {
    const input = document.querySelector(sel);
    if (!input) throw new Error('No input: ' + sel);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, val);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, selector, value);
}

async function clickSearch(page) {
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const sb = btns.find(b => b.innerText?.trim().includes('搜'));
    if (sb) sb.click();
  });
}

async function doReset(page) {
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('重置'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 600));
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  
  let page = pages.find(p => p.url().includes('adPlacement'));
  if (!page) {
    page = await browser.newPage();
    await page.goto('https://pre-xiaoer.alibaba-inc.com/bzb/noone/product-batch-registration/adPlacement', { waitUntil: 'networkidle2', timeout: 30000 });
  }

  // 关闭可能打开的弹窗
  await page.evaluate(() => {
    const cancelBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('取 消') || b.innerText?.includes('取消'));
    if (cancelBtn) cancelBtn.click();
    const closeBtn = document.querySelector('.tbd-drawer-close, .ant-modal-close');
    if (closeBtn) closeBtn.click();
  });
  await new Promise(r => setTimeout(r, 500));

  // 设置网络监听
  const cdpClient = await page.target().createCDPSession();
  await cdpClient.send('Network.enable');
  await cdpClient.send('Network.setCacheDisabled', { cacheDisabled: true });
  
  const responseMap = {};
  cdpClient.on('Network.responseReceived', ({ requestId, response }) => {
    if (response.url.includes('queryItemSuperDiscountActivity')) {
      responseMap[requestId] = { url: response.url, status: response.status };
    }
  });
  cdpClient.on('Network.loadingFinished', async ({ requestId }) => {
    if (responseMap[requestId]) {
      try {
        const { body } = await cdpClient.send('Network.getResponseBody', { requestId });
        responseMap[requestId].body = JSON.parse(body);
      } catch(e) {}
    }
  });

  // ============ TC01: 搜索平台商品ID 1039806673038 ============
  console.log('\n=== TC01: 搜索平台商品ID 1039806673038 ===');
  
  await clearWM(page);
  await doReset(page);
  
  // 清空之前监听的数据
  Object.keys(responseMap).forEach(k => delete responseMap[k]);
  
  // 填入商品ID（用标题/商品id输入框）
  await setReact(page, "input[placeholder*='标题']", '1039806673038');
  await new Promise(r => setTimeout(r, 300));
  
  const filledValue = await page.evaluate(() => {
    const input = document.querySelector("input[placeholder*='标题']");
    return input ? input.value : null;
  });
  console.log('TC01 - Input filled with:', filledValue);
  
  await clickSearch(page);
  await new Promise(r => setTimeout(r, 3500));
  await clearWM(page);
  const tc01Screenshot = await shot(page, 'tc01-search-result');
  console.log('TC01 - Screenshot:', tc01Screenshot);

  // 等待 API 响应
  await new Promise(r => setTimeout(r, 500));
  
  // 分析结果
  const tc01ApiResponse = Object.values(responseMap).find(r => r.body);
  console.log('TC01 - API responses:', Object.keys(responseMap).length);
  
  let tc01Pass = false;
  let tc01Message = '';
  let tc01ItemCount = 0;
  let tc01Items = [];
  
  if (tc01ApiResponse && tc01ApiResponse.body) {
    const model = tc01ApiResponse.body?.data?.model;
    tc01Items = model?.items || [];
    tc01ItemCount = model?.totalCount || 0;
    
    // 检查 request 中是否有搜索参数
    const reqData = tc01ApiResponse.body;
    console.log('TC01 - Total count:', tc01ItemCount);
    console.log('TC01 - Items sample:', JSON.stringify(tc01Items.slice(0,2).map(i => ({
      itemId: i?.itemInfo?.itemId,
      platformItemId: i?.itemInfo?.platformItemId,
      title: i?.itemInfo?.title?.slice(0, 40)
    })), null, 2));
    
    // 验证：搜索结果中含指定商品ID
    const found = tc01Items.some(item => {
      const info = item?.itemInfo || {};
      return String(info.itemId) === '1039806673038' || String(info.platformItemId) === '1039806673038';
    });
    
    if (found) {
      tc01Pass = true;
      tc01Message = `✅ TC01 PASS: 搜索结果中找到商品ID 1039806673038，共 ${tc01ItemCount} 条`;
    } else if (tc01ItemCount > 0) {
      tc01Pass = false;
      tc01Message = `❌ TC01 FAIL: 搜索返回 ${tc01ItemCount} 条结果，但未找到商品ID 1039806673038`;
    } else {
      tc01Pass = false;
      tc01Message = `❌ TC01 FAIL: 搜索无结果（totalCount=0 或无匹配）`;
    }
  } else {
    // 检查页面文字
    const pageText = await page.evaluate(() => document.body.innerText.slice(0, 500));
    console.log('TC01 - Page text (no API):', pageText);
    const hasId = pageText.includes('1039806673038');
    tc01Pass = hasId;
    tc01Message = hasId ? `✅ TC01 PASS: 页面中找到商品ID 1039806673038` : `❌ TC01 FAIL: 未找到API响应且页面中无商品ID`;
  }
  
  results.tc01 = { pass: tc01Pass, message: tc01Message, items: tc01Items.slice(0, 3) };
  console.log(tc01Message);

  // ============ TC02: 搜索商品标题 "测试商品请不要拍" ============
  console.log('\n=== TC02: 搜索商品标题 "测试商品请不要拍" ===');
  
  Object.keys(responseMap).forEach(k => delete responseMap[k]);
  await doReset(page);
  
  await setReact(page, "input[placeholder*='标题']", '测试商品请不要拍');
  await new Promise(r => setTimeout(r, 300));
  
  const tc02FilledValue = await page.evaluate(() => {
    const input = document.querySelector("input[placeholder*='标题']");
    return input ? input.value : null;
  });
  console.log('TC02 - Input filled with:', tc02FilledValue);
  
  await clickSearch(page);
  await new Promise(r => setTimeout(r, 3500));
  await clearWM(page);
  const tc02Screenshot = await shot(page, 'tc02-search-result');
  console.log('TC02 - Screenshot:', tc02Screenshot);

  await new Promise(r => setTimeout(r, 500));
  
  const tc02ApiResponse = Object.values(responseMap).find(r => r.body);
  
  let tc02Pass = false;
  let tc02Message = '';
  let tc02ItemCount = 0;
  let tc02Items = [];
  
  if (tc02ApiResponse && tc02ApiResponse.body) {
    const model = tc02ApiResponse.body?.data?.model;
    tc02Items = model?.items || [];
    tc02ItemCount = model?.totalCount || 0;
    
    console.log('TC02 - Total count:', tc02ItemCount);
    console.log('TC02 - Items:', JSON.stringify(tc02Items.slice(0, 3).map(i => ({
      itemId: i?.itemInfo?.itemId,
      title: i?.itemInfo?.title?.slice(0, 50)
    })), null, 2));
    
    // 验证：所有结果标题都含关键词
    const allMatch = tc02Items.every(item => {
      const title = item?.itemInfo?.title || '';
      return title.includes('测试商品请不要拍');
    });
    const hasResults = tc02ItemCount > 0;
    
    if (hasResults && allMatch) {
      tc02Pass = true;
      tc02Message = `✅ TC02 PASS: 搜索返回 ${tc02ItemCount} 条结果，标题均含"测试商品请不要拍"`;
    } else if (hasResults && !allMatch) {
      tc02Pass = false;
      tc02Message = `⚠️ TC02 PARTIAL: 搜索返回 ${tc02ItemCount} 条结果，但部分标题不含关键词`;
    } else {
      tc02Pass = false;
      tc02Message = `❌ TC02 FAIL: 搜索无结果`;
    }
  } else {
    const pageText = await page.evaluate(() => document.body.innerText.slice(0, 500));
    const hasTitle = pageText.includes('测试商品请不要拍');
    tc02Pass = hasTitle;
    tc02Message = hasTitle ? `✅ TC02 PASS (页面验证): 找到含"测试商品请不要拍"的商品` : `❌ TC02 FAIL: 无API响应且页面无结果`;
  }
  
  results.tc02 = { pass: tc02Pass, message: tc02Message, items: tc02Items.slice(0, 3) };
  console.log(tc02Message);

  // 保存结果
  const report = {
    timestamp: new Date().toISOString(),
    tc01: results.tc01,
    tc02: results.tc02,
    screenshotDir: OUTPUT_DIR + '/screenshots'
  };
  fs.writeFileSync(path.join(OUTPUT_DIR, 'report.json'), JSON.stringify(report, null, 2));
  
  console.log('\n=== 测试完成 ===');
  console.log(results.tc01.message);
  console.log(results.tc02.message);
  console.log('产物目录:', OUTPUT_DIR);

  browser.disconnect();
})().catch(e => { console.error('Fatal:', e); process.exit(1); });
