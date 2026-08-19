---
name: strategy-platform
version: 2.3.3
description: 监控和管理 i-FASHION 策略平台的生产批次，执行进度查询、失败排查、节点重试、LLM 资源监控等运维操作。只要用户提到批次（BT_xxxx）、环节（设计改款/视觉生图/视觉审核/算法过滤/套图生产/选款推送）、跑批、链路、个性化生产、生图任务、Gemini 进度、任务卡住、失败重试、审核推送，或询问"跑到哪了""为什么慢""失败原因""套图怎么样了"等，都应立即使用此 skill，不要等用户明确说"查批次"才触发。
---

# 策略平台 - 生产批次运维

通过 `taobao-cloth-afd-mcp` MCP 工具操作 i-FASHION 策略生产平台。涵盖批次进度查询、失败排查、重试操作、LLM 任务监控。

## 版本检查

每个会话首次使用时，按 [docs/version-check.md](docs/version-check.md) 静默检查更新。

## 前置条件

本 skill 依赖 `taobao-cloth-afd-mcp` MCP 服务。使用前请确认已安装：

1. 在 QoderWork 中检查是否已加载 `taobao-cloth-afd-mcp` 相关工具（如 `workflow_batch_query` 等）
2. 如未安装，请前往 [taobao-cloth-afd-mcp 安装页面](https://open.aone.alibaba-inc.com/console/platform/taobao-cloth-afd/mcp/server/taobao-cloth-afd-mcp) 完成 MCP 服务的添加和授权
3. 安装完成后重启 QoderWork 使配置生效

## 执行节奏

**每调用一个工具后立即输出，不要等所有工具都完成再统一汇报。** 节奏如下：

1. 调用工具 → 立即告知用户看到了什么
2. 说明接下来要做什么 → 再调用下一个工具
3. 可以并行的工具一起发出，但结果回来后逐步呈现

这样用户能跟上调查进度，而不是等待黑盒后突然收到一大段输出。

## 核心概念

生产流程采用三级层次结构：

```
批次（Batch, BT_xxxx）
  └─ 环节（Stage，如 设计改款 / 视觉生图 / 算法过滤）
       └─ 节点（Node，环节内并行执行的任务单元）
```

每个批次按顺序流转多个环节，每个环节内多个节点并行执行。节点状态：init / toSubmit / running / success / fail。

## 工具速查表

| 工具 | 用途 | 关键入参 |
|------|------|---------|
| `workflow_batch_query` | 查询批次信息 + 环节进度 | `batchId` 或 `batchName`（模糊匹配） |
| `get_stage_node_id` | 按环节名获取 stageNodeId | `batchId` + `stageName`（精确匹配） |
| `node_progress_query` | 查询节点级进度 | `getReq.batchId`（+ 可选 `stageNodeId`） |
| `query_fail_reason` | 获取失败原因统计 | `getReq.batchId` + `nodeId`/`stageNodeId` |
| `workflow_fail_retry` | 重试失败任务 | `batchId` + `nodeId` |
| `workflow_trigger_approve` | 触发切片审核 | `batchId` + `nodeIds[]` |
| `workflow_try_push_approve_task` | 推送审核任务 | `batchId` |
| `query_gemini_task_progress` | Gemini 任务累计统计（按模型/状态） | 可选：时间范围、场景、状态过滤 |
| `query_llm_running_progress` | LLM 资源实时快照（谁在跑什么） | 无 |
| `workflow_get_map_gen_info` | MAP 图片生成信息 | `batchId` |

工具入参/出参的完整字段定义见 [tool-reference.md](tool-reference.md)。**在以下情况读取它**：不确定某个字段名、需要知道完整的返回结构、或遇到工具调用报错时。日常工作流中不需要每次都读。

## 领域术语对照

| 用户说法 | 对应系统概念 |
|---------|------------|
| 设计、改款 | 设计改款环节 |
| 生首图、生图 | 视觉生图环节 |
| 去劣 | 审核中的第一轮：过滤低质量图（策略名通常含"去劣"） |
| 择优 | 审核中的第二轮：从通过图中选优（策略名通常含"择优"） |
| 种子款 | 企划环节产出的图，通常对应"种子款直推"类批次 |

审核流程通常先跑去劣、再跑择优，是两个独立策略节点，用户说"去劣完了吗"时，查 strategyName 含"去劣"的节点进度。

## 意图识别与批次定位

用户通常用自然语言而非 ID 描述批次，按以下策略解析：

**用户提供批次 ID**（如"BT_2072"）：直接调用 `workflow_batch_query({batchId: "BT_2072"})`。

**用户用名称描述批次**（如"个性化30批跑到哪了"）：

1. **直接尝试**：用原始短语作为 `batchName`
2. **关键词重排**：无结果时调整词序（如"30批个性化"）
3. **提取关键词**：取最具辨识度的词重试
4. **避免泛词**：不要单独用"测试"、"任务"等宽泛词，优先用人名（"yiyi"）或具体数字（"30批"）
5. **多结果处理**：按 `createTime` 降序排列，**默认直接汇报最新批次**，无需询问确认。只有用户说"不是这个"或"不对"时，才依次往前找

**用户提到审核相关操作**（如"能审核了吗""审核一下""切一下审核"）：

生图环节不可审核，用户说的审核一定指 stageName 含「审核」的环节。直接找 PROCESSING 状态中的审核类环节（改款审核、视觉审核等），不要去检查生图环节的 supportTriggerApprove。

**用户提到时间范围**（如"这周"、"今天"、"最近"）：

查询结果后用 `createTime` 过滤，无需询问用户确认，自动推断。

## 常用工作流

> 详细步骤见 [docs/workflows.md](docs/workflows.md)，执行时按需读取。

| # | 工作流 | 触发场景 | 核心工具 |
|---|--------|---------|---------|
| 1 | 批次进度查询 | "XX批次跑到哪了？" | `workflow_batch_query` |
| 2 | 活跃环节深度调查 | 工作流1后主动下钻 | `query_llm_running_progress` + `node_progress_query` + `query_fail_reason` |
| 3 | 重试失败任务 | failCount > 0 的节点 | `workflow_fail_retry` |
| 4 | 审核环节操作 | supportTriggerApprove=true | `workflow_trigger_approve` + `workflow_try_push_approve_task` |
| 5 | 平台健康巡检 | 定时巡逻/整体健康 | `query_gemini_task_progress` + `query_llm_running_progress` |
| 6 | approve 节点深度排查 | approve FAIL/HANDLING/replaceImage | DMS SQL 跨表分析 |
| 7 | SharedArrayBuffer 环境检查 | 视频编辑器/ffmpeg-wasm 报错 | curl 检查 COOP/COEP 响应头 |

**关键规则**：
- 工作流 1 不要止步于环节级汇总，对所有 PROCESSING 环节都应主动执行工作流 2 深度调查
- 多个环节可以同时 PROCESSING，不要只取第一个
- `stageNodeId` 直接从 stageProgress 的 `stageUid` 字段取得，无需额外调用 `get_stage_node_id`

## 已知问题与风险感知

> 详细问题模式与处置见 [docs/known-issues.md](docs/known-issues.md)，遇到相关症状时按需读取。

速查：BT_6148（replaceImage 快照不一致）、BT_5976（subJobId 缺失）、BT_6149（COOP/COEP）、BATCH 卡死（SchedulerX）、BT_7495（审核分配算法）、BT_7485（审核回调三条件）、单模型集中失败。

**replaceImage 风险**：用户提到"替换图片"时主动提醒 BATCH 模式快照不一致风险，建议 STREAM 模式。

## 与其他 F88 技能的协作

| 技能 | 互补关系 |
|------|---------|
| f88-failure-analysis | 本技能在 MCP/API 层做实时运维；failure-analysis 在 SQL/数据库层做离线归因。approve 失败深度排查可转交 failure-analysis 的工作流 9/10；批次效率问题（"为什么慢"/鬼打墙式重试）可转交 WF12 批次轨迹效率分析，失败批次沉淀回归用例可转交 WF13 Bad Case 回流 |
| f88-approve-verify-sql | approve 节点验证的 SQL 手册，工作流 6 的 SQL 模板详见该技能 |
| f88-link-config-check | 链路配置正确性检查，在工作流 6 发现 execMode 配置异常后可联动检查 |
| stylespot-prod-troubleshoot | 生产环境问题排查的总入口，本技能的工作流 6/7 覆盖的场景与其调查路径 3/5 重叠 |

## 注意事项

- `workflow_batch_query` 返回**数组**，单批次查询时始终取 `[0]`
- 批次 `status` 枚举：`PROCESSING` / `FINISHED` / `TERMINATED`（已终止 = 中途人工停止，未经用户确认不应重试）
- `query_fail_reason` 必须提供 `batchId` + 以下至少一项：`nodeId`、`stageNodeId`、`strategyNodeId`，否则报错
- `stage_progress_query` 已废弃，不要使用
- 工作流 6/7 走 DMS SQL 时：数据库连接见 F88测试知识库/references/shared/db-connections.md（stylespot 生产库 dbId=5335708）；查询安全规则（env 过滤铁律/写操作红线/ScheduleX 只读）见 F88测试知识库/references/shared/query-safety-rules.md
- SQL 查 `workflow_record_log` 必须带 `id > 4000000` 否则超时（近期批次建议 `id > 6400000` 进一步缩小扫描范围，与 f88-approve-verify-sql / f88-ffmpeg 口径一致）；status 失败值是 `FAIL` 不是 `FAILED`；错误字段是 `$.errorMsg` 不是 `$.errorMessage`
