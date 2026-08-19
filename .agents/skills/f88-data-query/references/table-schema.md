# F88 核心表结构（本地缓存）

> 只列各 skill 文档中实际用到的表与字段。查表结构先读本文，需要全量字段再 `DESC 表名`。

## workflow_record_log — 工作流节点执行日志（失败分析主表，超大表）

关键字段：`id`、`batch_id`、`workflow_instance_id`、`node_type`、`status`（SUCCESS/FAIL/HANDLING/INIT）、`extra_info`（JSON：`$.errorMsg` / `$.strategyName` / `$.nodeName` / `$.mainImgUrl` / `$.imageUrl`）、`output_json`（JSON：`$.outputVideo` / `$.passedImg`）、`input_json`、`trace_id`、`env`、`gmt_create`、`gmt_modified`

查询必带 `id >= {id_threshold}`，阈值通过 `~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py` 动态获取；node_type 无索引。禁止硬编码 4000000/6400000。

## g_workflow_instance — 工作流实例（连接日志与策略）

关键字段：`workflow_instance_id`、`strategy_id`、`common_variable`（JSON：`$.seller_id` / `$.execMode`）、`id`、`batch_id`、`stage_id`、`node_type`、`status`

## g_strategy — 策略配置（节点定义）

关键字段：`id`（**主键，不是 strategy_id**）、`name`、`workflow_def`（JSON：`$.innerNodes[]`，每个节点含 UId/name/type/modelType/imageSize/outputRatio/outputModel）、`extra_info`、`gmt_modified`、`creator_name`

与 g_link 无外键：从 g_link.struct JSON 解析 strategy IDs。

## g_afd_review_job — 审核任务（三层结构）

关键字段：`id`、`name`、`info`（创建时快照 JSON：`$.videoUrlReview.videoUrl`、`$.afdMid`；另有写法 `videoAuditContent.videoUrlReview.videoUrl`）、`extra`、`job_type`（0=主 / 1=子审核 / 3=抽检子 / 4=主审核 / 5=抽检主）、`job_status`（1=待处理 / 2=已观测到，语义待确认 / 4=处理中 / 5=已完成）、`parent_job_id`、`relation_id`（形如 BT_xxxx_<uuid>）、`relation_type`、`batch_id`（BT_xxxx，可直接按批次查）、`link_id`（=链路 ID）、`seller_id`、`seller_name`、`emp_id`/`emp_name`（处理人）、`assigned_emp_ids`/`assigned_emp_names`、`create_emp_id`/`create_emp_name`、`env`、`deleted`（0=有效）、`band_id`/`band_name`、`start_time`/`end_time`、`gmt_create`、`gmt_modified`

**2026-08-11 实测修正（stylespot dbId=5335708 information_schema 验证）**：无 `review_job_id`、`status`、`workflow_instance_id` 列（旧缓存有误，引用会报 Unknown column）；按批次查用 `batch_id='BT_xxxx' AND env='staging' AND deleted=0`（batch_id 列疑似无索引，超时则改按主键 id 查）。

**无 node_id 列**：定位节点用 parent_job_id + relation_id。info 是快照，replaceImage 不回写。

## g_afd_material — 素材表（实时 URL）

关键字段：`id`、`afd_mid`、`url`（实时）、`material_type`（IMAGE/VIDEO/MAIN_IMG，业务类型）、`type`（媒体格式，恒为"图片"，勿当业务类型用）、`operation_type`（replaceImage/replaceVideo/replaceMainImg/replaceSkuImg/replaceDetailImg）、`sub_job_id`、`workflow_instance_id`、`extra_info`（`$.operationDetail`）、`gmt_create`、`gmt_modified`

## g_workflow_batch — 批次主表

关键字段：`id`、`batch_id`（BT_xxxx）、`batch_name`、`batch_type`（如 link）、`status`（PROCESSING 等）、`relation_id`（=链路 ID，不是批次号）、`relation_type`（如 link）、`source_type`（如 F88）、`source_id`、`workflow_info`（JSON：uUid/name/type/nodes）、`input_info`、`extra_info`、`submitter_id`/`submitter_name`、`creator`/`modifier`、`version`、`tenant_id`、`env`、`is_deleted`、`gmt_create`、`gmt_modified`

**2026-08-11 实测修正（stylespot dbId=5335708）**：无 `name`/`exec_mode`/`chain_id` 列（旧缓存有误）；批次名用 `batch_name`，链路 ID 用 `relation_id`（relation_type='link'）。按 `batch_id='BT_xxxx' AND env='staging'` 查。

## g_link — 链路配置

关键字段：`id`、`name`、`env`、`life_cycle`（mass_prod/test/gray）、`submitter_name`、`struct`（stages JSON，含 strategy IDs）、`is_deleted`、`exec_mode`、`gmt_modified`

## g_admin_task — TPP 算法任务（回调检查）

关键字段：`job_id`（=workflow_record_log.id）、`task_status`（10 且 gmt_modified=gmt_create → 从未回调）、`gmt_create`、`gmt_modified`

## g_afd_material_prod_record — 素材生产记录（商品→批次映射）

关键字段：`id`、`item_id`、`seller_id`、`batch_id`、`biz_record_id`、`status`、`first_record_id`/`last_record_id`、`input_data`/`output_data`（JSON）、`tao_cate_id`/`tao_cate_name`、`tenant_id`、`env`、`deleted`、`gmt_create`/`gmt_modified`

**2026-08-12 实测修正（stylespot dbId=5335708 DESC 验证）**：无 `source_type`、`dispatch_status` 列（旧缓存有误，引用会报 Unknown column）；状态列是 `status`，软删列是 `deleted`。

## g_afd_recommend_material_pool_record — 种草/推荐素材池（发布与回流）

关键字段：`seller_id`、`item_id`、`biz_scene`、`status`（7=发布失败）、`ext_info`（`$.publishFailReason` / `$.contentId`）

## g_strategy_config — 策略-模型配置

关键字段：`id`、`strategy_name`、`model`、`status`（'ACTIVE'）
