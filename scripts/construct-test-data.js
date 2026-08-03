#!/usr/bin/env node
/**
 * 构造测试数据：链路 id=20180 试运行（双商家模式）
 * 流程：下载模板 → 填写数据 → 上传Excel → 发起运行
 * 
 * 业务规则：
 *   - 每次试运行使用两个不同的商家(seller_id)
 *   - 常用商家：2219662018344 和 2219635649153
 *   - 一个批次只产生一个审核任务（按批次聚合，不按商家拆分）
 */
'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CDP_URL = 'http://127.0.0.1:9222';
const LINK_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180';
const DOWNLOAD_DIR = '/tmp/chrome-downloads';
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');

// ── 双商家配置 ──
const MERCHANTS = [
  {
    seller_id: '2219662018344',
    note: '常用商家A',
    items: [
      { item_id: '1044587480343', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219662018344/O1CN01mA001.jpg' },
      { item_id: '1044587480344', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219662018344/O1CN01mA002.jpg' },
    ],
  },
  {
    seller_id: '2219635649153',
    note: '常用商家B',
    items: [
      { item_id: '1044587480345', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219635649153/O1CN01mB001.jpg' },
      { item_id: '1044587480346', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219635649153/O1CN01mB002.jpg' },
    ],
  },
];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ss(page, name) {
  const fp = path.join(SS_DIR, `construct-${name}.jpg`);
  await page.screenshot({ path: fp, type: 'jpeg', quality: 70 });
  console.log(`  📸 ${fp}`);
}

async function main() {
  console.log('🔗 连接 CDP...');
  const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
  const page = await browser.newPage();

  // 确保下载目录存在
  if (!fs.existsSync(DOWNLOAD_DIR)) fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });

  // 设置下载行为
  const client = await page.createCDPSession();
  await client.send('Page.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: DOWNLOAD_DIR,
  });
  console.log(`  下载目录: ${DOWNLOAD_DIR}`);

  // ===== Step 1: 导航到链路详情页 =====
  console.log('\n═══ Step 1: 导航到链路详情页 ═══');
  await page.goto(LINK_URL, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);
  await ss(page, 'step1-link-detail');

  const title = await page.title();
  console.log(`  页面标题: ${title}`);
  console.log(`  URL: ${page.url()}`);

  // 检查是否已登录
  const hasLogin = await page.evaluate(() => document.body.innerText.includes('F88'));
  if (!hasLogin) {
    console.log('  ❌ 未登录或未选择F88租户，请先手动登录');
    await page.close();
    await browser.disconnect();
    return;
  }
  console.log('  ✅ F88租户已验证');

  // ===== Step 2: 点击"试运行"按钮 =====
  console.log('\n═══ Step 2: 点击试运行 ═══');
  const clickedRun = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
      if (btn.textContent.trim() === '试运行' && btn.offsetHeight > 0) {
        btn.click();
        return true;
      }
    }
    return false;
  });
  console.log(`  点击试运行: ${clickedRun ? '成功' : '失败'}`);
  await sleep(2000);
  await ss(page, 'step2-trial-run-modal');

  // ===== Step 3: 下载模板 =====
  console.log('\n═══ Step 3: 下载Excel模板 ═══');
  const beforeFiles = fs.readdirSync(DOWNLOAD_DIR);
  console.log(`  下载前文件: ${beforeFiles.length}`);

  const clickedDownload = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button, span, div, a')];
    const dl = els.find(e => e.textContent.trim() === '下载模板' && e.offsetHeight > 0);
    if (dl) { dl.click(); return true; }
    return false;
  });
  console.log(`  点击下载模板: ${clickedDownload ? '成功' : '失败'}`);

  // 等待下载完成
  console.log('  等待下载...');
  await sleep(5000);
  const afterFiles = fs.readdirSync(DOWNLOAD_DIR);
  console.log(`  下载后文件: ${afterFiles.length}`);
  const newFiles = afterFiles.filter(f => !beforeFiles.includes(f));
  console.log(`  新文件: ${newFiles}`);

  // 查找 Excel 文件
  const allFiles = fs.readdirSync(DOWNLOAD_DIR);
  const xlsxFiles = allFiles.filter(f => f.endsWith('.xlsx') || f.endsWith('.xls'));
  console.log(`  下载目录中所有 Excel: ${xlsxFiles}`);

  let templatePath = null;
  if (newFiles.length > 0) {
    templatePath = path.join(DOWNLOAD_DIR, newFiles[0]);
  } else if (xlsxFiles.length > 0) {
    templatePath = path.join(DOWNLOAD_DIR, xlsxFiles[xlsxFiles.length - 1]);
  }

  if (!templatePath || !fs.existsSync(templatePath)) {
    console.log('  ⚠️ 模板文件未找到，检查下载目录...');
    // 也检查用户的默认下载目录
    const userDlDir = path.join(process.env.HOME, 'Downloads');
    if (fs.existsSync(userDlDir)) {
      const userFiles = fs.readdirSync(userDlDir).filter(f => f.endsWith('.xlsx') || f.endsWith('.xls'));
      console.log(`  用户下载目录 Excel: ${userFiles.slice(-5)}`);
      if (userFiles.length > 0) {
        templatePath = path.join(userDlDir, userFiles[userFiles.length - 1]);
        console.log(`  使用: ${templatePath}`);
      }
    }
  }

  // ===== Step 4: 读取模板结构并填写数据 =====
  console.log('\n═══ Step 4: 读取模板结构 ═══');
  if (templatePath && fs.existsSync(templatePath)) {
    console.log(`  模板路径: ${templatePath}`);
    console.log(`  模板大小: ${fs.statSync(templatePath).size} bytes`);

    // 用 Python 读取 Excel 结构
    const { execSync } = require('child_process');
    try {
      const result = execSync(`python3 -c "
import openpyxl
wb = openpyxl.load_workbook('${templatePath}')
for name in wb.sheetnames:
    ws = wb[name]
    print(f'Sheet: {name}, Rows: {ws.max_row}, Cols: {ws.max_column}')
    for row in ws.iter_rows(min_row=1, max_row=min(3, ws.max_row), values_only=False):
        print([cell.value for cell in row])
"`, { encoding: 'utf-8' });
      console.log('  模板结构:');
      console.log(result);
    } catch (e) {
      console.log(`  Python读取失败: ${e.message}`);
    }
  } else {
    console.log('  ❌ 无法获取模板文件');
  }

  // ===== Step 5: 构造并上传 Excel =====
  console.log('\n═══ Step 5: 构造测试数据并上传 ═══');

  // 根据已知入参构造数据：seller_id, seed_image_url, tao_cate, item_id
  // 双商家模式：每个商家2条数据，共4条，预期产生1个审核任务
  const testDataPath = path.join(DOWNLOAD_DIR, 'test-data.xlsx');

  // 用 Python 生成双商家测试数据
  const merchantsJson = JSON.stringify(MERCHANTS);
  try {
    const { execSync } = require('child_process');
    execSync(`python3 -c "
import json, openpyxl
wb = openpyxl.load_workbook('${templatePath}')
ws = wb.active
headers = [cell.value for cell in ws[1]]
print('Headers:', headers)

merchants = json.loads('${merchantsJson}')
row_idx = ws.max_row + 1
total = 0

for merchant in merchants:
    for item in merchant['items']:
        data = {
            'seller_id': merchant['seller_id'],
            'seed_image_url': item['seed_image_url'],
            'tao_cate': '女装',
            'item_id': item['item_id'],
        }
        for col_idx, header in enumerate(headers, 1):
            if header:
                key_match = {k.lower(): k for k in data.keys()}.get(header.lower())
                if key_match:
                    ws.cell(row=row_idx + total, column=col_idx, value=data[key_match])
        total += 1

wb.save('${testDataPath}')
print(f'Saved: ${testDataPath}')
print(f'Filled {total} rows (2 merchants x 2 items each)')
print(f'Expected: 1 audit task for the entire batch')
"`, { encoding: 'utf-8' });
    console.log('  ✅ 双商家测试数据已生成（2个商家，预期1个审核任务）');
  } catch (e) {
    console.log(`  生成测试数据失败: ${e.message}`);
    console.log('  尝试手动上传...');
  }

  // 上传文件
  if (fs.existsSync(testDataPath)) {
    console.log(`  上传文件: ${testDataPath}`);

    // 查找上传区域的 input[type=file]
    const fileInput = await page.$('input[type="file"]');
    if (fileInput) {
      await fileInput.uploadFile(testDataPath);
      console.log('  ✅ 文件已上传');
      await sleep(2000);
      await ss(page, 'step5-file-uploaded');
    } else {
      console.log('  ❌ 未找到文件上传 input');
      // 尝试通过 evaluate 查找
      const uploadResult = await page.evaluate(() => {
        const inputs = document.querySelectorAll('input[type="file"]');
        return inputs.length;
      });
      console.log(`  文件 input 数量: ${uploadResult}`);
    }
  }

  // ===== Step 6: 填写任务名称和运行类型 =====
  console.log('\n═══ Step 6: 填写任务信息 ═══');

  // 填写任务名称
  const taskName = `自动化回归测试_${new Date().toISOString().slice(0, 10)}`;
  const nameFilled = await page.evaluate((name) => {
    const inputs = document.querySelectorAll('input[placeholder*="任务名称"], input[placeholder*="请输入"]');
    for (const input of inputs) {
      if (input.placeholder.includes('任务名称') && input.offsetHeight > 0) {
        input.focus();
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, name);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    return false;
  }, taskName);
  console.log(`  任务名称 "${taskName}": ${nameFilled ? '已填写' : '未找到输入框'}`);

  // 选择运行类型
  const typeSelected = await page.evaluate(() => {
    const selects = document.querySelectorAll('.ant-select, .ant-select-selector');
    for (const sel of selects) {
      if (sel.offsetHeight > 0 && sel.closest('.ant-select')) {
        sel.click();
        return true;
      }
    }
    return false;
  });
  console.log(`  点击运行类型下拉: ${typeSelected ? '成功' : '失败'}`);
  await sleep(1000);

  // 选择第一个选项
  const optionClicked = await page.evaluate(() => {
    const options = document.querySelectorAll('.ant-select-item-option, .ant-select-dropdown .ant-select-item');
    for (const opt of options) {
      if (opt.offsetHeight > 0) {
        opt.click();
        return opt.textContent.trim();
      }
    }
    return null;
  });
  console.log(`  选择运行类型: ${optionClicked || '未找到选项'}`);
  await sleep(1000);
  await ss(page, 'step6-form-filled');

  // ===== Step 7: 发起运行 =====
  console.log('\n═══ Step 7: 发起任务运行 ═══');
  const submitted = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
      const text = btn.textContent.trim();
      if ((text.includes('发起任务运行') || text.includes('发起运行')) && btn.offsetHeight > 0) {
        console.log('Found button:', text);
        btn.click();
        return text;
      }
    }
    return null;
  });
  console.log(`  点击发起: ${submitted || '未找到按钮'}`);
  await sleep(3000);
  await ss(page, 'step7-submitted');

  // 检查结果
  const pageText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log('\n═══ 结果检查 ═══');
  if (pageText.includes('成功') || pageText.includes('已提交') || pageText.includes('运行中')) {
    console.log('  ✅ 测试数据构造成功！');
  } else if (pageText.includes('失败') || pageText.includes('错误') || pageText.includes('请')) {
    console.log('  ⚠️ 可能有错误提示，请检查截图');
  }
  console.log(`  页面前500字: ${pageText.substring(0, 200)}`);

  await page.close();
  await browser.disconnect();
  console.log('\n🏁 完成');
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });
