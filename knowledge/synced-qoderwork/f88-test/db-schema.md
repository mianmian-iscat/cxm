<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/db-schema.md -->
<!-- synced-at: 2026-07-11T03:52:35.004958 -->
<!-- skill: F88测试知识库 -->

---
id: infra/db-schema
title: F88 数据库表结构
tags: [数据库, 表结构, DB]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 数据库表结构

> **来源**：前端 `industry-source-code/iFashion-tools` + 后端 `stylespot/stylespot-admin`
> **底层应用**：cloth-btgplatform (appId: 251680)
> **数据库**：MySQL: stylespot@rm-lgay0v5lor8396yka

## 后端 DDD 分层

### 模块职责

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `common` | 枚举、工具、异常、常量 | `GeminiModelConfig`（Diamond 动态配置） |
| `client` | DTO、RPC 接口定义 | Request/Response 对象 |
| `domain` | 核心业务模型、域服务 | `Workflow2Engine`、`NodeProcessor`、`StrategyDomainService`、`DataSourceService` |
| `infrastructure` | DB 访问、外部服务 Facade、MQ、Tair | `GeminiApiFacadeIdeaLabImpl`、`QwenLLMFacadeImpl`、MyBatis Mapper |
| `application` | 应用服务、定时任务、消息消费者、处理器 | 18 种 `NodeProcessor` 实现、8 个 Scheduler Job |
| `interfaces` | REST 控制器、MCP 工具 | 12 个 Controller、`WorkflowBatchMcpTool`（10 个 MCP 工具） |

## 数据库表结构

### 核心表

| 表 | DO 类 | 关键字段 |
|----|-------|----------|
| `g_workflow_batch` | `WorkflowBatchDO` | batchId, batchType, workflowInfo(JSON), inputInfo, extraInfo, status, relationId, relationType, tenantId |
| `g_workflow_instance` | `WorkflowInstanceDO` | workflowInstanceId, batchId, stageType, strategyId, chainId, status, inputParam, commonVariable(JSON), workflowVariable, parentInstanceId, preInstanceId |
| `workflow_record_log` | `WorkflowRecordLogDO` | traceId, batchId, recordId, status, inputJson, outputJson, nodeId, nodeType, workflowInstanceId, strategyId, linkId, preRecordId, bizRecordId, reproductionStatus |

### 查询优化要点

#### workflow_record_log
- `workflow_record_log` 是超大表，查询**必须加 `id > 4000000`**（或更高阈值）
- `node_type` 字段**无索引**
- `seller_id` 通过 `JSON_EXTRACT(common_variable, '$.seller_id')` 提取
- `strategyName` 通过 `JSON_EXTRACT(extra_info, '$.strategyName')` 提取
- **避免使用 `JSON_VALID()`**（性能极差）
- ORDER BY **必须带 LIMIT**（ODPS 限制）
- 状态值是 `FAIL` 不是 `FAILED`（第一次查失败数据时几乎必踩）
- 错误信息字段是 `$.errorMsg` 不是 `$.errorMessage`

#### g_afd_material
- **无 seller_id/batch_id 独立列**：它们存在 info JSON 内（如 `info.batchId`、`info.linkId`），列结构为：id/gmt_create/afd_mid/type/biz_scene/name/source/url/info/extra/env/status/search_key
- **禁止裸查 JSON 路径**：`info ->> '$.batchId' = 'BT_XXXX'` 无索引 = 全表扫描 = 必然超时（DMS 20s 限制）
- **正确查询路径**：
  1. 先从 `workflow_record_log` 拿到 FAIL 记录的 `trace_id`（= workflow_instance_id）
  2. 用 `afd_mid`（有 UK 索引）或 `search_key` 关联查询
  3. 或加 `gmt_create` 时间范围 + `LIMIT 10` 缩小扫描范围
- **常用模式**：`WHERE afd_mid = 'xxx' LIMIT 10` 或 `WHERE gmt_create >= '2026-07-01' AND info ->> '$.batchId' = 'BT_xxx' LIMIT 10`

