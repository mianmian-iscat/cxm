/**
 * TC01 v3: 报入时间 2026-04-26 ~ 2026-04-29（今天），验证结果
 * 起始时间和终止时间不能是同一天（都是 00:00:00 时区间为零）
 */
const puppeteerPath = '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core';
const puppeteer = require(puppeteerPath);
const fs = require('fs');
const path = require('path');

const CDP_URL = 'http://127.0.0.1:9222';
const TS = new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);
const OUT = '/root/.openclaw/workspace/skills/web-automation/artifacts/xiaoer-adplacement-tc01-v3-' + TS;
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

(async () => {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  let page = pages.find(p => p.url().includes('adPlacement'));

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
  cdp.on('Network.requestWillBeSent', ({ request }) => {
    if (request.url.includes('queryItemSuperDiscountActivity')) reqBodies.push(request.postData);
  });
  cdp.on('Network.responseReceived', ({ requestId, response }) => {
    if (response.url.includes('queryItemSuperDiscountActivity')) responses[requestId] = response.url;
  });
  cdp.on('Network.loadingFinished', async ({ requestId }) => {
    if (responses[requestId]) {
      try {
        const { body } = await cdp.send('Network.getResponseBody', { requestId });
        responses[requestId] = JSON.parse(body);
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

  // 打开日期选择器
  await page.evaluate(() => {
    const picker = document.querySelector('.tbd-picker.tbd-picker-range');
    if (picker) picker.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await clearWM(page);
  await shot(page, '02-picker-opened');

  // 点击 4月26日 作为开始日期
  const cell26 = await page.evaluate(() => {
    const cell = document.querySelector('td[title="2026-04-26"]');
    if (!cell) return null;
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
  });
  console.log('Cell 26:', JSON.stringify(cell26));
  if (cell26?.x > 0) {
    await page.mouse.click(cell26.x, cell26.y);
    await new Promise(r => setTimeout(r, 300));
  }

  await clearWM(page);
  await shot(page, '03-start-date-selected');

  // 点击 4月29日（今天）作为结束日期
  const cell29 = await page.evaluate(() => {
    const cell = document.querySelector('td[title="2026-04-29"]');
    if (!cell) return null;
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
  });
  console.log('Cell 29:', JSON.stringify(cell29));
  if (cell29?.x > 0) {
    await page.mouse.click(cell29.x, cell29.y);
    await new Promise(r => setTimeout(r, 300));
  }

  // 检查选中的日期值
  const pickerVals = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input[placeholder="选择日期"]'));
    return inputs.map((e, i) => ({ i, value: e.value }));
  });
  console.log('Picker values:', JSON.stringify(pickerVals));
  await clearWM(page);
  await shot(page, '04-date-range-set');

  // 搜索
  await page.evaluate(() => {
    const sb = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('搜'));
    if (sb) sb.click();
  });
  await new Promise(r => setTimeout(r, 4000));
  await clearWM(page);
  await shot(page, '05-search-result');

  // 分析请求
  console.log('\nRequest bodies:');
  reqBodies.forEach(b => {
    try { console.log(JSON.stringify(JSON.parse(b)?._bzb_data)); }
    catch(e) { console.log(b?.slice(0, 200)); }
  });

  // 取最后一次（点击搜索后触发的）queryItemSuperDiscountActivity 响应
  const latestResp = Object.values(responses).filter(r => r?.data?.model).pop();
  const items = latestResp?.data?.model?.items || [];
  const total = latestResp?.data?.model?.totalCount || 0;
  console.log('\nTotal:', total);

  const cutoff = new Date('2026-04-26T00:00:00+08:00');
  const itemTimes = items.map(i => ({
    itemId: i?.itemInfo?.itemId,
    title: i?.itemInfo?.title?.slice(0, 30),
    applyTime: i?.activityInfo?.applyTime,
    status: i?.activityInfo?.applyStatusDesc
  }));
  console.log('Sample items:');
  itemTimes.forEach(i => console.log(' ', JSON.stringify(i)));

  const withTime = itemTimes.filter(i => i.applyTime);
  const beforeCutoff = withTime.filter(i => new Date(i.applyTime.replace(' ', 'T') + '+08:00') < cutoff);
  console.log('Items with time:', withTime.length, '| Before cutoff:', beforeCutoff.length);

  // 取最后一条请求（点击搜索后发出的）
  const lastReqBody = reqBodies[reqBodies.length - 1];
  let lastReqData = {};
  try { lastReqData = JSON.parse(lastReqBody)?._bzb_data || {}; } catch(e) {}
  console.log('最后一次搜索请求参数:', JSON.stringify(lastReqData));
  const hasDateParam = !!(lastReqData.applyStartDate);

  let pass, msg;
  if (!hasDateParam) {
    pass = false;
    msg = `❌ TC01 FAIL: 日期参数未传入 API，返回全量 ${total} 条`;
  } else if (total === 0) {
    pass = false;
    msg = `❌ TC01 FAIL: 无搜索结果`;
  } else if (beforeCutoff.length === 0) {
    pass = true;
    msg = `✅ TC01 PASS: 共 ${total} 条结果（含报入时间字段的 ${withTime.length} 条），全部报入时间 >= 2026-04-26`;
  } else {
    pass = false;
    msg = `❌ TC01 FAIL: 共 ${total} 条，其中 ${beforeCutoff.length} 条报入时间早于 2026-04-26: ${JSON.stringify(beforeCutoff)}`;
  }

  console.log('\n' + msg);
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ pass, message: msg, total, hasDateParam, pickerVals, items: itemTimes }, null, 2));
  console.log('产物:', OUT);
  browser.disconnect();
})().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
