#!/usr/bin/env node
/**
 * 统一批量运行器 — 一键执行目录下所有用例并生成汇总报告
 *
 * 用法：
 *   node batch-runner.js <用例目录或文件列表> [选项]
 *   node batch-runner.js eval/cases/f88-test/上游素材生产链路/种草链路/
 *   node batch-runner.js eval/cases/f88-test/ --filter "seed" --concurrency 1
 *
 * 选项：
 *   --filter <keyword>    只执行文件名包含 keyword 的用例
 *   --concurrency <n>     并发数（默认 1，串行执行最稳定）
 *   --output <dir>        结果输出目录（默认 artifacts/batch-results/）
 *   --retry-failed        失败用例自动重试一次
 *   --timeout <ms>        单用例超时（默认 120000）
 *   --report              生成 HTML 汇总报告
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const RUNNER = path.join(__dirname, 'run-browser-test.js');
const DEFAULT_OUTPUT = path.join(__dirname, '..', 'artifacts', 'batch-results');
const DEFAULT_TIMEOUT = 120000;

// ── 参数解析 ──
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    targets: [],
    filter: null,
    concurrency: 1,
    output: DEFAULT_OUTPUT,
    retryFailed: false,
    timeout: DEFAULT_TIMEOUT,
    report: false,
  };
  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--filter': opts.filter = args[++i]; break;
      case '--concurrency': opts.concurrency = parseInt(args[++i]) || 1; break;
      case '--output': opts.output = args[++i]; break;
      case '--retry-failed': opts.retryFailed = true; break;
      case '--timeout': opts.timeout = parseInt(args[++i]) || DEFAULT_TIMEOUT; break;
      case '--report': opts.report = true; break;
      default: opts.targets.push(args[i]);
    }
  }
  if (!opts.targets.length) {
    console.error('用法: node batch-runner.js <用例目录或文件> [--filter keyword] [--report]');
    process.exit(1);
  }
  return opts;
}

// ── 收集用例文件 ──
function collectCases(targets, filter) {
  const files = [];
  for (const target of targets) {
    const resolved = path.resolve(target);
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      if (resolved.endsWith('.json')) files.push(resolved);
    } else if (fs.existsSync(resolved) && fs.statSync(resolved).isDirectory()) {
      // 递归扫描目录下所有 .json 用例文件
      const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
            walk(full);
          } else if (entry.isFile() && entry.name.endsWith('.json') && !entry.name.startsWith('_')) {
            // 验证是有效用例（含 id + steps）
            try {
              const j = JSON.parse(fs.readFileSync(full, 'utf8'));
              if (j.id && Array.isArray(j.steps)) files.push(full);
            } catch (_) {}
          }
        }
      };
      walk(resolved);
    } else {
      console.error(`⚠ 目标不存在: ${target}`);
    }
  }
  // 过滤
  if (filter) {
    return files.filter(f => path.basename(f).includes(filter));
  }
  return files;
}

// ── 执行单个用例 ──
function runCase(caseFile, outputDir, timeout) {
  const baseName = path.basename(caseFile, '.json');
  const resultFile = path.join(outputDir, `${baseName}-result.json`);
  const start = Date.now();
  try {
    execSync(`node "${RUNNER}" "${caseFile}" "${resultFile}"`, {
      encoding: 'utf8',
      timeout,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    // runner 非零退出也算完成（用例可能 fail/error）
    if (!fs.existsSync(resultFile)) {
      // runner 本身崩溃
      const errorResult = {
        id: baseName,
        name: baseName,
        status: 'error',
        error: { message: e.message?.substring(0, 200) || 'runner 执行异常' },
        steps: [],
        duration: Date.now() - start,
      };
      fs.writeFileSync(resultFile, JSON.stringify(errorResult, null, 2));
    }
  }
  // 读取结果
  try {
    return JSON.parse(fs.readFileSync(resultFile, 'utf8'));
  } catch (_) {
    return { id: baseName, name: baseName, status: 'error', error: { message: '结果文件读取失败' }, steps: [], duration: Date.now() - start };
  }
}

// ── 生成汇总报告 ──
function generateReport(results, outputDir) {
  const total = results.length;
  const pass = results.filter(r => r.status === 'pass').length;
  const fail = results.filter(r => r.status === 'fail').length;
  const error = results.filter(r => r.status === 'error').length;
  const healed = results.filter(r => r.steps?.some(s => s.status === 'healed')).length;
  const totalDuration = results.reduce((s, r) => s + (r.duration || 0), 0);

  const summary = {
    timestamp: new Date().toISOString(),
    total, pass, fail, error, healed,
    passRate: total ? `${((pass / total) * 100).toFixed(1)}%` : '0%',
    totalDurationMs: totalDuration,
    totalDurationSec: (totalDuration / 1000).toFixed(1),
    results: results.map(r => ({
      id: r.id,
      name: r.name,
      status: r.status,
      duration: r.duration,
      steps: r.steps?.length || 0,
      error: r.error?.message || r.steps?.find(s => s.status === 'fail')?.assertResult?.message || null,
    })),
  };

  // JSON 汇总
  const summaryPath = path.join(outputDir, 'batch-summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

  // 控制台输出
  console.log('\n' + '═'.repeat(60));
  console.log(`  批量执行报告  ${summary.timestamp}`);
  console.log('═'.repeat(60));
  console.log(`  总计: ${total}  通过: ${pass}  失败: ${fail}  错误: ${error}  自愈: ${healed}`);
  console.log(`  通过率: ${summary.passRate}  总耗时: ${summary.totalDurationSec}s`);
  console.log('─'.repeat(60));

  for (const r of summary.results) {
    const icon = r.status === 'pass' ? '✓' : r.status === 'fail' ? '✗' : '⚠';
    const dur = ((r.duration || 0) / 1000).toFixed(1);
    console.log(`  ${icon} [${r.status.toUpperCase().padEnd(5)}] ${r.id} (${dur}s, ${r.steps} steps)`);
    if (r.error) console.log(`         └─ ${r.error.substring(0, 80)}`);
  }
  console.log('═'.repeat(60));
  console.log(`  结果目录: ${outputDir}`);
  console.log(`  汇总文件: ${summaryPath}\n`);

  return summary;
}

// ── 主入口 ──
function main() {
  const opts = parseArgs();
  const cases = collectCases(opts.targets, opts.filter);

  if (!cases.length) {
    console.error('未找到有效用例文件');
    process.exit(1);
  }

  console.log(`\n🚀 批量执行 ${cases.length} 个用例 (concurrency=${opts.concurrency}, timeout=${opts.timeout}ms)`);
  console.log(`   输出目录: ${opts.output}\n`);

  fs.mkdirSync(opts.output, { recursive: true });

  const results = [];
  const startTime = Date.now();

  for (let i = 0; i < cases.length; i++) {
    const caseFile = cases[i];
    const name = path.basename(caseFile, '.json');
    process.stdout.write(`  [${i + 1}/${cases.length}] ${name} ... `);

    const result = runCase(caseFile, opts.output, opts.timeout);
    results.push(result);

    const icon = result.status === 'pass' ? '✓' : result.status === 'fail' ? '✗' : '⚠';
    console.log(`${icon} ${result.status.toUpperCase()} (${((result.duration || 0) / 1000).toFixed(1)}s)`);
  }

  // 失败重试
  if (opts.retryFailed) {
    const failed = results.filter(r => r.status !== 'pass');
    if (failed.length) {
      console.log(`\n🔄 重试 ${failed.length} 个失败用例...`);
      for (const f of failed) {
        const caseFile = cases.find(c => path.basename(c, '.json') === f.id);
        if (!caseFile) continue;
        process.stdout.write(`  [retry] ${f.id} ... `);
        const retryResult = runCase(caseFile, opts.output, opts.timeout);
        // 替换原结果
        const idx = results.indexOf(f);
        if (idx >= 0) results[idx] = retryResult;
        const icon = retryResult.status === 'pass' ? '✓' : '✗';
        console.log(`${icon} ${retryResult.status.toUpperCase()}`);
      }
    }
  }

  const totalWall = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\n⏱ 总墙钟时间: ${totalWall}s`);

  generateReport(results, opts.output);
}

main();
