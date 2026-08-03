<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/code-architecture.md -->
<!-- synced-at: 2026-07-11T03:52:35.004491 -->
<!-- skill: F88测试知识库 -->

---
id: infra/code-architecture
title: F88 平台代码架构与技术实现
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [代码架构, 工作流引擎, 后端, 前端]
trigger_examples:
  - "工作流引擎实现细节"
  - "代码架构和类关系"
source_sessions: []
promotion_count: 0
---

# F88 素材生产平台 — 代码架构与技术实现

> 本文档从 `f88-code-level-reference.md` 拆分而来，集中收录所有系统架构、工作流引擎、类层级、API 定义、数据库 Schema 等结构性内容。已知问题/踩坑/风险请参阅 `patterns/code-level-issues.md`。

> **后端仓库**：`stylespot/stylespot-admin`（Pandora Boot + Spring Boot 2.5.12 + Java 11 + MyBatis Plus）
> **前端仓库**：`industry-source-code/iFashion-tools`（React + Redux + Axios）
> **更新时间**：2026-06-18
> **定位**：本文档是代码级深度参考，与 `platform-business-rules.md`（业务规则）、`afd-review-platform-tech.md`（审核平台设计）、`template-library-tech.md`（模板库产品方案）、`f88-material-production-tech.md`（策略平台架构总览）互补，不重复产品层描述。

> ⚠️ **操作安全红线**：供给品标题必须含「测试请不要拍」才可执行写操作（推送/创建任务/AI预审复核/发起素材生产）。其他均为生产数据，只读禁止写。测试seller: 2219662018344 / 2219635649153。

---

# 一、策略平台（代码级）

## 1.1 工作流引擎核心方法

**文件**：`domain/workflow2/service/impl/Workflow2EngineImpl.java`

### onNodeStart() 完整流程

```
1. 幂等守卫：record 已在 OVER/HANDLING 状态 → 直接返回
2. 批次终止检查：batch.status == TERMINATED → record 立即 FAIL（errorMsg="批次终止"）
3. 节点解析：workflowTool.getNode() → NodeProcessorFactory 获取处理器
4. 分布式锁：Tair key = "G_Workflow_Operation_" + workflowInstanceId
5. 变量解析：dataSourceService.parseVariableValue() → 解析失败则发 FAIL 消息返回
6. 种子素材：generateSeedMaterial() 创建 AfdMaterialEntity（如不存在）
7. 审核节点特殊处理：APPROVE 类型 → 状态改为 TO_SUBMIT（不立即执行）
8. 执行：workflowRecordDomainService.start() → nodeProcessor.process()
```

### onNodeFinish() 完整流程

```
1. 幂等守卫：record 已在 OVER 状态 → 直接返回
2. terminated 标志：true → 发 end 消息，不创建下游节点
3. 分布式锁（同上）
4. 状态更新：SUCCESS → finish(outputData) / FAIL → fail() + end 消息返回
5. 公共变量更新：tryUpdateCommonVariable() → 将输出中的 CommonVariableEnum 持久化
6. 策略记录：最后节点或 notPass → 创建策略级汇总 record
7. 下游导航：
   - 下游是 StageNode → submitWithStage()（重新走策略匹配）
   - 下游是普通 Node → 创建 record + 发 start 消息
```

### 裂变（Fission）细节

- **触发条件**：上游节点是 `GenImgNode` / `MapGenImgNode` / `FabricTryOnNode` 且 `outputModel == SINGLE`
- **路径编号**：1-based（"1.1"、"1.2"、"1.3"），父路径默认 "1"
- **异常处理**：上游未产出图片 → `BizException("上游未产出图片")`

### 策略匹配三级优先级

```
1. 输入参数匹配：input.data 中的 TARGET_STRATEGY_ID（支持逗号分隔，含中文逗号"，"）
2. 商家运营匹配：StrategyPickHelper → SellerPeriodConfigEntity（sellerId + bandId）
   - 三级时间回退：同波段周期 → 最近未来周期 → 最近过去周期
   - Tair 缓存 TTL=5min，test 生命周期链路被跳过
3. 默认策略：isDefault == true
- 多策略同时匹配时全部并行提交（matchNodes.forEach）
```

