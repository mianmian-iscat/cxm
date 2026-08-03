#!/usr/bin/env node
/**
 * 回归测试 HTML 报告生成器
 *
 * 读取 run-op-regression.js 输出的 JSON 结果，生成自包含 HTML 报告。
 *
 * 用法：
 *   node scripts/generate-regression-report.js                                    # 默认读 artifacts/op-regression-results.json
 *   node scripts/generate-regression-report.js artifacts/my-results.json          # 指定输入
 *   node scripts/generate-regression-report.js artifacts/my-results.json --out r.html
 */
'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_INPUT  = path.join(__dirname, '..', 'artifacts', 'op-regression-results.json');
const DEFAULT_OUTPUT = path.join(__dirname, '..', 'artifacts', 'regression-report.html');

// ── CLI 解析 ──
function parseArgs() {
  const args = process.argv.slice(2);
  let input = DEFAULT_INPUT;
  let output = DEFAULT_OUTPUT;
  for (let i = 0; i < args.length; i++) {
    if ((args[i] === '--out' || args[i] === '-o') && args[i + 1]) {
      output = args[++i];
    } else if (!args[i].startsWith('-')) {
      input = args[i];
    }
  }
  if (!path.isAbsolute(input))  input  = path.resolve(input);
  if (!path.isAbsolute(output)) output = path.resolve(output);
  return { input, output };
}

// ── 工具函数 ──
function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function ms2s(ms) { return (ms / 1000).toFixed(1) + 's'; }
function statusIcon(s) { return { pass: '✅', fail: '❌', skip: '⏭️', error: '💥' }[s] || '❓'; }
function statusColor(s) { return { pass: '#22c55e', fail: '#ef4444', skip: '#a3a3a3', error: '#f97316' }[s] || '#888'; }
function priorityColor(p) { return { P0: '#ef4444', P1: '#f59e0b', P2: '#3b82f6', P3: '#8b5cf6' }[p] || '#888'; }

