<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/.legacy/f88-platform-quickref.md -->
<!-- synced-at: 2026-07-11T07:00:04.156427 -->
<!-- skill: F88测试知识库 -->

# F88 平台速查（从 MEMORY 迁移）

> 本文件包含原 MEMORY.md 中 F88 域专属的速查知识。详细的架构/代码/API 文档见同目录下的其他 references 文件。

## 模板包

- 接口前缀 `/api/template/package/*`，表 `afd_seller_template_package`
- AFD/F88 的 applyRange/applyScene 枚举不同，注意区分
- 状态：0删除 / 1草稿 / 2审核中 / 3闲置 / 4使用中 / 5拒绝
- 同 sellerId+applyRange+applyScene 仅一个 IN_USE
- 命名：`mmtest_{场景中文}{环节中文}{月日}`，默认搭配×主图，创建前须确认环节/场景
- 审核节点接口返回全集，不按 applyRange 过滤

## 流式提报

- batch_id 按 link_id+日期聚合
- 无 input_data 时 f88_stage/process_mode 保持 NULL

## video_push

- uploadType：MAIN_IMAGE_DIRECT / SEEDING_VIDEO
- 入参 `vedio_url`
- 策略 10569 种草视频测试策略

## 测试店铺

- sellerId = 2219662018344

## i-FASHION 策略平台

- 生产库：rm-lgay0v5lor8396yka（db_id=5335708）
- 预发库：pc-0jl93173aepu185r2（db_id=6369910，无查询权限）
- 核心表：workflow_record_log（input/output JSON）、g_workflow_instance、g_strategy（workflow_def.innerNodes.modelType/outputRatio）
- 搭配特征表：taobao_tec_platform.afd_shop_template_flat（25列，ds分区），15维预提，每条为单品模版非整套
- node_type 为 id>4000000 或 batch_id
- seller_id/strategyName 用 JSON_EXTRACT(common_variable/extra_info)
- 失败状态 FAIL，错误在 extra_info->$.errorMsg
- 策略详情接口 `/api/workflow2/strategy/get?id={id}`

### 多租户隔离

- pre-aifashion-xiaoer：UI 切换 AFD/F88 后 API 和策略列表隔离
- save API 的 tenantId 须与 UI 一致
- F88 API 需 `X-AFD-Emp-Identity:f88` header

### batch API

- `/api/workflow/batch/getRunDetail?batchId=BT_xxxx` 返回 stageProgress
- `/api/workflow/batch/page` 分页，导出须 POST

### admin 路由

- `/review/standard-management`
- `/review/node-management`

## F88 抽检平台

- 前端：industry-source-code/iFashion-tools
- 后端：~/stylespot-admin/
- qt=1单图 / 2套装 / 3视频 / 4封面
- qt=2 确认后自动下一子任务，qt=1 仅过/不过
- 首图 toolbar 禁用、单图 toolbar 消失为 BUG
- 新建任务需 F88 身份、新 tab 防串租户
- allocation/inspectionConfig/buryConfig 经 dt()
- img_url_list 单 URL，participants≥1

### EditDrawer 权限

- canEditAllocation：status=1
- canEditInspectionSettings：<3
- Basic 恒 true，Create 恒 false

### job_type

- 0主 / 1子 / 2埋雷 / 3抽检
- qt=3 无埋雷

### 已知 BUG

- 漏传 qt=3 致 videoAuditContent 不更新
- auditOption=3 未清 isReReviewed
- submitTaskResult 未校验 notPassReasonList
- SubTable 中抽检/埋雷 accuracyRate、审核 passRate

### 视频抽检

- 列表：`/ptcTab=spotCheck`
- 详情：`/task/detail?taskId={id}&taskType=spotCheck`
- 提交：`/api/afd/review/inspection/audit/submit`
- 状态：0待审 / 1完成 / 2待抽检
- 列表"不正确" = auditOption=3

### 生产监控

- HANDLING 查 node_type 积压 / SUCCESS 基线
- AfdJob 回调不可靠（VIDEO_PUSH）

### ODPS 小时表

- project=taobao_tec_platform（ds+hh，LC=7d）
- s_g_afd_review_job_hour → g_afd_review_personal_main_task_hour（task_type 4/5/6）
- g_afd_review_normal_sub_task_detail_hour（job_type=1）

## F88 素材供给链路

- 测试主图 link_id=20180（PRD 写 20188）
- sellerId=2219662018344
- 驳回重生产为 20180 配置
- FAILED_HOLD/TIMEOUT 为 DB 字段值

### Diamond 开关

- LINK_RETRY_TIME_CONFIG（按 link_id 隔离）
- MATERIAL_PROD_TIMEOUT_HOURS（改 0=立即超时）

### SchedulerX2

- 超时扫描 Job=871788127（Group=stylespot-admin）
- 生产失败→FAILED_HOLD(72h)→定时扫描转 FAIL 下发
- 审核丢弃立即下发

### 相关表

- g_afd_material_prod_record
- g_afd_recommend_material_pool_record
- prod_record 无 terminal/fail_type/msg_push_time/link_id 字段，均在 extra_info JSON 中提取
- tenant_id 隔离

### 主动提报入口

- pre-xiaoer AI素材管理 → 创建任务
