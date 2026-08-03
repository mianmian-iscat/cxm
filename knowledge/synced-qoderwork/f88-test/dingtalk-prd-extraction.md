<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/dingtalk-prd-extraction.md -->
<!-- synced-at: 2026-07-11T03:52:35.005498 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/dingtalk-prd-extraction
title: 钉钉文档PRD读取方案（绕过虚拟滚动）
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [钉钉文档, PRD, 虚拟滚动, weaving-pro, iframe]
trigger_examples:
  - "weaving-pro平台PRD无法完整读取"
  - "钉钉文档DOM只渲染可视区域内容"
  - "需要提取PRD全文但只能看到部分内容"
source_sessions: [6/22视频审核PRD, 6/24种草素材, 6/24种草视频, 6/29视频审核剪辑]
promotion_count: 1
promotion_score: 0.85
---

# 钉钉文档PRD读取方案（绕过虚拟滚动）

## 概述

weaving-pro（钉钉文档平台）的DOM使用虚拟滚动技术，只渲染可视区域的内容，导致无法通过常规DOM读取获取PRD全文。有两种经过验证的替代方案可以提取完整内容。这个方案在4个不同会话中反复使用，是PRD分析的基础能力。

## 详细内容

### 方案一：fetch API 直接获取（推荐）

通过 weaving-func API 直接获取PRD原始数据，绕过DOM渲染：

```
GET https://weaving-func.fn.alibaba-inc.com/api/aiPrdProject/detail?projectId={id}
```

响应结构：
```json
{
  "data": {
    "prdInfo": {
      "markdownInfo": "...PRD全文Markdown格式..."
    }
  }
}
```

**优点**: 直接获取原始Markdown，无需处理DOM；内容完整
**适用**: projectId已知的场景

### 方案二：浏览器JS提取iframe内容

通过浏览器自动化在钉钉文档页面执行JS：

```javascript
// 获取iframe内容
const iframe = document.querySelector('iframe');
const text = iframe.contentDocument.body.innerText;
```

**优点**: 不需要知道projectId，直接在当前页面提取
**适用**: 已打开文档页面的场景

### React fiber结构解析

对于需要结构化提取的场景，文档内容在React fiber树中：
- `node._nodes[].leaves[].text`（klass=text的leaf节点）
- `heading-4` 对应章节标题

## 验证方法

1. 用方案一fetch一个已知projectId，检查返回的markdownInfo是否完整
2. 用方案二在打开的钉钉文档页面执行JS，对比提取内容与页面可见内容

## 关联知识

- [[dingtalk-iframe-content-extraction]] — iframe内容提取的通用方法
