<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/.legacy/review-image-download-original-bug.md -->
<!-- synced-at: 2026-07-11T03:52:35.006477 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/review-image-download-original-bug
title: 审核图"下载为原图"bug
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [审核平台, bug, 图片下载, 原图]
trigger_examples:
  - "审核图下载后得到的是原图而非处理后的图"
  - "复制URL和下载功能是否共用同一逻辑"
source_sessions: [6/10审核, 6/17复制URL关联分析]
promotion_count: 1
promotion_score: 0.75
---

# 审核图"下载为原图"bug

## 概述

审核平台的图片下载功能存在一个已确认的 bug（BUG-83101072）：点击"下载"按钮得到的是原始上传图而非经过处理（如裁剪、标注、高清化）后的图。复制URL功能与下载可能共用同一URL获取逻辑，导致两者都指向原图地址。

## 详细内容

- **Bug编号**: Aone BUG-83101072
- **现象**: 审核员在审核标注平台对图片进行处理（裁剪、高清化等）后，点击下载得到的是未经处理的原图
- **根因推测**: 下载功能获取的是图片的原始存储URL，而非处理后生成的新URL。复制URL功能存在相同问题
- **影响范围**: 审核员无法直接下载处理后的审核图，需要额外操作

## 验证方法

1. 在审核标注平台打开一张已处理的审核图
2. 点击工具栏"下载"按钮
3. 检查下载的文件是否为处理后的版本（对比原图和处理后图的差异）
4. 确认bug是否已修复

## 关联知识

- [[review-toolbar-copyurl-behavior]] — copyURL的BLOCKED行为已确认为预期
- [[review-platform-code-risks]] — 审核平台7个代码风险点中包含相关逻辑
