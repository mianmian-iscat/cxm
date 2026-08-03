#!/usr/bin/env node
/**
 * batch-run-style-shop.js — 批量执行风格店铺协作平台测试用例
 */
'use strict';
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const WORKSPACE = path.resolve(__dirname, '..');
const CASES_DIR = path.join(WORKSPACE, 'eval', 'cases', 'style-shop-collab');
const RUNNER = path.join(WORKSPACE, 'scripts', 'run-browser-test.js');
const OUT_DIR = '/tmp/style-shop-results';

fs.mkdirSync(OUT_DIR, { recursive: true });

// 递归收集所有 JSON 用例
function collectCases(dir) {
  const cases = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) cases.push(...collectCases(full));
    else if (entry.name.endsWith('.json')) cases.push(full);
  }
  return cases;
}

const allCases = collectCases(CASES_DIR).sort();
console.log(`=== 风格店铺协作平台 — 批量执行 ${allCases.length} 条用例 ===\n`);

const results = [];
let passCount = 0, failCount = 0, errorCount = 0;

for (let i = 0; i < allCases.length; i++) {
  const caseFile = allCases[i];
  const caseName = path.basename(caseFile, '.json');
  const module = path.basename(path.dirname(caseFile));
  const outFile = path.join(OUT_DIR, `${caseName}.json`);

  process.stderr.write(`[${i + 1}/${allCases.length}] ${module}/${caseName}...`);

  try {
    execSync(`node "${RUNNER}" "${caseFile}" "${outFile}"`, {
      timeout: 120000,
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: WORKSPACE,
    });

    const out = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    const steps = out.steps || [];
    const total = steps.length;
    const passed = steps.filter(s => s.status === 'pass').length;
    const failed = steps.filter(s => s.status === 'fail').length;
    const status = out.status || (failed === 0 ? 'pass' : 'fail');

    if (status === 'pass') {
      passCount++;
      process.stderr.write(` ✓ PASS (${passed}/${total})\n`);
    } else if (status === 'fail') {
      failCount++;
      process.stderr.write(` ✗ FAIL (${passed}/${total})\n`);
      const failSteps = steps.filter(s => s.status === 'fail');
      failSteps.forEach(s => {
        process.stderr.write(`    step${s.index}: ${s.description || s.type} — ${s.error?.substring(0, 80) || 'assertion failed'}\n`);
      });
    } else {
      errorCount++;
      process.stderr.write(` ✗ ERROR: ${out.error?.message?.substring(0, 80) || 'unknown'}\n`);
    }

    results.push({
      module, case: caseName, status, total, passed, failed,
      duration: out.duration ? `${(out.duration / 1000).toFixed(1)}s` : '-',
      failSteps: steps.filter(s => s.status === 'fail').map(s => ({
        step: s.index, desc: s.description, error: s.error?.substring(0, 120),
      })),
      screenshots: (out.screenshots || []).map(s => s.path),
    });
  } catch (err) {
    errorCount++;
    process.stderr.write(` ✗ CRASH: ${err.message.substring(0, 80)}\n`);
    results.push({ module, case: caseName, status: 'error', error: err.message.substring(0, 200) });
  }
}

// ── 汇总 ──
console.log(`\n${'═'.repeat(70)}`);
console.log(`执行汇总：共 ${allCases.length} 条 | ✓ 通过 ${passCount} | ✗ 失败 ${failCount} | ✗ 错误 ${errorCount}`);
console.log(`${'═'.repeat(70)}\n`);

// 按模块分组
const byModule = {};
results.forEach(r => { (byModule[r.module] = byModule[r.module] || []).push(r); });

for (const [mod, cases] of Object.entries(byModule)) {
  const modPass = cases.filter(c => c.status === 'pass').length;
  console.log(`📁 ${mod} (${modPass}/${cases.length} 通过)`);
  cases.forEach(c => {
    const icon = c.status === 'pass' ? '✓' : '✗';
    console.log(`  ${icon} ${c.case}: ${c.passed || 0}/${c.total || 0} (${c.duration || '-'})`);
    (c.failSteps || []).forEach(f => console.log(`      ↳ step${f.step}: ${f.desc} — ${f.error}`));
  });
  console.log();
}

// 保存结果
const summaryFile = path.join(OUT_DIR, 'summary.json');
fs.writeFileSync(summaryFile, JSON.stringify(results, null, 2));
console.log(`详细结果已保存到: ${summaryFile}`);
