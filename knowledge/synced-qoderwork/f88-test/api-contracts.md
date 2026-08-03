<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/api-contracts.md -->
<!-- synced-at: 2026-07-11T03:52:35.005132 -->
<!-- skill: F88测试知识库 -->

---
id: infra/api-contracts
title: F88 接口契约汇总
tags: [API, HSF, 接口契约]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 接口契约汇总

> **来源**：前端 `industry-source-code/iFashion-tools` + 后端 `stylespot/stylespot-admin`
> **底层应用**：cloth-btgplatform (appId: 251680)

## 完整 API 接口清单

### 策略平台 v2 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workflow2/strategy/page` | 策略列表（分页） |
| GET | `/api/workflow2/strategy/get` | 策略详情 |
| GET | `/api/workflow2/strategy/detail` | 策略详情（别名） |
| POST | `/api/workflow2/strategy/save` | 保存/创建策略 |
| POST | `/api/workflow2/strategy/delete` | 删除策略 |
| GET | `/api/workflow2/strategy/exportTemplate` | 导出策略模板 |
| POST | `/api/workflow2/strategy/run` | 运行策略（创建批次） |
| GET | `/api/workflow2/link/page` | 链路列表（分页） |
| GET | `/api/workflow2/link/get` | 链路详情 |
| POST | `/api/workflow2/link/save` | 保存链路 |
| POST | `/api/workflow2/link/delete` | 删除链路 |
| POST | `/api/workflow2/link/run` | 运行链路（创建批次） |
| POST | `/api/workflow2/link/copy` | 复制链路 |
| GET | `/api/workflow2/link/exportTemplate` | 导出链路模板 |
| GET | `/api/workflow2/common/getStageEnums` | 环节类型枚举 |
| GET | `/api/workflow2/common/getLifeCycleEnums` | 生命周期枚举 |
| GET | `/api/workflow2/common/getNodeTypeEnums` | 节点类型枚举 |
| GET | `/api/workflow2/common/getLlmModels` | LLM 模型列表 |
| GET | `/api/workflow2/common/getApproveTypeEnums` | 审核类型枚举 |
| GET | `/api/workflow2/common/getDesignAgentPromptVersions` | 改款 prompt 版本 |
| GET | `/api/workflow2/common/getCommonConfigMetas` | 通用配置元数据 |
| GET | `/api/workflow2/common/getSellerConfigMetas` | 商家配置元数据 |
| GET | `/api/workflow2/common/getItemArchiveConfigMetas` | 商品档案配置元数据 |
| GET | `/api/workflow2/common/getSp2ItemArchiveStageMetas` | SP→商品档案阶段元数据 |
| POST | `/api/workflow2/node/tryRun` | 节点试运行 |
| GET | `/api/workflow2/push/pageBand` | 推送波段列表 |
| GET | `/api/workflow2/push/checkInputFile` | 校验推送输入文件 |

### 批次管理接口（V1 兼容）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workflow/batch/page` | 批次列表（分页，支持 status/batchType/relationId 过滤） |
| POST | `/api/workflow/batch/submit` | 提交新批次 |
| GET | `/api/workflow/batch/checkInputFile` | 校验输入文件 |
| GET | `/api/workflow/batch/getAllBatchTypes` | 全部批次类型枚举 |
| POST/GET | `/api/workflow/batch/export` | 导出批次结果 Excel |
| GET | `/api/workflow/batch/getLastBatch` | 获取最新批次 |
| GET | `/api/workflow/batch/getRunDetail` | 批次运行详情 |
| POST | `/api/workflow/batch/start` | 启动批次 |
| POST | `/api/workflow/batch/terminate` | 终止批次 |
| POST | `/api/workflow/batch/retry` | 重试失败任务 |
| GET | `/api/workflow/batch/getNodeProcess` | 节点级进度 |
| POST | `/api/workflow/batch/triggerApprove` | 触发切片审核 |
| GET | `/api/workflow/batch/getStageReproductionInfo` | 获取重产信息 |
| POST | `/api/workflow/batch/reproduction` | 提交重产 |

### 素材处理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/material/submitRepairTask` | 提交修手任务 |
| POST | `/api/material/updateRepairImage` | 保存修手结果 |
| POST | `/api/material/cancelRepairTask` | 取消修手 |
| POST | `/api/material/submitFaceSwapTask` | 提交换脸任务 |
| POST | `/api/material/updateFaceSwapImage` | 保存换脸结果 |
| POST | `/api/material/cancelFaceSwapTask` | 取消换脸 |
| POST | `/api/material/submitLocalAdjustTask` | 提交局部调整 |
| POST | `/api/material/updateLocalAdjustImage` | 保存局部调整 |
| POST | `/api/material/cancelLocalAdjustTask` | 取消局部调整 |
| POST | `/api/material/highQuality` | 图片高清化 |
| POST | `/api/material/updateHighQuality` | 保存高清化 |
| POST | `/api/material/cancelHighQuality` | 取消高清化 |
| POST | `/api/material/crop` | 图片裁剪 |
| POST | `/api/material/expend` | AI 扩图 |
| POST | `/api/material/updateExpendImage` | 保存扩图 |
| POST | `/api/material/cancelExpend` | 取消扩图 |
| POST | `/api/material/mirror` | 图片镜像 |
| POST | `/api/material/submitCollocationSwapTask` | 换搭配任务 |
| POST | `/api/material/updateCollocationSwapImage` | 保存换搭配 |
| POST | `/api/material/cancelCollocationSwapTask` | 取消换搭配 |

### 租户隔离接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tenant/queryEmployeeIdentityList` | 查询可用租户身份 |
| POST | `/api/tenant/cacheEmployeeIdentity` | 缓存租户身份选择 |
| POST | `/api/tenant/queryTenantMenu` | 查询租户菜单树 |

### 文件上传

- `POST /api/file/upload` — multipart 上传，返回 OSS URL

## MCP 工具

后端提供 `WorkflowBatchMcpTool`（10 个 MCP 工具），位于 `interfaces/mcp/WorkflowBatchMcpTool.java`。

## 接口契约相关代码路径

| 关注点 | 路径 |
|--------|------|
| MCP 工具定义 | `interfaces/mcp/WorkflowBatchMcpTool.java` |
