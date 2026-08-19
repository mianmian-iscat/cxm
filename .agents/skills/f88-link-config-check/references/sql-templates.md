# SQL 查询模板

所有查询仅 SELECT，禁止 INSERT/UPDATE/DELETE。

## 1. 链路基本信息

```sql
-- 查询单条链路
SELECT id, name, env, life_cycle, submitter_name, gmt_modified, struct 
FROM g_link 
WHERE id = {LINK_ID} AND is_deleted = 0;

-- 查询所有生产链路
SELECT id, name, env, life_cycle, submitter_name, gmt_modified 
FROM g_link 
WHERE env = 'prod' AND is_deleted = 0
ORDER BY gmt_modified DESC;

-- 按生命周期筛选
SELECT id, name, life_cycle, submitter_name, gmt_modified
FROM g_link
WHERE env = 'prod' AND is_deleted = 0 AND life_cycle = '{STATE}'
ORDER BY gmt_modified DESC;
```

## 2. 策略 workflow_def 批量查询

```sql
-- 按策略 ID 批量查询
SELECT id, name, workflow_def
FROM g_strategy
WHERE id IN ({STRATEGY_IDS});

-- 查询单条策略
SELECT id, name, workflow_def, gmt_modified, creator_name
FROM g_strategy
WHERE id = {STRATEGY_ID};

-- 按链路 ID 关联查询（从 struct 中提取 strategy ID 后用 IN 查）
-- 注意：g_strategy 没有 link_id 外键，必须先解析 g_link.struct JSON 提取 strategy IDs
```

## 3. 批次与实例查询

```sql
-- 查询链路最近的批次
SELECT id, chain_id, status, gmt_create, gmt_modified
FROM g_workflow_batch
WHERE chain_id = {LINK_ID}
ORDER BY gmt_create DESC
LIMIT 10;

-- 查询批次的实例进度
SELECT wi.id, wi.stage_id, wi.status, wi.node_type, wi.gmt_create, wi.gmt_modified
FROM g_workflow_instance wi
WHERE wi.batch_id = {BATCH_ID}
ORDER BY wi.stage_id, wi.gmt_create;

-- 聚合批次进度（按 node_type + status）
SELECT node_type, status, COUNT(*) AS cnt
FROM g_workflow_instance
WHERE batch_id = {BATCH_ID}
GROUP BY node_type, status;
```

## 4. 失败记录查询

```sql
-- 查询批次失败实例
SELECT id, stage_id, node_type, status, error_msg, gmt_modified
FROM g_workflow_instance
WHERE batch_id = {BATCH_ID} AND status = 'FAIL'
ORDER BY gmt_modified DESC;

-- 查询批次失败日志
SELECT id, node_type, status, error_msg, input_json, output_json, gmt_create
FROM workflow_record_log
WHERE batch_id = {BATCH_ID} AND status = 'FAIL' AND id > 4000000
ORDER BY gmt_create DESC
LIMIT 50;
```

## 5. template_match 节点配置提取

```sql
-- 从 workflow_def 提取 template_match 节点配置（JSON_EXTRACT 方式）
-- 注意：innerNodes 是 JSON 数组，需应用层解析
SELECT id, name,
  JSON_EXTRACT(workflow_def, '$.innerNodes') AS inner_nodes
FROM g_strategy
WHERE id IN ({STRATEGY_IDS})
  AND JSON_EXTRACT(workflow_def, '$.innerNodes') IS NOT NULL;
```

**应用层解析要点**（Python）：
- `innerNodes[i].nodeType == 'template_match'` → 提取 matchScene, targetMatchCount, mustMatchFields, templateMaxUseCount, templatePkgCondition
- `innerNodes[i].nodeType == 'gen_img'` → 提取 modelType, imageSize, outputRatio, outputModel
- `innerNodes[i].nodeType == 'approve'` → 提取 approveType
- `innerNodes[i].nodeType == 'image_text_upload'` → 提取 uploadType, imageList 绑定

## 6. 上传策略排查

```sql
-- 查询含上传节点的策略
SELECT id, name, workflow_def
FROM g_strategy
WHERE workflow_def LIKE '%image_text_upload%'
  AND id IN ({STRATEGY_IDS});

-- 验证上传策略的 imageList 绑定
-- 需从 workflow_def.innerNodes 中找 nodeType='image_text_upload' 的节点
-- 检查 imageList.dataSourceConfig.workflowInputParamCode 是否为 pic_urls_passN
```

## 7. 参数流转验证

```sql
-- 查询链路 struct 中所有阶段的 inputParams
-- 需从 g_link.struct 解析，无直接 SQL
-- 应用层遍历 stages[].inputParams[]，检查 dataSourceType：
--   STAGE_OUTPUT → 引用的 stageUid 和 fieldCode 是否存在
--   WORKFLOW_INPUT_PARAM → workflowInputParamCode 是否与策略对齐
```

## 8. 活跃度检查

```sql
-- 查链路最近跑批时间
SELECT l.id, l.name, l.life_cycle, MAX(wb.gmt_create) AS last_batch_time
FROM g_link l
LEFT JOIN g_workflow_batch wb ON wb.chain_id = l.id
WHERE l.env = 'prod' AND l.is_deleted = 0 AND l.life_cycle = 'mass_prod'
GROUP BY l.id, l.name, l.life_cycle
ORDER BY last_batch_time DESC;
```

## 9. 执行模式（execMode）查询（M/D8 检查用）

```sql
-- 查询链路关联批次的 execMode（M1）
SELECT id, batch_id, exec_mode, status, relation_id, gmt_create
FROM g_workflow_batch
WHERE relation_id = '{LINK_ID}'
ORDER BY gmt_create DESC
LIMIT 10;

-- 批次级跨表 URL 一致性扫描（D8/M3：BATCH 快照 vs STREAM 实时值）
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) != m.url THEN 1 ELSE 0 END) AS mismatch_count
FROM g_afd_review_job rj
JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE rj.relation_id LIKE '{BATCH_ID}_%'
  AND rj.job_type IN (1, 3);
```

**注意**：
- execMode 合法枚举：`BATCH`（读 `g_afd_review_job.info` 快照）/ `STREAM`（读 `g_afd_material.url` 实时值）
- mismatch_count > 0 且 execMode=BATCH → approve 可能读取过期 URL（BT_6148 类），转 f88-failure-analysis 工作流 9/10 深度归因
- 检查 COOP/COEP 响应头（F5）用 shell 而非 SQL：`curl -sI https://{pre-prod-domain}/ | grep -iE 'cross-origin-(opener|embedder)-policy'`

## 10. DMS CLI 调用格式

```bash
cd ~/dms-alibaba && bin/dms-alibaba sql query stylespot \
  --db rm-lgay0v5lor8396yka \
  --sql "SELECT ..."
```

**注意**：
- DMS 实例 ID: `rm-lgay0v5lor8396yka`
- 数据库别名: `stylespot`
- 所有查询只允许 SELECT
- 返回结果为 JSON 格式，大数据量时重定向到文件再解析