## 1.2 调度器

### Workflow2RecordStartJob（核心调度器）

- 遍历所有 `TenantIdEnum`，每租户调用 `startSomeRecord(tenantId, batchCount=100)`
- 排除 APPROVE 节点（单独由 `ApproveTaskGenProgressJob` 处理）
- 按创建时间排序 PROCESSING 批次，先启动最早的

### WorkflowBatchProgressJob（进度计算）

- 只计算近期修改的批次（`now - LATEST_MINUTE_4_BATCH_STATISTIC` 分钟内有 record 变更的 batchId）
- 按环境过滤（`EnvUtil.getEnv()`）

### BatchAutoFinishProcessor

- **仅处理** `INDUSTRY_TAG_AND_SUGGESTED_PRICING` 批次类型
- 超时阈值：2 小时（硬编码，变量名 `towHour` 系 typo）
- **不处理策略平台批次**

## 1.3 LLM 任务链路

### NanoBananaTaskHandler（Gemini API 调用）

```
syncSubmitTask()：
1. 重试循环：最多 GEMINI_ALGORITHM_RETRY_COUNT 次
2. 构建 GeminiApiParam（outputRatio → aspectRatio；LLM_TEXT 场景 imageConfig=null）
3. URL 域名替换：scene-ossgw.taobao.com → industry-image.oss-cn-zhangjiakou.aliyuncs.com
4. 调用 GeminiApiFacade（流式/非流式由 GEMINI_STREAM_CALL 开关控制）
5. 结果处理：
   - GEN_IMG：提取图片字节 → 上传 OSS → 收集 URL
   - LLM_TEXT：提取文本 → 解析 ```json``` markdown 块
   - GEN_IMG_MAP：仅提取图片
6. 每次重试记录 TokenUsageSnapshot → 累加到 tokenUsageHistory
7. 重试间隔 2s
```

### GeminiApiFacadeIdeaLabImpl（API 调用实现）

- **AK 路由**：按 tenantId 从 `tenantAkMap` 取 AK，fallback 到默认 `ideaLabAk`
- **VIP Server**：`GEMINI_USE_VIP_SERVER` 开关，替换 hostname 为 VIP IP
- **图片处理**：≤7MB → base64 inlineData；>7MB → fileData（下载失败也 fallback 到 fileData）
- **流式解析**：SSE 逐行读取，`data:` 前缀行。多 chunk 合并：text 拼接、thought 拼接、inlineData 取最后、usageMetadata 取最后
- **错误检测**：`MPE-429` → CONCURRENCY_ISSUE；`MPE-001` → ALGO_CALL_ERROR；`PL-002` / "限流" / "429" / "100054" → 并发限流
- **Kill 开关**：`GEMINI_ALGORITHM_FAIL` → 立即抛异常（测试用）

### @TaskCallback 注解

```java
@TaskCallback {
    taskType,        // TaskTypeEnum
    taskStatus[],    // TaskStatusEnum 数组
    sceneCode,       // TaskSceneEnum
    order            // 优先级（低值高优先）
}
```

全代码库 43 处使用，链式职责模式（匹配后流转到下一个 handler）。

### AfdJob 生命周期

- **类型**：`LLM_GEN(100)`、`SUGGEST_PRICE(110)` + 7 种遗留工作流类型(1-7)
- **状态**：`INIT(0)` → `SUCCESS(1)` / `FAILED(2)`（简化三态）

## 1.4 视频生成（GenVideoProcessor）

- **节点类型**：`NodeTypeEnum.GEN_VIDEO`
- **输入**：最多 3 张图片（硬编码截断），currentUser/mainUser/itemId
- **URL 转换**：非 alicdn 图片自动上传到图片空间（防千牛 SDK SSRF 检查）
- **SDK**：`QN_VIDEO_SDK`，`QnVideoTaskBuilder.buildTask()`，`SdkVideoCallerSource.F88`
- **回调**：SUCCESS → 提取 videoUrl + coverUrl；其他状态 → fail 消息
- **幂等检查**：查询所有 QN_VIDEO_SDK 任务（DRAFT/SUBMIT/PROCESSING），在 Java 层按 workflowRecordId 过滤
- **tryRun**：不支持（返回 null）

