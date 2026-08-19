# F88 高频 SQL 模板库

> 执行方式见 SKILL.md（sql query ≤200 行 / sql run >200 行）。所有模板占位符：`{batch_id}`（BT_xxxx）、`{node_type}`、`{strategy_id}`、`{id_threshold}` 等。
> `{id_threshold}` 须通过 `python3 ~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py --days 7` 动态获取，模板中统一写为 `id >= {id_threshold}`；workflow_record_log 查询建议统一补 `env='staging'`。

## A. 批次状态 / 总览

### T-01 状态分布（node_type × status）— 最高频

```sql
SELECT node_type, status, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
GROUP BY node_type, status
ORDER BY node_type, status
```

### T-02 批次链路总览（走到哪个节点）

```sql
SELECT id, node_type, stage_type, status, gmt_modified, LEFT(output_json, 500) AS output_json
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id >= {id_threshold}
ORDER BY id DESC LIMIT 20
```

### T-03 批次元信息

```sql
SELECT batch_id, status, exec_mode, source_type
FROM g_workflow_batch
WHERE batch_id = '{batch_id}' AND env = 'staging'
```

按链路反查批次：`SELECT id, exec_mode, relation_id FROM g_workflow_batch WHERE relation_id = '{link_id}'`

### T-04 阶段任务数统计（检测任务丢失）

```sql
SELECT node_type, COUNT(*) AS total,
       SUM(status = 'SUCCESS') AS success_cnt,
       SUM(status = 'FAIL') AS fail_cnt,
       SUM(status = 'HANDLING') AS handling_cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id >= {id_threshold}
GROUP BY node_type ORDER BY MIN(id)
```

## B. 失败数据 / 错误分类

### T-05 错误信息样本

```sql
SELECT id, node_type,
       JSON_EXTRACT(extra_info, '$.errorMsg') AS error_msg,
       JSON_EXTRACT(extra_info, '$.strategyName') AS strategy_name
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND status = 'FAIL'
  AND node_type = '{node_type}' AND id >= {id_threshold}
LIMIT 10
```

### T-06 错误分类统计（CASE WHEN 签名分组）

```sql
SELECT CASE
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%Error 404%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%was not found on this server%' THEN 'API 404 (路径错误)'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%upstream request failed%' THEN '上游服务请求失败'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%RESOURCE_EXHAUSTED%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%429%' THEN 'Quota 耗尽 (429)'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%Internal error%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%500%' THEN '模型内部错误 (500)'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%算法返回结果为空%' THEN '算法返回空'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%unexpected end of stream%' THEN '流截断'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%Cannot fetch content%' THEN 'URL 不可访问'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%算法处理失败%' THEN '算法处理失败'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%model was deprecated%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%model not found%' THEN '模型已下线'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%AccessDenied%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%URL expired%' THEN 'CDN URL 签名过期'
  WHEN JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%SharedArrayBuffer%'
    OR JSON_EXTRACT(extra_info,'$.errorMsg') LIKE '%COOP%' THEN 'SharedArrayBuffer/COOP 缺失'
  ELSE CONCAT('其他: ', LEFT(JSON_EXTRACT(extra_info,'$.errorMsg'), 60))
END AS error_type, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND status = 'FAIL'
  AND node_type = '{node_type}' AND id >= {id_threshold}
GROUP BY error_type ORDER BY cnt DESC
```

完整 22 分支版（含治理-1~5 签名：ideaLAB 额度耗尽/模型无权限/Seedance 限流 PL-002/模板 URL 失效 URL_ERROR）见 `f88-failure-analysis/references/sql-templates.md`；签名库唯一归属 `F88测试知识库/references/patterns/error-signatures.md`。

### T-07 策略维度 / 时间维度

```sql
SELECT JSON_EXTRACT(extra_info,'$.strategyName') AS strategy_name, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id='{batch_id}' AND status='FAIL' AND node_type='{node_type}' AND id>= {id_threshold}
GROUP BY JSON_EXTRACT(extra_info,'$.strategyName') ORDER BY cnt DESC;

SELECT MIN(gmt_create) AS earliest, MAX(gmt_create) AS latest, COUNT(*) AS total
FROM workflow_record_log
WHERE batch_id='{batch_id}' AND status='FAIL' AND node_type='{node_type}' AND id>= {id_threshold}
```

