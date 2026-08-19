# 数据库表结构速查

> stylespot 数据库（rm-lgay0v5lor8396yka），DMS dbId=5335708

## workflow_record_log

| 字段 | 说明 |
|------|------|
| id | 自增主键，也用于范围过滤加速查询 |
| batch_id | 批次 ID（如 BT_5441） |
| workflow_instance_id | 关联 g_workflow_instance |
| node_type | 环节类型：gen_img / gen_video / llm_text / strategy / template_match / industry_tag / season_tag 等 |
| status | 状态：SUCCESS / FAIL / HANDLING / INIT |
| extra_info | JSON，包含 errorMsg、strategyName、nodeName 等 |
| output_json | JSON，包含输出物 URL（outputVideo 等） |
| gmt_create | 创建时间 |

## g_workflow_instance

| 字段 | 说明 |
|------|------|
| workflow_instance_id | 主键 |
| strategy_id | 关联 g_strategy.id |
| common_variable | JSON，包含 seller_id 等运行时变量 |

## g_strategy

| 字段 | 说明 |
|------|------|
| id | 主键（注意不是 strategy_id） |
| name | 策略名称 |
| workflow_def | JSON，包含 innerNodes 数组（各节点配置） |
| extra_info | JSON，策略级额外配置 |

innerNodes 中每个节点的常见字段：`UId`、`name`、`type`（对应 node_type）、`modelType`、`imageSize`、`outputRatio`、`outputModel`。

## g_afd_review_job

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| info | JSON，包含审核任务快照数据，关键路径：`$.videoUrlReview.videoUrl`（BATCH 模式下 ApproveProcessor 读取的 URL） |
| workflow_instance_id | 关联 g_workflow_instance |
| review_job_id | 审核任务 ID（审核平台侧） |
| status | 审核任务状态：INIT / PROCESSING / FINISH |
| gmt_create | 创建时间（快照时间点） |
| gmt_modified | 最后修改时间 |

> **关键陷阱**：`info` 字段是创建时的快照，replaceImage 操作不会回写此字段。BATCH 模式下 ApproveProcessor 读取的是这里的 `videoUrlReview.videoUrl`，而非 g_afd_material 的实时 URL。

## g_afd_material

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| url | 素材当前 URL（replaceImage 操作会更新此字段） |
| material_type | 素材类型：IMAGE / VIDEO / MAIN_IMG 等 |
| operation_type | 最近操作类型：replaceImage / replaceVideo / replaceMainImg / replaceSkuImg / replaceDetailImg 等 |
| sub_job_id | 子任务 ID，用于链路追踪（部分操作未传递此字段，导致 trace 断裂，BT_5976 类问题） |
| workflow_instance_id | 关联 g_workflow_instance |
| extra_info | JSON，操作附加信息 |
| gmt_create | 创建时间 |
| gmt_modified | 最后修改时间（replaceImage 操作后此字段更新） |

> **关键陷阱**：`sub_job_id` 在 5 类素材操作中约有 4 类未传递（BT_5976），导致无法通过 traceId 关联到具体素材操作。`url` 是实时值，与 g_afd_review_job.info 中的快照可能不一致。
