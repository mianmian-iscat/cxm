<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/video-push-code-defects.md -->
<!-- synced-at: 2026-07-11T03:52:35.005881 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/video-push-code-defects
title: 视频推送节点代码缺陷
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [视频推送, isVideoUrl, OSS, 代码缺陷]
trigger_examples:
  - "视频推送节点isVideoUrl判断不准确"
  - "OSS签名URL被误判为非视频"
  - "VideoPushTaskBuilder多视频只取第一个"
source_sessions: [6/17视频推送节点测试, 6/19复测]
promotion_count: 1
promotion_score: 0.75
---

# 视频推送节点代码缺陷

## 概述

视频推送节点（VideoPushTaskBuilder）存在多个代码级缺陷，影响视频URL识别准确性和多视频场景支持。这些缺陷在需求 82729666 测试中被发现，需要在后续版本中修复。

## 详细内容

### 缺陷1: isVideoUrl() 使用 endsWith(".mp4") 判断

`isVideoUrl()` 方法用 `endsWith(".mp4")` 判断URL是否为视频，但OSS签名URL会带query参数（如 `?Expires=xxx&Signature=xxx`），导致URL不以 `.mp4` 结尾而误判为非视频。

**修复建议**: 应改为解析URL路径部分后再判断后缀，或使用 `url.contains(".mp4")` 结合 `indexOf('?')` 截取。

### 缺陷2: VideoPushTaskBuilder 只取第一个视频

`VideoPushTaskBuilder` 只取 `videoUrls.get(0)` 而丢弃多视频场景中的其余视频URL。

**影响**: 当一个素材包含多个视频时，只有第一个会被推送。

### 缺陷3: tryRun() 抛 BizException 不支持试运行

`tryRun()` 方法直接抛出 `BizException`，不支持试运行（dry-run）模式，导致无法在预发环境安全验证推送逻辑。

## 验证方法

1. 构造一个带OSS签名参数的视频URL，验证 `isVideoUrl()` 返回值
2. 构造包含多个视频URL的推送任务，检查实际推送了几个
3. 调用 `tryRun()` 观察是否抛异常而非返回试运行结果

## 关联知识

- [[code-level-issues]] — 其他已知代码级问题
- [[features/08-视频生产]] — 视频生产模块完整知识
