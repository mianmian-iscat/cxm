<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/code-level-issues.md -->
<!-- synced-at: 2026-07-11T03:52:35.005381 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/code-level-issues
title: F88 代码级已知问题与踩坑记录
owner: 目民
version: 1.1.0
created: 2026-06-29
updated: 2026-07-02
tags: [代码级, known-issues, 踩坑, 后端, 前端]
trigger_examples:
  - "审核/策略平台代码层面踩坑"
  - "接口调用报错/数据异常排查"
source_sessions: []
promotion_count: 0
---

# F88 代码级已知问题与踩坑记录

> 本文档从 `f88-code-level-reference.md` 拆分而来，集中收录所有代码级已知问题、Bug、踩坑、风险点与 QA 高风险项。架构/设计/实现细节请参阅 `infra/code-architecture.md`。

> **后端仓库**：`stylespot/stylespot-admin`（Pandora Boot + Spring Boot 2.5.12 + Java 11 + MyBatis Plus）
> **前端仓库**：`industry-source-code/iFashion-tools`（React + Redux + Axios）
> **更新时间**：2026-06-18

> ⚠️ **操作安全红线**：供给品标题必须含「测试请不要拍」才可执行写操作（推送/创建任务/AI预审复核/发起素材生产）。其他均为生产数据，只读禁止写。测试seller: 2219662018344 / 2219635649153。

---

# 一、策略平台 — 已知问题与风险

## 1.1 裂变（Fission）QA 风险

- **QA 风险**：裂变后 record 数量可能远超输入行数

## 1.2 调度器风险

### Workflow2RecordStartJob

- Tair "started" 标记 TTL=20min（防重），**超时可能导致重复启动**

## 1.3 LLM 任务链路 — AfdJob 已知问题

- **已知问题**：job_status 回调不可靠，大量 job 卡在 INIT 未更新

## 1.4 视频生成（GenVideoProcessor）QA 风险

- **QA 风险**：幂等检查是全量查询后内存过滤，活跃视频任务多时性能差

---

# 二、审核平台 — 已知代码问题

## 2.10 审核平台已知代码问题

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | `distributionLogic` 枚举值与 `allocationMethod` 相反 | ReviewTaskAppService:550 | 代码有兼容处理但易混淆 |
| 2 | `SimpleDateFormat` 作为 static 字段（非线程安全） | ReviewTaskAppService:160, InspectionTaskAppService:90 | 并发下日期解析可能出错 |
| 3 | 视频审核数量累加到图片计数 | ReviewTaskAppService:2161-2167 | 视频审核污染图片统计 |
| 4 | 抽检结果同步到源任务失败被静默吞掉 | ReviewTaskAppService:3879-3883 | 源任务可能状态不一致 |
| 5 | `PERSONAL_TASK_WHITE_LIST` 可查看所有个人任务 | ReviewTaskAppService:649 | 权限绕过 |
| 6 | createTaskInner 的 `validateCreateCmdInner()` 多项校验被注释 | ReviewTaskAppService:2293-2304 | 策略平台创建的任务跳过分配校验，可能 NPE |
| 7 | 幂等仅按名称检查，不检查 relationId 重复 | createTaskInner() | 同 batch+node+record 不同名称会创建重复任务 |
| 8 | 埋雷 accuracyRate 仅在 COMPLETED 状态显示 | calculateTaskProgress():858 | 与 inspection 的显示时机不对称 |
| 9 | 埋雷一致性在个人埋雷任务未完成前被置 null | convertTasksToVOList():502-519 | 隐藏埋雷结果直到正式完成 |
| 10 | approve 回调 passedImg 取 originUrl 忽略 localAdjustUrl | ApproveProcessor callback | 局部修改后全链路使用修改前图片（BT_5967，已修复 BT_5976） |
| 11 | selectedImgUrls 中 hasFeedback=true 的图片出现在 passedImg | ApproveProcessor callback | 脏数据（测试数据构造问题，BT_5976 AFD_RT15993914），非代码缺陷 |
| 12 | season_tag 模型返回"季节标未识别"时 status 留 HANDLING 不变 FAIL | SeasonTag2Processor.buildFinishMessage() | 兜底前(record级)此 bug 导致节点永久卡住；兜底后不再触发（需求 83728544） |

---

# 三、模板库 — 已知问题

