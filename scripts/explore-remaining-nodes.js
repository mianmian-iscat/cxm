#!/usr/bin/env node
/**
 * 探查剩余节点类型（弹窗滚动后可见的节点）
 * 使用已有策略 10656
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'explore-nodes');
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  screenshot: ${name}.jpg`);
}

const REMAINING_NODES = ['匹配度打分', 'Caption', '改款prompt推理', '视频生成', '机审', '高清化处理', '视频上传'];

async function main() {
  console.log('=== 探查剩余节点 ===\n');

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const pages = await browser.pages();
  let page = pages.find(p => p.url().includes('pre-aifashion-xiaoer'));
  if (!page) page = pages[0];
  await page.bringToFront();
  await sleep(1000);

  // 导航到已有策略
  console.log('[1] 导航到策略详情页');
  await page.goto(`${BASE}/strategy/detail/10656`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  const report = JSON.parse(fs.readFileSync('/tmp/node-type-report.json', 'utf-8'));

  for (let i = 0; i < REMAINING_NODES.length; i++) {
    const nodeName = REMAINING_NODES[i];
    console.log(`\n[${i + 1}/${REMAINING_NODES.length}] ${nodeName}`);

    // 点击 "新增节点"
    const btnPos = await page.evaluate(() => {
      const els = document.querySelectorAll('button, span, div, a');
      for (const el of els) {
        const txt = el.textContent.replace(/\s+/g, '');
        if ((txt === '新增节点' || txt === '+新增节点') && el.offsetHeight > 0) {
          const r = el.getBoundingClientRect();
          return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
      }
      return null;
    });
    if (!btnPos) { console.log('  找不到新增节点按钮'); continue; }
    await page.mouse.click(btnPos.x, btnPos.y);
    await sleep(2000);

    // 滚动弹窗查找目标节点
    const cardPos = await page.evaluate(async (targetTitle) => {
      // 找弹窗的 wrap（可滚动容器）
      const modals = document.querySelectorAll('.ant-modal');
      let modal = null;
      for (const m of modals) {
        if (m.classList.contains('ant-modal-hidden')) continue;
        const r = m.getBoundingClientRect();
        if (r.width > 200) { modal = m; break; }
      }
      if (!modal) return null;
      const wrap = modal.closest('.ant-modal-wrap') || modal.parentElement;

      // 滚动查找
      for (let s = 0; s < 20; s++) {
        const cards = modal.querySelectorAll('.ant-card, [class*="card"]');
        for (const card of cards) {
          const titleEl = card.querySelector('.ant-card-meta-title');
          if (titleEl && titleEl.textContent.trim() === targetTitle) {
            // 滚动到卡片可见
            card.scrollIntoView({ block: 'center' });
            await new Promise(r => setTimeout(r, 200));
            const r = card.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
          }
        }
        wrap.scrollTop += 200;
        await new Promise(r => setTimeout(r, 200));
      }
      return null;
    }, nodeName);

    if (!cardPos) {
      console.log(`  找不到 "${nodeName}" 卡片，诊断中...`);
      // 诊断：截图并查找可滚动容器
      const diag = await page.evaluate((targetTitle) => {
        const modals = document.querySelectorAll('.ant-modal');
        for (const m of modals) {
          if (m.classList.contains('ant-modal-hidden')) continue;
          const r = m.getBoundingClientRect();
          if (r.width > 200) {
            const body = m.querySelector('.ant-modal-body');
            const content = m.querySelector('.ant-modal-content');
            const wrap = m.closest('.ant-modal-wrap');
            const titles = [];
            m.querySelectorAll('.ant-card-meta-title').forEach(t => titles.push(t.textContent.trim()));
            return {
              bodyScroll: body ? { h: body.scrollHeight, ch: body.clientHeight, st: body.scrollTop, overflow: getComputedStyle(body).overflow } : null,
              contentScroll: content ? { h: content.scrollHeight, ch: content.clientHeight } : null,
              wrapScroll: wrap ? { h: wrap.scrollHeight, ch: wrap.clientHeight, overflow: getComputedStyle(wrap).overflowY } : null,
              titles,
            };
          }
        }
        return { noModal: true };
      }, nodeName);
      console.log(`  诊断: ${JSON.stringify(diag).substring(0, 300)}`);
      await ss(page, `remaining-debug-${nodeName}`);
      // 关闭弹窗
      await page.keyboard.press('Escape');
      await sleep(500);
      continue;
    }

    // 点击卡片
    await page.mouse.click(cardPos.x, cardPos.y);
    await sleep(3000);
    await ss(page, `remaining-${String(i + 1).padStart(2, '0')}-${nodeName}`);

    // 提取表单字段
    const formInfo = await page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return { fields: [], sections: [], drawerOpen: false };
      const fields = [];
      const formItems = drawer.querySelectorAll('.ant-form-item');
      for (const item of formItems) {
        const labelEl = item.querySelector('.ant-form-item-label label, .ant-form-item-label');
        const label = labelEl ? labelEl.textContent.trim() : '';
        let type = 'unknown';
        if (item.querySelector('.ant-select')) type = 'select';
        else if (item.querySelector('textarea')) type = 'textarea';
        else if (item.querySelector('.ant-input-number')) type = 'number';
        else if (item.querySelector('input[type="text"], input:not([type])')) type = 'input';
        else if (item.querySelector('.ant-switch')) type = 'switch';
        else if (item.querySelector('.ant-radio-group')) type = 'radio';
        else if (item.querySelector('.ant-checkbox-group')) type = 'checkbox';
        fields.push({ label, type });
      }
      const sections = [];
      drawer.querySelectorAll('h3, h4, .ant-divider-inner-text').forEach(t => sections.push(t.textContent.trim()));
      return { fields, sections, drawerOpen: true };
    });

    console.log(`  抽屉: ${formInfo.drawerOpen ? '打开' : '未打开'}, 字段: ${formInfo.fields.length}`);
    formInfo.fields.forEach(f => console.log(`    - ${f.label} (${f.type})`));

    report.nodeTypes.push({
      title: nodeName,
      description: '',
      fields: formInfo.fields,
      sections: formInfo.sections,
      drawerOpen: formInfo.drawerOpen,
    });

    // 关闭抽屉
    await page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return;
      const closeBtn = drawer.querySelector('.ant-drawer-close');
      if (closeBtn) closeBtn.click();
    });
    await sleep(1500);
  }

  // 保存更新后的报告
  fs.writeFileSync('/tmp/node-type-report.json', JSON.stringify(report, null, 2));
  console.log(`\n报告已更新: ${report.nodeTypes.length} 种节点`);

  browser.disconnect();
  console.log('=== 完成 ===');
}

main().catch(e => { console.error('失败:', e); process.exit(1); });
