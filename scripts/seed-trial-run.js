#!/usr/bin/env node
/**
 * seed-trial-run.js — 种草链路纯接口造数脚本
 *
 * 功能：
 *   1. 生成 Excel（1 女装 + 1 非女装，共 2 条）
 *   2. 通过 CDP 连接已登录浏览器，上传 Excel 到 OSS
 *   3. 调用 /api/workflow2/link/run 触发种草链路试运行
 *
 * 前置条件：
 *   - Chrome 已启动并开启 CDP（--remote-debugging-port=9222）
 *   - 浏览器已登录 F88 预发环境
 *
 * 用法：
 *   node scripts/seed-trial-run.js
 *   node scripts/seed-trial-run.js --link-id 20205 --cdp http://127.0.0.1:9222
 */
'use strict';

const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// ── 配置 ──
const CDP_URL = process.env.CDP_URL || 'http://127.0.0.1:9222';
const DEFAULT_LINK_ID = '20205'; // 种草链路
const BASE_URL = 'https://pre-aifashion-xiaoer.alibaba-inc.com';
const FIXTURES_DIR = path.join(__dirname, '..', 'test-fixtures');
const SS_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');

// ── 种草链路造数：1 女装 + 1 非女装 ──
const SEED_DATA = [
  {
    seller_id: '2219662018344',
    seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219662018344/O1CN01mA001.jpg',
    tao_cate: '女装',
    item_id: '1044587480343',
  },
  {
    seller_id: '2219635649153',
    seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219635649153/O1CN01mB001.jpg',
    tao_cate: '男装',
    item_id: '1044587480345',
  },
];

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { linkId: DEFAULT_LINK_ID, cdp: CDP_URL };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--link-id' && args[i + 1]) opts.linkId = args[++i];
    if (args[i] === '--cdp' && args[i + 1]) opts.cdp = args[++i];
  }
  return opts;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Step 1: 生成 Excel ──
function generateExcel(outputPath) {
  if (!fs.existsSync(FIXTURES_DIR)) fs.mkdirSync(FIXTURES_DIR, { recursive: true });

  const headers = ['seller_id', 'seed_image_url', 'tao_cate', 'item_id'];
  const rowsJson = JSON.stringify(SEED_DATA);
  const headersJson = JSON.stringify(headers);

  const pyScript = `
import json, sys, openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

headers = json.loads(sys.argv[1])
rows = json.loads(sys.argv[2])
output = sys.argv[3]

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "trial_run_data"

for col_idx, h in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col_idx, value=h)
    cell.font = Font(bold=True)

for row_idx, row_data in enumerate(rows, 2):
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=row_idx, column=col_idx, value=row_data.get(h, ""))

for col_idx, h in enumerate(headers, 1):
    max_len = len(h)
    for row_idx in range(2, len(rows) + 2):
        val = str(ws.cell(row=row_idx, column=col_idx).value or "")
        max_len = max(max_len, len(val))
    ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

wb.save(output)
print(f"OK: {output} ({len(rows)} rows)")
`.trim();

  const pyPath = path.join(FIXTURES_DIR, '_gen_seed_excel.py');
  fs.writeFileSync(pyPath, pyScript, 'utf-8');

  try {
    const result = execSync(
      `python3 "${pyPath}" '${headersJson}' '${rowsJson}' "${outputPath}"`,
      { encoding: 'utf-8' }
    );
    console.log(`  ✅ Excel 生成成功: ${result.trim()}`);
  } finally {
    try { fs.unlinkSync(pyPath); } catch (_) {}
  }
}

// ── Step 2: 上传文件到 OSS ──
async function uploadFile(page, filePath) {
  console.log('\n═══ Step 2: 上传 Excel 到 OSS ═══');

  // 导航到 F88 页面获取 cookie 域
  await page.goto(`${BASE_URL}/strategy/list`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(2000);

  // 通过 fetch 上传文件（利用浏览器 cookie）
  const uploadResult = await page.evaluate(async () => {
    const formData = new FormData();
    // 注意：浏览器 evaluate 中无法直接读本地文件，需要通过 input 元素
    return { method: 'need_input_element' };
  });

  // 使用隐藏的 input[type=file] + fetch 方式
  const fileInput = await page.evaluateHandle(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.style.display = 'none';
    document.body.appendChild(input);
    return input;
  });

  await fileInput.uploadFile(filePath);
  await sleep(1000);

  // 通过 fetch 发送 multipart 上传
  const result = await page.evaluate(async (inputEl) => {
    const file = inputEl.files[0];
    if (!file) return { error: 'no file selected' };

    const formData = new FormData();
    formData.append('file', file);

    try {
      const resp = await fetch('/api/file/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      return { status: resp.status, data };
    } catch (e) {
      return { error: e.message };
    }
  }, fileInput);

  // 清理临时 input
  await page.evaluate((el) => el.remove(), fileInput);

  if (result.error) {
    console.log(`  ❌ 上传失败: ${result.error}`);
    return null;
  }

  console.log(`  上传状态: ${result.status}`);
  console.log(`  响应: ${JSON.stringify(result.data).substring(0, 200)}`);

  // 提取文件 URL（兼容多种返回结构）
  const fileUrl = result.data?.data?.url
    || result.data?.data?.fileUrl
    || result.data?.url
    || result.data?.fileUrl
    || null;

  if (fileUrl) {
    console.log(`  ✅ 文件 URL: ${fileUrl}`);
  } else {
    console.log('  ⚠️ 未能提取文件 URL，完整响应:');
    console.log(JSON.stringify(result.data, null, 2));
  }

  return fileUrl;
}

// ── Step 3: 触发试运行 ──
async function triggerLinkRun(page, linkId, fileUrl, batchName) {
  console.log('\n═══ Step 3: 触发种草链路试运行 ═══');
  console.log(`  链路ID: ${linkId}`);
  console.log(`  批次名: ${batchName}`);
  console.log(`  文件URL: ${fileUrl}`);

  const result = await page.evaluate(async (params) => {
    const { linkId, fileUrl, batchName } = params;
    try {
      const resp = await fetch('/api/workflow2/link/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: parseInt(linkId),
          batchName: batchName,
          fileUrl: fileUrl,
          runMode: 'test',
        }),
      });
      const data = await resp.json();
      return { status: resp.status, data };
    } catch (e) {
      return { error: e.message };
    }
  }, { linkId, fileUrl, batchName });

  if (result.error) {
    console.log(`  ❌ 触发失败: ${result.error}`);
    return null;
  }

  console.log(`  HTTP 状态: ${result.status}`);
  console.log(`  响应: ${JSON.stringify(result.data).substring(0, 300)}`);

  const batchId = result.data?.data?.batchId || result.data?.batchId || null;
  if (batchId) {
    console.log(`  ✅ batchId: ${batchId}`);
  } else if (result.data?.success) {
    console.log('  ✅ 接口返回成功（未获取到 batchId）');
  } else {
    console.log('  ⚠️ 未获取到 batchId，请检查响应');
  }

  return result.data;
}

