# SQL 查询模板（T1-T9）

根据 SKILL.md 路由表确定模板编号后，读取对应章节获取完整 SQL。

---

## T1：批次失败分析

```sql
-- T1-1：批次全貌（节点 × 状态分布）
SELECT node_type, status, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 9000000 AND env = 'staging'
GROUP BY node_type, status ORDER BY node_type, status;

-- T1-2：失败记录错误分类
SELECT CASE
  WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%429%' THEN 'Quota (429)'
  WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%500%' THEN 'Model internal (500)'
  WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%model was deprecated%' THEN 'Model deprecated'
  WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%Cannot fetch content%' THEN 'URL inaccessible'
  WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%timeout%' THEN 'Timeout'
  ELSE CONCAT('Other: ', LEFT(JSON_EXTRACT(extra_info, '$.errorMsg'), 80))
END AS error_type, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND status = 'FAIL' AND id > 9000000 AND env = 'staging'
GROUP BY error_type ORDER BY cnt DESC;

-- T1-3：TPP 算法任务回调检查（gen_img 节点）
SELECT t.task_status, COUNT(*) AS cnt
FROM g_admin_task t
WHERE t.job_id IN (
  SELECT a.id FROM workflow_record_log a
  WHERE a.batch_id = '{batch_id}' AND a.node_type = 'gen_img' AND a.id > 9000000
)
GROUP BY t.task_status;
```

## T2：审核节点排查

```sql
-- T2-1：审核任务层级（主任务/子任务/巡检）
SELECT job_type, job_status, COUNT(*) AS cnt
FROM g_afd_review_job
WHERE relation_id LIKE '{batch_id}_%'
GROUP BY job_type, job_status ORDER BY job_type, job_status;

-- T2-2：审核快照 vs 实时 URL 一致性（replaceImage 副作用检查）
SELECT COUNT(*) AS total,
  SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) != m.url
      THEN 1 ELSE 0 END) AS mismatch_cnt
FROM g_afd_review_job rj
JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE rj.relation_id LIKE '{batch_id}_%' AND rj.job_type IN (1, 3);

-- T2-3：审核回调状态
SELECT a.node_type, a.status, COUNT(*) AS cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}' AND a.id > 9000000 AND env = 'staging'
  AND a.node_type IN ('approve', 'image_text_upload')
GROUP BY a.node_type, a.status;
```

## T3：素材生产排查

```sql
-- T3-1：商品关联批次
SELECT batch_id, status, tao_cate_name
FROM g_afd_material_prod_record
WHERE item_id = '{item_id}' AND env = 'staging'
ORDER BY id DESC LIMIT 20;

-- T3-2：素材产出物检查（按 biz_scene 统计 URL 覆盖率）
SELECT m.biz_scene, m.source, COUNT(*) AS cnt,
  SUM(CASE WHEN m.url IS NOT NULL AND m.url != '' THEN 1 ELSE 0 END) AS with_url
FROM g_afd_material m
JOIN (
  SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(extra_info, '$.afdMid')) AS afd_mid
  FROM workflow_record_log
  WHERE batch_id = '{batch_id}' AND id > 9000000 AND env = 'staging'
    AND extra_info IS NOT NULL
) w ON m.afd_mid = w.afd_mid
WHERE m.env = 'staging'
GROUP BY m.biz_scene, m.source;

-- T3-3：素材数据完整性审计（按 source 检查 URL 覆盖）
SELECT m.source, COUNT(*) AS total,
  SUM(CASE WHEN m.url IS NOT NULL AND m.url != '' THEN 1 ELSE 0 END) AS with_url,
  ROUND(SUM(CASE WHEN m.url IS NOT NULL AND m.url != '' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS coverage_pct
FROM g_afd_material m
JOIN (
  SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(extra_info, '$.afdMid')) AS afd_mid
  FROM workflow_record_log
  WHERE batch_id = '{batch_id}' AND id > 9000000 AND env = 'staging'
    AND extra_info IS NOT NULL
) w ON m.afd_mid = w.afd_mid
WHERE m.env = 'staging'
GROUP BY m.source;
```

## T4：种草发布排查

> **注意**：`g_afd_recommend_material_pool_record` 数据量极大，所有查询必须带 `env = 'staging'` 和 `LIMIT`，否则 ReadTimeout。

