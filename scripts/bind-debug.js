#!/usr/bin/env node
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP = 'http://127.0.0.1:9222';
const SS = path.join(__dirname, '..', 'artifacts', 'screenshots', 'full-link');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const LINK = '20235';
const STRATS = ['刷标签策略_138413','首图生图策略_138413','首图审核策略_138413','套图生图策略_138413','套图审核策略_138413'];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const shot = async (p, n) => { fs.mkdirSync(SS,{recursive:true}); await p.screenshot({path:path.join(SS,n+'.jpg'),type:'jpeg',quality:70}); };

async function main() {
  const browser = await puppeteer.connect({ browserURL: CDP, defaultViewport: null });
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE}/strategy/linkDetail?id=${LINK}`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    
    // 添加5环节
    let cnt = 0;
    while (cnt < 5) {
      const pos = await page.evaluate(() => {
        for (const b of document.querySelectorAll('button.ant-btn-primary')) {
          if (b.textContent.trim().replace(/\s+/g,'').includes('添加环节') && b.offsetHeight > 0) {
            const r = b.getBoundingClientRect();
            return { x: r.x + r.width/2, y: r.y + r.height/2 };
          }
        }
        return null;
      });
      if (!pos) break;
      await page.mouse.click(pos.x, pos.y);
      cnt++;
      await sleep(1000);
    }
    console.log('环节:', cnt);

    // 逐个绑定，每次绑定后检查全局状态
    for (let i = 0; i < STRATS.length; i++) {
      console.log(`\n环节${i+1} → ${STRATS[i]}`);
      
      // scrollIntoView + 获取坐标
      const btnPos = await page.evaluate((idx) => {
        // 只匹配 ant-space-item DIV（有onClick的容器），排除SPAN
        const divs = [...document.querySelectorAll('div.ant-space-item, button')].filter(el => 
          el.textContent.trim().replace(/\s+/g,'') === '添加策略' && el.offsetHeight > 0
        );
        if (idx >= divs.length) return null;
        divs[idx].scrollIntoView({ block: 'center' });
        const r = divs[idx].getBoundingClientRect();
        return { x: r.x + r.width/2, y: r.y + r.height/2 };
      }, i);
      if (!btnPos) { console.log('  ❌ 按钮未找到'); continue; }
      
      await sleep(1000);
      
      // 强制触发页面重渲染
      await page.evaluate(() => window.scrollTo(0, 0));
      await sleep(500);
      await page.evaluate(() => window.scrollTo(0, 99999));
      await sleep(500);
      
      await page.mouse.click(btnPos.x, btnPos.y);
      await sleep(3000);
      
      // 验证弹窗
      const modalOpen = await page.evaluate(() => !!document.querySelector('.ant-modal:not(.ant-modal-hidden)'));
      if (!modalOpen) { console.log('  ❌ 弹窗未开'); continue; }
      
      // 选择策略
      await page.evaluate((name) => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return;
        for (const row of modal.querySelectorAll('tr')) {
          if (row.textContent.includes(name)) {
            for (const b of row.querySelectorAll('button, a')) {
              if (b.textContent.trim() === '选择') { b.click(); return; }
            }
          }
        }
      }, STRATS[i]);
      
      // 等待弹窗关闭
      await sleep(2000);
      
      // 全局状态检查
      const state = await page.evaluate(() => {
        const text = document.body.innerText;
        const empty = (text.match(/暂无策略/g) || []).length;
        return { empty, bound: 5 - empty };
      });
      console.log(`  → 已绑定=${state.bound}, 空=${state.empty}`);
      
      // 如果绑定后状态没更新，截图看看
      if (state.bound !== i + 1) {
        await shot(page, `debug-bind-${i+1}`);
        console.log(`  ⚠️ 期望${i+1}个绑定，实际${state.bound}个`);
      }
    }

    // 保存
    console.log('\n--- 保存 ---');
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(500);
    await page.evaluate(() => {
      for (const b of document.querySelectorAll('button')) {
        if (b.textContent.trim().replace(/\s+/g,'') === '保存' && b.offsetHeight > 0) {
          b.scrollIntoView({ block: 'center' });
          b.click();
          return;
        }
      }
    });
    await sleep(3000);
    const msgs = await page.evaluate(() => 
      [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
    );
    console.log('保存:', JSON.stringify(msgs));
    await shot(page, 'save-result');

    // 刷新验证
    await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    const final = await page.evaluate(() => {
      const t = document.body.innerText;
      return { stages: (t.match(/环节\d+/g)||[]).length, empty: (t.match(/暂无策略/g)||[]).length };
    });
    console.log('刷新后:', JSON.stringify(final));
    await shot(page, 'final');

  } catch(e) { console.error('❌', e.message); await shot(page, 'error'); }
  await page.close();
  await browser.disconnect();
  console.log('\n🏁');
}
main().catch(e => { console.error(e.message); process.exit(1); });