// ── 主逻辑 ──
function generate(data) {
  const { summary, results } = data;
  const passRate = summary.total > 0 ? ((summary.pass / summary.total) * 100).toFixed(1) : '0.0';
  const totalDuration = results.reduce((sum, r) => sum + (r.duration || 0), 0);

  // 环形进度条 SVG
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - summary.pass / Math.max(summary.total, 1));

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>回归测试报告 - ${esc(summary.time)}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f5f5; color: #1a1a1a; }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
  
  /* Header */
  .header { background: linear-gradient(135deg, #1e293b, #334155); color: #fff; border-radius: 16px; padding: 32px; margin-bottom: 24px; }
  .header h1 { font-size: 22px; font-weight: 600; margin-bottom: 8px; }
  .header .meta { font-size: 13px; color: #94a3b8; }
  
  /* Dashboard */
  .dashboard { display: grid; grid-template-columns: 200px 1fr; gap: 24px; margin-bottom: 24px; }
  .ring-card { background: #fff; border-radius: 12px; padding: 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .ring-card svg { width: 120px; height: 120px; }
  .ring-card .rate { font-size: 28px; font-weight: 700; margin-top: 8px; }
  .ring-card .rate-label { font-size: 12px; color: #888; }
  
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; align-content: start; }
  .stat-card { background: #fff; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .stat-card .num { font-size: 32px; font-weight: 700; }
  .stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
  
  /* Filter tabs */
  .filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .filter-btn { padding: 6px 16px; border-radius: 20px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; font-size: 13px; transition: all .15s; }
  .filter-btn:hover { border-color: #3b82f6; color: #3b82f6; }
  .filter-btn.active { background: #1e293b; color: #fff; border-color: #1e293b; }
  
  /* Case list */
  .case-list { display: flex; flex-direction: column; gap: 8px; }
  .case-item { background: #fff; border-radius: 10px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); cursor: pointer; transition: box-shadow .15s; display: grid; grid-template-columns: 40px 1fr auto auto; align-items: center; gap: 12px; }
  .case-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
  .case-item .icon { font-size: 20px; text-align: center; }
  .case-item .info .name { font-size: 14px; font-weight: 500; }
  .case-item .info .file { font-size: 11px; color: #999; margin-top: 2px; }
  .case-item .badge { font-size: 11px; padding: 2px 10px; border-radius: 10px; font-weight: 600; color: #fff; }
  .case-item .duration { font-size: 12px; color: #999; min-width: 50px; text-align: right; }
  
  /* Detail panel */
  .detail { display: none; background: #f8fafc; border-top: 1px solid #e5e7eb; padding: 16px 20px; margin-top: 12px; border-radius: 0 0 10px 10px; }
  .detail.open { display: block; }
  .detail h4 { font-size: 13px; color: #64748b; margin-bottom: 8px; }
  .step-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .step-table th { text-align: left; padding: 6px 8px; background: #f1f5f9; color: #64748b; font-weight: 500; }
  .step-table td { padding: 6px 8px; border-top: 1px solid #f1f5f9; }
  .step-table tr.fail td { background: #fef2f2; }
  .error-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 12px; font-size: 12px; color: #991b1b; margin-top: 8px; font-family: monospace; word-break: break-all; white-space: pre-wrap; }
  
  /* Footer */
  .footer { text-align: center; padding: 24px; font-size: 11px; color: #aaa; }

  @media (max-width: 700px) {
    .dashboard { grid-template-columns: 1fr; }
    .stats { grid-template-columns: repeat(2, 1fr); }
    .case-item { grid-template-columns: 30px 1fr auto; }
    .case-item .duration { display: none; }
  }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>📋 原创保护 UI 回归测试报告</h1>
    <div class="meta">执行时间: ${esc(new Date(summary.time).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }))} &nbsp;|&nbsp; CDP: ${esc(summary.cdpUrl || '-')} &nbsp;|&nbsp; 总耗时: ${totalDuration > 0 ? ms2s(totalDuration) : '-'}</div>
  </div>

  <!-- Dashboard -->
  <div class="dashboard">
    <div class="ring-card">
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="${radius}" fill="none" stroke="#e5e7eb" stroke-width="10"/>
        <circle cx="60" cy="60" r="${radius}" fill="none" stroke="${passRate >= 80 ? '#22c55e' : passRate >= 50 ? '#f59e0b' : '#ef4444'}" stroke-width="10"
          stroke-dasharray="${circumference}" stroke-dashoffset="${offset}" stroke-linecap="round"
          transform="rotate(-90 60 60)"/>
        <text x="60" y="60" text-anchor="middle" dy="0.35em" font-size="22" font-weight="700" fill="#1a1a1a">${passRate}%</text>
      </svg>
      <div class="rate-label">通过率</div>
    </div>
    <div class="stats">
      <div class="stat-card"><div class="num" style="color:#22c55e">${summary.pass}</div><div class="label">✅ 通过</div></div>
      <div class="stat-card"><div class="num" style="color:#ef4444">${summary.fail}</div><div class="label">❌ 失败</div></div>
      <div class="stat-card"><div class="num" style="color:#a3a3a3">${summary.skip}</div><div class="label">⏭️ 跳过</div></div>
      <div class="stat-card"><div class="num" style="color:#f97316">${summary.error}</div><div class="label">💥 异常</div></div>
    </div>
  </div>

  <!-- Filter -->
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterCases('all')">全部 (${summary.total})</button>
    <button class="filter-btn" onclick="filterCases('pass')">✅ 通过 (${summary.pass})</button>
    <button class="filter-btn" onclick="filterCases('fail')">❌ 失败 (${summary.fail})</button>
    <button class="filter-btn" onclick="filterCases('error')">💥 异常 (${summary.error})</button>
    <button class="filter-btn" onclick="filterCases('skip')">⏭️ 跳过 (${summary.skip})</button>
  </div>

  <!-- Case List -->
  <div class="case-list" id="caseList">
${results.map((r, idx) => renderCase(r, idx)).join('\n')}
  </div>

  <div class="footer">
    web-automation regression report &middot; generated ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
  </div>
</div>

<script>
function filterCases(status) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.case-item').forEach(item => {
    const s = item.dataset.status;
    item.style.display = (status === 'all' || s === status) ? '' : 'none';
    // 隐藏关联 detail
    const detail = item.nextElementSibling;
    if (detail && detail.classList.contains('detail')) detail.classList.remove('open');
  });
}

function toggleDetail(btn) {
  const item = btn.closest('.case-item');
  const detail = item.nextElementSibling;
  if (detail && detail.classList.contains('detail')) {
    detail.classList.toggle('open');
  }
}
</script>
</body>
</html>`;
}

function renderCase(r, idx) {
  const icon = statusIcon(r.status);
  const color = statusColor(r.status);
  const dur = r.duration ? ms2s(r.duration) : '-';
  const priority = r.priority || '-';
  const pColor = priorityColor(priority);
  
  // 步骤详情
  let stepsHtml = '';
  if (r.steps && r.steps.length > 0) {
    stepsHtml = `<h4>执行步骤 (${r.steps.length})</h4>
    <table class="step-table">
      <tr><th>#</th><th>类型</th><th>描述</th><th>状态</th></tr>
      ${r.steps.map(s => {
        const sIcon = s.status === 'pass' ? '✅' : s.status === 'fail' ? '❌' : '⏭️';
        const rowClass = s.status === 'fail' ? 'fail' : '';
        return `<tr class="${rowClass}"><td>${s.index}</td><td>${esc(s.type)}</td><td>${esc(s.description || '-')}</td><td>${sIcon}</td></tr>`;
      }).join('')}
    </table>`;
  }

  // 错误信息
  let errorHtml = '';
  if (r.error && r.error.message) {
    errorHtml = `<div class="error-box">${esc(r.error.message)}</div>`;
  }

  // skip 原因
  let skipHtml = '';
  if (r.status === 'skip' && r.skipReason) {
    skipHtml = `<div class="error-box" style="background:#f8fafc;border-color:#e2e8f0;color:#64748b">⏭️ ${esc(r.skipReason)}</div>`;
  }

  // post asserts
  let postAssertHtml = '';
  if (r.postAsserts && r.postAsserts.length > 0) {
    const failed = r.postAsserts.filter(a => !a.pass);
    if (failed.length > 0) {
      postAssertHtml = `<h4 style="margin-top:12px">API 断言失败</h4>` +
        failed.map(a => `<div class="error-box">${esc(a.desc || a.description || '')}: expected=${esc(JSON.stringify(a.expected))}, actual=${esc(a.actual || '-')}</div>`).join('');
    }
  }

  const hasDetail = stepsHtml || errorHtml || skipHtml || postAssertHtml;

  return `    <div class="case-item" data-status="${esc(r.status)}" ${hasDetail ? 'onclick="toggleDetail(this)"' : ''}>
      <div class="icon">${icon}</div>
      <div class="info">
        <div class="name">${esc(r.name || r.id || r.file)}</div>
        <div class="file">${esc(r.file)}</div>
      </div>
      <span class="badge" style="background:${pColor}">${esc(priority)}</span>
      <div class="duration">${dur}</div>
    </div>
    ${hasDetail ? `<div class="detail">${stepsHtml}${errorHtml}${skipHtml}${postAssertHtml}</div>` : '<div class="detail"></div>'}`;
}

// ── 入口 ──
const { input, output } = parseArgs();
if (!fs.existsSync(input)) {
  console.error(`输入文件不存在: ${input}`);
  console.error('用法: node scripts/generate-regression-report.js [results.json] [--out report.html]');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(input, 'utf8'));
const html = generate(data);

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html, 'utf8');
console.log(`✅ 报告已生成: ${output}`);
console.log(`   ${data.summary.total} 个用例 | 通过 ${data.summary.pass} | 失败 ${data.summary.fail} | 异常 ${data.summary.error} | 跳过 ${data.summary.skip}`);
