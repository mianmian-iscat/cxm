#!/usr/bin/env node
/**
 * 模板包管理页面原子级功能探查
 * 逐个按钮实际操作 + 采集DOM/API响应
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'template-pkg-probe');
const OUT_DIR = path.join(__dirname, '..', 'artifacts');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${name}`);
  return fp;
}

// 采集网络请求
function setupNetworkCapture(page) {
  const requests = [];
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (url.includes('/api/') || url.includes('bzb.api') || url.includes('mtop.')) {
        const status = resp.status();
        let body = null;
        try { body = await resp.text(); body = body.substring(0, 500); } catch(e) {}
        requests.push({ url: url.substring(0, 200), status, bodySnippet: body });
      }
    } catch(e) {}
  });
  return requests;
}

async function main() {
  console.log('🔍 模板包管理页面原子级功能探查');
  console.log(`  CDP: ${CDP_URL}\n`);

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();
  const networkLog = setupNetworkCapture(page);
  const results = {};

  try {
    // ═══ Phase 1: 页面加载 ═══
    console.log('═══ Phase 1: 页面加载与结构采集 ═══');
    await page.goto(`${BASE}/templateManagement`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    await ss(page, '01-page-loaded');

    // 采集页面结构
    results.pageStructure = await page.evaluate(() => {
      const filters = Array.from(document.querySelectorAll('.ant-select, .ant-input, input[placeholder]')).map(el => ({
        type: el.tagName,
        placeholder: el.getAttribute('placeholder') || el.querySelector('input')?.getAttribute('placeholder') || '',
        className: el.className?.substring(0, 60) || '',
        value: el.value || ''
      }));

      const buttons = Array.from(document.querySelectorAll('button, .ant-btn')).filter(b => b.offsetHeight > 0).map(b => ({
        text: b.innerText?.trim()?.substring(0, 30),
        type: b.getAttribute('type') || '',
        className: b.className?.substring(0, 60) || '',
        disabled: b.disabled
      }));

      // 采集卡片列表
      const cards = [];
      document.querySelectorAll('[class*=card], [class*=Card], .ant-card').forEach((card, i) => {
        if (i >= 8) return;
        const name = card.querySelector('[class*=name], [class*=title], h3, h4')?.innerText?.trim() || '';
        const status = card.querySelector('[class*=status], [class*=tag], .ant-tag')?.innerText?.trim() || '';
        const tags = Array.from(card.querySelectorAll('.ant-tag, [class*=tag]')).map(t => t.innerText?.trim()).filter(Boolean);
        const actions = Array.from(card.querySelectorAll('button, a, [role=button], [class*=action]')).map(a => a.innerText?.trim()).filter(Boolean);
        const creator = card.innerText?.match(/创建人[：:]\s*(\S+)/)?.[1] || '';
        cards.push({ index: i, name, status, tags: [...new Set(tags)], actions, creator, textSnippet: card.innerText?.substring(0, 150) });
      });

      return { filters, buttons, cards, pageTitle: document.title, url: window.location.href };
    });

    console.log(`  页面标题: ${results.pageStructure.pageTitle}`);
    console.log(`  URL: ${results.pageStructure.url}`);
    console.log(`  筛选器: ${results.pageStructure.filters.length}个`);
    results.pageStructure.filters.forEach((f, i) => console.log(`    [${i}] ${f.type} placeholder="${f.placeholder}"`));
    console.log(`  按钮: ${results.pageStructure.buttons.length}个`);
    results.pageStructure.buttons.forEach((b, i) => console.log(`    [${i}] "${b.text}" ${b.disabled ? '(disabled)' : ''}`));
    console.log(`  卡片: ${results.pageStructure.cards.length}个`);
    results.pageStructure.cards.forEach((c, i) => console.log(`    [${i}] "${c.name}" status="${c.status}" actions=[${c.actions.join(',')}]`));

    // ═══ Phase 2: 筛选器操作 ═══
    console.log('\n═══ Phase 2: 筛选器逐个操作 ═══');
    const filterResults = [];
    const selects = await page.$$('.ant-select');
    for (let i = 0; i < Math.min(selects.length, 4); i++) {
      const select = selects[i];
      const isVisible = await select.evaluate(el => el.offsetHeight > 0);
      if (!isVisible) continue;

      // 点击展开
      await select.click();
      await sleep(1000);

      // 采集下拉选项
      const options = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('.ant-select-item-option-content, .ant-select-dropdown .ant-select-item')).map(o => ({
          text: o.innerText?.trim(),
          visible: o.offsetHeight > 0
        })).filter(o => o.visible && o.text);
      });

      const placeholder = await select.evaluate(el => el.getAttribute('placeholder') || el.querySelector('input')?.getAttribute('placeholder') || el.innerText?.trim()?.substring(0, 20) || '');

      filterResults.push({ index: i, placeholder, options: options.map(o => o.text) });
      console.log(`  筛选器[${i}] "${placeholder}": [${options.map(o => o.text).join(', ')}]`);

      // 选择第一个非全部选项
      if (options.length > 1) {
        const firstOption = options.find(o => o.text !== '全部') || options[0];
        await page.evaluate((text) => {
          const items = Array.from(document.querySelectorAll('.ant-select-item-option-content'));
          const item = items.find(i => i.innerText?.trim() === text);
          if (item) item.click();
        }, firstOption.text);
        await sleep(1500);

        // 采集筛选后卡片数
        const filteredCount = await page.evaluate(() => {
          return document.querySelectorAll('[class*=card], [class*=Card], .ant-card').length;
        });
        console.log(`    选择"${firstOption.text}"后卡片数: ${filteredCount}`);
        filterResults[filterResults.length - 1].filteredCount = filteredCount;
      }

      // 关闭下拉
      await page.keyboard.press('Escape');
      await sleep(500);
    }
    results.filters = filterResults;
    await ss(page, '02-filters-explored');

    // ═══ Phase 3: 新建模板包 ═══
    console.log('\n═══ Phase 3: 新建模板包弹窗 ═══');
    networkLog.length = 0;

    // 点击新建
    const createClicked = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.innerText.includes('新建') && b.offsetHeight > 0);
      if (btn) { btn.click(); return true; }
      return false;
    });
    await sleep(2000);

    if (createClicked) {
      const modalInfo = await page.evaluate(() => {
        const modal = document.querySelector('.ant-modal, .ant-drawer, [class*=modal], [class*=Modal]');
        if (!modal) return { exists: false };
        const title = modal.querySelector('.ant-modal-title, .ant-drawer-title, h3, h4')?.innerText?.trim() || '';
        const fields = Array.from(modal.querySelectorAll('.ant-form-item, label, input, textarea, .ant-select')).map(f => ({
          type: f.tagName,
          label: f.querySelector('.ant-form-item-label, label')?.innerText?.trim() || f.getAttribute('placeholder') || f.getAttribute('aria-label') || '',
          required: !!f.querySelector('.ant-form-item-required, [class*=required]'),
          inputType: f.querySelector('input')?.type || f.tagName.toLowerCase()
        }));
        const buttons = Array.from(modal.querySelectorAll('button')).map(b => b.innerText?.trim()).filter(Boolean);
        return { exists: true, title, fields, buttons, textSnippet: modal.innerText?.substring(0, 300) };
      });
      results.createModal = modalInfo;
      console.log(`  弹窗标题: ${modalInfo.title}`);
      console.log(`  表单字段: ${modalInfo.fields?.length}个`);
      modalInfo.fields?.forEach((f, i) => console.log(`    [${i}] ${f.label} (${f.inputType}) ${f.required ? '*' : ''}`));
      console.log(`  按钮: [${modalInfo.buttons?.join(', ')}]`);

      // 尝试空提交
      const submitBtn = await page.evaluate(() => {
        const modal = document.querySelector('.ant-modal, .ant-drawer');
        if (!modal) return null;
        const btns = Array.from(modal.querySelectorAll('button'));
        const submit = btns.find(b => /确\s*定|创\s*建|保\s*存/.test(b.innerText));
        if (submit && !submit.disabled) { submit.click(); return submit.innerText?.trim(); }
        return null;
      });
      await sleep(1500);

      // 采集验证错误
      const validationErrors = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('.ant-form-item-explain-error, [class*=error], [class*=Error]')).map(e => ({
          text: e.innerText?.trim(),
          visible: e.offsetHeight > 0
        })).filter(e => e.visible && e.text);
      });
      results.createValidation = { submitClicked: submitBtn, errors: validationErrors };
      console.log(`  空提交: ${submitBtn ? '已点击' : '按钮不可用'}`);
      console.log(`  验证错误: ${validationErrors.length}个`);
      validationErrors.forEach(e => console.log(`    ❌ ${e.text}`));

      await ss(page, '03-create-modal');

      // 关闭弹窗
      await page.evaluate(() => {
        const modal = document.querySelector('.ant-modal, .ant-drawer');
        if (modal) {
          const cancelBtn = Array.from(modal.querySelectorAll('button')).find(b => /取\s*消|关\s*闭/.test(b.innerText));
          if (cancelBtn) cancelBtn.click();
          else { const close = modal.querySelector('[class*=close], .ant-modal-close'); if(close) close.click(); }
        }
      });
      await sleep(1000);
    }

    // ═══ Phase 4: 导入模板包 ═══
    console.log('\n═══ Phase 4: 导入模板包 ═══');
    networkLog.length = 0;

    const importClicked = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.innerText.includes('导入') && b.offsetHeight > 0);
      if (btn) { btn.click(); return true; }
      return false;
    });
    await sleep(2000);

    if (importClicked) {
      const importModal = await page.evaluate(() => {
        const modal = document.querySelector('.ant-modal, .ant-drawer, [class*=modal], [class*=upload]');
        if (!modal) return { exists: false };
        const title = modal.querySelector('.ant-modal-title, h3, h4')?.innerText?.trim() || '';
        const hasUpload = !!modal.querySelector('.ant-upload, input[type=file], [class*=upload]');
        const text = modal.innerText?.substring(0, 300) || '';
        const buttons = Array.from(modal.querySelectorAll('button')).map(b => b.innerText?.trim()).filter(Boolean);
        return { exists: true, title, hasUpload, buttons, text };
      });
      results.importModal = importModal;
      console.log(`  弹窗标题: ${importModal.title}`);
      console.log(`  含上传组件: ${importModal.hasUpload}`);
      console.log(`  按钮: [${importModal.buttons?.join(', ')}]`);
      console.log(`  文本: ${importModal.text?.substring(0, 150)}`);
      await ss(page, '04-import-modal');

      // 关闭
      await page.keyboard.press('Escape');
      await sleep(1000);
    }

    // ═══ Phase 5: 卡片操作（逐个） ═══
    console.log('\n═══ Phase 5: 卡片操作（逐张采集） ═══');
    networkLog.length = 0;

    const cardActions = [];
    const cardCount = results.pageStructure.cards.length;
    for (let ci = 0; ci < Math.min(cardCount, 3); ci++) {
      console.log(`\n  ── 卡片[${ci}] ──`);

      // 获取卡片信息
      const cardInfo = await page.evaluate((idx) => {
        const cards = Array.from(document.querySelectorAll('[class*=card], [class*=Card], .ant-card'));
        const card = cards[idx];
        if (!card) return null;
        const name = card.querySelector('[class*=name], [class*=title], h3, h4')?.innerText?.trim() || '';
        const status = card.querySelector('.ant-tag, [class*=status]')?.innerText?.trim() || '';
        const allText = card.innerText?.substring(0, 200) || '';
        return { name, status, text: allText };
      }, ci);
      if (!cardInfo) continue;
      console.log(`  名称: ${cardInfo.name}, 状态: ${cardInfo.status}`);

      // 5a: 查看详情
      console.log(`  → 点击"查看详情"`);
      networkLog.length = 0;
      const detailClicked = await page.evaluate((idx) => {
        const cards = Array.from(document.querySelectorAll('[class*=card], [class*=Card], .ant-card'));
        const card = cards[idx];
        if (!card) return false;
        const links = Array.from(card.querySelectorAll('a, button, [role=button], span'));
        const btn = links.find(l => l.innerText?.trim().includes('查看详情'));
        if (btn) { btn.click(); return true; }
        return false;
      }, ci);
      await sleep(3000);

      if (detailClicked) {
        const detailPage = await page.evaluate(() => {
          const url = window.location.href;
          const title = document.title;
          // 检查是否弹出新页面/模态框
          const modal = document.querySelector('.ant-modal, .ant-drawer, [class*=detail], [class*=Detail]');
          const modalInfo = modal ? { exists: true, title: modal.querySelector('.ant-modal-title, h3')?.innerText?.trim(), text: modal.innerText?.substring(0, 200) } : null;
          // 采集页面字段
          const fields = Array.from(document.querySelectorAll('[class*=field], [class*=Field], [class*=info], [class*=Info], dt, dd, label')).slice(0, 20).map(f => ({
            label: f.querySelector('label, dt, [class*=label]')?.innerText?.trim() || f.getAttribute('title') || '',
            value: f.querySelector('dd, [class*=value], span')?.innerText?.trim()?.substring(0, 50) || ''
          })).filter(f => f.label);
          return { url, title, modal: modalInfo, fields, bodySnippet: document.body.innerText?.substring(0, 300) };
        });
        cardActions.push({ cardIndex: ci, cardName: cardInfo.name, action: '查看详情', result: detailPage, apis: [...networkLog] });
        console.log(`    URL: ${detailPage.url}`);
        console.log(`    模态框: ${detailPage.modal?.exists ? detailPage.modal.title : '无'}`);
        console.log(`    字段: ${detailPage.fields?.length}个`);
        detailPage.fields?.slice(0, 5).forEach(f => console.log(`      ${f.label}: ${f.value}`));
        console.log(`    API调用: ${networkLog.length}个`);
        networkLog.slice(0, 3).forEach(a => console.log(`      ${a.status} ${a.url.substring(0, 80)}`));
        await ss(page, `05-card${ci}-detail`);

        // 返回列表
        await page.goBack();
        await sleep(2000);
        // 如果没goBack成功，重新导航
        if (!page.url().includes('templateManagement') && !page.url().includes('template')) {
          await page.goto(`${BASE}/templateManagement`, { waitUntil: 'networkidle2', timeout: 15000 });
          await sleep(2000);
        }
      }

      // 5b: ... 菜单（更多操作）
      console.log(`  → 点击"..."更多菜单`);
      networkLog.length = 0;
      const menuClicked = await page.evaluate((idx) => {
        const cards = Array.from(document.querySelectorAll('[class*=card], [class*=Card], .ant-card'));
        const card = cards[idx];
        if (!card) return false;
        // 找...按钮或更多图标
        const moreBtn = card.querySelector('[class*=more], .anticon-ellipsis, .anticon-more, [aria-label=more], [aria-label=ellipsis]');
        if (moreBtn) { moreBtn.click(); return 'more'; }
        // 或者直接找...文字
        const dots = Array.from(card.querySelectorAll('span, button')).find(b => b.innerText?.trim() === '...');
        if (dots) { dots.click(); return 'dots'; }
        return false;
      }, ci);
      await sleep(1500);

      if (menuClicked) {
        const menuItems = await page.evaluate(() => {
          const dropdown = document.querySelector('.ant-dropdown, .ant-popover, [class*=dropdown], [class*=menu]');
          if (!dropdown) return [];
          return Array.from(dropdown.querySelectorAll('.ant-dropdown-menu-item, [class*=menuItem], li, a')).map(item => ({
            text: item.innerText?.trim(),
            visible: item.offsetHeight > 0
          })).filter(i => i.visible && i.text);
        });
        cardActions.push({ cardIndex: ci, cardName: cardInfo.name, action: '更多菜单', menuItems });
        console.log(`    菜单项: [${menuItems.map(m => m.text).join(', ')}]`);
        await ss(page, `05-card${ci}-menu`);
        // 关闭菜单
        await page.keyboard.press('Escape');
        await sleep(500);
      }

      // 5c: 置为闲置 / 立即使用
      const statusAction = cardInfo.status === '使用中' ? '置为闲置' : '立即使用';
      console.log(`  → 点击"${statusAction}"`);
      networkLog.length = 0;
      const statusClicked = await page.evaluate((actionText) => {
        const btns = Array.from(document.querySelectorAll('button, a, span, [role=button]'));
        const btn = btns.find(b => b.innerText?.trim().includes(actionText) && b.offsetHeight > 0);
        if (btn) { btn.click(); return true; }
        return false;
      }, statusAction);
      await sleep(2000);

      if (statusClicked) {
        // 检查是否弹出确认框
        const confirmDialog = await page.evaluate(() => {
          const modal = document.querySelector('.ant-modal-confirm, .ant-modal, .ant-popconfirm');
          if (!modal) return { exists: false };
          return {
            exists: true,
            title: modal.querySelector('.ant-modal-confirm-title, .ant-modal-title')?.innerText?.trim() || '',
            content: modal.querySelector('.ant-modal-confirm-content, .ant-modal-body')?.innerText?.trim()?.substring(0, 200) || '',
            buttons: Array.from(modal.querySelectorAll('button')).map(b => b.innerText?.trim()).filter(Boolean)
          };
        });

        cardActions.push({
          cardIndex: ci, cardName: cardInfo.name, action: statusAction,
          confirmDialog, apis: [...networkLog]
        });
        console.log(`    确认弹窗: ${confirmDialog.exists ? '是' : '否'}`);
        if (confirmDialog.exists) {
          console.log(`    标题: ${confirmDialog.title}`);
          console.log(`    内容: ${confirmDialog.content?.substring(0, 100)}`);
          console.log(`    按钮: [${confirmDialog.buttons?.join(', ')}]`);

          // 点击取消/关闭（不真正执行状态变更）
          await page.evaluate(() => {
            const modal = document.querySelector('.ant-modal, .ant-popconfirm');
            if (modal) {
              const cancelBtn = Array.from(modal.querySelectorAll('button')).find(b => /取\s*消|关\s*闭/.test(b.innerText));
              if (cancelBtn) cancelBtn.click();
            }
          });
          await sleep(1000);
        }
        console.log(`    API: ${networkLog.length}个`);
        networkLog.slice(0, 3).forEach(a => console.log(`      ${a.status} ${a.url.substring(0, 80)}`));
        await ss(page, `05-card${ci}-status-action`);
      }
    }
    results.cardActions = cardActions;

    // ═══ Phase 6: 搜索 ═══
    console.log('\n═══ Phase 6: 搜索功能 ═══');
    const searchInput = await page.$('input[placeholder*="名称"], input[placeholder*="搜索"], input[placeholder*="输入"]');
    if (searchInput) {
      await searchInput.click();
      await searchInput.type('测试', { delay: 100 });
      await sleep(1000);

      // 按回车
      await page.keyboard.press('Enter');
      await sleep(2000);

      const searchResults = await page.evaluate(() => {
        const cards = Array.from(document.querySelectorAll('[class*=card], [class*=Card], .ant-card'));
        return cards.map(c => c.querySelector('[class*=name], [class*=title], h3, h4')?.innerText?.trim() || '').filter(Boolean);
      });
      results.search = { query: '测试', resultCount: searchResults.length, names: searchResults };
      console.log(`  搜索"测试"结果: ${searchResults.length}个卡片`);
      searchResults.forEach(n => console.log(`    - ${n}`));
      await ss(page, '06-search');

      // 清除搜索
      await page.evaluate(() => {
        const input = document.querySelector('input[placeholder*="名称"], input[placeholder*="搜索"]');
        if (input) { input.value = ''; input.dispatchEvent(new Event('input', { bubbles: true })); }
        const resetBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('重置'));
        if (resetBtn) resetBtn.click();
      });
      await sleep(1500);
    }

    // ═══ Phase 7: 分页 ═══
    console.log('\n═══ Phase 7: 分页 ═══');
    const pagination = await page.evaluate(() => {
      const pag = document.querySelector('.ant-pagination, [class*=pagination]');
      if (!pag) return { exists: false };
      const total = pag.querySelector('[class*=total]')?.innerText?.trim() || '';
      const pages = Array.from(pag.querySelectorAll('li, button')).map(p => p.innerText?.trim()).filter(Boolean);
      return { exists: true, total, pages };
    });
    results.pagination = pagination;
    console.log(`  分页: ${pagination.exists ? '存在' : '不存在'}`);
    if (pagination.exists) {
      console.log(`  总计: ${pagination.total}`);
      console.log(`  页码: [${pagination.pages?.join(', ')}]`);
    }

    // ═══ 输出汇总 ═══
    console.log('\n════════════════════════════');
    console.log('📊 探查汇总');
    console.log('════════════════════════════');
    console.log(`网络请求总数: ${networkLog.length}`);

    // 保存JSON
    const outputPath = path.join(OUT_DIR, 'template-pkg-probe-results.json');
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
    console.log(`\n📁 结果已保存: ${outputPath}`);

  } catch (e) {
    console.error(`\n❌ 异常: ${e.message}`);
    console.error(e.stack?.substring(0, 300));
    await ss(page, 'error');
  }

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(console.error);
