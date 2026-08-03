#!/usr/bin/env node
'use strict';
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const SS = path.join(__dirname, '..', 'artifacts', 'screenshots', 'template-pkg-probe');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await puppeteer.connect({ browserURL: 'http://127.0.0.1:9222', defaultViewport: null });
  const page = await browser.newPage();
  const apis = [];
  page.on('response', async resp => {
    try {
      const u = resp.url();
      if (u.includes('/api/') || u.includes('bzb.api')) {
        let b = ''; try { b = (await resp.text()).substring(0, 800); } catch(e) {}
        apis.push({ url: u.substring(0,200), status: resp.status(), body: b });
      }
    } catch(e) {}
  });

  if (!fs.existsSync(SS)) fs.mkdirSync(SS, { recursive: true });

  await page.goto('https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement', { waitUntil:'networkidle2', timeout:30000 });
  await sleep(3000);

  // 进入F88测试店铺详情(13个包)
  await page.evaluate(() => {
    const cards = document.querySelectorAll('[class*=shopCard]');
    for (const c of cards) { if (c.innerText?.includes('F88测试店铺')) { c.querySelector('button')?.click(); return; } }
  });
  await sleep(3000);

  // ═══ 1. ellipsis 菜单 ═══
  console.log('═══ 1. ellipsis菜单 ═══');
  const ellipsisBtns = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button')).filter(b => {
      const icon = b.querySelector('[class*=anticon]');
      return icon && icon.classList.toString().includes('ellipsis') && b.offsetHeight > 0;
    }).map(b => {
      const r = b.getBoundingClientRect();
      return { x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) };
    });
  });
  console.log('ellipsis按钮数:', ellipsisBtns.length);
  
  if (ellipsisBtns.length > 0) {
    await page.mouse.click(ellipsisBtns[0].x, ellipsisBtns[0].y);
    await sleep(1500);

    const overlays = await page.evaluate(() => {
      const result = [];
      document.querySelectorAll('.ant-dropdown, .ant-popover, [class*=popup], [class*=Popup]').forEach(d => {
        const style = getComputedStyle(d);
        if (style.display !== 'none' && style.visibility !== 'hidden') {
          const items = Array.from(d.querySelectorAll('[class*=menuItem], [class*=MenuItem], .ant-dropdown-menu-item, li, [role=menuitem], a'))
            .filter(i => i.offsetHeight > 0 && i.innerText?.trim())
            .map(i => i.innerText?.trim());
          result.push({ className: d.className?.substring(0,80), text: d.innerText?.substring(0,200), items });
        }
      });
      return result;
    });
    console.log('浮层:', overlays.length);
    overlays.forEach(o => { console.log('  class:', o.className); console.log('  text:', o.text?.substring(0,100)); console.log('  items:', o.items); });
    await page.screenshot({ path: path.join(SS, 'ellipsis-overlay.jpg'), type: 'jpeg', quality: 80 });
    await page.keyboard.press('Escape');
    await sleep(500);
  }

  // ═══ 2. 立即使用 ═══
  console.log('\n═══ 2. 立即使用 ═══');
  apis.length = 0;
  const idleBtn = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === '立即使用' && b.offsetHeight > 0);
    if (btn) { const r = btn.getBoundingClientRect(); return { x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) }; }
    return null;
  });
  if (idleBtn) {
    await page.mouse.click(idleBtn.x, idleBtn.y);
    await sleep(2000);
    
    const confirm = await page.evaluate(() => {
      const r = {};
      // Check ALL possible confirm UIs
      document.querySelectorAll('.ant-popover, .ant-popconfirm, .ant-modal, .ant-modal-wrap, .ant-message, .ant-notification').forEach(el => {
        const style = getComputedStyle(el);
        if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0) {
          r[el.className?.split(' ')[0]?.substring(0,30)] = el.innerText?.substring(0, 200);
        }
      });
      return r;
    });
    console.log('确认UI:', JSON.stringify(confirm, null, 2));
    console.log('API:', apis.length);
    apis.slice(0,5).forEach(a => console.log('  ' + a.status + ' ' + a.url.substring(0,100)));
    await page.screenshot({ path: path.join(SS, 'use-immediately.jpg'), type: 'jpeg', quality: 80 });
    
    // Try cancel
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancel = btns.find(b => /取\s*消|否/.test(b.innerText) && b.offsetHeight > 0);
      if (cancel) cancel.click();
    });
    await sleep(1000);
  } else {
    console.log('未找到立即使用按钮');
  }

  // ═══ 3. 置为闲置 ═══
  console.log('\n═══ 3. 置为闲置 ═══');
  apis.length = 0;
  const busyBtn = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === '置为闲置' && b.offsetHeight > 0);
    if (btn) { const r = btn.getBoundingClientRect(); return { x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) }; }
    return null;
  });
  if (busyBtn) {
    await page.mouse.click(busyBtn.x, busyBtn.y);
    await sleep(2000);
    
    const confirm2 = await page.evaluate(() => {
      const r = {};
      document.querySelectorAll('.ant-popover, .ant-popconfirm, .ant-modal, .ant-modal-wrap, .ant-message, .ant-notification').forEach(el => {
        const style = getComputedStyle(el);
        if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0) {
          r[el.className?.split(' ')[0]?.substring(0,30)] = el.innerText?.substring(0, 200);
        }
      });
      return r;
    });
    console.log('确认UI:', JSON.stringify(confirm2, null, 2));
    console.log('API:', apis.length);
    apis.slice(0,5).forEach(a => console.log('  ' + a.status + ' ' + a.url.substring(0,100)));
    await page.screenshot({ path: path.join(SS, 'set-idle.jpg'), type: 'jpeg', quality: 80 });
    
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancel = btns.find(b => /取\s*消|否/.test(b.innerText) && b.offsetHeight > 0);
      if (cancel) cancel.click();
    });
    await sleep(1000);
  }

  // ═══ 4. 新建模版包向导 Step1 ═══
  console.log('\n═══ 4. 新建模版包向导 ═══');
  apis.length = 0;
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('新建模版包'));
    if (btn) btn.click();
  });
  await sleep(2000);

  // Step1 详细采集
  const step1Info = await page.evaluate(() => {
    // 进度条
    const steps = Array.from(document.querySelectorAll('.ant-steps-item, [class*=stepItem]')).map(s => ({
      text: s.innerText?.trim()?.substring(0, 20),
      status: s.classList.toString().match(/process|finish|wait|error/)?.[0] || ''
    }));
    // 所有表单标签(含*)
    const labels = Array.from(document.querySelectorAll('label, .ant-form-item-label')).filter(el => el.offsetHeight > 0).map(el => el.innerText?.trim()).filter(Boolean);
    // Select
    const selects = Array.from(document.querySelectorAll('.ant-select')).filter(s => s.offsetHeight > 0).map(s => ({
      ph: s.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || '',
      val: s.querySelector('.ant-select-selection-item')?.innerText?.trim() || ''
    }));
    // Input/Textarea
    const fields = Array.from(document.querySelectorAll('input, textarea')).filter(i => i.offsetHeight > 0).map(i => ({
      tag: i.tagName.toLowerCase(),
      ph: i.getAttribute('placeholder') || '',
      maxLen: i.getAttribute('maxlength') || ''
    }));
    // 按钮
    const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetHeight > 0).map(b => ({
      text: b.innerText?.trim(), disabled: b.disabled
    }));
    return { steps, labels, selects, fields, btns };
  });
  console.log('Steps:', step1Info.steps);
  console.log('Labels:', step1Info.labels);
  console.log('Selects:', step1Info.selects);
  console.log('Fields:', step1Info.fields);
  console.log('Btns:', step1Info.btns);

  // 逐个打开select看选项
  console.log('\n→ 逐个Select选项:');
  const allSelects = await page.$$('.ant-select');
  for (const sel of allSelects) {
    const visible = await sel.evaluate(el => el.offsetHeight > 0);
    if (!visible) continue;
    const ph = await sel.evaluate(el => el.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || el.querySelector('input')?.getAttribute('placeholder') || '');
    
    await sel.click();
    await sleep(800);
    
    const opts = await page.evaluate(() => {
      const dd = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      if (!dd) return [];
      return Array.from(dd.querySelectorAll('.ant-select-item-option-content')).map(o => o.innerText?.trim()).filter(Boolean);
    });
    if (opts.length > 0) {
      console.log(`  Select "${ph}": [${opts.join(', ')}]`);
    }
    
    await page.keyboard.press('Escape');
    await sleep(300);
  }

  await page.screenshot({ path: path.join(SS, 'create-step1-detail.jpg'), type: 'jpeg', quality: 80 });

  // 关闭弹窗
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const cancel = btns.find(b => /取\s*消/.test(b.innerText));
    if (cancel) cancel.click();
  });
  await sleep(1000);

  // ═══ 5. 导入模板包向导 ═══
  console.log('\n═══ 5. 导入模板包向导 ═══');
  apis.length = 0;
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('导入模板包'));
    if (btn) btn.click();
  });
  await sleep(2000);

  const importStep1 = await page.evaluate(() => {
    const steps = Array.from(document.querySelectorAll('.ant-steps-item, [class*=stepItem]')).map(s => ({
      text: s.innerText?.trim()?.substring(0, 20),
      status: s.classList.toString().match(/process|finish|wait|error/)?.[0] || ''
    }));
    const labels = Array.from(document.querySelectorAll('label, .ant-form-item-label')).filter(el => el.offsetHeight > 0).map(el => el.innerText?.trim()).filter(Boolean);
    const selects = Array.from(document.querySelectorAll('.ant-select')).filter(s => s.offsetHeight > 0).map(s => ({
      ph: s.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || '',
      val: s.querySelector('.ant-select-selection-item')?.innerText?.trim() || ''
    }));
    const fields = Array.from(document.querySelectorAll('input, textarea')).filter(i => i.offsetHeight > 0).map(i => ({
      tag: i.tagName.toLowerCase(), ph: i.getAttribute('placeholder') || '', maxLen: i.getAttribute('maxlength') || ''
    }));
    const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetHeight > 0).map(b => ({
      text: b.innerText?.trim(), disabled: b.disabled
    }));
    return { steps, labels, selects, fields, btns };
  });
  console.log('导入 Steps:', importStep1.steps);
  console.log('导入 Labels:', importStep1.labels);
  console.log('导入 Selects:', importStep1.selects);
  console.log('导入 Fields:', importStep1.fields);
  console.log('导入 Btns:', importStep1.btns);

  // Select 选项
  console.log('\n→ 导入Select选项:');
  const importSelects = await page.$$('.ant-select');
  for (const sel of importSelects) {
    const visible = await sel.evaluate(el => el.offsetHeight > 0);
    if (!visible) continue;
    const ph = await sel.evaluate(el => el.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || '');
    await sel.click();
    await sleep(800);
    const opts = await page.evaluate(() => {
      const dd = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      if (!dd) return [];
      return Array.from(dd.querySelectorAll('.ant-select-item-option-content')).map(o => o.innerText?.trim()).filter(Boolean);
    });
    if (opts.length > 0) console.log(`  Select "${ph}": [${opts.join(', ')}]`);
    await page.keyboard.press('Escape');
    await sleep(300);
  }
  await page.screenshot({ path: path.join(SS, 'import-step1.jpg'), type: 'jpeg', quality: 80 });

  // 关闭
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const cancel = btns.find(b => /取\s*消/.test(b.innerText));
    if (cancel) cancel.click();
  });
  await sleep(1000);

  // ═══ 6. 筛选器操作 ═══
  console.log('\n═══ 6. 模板包列表筛选器 ═══');
  // 采集模板包列表区域的筛选器(非店铺级)
  const filterBar = await page.evaluate(() => {
    // 找有"名称/ID/负责人"placeholder的input
    const nameInput = document.querySelector('input[placeholder*="名称"]');
    const envSelects = Array.from(document.querySelectorAll('.ant-select')).filter(s => {
      const text = s.innerText?.trim();
      return s.offsetHeight > 0 && (text?.includes('应用') || text?.includes('状态') || text?.includes('所有'));
    }).map(s => ({
      text: s.innerText?.trim()?.substring(0, 30),
      ph: s.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || ''
    }));
    return {
      hasNameInput: !!nameInput,
      namePh: nameInput?.getAttribute('placeholder'),
      envSelects
    };
  });
  console.log('筛选器:', JSON.stringify(filterBar, null, 2));

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => console.error(e.message, e.stack?.substring(0,300)));