## C. 节点流转 / 任务丢失

### T-08 任务丢失追踪（上游有、下游无）

```sql
SELECT up.workflow_instance_id, up.status AS upstream_status,
       JSON_UNQUOTE(JSON_EXTRACT(up.extra_info,'$.errorMsg')) AS upstream_error
FROM workflow_record_log up
WHERE up.batch_id='{batch_id}' AND up.node_type='{upstream_node}' AND up.id>= {id_threshold}
  AND up.workflow_instance_id NOT IN (
    SELECT dn.workflow_instance_id FROM workflow_record_log dn
    WHERE dn.batch_id='{batch_id}' AND dn.node_type='{downstream_node}' AND dn.id>= {id_threshold})
LIMIT 50
```

### T-09 trace 断裂检测

```sql
SELECT a.trace_id, a.node_type AS stuck_node
FROM workflow_record_log a
LEFT JOIN workflow_record_log b ON a.trace_id = b.trace_id
  AND b.node_type = '{expected_next_node}' AND b.id >= {id_threshold}
WHERE a.batch_id='{batch_id}' AND a.id>= {id_threshold} AND a.env='staging'
  AND a.status='SUCCESS' AND a.node_type='{current_node}' AND b.id IS NULL
LIMIT 20
```

### T-10 TPP 回调检查（g_admin_task）

```sql
SELECT t.task_status, COUNT(*) AS cnt,
       MIN(t.gmt_create) AS earliest, MAX(t.gmt_create) AS latest
FROM g_admin_task t
WHERE t.job_id IN (
  SELECT a.id FROM workflow_record_log a
  WHERE a.batch_id='{batch_id}' AND a.node_type='gen_img' AND a.id>= {id_threshold})
GROUP BY t.task_status
```

判读：task_status=10 且 gmt_modified=gmt_create → TPP 从未回调（记录永远 HANDLING）。

## D. 策略 / 链路配置

### T-11 日志反查 strategy_id

```sql
SELECT DISTINCT b.strategy_id, b.workflow_instance_id,
       JSON_EXTRACT(b.common_variable,'$.seller_id') AS seller_id
FROM workflow_record_log a
JOIN g_workflow_instance b ON a.workflow_instance_id = b.workflow_instance_id
WHERE a.batch_id='{batch_id}' AND a.status='FAIL' AND a.node_type='{node_type}' AND a.id>= {id_threshold}
LIMIT 10
```

JOIN 超时时拆两步：先单查 workflow_record_log 拿 workflow_instance_id 列表，再单查 g_workflow_instance。

### T-12 策略配置提取

```sql
SELECT id, name, workflow_def FROM g_strategy WHERE id = {strategy_id}
```

应用层解析 `workflow_def.innerNodes[]`：UId/name/type/modelType/imageSize/outputRatio/outputModel。注意 g_strategy 主键是 `id` 不是 strategy_id。

### T-13 链路查询（g_link）

```sql
SELECT id, name, env, life_cycle, submitter_name, gmt_modified, struct
FROM g_link WHERE id = {link_id} AND is_deleted = 0
```

g_strategy 没有 link_id 外键：必须先解析 g_link.struct JSON 提取 strategy IDs，再查 T-12。

## E. 审核任务三层结构

### T-14 审核任务层级（job_type × job_status）

```sql
SELECT job_type, job_status, COUNT(*) AS cnt
FROM g_afd_review_job
WHERE relation_id LIKE '{batch_id}_%'
GROUP BY job_type, job_status ORDER BY job_type, job_status
```

判读：job_type 0=主/1=子审核/3=抽检子/4=主审核/5=抽检主；job_status 1=待处理/4=处理中/5=已完成。只要有 job_type=3 或 5 且 status=1，approve 就一定在等抽检，不是卡死。

## F. 素材 URL / 跨表一致性

### T-15 跨表一致性（review_job 快照 vs material 实时 URL）

```sql
SELECT COUNT(*) AS total,
  SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info,'$.videoUrlReview.videoUrl')) != m.url
      THEN 1 ELSE 0 END) AS mismatch_cnt
FROM g_afd_review_job rj
JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info,'$.afdMid')) = m.afd_mid
WHERE rj.relation_id LIKE '{batch_id}_%' AND rj.job_type IN (1, 3)
```

