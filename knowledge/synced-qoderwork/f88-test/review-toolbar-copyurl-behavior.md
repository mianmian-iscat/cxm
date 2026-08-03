<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/.legacy/review-toolbar-copyurl-behavior.md -->
<!-- synced-at: 2026-07-11T03:52:35.006597 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/review-toolbar-copyurl-behavior
title: 审核图copyURL BLOCKED为预期行为
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [审核平台, copyURL, BLOCKED, 预期行为]
trigger_examples:
  - "审核图复制URL按钮显示BLOCKED"
  - "工具栏按钮状态异常是否为bug"
source_sessions: [6/10审核, 6/11审核, 6/17关联, 6/19复测]
promotion_count: 1
promotion_score: 0.64
---

# 审核图copyURL BLOCKED为预期行为

## 概述

审核标注平台图片工具栏的"复制URL"功能在特定场景下显示BLOCKED状态，经6/19复测确认这是预期行为而非bug。工具栏按钮应以截图5所示的按钮集合为准。

## 详细内容

- **现象**: 复制URL按钮在某些状态下被BLOCKED
- **结论**: 经产品确认（6/19复测），BLOCKED状态是设计预期，非代码缺陷
- **正确按钮集合**: 替换 / 局部修改 / 复制URL / 裁剪 / 高清化 / red / 驳回（共7个）
- **已关闭相关bug**: 与copyURL BLOCKED相关的3个问题均已确认为预期行为

## 验证方法

1. 在审核标注平台打开不同状态的审核图
2. 观察工具栏按钮的可用性状态
3. 确认BLOCKED状态是否与业务规则一致（如未处理完成的图不允许复制URL）

## 关联知识

- [[review-image-download-original-bug]] — 下载功能下载原图是真实bug
- [[review-platform-code-risks]] — 审核平台代码风险点