## 3.3 模板匹配已知问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | `tagSearchConditionEntityList` 是 static 缓存，永不失效 | 类目标签数据变更需 JVM 重启 |
| 2 | Tair 计数全部超限时清除重试 | `templateMaxUseCount` 是轮转计数而非硬上限 |
| 3 | `templatePackages.get(0).getId()` 用于所有模板的 usedId | 多包场景（理论上不该有）可能 pkgId 错误 |
| 4 | 季节匹配不对称 | "春季".contains("春")=true ≠ "春".contains("春季")=false |
| 5 | biz_record_id 去重仅在 CLONE_FROM_INSTANCE_ID 存在时生效 | 独立并行链路间不去重 |

## 3.6 裁头处理器（ImageCropProcessor）QA 风险

- **QA 风险**：y2 未做边界校验（可能为 0 或超过图片高度）

---

# 四、QA 测试高风险清单（代码级汇总）

> ⚠️ **首要红线**：所有写操作（推送/创建任务/AI预审复核）仅针对供给品标题含「测试请不要拍」的数据，其他数据只读。

## 策略平台

| # | 风险 | 代码位置 | 测试建议 |
|---|------|----------|----------|
| 1 | startSomeRecord Tair 标记 20min TTL，超时可能重复启动 | Workflow2RecordStartJob | 模拟长时间处理任务，验证幂等 |
| 2 | 裂变 record 数量指数增长 | Workflow2EngineImpl.buildWorkflowRecordLogEntity1 | 大量图片输入，验证进度统计正确 |
| 3 | AfdJob 回调不可靠，job 卡 INIT | NanoBananaTaskHandler | 回调超时场景测试 |
| 4 | 策略匹配多策略并行提交 | submitWithStage() line 247 | 验证多策略同时命中时的实例创建 |
| 5 | GenVideo 幂等检查全量查询后内存过滤 | GenVideoProcessor.checkDataProcessed | 大量活跃视频任务时的性能和正确性 |
| 6 | 变量解析失败发 FAIL 但不抛异常 | onNodeStart() lines 426-459 | 验证错误信息是否完整传递 |
| 7 | 批次 TERMINATED 后 record 立即 FAIL | onNodeStart() line 413 | 终止后已有 RUNNING 任务的处理 |

## 审核平台

| # | 风险 | 代码位置 | 测试建议 |
|---|------|----------|----------|
| 8 | SimpleDateFormat 非线程安全 | ReviewTaskAppService:160 | 并发审核提交，检查时间字段 |
| 9 | 视频审核污染图片统计 | ReviewTaskAppService:2161-2167 | 混合视频+图片审核任务，验证计数 |
| 10 | 抽检结果同步失败被吞 | ReviewTaskAppService:3879-3883 | 模拟同步失败，验证源任务状态 |
| 11 | createTaskInner 幂等仅按名称 | createTaskInner() | 同 relationId 不同名称是否创建重复 |
| 12 | distributionLogic 枚举反转 | ReviewTaskAppService:550 | 验证按商家分配的实际行为 |
| 13 | PERSONAL_TASK_WHITE_LIST 权限绕过 | ReviewTaskAppService:649 | 白名单用户可见范围验证 |
| 14 | 埋雷不支持套图审核 | InspectionTaskAppService:220 | 套图审核任务不创建埋雷 |

## 模板库

| # | 风险 | 代码位置 | 测试建议 |
|---|------|----------|----------|
| 15 | setValid() 并发竞态（无 DB 锁） | SellerTemplatePackageServiceImpl:1376-1416 | 并发激活同 seller 不同包 |
| 16 | tagSearchConditionEntityList 静态缓存永不失效 | TemplateMatchProcessor:65 | 类目标签变更后验证匹配结果 |
| 17 | Tair 计数重置（全超限时清除） | TemplateMatchProcessor.parseAndSortTemplates | 大量请求耗尽配额后验证轮转 |
| 18 | 季节匹配不对称 | TemplateMatchProcessor SEASON_FILTER_MAPPING | 验证各季节组合的匹配结果 |
| 19 | 裁头 y2 无边界校验 | ImageCropProcessor.cropImageByY2 | 极端人脸位置（顶部/底部） |
| 20 | 模板包状态流转回退 | editTemplatePackage() IDLE → DRAFT | 编辑后重新审核流程 |
