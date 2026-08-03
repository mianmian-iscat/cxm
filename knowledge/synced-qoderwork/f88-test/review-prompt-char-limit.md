<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/.legacy/review-prompt-char-limit.md -->
<!-- synced-at: 2026-07-11T03:52:35.006360 -->
<!-- skill: F88测试知识库 -->

---
id: features/review-prompt-char-limit
title: 审核Prompt字符限制为2000字符
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [审核平台, Prompt, 字符限制, 前端偏差]
trigger_examples:
  - "审核Prompt字符限制是多少"
  - "前端UI显示3000但PRD定义2000"
  - "TC 3.1/3.13/3.14/7.3字符限制用例"
source_sessions: [6/10审核, 6/11审核, 6/17用例调整]
promotion_count: 1
promotion_score: 0.64
---

# 审核Prompt字符限制为2000字符

## 概述

审核平台的Prompt字符限制PRD定义为2000字符，但前端UI曾显示为3000字符，属于前端显示偏差。相关测试用例已统一修改为2000字符标准。

## 详细内容

- **PRD定义**: 2000字符上限
- **前端偏差**: UI曾显示3000字符，为前端实现与PRD不一致
- **已修复用例**: TC 3.1、TC 3.13、TC 3.14、TC 7.3 均已改回2000字符标准
- **当前状态**: 需确认前端是否已修复显示问题

## 验证方法

1. 在审核平台输入Prompt，观察前端显示的字符限制提示
2. 尝试输入超过2000字符的Prompt，验证是否被拦截
3. 确认前端显示的限制值与PRD一致

## 关联知识

- [[09-审核平台-业务规则]] — 审核平台完整业务规则
- [[review-platform-code-risks]] — 审核平台代码风险点
