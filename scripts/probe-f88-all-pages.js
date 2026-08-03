#!/usr/bin/env node
/**
 * F88全页面批量探查 - 逐页采集DOM结构+按钮+筛选器+API
 * 覆盖: 审核管理(4页) + 策略平台(3页) + 模版库(2页) + 商家管理(1页)
 */
'use strict';
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'f88-all-pages');
const OUT_DIR = path.join(__dirname, '..', 'artifacts');
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGES = [
  { name: '个人任务中心', url: '/review/personal-task-center' },
  { name: '审核标准管理', url: '/review/standard-management' },
  { name: '审核节点管理', url: '/review/node-management' },
  { name: '任务管理', url: '/review/task-management' },
  { name: '链路列表', url: '/strategy/linkList' },
  { name: '策略列表', url: '/strategy/list' },
  { name: '生产看板', url: '/strategy/productionDashboard' },
  { name: '模版包管理', url: '/templateManagement' },
  { name: '淘内资源池', url: '/templateLibrary' },
  { name: '优质模板库', url: '/selfTemplateLibrary_f88' },
  { name: '商家管理', url: '/afdMerchantManagement/shopConfig' },
];

async function probePage(page, pg) {
  const result = { name: pg.name, url: pg.url, fullUrl: '', error: null };
  const apis = [];
  
  const apiHandler = async (resp) => {
    try {
      const u = resp.url();
      if (u.includes('/api/') || u.includes('bzb.api') || u.includes('mtop.')) {
        let b = ''; try { b = (await resp.text()).substring(0, 500); } catch(e) {}
        apis.push({ url: u.substring(0, 200), status: resp.status(), body: b });
      }
    } catch(e) {}
  };
  page.on('response', apiHandler);

  try {
    await page.goto(`${BASE}${pg.url}`, { waitUntil: 'networkidle2', timeout: 15000 });
    await sleep(4000);
    result.fullUrl = page.url();

    // 截图
    await page.screenshot({ path: path.join(SS_DIR, `${pg.name}.jpg`), type: 'jpeg', quality: 75 });

    // 基础结构
    result.bodyText = await page.evaluate(() => document.body.innerText.substring(0, 3000));
    
    // 所有可见按钮
    result.buttons = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button, [role=button], a.ant-btn'))
        .filter(b => b.offsetHeight > 0)
        .map(b => {
          const icon = b.querySelector('.anticon, svg');
          return {
            text: b.innerText?.trim().substring(0, 40),
            ariaLabel: b.getAttribute('aria-label') || '',
            iconType: icon?.getAttribute('aria-label') || icon?.getAttribute('class')?.match(/anticon-(\w+)/)?.[1] || '',
            disabled: b.disabled
          };
        });
    });

    // 筛选器
    result.filters = await page.evaluate(() => {
      const r = [];
      document.querySelectorAll('.ant-select').forEach(s => {
        if (s.offsetHeight === 0) return;
        r.push({
          type: 'Select',
          placeholder: s.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || '',
          value: s.querySelector('.ant-select-selection-item')?.innerText?.trim() || '',
          label: s.closest('.ant-form-item, [class*=filter]')?.querySelector('label, [class*=label]')?.innerText?.trim() || ''
        });
      });
      document.querySelectorAll('input[placeholder], input:not([type=hidden])').forEach(i => {
        if (i.offsetHeight === 0 || i.type === 'hidden') return;
        const ph = i.getAttribute('placeholder') || '';
        if (!ph && !i.value) return;
        r.push({ type: 'Input', placeholder: ph, value: i.value, inputType: i.type });
      });
      return r;
    });

    // Tab栏
    result.tabs = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('.ant-tabs-tab, [role=tab]'))
        .filter(t => t.offsetHeight > 0)
        .map(t => ({
          text: t.innerText?.trim().substring(0, 30),
          active: t.classList.contains('ant-tabs-tab-active') || t.getAttribute('aria-selected') === 'true'
        }));
    });

    // 表格
    result.tables = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('table, .ant-table-wrapper'))
        .filter(t => t.offsetHeight > 0)
        .map(t => {
          const headers = Array.from(t.querySelectorAll('th')).map(th => th.innerText?.trim().substring(0, 25));
          const rowCount = t.querySelectorAll('tbody tr').length;
          return { headers, rowCount };
        });
    });

    // 卡片
    result.cards = await page.evaluate(() => {
      const cardEls = document.querySelectorAll('.ant-card, [class*=card], [class*=Card]');
      const visible = Array.from(cardEls).filter(c => c.offsetHeight > 0);
      return {
        count: visible.length,
        samples: visible.slice(0, 3).map(c => ({
          text: c.innerText?.substring(0, 150),
          buttons: Array.from(c.querySelectorAll('button, a, [role=button]')).map(b => b.innerText?.trim()).filter(Boolean).slice(0, 5)
        }))
      };
    });

    // 分页
    result.pagination = await page.evaluate(() => {
      const p = document.querySelector('.ant-pagination, [class*=pagination]');
      if (!p || p.offsetHeight === 0) return null;
      return { text: p.innerText?.trim().substring(0, 100), hasPrev: !p.querySelector('li.ant-pagination-disabled') || !p.querySelector('[class*=prev]')?.closest('li')?.classList.contains('ant-pagination-disabled') };
    });

    // 逐个展开Select采集选项（只取前3个）
    result.selectOptions = [];
    const selects = await page.$$('.ant-select');
    for (let i = 0; i < Math.min(selects.length, 4); i++) {
      const visible = await selects[i].evaluate(el => el.offsetHeight > 0);
      if (!visible) continue;
      const ph = await selects[i].evaluate(el => el.querySelector('.ant-select-selection-placeholder')?.innerText?.trim() || el.querySelector('.ant-select-selection-item')?.innerText?.trim() || '');
      
      await selects[i].click();
      await sleep(800);
      const opts = await page.evaluate(() => {
        const dd = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
        if (!dd) return [];
        return Array.from(dd.querySelectorAll('.ant-select-item-option-content')).map(o => o.innerText?.trim()).filter(Boolean);
      });
      if (opts.length > 0) {
        result.selectOptions.push({ select: ph || `Select[${i}]`, options: opts });
      }
      await page.keyboard.press('Escape');
      await sleep(300);
    }

    // 尝试点击第一个操作按钮（查看详情/编辑/审核等）
    result.firstAction = null;
    const actionBtns = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button, a, [role=button]'));
      const actionBtn = btns.find(b => {
        const t = b.innerText?.trim();
        return b.offsetHeight > 0 && (t?.includes('查看详情') || t?.includes('编辑') || t?.includes('审核') || t?.includes('打开') || t?.includes('查看'));
      });
      if (actionBtn) {
        const r = actionBtn.getBoundingClientRect();
        return { text: actionBtn.innerText?.trim(), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) };
      }
      return null;
    });

    if (actionBtns) {
      apis.length = 0;
      await page.mouse.click(actionBtns.x, actionBtns.y);
      await sleep(2500);

      result.firstAction = {
        clicked: actionBtns.text,
        newUrl: page.url(),
        modalDetected: await page.evaluate(() => {
          const m = document.querySelector('.ant-modal:not([style*="display: none"]), .ant-drawer:not([style*="display: none"])');
          if (m && m.offsetHeight > 0) return { type: m.className?.includes('drawer') ? 'drawer' : 'modal', text: m.innerText?.substring(0, 300) };
          const pop = document.querySelector('.ant-popover:not(.ant-popover-hidden)');
          if (pop) return { type: 'popover', text: pop.innerText?.substring(0, 200) };
          return null;
        }),
        apis: apis.slice(0, 5).map(a => ({ url: a.url, status: a.status }))
      };
      
      await page.screenshot({ path: path.join(SS_DIR, `${pg.name}-action.jpg`), type: 'jpeg', quality: 75 });
      
      // 关闭弹窗/返回
      await page.keyboard.press('Escape');
      await sleep(500);
      if (page.url() !== result.fullUrl) {
        await page.goBack();
        await sleep(2000);
      }
    }

    result.apiCount = apis.length;
    result.sampleApis = apis.slice(0, 5);
    
    console.log(`  ✅ ${pg.name}: ${result.buttons.length}按钮, ${result.filters.length}筛选, ${result.tables.length}表格, ${result.cards.count}卡片, ${apis.length}API`);
    
  } catch(e) {
    result.error = e.message;
    console.log(`  ❌ ${pg.name}: ${e.message}`);
  }

  page.off('response', apiHandler);
  return result;
}

