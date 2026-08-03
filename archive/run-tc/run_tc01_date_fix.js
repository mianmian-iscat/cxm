/**
 * TC01 修复版：正确操作日期选择器，确保日期参数传入 API
 * 使用坐标点击日历格子方式选日期
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const TS = new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);
const OUT = '/root/.openclaw/workspace/skills/web-automation/artifacts/xiaoer-adplacement-tc01-datefix-' + TS;
fs.mkdirSync(OUT + '/screenshots', { recursive: true });

async function shot(page, label) {
  const { data } = await page._client().send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const p = path.join(OUT, 'screenshots', label + '.png');
  fs.writeFileSync(p, Buffer.from(data, 'base64'));
  console.log('📸', label);
  return p;
}
async function clearWM(page) {
  await page.evaluate(() => document.querySelectorAll('.wm_div_id,[id^="wm_"]').forEach(e => e.remove()));
}
async function setReact(page, selector, value) {
  return page.evaluate((sel, val) => {
    const input = document.querySelector(sel);
    if (!input) return false;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, val);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }, selector, value);
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  let page = pages.find(p => p.url().includes('adPlacement'));
  if (!page) {
    page = await browser.newPage();
    await page.goto('https://pre-xiaoer.alibaba-inc.com/bzb/noone/product-batch-registration/adPlacement', { waitUntil: 'networkidle2', timeout: 30000 });
  }

  // 关闭弹窗
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('取 消') || b.innerText?.includes('取消'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 400));

  const cdp = await page.target().createCDPSession();
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });

  const reqBodies = [];
  const responses = {};
  cdp.on('Network.requestWillBeSent', ({ requestId, request }) => {
    if (request.url.includes('queryItemSuperDiscountActivity')) {
      reqBodies.push({ id: requestId, body: request.postData });
    }
  });
  cdp.on('Network.responseReceived', ({ requestId, response }) => {
    if (response.url.includes('queryItemSuperDiscountActivity')) responses[requestId] = response.url;
  });
  cdp.on('Network.loadingFinished', async ({ requestId }) => {
    if (responses[requestId]) {
      try {
        const { body } = await cdp.send('Network.getResponseBody', { requestId });
        responses[requestId] = { url: responses[requestId], body: JSON.parse(body) };
      } catch(e) {}
    }
  });

  // 重置
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('重置'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 700));
  await clearWM(page);
  await shot(page, '01-reset');

  // 方法：直接操作日期选择器的 input，通过 react setter 设置值
  // 先点击打开 picker
  await page.evaluate(() => {
    const picker = document.querySelector('.tbd-picker.tbd-picker-range');
    if (picker) picker.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await clearWM(page);
  await shot(page, '02-picker-panel');

  // 检查面板打开状态
  const panelOpen = await page.evaluate(() => {
    const p = document.querySelector('.tbd-picker-dropdown, .tbd-picker-panel-container');
    return p ? { found: true, text: p.innerText?.slice(0, 100) } : { found: false };
  });
  console.log('Panel:', JSON.stringify(panelOpen));

  // 找 4月26日 的日历格并点击（td[title="2026-04-26"]）
  const cell26 = await page.evaluate(() => {
    const cell = document.querySelector('td[title="2026-04-26"]');
    if (!cell) return null;
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width/2, y: rect.y + rect.height/2, text: cell.innerText?.trim() };
  });
  console.log('Cell 2026-04-26:', JSON.stringify(cell26));

  if (cell26 && cell26.x > 0) {
    // 点击 4月26日 作为开始日期
    await page.mouse.click(cell26.x, cell26.y);
    await new Promise(r => setTimeout(r, 400));
    await clearWM(page);
    await shot(page, '03-start-date-clicked');

    // 检查面板状态（选择开始日期后需要再选结束日期）
    const afterFirstClick = await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input[placeholder="选择日期"]'));
      return inputs.map((e, i) => ({ i, value: e.value }));
    });
    console.log('After first click:', JSON.stringify(afterFirstClick));

    // 选择结束日期：点击同一天（2026-04-26 到 2026-04-26，即等于那一天）
    // 或者选择今天（2026-04-29）作为结束
    const todayCell = await page.evaluate(() => {
      const today = document.querySelector('.tbd-picker-cell-today, td.tbd-picker-cell-today');
      if (today) {
        const rect = today.getBoundingClientRect();
        return { x: rect.x + rect.width/2, y: rect.y + rect.height/2, text: today.innerText?.trim() };
      }
      // 找 4月29日
      const cell29 = document.querySelector('td[title="2026-04-29"]');
      if (cell29) {
        const rect = cell29.getBoundingClientRect();
        return { x: rect.x + rect.width/2, y: rect.y + rect.height/2, text: cell29.innerText?.trim() };
      }
      return null;
    });
    console.log('Today cell:', JSON.stringify(todayCell));

    if (todayCell && todayCell.x > 0) {
      await page.mouse.click(todayCell.x, todayCell.y);
      await new Promise(r => setTimeout(r, 400));
      await clearWM(page);
      await shot(page, '04-end-date-clicked');
    } else {
      // 点 26 日再次点击作为结束
      await page.mouse.click(cell26.x, cell26.y);
      await new Promise(r => setTimeout(r, 400));
    }

    // 检查 picker 的值
    const pickerValues = await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input[placeholder="选择日期"]'));
      return inputs.map((e, i) => ({ i, value: e.value }));
    });
    console.log('Picker values:', JSON.stringify(pickerValues));
    await clearWM(page);
    await shot(page, '05-date-range-selected');
  } else {
    console.log('Cell 2026-04-26 not found or rect=(0,0)');
    // 记录当前日历内容
    const calText = await page.evaluate(() => {
      const p = document.querySelector('.tbd-picker-dropdown, .tbd-picker-panel-container');
      return p?.innerText?.slice(0, 300);
    });
    console.log('Calendar text:', calText);
    await shot(page, '03-no-cell-found');
    browser.disconnect();
    return;
  }

  // 搜索
  await page.evaluate(() => {
    const sb = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('搜'));
    if (sb) sb.click();
  });
  await new Promise(r => setTimeout(r, 4000));
  await clearWM(page);
  await shot(page, '06-search-result');

  // 检查请求参数
  console.log('\nRequest bodies:');
  reqBodies.forEach(r => {
    try { console.log(JSON.stringify(JSON.parse(r.body)?._bzb_data || r.body)); }
    catch(e) { console.log(r.body?.slice(0, 200)); }
  });

  // 分析结果
  const latestResp = Object.values(responses).find(r => r.body);
  const items = latestResp?.body?.data?.model?.items || [];
  const total = latestResp?.body?.data?.model?.totalCount || 0;
  console.log('\nTotal items:', total);

  const cutoff = new Date('2026-04-26T00:00:00+08:00');
  const itemTimes = items.map(i => ({
    itemId: i?.itemInfo?.itemId,
    title: i?.itemInfo?.title?.slice(0, 30),
    applyTime: i?.activityInfo?.applyTime,
    status: i?.activityInfo?.applyStatusDesc
  }));
  
  console.log('Items with applyTime:');
  itemTimes.forEach(i => console.log(' ', JSON.stringify(i)));

  const hasDateParam = reqBodies.some(r => {
    try { const d = JSON.parse(r.body); return d._bzb_data?.applyStartDate || d._bzb_data?.startTime || d._bzb_data?.applyDateStart; }
    catch(e) { return false; }
  });
  console.log('Has date param in request:', hasDateParam);

  const beforeCutoff = itemTimes.filter(i => {
    if (!i.applyTime) return false;
    return new Date(i.applyTime.replace(' ', 'T') + '+08:00') < cutoff;
  });
  console.log('Items before cutoff:', beforeCutoff.length);

  let pass, msg;
  if (!hasDateParam) {
    pass = false;
    msg = `❌ TC01 FAIL: 日期筛选参数未传入 API（请求体无日期字段），返回全量 ${total} 条`;
  } else if (total === 0) {
    pass = false;
    msg = `❌ TC01 FAIL: 搜索无结果`;
  } else if (beforeCutoff.length === 0) {
    pass = true;
    msg = `✅ TC01 PASS: 共 ${total} 条结果，所有商品报入时间 >= 2026-04-26`;
  } else {
    pass = false;
    msg = `❌ TC01 FAIL: 共 ${total} 条结果，其中 ${beforeCutoff.length} 条报入时间早于 2026-04-26`;
  }
  
  console.log('\n' + msg);
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ pass, message: msg, total, items: itemTimes.slice(0,10) }, null, 2));
  console.log('产物:', OUT);

  browser.disconnect();
})().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
