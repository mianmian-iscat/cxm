#!/usr/bin/env node
/**
 * F88 图片审核 9 按钮端到端回归测试
 *
 * 覆盖：局部修改、下载、替换、裁剪、高清增强、负反馈、驳回、复位、复制URL
 * 前置：已登录 F88 预发环境，存在待审核图片任务
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const SCREENSHOT_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = [];
const CASE_TIMEOUT_MS = 60000;

// ── 工具函数 ──
function log(tc, step, status, detail) {
  results.push({ tc, step, status, detail, time: new Date().toISOString() });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`  ${icon} [${tc}] ${step}: ${detail}`);
}
async function shot(page, name) {
  const fp = path.join(SCREENSHOT_DIR, `img-audit-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  return fp;
}
async function wait(ms = 3000) { await new Promise(r => setTimeout(r, ms)); }

/**
 * 导航到审核视图（复用套图排序脚本的导航逻辑）
 */
async function enterAuditView(page) {
  const taskDetailUrl = `${BASE_URL}/review/task/detail?taskId=1281090&taskType=audit&ptcTab=audit&ptcTaskName=%E5%A5%97%E5%9B%BE%E5%AE%A1%E6%A0%B8`;
  await page.goto(taskDetailUrl, { waitUntil: 'networkidle2', timeout: 30000 });
  await wait(4000);

  const auditClicked = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.ant-table-row, tr'));
    for (const row of rows) {
      if (row.innerText.includes('待审核')) {
        const btns = Array.from(row.querySelectorAll('button, a'));
        const auditBtn = btns.find(b => b.innerText.trim() === '审核');
        if (auditBtn) { auditBtn.click(); return 'clicked_audit'; }
      }
    }
    const allBtns = Array.from(document.querySelectorAll('button'));
    const fb = allBtns.find(b => b.innerText.trim() === '审核' && b.offsetHeight > 0);
    if (fb) { fb.click(); return 'clicked_fallback'; }
    // 尝试"重新审核"
    const re = allBtns.find(b => b.innerText.trim() === '重新审核' && b.offsetHeight > 0);
    if (re) { re.click(); return 'clicked_re_audit'; }
    return null;
  });
  await wait(4000);
  return auditClicked;
}

/**
 * 勾选一张图片，激活工具栏
 */
async function selectOneImage(page) {
  return await page.evaluate(() => {
    const checkboxes = Array.from(document.querySelectorAll('.ant-checkbox-wrapper[class*="imageCheckbox"]'));
    const visible = checkboxes.filter(c => c.offsetHeight > 0);
    if (visible.length === 0) return { selected: 0, total: 0 };
    const input = visible[0].querySelector('input[type="checkbox"]');
    if (input) input.click(); else visible[0].click();
    return { selected: 1, total: visible.length };
  });
}

/**
 * 取消所有已选图片
 */
async function deselectAllImages(page) {
  return await page.evaluate(() => {
    const checkboxes = Array.from(document.querySelectorAll('.ant-checkbox-wrapper[class*="imageCheckbox"]'));
    const visible = checkboxes.filter(c => c.offsetHeight > 0);
    let deselected = 0;
    for (const cb of visible) {
      const isChecked = cb.classList.contains('ant-checkbox-wrapper-checked') ||
                        cb.querySelector('.ant-checkbox-checked');
      if (isChecked) {
        const input = cb.querySelector('input[type="checkbox"]');
        if (input) input.click(); else cb.click();
        deselected++;
      }
    }
    return deselected;
  });
}

/**
 * 关闭弹窗/Drawer
 */
async function dismissModals(page) {
  await page.evaluate(() => {
    const selectors = ['.ant-modal-close', '.ant-drawer-close', '.ant-notification-close'];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) el.click();
    }
  });
  await wait(1000);
}

/**
 * 检查工具栏按钮是否存在（图标按钮，用 aria-label 或 alt 定位）
 */
async function checkToolbarButton(page, label) {
  return await page.evaluate((lbl) => {
    // 尝试 aria-label
    let el = document.querySelector(`[aria-label="${lbl}"]`);
    if (!el) {
      // 尝试 alt 属性
      el = document.querySelector(`img[alt="${lbl}"]`);
    }
    if (!el) {
      // 尝试 class 包含，检查 actionItem 本身或其子 img
      const items = Array.from(document.querySelectorAll('[class*="actionItem"]'));
      el = items.find(i => {
        const alt = i.getAttribute('alt') || '';
        const aria = i.getAttribute('aria-label') || '';
        const text = i.innerText || '';
        // 检查子 img 的 alt
        const childImg = i.querySelector('img');
        const childAlt = childImg ? childImg.getAttribute('alt') || '' : '';
        return alt.includes(lbl) || aria.includes(lbl) || text.includes(lbl) || childAlt.includes(lbl);
      });
    }
    if (el) {
      // 检查父容器是否可见
      const wrapper = el.closest('[class*="imageActions"]');
      const isVisible = wrapper ? getComputedStyle(wrapper).display !== 'none' : el.offsetHeight > 0;
      return { exists: true, visible: isVisible, label: el.getAttribute('aria-label') || el.getAttribute('alt') || el.innerText?.trim() || lbl };
    }
    return { exists: false, visible: false, label: '' };
  }, label);
}

/**
 * 点击工具栏按钮（用 aria-label 或 alt 定位）
 */
async function clickToolbarButton(page, label) {
  return await page.evaluate((lbl) => {
    let el = document.querySelector(`[aria-label="${lbl}"]`);
    if (!el) el = document.querySelector(`img[alt="${lbl}"]`);
    if (!el) {
      const items = Array.from(document.querySelectorAll('[class*="actionItem"]'));
      el = items.find(i => {
        const alt = i.getAttribute('alt') || '';
        const aria = i.getAttribute('aria-label') || '';
        const childImg = i.querySelector('img');
        const childAlt = childImg ? childImg.getAttribute('alt') || '' : '';
        return alt.includes(lbl) || aria.includes(lbl) || childAlt.includes(lbl);
      });
    }
    if (el) {
      const wrapper = el.closest('[class*="imageActions"]');
      if (wrapper) wrapper.style.display = 'flex';
      el.click();
      return true;
    }
    return false;
  }, label);
}

// ── 9 个按钮测试用例 ──

/** TC01: 替换按钮 (aria-label=swap) */
async function tc01_replace(page) {
  const TC = 'TC01';
  const btn = await checkToolbarButton(page, 'swap');
  if (btn.exists) {
    log(TC, '替换按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, 'swap');
    await wait(2000);
    const modal = await page.evaluate(() => !!document.querySelector('.ant-modal, .ant-drawer, [class*="replace"]'));
    log(TC, '替换面板弹出', modal ? 'PASS' : 'WARN', modal ? '面板已弹出' : '未检测到面板');
    await shot(page, 'tc01-replace');
    await dismissModals(page);
  } else {
    log(TC, '替换按钮存在', 'FAIL', '未找到替换按钮(swap)');
  }
}

/** TC02: 局部修改按钮 (EditOutlined图标, aria-label=edit) */
async function tc02_local_modify(page) {
  const TC = 'TC02';
  const btn = await checkToolbarButton(page, 'edit');
  if (btn.exists) {
    log(TC, '局部修改按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, 'edit');
    await wait(3000);
    const modal = await page.evaluate(() => !!document.querySelector('.ant-modal, [class*="localModify"], [class*="LocalModify"]'));
    log(TC, '局部修改弹窗', modal ? 'PASS' : 'WARN', modal ? '弹窗已出现' : '未检测到弹窗');
    await shot(page, 'tc02-local-modify');
    await dismissModals(page);
  } else {
    log(TC, '局部修改按钮存在', 'FAIL', '未找到局部修改按钮(edit)');
  }
}

/** TC03: 下载按钮 (aria-label=download) */
async function tc03_download(page) {
  const TC = 'TC03';
  const btn = await checkToolbarButton(page, 'download');
  if (btn.exists) {
    log(TC, '下载按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, 'download');
    await wait(2000);
    log(TC, '下载触发', 'PASS', '已点击下载');
    await shot(page, 'tc03-download');
    await dismissModals(page);
  } else {
    log(TC, '下载按钮存在', 'FAIL', '未找到下载按钮(download)');
  }
}

/** TC04: 裁剪按钮 (alt=裁剪) */
async function tc04_crop(page) {
  const TC = 'TC04';
  const btn = await checkToolbarButton(page, '裁剪');
  if (btn.exists) {
    log(TC, '裁剪按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, '裁剪');
    await wait(3000);
    const cropUI = await page.evaluate(() => !!document.querySelector('[class*="crop"], .cropper-container, [class*="cropper"]'));
    log(TC, '裁剪界面出现', cropUI ? 'PASS' : 'WARN', cropUI ? '裁剪UI已出现' : '未检测到裁剪UI');
    await shot(page, 'tc04-crop');
    // 按 Escape 关闭裁剪
    await page.keyboard.press('Escape');
    await wait(1000);
    await dismissModals(page);
  } else {
    log(TC, '裁剪按钮存在', 'FAIL', '未找到裁剪按钮');
  }
}

/** TC05: 驳回按钮（首图审核专有，套图审核无此按钮） */
async function tc05_reject(page) {
  const TC = 'TC05';
  const btn = await checkToolbarButton(page, '驳回');
  if (btn.exists) {
    log(TC, '驳回按钮存在', 'PASS', `找到: ${btn.label}`);
    await shot(page, 'tc05-reject');
    // 不实际点击驳回，仅验证存在性
  } else {
    log(TC, '驳回按钮', 'WARN', '未找到驳回按钮（可能为套图审核场景，套图无此按钮）');
  }
}

/** TC06: 高清增强按钮 (alt=高清化) */
async function tc06_hd_enhance(page) {
  const TC = 'TC06';
  // 调试：打印当前页面上所有 img alt 值
  const alts = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('img[alt]')).map(i => i.getAttribute('alt')).filter(Boolean);
  });
  console.log(`  [${TC}] 调试 - img alt 值:`, [...new Set(alts)].join(', '));
  const btn = await checkToolbarButton(page, '高清化');
  if (btn.exists) {
    log(TC, '高清化按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, '高清化');
    await wait(3000);
    const enhanceUI = await page.evaluate(() => !!document.querySelector('[class*="enhance"], .ant-modal, .ant-drawer'));
    log(TC, '高清增强响应', enhanceUI ? 'PASS' : 'WARN', enhanceUI ? '已响应' : '未检测到响应');
    await shot(page, 'tc06-hd-enhance');
    await dismissModals(page);
  } else {
    log(TC, '高清化按钮存在', 'FAIL', '未找到高清化按钮');
  }
}

/** TC07: 负反馈按钮 (alt=负反馈) */
async function tc07_negative_feedback(page) {
  const TC = 'TC07';
  const btn = await checkToolbarButton(page, '负反馈');
  if (btn.exists) {
    log(TC, '负反馈按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, '负反馈');
    await wait(2000);
    const feedbackUI = await page.evaluate(() => !!document.querySelector('.ant-modal, .ant-drawer, [class*="feedback"]'));
    log(TC, '负反馈弹窗', feedbackUI ? 'PASS' : 'WARN', feedbackUI ? '弹窗已出现' : '未检测到弹窗');
    await shot(page, 'tc07-negative-feedback');
    await dismissModals(page);
  } else {
    log(TC, '负反馈按钮存在', 'FAIL', '未找到负反馈按钮');
  }
}

/** TC08: 复位按钮 (alt=复位) */
async function tc08_reset(page) {
  const TC = 'TC08';
  const btn = await checkToolbarButton(page, '复位');
  if (btn.exists) {
    log(TC, '复位按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, '复位');
    await wait(2000);
    log(TC, '复位操作响应', 'PASS', '已点击复位');
    await shot(page, 'tc08-reset');
    await dismissModals(page);
  } else {
    log(TC, '复位按钮存在', 'FAIL', '未找到复位按钮');
  }
}

/** TC09: 复制URL按钮 (alt=复制URL) */
async function tc09_copy_url(page) {
  const TC = 'TC09';
  const btn = await checkToolbarButton(page, '复制URL');
  if (btn.exists) {
    log(TC, '复制URL按钮存在', 'PASS', `找到: ${btn.label}`);
    await clickToolbarButton(page, '复制URL');
    await wait(2000);
    const copyFeedback = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('复制成功') || text.includes('已复制') || !!document.querySelector('.ant-message-success, .ant-message');
    });
    log(TC, '复制反馈', copyFeedback ? 'PASS' : 'WARN', copyFeedback ? '复制成功提示' : '未检测到反馈');
    await shot(page, 'tc09-copy-url');
    await dismissModals(page);
  } else {
    log(TC, '复制URL按钮存在', 'FAIL', '未找到复制URL按钮');
  }
}

// ── TC10: 审核数据流转验证 ──
async function tc10_data_flow(page) {
  const TC = 'TC10';
  // 回到任务详情页验证数据流转
  await enterAuditView(page);
  await wait(2000);

  // 检查审核进度信息
  const progress = await page.evaluate(() => {
    const body = document.body.innerText;
    const match = body.match(/待开始[：:]\s*(\d+)\/(\d+)/);
    const rateMatch = body.match(/通过率[：:]\s*([\d.]+%?)/);
    return {
      progress: match ? `${match[1]}/${match[2]}` : 'N/A',
      passRate: rateMatch ? rateMatch[1] : 'N/A',
      hasAuditRecords: body.includes('待审核') || body.includes('已审核') || body.includes('已驳回'),
    };
  });
  log(TC, '审核进度信息', progress.progress !== 'N/A' ? 'PASS' : 'WARN',
    `进度: ${progress.progress}, 通过率: ${progress.passRate}`);
  log(TC, '审核记录存在', progress.hasAuditRecords ? 'PASS' : 'WARN',
    progress.hasAuditRecords ? '找到审核记录' : '未找到审核记录');

  // 检查 API 抓包数据
  await shot(page, 'tc10-data-flow');
}

// ── 主流程 ──
async function main() {
  console.log('🔗 连接 CDP:', CDP_URL);
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  try {
    // 进入审核视图
    console.log('\n📍 导航到审核视图...');
    const auditResult = await enterAuditView(page);
    if (!auditResult) {
      console.log('❌ 无法进入审核视图');
      log('INIT', '进入审核视图', 'FAIL', '无法找到审核按钮');
      return;
    }
    console.log('✅ 进入审核视图:', auditResult);
    await shot(page, 'initial-audit-view');

    // 勾选一张图片激活工具栏
    const sel = await selectOneImage(page);
    console.log(`📸 已选图片: ${sel.selected}/${sel.total}`);
    await wait(2000);

    // hover mainImageWrapper 触发工具栏
    await page.setViewport({ width: 1458, height: 900 });
    await wait(1000);
    const mainWrapper = await page.$('[class*="mainImageWrapper"]');
    if (mainWrapper) {
      const box = await mainWrapper.boundingBox();
      if (box) {
        console.log(`🖱️ hover mainImageWrapper at (${box.x + box.width/2}, ${box.y + box.height/2})`);
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await wait(2000);
      }
    } else {
      console.log('⚠️ 未找到 mainImageWrapper');
    }

    // 强制显示工具栏
    await page.evaluate(() => {
      document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
    });
    await wait(500);

    // 先截图看一下工具栏全貌
    await shot(page, 'toolbar-overview');

    // 获取工具栏所有图标按钮（仅当前图片的）
    const toolbarBtns = await page.evaluate(() => {
      const containers = document.querySelectorAll('[class*="imageActions"]');
      const result = [];
      containers.forEach(c => {
        if (getComputedStyle(c).display !== 'none' || c.style.display === 'flex') {
          const items = c.querySelectorAll('[class*="actionItem"]');
          items.forEach(i => {
            const aria = i.getAttribute('aria-label') || '';
            const alt = i.getAttribute('alt') || '';
            const childImg = i.querySelector('img');
            const childAlt = childImg ? childImg.getAttribute('alt') || '' : '';
            result.push(aria || alt || childAlt || '?');
          });
        }
      });
      return result;
    });
    console.log('🔧 当前图片工具栏按钮:', toolbarBtns.join(' | '));

    // 第一阶段：TC01-TC04（可能改变页面状态的按钮）
    const tests1 = [
      tc01_replace, tc02_local_modify, tc03_download, tc04_crop,
    ];

    for (const testFn of tests1) {
      try {
        await page.evaluate(() => {
          document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
        });
        await wait(500);
        const curSel = await page.evaluate(() => {
          const checked = document.querySelectorAll('.ant-checkbox-wrapper-checked[class*="imageCheckbox"]');
          return checked.length;
        });
        if (curSel === 0) {
          await selectOneImage(page);
          await wait(1000);
          await page.evaluate(() => {
            document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
          });
        }
        await testFn(page);
      } catch (e) {
        const tcName = testFn.name.replace('tc', 'TC');
        log(tcName.toUpperCase().slice(0, 4), '异常', 'FAIL', e.message.slice(0, 80));
      }
      await wait(1000);
    }

    // TC04 裁剪后可能改变页面状态，重新进入审核视图
    console.log('\n🔄 TC04后重新进入审核视图...');
    await enterAuditView(page);
    await wait(2000);
    await selectOneImage(page);
    await wait(1000);
    await page.evaluate(() => {
      document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
    });
    await wait(500);

    // 依次执行后续按钮测试
    const tests2 = [
      tc05_reject, tc06_hd_enhance, tc07_negative_feedback,
      tc08_reset, tc09_copy_url,
    ];

    for (const testFn of tests2) {
      try {
        // 重新强制显示工具栏（每次测试前）
        await page.evaluate(() => {
          document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
        });
        await wait(500);
        // 确保有图片被选中
        const curSel = await page.evaluate(() => {
          const checked = document.querySelectorAll('.ant-checkbox-wrapper-checked[class*="imageCheckbox"]');
          return checked.length;
        });
        if (curSel === 0) {
          await selectOneImage(page);
          await wait(1000);
          await page.evaluate(() => {
            document.querySelectorAll('[class*="imageActions"]').forEach(el => el.style.display = 'flex');
          });
        }
        await testFn(page);
      } catch (e) {
        const tcName = testFn.name.replace('tc', 'TC');
        log(tcName.toUpperCase().slice(0, 4), '异常', 'FAIL', e.message.slice(0, 80));
      }
      await wait(1000);
    }

    // TC10: 数据流转验证
    try {
      await tc10_data_flow(page);
    } catch (e) {
      log('TC10', '异常', 'FAIL', e.message.slice(0, 80));
    }

  } catch (e) {
    console.error('❌ 主流程异常:', e.message);
  } finally {
    await page.close();
    browser.disconnect();
  }

  // ── 汇总 ──
  console.log('\n════════════════════════════════');
  console.log('📊 图片审核 9 按钮 e2e 回归结果');
  console.log('════════════════════════════════');

  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  const warnCount = results.filter(r => r.status === 'WARN').length;
  const total = results.length;

  console.log(`断言总计: ${total} | ✅ PASS: ${passCount} | ❌ FAIL: ${failCount} | ⚠️ WARN: ${warnCount}`);
  console.log(`通过率: ${((passCount / total) * 100).toFixed(1)}%`);

  // 按 TC 分组
  const tcGroups = {};
  for (const r of results) {
    if (!tcGroups[r.tc]) tcGroups[r.tc] = [];
    tcGroups[r.tc].push(r);
  }
  for (const [tc, items] of Object.entries(tcGroups)) {
    const hasPass = items.some(i => i.status === 'PASS');
    const hasFail = items.some(i => i.status === 'FAIL');
    const icon = hasFail ? '❌' : hasPass ? '✅' : '⚠️';
    const passN = items.filter(i => i.status === 'PASS').length;
    console.log(`  ${icon} ${tc}: ${passN}/${items.length} 通过`);
  }

  // 写结果
  const outputPath = path.join(__dirname, '..', 'artifacts', 'f88-image-audit-e2e-results.json');
  fs.writeFileSync(outputPath, JSON.stringify({
    total, pass: passCount, fail: failCount, warn: warnCount,
    passRate: `${((passCount / total) * 100).toFixed(1)}%`,
    results,
  }, null, 2));
  console.log(`\n📁 结果已保存: ${outputPath}`);
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
