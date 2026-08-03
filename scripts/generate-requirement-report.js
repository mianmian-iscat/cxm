#!/usr/bin/env node
/**
 * generate-requirement-report.js — 新需求测试报告生成器
 *
 * 读取 run-requirement-tests.js 输出的 execution-results.json，
 * 生成 HTML 本地报告 + 钉钉图文消息 Markdown。
 *
 * 用法:
 *   node scripts/generate-requirement-report.js                              # 默认读 artifacts/execution-results.json
 *   node scripts/generate-requirement-report.js artifacts/my-results.json    # 指定输入
 *   node scripts/generate-requirement-report.js --input x.json --out r.html  # 指定输出
 *   node scripts/generate-requirement-report.js --dingtalk-markdown           # 同时输出钉钉 Markdown
 */
'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_INPUT  = path.join(__dirname, '..', 'artifacts', 'execution-results.json');
const DEFAULT_OUTPUT = path.join(__dirname, '..', 'artifacts', 'requirement-report.html');

// ── CLI ──
function parseArgs() {
  const argv = process.argv.slice(2);
  let input = DEFAULT_INPUT;
  let output = DEFAULT_OUTPUT;
  let dingtalkMd = false;
  for (let i = 0; i < argv.length; i++) {
    if ((argv[i] === '--out' || argv[i] === '-o') && argv[i + 1]) output = argv[++i];
    else if (argv[i] === '--input' && argv[i + 1]) input = argv[++i];
    else if (argv[i] === '--dingtalk-markdown') dingtalkMd = true;
    else if (!argv[i].startsWith('-')) input = argv[i];
  }
  if (!path.isAbsolute(input))  input  = path.resolve(input);
  if (!path.isAbsolute(output)) output = path.resolve(output);
  return { input, output, dingtalkMd };
}

// ── 工具 ──
function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function ms2s(ms) { return (ms / 1000).toFixed(1) + 's'; }
function statusIcon(s) { return { pass: '✅', fail: '❌', skip: '⏭️', error: '💥' }[s] || '❓'; }
function statusColor(s) { return { pass: '#22c55e', fail: '#ef4444', skip: '#a3a3a3', error: '#f97316' }[s] || '#888'; }
function priorityColor(p) { return { P0: '#ef4444', P1: '#f59e0b', P2: '#3b82f6', P3: '#8b5cf6' }[p] || '#888'; }