## 1.5 节点类型枚举完整清单

| 代码 | 支持重试 | 支持重产 | isLlm | isGenImg | haveTemplateInput |
|------|----------|----------|-------|----------|-------------------|
| `strategy` | — | — | — | — | — |
| `stage` | — | — | — | — | — |
| `link` | — | — | — | — | — |
| `llm_text` | ✅ | — | ✅ | — | — |
| `gen_img` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `map_gen_img` | ✅ | — | ✅ | ✅ | ✅ |
| `approve` | — | — | — | — | — |
| `gen_video` | ✅ | — | — | — | — |
| `template_match` | ✅ | — | — | — | — |
| `crop_head` | ✅ | ✅ | — | — | ✅ |
| `fabric_tryon` | ✅ | — | — | — | ✅ |
| `caption` | ✅ | — | — | — | — |
| `design_agent_prompt` | ✅ | — | ✅ | — | — |
| `match_score` | ✅ | — | — | — | — |
| `season_tag` | ✅ | — | — | — | — |
| `industry_tag` | ✅ | — | — | — | — |
| `suggest_price` | ✅ | — | — | — | — |
| `sub_category` | ✅ | — | — | — | — |
| `style_allocation` | ✅ | — | — | — | — |
| `push_select` | ✅ | — | — | — | — |
| `select_image` | ✅ | — | — | — | — |

---

# 二、审核平台（代码级）

## 2.1 任务创建完整链路

### 手动创建（source=2）

```
ReviewTaskController.createMainTask()
  → ReviewTaskAppService.createTask()
    1. 参数校验（名称唯一、节点存在、标准存在）
    2. Excel 解析：reviewExcelParserAppService.parseSubTaskDataFromFile()
    3. 分配计算：validateAndProcessAllocation() → allocateTask()
    4. 构建主任务：ReviewJobEntity(jobType=MAIN_TASK, jobStatus=PENDING)
    5. 插入主任务
    6. 创建子任务：createSubJob()
       a. buildSubTaskEntities() → 每条数据一个 NORMAL_SUB_TASK
       b. createPersonalMainTasksForReviewers() → 每个审核人一个 PERSONAL_MAIN_TASK(job_type=4)
       c. 设置 empJobId → 子任务关联到审核人的个人主任务
       d. MetaQ 批量发送 ReviewSubJobCreateMessage
```

### 策略平台创建（source=1）

```
ApproveProcessor.createApproveJob()
  → ReviewTaskAppService.createTaskInner()
    - 任务名已存在 + source=1 → 返回已有任务 ID（按名称幂等）
    - 默认值：expectedDeliveryTime=now+1天，priority=0
    - 从 ReviewNodeEntity.extraInfo 读默认配置（标准、难度、人效、抽检/埋雷配置、分配逻辑、成员）
    - TEST 模式下所有任务分配给创建者
    - relationId 格式：{batchId}_{nodeUId}_{minWorkflowRecordId}
```

### 分配逻辑（三种方式）

| 代码 | 名称 | 逻辑 | 限制 |
|------|------|------|------|
| 1 | 均分 EVEN_DISTRIBUTION | 总数/参与人数 | — |
| 2 | 按商家 BY_SELLER | 按 seller_id 分组 → 映射到指定参与人 | 仅 commercialOperations 角色 |
| 3 | 手动 MANUAL | 前端指定每人数量 → 校验总和=总数 | — |

**按商家分配细节**：`sellerToParticipantMap` 在分配时计算，传入 `buildSubTaskEntities()`。无 seller_id 时使用 mock ID（从 -1 递减）。

### 子任务排序字段

`sort = {sellerId}_{md5(referenceImageUrl)}` — 确保同商家同图片相邻。

## 2.2 任务实体与 job_type 完整枚举

| job_type | 枚举 | Info 类 | 说明 |
|----------|------|---------|------|
| 0 | MAIN_TASK | ReviewJobMainTaskInfo | 主任务（配置+管理） |
| 1 | NORMAL_SUB_TASK | ReviewJobNormalSubTaskInfo | 普通审核子任务 |
| 2 | BURY_SUB_TASK | ReviewJobBurySubTaskInfo | 埋雷子任务 |
| 3 | INSPECTION_SUB_TASK | ReviewJobInspectionSubTaskInfo | 抽检子任务 |
| 4 | PERSONAL_MAIN_TASK | ReviewJobMainTaskInfo | 个人审核主任务 |
| 5 | PERSONAL_INSPECTION_MAIN_TASK | ReviewJobMainTaskInfo | 个人抽检主任务 |
| 6 | PERSONAL_BURY_MAIN_TASK | ReviewJobMainTaskInfo | 个人埋雷主任务 |

### MainTaskInfo 关键字段

- `questionType`：1=单图、2=套图、3=视频
- `allocation`：TaskAllocationDTO（方法 + 参与人 + 数量）
- `inspectionConfig` / `buryConfig`：抽检/埋雷配置
- `distributionLogic`：1=按商家、2=均分 — **注意：与 allocationMethod 枚举值相反（历史原因，代码中有兼容处理）**
- `pauseRecords` / `totalPauseDurationSeconds`：暂停记录
- `runMode`：FORMAL / TEST

## 2.3 主任务状态机

```
PENDING(1) → IN_PROGRESS(2) → WAITING_INSPECTION(3) → INSPECTING(4) → COMPLETED(5)
             ↓ 无抽检/埋雷                          ↓
             → COMPLETED(5)                        → COMPLETED(5)
             ↓ 暂停
             → PAUSING(6)
```

子任务状态：`PENDING(0)` → `APPROVED(1)` / `REJECTED(2)`

## 2.4 审核操作（auditOption）

| 值 | 含义 | 子任务状态变化 |
|----|------|----------------|
| 1 | 通过 | → APPROVED(1) |
| 2 | 不通过 | → REJECTED(2) |
| 3 | 重新审核 | → PENDING(0)，清除 endTime/auditTime/notPassReasonList |

### 抽检一致性判定（checkInspectionTaskConsistency）

- auditOption==1 + sourceSubTaskStatus==APPROVED → 一致(true)
- auditOption==2 + sourceSubTaskStatus==REJECTED → 进一步检查：
  - 单图：驳回原因列表是否一致（无序比较 `isFeedbackReasonListEqual`）
  - 套图：选中图片列表是否一致（按 afdMid 比较）
- 其他组合 → 不一致(false)

### 埋雷一致性判定（checkBuryTaskConsistency）

逻辑与抽检一致，但使用 `isConsistent` 字段（非 `isReReviewed`）。

## 2.5 抽检创建流程

```
所有审核人个人主任务完成 → doCompleteMainTaskIfAllPersonalDone()
1. 视频审核(questionType=3)：跳过抽检/埋雷，直接完成
2. 未启用抽检/埋雷：直接完成 → 触发下游
3. 否则：
   a. 创建埋雷任务（每审核人 5%，上限 50，随机抽取）
   b. 创建抽检任务（按比例或固定数量，按 sampleSourceUserIds 分组均匀分配，余数分配给前几人）
   c. 更新主任务 → INSPECTING(4)
```

**抽检采样细节**：
- 样本数 = `totalSampleCount`（配置值）或 `ceil(totalSubTaskCount * ratio / 100)`
- 最小 1，最大 = 子任务总数
- 深拷贝 auditContent（避免引用共享）

## 2.6 审核结果下游流转

