<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/review-platform-architecture.md -->
<!-- synced-at: 2026-07-22T15:00:02.873229 -->
<!-- skill: F88测试知识库 -->

---
id: infra/review-platform-architecture
title: F88 审核平台技术架构
tags: [审核平台, 技术架构, DB设计, 权限]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 审核平台技术架构

> 来源：[钉钉文档](https://alidocs.dingtalk.com/i/nodes/lyQod3RxJKe9QjOMioxvZRQRWkb4Mw9r)
> PRD：[审核/标注管理中心需求文档](https://alidocs.dingtalk.com/i/nodes/dpYLaezmVNRMGX56CklKEPwXVrMqPxX6)
> 接口文档：[接口文档](https://alidocs.dingtalk.com/i/nodes/AR4GpnMqJzKpOoklFDAlOG6P8Ke0xjE3)

## 数据库设计

### 审核定义表 `g_review_standard`
存放审核标准和审核节点类型。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint(20) | 主键 |
| name | varchar(64) | 名称，唯一 |
| emp_id / emp_name | varchar(64) | 创建小二 |
| type | tinyint(3) | **1=审核标准, 2=审核节点** |
| extra | json | 扩展字段（见下方说明） |
| env | varchar(32) | 环境标识 prod/staging |

**extra 字段说明：**
- 审核标准：存放审核标准更改历史
- 审核节点类型：存放节点类型下的各种配置

### 审核任务表 `g_afd_review_job`
不支持定制筛选项，因此独立建表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint(20) | 主键 |
| name | varchar(64) | 任务名称（主任务） |
| emp_id / emp_name | varchar(64) | 审核小二（普通任务实际审核人/质检任务分配审核人） |
| inspection_emp_id / inspection_emp_name | varchar(64) | 抽检小二 |
| assigned_emp_ids / assigned_emp_names | text | 分配小二列表，逗号分隔 |
| job_type | tinyint(3) | **0=主任务, 1=正常审核子任务, 2=埋雷子任务, 3=抽检子任务** |
| job_status | int | **0=待开始, 1=审核中, 2=待抽检, 3=抽检中, 4=已完成, 5=已取消** |
| parent_job_id | bigint | 父级job id，主任务为0 |
| seller_id / seller_name | - | 商家信息 |
| info | text | JSON格式，任务核心业务数据 |
| extra | text | JSON格式，扩展字段 |
| relation_id | varchar(64) | 关联生产平台任务ID或其他业务ID |
| relation_type | int | 1=生产平台任务，2=手动创建任务 |

**索引：** idx_parent_job_id, idx_relation_id, idx_job_type, idx_job_status, idx_parent_type_status

### 任务类型与页面映射
| 页面 | 查询 job_type |
|------|--------------|
| 主任务列表 | 0 |
| 正常审核页面 | 1, 3 |
| 埋雷页面 | 2 |
| 抽检页面 | 3 |

## 三层 job_type 架构

| job_type | 含义 | 说明 |
|----------|------|------|
| 0 | 主任务 | 管理和配置层，承载上传文件、预期交付时间、职能角色、参与人员分配 |
| 1 | 正常审核子任务 | 实际审核执行层，套图审核（单图审核已下线） |
| 2 | 埋雷子任务 | 质量校验层，从每人子任务中抽取5%（上限50个）复审 |
| 3 | 抽检子任务 | 质量抽检层，抽检结果覆盖原任务结果 |

主任务与子任务为 1:N 关系，通过 `parent_job_id` 关联。三类子任务（job_type=1/2/3）共用 `info` 字段结构，可共用接口查询。

## 角色权限设计

### 五种角色
标注、标注组长、商运、产运、产品

### 权限配置方式
通过 **Diamond 动态配置**控制可见性和功能点：
- 可见性：所有页面都需要配置
- 功能点：不配置默认所有人有权限

### 页面可见性矩阵
| 页面 | 标注 | 标注组长 | 商运 | 产运 | 产品 |
|------|------|----------|------|------|------|
| 审核标准管理页 | ❌ | ✅ | ✅ | ✅ | ✅ |
| 审核节点管理页 | ❌ | ❌ | ❌ | ✅ | ✅ |
| 任务管理页 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 审核详情页 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 抽检详情页 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 资源管理 | ❌ | ❌ | ❌ | ✅ | ✅ |

### 功能点控制
| 页面 | 功能点 | 标注 | 标注组长 | 商运 | 产运 | 产品 |
|------|--------|------|----------|------|------|------|
| 任务管理页 | 新建任务 | ❌置灰 | ✅ | ✅ | ✅ | ✅ |
| 任务管理页 | 删除任务 | ❌置灰 | ❌置灰 | ❌置灰 | ✅ | ✅ |
| 审核详情页 | 全部审核完成按钮 | ❌置灰 | ✅ | ✅ | ✅ | ✅ |
| 抽检任务列表弹窗 | 抽检任务查看详情 | ❌置灰 | ✅ | ✅ | ✅ | ✅ |

### Diamond 配置地址
- [MSE预发配置](https://mse.alibaba-inc.com/pre/diamond/configlist/configdetail?dataId=menu-config&group=stylespot-admin&namespaceId=stylespot-admin&tab=content)

### 能力标签
- 只有标注和组长有能力标签
- 用英文逗号分割
- 示例：`种子图去劣,设计改款去劣`

## QA 实测要点

### review_job 状态机（QA 简化视角）
官方定义有 6 个状态（见上方），但 QA 验证时关注简化语义：
- **0=PENDING** / **1=审核通过(确认)** / **2=丢弃/完成** / **5=DONE(全部完成)**
- 重新审核会将状态重置为 0 并清除 auditTime

### 模板库"提交审核"前端 bug
- 弹窗所有套图节点报"节点选择错误"，前端筛选旧 questionType=2 导致后端 v3.0（只认 questionType=5）拒绝
- **Workaround**：直接调 `POST /api/afd/review/task/main/create` 创建审核任务，绕过前端向导

### 首图审核 checkbox 行为
- checkbox 初始 disabled，须先进入审核 detail 页再勾选才 enabled
- 丢弃后重新审核时恢复可勾选
