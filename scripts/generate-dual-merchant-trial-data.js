#!/usr/bin/env node
/**
 * generate-dual-merchant-trial-data.js
 * 
 * 生成双商家试运行测试数据 Excel 文件
 * 
 * 业务规则：
 *   - 每次试运行必须使用两个不同的商家(seller_id)
 *   - 常用商家：2219662018344 和 2219635649153
 *   - 一个批次的数据只会产生一个审核任务（按批次聚合，不按商家拆分）
 * 
 * 输出：test-fixtures/dual-merchant-trial-data.xlsx
 * 
 * 用法：
 *   node scripts/generate-dual-merchant-trial-data.js [--link-id 20180] [--output path/to/output.xlsx]
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// ── 配置 ──
const DEFAULT_LINK_ID = '20180';
const FIXTURES_DIR = path.join(__dirname, '..', 'test-fixtures');
const DEFAULT_OUTPUT = path.join(FIXTURES_DIR, 'dual-merchant-trial-data.xlsx');

// ── 双商家配置（核心：两个不同seller_id）──
const MERCHANTS = [
  {
    seller_id: '2219662018344',
    note: '常用商家A',
    items: [
      { item_id: '1044587480343', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219662018344/O1CN01mA001.jpg', tao_cate: '女装' },
      { item_id: '1044587480344', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219662018344/O1CN01mA002.jpg', tao_cate: '女装' },
    ],
  },
  {
    seller_id: '2219635649153',
    note: '常用商家B',
    items: [
      { item_id: '1044587480345', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219635649153/O1CN01mB001.jpg', tao_cate: '女装' },
      { item_id: '1044587480346', seed_image_url: 'https://img.alicdn.com/imgextra/i1/2219635649153/O1CN01mB002.jpg', tao_cate: '女装' },
    ],
  },
];

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { linkId: DEFAULT_LINK_ID, output: DEFAULT_OUTPUT };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--link-id' && args[i + 1]) opts.linkId = args[++i];
    if (args[i] === '--output' && args[i + 1]) opts.output = args[++i];
  }
  return opts;
}

function main() {
  const opts = parseArgs();
  console.log('🔧 双商家试运行造数脚本');
  console.log(`  链路ID: ${opts.linkId}`);
  console.log(`  输出: ${opts.output}`);
  console.log(`  商家A: ${MERCHANTS[0].seller_id} (${MERCHANTS[0].note})`);
  console.log(`  商家B: ${MERCHANTS[1].seller_id} (${MERCHANTS[1].note})`);
  console.log();

  // 确保目录存在
  if (!fs.existsSync(FIXTURES_DIR)) {
    fs.mkdirSync(FIXTURES_DIR, { recursive: true });
    console.log(`  📁 创建目录: ${FIXTURES_DIR}`);
  }

  // 构造 Excel 列：seller_id, seed_image_url, tao_cate, item_id
  const headers = ['seller_id', 'seed_image_url', 'tao_cate', 'item_id'];
  
  // 汇总所有行数据
  const rows = [];
  for (const merchant of MERCHANTS) {
    for (const item of merchant.items) {
      rows.push({
        seller_id: merchant.seller_id,
        seed_image_url: item.seed_image_url,
        tao_cate: item.tao_cate,
        item_id: item.item_id,
      });
    }
  }

  console.log(`  数据行数: ${rows.length} (商家A ${MERCHANTS[0].items.length}条 + 商家B ${MERCHANTS[1].items.length}条)`);
  console.log();

  // 用 Python openpyxl 生成 Excel（写入临时脚本文件避免转义问题）
  const pyScriptPath = path.join(FIXTURES_DIR, '_gen_excel.py');
  const pyScript = [
    'import json, sys, os',
    'try:',
    '    import openpyxl',
    '    from openpyxl.styles import Font',
    '    from openpyxl.utils import get_column_letter',
    'except ImportError:',
    '    print("ERROR: openpyxl not installed. Run: pip install openpyxl", file=sys.stderr)',
    '    sys.exit(1)',
    '',
    'headers = json.loads(sys.argv[1])',
    'rows = json.loads(sys.argv[2])',
    'output = sys.argv[3]',
    '',
    'wb = openpyxl.Workbook()',
    'ws = wb.active',
    'ws.title = "trial_run_data"',
    '',
    'for col_idx, h in enumerate(headers, 1):',
    '    cell = ws.cell(row=1, column=col_idx, value=h)',
    '    cell.font = Font(bold=True)',
    '',
    'for row_idx, row_data in enumerate(rows, 2):',
    '    for col_idx, h in enumerate(headers, 1):',
    '        ws.cell(row=row_idx, column=col_idx, value=row_data.get(h, ""))',
    '',
    'for col_idx, h in enumerate(headers, 1):',
    '    max_len = len(h)',
    '    for row_idx in range(2, len(rows) + 2):',
    '        val = str(ws.cell(row=row_idx, column=col_idx).value or "")',
    '        max_len = max(max_len, len(val))',
    '    ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)',
    '',
    'wb.save(output)',
    'print(f"OK: {output} ({len(rows)} rows)")',
  ].join('\n');
  fs.writeFileSync(pyScriptPath, pyScript, 'utf-8');

  try {
    console.log('📝 生成 Excel...');
    const result = execSync(
      `python3 "${pyScriptPath}" '${JSON.stringify(headers)}' '${JSON.stringify(rows)}' "${opts.output}"`,
      { encoding: 'utf-8', cwd: path.join(__dirname, '..') }
    );
    console.log(`  ✅ ${result.trim()}`);
  } catch (e) {
    console.log(`  ❌ 生成失败: ${e.message}`);
    process.exit(1);
  } finally {
    // 清理临时脚本
    try { fs.unlinkSync(pyScriptPath); } catch (_) { /* ignore */ }
  }

  // 同时生成 JSON 格式的 input 供 impl.py 直接使用
  const inputJson = {
    id: `dual-merchant-trial-${opts.linkId}`,
    name: '双商家试运行造数 → 审核任务聚合验证',
    businessType: 'f88_material_audit',
    context: {
      urlPattern: 'pre-aifashion-xiaoer.alibaba-inc.com',
      url: `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=${opts.linkId}`,
      waitAfterLoad: 3000,
      auth: 'buc',
    },
    steps: [
      { type: 'navigate', url: `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=${opts.linkId}`, waitUntil: 'networkidle', description: '打开链路详情页' },
      { type: 'wait', ms: 6000, description: '等待SPA加载' },
      { type: 'clickText', text: '试运行', description: '点击试运行按钮' },
      { type: 'wait', ms: 3000, description: '等待试运行弹窗' },
      { type: 'uploadFile', selector: '.ant-modal:not(.ant-modal-hidden) input[type=file]', filePath: opts.output, description: '上传双商家Excel' },
      { type: 'wait', ms: 3000, description: '等待上传完成' },
      { type: 'screenshot', label: 'dual-merchant-uploaded', description: '上传后截图' },
    ],
    _meta: {
      generatedBy: 'generate-dual-merchant-trial-data.js',
      merchants: MERCHANTS.map(m => m.seller_id),
      totalRows: rows.length,
      businessRule: '一个批次双商家只产生1个审核任务',
    },
  };

  const inputPath = path.join(FIXTURES_DIR, 'dual-merchant-trial-input.json');
  fs.writeFileSync(inputPath, JSON.stringify(inputJson, null, 2), 'utf-8');
  console.log(`  ✅ input JSON: ${inputPath}`);

  // 输出数据摘要
  console.log();
  console.log('═══ 数据摘要 ═══');
  console.log('Excel 列: seller_id | seed_image_url | tao_cate | item_id');
  console.log('─────────────────────────────────────────────────');
  for (const row of rows) {
    console.log(`  ${row.seller_id} | ${row.item_id} | ${row.tao_cate}`);
  }
  console.log('─────────────────────────────────────────────────');
  console.log(`总计: ${rows.length} 行, 2 个商家, 预期: 1 个审核任务`);
  console.log();
  console.log('📋 使用方式:');
  console.log(`  python impl.py eval/cases/f88-test/链路管理/链路详情/e2e_f88_dual_merchant_trial_run.json`);
  console.log(`  或手动上传: ${opts.output}`);
  console.log();
  console.log('🏁 完成');
}

main();