```
completeMainTaskAndTriggerDownstream()：
1. 主任务 → COMPLETED(5)
2. 路由：
   - relationType=PRODUCTION_PLATFORM(1) → approveProcessor.finishMainTaskApprove()
   - relationType=TEMPLATE_LIBRARY(3) → sellerTemplatePackageService.finishTemplateReviewMainTask()

finishMainTaskApprove()：
1. 发送 ReviewMainTaskFinishMessage
2. → ReviewPlatformMessageListener 分页遍历所有子任务 → 逐条发 ReviewSubTaskFinishMessage
3. → approveProcessor.handleSubTaskFinished()
   - 提取 passedImgUrls → 为空则 terminated=true + notPass=true
   - 发送 WorkflowRecordFinishMessage → 回到策略平台引擎
```

**notPass 终止**：passedImgUrls 为空（审核全部不通过）→ 引擎收到 `terminated=true`，终止该 record 流程。

## 2.7 MQ 消息清单

Topic: `TOPIC_AFD_REVIEW_PLATFORM`

| Tag | 消息类 | 触发时机 |
|-----|--------|----------|
| MAIN_TASK_FINISH | ReviewMainTaskFinishMessage | 主任务完成 |
| SUB_TASK_FINISH | ReviewSubTaskFinishMessage | 主任务完成后逐条发 |
| CREATE_SUB_JOB | ReviewSubJobCreateMessage | 子任务批量创建 |
| UPDATE_SUB_JOB | ReviewSubJobCreateMessage | 子任务批量更新 |
| MATERIAL_TRANSFER | MaterialTransferMessage | 素材 URL 转移到审核平台 OSS |

## 2.8 素材操作接口完整清单

| 操作 | submit | update | cancel |
|------|--------|--------|--------|
| 修手 | submitRepairTask | updateRepairImage | cancelRepairTask |
| 换脸 | submitFaceSwapTask | updateFaceSwapImage | cancelFaceSwapTask |
| 局部调整 | submitLocalAdjustTask | updateLocalAdjustImage | cancelLocalAdjustTask |
| 高清化 | highQuality | updateHighQuality | cancelHighQuality |
| 裁剪 | crop | — | — |
| AI 扩图 | expend | updateExpendImage | cancelExpend |
| 镜像 | mirror | — | — |
| 换搭配 | submitCollocationSwapTask | updateCollocationSwapImage | cancelCollocationSwapTask |

## 2.9 权限系统

### 角色枚举

| 代码 | 中文 | 可创建任务 | 可删除任务 | 可全部审核完成 | 可查看抽检 |
|------|------|------------|------------|----------------|------------|
| annotator | 标注 | ❌ | ❌ | ❌ | ❌ |
| annotationTeamLead | 标注组长 | ✅ | ❌ | ✅ | ✅ |
| commercialOperations | 商运 | ✅ | ❌ | ✅ | ✅ |
| productOperations | 产运 | ✅ | ✅ | ✅ | ✅ |
| productManager | 产品 | ✅ | ✅ | ✅ | ✅ |

### 菜单可见性

- 无角色 → 所有审核菜单隐藏
- 仅 annotator → 审核标准管理隐藏
- annotator + teamLead + commercialOps → 审核节点管理隐藏
- 权限配置通过 GeneralConfig（HSF），按 tenantId 过滤

---

# 三、模板库（代码级）

## 3.1 模板包状态机

```
DRAFT(1) → REVIEWING(2) → IDLE(3) → IN_USE(4)
                        ↘ REJECTED(5)    ↘ IDLE(3)（被其他包替换时）
DELETED(0)
APPROVE(6), PENDING(7), WAIT(8) — 辅助状态
```

- **DRAFT → REVIEWING**：`audit()` 提交审核
- **REVIEWING → IDLE**：审核通过
- **REVIEWING → REJECTED**：审核拒绝
- **IDLE → IN_USE**：`setValid()` 激活
- **IN_USE → IDLE**：同 seller+range+scene 有新包激活时，旧包降级
- **约束**：同 seller_id + apply_range + apply_scene 仅一个 IN_USE（**应用层校验，非 DB 唯一约束，有并发竞态风险**）

### setValid() 前置检查

