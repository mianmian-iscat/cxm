# 监控专用 SQL 模板

所有查询通过 `dms-alibaba` CLI 执行，数据库参数：`stylespot --db rm-lgay0v5lor8396yka`。

**重要**：
1. 所有 `workflow_record_log` 查询必须加 `id > 4000000`（或更高的阈值）以防止超时。
2. **所有查询必须加 `AND env = 'staging'`**，仅巡检预发环境数据。线上数据（env='prod'）只能查看不能动。

## 活跃批次列表

```sql
SELECT batch_id, COUNT(*) AS total_records,
       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_cnt,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_cnt,
       SUM(CASE WHEN status = 'HANDLING' THEN 1 ELSE 0 END) AS handling_cnt,
       MIN(gmt_create) AS earliest,
       MAX(gmt_create) AS latest
FROM workflow_record_log
WHERE id > 4000000
  AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY batch_id
ORDER BY latest DESC
```

## 批次健康度快照

```sql
SELECT node_type, status, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = 'staging'
GROUP BY node_type, status
ORDER BY node_type, status
```

## HANDLING 停滞检测

```sql
SELECT id, node_type, gmt_modified,
       TIMESTAMPDIFF(MINUTE, gmt_modified, NOW()) AS stuck_minutes
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'HANDLING'
  AND id > 4000000
  AND env = 'staging'
  AND TIMESTAMPDIFF(MINUTE, gmt_modified, NOW()) > 30
ORDER BY stuck_minutes DESC
```

## LLM 429 错误统计

```sql
SELECT node_type, COUNT(*) AS cnt,
       MIN(gmt_create) AS first_seen,
       MAX(gmt_create) AS last_seen
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND id > 4000000
  AND env = 'staging'
  AND (JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%429%'
       OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%RESOURCE_EXHAUSTED%')
GROUP BY node_type
```

## Mock 错误检测

```sql
SELECT node_type, COUNT(*) AS cnt,
       JSON_EXTRACT(extra_info, '$.errorMsg') AS error_msg
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND id > 4000000
  AND env = 'staging'
  AND JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%mock%'
GROUP BY node_type, JSON_EXTRACT(extra_info, '$.errorMsg')
```

## 阶段执行确认

查询当前批次实际触发了哪些 strategy（对应哪些阶段）：

```sql
SELECT DISTINCT b.strategy_id, s.name AS strategy_name,
       COUNT(a.id) AS record_cnt
FROM workflow_record_log a
JOIN g_workflow_instance b ON a.workflow_instance_id = b.workflow_instance_id
LEFT JOIN g_strategy s ON b.strategy_id = s.id
WHERE a.batch_id = '{batch_id}'
  AND a.id > 4000000
  AND a.env = 'staging'
GROUP BY b.strategy_id, s.name
ORDER BY b.strategy_id
```

注意：JOIN 可能超时，如超时可分两步查。

## 审核输出参数检查

```sql
SELECT a.id, a.node_type, a.status,
       JSON_EXTRACT(a.output_json, '$.passedImg') AS passed_img,
       JSON_EXTRACT(a.extra_info, '$.errorMsg') AS error_msg
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.node_type LIKE '%approve%'
  AND a.id > 4000000
  AND a.env = 'staging'
```

## 上游服务错误统计

```sql
SELECT
  CASE
    WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%upstream request failed%'
      THEN 'upstream_request_failed'
    WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%Cannot fetch content%'
      THEN 'url_inaccessible'
    WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%Error 404%'
      THEN 'api_404'
    WHEN JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%500%'
      THEN 'server_500'
    ELSE 'other'
  END AS error_type,
  COUNT(*) AS cnt,
  MAX(gmt_create) AS latest
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND id > 4000000
  AND env = 'staging'
GROUP BY error_type
ORDER BY cnt DESC
```

## 输出物 URL 抽样

```sql
SELECT id, node_type, status,
       JSON_EXTRACT(output_json, '$.outputVideo') AS output_video,
       JSON_EXTRACT(output_json, '$.outputImage') AS output_image
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'SUCCESS'
  AND node_type IN ('gen_video', 'gen_img')
  AND id > 4000000
  AND env = 'staging'
ORDER BY id DESC
LIMIT 10
```

## 跨批次失败趋势（最近 5 个批次）

```sql
SELECT batch_id,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_cnt,
       ROUND(SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS fail_rate
FROM workflow_record_log
WHERE id > 4000000
  AND env = 'staging'
  AND batch_id IN ({batch_id_list})
GROUP BY batch_id
ORDER BY batch_id DESC
```

替换 `{batch_id_list}` 为逗号分隔的批次 ID 列表（如 `'BT_5819','BT_5708','BT_5621'`）。

---

## 算法网关错误统计（WF7）