```sql
-- T4-1：发布/回流状态（原始行采样，禁止 GROUP BY — 该表极大，聚合必超时）
-- 拿到原始行后在代码层按 biz_scene + status 做 COUNT 统计
SELECT id, biz_scene, status
FROM g_afd_recommend_material_pool_record
WHERE seller_id = '{seller_id}' AND env = 'staging'
LIMIT 100;

-- T4-2：发布失败原因（status=7 为发布失败，禁止 GROUP BY — 取原始行由代码层统计）
SELECT id, biz_scene,
  JSON_EXTRACT(ext_info, '$.publishFailReason') AS fail_reason
FROM g_afd_recommend_material_pool_record
WHERE seller_id = '{seller_id}' AND status = 7 AND env = 'staging'
LIMIT 50;

-- T4-3：contentId 为空检查（取原始行，代码层判断空占比）
SELECT id, biz_scene,
  JSON_EXTRACT(ext_info, '$.contentId') AS content_id
FROM g_afd_recommend_material_pool_record
WHERE seller_id = '{seller_id}' AND biz_scene = '{biz_scene}' AND env = 'staging'
LIMIT 50;
```

## T5：卖家维度排查

> **注意**：`g_afd_recommend_material_pool_record` 和 `g_afd_material_prod_record` 按 seller_id 查询均会 ReadTimeout（表极大）。改用 batch_id 精确查询；如需 item_id 维度也可秒回。

```sql
-- T5-1：批次商品映射（用 batch_id 查，seller_id 会超时）
SELECT item_id, batch_id, status, tao_cate_name
FROM g_afd_material_prod_record
WHERE batch_id = '{batch_id}' AND env = 'staging'
ORDER BY id DESC LIMIT 50;
```

## T6：阶段衔接排查

```sql
-- T6-1：批次元信息
SELECT batch_id, status, batch_type, source_type, gmt_create
FROM g_workflow_batch
WHERE batch_id = '{batch_id}' AND env = 'staging';

-- T6-2：阶段间流转完整性
SELECT a.node_type AS from_node, a.status AS from_status,
       b.node_type AS to_node, b.status AS to_status,
       COUNT(*) AS cnt
FROM workflow_record_log a
JOIN workflow_record_log b ON a.trace_id = b.trace_id
WHERE a.batch_id = '{batch_id}' AND a.id > 9000000 AND a.env = 'staging'
  AND b.batch_id = '{batch_id}' AND b.id > 9000000 AND b.env = 'staging'
GROUP BY a.node_type, a.status, b.node_type, b.status
ORDER BY a.node_type;

-- T6-3：断裂 trace 检测（有上游无下游）
SELECT a.trace_id, a.node_type AS stuck_node
FROM workflow_record_log a
LEFT JOIN workflow_record_log b ON a.trace_id = b.trace_id
  AND b.node_type = '{expected_next_node}' AND b.id > 9000000
WHERE a.batch_id = '{batch_id}' AND a.id > 9000000 AND a.env = 'staging'
  AND a.status = 'SUCCESS' AND a.node_type = '{current_node}'
  AND b.id IS NULL
LIMIT 20;
```

## T7：链路配置检查

```sql
-- T7-1：链路定义
SELECT id, name, life_cycle, is_deleted
FROM g_link WHERE env = 'staging' AND is_deleted = 0;

-- T7-2：策略节点定义（innerNodes 解析）
SELECT id, name, stage_code, life_cycle_code,
  JSON_LENGTH(JSON_EXTRACT(workflow_def, '$.innerNodes')) AS node_count
FROM g_strategy WHERE id = '{strategy_id}';
```

## T8：链路追踪（SLS 辅通道）

需要用户提供 traceId 或精确时间窗口。通过 normandy CLI 查询 SLS 日志，验证 MQ 消息是否正常发送。

```bash
# 查询 workflow 完成消息发送记录
normandy log list --source sls \
  --project stylespot-admin-log --logstore stylespot-admin-online \
  --query "sendWorkflowRecordFinishMsg and {traceId}" \
  --from "YYYY-MM-DD HH:MM:SS+0800" --to "YYYY-MM-DD HH:MM:SS+0800" \
  --size 50 --reverse --output json

# 查询 MQ 消息消费记录
normandy log list --source sls \
  --project stylespot-admin-log --logstore stylespot-admin-online \
  --query "ConsumeMessageThread and {batchId}" \
  --from "YYYY-MM-DD HH:MM:SS+0800" --to "YYYY-MM-DD HH:MM:SS+0800" \
  --size 50 --reverse --output json

# 查询 approve 回调
normandy log list --source sls \
  --project stylespot-admin-log --logstore stylespot-admin-online \
  --query "approve and callback and {batchId}" \
  --from "YYYY-MM-DD HH:MM:SS+0800" --to "YYYY-MM-DD HH:MM:SS+0800" \
  --size 50 --reverse --output json
```

## T9：视频产出校验

```bash
# ffprobe 校验视频参数
ffprobe -v quiet -print_format json -show_streams -show_format "{video_url}"
```

对比 `workflow_record_log.output_json` 中记录的分辨率/编码/码率/帧率/时长与策略配置是否一致。
