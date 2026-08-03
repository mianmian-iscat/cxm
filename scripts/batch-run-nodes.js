#!/usr/bin/env node
// 批量执行策略节点测试用例并汇总结果
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const BASE = path.resolve(__dirname, '..');
const RUNNER = path.join(BASE, 'scripts/run-browser-test.js');
const CASES_DIR = path.join(BASE, 'eval/cases/f88-test/策略管理/策略详情');

const cases = [
  // 生图节点
  '生图/atomic_f88_node-image_gen-trial-run.json',
  '生图/atomic_f88_node-image_gen-config.json',
  '生图/atomic_f88_node-image_gen-var-binding.json',
  '生图/atomic_f88_node-image_gen-model-options.json',
  '生图/atomic_f88_node-image_gen-output-mode.json',
  '生图/e2e_f88_node-image_gen-single-output.json',
  '生图/e2e_f88_node-image_gen-pack-output.json',
  // 视频上传节点
  '视频上传/atomic_f88_node-video_upload-trial-run.json',
  '视频上传/atomic_f88_node-video_upload-config.json',
  '视频上传/atomic_f88_node-video_upload-validation.json',
  '视频上传/atomic_f88_node-video_upload-var-binding.json',
  // 图文上传节点
  '图文上传/atomic_f88_node-image_text_upload-trial-run.json',
  '图文上传/atomic_f88_node-image_text_upload-config.json',
  '图文上传/atomic_f88_node-image_text_upload-validation.json',
  '图文上传/atomic_f88_node-image_text_upload-var-binding.json',
];

const results = [];
let allPass = true;

for (const c of cases) {
  const full = path.join(CASES_DIR, c);
  if (!fs.existsSync(full)) {
    results.push({ case: c, total: 0, passed: 0, failed: 0, status: 'SKIP', error: '文件不存在' });
    continue;
  }
  const outFile = `/tmp/batch-${Date.now()}-${Math.random().toString(36).slice(2,8)}.json`;
  const name = c.split('/').pop().replace('.json', '');
  console.error(`[${results.length + 1}/${cases.length}] 运行: ${name}...`);
  
  try {
    execSync(`node "${RUNNER}" "${full}" "${outFile}"`, { timeout: 300000, stdio: ['pipe', 'pipe', 'pipe'] });
    const out = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    const steps = out.steps || [];
    const total = steps.length;
    const passed = steps.filter(s => s.status === 'pass').length;
    const failed = steps.filter(s => s.status === 'fail').length;
    const failSteps = steps.filter(s => s.status === 'fail').map(s => `step ${s.index}: ${s.description || s.type} - ${s.error || '?'}`);
    const status = failed === 0 ? 'PASS' : 'FAIL';
    if (failed > 0) allPass = false;
    results.push({ case: name, total, passed, failed, status, failSteps });
    console.error(`  → ${status}: ${passed}/${total}${failed > 0 ? ` (${failed} failures)` : ''}`);
  } catch (err) {
    allPass = false;
    results.push({ case: name, total: 0, passed: 0, failed: 0, status: 'ERROR', error: err.message.slice(0, 200) });
    console.error(`  → ERROR: ${err.message.slice(0, 100)}`);
  }
}

console.log('\n═══════════════════════════════════════════════════════');
console.log('  策略节点端到端测试 - 批量验证结果');
console.log('═══════════════════════════════════════════════════════');
let totalAll = 0, passedAll = 0, failedAll = 0;
for (const r of results) {
  totalAll += r.total;
  passedAll += r.passed;
  failedAll += r.failed;
  const icon = r.status === 'PASS' ? '✅' : r.status === 'SKIP' ? '⏭️' : '❌';
  console.log(`${icon} ${r.case.padEnd(50)} ${r.status === 'SKIP' ? 'SKIP' : `${r.passed}/${r.total}`}`);
  if (r.failSteps) r.failSteps.forEach(f => console.log(`   └─ ${f}`));
  if (r.error && r.status !== 'SKIP') console.log(`   └─ ${r.error}`);
}
console.log('───────────────────────────────────────────────────────');
console.log(`总计: ${passedAll}/${totalAll} 步骤通过, ${results.filter(r=>r.status==='PASS').length}/${results.length} 用例通过`);
console.log(`整体结果: ${allPass ? '✅ ALL PASS' : '❌ HAS FAILURES'}`);