#### 生图失败排查方法论（三层下沉）
1. **第一层**：`workflow_record_log.extra_info.errorMsg` — 仅有节点级汇总（如"存在生成失败的图片，节点执行失败"），**不含具体原因**
2. **第二层**：`workflow_record_log` 子节点（通过 `parent_id` 链追溯）的 `output_json` — 含上游传递的图片失败详情（如 Azure 安全拦截 `safety_violations=[sexual]`）
3. **第三层**：`prod_record.error_message` — 有原始 API 错误信息（GPT-Image HTTP 400、MPE-001 等），是最终定位根因的数据源
- **铁律**：排查生图失败不能停在第一层，必须下沉到第二或第三层才能看到真实原因

#### DMS CLI 通用注意事项
- DMS CLI `sql query` 返回 JSON 中 bigint/decimal 字段以 **str** 形式出现（如 `'100000949'`、`'335'`）
- pytest assert 数值比较前必须 `int()`/`float()` cast，否则 TypeError 或 in-tuple 误判（TC-034/038 踩坑）

#### dms-alibaba CLI 参数约定
- `--db` 参数必须用**实例名**（如 `rm-lgay0v5lor8396yka`），最后一个位置参数才是数据库组名（如 `stylespot`）
- **例外**：scenario 组 `--db` 用 schema 名（`scenario`），`dms-alibaba sql query --db scenario --sql "..." scenario_prod`
- `g_afd_review_job` 字段是 `name` 非 `job_name`；DMS MCP executeScript 对该表超时，须用 dms-alibaba CLI + id>N 过滤
- stylespot 全实例（逻辑库 30417/物理 dev 6369910/物理 prod 5335708）及 taobao-cloth-afd-mcp 均无查询权限；F88 DB 验证走 dms-alibaba CLI

## 处理器接口：`NodeProcessor`

```java
process(NodeProcessorContext)    // 主执行
tryRun(Node, Map, EmpInfo)       // 试运行
parseOutput(WorkflowRecordLogEntity)  // 输出解析（审核节点用）
extractPrompts(WorkflowRecordLogEntity, Node)  // 提取 prompt 调试信息
```

### 完整处理器清单

| NodeType | 处理器 | 处理类型 | 核心逻辑 |
|----------|--------|----------|----------|
| `llm_text` | `LLMTextProcessor` | AI 生成 | LLM 文本生成，NanoBanana 任务，支持 JSON 字段提取。回调类型 `ALGO_NANO_BANANA` |
| `gen_img` | `GenImgProcessor` | AI 生图 | 图片生成（继承 `GenAbstractProcessor`），`TaskSceneEnum.GEN_IMG`，成功后创建素材 |
| `map_gen_img` | `GenImgMapProcessor` | AI 生图 | MAP 多图生成（多 prompt），类似 GenImg 但处理多 prompt |
| `gen_video` | `GenVideoProcessor` | AI 生视频 | 千牛视频 SDK（`QN_VIDEO_SDK`），最多 3 张输入图，非 alicdn 图自动上传，返回视频 URL + 封面 URL |
| `template_match` | `TemplateMatchProcessor` | 匹配 | 查询商家活跃模板包 → 类目/季节/风格过滤 → 优先级排序（类目 > 季节 > 风格 > CTR）→ Tair 计数（每模板每批次最多 5 次） |
| `approve` | `ApproveProcessor` | 审核 | 桥接生产与审核系统，创建 `g_afd_review_job` 任务。3 种审核类型（见下） |
| `crop_head` | `ImageCropProcessor` | 图片处理 | 人脸框检测 + 裁头 |
| `fabric_tryon` | `FabricTryOnProcessor` | AI 生成 | 面料上身 |
| `caption` | `CaptionProcessor` | 文本生成 | Caption 文案生成 |
| `design_agent_prompt` | `DesignAgentPromptProcessor` | 自研推理 | 改款 prompt 推理（自研模型） |
| `match_score` | `MatchingScoreProcessor` | 评分 | 匹配度打分 |
| `season_tag` | `SeasonTag2Processor` | 标签 | 季节标打标 |
| `industry_tag` | `IndustryTagProcessor` | 标签 | 产业标打标 |
| `suggest_price` | `SuggestPriceProcessor` | 定价 | 建议定价 |
| `sub_category` | `SubCategoryProcessor` | 分类 | 副类目分类 |
| `style_allocation` | `StyleAllocationProcessor` | 分配 | 款式分配 |
| `push_select` | `StylePushSelectProcessor` | 推送 | 推选款 |
| `select_image` | `SelectImageProcessor` | 选片 | 选片 |

