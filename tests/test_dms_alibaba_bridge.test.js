/**
 * tests/test_dms_alibaba_bridge.test.js — dms-alibaba-bridge 单元测试
 * 使用 Node.js 内置 node:test 框架，零依赖。
 * 运行：node --test tests/test_dms_alibaba_bridge.test.js
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const bridge = require('../scripts/dms-alibaba-bridge.js');

test('parseArgs: 空格分隔形式', () => {
  const r = bridge.parseArgs(['--group', 'g1', '--db', 'd1', '--sql', 'SELECT 1']);
  assert.deepEqual(r, { group: 'g1', db: 'd1', sql: 'SELECT 1' });
});

test('parseArgs: 等号形式', () => {
  const r = bridge.parseArgs(['--group=g1', '--timeout=5000']);
  assert.equal(r.group, 'g1');
  assert.equal(r.timeout, '5000');
});

test('parseArgs: 布尔 flag', () => {
  const r = bridge.parseArgs(['--help']);
  assert.equal(r.help, true);
});

test('applyParams: 数字替换', () => {
  const out = bridge.applyParams('SELECT * FROM t WHERE id=:id', { id: 123 });
  assert.equal(out, 'SELECT * FROM t WHERE id=123');
});

test('applyParams: 字符串替换 + 单引号转义', () => {
  const out = bridge.applyParams('SELECT * FROM t WHERE name=:n', { n: "O'Brien" });
  assert.equal(out, "SELECT * FROM t WHERE name='O''Brien'");
});

test('applyParams: null 替换为 NULL', () => {
  const out = bridge.applyParams('SELECT * FROM t WHERE a=:a', { a: null });
  assert.equal(out, 'SELECT * FROM t WHERE a=NULL');
});

test('applyParams: boolean 替换为 1/0', () => {
  assert.equal(bridge.applyParams('WHERE a=:a', { a: true }), 'WHERE a=1');
  assert.equal(bridge.applyParams('WHERE a=:a', { a: false }), 'WHERE a=0');
});

test('applyParams: 同一占位符出现多次', () => {
  const out = bridge.applyParams('WHERE a=:x OR b=:x', { x: 5 });
  assert.equal(out, 'WHERE a=5 OR b=5');
});

test('applyParams: 空 params 原样返回', () => {
  const sql = 'SELECT 1';
  assert.equal(bridge.applyParams(sql, null), sql);
  assert.equal(bridge.applyParams(sql, undefined), sql);
  assert.equal(bridge.applyParams(sql, {}), sql);
});

test('parseOutput: JSON 数组', () => {
  const r = bridge.parseOutput('[{"a":1},{"a":2}]');
  assert.equal(r.rowCount, 2);
  assert.deepEqual(r.rows, [{ a: 1 }, { a: 2 }]);
  assert.equal(r.rawFormat, 'array');
});

test('parseOutput: wrapper 对象带 data 数组', () => {
  const r = bridge.parseOutput('{"success":true,"data":[{"a":1}]}');
  assert.equal(r.rowCount, 1);
  assert.deepEqual(r.rows, [{ a: 1 }]);
  assert.equal(r.rawFormat, 'wrapper');
});

test('parseOutput: wrapper 对象带 rows 数组', () => {
  const r = bridge.parseOutput('{"rows":[{"a":1},{"a":2}],"count":2}');
  assert.equal(r.rowCount, 2);
  assert.equal(r.rawFormat, 'wrapper');
});

test('parseOutput: 单对象包成单行', () => {
  const r = bridge.parseOutput('{"x":1,"y":2}');
  assert.equal(r.rowCount, 1);
  assert.deepEqual(r.rows, [{ x: 1, y: 2 }]);
  assert.equal(r.rawFormat, 'single-object');
});

test('parseOutput: 非 JSON 兜底', () => {
  const r = bridge.parseOutput('not json');
  assert.equal(r.rowCount, 0);
  assert.deepEqual(r.rows, []);
  assert.equal(r.rawFormat, 'non-json');
  assert.ok(r.rawStdout.includes('not json'));
});

test('parseOutput: 空字符串', () => {
  const r = bridge.parseOutput('');
  assert.equal(r.rowCount, 0);
  assert.equal(r.rawFormat, 'empty');
});

test('parseOutput: 超长非 JSON 截断到 2000 字符', () => {
  const r = bridge.parseOutput('x'.repeat(5000));
  assert.equal(r.rawFormat, 'non-json');
  assert.ok(r.rawStdout.length <= 2000);
});

test('DEFAULT_BIN / MAX_SQL_LEN 常量暴露', () => {
  assert.ok(typeof bridge.DEFAULT_BIN === 'string');
  assert.equal(bridge.MAX_SQL_LEN, 4000);
});
