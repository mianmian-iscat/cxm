<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/review-platform-code-risks.md -->
<!-- synced-at: 2026-07-11T03:52:35.005263 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/review-platform-code-risks
title: F88审核平台代码7个风险点
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [审核平台, 代码风险, X-AFD-Emp-Identity, 图片处理]
trigger_examples:
  - "审核平台有哪些已知代码风险"
  - "X-AFD-Emp-Identity header是什么"
  - "审核图URL无后缀时extractFormat会怎样"
source_sessions: [6/16审核创建skill, 6/17代码风险分析]
promotion_count: 1
promotion_score: 0.75
---

# F88审核平台代码7个风险点

## 概述

F88审核平台代码中存在7个已识别的风险点，涵盖视频/图片未处理、权限控制、URL解析边界等场景。这些风险点在需求82959767代码分析中发现，需要在测试设计中重点覆盖。

## 详细内容

### 1. 视频未处理风险
视频素材可能未经过处理直接进入审核流程，导致审核员看到的是原始视频。

### 2. 参考图未处理风险
参考图可能未经过处理（如裁剪、格式转换）就被引用，影响审核判断。

### 3. 仅抽检流程风险
某些场景下只走抽检流程而非全检，可能导致问题素材漏审。

### 4. taskId粒度问题
使用 `inspectionTaskId` 作为任务标识，粒度可能不够细，存在并发冲突风险。

### 5. URL无后缀时extractFormat返回null
`ImageUtils.extractFormat()` 从URL路径中提取文件格式，当URL无后缀（如 `https://cdn.example.com/image`）时返回null，可能导致下游处理异常。

### 6. 7天过期机制
审核数据存在7天过期机制，过期后无法访问，需要在测试中考虑过期场景。

### 7. convertOssUrl内网endpoint替换
`convertOssUrl()` 方法将OSS URL转换为内网endpoint，在跨环境（预发/线上）测试时可能导致URL不可访问。

### X-AFD-Emp-Identity Header

审核任务创建API需要 `X-AFD-Emp-Identity` 请求头来标识操作人身份。缺失该header会导致API调用失败。

## 验证方法

1. 构造URL无后缀的审核图，验证 `extractFormat()` 返回值
2. 测试7天过期后的审核图访问行为
3. 在预发环境验证 `convertOssUrl()` 的内网endpoint替换逻辑

## 关联知识

- [[review-image-download-original-bug]] — 下载原图bug与图片处理逻辑相关
- [[review-toolbar-copyurl-behavior]] — 工具栏按钮行为
- [[code-level-issues]] — 其他代码级问题汇总