// ── HTML 报告 ──
function generateHTML(data) {
  const { summary, cases, prd_id, executed_at } = data;
  const total = cases.length;
  const passRate = total > 0 ? ((summary.pass / total) * 100).toFixed(1) : '0.0';
  const totalDuration = cases.reduce((s, c) => s + (c.duration || 0), 0);

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - summary.pass / Math.max(total, 1));

  // 按优先级分组统计
  const byPriority = {};
  for (const c of cases) {
    const p = c.priority || 'P2';
    if (!byPriority[p]) byPriority[p] = { total: 0, pass: 0, fail: 0, error: 0, skip: 0 };
    byPriority[p].total++;
    byPriority[p][c.status]++;
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>需求测试报告 - PRD ${esc(prd_id || '')}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f5f5; color: #1a1a1a; }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
  .header { background: linear-gradient(135deg, #7c3aed, #4f46e5); color: #fff; border-radius: 16px; padding: 32px; margin-bottom: 24px; }
  .header h1 { font-size: 22px; font-weight: 600; margin-bottom: 8px; }
  .header .meta { font-size: 13px; color: #c4b5fd; }
  .header .prd-badge { display: inline-block; background: rgba(255,255,255,0.2); padding: 2px 12px; border-radius: 12px; font-size: 12px; margin-left: 8px; }
  .dashboard { display: grid; grid-template-columns: 200px 1fr; gap: 24px; margin-bottom: 24px; }
  .ring-card { background: #fff; border-radius: 12px; padding: 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .ring-card svg { width: 120px; height: 120px; }
  .ring-card .rate-label { font-size: 12px; color: #888; margin-top: 4px; }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; align-content: start; }
  .stat-card { background: #fff; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .stat-card .num { font-size: 32px; font-weight: 700; }
  .stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
  .priority-table { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .priority-table h3 { font-size: 14px; margin-bottom: 12px; color: #334155; }
  .priority-table table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .priority-table th { text-align: left; padding: 8px 12px; background: #f8fafc; color: #64748b; font-weight: 500; border-bottom: 1px solid #e5e7eb; }
  .priority-table td { padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }
  .filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .filter-btn { padding: 6px 16px; border-radius: 20px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; font-size: 13px; transition: all .15s; }
  .filter-btn:hover { border-color: #7c3aed; color: #7c3aed; }
  .filter-btn.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }
  .case-list { display: flex; flex-direction: column; gap: 8px; }
  .case-item { background: #fff; border-radius: 10px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); cursor: pointer; transition: box-shadow .15s; display: grid; grid-template-columns: 40px 1fr auto auto; align-items: center; gap: 12px; }
  .case-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
  .case-item .icon { font-size: 20px; text-align: center; }
  .case-item .info .name { font-size: 14px; font-weight: 500; }
  .case-item .info .desc { font-size: 11px; color: #999; margin-top: 2px; }
  .case-item .badge { font-size: 11px; padding: 2px 10px; border-radius: 10px; font-weight: 600; color: #fff; }
  .case-item .duration { font-size: 12px; color: #999; min-width: 50px; text-align: right; }
  .detail { display: none; background: #f8fafc; border-top: 1px solid #e5e7eb; padding: 16px 20px; margin-top: 12px; border-radius: 0 0 10px 10px; }
  .detail.open { display: block; }
  .detail h4 { font-size: 13px; color: #64748b; margin-bottom: 8px; }
  .step-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .step-table th { text-align: left; padding: 6px 8px; background: #f1f5f9; color: #64748b; font-weight: 500; }
  .step-table td { padding: 6px 8px; border-top: 1px solid #f1f5f9; }
  .step-table tr.fail td { background: #fef2f2; }
  .error-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 12px; font-size: 12px; color: #991b1b; margin-top: 8px; font-family: monospace; word-break: break-all; white-space: pre-wrap; }
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
  <div class="header">
    <h1>📋 新需求测试报告 <span class="prd-badge">PRD ${esc(prd_id || '-')}</span></h1>
    <div class="meta">执行时间: ${esc(new Date(executed_at || Date.now()).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }))} &nbsp;|&nbsp; CDP: ${esc(data.cdp_url || '-')} &nbsp;|&nbsp; 总耗时: ${totalDuration > 0 ? ms2s(totalDuration) : '-'}</div>
  </div>

  <div class="dashboard">
    <div class="ring-card">
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="${radius}" fill="none" stroke="#e5e7eb" stroke-width="10"/>
        <circle cx="60" cy="60" r="${radius}" fill="none" stroke="${parseFloat(passRate) >= 80 ? '#22c55e' : parseFloat(passRate) >= 50 ? '#f59e0b' : '#ef4444'}" stroke-width="10"
          stroke-dasharray="${circumference}" stroke-dashoffset="${offset}" stroke-linecap="round"
          transform="rotate(-90 60 60)"/>
        <text x="60" y="60" text-anchor="middle" dy="0.35em" font-size="22" font-weight="700" fill="#1a1a1a">${passRate}%</text>
      </svg>
      <div class="rate-label">通过率</div>
    </div>
    <div class="stats">
      <div class="stat-card"><div class="num" style="color:#22c55e">${summary.pass}</div><div class="label">✅ 通过</div></div>
      <div class="stat-card"><div class="num" style="color:#ef4444">${summary.fail}</div><div class="label">❌ 失败</div></div>
      <div class="stat-card"><div class="num" style="color:#f97316">${summary.error}</div><div class="label">💥 异常</div></div>
      <div class="stat-card"><div class="num" style="color:#a3a3a3">${summary.skip}</div><div class="label">⏭️ 跳过</div></div>
    </div>
  </div>

  <!-- 按优先级统计 -->
  <div class="priority-table">
    <h3>📊 按优先级分布</h3>
    <table>
      <tr><th>优先级</th><th>总数</th><th>✅ 通过</th><th>❌ 失败</th><th>💥 异常</th><th>⏭️ 跳过</th><th>通过率</th></tr>
      ${Object.entries(byPriority).sort(([a],[b]) => a.localeCompare(b)).map(([p, s]) => {
        const rate = s.total > 0 ? ((s.pass / s.total) * 100).toFixed(0) + '%' : '-';
        return `<tr><td><span style="color:${priorityColor(p)};font-weight:600">${esc(p)}</span></td><td>${s.total}</td><td>${s.pass || 0}</td><td>${s.fail || 0}</td><td>${s.error || 0}</td><td>${s.skip || 0}</td><td>${rate}</td></tr>`;
      }).join('')}
    </table>
  </div>

  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterCases('all')">全部 (${total})</button>
    <button class="filter-btn" onclick="filterCases('pass')">✅ 通过 (${summary.pass})</button>
    <button class="filter-btn" onclick="filterCases('fail')">❌ 失败 (${summary.fail})</button>
    <button class="filter-btn" onclick="filterCases('error')">💥 异常 (${summary.error})</button>
    <button class="filter-btn" onclick="filterCases('skip')">⏭️ 跳过 (${summary.skip})</button>
  </div>

  <div class="case-list" id="caseList">
    ${cases.map((c, i) => renderCase(c, i)).join('\n')}
  </div>

  <div class="footer">
    web-automation requirement report &middot; PRD ${esc(prd_id || '-')} &middot; generated ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
  </div>
</div>

<script>
function filterCases(status) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.case-item').forEach(item => {
    item.style.display = (status === 'all' || item.dataset.status === status) ? '' : 'none';
  });
}
function toggleDetail(btn) {
  const item = btn.closest('.case-item');
  const detail = item.nextElementSibling;
  if (detail && detail.classList.contains('detail')) detail.classList.toggle('open');
}
</script>
</body>
</html>`;
}

function renderCase(c, idx) {
  const icon = statusIcon(c.status);
  const color = statusColor(c.status);
  const dur = c.duration ? ms2s(c.duration) : '-';
  const priority = c.priority || '-';
  const pColor = priorityColor(priority);

  let stepsHtml = '';
  if (c.steps && c.steps.length > 0) {
    stepsHtml = `<h4>执行步骤 (${c.steps.length})</h4>
    <table class="step-table">
      <tr><th>#</th><th>类型</th><th>描述</th><th>状态</th></tr>
      ${c.steps.map(s => {
        const sIcon = s.status === 'pass' ? '✅' : s.status === 'fail' ? '❌' : '⏭️';
        const rowClass = s.status === 'fail' ? 'fail' : '';
        return `<tr class="${rowClass}"><td>${s.index || '-'}</td><td>${esc(s.type)}</td><td>${esc(s.description || '-')}</td><td>${sIcon}</td></tr>`;
      }).join('')}
    </table>`;
  }

  let errorHtml = '';
  if (c.error && c.error.message) {
    errorHtml = `<div class="error-box">${esc(c.error.message)}</div>`;
  }

  let skipHtml = '';
  if (c.status === 'skip' && c.skipReason) {
    skipHtml = `<div class="error-box" style="background:#f8fafc;border-color:#e2e8f0;color:#64748b">⏭️ ${esc(c.skipReason)}</div>`;
  }

  const hasDetail = stepsHtml || errorHtml || skipHtml;

  return `    <div class="case-item" data-status="${esc(c.status)}" ${hasDetail ? 'onclick="toggleDetail(this)"' : ''}>
      <div class="icon">${icon}</div>
      <div class="info">
        <div class="name">${esc(c.name || c.id)}</div>
        <div class="desc">${esc(c.description || c.filename || '')}</div>
      </div>
      <span class="badge" style="background:${pColor}">${esc(priority)}</span>
      <div class="duration">${dur}</div>
    </div>
    ${hasDetail ? `<div class="detail">${stepsHtml}${errorHtml}${skipHtml}</div>` : '<div class="detail"></div>'}`;
}

// ── 钉钉 Markdown 报告 ──
function generateDingtalkMarkdown(data) {
  const { summary, cases, prd_id } = data;
  const passRate = summary.passRate || '0%';
  const total = cases.length;

  let md = `## 📋 新需求测试报告 — PRD ${prd_id || '-'}\n\n`;
  md += `**通过率: ${passRate}** | 总计 ${total} | ✅ ${summary.pass} | ❌ ${summary.fail} | 💥 ${summary.error} | ⏭️ ${summary.skip}\n\n`;
  md += `---\n\n`;

  // 失败/异常用例详情
  const failed = cases.filter(c => c.status === 'fail' || c.status === 'error');
  if (failed.length > 0) {
    md += `### ❌ 失败用例 (${failed.length})\n\n`;
    for (const c of failed) {
      md += `- **${c.name || c.id}** (${c.priority}): ${c.error?.message || '未知错误'}\n`;
    }
    md += '\n';
  }

  // 通过用例列表
  const passed = cases.filter(c => c.status === 'pass');
  if (passed.length > 0) {
    md += `### ✅ 通过用例 (${passed.length})\n\n`;
    for (const c of passed) {
      md += `- ${c.name || c.id} (${c.priority})\n`;
    }
    md += '\n';
  }

  md += `---\n*报告生成时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}*\n`;

  return md;
}

// ── 入口 ──
const { input, output, dingtalkMd } = parseArgs();

if (!fs.existsSync(input)) {
  console.error(`输入文件不存在: ${input}`);
  console.error('用法: node scripts/generate-requirement-report.js [results.json] [--out report.html] [--dingtalk-markdown]');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(input, 'utf8'));
const html = generateHTML(data);

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html, 'utf8');
console.log(`✅ HTML 报告已生成: ${output}`);

if (dingtalkMd) {
  const mdContent = generateDingtalkMarkdown(data);
  const mdPath = output.replace(/\.html$/, '.md');
  fs.writeFileSync(mdPath, mdContent, 'utf8');
  console.log(`✅ 钉钉 Markdown 已生成: ${mdPath}`);

  // 同时输出到 stdout 方便管道传输
  console.log('\n--- 钉钉消息内容 ---');
  console.log(mdContent);
  console.log('--- END ---\n');
}

console.log(`   PRD: ${data.prd_id || '-'} | ${data.summary.total} 用例 | 通过 ${data.summary.pass} | 失败 ${data.summary.fail} | 异常 ${data.summary.error} | 跳过 ${data.summary.skip}`);