## 枚举常量速查

### WorkflowStageTypeEnum（环节类型，18 种）

| 代码 | 中文 | 说明 |
|------|------|------|
| `BAND_PLANING` | 波段企划 | — |
| `STYLE_MODIFICATION` | 款式修改 | — |
| `SUGGESTED_PRICING` | 建议定价 | — |
| `STYLE_AUDIT` | 款式审核 | — |
| `STYLE_ALLOCATION` | 款式分配 | — |
| `FITTING` | 试穿 | — |
| `INFLUENCER_MERCHANT_MAIN_IMAGE_GENERATION` | 红人商家主图生成 | — |
| `BRAND_MERCHANT_MAIN_IMAGE_GENERATION` | 品牌商家主图生成 | — |
| `MAIN_IMAGE_SELECTION` | 主图选片 | — |
| `PUSH` | 推送 | — |
| `SEASON_TAG` | 季节标 | — |
| `OSS_2_CDN` | OSS转CDN | — |
| `PLANING` | 企划 | — |
| `DESIGN` | 设计改款 | — |
| `COLLOCATION` | 搭配 | — |
| `VIEW` | 视觉生图 | — |
| `SET` | 套图 | — |
| `APPROVE` | 审核 | — |
| `INFO_SUP` | 信息补充 | — |
| `FABRIC_TRY_ON` | 面料上身 | — |
| `VIDEO` | 视频 | — |

### NodeTypeEnum（节点类型，21 种）

| 代码 | 中文 | 支持重试 | 支持重产 |
|------|------|----------|----------|
| `strategy` | 策略 | — | — |
| `stage` | 环节 | — | — |
| `llm_text` | LLM文本 | ✅ | — |
| `gen_img` | 生图 | ✅ | ✅ |
| `map_gen_img` | MAP生图 | ✅ | — |
| `approve` | 审核 | — | — |
| `gen_video` | 视频生成 | ✅ | — |
| `template_match` | 模版匹配 | ✅ | — |
| `crop_head` | 图片裁头 | ✅ | — |
| `fabric_tryon` | 面料上身 | ✅ | — |
| `caption` | Caption | ✅ | — |
| `push_select` | 推选款 | ✅ | — |
| `select_image` | 选片 | ✅ | — |
| `suggest_price` | 定价 | ✅ | — |
| `industry_tag` | 产业标 | ✅ | — |
| `season_tag` | 季节标 | ✅ | — |
| `design_agent_prompt` | 改款prompt推理 | ✅ | — |
| `match_score` | 匹配度打分 | ✅ | — |
| `sub_category` | 副类目 | ✅ | — |
| `style_allocation` | 款式分配 | ✅ | — |

**辅助方法**：`isLlm()` (llm_text/design_agent_prompt)、`isGenImg()` (gen_img/map_gen_img/fabric_tryon)、`haveTemplateInput()` (gen_img/map_gen_img/fabric_tryon)

### WorkflowStatusEnum（记录状态）

| 状态 | 说明 |
|------|------|
| `INIT` | 初始化 |
| `TO_SUBMIT` | 待提交（审核节点等待批量创建） |
| `HANDLING` | 处理中 |
| `RETRYING` | 重试中 |
| `SUCCESS` | 成功 |
| `FAIL` | 失败 |
| `PERM_FAIL` | 永久失败 |

