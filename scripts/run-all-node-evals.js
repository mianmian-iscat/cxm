#!/usr/bin/env node
/**
 * 批量运行所有 F88 节点 eval 用例
 * 逐个运行，失败即记录，最后汇总
 */
'use strict';
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const CASES_DIR = path.join(__dirname, '..', 'eval', 'cases', 'f88-test');
const RUNNER = path.join(__dirname, 'run-browser-test.js');

const CASES = [
  'ui_f88_create_llm_text_strategy.json',
  'ui_f88_create_image_gen_strategy.json',
  'ui_f88_create_map_image_strategy.json',
  'ui_f88_create_season_tag_strategy.json',
  'ui_f88_create_industry_tag_strategy.json',
  'ui_f88_create_pricing_strategy.json',
  'ui_f88_create_manual_audit_strategy.json',
  'ui_f88_create_style_alloc_strategy.json',
  'ui_f88_create_fabric_tryon_strategy.json',
  'ui_f88_create_image_crop_strategy.json',
  'ui_f88_create_match_score_strategy.json',
  'ui_f88_create_caption_strategy.json',
  'ui_f88_create_redesign_prompt_strategy.json',
  'ui_f88_create_video_gen_strategy.json',
  'ui_f88_create_auto_audit_strategy.json',
  'ui_f88_create_hd_enhance_strategy.json',
  'ui_f88_create_video_upload_strategy.json',
];

// Allow specifying a start index
const startIdx = parseInt(process.argv[2] || '0', 10);
const results = [];

console.log(`=== 批量运行 F88 节点 eval 用例 ===`);
console.log(`起始索引: ${startIdx}, 共 ${CASES.length - startIdx} 个\n`);

for (let i = startIdx; i < CASES.length; i++) {
  const caseFile = CASES[i];
  const caseName = caseFile.replace('ui_f88_create_', '').replace('_strategy.json', '');
  const outputFile = `/tmp/eval-batch-${caseName}.json`;

  console.log(`[${i + 1}/${CASES.length}] ${caseName}...`);
  const startTime = Date.now();

  try {
    execSync(`node "${RUNNER}" "${path.join(CASES_DIR, caseFile)}" "${outputFile}"`, {
      timeout: 180000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const data = JSON.parse(fs.readFileSync(outputFile, 'utf-8'));
    const steps = data.steps || [];
    const passed = steps.filter(s => s.status === 'pass').length;
    const failed = steps.filter(s => s.status !== 'pass');
    const duration = ((data.duration || 0) / 1000).toFixed(1);

    const result = {
      name: caseName,
      status: data.status,
      passed: `${passed}/${steps.length}`,
      duration: `${duration}s`,
      failedSteps: failed.map(s => `step${s.index}: ${s.type} ${s.description?.substring(0, 40)}`),
    };
    results.push(result);

    if (data.status === 'pass') {
      console.log(`  ✓ PASS (${passed}/${steps.length}) ${duration}s`);
    } else {
      console.log(`  ✗ ${data.status.toUpperCase()} (${passed}/${steps.length}) ${duration}s`);
      failed.forEach(s => {
        console.log(`    step${s.index}: ${s.type} "${s.description?.substring(0, 50)}" [${s.status}]`);
        if (s.error) console.log(`      error: ${String(s.error).substring(0, 80)}`);
      });
    }
  } catch (e) {
    results.push({ name: caseName, status: 'error', error: e.message?.substring(0, 80) });
    console.log(`  ✗ ERROR: ${e.message?.substring(0, 80)}`);
  }
}

// Summary
console.log('\n=== 汇总 ===');
const passCount = results.filter(r => r.status === 'pass').length;
const failCount = results.filter(r => r.status !== 'pass').length;
console.log(`通过: ${passCount}/${results.length}, 失败: ${failCount}`);
results.forEach(r => {
  const icon = r.status === 'pass' ? '✓' : '✗';
  console.log(`  ${icon} ${r.name}: ${r.passed || r.status} ${r.duration || ''}`);
  if (r.failedSteps) r.failedSteps.forEach(f => console.log(`      ${f}`));
});

// Write summary to file
fs.writeFileSync('/tmp/eval-batch-summary.json', JSON.stringify(results, null, 2));
console.log('\n详细结果已保存到 /tmp/eval-batch-summary.json');