// ── 主流程 ──
async function main() {
  const opts = parseArgs();
  console.log('🌱 种草链路纯接口造数');
  console.log(`  CDP: ${opts.cdp}`);
  console.log(`  链路ID: ${opts.linkId}`);
  console.log(`  数据: 女装 × 1 + 非女装(男装) × 1`);
  console.log();

  // 确保目录存在
  for (const dir of [FIXTURES_DIR, SS_DIR]) {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  }

  // Step 1: 生成 Excel
  console.log('═══ Step 1: 生成 Excel ═══');
  const excelPath = path.join(FIXTURES_DIR, 'seed-trial-data.xlsx');
  generateExcel(excelPath);

  // 打印数据摘要
  console.log('\n  数据摘要:');
  console.log('  ─────────────────────────────────────────');
  for (const row of SEED_DATA) {
    console.log(`  ${row.seller_id} | ${row.tao_cate} | ${row.item_id}`);
  }
  console.log('  ─────────────────────────────────────────');

  // Step 2 & 3: 连接浏览器 → 上传 → 触发
  console.log('\n═══ 连接 CDP ═══');
  let browser;
  try {
    browser = await puppeteer.connect({ browserURL: opts.cdp, defaultViewport: null });
  } catch (e) {
    console.log(`  ❌ 无法连接 CDP: ${e.message}`);
    console.log('  请确保 Chrome 已启动并开启 --remote-debugging-port=9222');
    console.log(`  Excel 已生成: ${excelPath}，可手动上传`);
    process.exit(1);
  }

  const page = await browser.newPage();

  try {
    // 上传
    const fileUrl = await uploadFile(page, excelPath);
    if (!fileUrl) {
      console.log('\n❌ 文件上传失败，终止');
      await page.close();
      return;
    }

    // 截图
    const ssPath = path.join(SS_DIR, 'seed-trial-upload.jpg');
    await page.screenshot({ path: ssPath, type: 'jpeg', quality: 70 });
    console.log(`  📸 ${ssPath}`);

    // 触发试运行
    const batchName = `种草造数_${new Date().toISOString().slice(0, 16).replace(/[-T:]/g, '')}`;
    const runResult = await triggerLinkRun(page, opts.linkId, fileUrl, batchName);

    // 截图
    await sleep(2000);
    const ssPath2 = path.join(SS_DIR, 'seed-trial-triggered.jpg');
    await page.screenshot({ path: ssPath2, type: 'jpeg', quality: 70 });
    console.log(`  📸 ${ssPath2}`);

    // 保存结果
    const output = {
      timestamp: new Date().toISOString(),
      linkId: opts.linkId,
      batchName,
      fileUrl,
      excelPath,
      runResult,
      seedData: SEED_DATA,
    };
    const outputPath = path.join(__dirname, '..', 'artifacts', 'seed-trial-run-last.json');
    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf-8');
    console.log(`\n  💾 结果已保存: ${outputPath}`);

    // 查看批次
    if (runResult?.data?.batchId || runResult?.batchId) {
      const bid = runResult.data?.batchId || runResult.batchId;
      console.log(`\n📋 查看批次: ${BASE_URL}/strategy/linkDetail?id=${opts.linkId}`);
      console.log(`  在批次列表中筛选: ${batchName}`);
    }

    console.log('\n🏁 完成');
  } catch (e) {
    console.error(`\n❌ 执行异常: ${e.message}`);
    const ssPath = path.join(SS_DIR, 'seed-trial-error.jpg');
    await page.screenshot({ path: ssPath, type: 'jpeg', quality: 70 }).catch(() => {});
    console.log(`  📸 ${ssPath}`);
  } finally {
    await page.close();
    browser.disconnect();
  }
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });
