#!/usr/bin/env node
/**
 * 点击运行类型下拉箭头，选择选项，提交运行
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ss(page, name) {
  const fp = path.join(SS_DIR, `dd-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
}

async function main() {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  // 1. 导航 + 打开试运行弹窗
  console.log('1. 打开链路详情 + 试运行弹窗...');
  await page.goto('https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180', {
    waitUntil: 'networkidle2', timeout: 30000
  });
  await sleep(3000);

  const runBtnClicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '试运行' && b.offsetHeight > 0);
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log(`  试运行: ${runBtnClicked}`);
  await sleep(2000);

  // 2. 上传 Excel（用正确的4列模板）
  console.log('2. 构造并上传测试数据...');
  const testDataPath = '/tmp/f88-test-data-v2.xlsx';
  const { execSync } = require('child_process');
  execSync(`python3 -c "
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
# 链路起点入参必填字段
ws.append(['seller_id','seed_image_url','tao_cate','item_id'])
ws.append(['2219635649153','https://img.alicdn.com/imgextra/i1/O1CN01Z5paLz1O4SsHjYjJN_!!6000000001652-0-tps-800-800.jpg','女装','1044587480343'])
wb.save('${testDataPath}')
print('OK')
" 2>/dev/null`);
  console.log(`  文件: ${testDataPath}, 大小: ${fs.statSync(testDataPath).size} bytes`);
  const fileInput = await page.$('input[type="file"]');
  if (fileInput) {
    await fileInput.uploadFile(testDataPath);
    await sleep(2000);
    console.log('  ✅ 已上传');
  }

  // 3. 填写任务名称
  console.log('3. 填写任务名称...');
  const nameInput = await page.$('input[placeholder="请输入任务名称"]');
  if (nameInput) {
    await nameInput.click({ clickCount: 3 });
    await nameInput.type(`回归测试_${Date.now()}`);
    console.log('  ✅ 已填写');
  }
  await ss(page, 'before-dropdown');

  // 4. 点击运行类型的下拉箭头
  console.log('4. 点击运行类型下拉箭头...');
  
  // 方法：找到"运行类型"相关的 ant-select，点击其 arrow
  const arrowClicked = await page.evaluate(() => {
    // 遍历所有 ant-select，找到包含"请选择运行类型"placeholder的
    const selects = document.querySelectorAll('.ant-select');
    for (const sel of selects) {
      const ph = sel.querySelector('.ant-select-selection-placeholder');
      if (ph && ph.textContent.includes('请选择运行类型')) {
        // 点击箭头 .ant-select-arrow
        const arrow = sel.querySelector('.ant-select-arrow');
        if (arrow) {
          arrow.click();
          return 'clicked arrow';
        }
        // fallback: 点击 selector
        const selector = sel.querySelector('.ant-select-selector');
        if (selector) {
          selector.click();
          return 'clicked selector';
        }
      }
    }
    return 'not found';
  });
  console.log(`  ${arrowClicked}`);
  await sleep(1500);

  // 检查下拉是否展开（Ant Design 下拉渲染在 body 末尾）
  const dropdownInfo = await page.evaluate(() => {
    const dds = document.querySelectorAll('.ant-select-dropdown');
    const results = [];
    for (const dd of dds) {
      const hidden = dd.classList.contains('ant-select-dropdown-hidden');
      const display = window.getComputedStyle(dd).display;
      const items = [...dd.querySelectorAll('.ant-select-item-option')].map(i => i.textContent.trim());
      results.push({ hidden, display, items, rect: dd.getBoundingClientRect() });
    }
    return results;
  });
  console.log(`  下拉框数量: ${dropdownInfo.length}`);
  for (const dd of dropdownInfo) {
    console.log(`    hidden=${dd.hidden}, display=${dd.display}, items=${JSON.stringify(dd.items)}, rect=${JSON.stringify(dd.rect)}`);
  }
  await ss(page, 'dropdown-state');

  // 5. 如果有可见的下拉，点击第一个选项
  if (dropdownInfo.some(dd => !dd.hidden && dd.items.length > 0)) {
    const selected = await page.evaluate(() => {
      const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dds) {
        const items = dd.querySelectorAll('.ant-select-item-option');
        if (items.length > 0) {
          const text = items[0].textContent.trim();
          items[0].click();
          return text;
        }
      }
      return null;
    });
    console.log(`  ✅ 选择了: ${selected}`);
  } else {
    // 方法2: 用 puppeteer mousedown 事件
    console.log('  下拉未展开，尝试 mousedown...');
    const selectBox = await page.evaluate(() => {
      const selects = document.querySelectorAll('.ant-select');
      for (const sel of selects) {
        const ph = sel.querySelector('.ant-select-selection-placeholder');
        if (ph && ph.textContent.includes('请选择运行类型')) {
          const rect = sel.querySelector('.ant-select-selector').getBoundingClientRect();
          return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
        }
      }
      return null;
    });
    if (selectBox) {
      // puppeteer 原生 mousedown
      await page.mouse.click(selectBox.x, selectBox.y);
      await sleep(1500);
      
      const dropdownAfter = await page.evaluate(() => {
        const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
        const results = [];
        for (const dd of dds) {
          results.push([...dd.querySelectorAll('.ant-select-item-option')].map(i => i.textContent.trim()));
        }
        return results;
      });
      console.log(`  mousedown 后可见下拉: ${JSON.stringify(dropdownAfter)}`);
      
      if (dropdownAfter.length > 0 && dropdownAfter[0].length > 0) {
        const sel2 = await page.evaluate(() => {
          const dd = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
          if (dd) {
            // 选择"测试"而非"正式"
            const items = dd.querySelectorAll('.ant-select-item-option');
            for (const item of items) {
              if (item.textContent.trim() === '测试') {
                item.click();
                return item.textContent.trim();
              }
            }
            // fallback: 选第一个
            if (items[0]) { items[0].click(); return items[0].textContent.trim(); }
          }
          return null;
        });
        console.log(`  ✅ 选择了: ${sel2}`);
      }
      await ss(page, 'after-mousedown');
    }
  }

  await sleep(1000);

  // 6. 提交
  console.log('6. 发起任务运行...');
  await ss(page, 'before-submit');
  const result = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('发起任务运行') && b.offsetHeight > 0);
    if (btn) { btn.click(); return btn.textContent.trim(); }
    return 'not found';
  });
  console.log(`  ${result}`);
  await sleep(3000);
  await ss(page, 'after-submit');

  // 检查结果
  const msgs = await page.evaluate(() => {
    return [...document.querySelectorAll('.ant-message-notice, .ant-notification-notice, .ant-alert')].map(m => m.textContent.trim());
  });
  if (msgs.length) console.log(`  消息: ${JSON.stringify(msgs)}`);

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });
