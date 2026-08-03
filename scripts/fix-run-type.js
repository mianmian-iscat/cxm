#!/usr/bin/env node
/**
 * 修复：选择运行类型 + 重新发起运行
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = 'http://127.0.0.1:9222';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ss(page, name) {
  const fp = path.join(SS_DIR, `fix-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
}

async function main() {
  console.log('🔗 连接 CDP...');
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  // 导航到链路详情页
  console.log('导航到链路详情页...');
  await page.goto('https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180', {
    waitUntil: 'networkidle2', timeout: 30000
  });
  await sleep(3000);

  // 点击试运行
  console.log('点击试运行...');
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '试运行' && b.offsetHeight > 0);
    if (btn) btn.click();
  });
  await sleep(2000);
  await ss(page, 'modal-open');

  // 先下载模板到正确位置
  console.log('\n═══ 下载模板 ═══');
  const client = await page.createCDPSession();
  const downloadDir = path.join(process.env.HOME, 'Downloads');
  await client.send('Page.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: downloadDir,
  });
  
  const beforeFiles = fs.readdirSync(downloadDir).filter(f => f.endsWith('.xlsx') || f.endsWith('.xls'));
  console.log(`  下载前 Excel 数量: ${beforeFiles.length}`);
  
  await page.evaluate(() => {
    const el = [...document.querySelectorAll('button, span, div, a')].find(e => e.textContent.trim() === '下载模板' && e.offsetHeight > 0);
    if (el) el.click();
  });
  
  // 等待下载
  for (let i = 0; i < 10; i++) {
    await sleep(1000);
    const afterFiles = fs.readdirSync(downloadDir).filter(f => f.endsWith('.xlsx') || f.endsWith('.xls'));
    if (afterFiles.length > beforeFiles.length) {
      const newFile = afterFiles.find(f => !beforeFiles.includes(f));
      console.log(`  ✅ 下载完成: ${newFile}`);
      break;
    }
    // 也检查 .crdownload (正在下载)
    const crFiles = fs.readdirSync(downloadDir).filter(f => f.endsWith('.crdownload'));
    if (crFiles.length === 0 && i > 2) {
      console.log(`  等待 ${i+1}s...`);
    }
  }

  const afterFiles = fs.readdirSync(downloadDir).filter(f => f.endsWith('.xlsx') || f.endsWith('.xls'));
  const latestFile = afterFiles[afterFiles.length - 1];
  console.log(`  最新 Excel: ${latestFile}`);

  // 读取模板结构
  if (latestFile) {
    const { execSync } = require('child_process');
    try {
      const result = execSync(`python3 -c "
import openpyxl
wb = openpyxl.load_workbook('${path.join(downloadDir, latestFile)}')
ws = wb.active
headers = [cell.value for cell in ws[1]]
print('Headers:', headers)
print('Max row:', ws.max_row, 'Max col:', ws.max_column)
for r in range(2, min(4, ws.max_row+1)):
    print(f'Row {r}:', [cell.value for cell in ws[r]])
" 2>/dev/null`, { encoding: 'utf-8' });
      console.log('  模板结构:');
      console.log(result.trim().split('\n').map(l => '    ' + l).join('\n'));
    } catch(e) {}
  }

  // ===== 上传 Excel =====
  console.log('\n═══ 上传测试数据 ═══');
  // 先用刚才下载的模板构造测试数据
  if (latestFile) {
    const templatePath = path.join(downloadDir, latestFile);
    const testDataPath = path.join('/tmp', 'f88-test-data.xlsx');
    const { execSync } = require('child_process');
    try {
      const output = execSync(`python3 -c "
import openpyxl, json
wb = openpyxl.load_workbook('${templatePath}')
ws = wb.active
headers = [cell.value for cell in ws[1]]
print('模板headers:', headers)

# 清空原有数据，只保留header
for row in range(2, ws.max_row + 1):
    for col in range(1, ws.max_column + 1):
        ws.cell(row=row, column=col, value=None)

# 写入1条测试数据
data = {
    'seller_id': '2219635649153',
    'seed_image_url': 'https://img.alicdn.com/imgextra/i1/O1CN01Z5paLz1O4SsHjYjJN_!!6000000001652-0-tps-800-800.jpg',
    'tao_cate': '女装',
    'item_id': '1044587480343'
}

# 匹配header填写
for col_idx, header in enumerate(headers, 1):
    if header and str(header).strip() in data:
        ws.cell(row=2, column=col_idx, value=data[str(header).strip()])

wb.save('${testDataPath}')
print('Saved:', '${testDataPath}')
" 2>/dev/null`, { encoding: 'utf-8' });
      console.log(output.trim());
    } catch(e) {
      console.log(`  构造数据失败: ${e.message}`);
    }

    // 上传
    const testDataFullPath = '/tmp/f88-test-data.xlsx';
    if (fs.existsSync(testDataFullPath)) {
      const fileInput = await page.$('input[type="file"]');
      if (fileInput) {
        await fileInput.uploadFile(testDataFullPath);
        console.log('  ✅ 测试数据已上传');
        await sleep(2000);
        await ss(page, 'data-uploaded');
      } else {
        console.log('  ❌ 未找到 file input');
      }
    }
  }

  // ===== 填写任务名称 =====
  console.log('\n═══ 填写表单 ═══');
  const taskName = `自动化回归_${new Date().toISOString().slice(0,16).replace(/[T:-]/g,'')}`;
  
  // 任务名称 - 使用 puppeteer 的 type 方法
  const nameInput = await page.$('input[placeholder*="任务名称"]');
  if (nameInput) {
    await nameInput.click({ clickCount: 3 }); // 全选
    await nameInput.type(taskName);
    console.log(`  任务名称: ${taskName}`);
  } else {
    console.log('  ❌ 未找到任务名称输入框');
  }

  // ===== 运行类型 - Ant Design Select =====
  console.log('\n═══ 选择运行类型 ═══');
  
  // 方法1: 点击 .ant-select-selector 触发下拉
  const selectClicked = await page.evaluate(() => {
    // 找到"运行类型"相关的 select
    const labels = document.querySelectorAll('.ant-form-item-label, label, span');
    for (const label of labels) {
      if (label.textContent.trim().includes('运行类型')) {
        const formItem = label.closest('.ant-form-item, .ant-row, div');
        if (formItem) {
          const selector = formItem.querySelector('.ant-select-selector, .ant-select');
          if (selector) {
            selector.click();
            return 'clicked via label proximity';
          }
        }
      }
    }
    // fallback: 直接找 ant-select
    const selects = document.querySelectorAll('.ant-select:not(.ant-select-disabled)');
    for (const sel of selects) {
      const ph = sel.querySelector('.ant-select-selection-placeholder');
      if (ph && ph.textContent.includes('运行类型')) {
        sel.querySelector('.ant-select-selector').click();
        return 'clicked via placeholder';
      }
    }
    return null;
  });
  console.log(`  Select 点击: ${selectClicked}`);
  await sleep(1500);
  await ss(page, 'dropdown-open');

  // 选择下拉选项
  const optionSelected = await page.evaluate(() => {
    // Ant Design 下拉菜单渲染在 body 末尾
    const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
    for (const dd of dropdowns) {
      const items = dd.querySelectorAll('.ant-select-item-option');
      if (items.length > 0) {
        const firstText = items[0].textContent.trim();
        items[0].click();
        return firstText;
      }
    }
    return null;
  });
  console.log(`  选择选项: ${optionSelected || '未找到'}`);
  await sleep(1000);

  if (!optionSelected) {
    // 方法2: 用 keyboard 操作
    console.log('  尝试 keyboard 方式...');
    await page.keyboard.press('Tab'); // 可能需要 tab 到 select
    await sleep(500);
    await page.keyboard.press('Enter'); // 打开下拉
    await sleep(1000);
    await page.keyboard.press('ArrowDown'); // 选第一个
    await sleep(500);
    await page.keyboard.press('Enter'); // 确认
    await sleep(500);
    await ss(page, 'dropdown-keyboard');
  }

  // ===== 发起运行 =====
  console.log('\n═══ 发起任务运行 ═══');
  await sleep(500);
  await ss(page, 'before-submit');

  const submitResult = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => 
      b.textContent.includes('发起任务运行') && b.offsetHeight > 0
    );
    if (btn) {
      const isDisabled = btn.disabled || btn.classList.contains('ant-btn-disabled');
      btn.click();
      return { clicked: true, disabled: isDisabled, text: btn.textContent.trim() };
    }
    return { clicked: false };
  });
  console.log(`  提交按钮: ${JSON.stringify(submitResult)}`);
  await sleep(3000);
  await ss(page, 'after-submit');

  // 检查最终结果
  const finalText = await page.evaluate(() => {
    // 查找 message / notification
    const msgs = document.querySelectorAll('.ant-message, .ant-notification, .ant-alert');
    const texts = [...msgs].map(m => m.textContent.trim());
    return texts.length > 0 ? texts : [document.body.innerText.substring(0, 300)];
  });
  console.log('\n═══ 最终结果 ═══');
  console.log(`  ${JSON.stringify(finalText)}`);

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });
