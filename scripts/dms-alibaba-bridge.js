#!/usr/bin/env node
/**
 * scripts/dms-alibaba-bridge.js — dms-alibaba CLI 桥（一期 dbAssert 专用）
 *
 * 职责：
 *   封装 `dms-alibaba sql query <group> --db <db> --sql <sql>` 命令，
 *   stdout 吐纯 JSON，供 Python 层 step_executor._handle_db_assert 消费。
 *
 * 设计原则：
 *   - 零外部依赖（纯 Node.js 标准库）
 *   - 超时保护（默认 30s，可 --timeout 覆盖）
 *   - 结构化错误（不抛异常，统一 JSON 返回，Python 端按 status 判断）
 *   - 复用现有 dms-alibaba 安装路径（`/Users/caoxuemei/dms-alibaba/bin/dms-alibaba`）
 *
 * CLI:
 *   node dms-alibaba-bridge.js --group <g> --db <db> --sql <sql> [--params <json>] [--timeout <ms>] [--bin <path>]
 *
 * 输出契约（stdout 始终为 JSON）：
 *   {
 *     "status": "ok" | "error" | "timeout",
 *     "group": "...", "db": "...", "sql": "...",
 *     "rows": [...],
 *     "rowCount": 0,
 *     "durationMs": 1234,
 *     "stderr": "...",
 *     "error": "..."   // 仅失败时
 *   }
 */

'use strict';

const { spawn } = require('child_process');
const path = require('path');

const DEFAULT_BIN = '/Users/caoxuemei/dms-alibaba/bin/dms-alibaba';
const DEFAULT_TIMEOUT_MS = 30000;
const MAX_SQL_LEN = 4000;

/**
 * 解析命令行参数（极简版，只支持 --key value 与 --key=value）
 */
function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const body = a.slice(2);
    if (body.includes('=')) {
      const [k, ...rest] = body.split('=');
      args[k] = rest.join('=');
    } else {
      const v = argv[i + 1];
      if (v && !v.startsWith('--')) {
        args[body] = v;
        i++;
      } else {
        args[body] = true;
      }
    }
  }
  return args;
}

/**
 * 把 params 字典应用到 SQL（:name 占位符替换）。
 * 仅做字符串替换，不防注入（防注入靠 Python 层 check_sql_readonly）。
 */
function applyParams(sql, params) {
  if (!params || typeof params !== 'object') return sql;
  let out = sql;
  for (const [name, value] of Object.entries(params)) {
    const token = `:${name}`;
    let literal;
    if (value === null || value === undefined) {
      literal = 'NULL';
    } else if (typeof value === 'number') {
      literal = String(value);
    } else if (typeof value === 'boolean') {
      literal = value ? '1' : '0';
    } else {
      // 字符串：单引号转义 '' -> ''''
      const safe = String(value).replace(/'/g, "''");
      literal = `'${safe}'`;
    }
    // 全局替换
    out = out.split(token).join(literal);
  }
  return out;
}

/**
 * 执行 CLI 调用，返回 Promise<{status, stdout, stderr, exitCode, durationMs}>。
 */
function runCli({ bin, group, db, sql, timeoutMs }) {
  const start = Date.now();
  return new Promise((resolve) => {
    const child = spawn(
      bin,
      ['sql', 'query', group, '--db', db, '--sql', sql],
      { stdio: ['ignore', 'pipe', 'pipe'] }
    );

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      try { child.kill('SIGKILL'); } catch (_) {}
    }, timeoutMs);

    child.stdout.on('data', (c) => { stdout += c.toString(); });
    child.stderr.on('data', (c) => { stderr += c.toString(); });

    child.on('error', (err) => {
      clearTimeout(timer);
      resolve({
        status: 'error',
        stdout,
        stderr: stderr + (stderr ? '\n' : '') + `spawn error: ${err.message}`,
        exitCode: -1,
        durationMs: Date.now() - start,
        spawnError: err.message,
      });
    });

    child.on('close', (code) => {
      clearTimeout(timer);
      const durationMs = Date.now() - start;
      if (timedOut) {
        resolve({
          status: 'timeout',
          stdout, stderr,
          exitCode: code,
          durationMs,
          error: `CLI 超时 ${timeoutMs}ms`,
        });
      } else if (code !== 0) {
        resolve({
          status: 'error',
          stdout, stderr,
          exitCode: code,
          durationMs,
          error: `CLI exit ${code}: ${(stderr || stdout).slice(0, 500)}`,
        });
      } else {
        resolve({
          status: 'ok',
          stdout, stderr,
          exitCode: 0,
          durationMs,
        });
      }
    });
  });
}

/**
 * 解析 CLI stdout 为 {rows, rowCount}。
 * dms-alibaba `sql query` 文档说明为纯 JSON：
 *   可能是 { data: { rows: [...] } } 或 { data: [...] } 或直接 [...].
 * 如果 stdout 不是 JSON，则按行解析为原始文本兜底。
 */
function parseOutput(stdout) {
  const trimmed = (stdout || '').trim();
  if (!trimmed) return { rows: [], rowCount: 0, rawFormat: 'empty' };

  // 先尝试 JSON 解析
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return { rows: parsed, rowCount: parsed.length, rawFormat: 'array' };
    }
    if (parsed && typeof parsed === 'object') {
      // 常见封装：{success, data} 或 {rows, count}
      const data = parsed.data ?? parsed.rows ?? parsed.result;
      if (Array.isArray(data)) {
        return { rows: data, rowCount: data.length, rawFormat: 'wrapper' };
      }
      // 单行结果包装为对象
      return { rows: [parsed], rowCount: 1, rawFormat: 'single-object' };
    }
  } catch (_) {
    // 非 JSON，尝试按行解析（sql run 的表格输出兜底）
  }

  // 兜底：把 stdout 原样返回，Python 端可看
  return {
    rows: [],
    rowCount: 0,
    rawFormat: 'non-json',
    rawStdout: trimmed.slice(0, 2000),
  };
}

/**
 * 主入口。
 */
async function main(argv) {
  const args = parseArgs(argv);

  if (args.help || args.h) {
    process.stdout.write(
      'dms-alibaba-bridge: 封装 `dms-alibaba sql query` 命令\n' +
      '用法: node dms-alibaba-bridge.js --group <g> --db <db> --sql <sql> ' +
      '[--params <json>] [--timeout <ms>] [--bin <path>]\n'
    );
    process.exit(0);
  }

  const group = args.group;
  const db = args.db;
  let sql = args.sql;
  const paramsJson = typeof args.params === 'string' ? args.params : null;
  const timeoutMs = args.timeout ? parseInt(args.timeout, 10) : DEFAULT_TIMEOUT_MS;
  const bin = args.bin || DEFAULT_BIN;

  const missing = [];
  if (!group) missing.push('--group');
  if (!db) missing.push('--db');
  if (!sql) missing.push('--sql');
  if (missing.length) {
    const out = {
      status: 'error',
      error: `缺少必填参数: ${missing.join(', ')}`,
      durationMs: 0,
    };
    process.stdout.write(JSON.stringify(out));
    process.exit(2);
  }

  // 参数替换
  if (paramsJson) {
    let params;
    try {
      params = JSON.parse(paramsJson);
    } catch (e) {
      process.stdout.write(JSON.stringify({
        status: 'error',
        error: `--params JSON 解析失败: ${e.message}`,
        durationMs: 0,
      }));
      process.exit(2);
    }
    sql = applyParams(sql, params);
  }

  if (sql.length > MAX_SQL_LEN) {
    process.stdout.write(JSON.stringify({
      status: 'error',
      error: `SQL 长度超过 ${MAX_SQL_LEN}`,
      durationMs: 0,
    }));
    process.exit(2);
  }

  const run = await runCli({ bin, group, db, sql, timeoutMs });

  let rows = [];
  let rowCount = 0;
  let rawFormat = '';
  let rawStdout = '';
  if (run.status === 'ok') {
    const parsed = parseOutput(run.stdout);
    rows = parsed.rows;
    rowCount = parsed.rowCount;
    rawFormat = parsed.rawFormat;
    rawStdout = parsed.rawStdout || '';
  }

  const out = {
    status: run.status,
    group,
    db,
    sql,
    rows,
    rowCount,
    durationMs: run.durationMs,
    exitCode: run.exitCode,
  };
  if (rawFormat) out.rawFormat = rawFormat;
  if (rawStdout) out.rawStdout = rawStdout;
  if (run.error) out.error = run.error;
  if (run.stderr) out.stderr = run.stderr.slice(0, 1000);
  if (run.spawnError) out.spawnError = run.spawnError;

  process.stdout.write(JSON.stringify(out));
  process.exit(run.status === 'ok' ? 0 : 1);
}

// 导出（供单元测试或 Python 子进程调用时直接 require）
module.exports = { parseArgs, applyParams, parseOutput, main, DEFAULT_BIN, MAX_SQL_LEN };

if (require.main === module) {
  main(process.argv.slice(2)).catch((e) => {
    process.stdout.write(JSON.stringify({
      status: 'error',
      error: `bridge 内部错误: ${e.message}`,
      durationMs: 0,
    }));
    process.exit(1);
  });
}
