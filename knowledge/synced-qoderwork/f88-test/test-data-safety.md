<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/contracts/test-data-safety.md -->
<!-- synced-at: 2026-07-11T03:52:35.006241 -->
<!-- skill: F88测试知识库 -->

---
id: contracts/test-data-safety
title: F88 测试数据安全红线
tags: [安全红线, 数据隔离, 测试规范]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 测试数据安全红线

## 素材生产数据安全红线 ⚠️

**操作原则：供给品标题必须含「测试请不要拍」才可执行写操作（推送/创建任务/AI预审复核/发起素材生产）。**

| 条件 | 权限 | 操作范围 |
|------|------|---------|
| 供给品标题含「测试请不要拍」 | 可操作 | 推送F88、创建生产任务、AI预审复核、发起素材生成 |
| 供给品标题不含「测试请不要拍」 | 🔒 只读 | 仅查询/查看，禁止任何写操作 |

- 测试商家账号：2219662018344（F88测试店铺）、2219635649153（F88测试卖家0213）
- 此规则覆盖素材生产全流程：从无到有 + 主动提报
- 违反此规则可能影响生产数据，后果严重

## 测试脚本安全规范

- BASE_URL 默认指向沙箱地址
- 通过环境变量 `TEST_BASE_URL` 支持覆盖
- 预发环境可执行写操作
- 生产环境仅只读查看