`OVER_STATUS_LIST` = SUCCESS + FAIL + PERM_FAIL
`HANDLING_STATUS_LIST` = HANDLING + RETRYING

### WorkflowBatchTypeEnum（批次类型）

| 类型 | 说明 |
|------|------|
| `STRATEGY` | 单策略批次 |
| `LINK` | 链路批次（多策略链） |
| `NODE` | 单节点批次 |
| `INDUSTRY_TAG_AND_SUGGESTED_PRICING` | 产业标+定价 |
| `SEASON_TAG` | 季节标 |
| `OSS_2_CDN` | OSS转CDN |

### LifeCycleEnum（生命周期）

| 值 | 说明 |
|----|------|
| `test` | 实验 |
| `gray` | 灰度 |
| `mass_prod` | 量产 |

### GenImgOutputModel（生图输出模式）

| 模式 | 说明 | 裂变行为 |
|------|------|----------|
| `SINGLE` | 单图输出 | 每张图独立创建下游 record |
| 批量 | 批量输出 | 整体作为一条 record 传递 |

### TemplateMatchTypeEnum（模板匹配维度）

| 维度 | 优先级 |
|------|--------|
| `CATE` (类目) | 最高 |
| `SEASON` (季节) | 次高 |
| `STYLE` (风格) | 次低 |
| `CTR` | 最低 |

## QA 测试要点汇总

### ⚠️ 操作安全红线（必读）
**供给品标题必须含「测试请不要拍」才可执行任何写操作。** 包括但不限于：推送素材生产、创建任务、AI预审复核、发起素材生成。其他所有数据均为生产数据，仅可查看，禁止一切写操作。
- 测试商家：seller_id 2219662018344（F88测试店铺）、2219635649153（F88测试卖家0213）
- 覆盖范围：从无到有（source_type=F88）+ 主动提报（source_type=F88_MATERIAL）
- AI素材管理页面：仅标题含「测试请不要拍」的商品才可点击【创建任务】

### 高风险区域

1. **裂变逻辑**：GenImg/MapGenImg/FabricTryOn 的 SINGLE 输出模式下，record 数量指数级增长，进度统计和重试逻辑易出错
2. **回调不可靠**：AfdJob `job_status` 回调可能丢失，导致 record 卡在 HANDLING（已知问题）
3. **审核任务生成时序**：approve 节点需先 trigger_approve 打标，再 try_push_approve_task 生成任务，两步顺序关系
4. **策略匹配优先级**：三级匹配（输入参数 → 商家运营 → 默认）可能命中非预期策略
5. **模板匹配疲劳度**：Tair 计数（每模板每批次最多 5 次），分布式锁保证原子性，锁超时可能导致计数偏差
6. **前后端视频上限不一致**：后端 10 条 vs 前端 15 项
7. **租户串扰**：新开 tab 时 X-AFD-Emp-Identity 可能残留上一租户

### 关键代码路径

| 关注点 | 路径 |
|--------|------|
| MCP 工具定义 | `interfaces/mcp/WorkflowBatchMcpTool.java` |
| 工作流引擎 | `domain/workflow2/service/impl/Workflow2EngineImpl.java` |
| 策略域服务 | `domain/workflow2/service/impl/StrategyDomainServiceImpl.java` |
| 节点处理器工厂 | `domain/workflow2/factory/NodeProcessorFactory.java` |
| Gemini API 集成 | `infrastructure/facade/nano/GeminiApiFacadeIdeaLabImpl.java` |
| Qwen LLM 集成 | `infrastructure/facade/llm/QwenLLMFacadeImpl.java` |
| 审核任务生成 | `application/workflow2/processor/approve/ApproveProcessor.java` |
| 调度器（核心） | `application/afd/scheduler/Workflow2RecordStartJob.java` |
| 模板匹配 | `application/workflow2/processor/template/TemplateMatchProcessor.java` |
| 视频生成 | `application/workflow2/processor/gen/GenVideoProcessor.java` |
| 数据源解析 | `domain/workflow2/datasource/DataSourceServiceImpl.java` |
