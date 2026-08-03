#!/usr/bin/env node
/**
 * 给链路20235添加5个环节 + 绑定5个策略
 * 环节结构: 刷标签→首图生图→首图审核→套图生图→套图审核
 * 策略ID: 10590, 10591, 10592, 10593, 10594
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'full-link');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const LINK_ID = '20235';
const STAGES = ['刷标签', '首图生图', '首图审核', '套图生图', '套图审核'];
const STRATEGIES = [
  { name: `刷标签策略_138413`, id: '10590' },
  { name: `首图生图策略_138413`, id: '10591' },
  { name: `首图审核策略_138413`, id: '10592' },
  { name: `套图生图策略_138413`, id: '10593' },
  { name: `套图审核策略_138413`, id: '10594' },
];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${name}.jpg`);
}

async function main() {
  console.log('🚀 添加环节 + 绑定策略');
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  try {
    // ========== 1. 打开链路详情 ==========
    await page.goto(`${BASE}/strategy/linkDetail?id=${LINK_ID}`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);

    // ========== 2. 添加5个环节 ==========
    console.log('\n========== Step 1: 添加环节 ==========');
    
    // 先检查当前已有几个环节
    let currentCount = await page.evaluate(() => {
      const text = document.body.innerText;
      return (text.match(/环节\d+/g) || []).length;
    });
    console.log(`  当前环节数: ${currentCount}`);

    for (let i = currentCount; i < STAGES.length; i++) {
      console.log(`  添加环节 ${i + 1}/${STAGES.length}: ${STAGES[i]}`);
      
      // 找到 +添加环节 primary按钮
      const btnPos = await page.evaluate(() => {
        const btns = [...document.querySelectorAll('button.ant-btn-primary')];
        for (const b of btns) {
          const t = b.textContent.trim().replace(/\s+/g, '');
          if (t === '添加环节' || t === '+添加环节') {
            const r = b.getBoundingClientRect();
            if (r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
        return null;
      });
      
      if (btnPos) {
        await page.mouse.click(btnPos.x, btnPos.y);
        console.log(`    ✅ 点击添加环节`);
      } else {
        console.log(`    ❌ 按钮未找到`);
        break;
      }
      await sleep(2000);
      
      // 验证环节数增加
      const newCount = await page.evaluate(() => {
        const text = document.body.innerText;
        return (text.match(/环节\d+/g) || []).length;
      });
      console.log(`    环节数: ${newCount}`);
    }

    await ss(page, 'all-stages-inline');

    // ========== 3. 保存链路 ==========
    console.log('\n========== Step 2: 保存链路 ==========');
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button, div, span')];
      for (const b of btns) {
        const t = b.textContent.trim().replace(/\s+/g, '');
        if (t === '保存' && b.offsetHeight > 0 && b.tagName === 'BUTTON') {
          b.click();
          return;
        }
      }
    });
    await sleep(3000);

    const msgs = await page.evaluate(() =>
      [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
    );
    console.log(`  保存消息: ${JSON.stringify(msgs)}`);
    await ss(page, 'stages-saved');

    // ========== 4. 查看运行结果 → 绑定策略 ==========
    console.log('\n========== Step 3: 绑定策略 ==========');
    
    // 点击 查看运行结果
    const viewBtn = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')];
      for (const b of btns) {
        const t = b.textContent.trim().replace(/\s+/g, '');
        if (t === '查看运行结果' && b.offsetHeight > 0) {
          const r = b.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      return null;
    });
    if (viewBtn) {
      await page.mouse.click(viewBtn.x, viewBtn.y);
      console.log('  ✅ 查看运行结果');
    }
    await sleep(3000);

    // 采集环节信息确认
    const stageInfo = await page.evaluate(() => {
      const text = document.body.innerText;
      const stages = [];
      const lines = text.split('\n');
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].trim().startsWith('环节')) {
          stages.push(lines[i].trim());
          // 下一行可能是策略信息
          if (i + 1 < lines.length) stages.push('  → ' + lines[i + 1].trim());
        }
      }
      return stages;
    });
    console.log(`  环节状态: ${JSON.stringify(stageInfo, null, 2)}`);
    await ss(page, 'run-results-view');

    // 逐个绑定策略
    for (let i = 0; i < STRATEGIES.length; i++) {
      const strat = STRATEGIES[i];
      console.log(`  绑定策略 ${i + 1}: ${strat.name}`);

      // 点击"添加策略"（找到第一个）
      const addClicked = await page.evaluate(() => {
        const btns = [...document.querySelectorAll('button, a, span, div')];
        for (const b of btns) {
          const t = b.textContent.trim().replace(/\s+/g, '');
          if (t === '添加策略' && b.offsetHeight > 0) {
            b.click();
            return true;
          }
        }
        return false;
      });
      if (!addClicked) {
        console.log(`    ⚠️ 添加策略按钮未找到（可能环节数不够）`);
        break;
      }
      await sleep(2000);

      // 在弹窗中搜索策略
      const searchInput = await page.$('.ant-modal input, .ant-drawer input');
      if (searchInput) {
        await searchInput.click({ clickCount: 3 });
        await searchInput.type(strat.name);
        await page.keyboard.press('Enter');
        await sleep(2000);
      }

      // 选择策略行（radio）
      const selected = await page.evaluate((name) => {
        const rows = document.querySelectorAll('tr, .ant-list-item, .ant-radio-wrapper');
        for (const r of rows) {
          if (r.textContent.includes(name)) {
            const radio = r.querySelector('input[type=radio], .ant-radio-wrapper, .ant-radio');
            if (radio) { radio.click(); return r.textContent.trim().substring(0, 50); }
            r.click();
            return r.textContent.trim().substring(0, 50);
          }
        }
        return null;
      }, strat.name);
      console.log(`    选择: ${selected || '未找到'}`);
      await sleep(500);

      // 确定
      await page.evaluate(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (modal) {
          const btn = [...modal.querySelectorAll('button')].find(b => /确.*定/.test(b.textContent));
          if (btn) btn.click();
        }
      });
      await sleep(2000);
      console.log(`    ✅ 已绑定`);
    }

    await ss(page, 'strategies-bound');

    // ========== 5. 汇总 ==========
    console.log('\n========== 汇总 ==========');
    console.log(`  链路ID: ${LINK_ID}`);
    console.log(`  环节数: ${STAGES.length}`);
    console.log(`  策略数: ${STRATEGIES.length}`);
    console.log(`  URL: ${BASE}/strategy/linkDetail?id=${LINK_ID}`);

  } catch (e) {
    console.error(`\n❌ 异常: ${e.message}`);
    await ss(page, 'error');
  }

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