async function main() {
  console.log('🔍 F88全页面批量探查');
  console.log(`  CDP: ${CDP_URL}`);
  console.log(`  页面数: ${PAGES.length}\n`);

  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null, protocolTimeout: 60000 });
  const page = await browser.newPage();
  const allResults = {};

  for (const pg of PAGES) {
    console.log(`\n═══ ${pg.name} (${pg.url}) ═══`);
    allResults[pg.name] = await probePage(page, pg);
  }

  // 保存结果
  const outputPath = path.join(OUT_DIR, 'f88-all-pages-probe.json');
  fs.writeFileSync(outputPath, JSON.stringify(allResults, null, 2));
  console.log(`\n📁 结果已保存: ${outputPath}`);

  // 汇总
  console.log('\n════════════════════════════');
  console.log('📊 探查汇总');
  console.log('════════════════════════════');
  for (const [name, r] of Object.entries(allResults)) {
    if (r.error) {
      console.log(`  ❌ ${name}: ${r.error}`);
    } else {
      console.log(`  ✅ ${name}: ${r.buttons?.length}按钮 ${r.filters?.length}筛选 ${r.tables?.length}表格 ${r.cards?.count}卡片 ${r.tabs?.length}Tab`);
    }
  }

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => console.error(e.message, e.stack?.substring(0, 300)));
