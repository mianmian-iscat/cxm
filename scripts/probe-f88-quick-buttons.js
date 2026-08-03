#!/usr/bin/env node
/**
 * F88 审核节点参与人快捷按钮 — DOM 结构探查脚本
 * 需求: Aone #84417990
 *
 * 连接 CDP 浏览器，打开审核节点管理页，探查并输出关键 DOM 结构信息。
 * 用于验证测试用例中的 CSS 选择器是否匹配实际页面。
 *
 * 用法：
 *   node scripts/probe-f88-quick-buttons.js
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SCREENSHOT_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');

async function main() {
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  try {
    // ── 1. 导航到审核节点管理页 ──
    console.log('📍 导航到审核节点管理页...');
    await page.goto(`${BASE_URL}/review/node-management`, { waitUntil: 'networkidle2', timeout: 30000 });
    await new Promise(r => setTimeout(r, 3000));

    // ── 2. 验证列表页基本信息 ──
    const listInfo = await page.evaluate(() => {
      const rows = document.querySelectorAll('.ant-table-row');
      return { rowCount: rows.length, title: document.title };
    });
    console.log(`✅ 列表页加载完成: ${listInfo.rowCount} 行数据`);

    // ── 3. 点击编辑 ──
    console.log('📍 点击第一行编辑按钮...');
    const editResult = await page.evaluate(() => {
      const rows = document.querySelectorAll('.ant-table-row');
      if (rows.length === 0) return { clicked: false, error: 'no rows' };
      const btns = Array.from(rows[0].querySelectorAll('button'));
      const editBtn = btns.find(b => b.textContent.trim() === '编辑');
      if (editBtn) { editBtn.click(); return { clicked: true }; }
      return { clicked: false, error: 'no edit btn' };
    });
    if (!editResult.clicked) { console.error('❌ 无法点击编辑:', editResult.error); return; }
    await new Promise(r => setTimeout(r, 3000));

    // ── 4. 探查编辑页结构 ──
    console.log('\n═══ 编辑页 DOM 结构探查 ═══\n');

    const editPageInfo = await page.evaluate(() => {
      const result = {};

      // 4.1 页面类型
      result.hasDrawer = !!document.querySelector('.ant-drawer');
      result.hasModal = !!document.querySelector('.ant-modal');
      result.hasInlineForm = !!document.querySelector('.ant-form');

      // 4.2 已选参与人标签
      const labelContainer = document.querySelector('[class*=selectedLabel]');
      result.labelContainer = labelContainer ? {
        tag: labelContainer.tagName,
        className: labelContainer.className.slice(0, 120),
        text: labelContainer.textContent.trim().slice(0, 80),
      } : null;

      // 4.3 三个快捷按钮
      const allBtns = Array.from(document.querySelectorAll('button'));
      const quickBtns = allBtns.filter(b => {
        const t = b.textContent.trim();
        return t === '复制' || t === '批量填写' || t === '清空';
      });
      result.quickButtons = quickBtns.map(b => ({
        text: b.textContent.trim(),
        className: b.className.slice(0, 120),
        disabled: b.disabled,
        parentClass: (b.parentElement?.className || '').slice(0, 80),
        rect: (() => { const r = b.getBoundingClientRect(); return { top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height) }; })(),
      }));

      // 4.4 参与人标签（ant-select-selection-item）
      const participantSection = document.querySelector('[class*=participantSection]') || document.querySelector('[class*=selectedLabel]');
      if (participantSection) {
        const items = participantSection.querySelectorAll('.ant-select-selection-item');
        result.participantItems = {
          count: items.length,
          samples: Array.from(items).slice(0, 5).map(i => ({
            tag: i.tagName,
            className: i.className.slice(0, 80),
            text: i.textContent.trim().slice(0, 30),
          })),
        };
      }

      // 4.5 form-item 结构
      const formItems = document.querySelectorAll('.ant-form-item');
      result.formItems = Array.from(formItems).map(item => {
        const label = item.querySelector('.ant-form-item-label');
        return {
          label: label ? label.textContent.trim() : 'N/A',
          className: item.className.slice(0, 80),
        };
      }).filter(f => f.label !== 'N/A');

      return result;
    });

    console.log('── 页面容器类型 ──');
    console.log(`  Drawer: ${editPageInfo.hasDrawer ? '✅' : '❌'}`);
    console.log(`  Modal:  ${editPageInfo.hasModal ? '✅' : '❌'}`);
    console.log(`  Inline Form: ${editPageInfo.hasInlineForm ? '✅' : '❌'}`);

    console.log('\n── 已选参与人标签容器 ──');
    if (editPageInfo.labelContainer) {
      console.log(`  Tag: ${editPageInfo.labelContainer.tag}`);
      console.log(`  Class: ${editPageInfo.labelContainer.className}`);
      console.log(`  Text: ${editPageInfo.labelContainer.text}`);
    } else {
      console.log('  ❌ 未找到');
    }

    console.log('\n── 三个快捷按钮 ──');
    console.log(`  找到 ${editPageInfo.quickButtons.length} 个:`);
    for (const btn of editPageInfo.quickButtons) {
      console.log(`  [${btn.text}] disabled=${btn.disabled} pos=(${btn.rect.left},${btn.rect.top}) class=${btn.className.slice(0, 60)}`);
    }

    console.log('\n── 参与人选择项 ──');
    if (editPageInfo.participantItems) {
      console.log(`  Count: ${editPageInfo.participantItems.count}`);
      console.log(`  Selector: .ant-select-selection-item`);
      for (const s of editPageInfo.participantItems.samples) {
        console.log(`    "${s.text}"`);
      }
    }

    console.log('\n── 表单项标签 ──');
    for (const f of editPageInfo.formItems) {
      console.log(`  "${f.label}"`);
    }

    // ── 5. 测试批量填写弹窗 ──
    console.log('\n═══ 批量填写弹窗探查 ═══\n');
    const batchInfo = await page.evaluate(async () => {
      const btns = Array.from(document.querySelectorAll('button'));
      const batchBtn = btns.find(b => b.textContent.trim() === '批量填写');
      if (!batchBtn) return { error: 'no batch btn' };
      batchBtn.click();
      await new Promise(r => setTimeout(r, 1500));

      const modal = document.querySelector('.ant-modal');
      if (!modal) return { error: 'no modal' };

      const info = {
        title: modal.querySelector('.ant-modal-title')?.textContent?.trim() || 'N/A',
        bodyText: modal.querySelector('.ant-modal-body')?.textContent?.trim().slice(0, 200) || 'N/A',
        hasTextarea: !!modal.querySelector('textarea'),
        textareaPlaceholder: modal.querySelector('textarea')?.placeholder || 'N/A',
        footerBtns: Array.from(modal.querySelectorAll('.ant-modal-footer button')).map(b => b.textContent.trim()),
      };

      // 关闭弹窗
      const cancelBtn = modal.querySelector('.ant-modal-footer button');
      if (cancelBtn) cancelBtn.click();
      await new Promise(r => setTimeout(r, 500));
      return info;
    });
    console.log(`  Title: ${batchInfo.title}`);
    console.log(`  Body: ${batchInfo.bodyText}`);
    console.log(`  Textarea: ${batchInfo.hasTextarea ? '✅' : '❌'} (placeholder: ${batchInfo.textareaPlaceholder})`);
    console.log(`  Footer Buttons: ${(batchInfo.footerBtns || []).join(', ')}`);

    // ── 6. 测试清空确认气泡 ──
    console.log('\n═══ 清空确认气泡探查 ═══\n');
    const clearInfo = await page.evaluate(async () => {
      const btns = Array.from(document.querySelectorAll('button'));
      const clearBtn = btns.find(b => b.textContent.trim() === '清空');
      if (!clearBtn) return { error: 'no clear btn' };
      clearBtn.click();
      await new Promise(r => setTimeout(r, 1000));

      const popconfirm = document.querySelector('.ant-popconfirm');
      if (!popconfirm) return { error: 'no popconfirm' };

      const info = {
        text: popconfirm.textContent.trim().slice(0, 100),
        btns: Array.from(popconfirm.querySelectorAll('button')).map(b => b.textContent.trim()),
        className: popconfirm.className.slice(0, 100),
        visible: popconfirm.offsetHeight > 0,
      };

      // 关闭气泡（点取消）
      const cancelBtn = Array.from(popconfirm.querySelectorAll('button')).find(b => b.textContent.trim() === '取消');
      if (cancelBtn) cancelBtn.click();
      return info;
    });
    console.log(`  Text: ${clearInfo.text}`);
    console.log(`  Buttons: ${(clearInfo.btns || []).join(', ')}`);
    console.log(`  Visible: ${clearInfo.visible}`);

    // ── 7. 截图 ──
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const shotPath = path.join(SCREENSHOT_DIR, 'probe-quick-buttons.jpg');
    await page.screenshot({ path: shotPath, type: 'jpeg', quality: 70 });
    console.log(`\n📸 截图: ${shotPath}`);

    // ── 输出选择器验证摘要 ──
    console.log('\n═══ 选择器验证摘要 ═══\n');
    const checks = [
      { name: '.ant-table-row (列表行)', ok: listInfo.rowCount > 0 },
      { name: '编辑按钮 (button:编辑)', ok: editResult.clicked },
      { name: '已选参与人标签 ([class*=selectedLabel])', ok: !!editPageInfo.labelContainer },
      { name: '复制按钮', ok: editPageInfo.quickButtons.some(b => b.text === '复制') },
      { name: '批量填写按钮', ok: editPageInfo.quickButtons.some(b => b.text === '批量填写') },
      { name: '清空按钮', ok: editPageInfo.quickButtons.some(b => b.text === '清空') },
      { name: '.ant-select-selection-item (参与人标签)', ok: (editPageInfo.participantItems?.count || 0) > 0 },
      { name: '批量填写Modal (.ant-modal)', ok: !!batchInfo.title },
      { name: '确认导入按钮', ok: (batchInfo.footerBtns || []).some(t => t.includes('确认导入')) },
      { name: '清空Popconfirm (.ant-popconfirm)', ok: !!clearInfo.text },
      { name: '确认清空按钮', ok: (clearInfo.btns || []).some(t => t.includes('确认清空')) },
    ];
    let passCount = 0;
    for (const c of checks) {
      const icon = c.ok ? '✅' : '❌';
      if (c.ok) passCount++;
      console.log(`  ${icon} ${c.name}`);
    }
    console.log(`\n  结果: ${passCount}/${checks.length} 通过`);

  } catch (e) {
    console.error('❌ 错误:', e.message);
  } finally {
    await page.close();
  }
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