- `finishRefreshTag`：标签刷新未完成 → 阻止激活
- 查询已有 IN_USE 包 → 逐个降级为 IDLE → 新包设为 IN_USE

## 3.2 模板包 DO（`afd_seller_template_package`）

| 字段 | 说明 |
|------|------|
| seller_id | 商家 ID |
| package_name | 包名 |
| apply_range | 应用环节 |
| apply_scene | 应用场景 |
| status | 状态码(0-8) |
| tenant_id | 租户隔离（AFD/F88） |
| template_content | JSON（所有模板图数据） |
| package_history | 版本历史 |
| current_version | 版本号 |

## 3.3 模板匹配算法（TemplateMatchProcessor）

### process() 完整流程

```
1. 提取上下文：sellerId, stage(applyRange), scene(applyScene), taoCate, seasonTag, styleTags, targetMatchCount(默认1)
2. 查询活跃包：status=4(IN_USE) + sellerId + stage + scene
3. 克隆去重：tryGetUsedTemplateIds() → 检查 CLONE_FROM_INSTANCE_ID → 提取已匹配模板 ID（biz_record_id 去重）
4. 解析+排序（parseAndSortTemplates）：
   a. 解析：遍历所有包 → 反序列化 templateContent → 仅取 auditStatus=6(APPROVE) 的模板
   b. 类目过滤：
      - mustMatchFields 不含 match_cate 时才过滤
      - 匹配逻辑：tagId 精确匹配(score=2) / 同 parentTagId(score=1)
      - 存活模板太少 → 提前返回
   c. 季节过滤：
      - SEASON_FILTER_MAPPING 决定允许的季节组合（如"春"允许"春""夏""秋"）
      - 模糊匹配：targetSeason.contains(tag.trim()) → 不对称！"春季".contains("春")=true，反之 false
   d. Tair 使用计数：
      - key: template_use_count:{batchId}:{templateId}，TTL=24h
      - 超 maxCount 的模板被过滤
      - **全部超限时清除所有计数重试**（软限制，非硬上限）
   e. 排序（matchTypes 列表顺序决定优先级）：
      - cate: 类目匹配分(2精确/1同父/0无) + 使用次数升序
      - season: 季节分(2精确/1模糊/0无)
      - style: 风格分(2完全匹配/1有交集/0无)
      - ctr: recApplyItemCtrOnline14d 降序
   f. 克隆去重：移除已用模板 → 不够 targetMatchCount 则保留
   g. 截断：取 top targetMatchCount
5. 使用计数递增：incrUserCount()
6. 输出：matched_template_ids, matched_template_used_ids(sellerId_pkgId_templateId), matched_template_pkg, matchedImg
```

## 3.4 模板创建类型与策略路由

| 类型 | 路由目标 |
|------|----------|
| LOCAL_UPLOAD | strategy 10033 |
| SELF_MODEL_GENERATE | multipleTaskService（内部任务框架） |
| EXTERNAL_MODEL_GENERATE | strategy 10081（按模型路由） |
| └ gemini-2.5-flash-06-17 | strategy 10194 |
| └ gemini-2.5-flash-image | strategy 10195 |
| └ gemini-3-flash-preview | strategy 10196 |
| └ gemini-3-pro-image-preview | strategy 10197 |
| └ gemini-3.1-flash-image-preview | strategy 10198 |
| IMAGE_WASH | strategy 10225 |

## 3.5 多租户隔离

### 隔离层级

| 层 | 机制 |
|----|------|
| DB | `tenant_id` 列 + WHERE 条件过滤 |
| Hologres | 独立表：`ads_aifashion_template_gallery_f88` vs `ads_aifashion_template_gallery` |
| 应用场景 | ApplySceneEnum 绑定 tenant：F88 有 `F88_MAIN_IMAGE`、`F88_SEEDING` |
| 应用环节 | F88: 搭配/视觉/套图/视频 (`isF88Template`) vs AFD: 设计/搭配/视图/套图 (`isTemplate`) |
| 枚举列表 | `getEnumMap()` 按当前租户身份返回不同 applyRange |

