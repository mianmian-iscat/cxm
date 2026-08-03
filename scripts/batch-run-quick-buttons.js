#!/usr/bin/env node
/**
 * 批量执行「审核节点参与人快捷按钮」测试用例
 * 需求: Aone #84417990 — 复制/批量填写/清空 三按钮
 *
 * 用法：
 *   node scripts/batch-run-quick-buttons.js
 *   node scripts/batch-run-quick-buttons.js --sequential   # 串行模式
 */
'use strict';
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const BASE = path.resolve(__dirname, '..');
const RUNNER = path.join(BASE, 'scripts/run-browser-test.js');
const CASES_DIR = path.join(BASE, 'eval/cases/f88-test/审核管理/审核节点管理/参与人快捷按钮');

const cases = [
  // P0 核心用例
  'TC-AN-QB-001-复制有参与人.json',
  'TC-AN-QB-003-批量填写合法JSON.json',
  'TC-AN-QB-004-批量填写部分不合法.json',
  'TC-AN-QB-008-清空确认.json',
  'TC-AN-QB-010-UI布局三按钮.json',
  // P1 补充用例
  'TC-AN-QB-002-复制无参与人.json',
  'TC-AN-QB-005-批量填写全部不合法.json',
  'TC-AN-QB-006-批量填写非法JSON.json',
  'TC-AN-QB-009-清空取消.json',
  // P2 边界用例
  'TC-AN-QB-007-批量填写空输入.json',
  // 边界场景补充
  'TC-AN-QB-011-批量填写重复empId去重.json',
  'TC-AN-QB-012-批量填写超大批量.json',
  'TC-AN-QB-013-弹窗关闭方式.json',
  'TC-AN-QB-014-清空无参与人时点击.json',
  'TC-AN-QB-015-端到端连续操作.json',
];

const OUTPUT_DIR = path.join(BASE, 'artifacts');
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const results = [];
let allPass = true;
const startTime = Date.now();

console.log('═══════════════════════════════════════════════════════');
console.log('  审核节点参与人快捷按钮 — 批量 e2e 测试');
console.log('  需求: Aone #84417990');
console.log('═══════════════════════════════════════════════════════');
console.log(`📁 用例目录: ${CASES_DIR}`);
console.log(`🔢 用例数量: ${cases.length}\n`);

for (const c of cases) {
  const full = path.join(CASES_DIR, c);
  const name = c.replace('.json', '');
  const idx = results.length + 1;
  console.error(`[${idx}/${cases.length}] 运行: ${name}...`);

  if (!fs.existsSync(full)) {
    results.push({ case: name, total: 0, passed: 0, failed: 0, status: 'SKIP', error: '文件不存在' });
    console.error(`  → SKIP: 文件不存在`);
    continue;
  }

  const outFile = `/tmp/batch-qb-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
  const caseStart = Date.now();

  try {
    execSync(`node "${RUNNER}" "${full}" "${outFile}"`, {
      timeout: 120000,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, WEB_AUTO_SCREENSHOTS_DIR: path.join(OUTPUT_DIR, 'screenshots') },
    });
    const out = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    const steps = out.steps || [];
    const total = steps.length;
    const passed = steps.filter(s => s.status === 'pass').length;
    const failed = steps.filter(s => s.status === 'fail').length;
    const failSteps = steps
      .filter(s => s.status === 'fail')
      .map(s => `step ${s.index}: ${s.description || s.type} — ${s.error || '?'}`);
    const elapsed = ((Date.now() - caseStart) / 1000).toFixed(1);
    const status = failed === 0 ? 'PASS' : 'FAIL';
    if (failed > 0) allPass = false;
    results.push({ case: name, total, passed, failed, status, failSteps, elapsed });
    console.error(`  → ${status}: ${passed}/${total} (${elapsed}s)${failed > 0 ? ` (${failed} failures)` : ''}`);
  } catch (err) {
    allPass = false;
    const elapsed = ((Date.now() - caseStart) / 1000).toFixed(1);
    const errMsg = err.stderr ? err.stderr.toString().slice(0, 200) : err.message.slice(0, 200);
    results.push({ case: name, total: 0, passed: 0, failed: 0, status: 'ERROR', error: errMsg, elapsed });
    console.error(`  → ERROR (${elapsed}s): ${errMsg.slice(0, 100)}`);
  }
}

// ── 汇总报告 ──
const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
console.log('\n═══════════════════════════════════════════════════════');
console.log('  审核节点参与人快捷按钮 — 批量验证结果');
console.log('═══════════════════════════════════════════════════════');

let totalAll = 0, passedAll = 0, failedAll = 0;
for (const r of results) {
  totalAll += r.total;
  passedAll += r.passed;
  failedAll += r.failed;
  const icon = r.status === 'PASS' ? '✅' : r.status === 'SKIP' ? '⏭️' : r.status === 'ERROR' ? '💥' : '❌';
  const tag = r.status === 'SKIP' ? 'SKIP' : `${r.passed}/${r.total}`;
  console.log(`${icon} ${r.case.padEnd(45)} ${tag.padEnd(8)} ${r.elapsed || '-'}s`);
  if (r.failSteps) r.failSteps.forEach(f => console.log(`   └─ ${f}`));
  if (r.error && r.status !== 'SKIP') console.log(`   └─ ${r.error.slice(0, 120)}`);
}

console.log('───────────────────────────────────────────────────────');
console.log(`总计: ${passedAll}/${totalAll} 步骤通过, ${results.filter(r => r.status === 'PASS').length}/${results.length} 用例通过`);
console.log(`耗时: ${totalTime}s`);
console.log(`整体结果: ${allPass ? '✅ ALL PASS' : '❌ HAS FAILURES'}`);

// ── 写结果文件 ──
const outputPath = path.join(OUTPUT_DIR, 'f88-quick-buttons-results.json');
fs.writeFileSync(outputPath, JSON.stringify({
  requirement: 'Aone #84417990',
  feature: '审核节点参与人快捷按钮(复制/批量填写/清空)',
  timestamp: new Date().toISOString(),
  totalTime: `${totalTime}s`,
  summary: {
    total: results.length,
    passed: results.filter(r => r.status === 'PASS').length,
    failed: results.filter(r => r.status === 'FAIL').length,
    error: results.filter(r => r.status === 'ERROR').length,
    skipped: results.filter(r => r.status === 'SKIP').length,
    allPass,
  },
  results,
}, null, 2), 'utf8');
console.log(`\n📁 结果已保存: ${outputPath}`);

process.exit(allPass ? 0 : 1);
