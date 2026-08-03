#!/usr/bin/env node
/**
 * 探查链路20180审核任务的工具栏按钮
 * 验证：局部修改按钮是否在DOM中存在
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots', 'toolbar-probe');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ss(page, name) {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
  const fp = path.join(SS_DIR, `${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
  return fp;
}

async function main() {
  console.log('🔍 探查链路20180审核任务工具栏按钮');
  console.log(`  CDP: ${CDP_URL}\n`);

  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  try {
    // Step 1: 打开个人任务中心
    console.log('Step 1: 打开个人任务中心...');
    await page.goto(`${BASE}/review/personal-task-center`, {
      waitUntil: 'networkidle2', timeout: 30000
    });
    await sleep(3000);
    await ss(page, '01-task-center');

    // Step 2: 筛选待审核
    console.log('Step 2: 筛选待审核任务...');
    const filterClicked = await page.evaluate(() => {
      const selects = document.querySelectorAll('.ant-select');
      for (const s of selects) {
        if (s.innerText.includes('审核状态') || s.innerText.includes('全部')) {
          s.querySelector('.ant-select-selector')?.click();
          return true;
        }
      }
      return false;
    });
    await sleep(1000);
    
    // 选择待审核
    await page.evaluate(() => {
      const options = document.querySelectorAll('.ant-select-item-option-content');
      for (const opt of options) {
        if (opt.innerText.trim() === '待审核') {
          opt.click();
          return true;
        }
      }
      return false;
    });
    await sleep(2000);
    await ss(page, '02-filtered');

    // Step 3: 找到任务并进入审核
    console.log('Step 3: 进入审核详情...');
    const auditClicked = await page.evaluate(() => {
      // 优先找"开始任务"，其次"查看详情"
      const links = Array.from(document.querySelectorAll('a, button, span'));
      const startBtn = links.find(b => b.innerText.trim() === '开始任务' && b.offsetHeight > 0);
      if (startBtn) { startBtn.click(); return 'startTask'; }
      const detailBtn = links.find(b => b.innerText.trim() === '查看详情' && b.offsetHeight > 0);
      if (detailBtn) { detailBtn.click(); return 'viewDetail'; }
      return null;
    });
    console.log(`  点击: ${auditClicked}`);
    
    if (!auditClicked) {
      console.log('  ❌ 未找到开始任务/查看详情按钮');
      await ss(page, 'no-audit-btn');
      return;
    }
    await sleep(4000);

    // 如果弹出确认框，点击确认
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const confirmBtn = btns.find(b => /确[定认]|开始/.test(b.innerText.trim()) && b.offsetHeight > 0);
      if (confirmBtn) confirmBtn.click();
    });
    await sleep(3000);
    await ss(page, '03-audit-view');

    // Step 3b: 如果是任务列表页，点击行内“审核”链接进入图片审核
    console.log('Step 3b: 点击行内审核链接...');
    const rowClicked = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a, span'));
      const reviewLink = links.find(b => b.innerText.trim() === '审核' && b.offsetHeight > 0 && b.closest('tr'));
      if (reviewLink) { reviewLink.click(); return true; }
      return false;
    });
    if (rowClicked) {
      console.log('  已点击行内审核链接');
      await sleep(4000);
      // 检查是否有确认弹窗
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('.ant-modal button, .ant-drawer button'));
        const okBtn = btns.find(b => /确[定认]|开始/.test(b.innerText.trim()) && b.offsetHeight > 0);
        if (okBtn) okBtn.click();
      });
      await sleep(3000);
      await ss(page, '03b-image-review');
    }

    // Step 4: 获取页面信息
    console.log('\nStep 4: 获取审核页面信息...');
    const pageInfo = await page.evaluate(() => {
      // 获取任务信息
      const headerText = document.querySelector('[class*="header"]')?.innerText || '';
      const bodyText = document.body.innerText.substring(0, 500);
      
      // 检查组件类型
      const hasSingleImage = !!document.querySelector('[class*="SingleImageReview"]');
      const hasSetImage = !!document.querySelector('[class*="SetImageReview"]');
      const hasCoverImage = !!document.querySelector('[class*="CoverImageReview"]');
      
      return {
        headerText: headerText.substring(0, 200),
        bodySnippet: bodyText,
        componentType: hasSingleImage ? 'SingleImageReview' : 
                       hasSetImage ? 'SetImageReview' :
                       hasCoverImage ? 'CoverImageReview' : 'Unknown',
        url: window.location.href
      };
    });
    console.log(`  组件类型: ${pageInfo.componentType}`);
    console.log(`  URL: ${pageInfo.url}`);

    // Step 5: 搜索所有 actionItem 按钮
    console.log('\nStep 5: 搜索工具栏按钮...');
    const buttons = await page.evaluate(() => {
      const results = {
        allActionItems: [],
        imageActionsContainers: [],
        tooltipButtons: [],
        imgAltButtons: [],
        editOutlinedButtons: [],
        shouldShowTab: null,
      };

      // 搜索所有 actionItem
      document.querySelectorAll('[class*="actionItem"]').forEach((el, i) => {
        const tooltip = el.closest('[class*="ant-tooltip"]') || 
                        el.parentElement?.closest('.ant-tooltip-open');
        const title = el.closest('.ant-tooltip-inner')?.textContent || 
                      el.getAttribute('title') || '';
        const rect = el.getBoundingClientRect();
        const parentClass = el.parentElement?.className || '';
        const parentDisplay = el.parentElement ? 
          window.getComputedStyle(el.parentElement).display : 'unknown';
        
        results.allActionItems.push({
          index: i,
          title: title,
          text: el.innerText?.trim()?.substring(0, 30) || '',
          alt: el.querySelector('img')?.alt || '',
          iconType: el.querySelector('[class*="anticon"]')?.getAttribute('aria-label') || 
                    el.querySelector('[class*="anticon"]')?.className?.match(/anticon-(\w+)/)?.[1] || '',
          parentClass: parentClass.substring(0, 60),
          parentDisplay,
          visible: rect.width > 0 && rect.height > 0,
          rect: { w: Math.round(rect.width), h: Math.round(rect.height) }
        });
      });

      // 搜索所有 imageActions 容器
      document.querySelectorAll('[class*="imageActions"]').forEach((el, i) => {
        const style = window.getComputedStyle(el);
        const childCount = el.querySelectorAll('[class*="actionItem"]').length;
        results.imageActionsContainers.push({
          index: i,
          display: style.display,
          visibility: style.visibility,
          childActionItems: childCount,
          className: el.className.substring(0, 80)
        });
      });

      // 搜索所有 Tooltip 包裹的按钮
      document.querySelectorAll('.ant-tooltip').forEach(el => {
        const title = el.querySelector('.ant-tooltip-inner')?.textContent || '';
        if (title && /局部修改|替换|下载|裁剪|高清化|负反馈|复位|复制|编辑/.test(title)) {
          results.tooltipButtons.push({
            title,
            visible: el.offsetHeight > 0
          });
        }
      });

      // 搜索 img[alt] 按钮
      document.querySelectorAll('img[alt]').forEach(img => {
        if (/局部修改|替换|下载|裁剪|高清化|负反馈|复位|复制URL|编辑/.test(img.alt)) {
          results.imgAltButtons.push({
            alt: img.alt,
            visible: img.offsetHeight > 0 && img.getBoundingClientRect().width > 0
          });
        }
      });

      // 搜索 EditOutlined (局部修改图标)
      document.querySelectorAll('[aria-label="edit"], .anticon-edit').forEach(el => {
        results.editOutlinedButtons.push({
          tagName: el.tagName,
          visible: el.offsetHeight > 0,
          parentTitle: el.closest('.ant-tooltip-inner')?.textContent || ''
        });
      });

      return results;
    });

    // 输出结果
    console.log(`\n📊 搜索结果:`);
    console.log(`  actionItem 总数: ${buttons.allActionItems.length}`);
    console.log(`  imageActions 容器: ${buttons.imageActionsContainers.length}`);
    console.log(`  Tooltip 按钮: ${buttons.tooltipButtons.length}`);
    console.log(`  img[alt] 按钮: ${buttons.imgAltButtons.length}`);
    console.log(`  EditOutlined: ${buttons.editOutlinedButtons.length}`);

    console.log(`\n📋 imageActions 容器详情:`);
    buttons.imageActionsContainers.forEach((c, i) => {
      console.log(`  [${i}] display=${c.display}, 子按钮=${c.childActionItems}, class=${c.className}`);
    });

    console.log(`\n📋 actionItem 详情:`);
    buttons.allActionItems.forEach((b, i) => {
      const label = b.title || b.alt || b.iconType || b.text || '(unknown)';
      console.log(`  [${i}] ${label} | visible=${b.visible} | parentDisplay=${b.parentDisplay} | ${b.rect.w}x${b.rect.h}`);
    });

    console.log(`\n📋 Tooltip 按钮:`);
    buttons.tooltipButtons.forEach((b, i) => {
      console.log(`  [${i}] "${b.title}" visible=${b.visible}`);
    });

    console.log(`\n📋 img[alt] 按钮:`);
    buttons.imgAltButtons.forEach((b, i) => {
      console.log(`  [${i}] alt="${b.alt}" visible=${b.visible}`);
    });

    console.log(`\n📋 EditOutlined (局部修改图标):`);
    buttons.editOutlinedButtons.forEach((b, i) => {
      console.log(`  [${i}] ${b.tagName} visible=${b.visible} title="${b.parentTitle}"`);
    });

    // Step 6: 尝试 hover 触发工具栏
    console.log('\nStep 6: hover 审核图片触发工具栏...');
    const imgEl = await page.$('.ant-drawer img, [class*="reviewSection"] img, [class*="mainImageArea"] img');
    if (imgEl) {
      const box = await imgEl.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await sleep(1500);
        await ss(page, '04-after-hover');

        // 重新检查
        const afterHover = await page.evaluate(() => {
          const containers = [];
          document.querySelectorAll('[class*="imageActions"]').forEach((el, i) => {
            const style = window.getComputedStyle(el);
            const childCount = el.querySelectorAll('[class*="actionItem"]').length;
            containers.push({
              index: i,
              display: style.display,
              childActionItems: childCount
            });
          });

          const tooltips = [];
          document.querySelectorAll('.ant-tooltip').forEach(el => {
            const title = el.querySelector('.ant-tooltip-inner')?.textContent || '';
            if (title && /局部修改|替换|下载|裁剪|高清化|负反馈|复位|复制|编辑/.test(title)) {
              const rect = el.getBoundingClientRect();
              tooltips.push({
                title,
                visible: rect.width > 0 && rect.height > 0
              });
            }
          });

          return { containers, tooltips };
        });

        console.log(`\n📊 hover 后结果:`);
        afterHover.containers.forEach((c, i) => {
          console.log(`  imageActions[${i}] display=${c.display} children=${c.childActionItems}`);
        });
        afterHover.tooltips.forEach((t, i) => {
          console.log(`  tooltip[${i}] "${t.title}" visible=${t.visible}`);
        });
      }
    }

    // Step 7: Force display 并再次检查
    console.log('\nStep 7: force display:flex 所有 imageActions...');
    const forceResult = await page.evaluate(() => {
      document.querySelectorAll('[class*="imageActions"]').forEach(el => {
        el.style.display = 'flex';
      });
      // 重新收集
      const items = [];
      document.querySelectorAll('[class*="actionItem"]').forEach((el, i) => {
        const tooltip = el.closest('.ant-tooltip-inner')?.textContent || 
                       el.getAttribute('title') || '';
        const alt = el.querySelector('img')?.alt || '';
        const icon = el.querySelector('[class*="anticon"]')?.className?.match(/anticon-(\w+)/)?.[1] || '';
        const label = tooltip || alt || icon || el.innerText?.trim()?.substring(0, 20) || '';
        items.push({ index: i, label, visible: el.getBoundingClientRect().width > 0 });
      });
      return items;
    });

    console.log(`\n📊 force display 后所有 actionItem:`);
    forceResult.forEach((b, i) => {
      console.log(`  [${i}] "${b.label}" visible=${b.visible}`);
    });

    // 最终判断
    const hasLocalModify = forceResult.some(b => /局部修改|edit/i.test(b.label));
    console.log(`\n${hasLocalModify ? '✅' : '❌'} 局部修改按钮: ${hasLocalModify ? '存在' : '不存在'}`);
    
    const uniqueLabels = [...new Set(forceResult.map(b => b.label).filter(Boolean))];
    console.log(`\n📋 去重后按钮列表 (${uniqueLabels.length}个):`);
    uniqueLabels.forEach(l => console.log(`  - ${l}`));

    await ss(page, '05-final');

  } catch (e) {
    console.error(`\n❌ 异常: ${e.message}`);
    await ss(page, 'error');
  }

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(console.error);
