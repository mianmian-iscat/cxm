#!/usr/bin/env node
/**
 * promote_to_regression.js — 新需求测试通过后，自动将 PASS 用例入库到回归套件
 *
 * 用法:
 *   node scripts/promote_to_regression.js --results <execution-results.json> [--prd-id <id>] [--dry-run]
 *
 * 输入: execution-results.json (来自 run-requirement-tests.js 输出)
 * 行为:
 *   1. 读取执行结果，筛选 status=pass 的用例
 *   2. 将用例文件复制到 eval/cases/f88-test/ 主目录
 *   3. 更新 regression_manifest.json
 *   4. 更新 SKILL.md 用例表
 *   5. 可选 git commit
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const WORKSPACE = path.resolve(__dirname, '..');
const CASES_DIR = path.join(WORKSPACE, 'eval', 'cases', 'f88-test');
const MANIFEST_PATH = path.join(WORKSPACE, 'regression_manifest.json');
const SKILL_MD_PATH = path.join(WORKSPACE, 'scenes', 'f88-test', 'SKILL.md');

// ── CLI 参数解析 ──
const args = process.argv.slice(2);
let resultsFile = '';
let prdId = '';
let dryRun = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--results' && args[i + 1]) resultsFile = args[++i];
  else if (args[i] === '--prd-id' && args[i + 1]) prdId = args[++i];
  else if (args[i] === '--dry-run') dryRun = true;
}

if (!resultsFile) {
  console.error('用法: node promote_to_regression.js --results <file.json> [--prd-id <id>] [--dry-run]');
  process.exit(1);
}

// ── 工具函数 ──
function log(msg, level = 'INFO') {
  const ts = new Date().toISOString().substring(11, 19);
  const icon = level === 'OK' ? '✅' : level === 'WARN' ? '⚠️' : level === 'ERR' ? '❌' : 'ℹ️';
  console.log(`${icon} [${ts}] ${msg}`);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function writeJson(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n');
}

// ── 主流程 ──
function main() {
  // 1. 读取执行结果
  const results = readJson(path.resolve(resultsFile));
  const cases = results.cases || results;

  if (!Array.isArray(cases)) {
    log('执行结果格式错误，需要 { cases: [...] } 或 [...] 数组', 'ERR');
    process.exit(1);
  }

  log(`读取执行结果: ${cases.length} 条用例`);

  // 2. 筛选 PASS 用例
  const passed = cases.filter(c => c.status === 'pass' || c.status === 'PASS');
  const failed = cases.filter(c => c.status === 'fail' || c.status === 'FAIL');
  const skipped = cases.filter(c => c.status === 'skip' || c.status === 'SKIP');

  log(`PASS: ${passed.length}, FAIL: ${failed.length}, SKIP: ${skipped.length}`);

  if (passed.length === 0) {
    log('没有 PASS 的用例，跳过入库', 'WARN');
    return;
  }

  // 3. 复制用例到主目录
  const promoted = [];
  const skipped_existing = [];

  for (const tc of passed) {
    const srcFile = tc.file || tc.source_file;
    if (!srcFile) {
      log(`用例 ${tc.id || tc.name} 缺少文件路径，跳过`, 'WARN');
      continue;
    }

    const srcPath = path.resolve(srcFile);
    const filename = path.basename(srcPath);
    const destPath = path.join(CASES_DIR, filename);

    // 检查是否已存在
    if (fs.existsSync(destPath)) {
      skipped_existing.push(filename);
      log(`已存在: ${filename}`, 'WARN');
      continue;
    }

    if (!dryRun) {
      // 读取并更新用例内容
      let caseContent = readJson(srcPath);

      // 添加回归标记
      caseContent._promoted = {
        from_prd: prdId || 'unknown',
        promoted_at: new Date().toISOString(),
        original_file: srcFile
      };

      // 确保有 regression 类别标记
      if (!caseContent.tags) caseContent.tags = [];
      if (!caseContent.tags.includes('regression')) {
        caseContent.tags.push('regression');
      }

      writeJson(destPath, caseContent);
      promoted.push(filename);
      log(`入库: ${filename}`);
    } else {
      promoted.push(filename);
      log(`[DRY-RUN] 将入库: ${filename}`);
    }
  }

  log(`入库 ${promoted.length} 条，跳过已存在 ${skipped_existing.length} 条`);

  if (promoted.length === 0) {
    log('无新用例需要入库', 'WARN');
    return;
  }

  // 4. 更新 regression_manifest.json
  if (!dryRun) {
    try {
      const manifest = readJson(MANIFEST_PATH);
      manifest.last_updated = new Date().toISOString().substring(0, 10);

      // 将新用例添加到 f88-full-weekly 套件
      if (manifest.suites['f88-full-weekly']) {
        log(`manifest 更新: last_updated = ${manifest.last_updated}`);
        writeJson(MANIFEST_PATH, manifest);
      }
    } catch (e) {
      log(`manifest 更新失败: ${e.message}`, 'WARN');
    }
  }

  // 5. 更新 SKILL.md
  if (!dryRun) {
    try {
      let skillMd = fs.readFileSync(SKILL_MD_PATH, 'utf-8');
      const newRows = promoted.map(f => {
        const caseData = readJson(path.join(CASES_DIR, f));
        const name = caseData.name || f;
        const desc = caseData.description || '';
        return `| \`${f}\` | 新需求 PRD-${prdId || '?'} | ${desc.substring(0, 80)} |`;
      });

      // 在"### 新需求自动入库"区域追加（如不存在则创建）
      if (skillMd.includes('### 新需求自动入库')) {
        const marker = '### 新需求自动入库';
        const idx = skillMd.indexOf(marker);
        const afterHeader = skillMd.indexOf('\n', skillMd.indexOf('|------|', idx)) + 1;
        skillMd = skillMd.substring(0, afterHeader) + newRows.join('\n') + '\n' + skillMd.substring(afterHeader);
      } else {
        skillMd += `\n### 新需求自动入库\n\n| 用例 | 来源 | 描述 |\n|------|------|------|\n${newRows.join('\n')}\n`;
      }

      fs.writeFileSync(SKILL_MD_PATH, skillMd);
      log(`SKILL.md 已更新: +${promoted.length} 行`);
    } catch (e) {
      log(`SKILL.md 更新失败: ${e.message}`, 'WARN');
    }
  }

  // 6. 输出汇总
  const summary = {
    prd_id: prdId || 'unknown',
    promoted_at: new Date().toISOString(),
    total_results: cases.length,
    passed: passed.length,
    failed: failed.length,
    skipped: skipped.length,
    promoted_files: promoted,
    skipped_existing: skipped_existing
  };

  const summaryPath = path.join(WORKSPACE, 'artifacts', `promotion-${prdId || Date.now()}.json`);
  if (!dryRun) {
    fs.mkdirSync(path.dirname(summaryPath), { recursive: true });
    writeJson(summaryPath, summary);
    log(`汇总报告: ${summaryPath}`);
  }

  console.log('\n════════════════════════════════════');
  console.log(`  回归入库完成: ${promoted.length} 条用例已入库`);
  console.log(`  跳过已存在: ${skipped_existing.length} 条`);
  console.log(`  失败未入库: ${failed.length} 条`);
  console.log('════════════════════════════════════\n');
}

main();