判读：mismatch>0 且 execMode=BATCH → approve 读旧 URL（参考 BT_6148）；STREAM 下快照不一致不影响 approve。备选 JOIN 键：`rj.workflow_instance_id = m.workflow_instance_id`。

### T-16 subJobId 覆盖率审计

```sql
SELECT operation_type, COUNT(*) AS total,
       SUM(CASE WHEN sub_job_id IS NOT NULL AND sub_job_id!='' THEN 1 ELSE 0 END) AS with_subjobid,
       ROUND(SUM(CASE WHEN sub_job_id IS NOT NULL AND sub_job_id!='' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS coverage_pct
FROM g_afd_material
WHERE workflow_instance_id IN (
  SELECT workflow_instance_id FROM workflow_record_log
  WHERE batch_id='{batch_id}' AND id>= {id_threshold})
GROUP BY operation_type
```

## G. 其他常用

### T-17 URL 提取（有效性检测前置）

```sql
SELECT id,
  JSON_UNQUOTE(JSON_EXTRACT(extra_info,'$.mainImgUrl')) AS main_img_url,
  JSON_UNQUOTE(JSON_EXTRACT(extra_info,'$.imageUrl')) AS image_url,
  JSON_UNQUOTE(JSON_EXTRACT(output_json,'$.outputVideo')) AS output_video,
  JSON_UNQUOTE(JSON_EXTRACT(output_json,'$.passedImg')) AS passed_img
FROM workflow_record_log
WHERE batch_id='{batch_id}' AND status='FAIL' AND id>= {id_threshold} LIMIT 50
```

### T-18 种草发布失败原因

```sql
SELECT biz_scene, JSON_EXTRACT(ext_info,'$.publishFailReason') AS fail_reason, COUNT(*)
FROM g_afd_recommend_material_pool_record
WHERE seller_id='{seller_id}' AND status=7
GROUP BY biz_scene, fail_reason
```

### T-19 商品关联批次

```sql
SELECT batch_id, source_type, dispatch_status
FROM g_afd_material_prod_record
WHERE item_id='{item_id}' AND env='staging'
ORDER BY id DESC LIMIT 20
```

### T-20 表结构自检

```sql
DESC workflow_record_log;
DESC g_afd_review_job;
DESC g_afd_material;
```

## H. 评测体系增强

### T-21 批次 Trace 查询（执行轨迹树）

```sql
-- 输入 batch_id，输出完整执行轨迹（按时间排序的节点序列）
SELECT 
  wrl.id,
  wrl.node_type,
  wrl.stage_type,
  wrl.status,
  wrl.gmt_create,
  wrl.gmt_modified,
  TIMESTAMPDIFF(SECOND, wrl.gmt_create, wrl.gmt_modified) AS duration_sec,
  LEFT(JSON_EXTRACT(wrl.extra_info, '$.errorMsg'), 200) AS error_msg,
  LEFT(wrl.output_json, 300) AS output_summary
FROM workflow_record_log wrl
WHERE wrl.batch_id = '{batch_id}' 
  AND wrl.id >= {id_threshold}
  AND wrl.env = 'staging'
ORDER BY wrl.id ASC
```

用途：生成批次执行轨迹树，标注每个节点的耗时、状态、输入输出摘要。用于可观测性增强（改造四）。

### T-22 批次轨迹效率分析

```sql
-- 输入 batch_id，输出每个节点的执行次数、平均耗时、失败次数，用于计算收敛度分数
SELECT 
  node_type,
  COUNT(*) AS exec_count,
  AVG(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)) AS avg_duration_sec,
  MAX(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)) AS max_duration_sec,
  SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_count,
  SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
  MIN(gmt_create) AS first_exec,
  MAX(gmt_modified) AS last_exec
FROM workflow_record_log
WHERE batch_id = '{batch_id}' 
  AND id >= {id_threshold}
  AND env = 'staging'
GROUP BY node_type
ORDER BY MIN(id)
```

用途：计算批次收敛度分数（最优步数/实际步数）、重试率、性能瓶颈节点。用于轨迹评估（改造五）。