```sql
SELECT node_type,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_cnt,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_cnt,
       ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS success_rate,
       JSON_EXTRACT(extra_info, '$.errorMsg') AS top_error
FROM workflow_record_log
WHERE id > 4000000
  AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND node_type IN ('gen_img', 'gen_video', 'strategy', 'algo_filter', 'quality_score', 'style_transfer')
GROUP BY node_type
ORDER BY fail_cnt DESC
```

## 异步回调成功率（WF7）

检查算法异步回调是否正常回传（HANDLING→SUCCESS/FAIL 的转化率）：

```sql
SELECT node_type,
       SUM(CASE WHEN status = 'HANDLING' THEN 1 ELSE 0 END) AS handling_cnt,
       SUM(CASE WHEN status IN ('SUCCESS', 'FAIL') THEN 1 ELSE 0 END) AS completed_cnt,
       ROUND(SUM(CASE WHEN status IN ('SUCCESS', 'FAIL') THEN 1 ELSE 0 END) /
             NULLIF(COUNT(*), 0) * 100, 1) AS callback_rate
FROM workflow_record_log
WHERE id > 4000000
  AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 2 HOUR)
  AND node_type IN ('gen_img', 'gen_video', 'strategy', 'algo_filter')
GROUP BY node_type
```

## 节点处理超时统计（WF7）

按节点类型统计平均/最大处理时长，对比阈值（gen_img=300s, gen_video=600s, strategy=180s）：

```sql
SELECT node_type,
       COUNT(*) AS total,
       ROUND(AVG(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)), 0) AS avg_seconds,
       MAX(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)) AS max_seconds,
       SUM(CASE
         WHEN node_type = 'gen_img' AND TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified) > 300 THEN 1
         WHEN node_type = 'gen_video' AND TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified) > 600 THEN 1
         WHEN node_type = 'strategy' AND TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified) > 180 THEN 1
         ELSE 0
       END) AS timeout_cnt
FROM workflow_record_log
WHERE id > 4000000
  AND env = 'staging'
  AND status = 'SUCCESS'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND node_type IN ('gen_img', 'gen_video', 'strategy')
GROUP BY node_type
```

## 企划案产出检查（WF8）

检查企划案数据产出是否符合 T+1 时效：

```sql
SELECT MAX(ds) AS latest_partition,
       DATEDIFF(CURDATE(), STR_TO_DATE(MAX(ds), '%Y%m%d')) AS delay_days,
       COUNT(*) AS record_cnt
FROM ads_g_item_profile_shop_gene
WHERE ds >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 DAY), '%Y%m%d')
```

**注意**: 如果该表不在 stylespot DB 中，需确认具体 DB 连接信息。

## 商品数据时效检查（WF8）

检查商品画像数据最新分区，确认是否及时更新：

```sql
SELECT MAX(ds) AS latest_partition,
       DATEDIFF(CURDATE(), STR_TO_DATE(MAX(ds), '%Y%m%d')) AS delay_days,
       COUNT(*) AS total_records
FROM ads_g_item_profile_shop_gene
WHERE ds >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 DAY), '%Y%m%d')
  AND item_id IS NOT NULL
```

## 素材产出量检查（WF8）

统计最近 24h 的素材产出量并与 7 日均值对比：

```sql
SELECT
  (SELECT COUNT(*)
   FROM workflow_record_log
   WHERE id > 4000000 AND env = 'staging'
     AND status = 'SUCCESS'
     AND node_type IN ('gen_img', 'gen_video')
     AND gmt_create > DATE_SUB(NOW(), INTERVAL 24 HOUR)
  ) AS today_output,
  (SELECT ROUND(COUNT(*) / 7, 0)
   FROM workflow_record_log
   WHERE id > 4000000 AND env = 'staging'
     AND status = 'SUCCESS'
     AND node_type IN ('gen_img', 'gen_video')
     AND gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
  ) AS avg_7d_output
```

## 潜力预估数据检查（WF8）

检查潜力预估模型产出的最新数据更新时间：

```sql
SELECT MAX(gmt_modified) AS latest_update,
       TIMESTAMPDIFF(HOUR, MAX(gmt_modified), NOW()) AS delay_hours,
       COUNT(*) AS total_records
FROM ads_g_item_profile_shop_gene
WHERE ds = DATE_FORMAT(CURDATE(), '%Y%m%d')
  AND potential_score IS NOT NULL
```

**注意**: `potential_score` 字段名需确认实际列名，可能为 `score` 或 `predict_score`。

## 阶段时效统计（WF10）

按批次统计各里程碑时间点与耗时，供 R025-R028 时效告警使用。
阶段名（strategy_name）按链路实际配置替换占位符。

