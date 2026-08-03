<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/contracts/quick-audit-hsf-mock-behavior.md -->
<!-- synced-at: 2026-07-11T03:52:35.006130 -->
<!-- skill: F88测试知识库 -->

---
id: contracts/quick-audit-hsf-mock-behavior
title: 快审HSF syncAuditOperation为模拟调用
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [快审, HSF, syncAuditOperation, 模拟调用, 原创保护]
trigger_examples:
  - "快审HSF调用后状态没有变化"
  - "syncAuditOperation只记录op_record不推进状态"
  - "快审真实操作需要找谁"
source_sessions: [6/24快审扣除]
promotion_count: 1
promotion_score: 0.72
---

# 快审HSF syncAuditOperation为模拟调用

## 概述

原创保护平台的快审HSF接口 `TopRightHsfService.syncAuditOperation` 是一个模拟调用：它只记录操作日志（op_record）但不实际推进业务状态。真实的快审通过/驳回需要由特定人员操作。

## 详细内容

### 接口行为

- **接口**: `TopRightHsfService.syncAuditOperation`
- **参数**: 操作类型为 `QUICK_AUDIT_AGREE` 或 `QUICK_AUDIT_REJECT`
- **实际行为**: 仅在 `yc_right_apply_op_record` 表中记录一条操作日志
- **DB状态**: 仍停留在 `QUICK_AUDITING`，不会推进到下一状态

### 真实快审操作

真实的快审通过/驳回必须由以下人员操作：

- **联系人**: 钉钉 @卢彩xq
- **专利机构**: lzxc
- **操作渠道**: 钉钉通知/操作面板

### 结算单创建时机

`settle_order` 结算单在 `SUBMIT_APPLY`（初审提交）阶段创建，快审全程不涉及结算单操作。即快审通过/驳回都不会产生或修改结算单。

### 测试注意事项

1. 通过HSF调用快审后，务必检查DB状态是否仍为 `QUICK_AUDITING`
2. 如需完整流程测试，需联系卢彩xq进行真实快审操作
3. 快审扣减服务次数的验证需要真实操作触发，HSF模拟无法验证

## 验证方法

1. 调用 `syncAuditOperation(QUICK_AUDIT_AGREE)`
2. 查询 `yc_right_apply_op_record` 表确认记录已写入
3. 查询主表确认状态仍为 `QUICK_AUDITING`
4. 确认 `settle_order` 表无新增记录

## 关联知识

- [[test-data-safety]] — 测试数据安全规范
- [[db-schema]] — 数据库表结构