### 三种模板池

| 池 | code | Hologres 表 |
|----|------|-------------|
| 淘内 | templateLibrary | AFD: `ads_aifashion_template_gallery` / F88: `ads_aifashion_template_gallery_f88` |
| 自研 | selfTemplateLibrary | `ads_aifashion_self_template_gallery` |
| 站外 | aiTemplateLibrary | `ads_aifashion_ai_template_gallery` |

## 3.6 裁头处理器（ImageCropProcessor）

```
1. 输入：inputImage URL
2. 提交 CompositionAnalysis 任务（DetType=FACE_BBOX）→ 异步
3. 回调 SUCCESS → 获取 face bbox [x1, y1, x2, y2]
4. 取 y2（人脸底部）→ OSS 图片处理裁剪：image/crop,x_0,y_{y2}
5. 无人脸 → 使用原图
6. tryCreateMaterial() 注册输出素材
```

## 3.7 商家筹备状态

`preparation_status` 是动态计算（非直接读 DB 列）：

```
1. 查 seller 是否有 IN_USE 的模板包（applyRange ∈ [COLLOCATION, VIEW]）
2. 查 seller 企划是否完成
3. 组合：
   - 模板包就绪 → COMPLETED(2)
   - 企划完成但模板未就绪 → IN_PROGRESS(1)
   - 否则 → PENDING(0)
```

仅 COMPLETED 状态商家可进入生产。

## 3.8 Hologres 模板数据表

`ads_aifashion_template_gallery_f88` 含 80+ 列：

- **标识**：template_id, template_num_id, src_tfs, item_id, seller_id
- **标签**：style_tags/ids, shape_tags/ids, color_tags/ids, texture_tags/ids, season_tags/ids, goutu_tags
- **图片元数据**：pict_height, pict_width, pic_ratio, pic_hash
- **效果指标**（7d/14d/30d 窗口，recent + online）：rec_pv, rec_click, rec_ctr, rec_gmv, rec_item_pv, rec_item_click, rec_item_ctr, rec_item_gmv
- **置信区间**：rec_ctr_recent_30d_lb / _ub

---

# 四、跨模块交互

## 4.1 策略平台 → 审核平台

```
ApproveProcessor.createApproveJob()
  → 收集 TO_SUBMIT 的 approve record
  → 构建 ReviewTaskCreateCmd
  → ReviewTaskAppService.createTaskInner(source=1)
  → 创建主任务 + 子任务 + 个人任务
  → relationId = batchId_nodeUId_minLogId
```

## 4.2 审核平台 → 策略平台

```
completeMainTaskAndTriggerDownstream()
  → relationType=PRODUCTION_PLATFORM → approveProcessor.finishMainTaskApprove()
  → MAIN_TASK_FINISH MQ → 遍历子任务发 SUB_TASK_FINISH
  → handleSubTaskFinished() → WorkflowRecordFinishMessage
  → Workflow2EngineImpl.onNodeFinish() → 继续下游节点
```

## 4.3 模板库 → 策略平台

```
TemplateMatchProcessor.process()
  → 查询 IN_USE 模板包
  → 匹配算法选模板
  → 输出 matched_template_used_ids 到工作流变量
  → 下游 GenImgNode 通过 {{node.matchedImg}} 引用
```

## 4.4 审核平台 → 模板库

```
completeMainTaskAndTriggerDownstream()
  → relationType=TEMPLATE_LIBRARY → sellerTemplatePackageService.finishTemplateReviewMainTask()
  → 审核通过 → 模板包 IDLE → 可激活 IN_USE
  → 审核拒绝 → 模板包 REJECTED
```

## 4.5 素材追踪链路

```
GenImgNode 完成 → WorkflowMaterialDomainService.tryCreateMaterial()
  → 创建 AfdMaterialEntity
  → fillTemplateInfo()：回溯 preRecordId 链 → 找 TEMPLATE_MATCH record → 填充模板追踪信息
  → useTemplateIds / useTemplateUsedIds / useTemplateUrls / useTemplatePkgIds
```
