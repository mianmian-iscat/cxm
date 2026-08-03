<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/environment-matrix.md -->
<!-- synced-at: 2026-07-11T03:52:35.004200 -->
<!-- skill: F88测试知识库 -->

---
id: infra/environment-matrix
title: F88 测试环境与规范矩阵
tags: [测试环境, 沙箱, 预发, 线上, 规范]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 测试环境与规范矩阵

## 环境管理

| 环境 | 地址 | 权限 | 用途 |
|------|------|------|------|
| 沙箱 | sandbox-aifashion-xiaoer.alibaba-inc.com | 可读写 | 开发调试 |
| 预发 | pre-aifashion-xiaoer.alibaba-inc.com | 可写 | 集成测试 |
| 生产 | aifashion-xiaoer.alibaba-inc.com | 只读 | 线上验证 |

## 用例格式规范

- XMind：使用 tab 缩进文本格式，可直接粘贴导入 XMind
- pytest：遵循标准 pytest 格式，类组织用例
- 用例ID格式：`TC_{模块缩写}_{序号}`

## 缺陷创建规范

- F88 项目使用 type 515（大淘宝缺陷模版）
- 关联需求使用 cfs 141538
- 发现阶段字段 ID 为 47
- `--relation parent` 在 F88 项目不可用

## 报告规范

- 标题格式：`{需求名称}项目质量报告_{YYYYMMDD}`
- 开发人员：参与者 - 测试 - 产品（去重仅名字）
- 用例评审人 = 测试人员
- Bug空间 = 项目缺陷页URL
- KindEditor 通过 iframe.contentDocument.body.innerHTML 设置

## 测试流程规范

### 需求分析阶段
1. 读取PRD和技术方案
2. 提取功能点并确认
3. 识别测试风险和难点

### 用例设计阶段
1. 先产出 XMind tab 缩进文本
2. 结构化评审（用户确认）
3. 待确认项先跳过继续生成
4. 验证阶段再补充完善

### 测试执行阶段
1. 按优先级执行（P0 → P1 → P2 → P3）
2. 发现缺陷及时记录
3. 阻塞性问题标记并上报

### 测试报告阶段
1. 统计测试执行结果
2. 提取人员信息
3. 填写质量报告
4. 回填需求页

## 质量标准

### 用例覆盖要求
- P0 功能点：100% 覆盖
- P1 功能点：≥ 90% 覆盖
- P2 功能点：≥ 80% 覆盖

### 缺陷管理要求
- P0 缺陷：发现后 4 小时内响应
- P1 缺陷：发现后 24 小时内响应
- 闭环率目标：≥ 85%

### 测试通过标准
- P0 用例全部通过
- P1 用例通过率 ≥ 95%
- 无 P0/P1 级别未闭环缺陷
