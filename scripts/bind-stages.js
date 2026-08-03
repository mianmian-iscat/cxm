#!/usr/bin/env node
/**
 * 链路20235: 添加环节 → 逐环节绑策略 → 配入参 → 保存
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP = 'http://127.0.0.1:9222';
const SS = path.join(__dirname, '..', 'artifacts', 'screenshots', 'full-link');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const LINK = '20235';
const STRATS = ['刷标签策略_138413','首图生图策略_138413','首图审核策略_138413','套图生图策略_138413','套图审核策略_138413'];
const PARAMS = ['seller_id','seed_image_url','tao_cate','item_id'];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const shot = async (p, n) => { fs.mkdirSync(SS,{recursive:true}); await p.screenshot({path:path.join(SS,n+'.jpg'),type:'jpeg',quality:70}); console.log('  📸 '+n); };

async function main() {
  console.log('🚀 链路完整构建');
  const browser = await puppeteer.connect({ browserURL: CDP, defaultViewport: null });
  const page = await browser.newPage();
  try {
    await page.goto(`${BASE}/strategy/linkDetail?id=${LINK}`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);

    // ========== 1. 添加5个环节 ==========
    console.log('\n=== Step 1: 添加环节 ===');
    let cnt = await page.evaluate(() => (document.body.innerText.match(/环节\d+/g)||[]).length);
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
      await sleep(1500);
    }
    console.log(`  环节数: ${cnt}`);
    await shot(page, 's1-stages');

    // ========== 2. 逐环节绑定策略 ==========
    console.log('\n=== Step 2: 绑定策略 ===');
    for (let i = 0; i < STRATS.length; i++) {
      const name = STRATS[i];
      console.log(`\n  环节${i+1} → ${name}`);

      // 滚动到第i个"添加策略"按钮可见位置，获取精准坐标
      const btnPos = await page.evaluate((idx) => {
        const candidates = [];
        for (const el of document.querySelectorAll('button, a, span, div')) {
          const t = el.textContent.trim().replace(/\s+/g, '');
          if (t === '添加策略' && el.offsetHeight > 0 && el.tagName === 'DIV') {
            candidates.push(el);
          }
        }
        if (idx >= candidates.length) return { pos: null, total: candidates.length };
        // 滚动到可见
        candidates[idx].scrollIntoView({ block: 'center' });
        const r = candidates[idx].getBoundingClientRect();
        return { pos: { x: r.x + r.width/2, y: r.y + r.height/2 }, total: candidates.length };
      }, i);

      console.log(`    按钮: ${btnPos.total}个, 目标: #${i+1}`);
      if (!btnPos.pos) { console.log('    ❌ 未找到'); continue; }
      await sleep(500);

      await page.mouse.click(btnPos.pos.x, btnPos.pos.y);
      await sleep(2500);

      // 检查弹窗是否打开，没打开则重试
      let modalOpen = await page.evaluate(() => !!document.querySelector('.ant-modal:not(.ant-modal-hidden)'));
      if (!modalOpen) {
        console.log('    ⚠️ 弹窗未开，重试');
        await page.mouse.click(btnPos.pos.x, btnPos.pos.y);
        await sleep(2500);
        modalOpen = await page.evaluate(() => !!document.querySelector('.ant-modal:not(.ant-modal-hidden)'));
      }
      if (!modalOpen) { console.log('    ❌ 弹窗仍未打开'); continue; }

      // 在弹窗中点"选择"按钮
      const sel = await page.evaluate((target) => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        if (!modal) return { error: 'no modal' };
        const rows = [...modal.querySelectorAll('tr')];
        for (const row of rows) {
          if (row.textContent.includes(target)) {
            const btns = [...row.querySelectorAll('button, a')];
            for (const btn of btns) {
              if (btn.textContent.trim() === '选择') {
                btn.click();
                return { ok: true, text: row.textContent.trim().substring(0, 60) };
              }
            }
          }
        }
        return { error: 'not found', rowCount: rows.length };
      }, name);
      console.log(`    选择: ${JSON.stringify(sel)}`);
      await sleep(3000);

      const msg = await page.evaluate(() =>
        [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
      );
      if (msg.length) console.log(`    消息: ${JSON.stringify(msg)}`);
      await shot(page, `s2-bind-${i+1}`);
    }

    // ========== 3. 配置起点入参 ==========
    console.log('\n=== Step 3: 配置入参 ===');
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(500);

    const editPos = await page.evaluate(() => {
      for (const el of document.querySelectorAll('button')) {
        if (el.textContent.trim() === '编辑' && el.offsetHeight > 0) {
          const r = el.getBoundingClientRect();
          return { x: r.x + r.width/2, y: r.y + r.height/2 };
        }
      }
      return null;
    });
    if (editPos) {
      await page.mouse.click(editPos.x, editPos.y);
      await sleep(2000);
      console.log('  ✅ 编辑抽屉');

      for (const field of PARAMS) {
        const addPos = await page.evaluate(() => {
          const d = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
          if (!d) return null;
          for (const b of d.querySelectorAll('button')) {
            if (b.textContent.includes('新增字段')) {
              const r = b.getBoundingClientRect();
              return { x: r.x + r.width/2, y: r.y + r.height/2 };
            }
          }
          return null;
        });
        if (!addPos) { console.log('    新增字段按钮未找到'); break; }
        await page.mouse.click(addPos.x, addPos.y);
        await sleep(1500);

        // 填写字段名
        const inputInfo = await page.evaluate(() => {
          const d = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
          if (!d) return null;
          const inputs = [...d.querySelectorAll('input:not([type=hidden])')].filter(i => i.offsetHeight > 0);
          if (!inputs.length) return null;
          const last = inputs[inputs.length - 1];
          const r = last.getBoundingClientRect();
          return { x: r.x + r.width/2, y: r.y + r.height/2, value: last.value };
        });
        if (inputInfo && !inputInfo.value) {
          await page.mouse.click(inputInfo.x, inputInfo.y);
          await sleep(300);
          await page.keyboard.type(field);
          console.log(`    ✅ ${field}`);
        } else {
          console.log(`    ⚠️ input: ${JSON.stringify(inputInfo)}`);
        }
        await sleep(500);
      }

      // 保存入参
      const savePos = await page.evaluate(() => {
        const d = document.querySelector('.ant-drawer:not(.ant-drawer-hidden)');
        if (!d) return null;
        for (const b of d.querySelectorAll('button')) {
          if (b.textContent.includes('保')) {
            const r = b.getBoundingClientRect();
            return { x: r.x + r.width/2, y: r.y + r.height/2 };
          }
        }
        return null;
      });
      if (savePos) {
        await page.mouse.click(savePos.x, savePos.y);
        await sleep(2000);
      }
      const msg = await page.evaluate(() =>
        [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
      );
      console.log(`  入参: ${JSON.stringify(msg)}`);
      await shot(page, 's3-params');
    }

    // ========== 4. 保存链路 ==========
    console.log('\n=== Step 4: 保存链路 ===');
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(500);
    const savePos = await page.evaluate(() => {
      for (const b of document.querySelectorAll('button')) {
        if (b.textContent.trim().replace(/\s+/g, '') === '保存' && b.offsetHeight > 0) {
          const r = b.getBoundingClientRect();
          return { x: r.x + r.width/2, y: r.y + r.height/2 };
        }
      }
      return null;
    });
    if (savePos) {
      await page.mouse.click(savePos.x, savePos.y);
      await sleep(3000);
    }
    const msg = await page.evaluate(() =>
      [...document.querySelectorAll('.ant-message-notice')].map(m => m.textContent.trim())
    );
    console.log(`  保存: ${JSON.stringify(msg)}`);
    await shot(page, 's4-saved');

    // ========== 5. 验证 ==========
    console.log('\n=== Step 5: 验证 ===');
    await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    const info = await page.evaluate(() => {
      const t = document.body.innerText;
      return { stages: (t.match(/环节\d+/g)||[]).length, empty: (t.match(/暂无策略/g)||[]).length, hasParams: !t.includes('暂无入参') };
    });
    console.log(`  环节: ${info.stages}, 空: ${info.empty}, 入参: ${info.hasParams?'有':'无'}`);
    await shot(page, 's5-final');
    console.log(`\n  URL: ${BASE}/strategy/linkDetail?id=${LINK}`);

  } catch(e) {
    console.error(`❌ ${e.message}`);
    await shot(page, 'error');
  }
  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}
main().catch(e => { console.error(e.message); process.exit(1); });