```sql
-- 活跃批次的阶段里程碑耗时
SELECT
  l.batch_id,
  MIN(l.gmt_create) AS batch_created,
  MIN(CASE WHEN l.strategy_name LIKE '{首图生成阶段名}%' AND l.status = 'SUCCESS' THEN l.gmt_modified END) AS first_img_gen_done,
  MIN(CASE WHEN l.strategy_name LIKE '{首图审核阶段名}%' AND l.node_type = 'approve' AND l.status = 'SUCCESS' THEN l.gmt_modified END) AS first_img_review_done,
  MAX(CASE WHEN l.strategy_name LIKE '{套图生成阶段名}%' AND l.status = 'SUCCESS' THEN l.gmt_modified END) AS suite_img_gen_done,
  MAX(CASE WHEN l.strategy_name LIKE '{套图审核阶段名}%' AND l.node_type = 'approve' AND l.status = 'SUCCESS' THEN l.gmt_modified END) AS suite_img_review_done,
  TIMESTAMPDIFF(HOUR, MIN(l.gmt_create), NOW()) AS total_elapsed_hours
FROM workflow_record_log l
WHERE l.id > 4000000 AND l.env = 'staging'
  AND l.batch_id IN ({active_batch_ids})
GROUP BY l.batch_id
```

判定：
- first_img_gen_done 为 NULL 且 total_elapsed_hours > T1 → R025
- first_img_review_done 为 NULL 且距 first_img_gen_done 超 T2 → R026
- suite_img_gen_done 为 NULL 且 total_elapsed_hours > T3 → R027
- suite_img_review_done 为 NULL 且 total_elapsed_hours > T4，或 total_elapsed_hours > 44 → R028

## 环节对账（WF11）

来源《F88链路数据对账方案 v2》（BT_7324 案例）。比较相邻环节"上游可用产出 vs 下游实际接收"。
注意：approve 节点同时承载首图审核与套图审核（nodeName 均为"人工审核"），须用 trace_id 关联上游节点区分。

```sql
-- 对账点4（关键，R029）：套图审核 → 内容上传
WITH approve_set AS (
  SELECT DISTINCT a.trace_id
  FROM workflow_record_log a
  INNER JOIN workflow_record_log b
    ON a.trace_id = b.trace_id
  WHERE a.batch_id = '{batch_id}' AND a.id > 4000000 AND a.env = 'staging'
    AND a.node_type = 'approve' AND a.status = 'SUCCESS'
    AND b.node_type = 'map_gen_img' AND b.status = 'SUCCESS'
),
upload_records AS (
  SELECT DISTINCT trace_id
  FROM workflow_record_log
  WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = 'staging'
    AND node_type = 'image_text_upload'
)
SELECT
  (SELECT COUNT(*) FROM approve_set) AS suite_approve_cnt,
  (SELECT COUNT(*) FROM upload_records) AS upload_cnt,
  (SELECT COUNT(*) FROM approve_set) - (SELECT COUNT(*) FROM upload_records) AS gap;
```

```sql
-- 对账点3（R031）：套图生成 → 套图审核覆盖
SELECT
  (SELECT COUNT(DISTINCT trace_id) FROM workflow_record_log
   WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = 'staging'
     AND node_type = 'map_gen_img' AND status = 'SUCCESS') AS map_gen_ok,
  (SELECT COUNT(*) FROM (
     SELECT DISTINCT a.trace_id FROM workflow_record_log a
     INNER JOIN workflow_record_log b ON a.trace_id = b.trace_id
     WHERE a.batch_id = '{batch_id}' AND a.id > 4000000 AND a.env = 'staging'
       AND a.node_type = 'approve' AND a.status = 'SUCCESS'
       AND b.node_type = 'map_gen_img' AND b.status = 'SUCCESS') t) AS suite_approve_ok;
```

```sql
-- 对账点5（R030）：内容上传失败率与原因分布
SELECT JSON_EXTRACT(extra_info, '$.errorMsg') AS error_msg, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = 'staging'
  AND node_type = 'image_text_upload' AND status = 'FAIL'
GROUP BY error_msg
ORDER BY cnt DESC;
```

```sql
-- 全量环节状态分布（对账总览，含参考对账点1/2）
SELECT node_type, status, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = 'staging'
GROUP BY node_type, status
ORDER BY node_type, status;
```

判定：
- 套图审核→上传 gap > 5% → R029 P1；> 20% → R029 P0（BT_7324 为 37.2%）
- 上传 FAIL 率 > 10% → R030 P1；> 20% → R030 P0
- 套图审核 SUCCESS < map_gen_img SUCCESS × 90% → R031 P1
- 参考对账点（template_match→industry_tag、llm_text→map_gen_img）非 1:1 关系，BT_7324 回溯验证为"预期内偏差"，默认跳过，待基线校准后再启用
