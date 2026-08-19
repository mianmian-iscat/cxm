# SQL 查询模板

所有查询通过 dms-alibaba CLI 执行，数据库参数：`stylespot --db rm-lgay0v5lor8396yka`。

**重要**：所有 `workflow_record_log` 查询必须加 `id > 4000000`（或更高的阈值）以防止超时。

## 状态分布查询

```sql
SELECT a.status, a.node_type, COUNT(*) AS cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}' AND a.id > 4000000
GROUP BY a.status, a.node_type
ORDER BY a.node_type, a.status
```

替换 `{batch_id}` 为实际批次 ID（如 BT_5441）。

## 错误信息样本提取

```sql
SELECT a.id, a.node_type,
       JSON_EXTRACT(a.extra_info, '$.errorMsg') AS error_msg,
       JSON_EXTRACT(a.extra_info, '$.strategyName') AS strategy_name
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.node_type = '{node_type}'
  AND a.id > 4000000
LIMIT 10
```

## 错误分类统计

根据实际错误模式调整 CASE WHEN 条件，以下为与 SKILL.md 工作流 2 错误目录同步的完整模板（含治理-1~5 签名）：

```sql
SELECT
  CASE
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Error 404%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%was not found on this server%'
      THEN 'API 404 (路径错误)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%upstream request failed%'
      THEN '上游服务请求失败'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%RESOURCE_EXHAUSTED%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%429%'
      THEN 'Quota 耗尽 (429)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Internal error%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%500%'
      THEN '模型内部错误 (500)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%算法返回结果为空%'
      THEN '算法返回空'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%unexpected end of stream%'
      THEN '流截断'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Cannot fetch content%'
      THEN 'URL 不可访问'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%算法处理失败%'
      THEN '算法处理失败'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%model was deprecated%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%model not found%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%模型已下线%'
      THEN '模型已下线 (核查 modelType)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%AccessDenied%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%SignatureDoesNotMatch%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%URL expired%'
      THEN 'CDN URL 签名过期'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%转存失败%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%图片下载失败, responseCode=403%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%taojimu.oss%'
      THEN '商详图转存 403 (淘积木 OSS 未走转存永久 CDN)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%callback timeout%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%排队超时%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%queue timeout%'
      THEN 'TPP 排队超时/回调丢失'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%JSON parse%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Unexpected character%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Unexpected token%'
      THEN 'JSON 解析失败 (非法字符)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%task not found%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%downstream missing%'
      THEN '下游任务丢失 (上游部分失败)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%SharedArrayBuffer%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Cross-Origin Isolated%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%COOP%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%COEP%'
      THEN 'SharedArrayBuffer/COOP 缺失 (BT_6149, 环境问题)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%subJobId%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%sub_job_id%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%trace lost%'
      THEN 'subJobId 未传递 (BT_5976)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%stale URL%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%旧 URL%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%review_job.info 未更新%'
      THEN 'replaceImage 跨表不一致 (BT_6148)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%mode mismatch%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%模式不一致%'
      THEN 'BATCH/STREAM 模式差异'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%F88_4%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%F88_5%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%额度已消耗完%'
      THEN '治理-1: ideaLAB 额度耗尽'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%was not found or your project does not have access%'
      THEN '治理-2: 模型不可用/无权限'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%PL-002%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%video generation任务已达到%'
      THEN '治理-4: Seedance 平台限流'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%URL_ERROR%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%ERROR_NOT_FOUND%'
      THEN '治理-5: 模板 URL 失效'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%FASTJSON%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%error, offset%'
      THEN 'LLM JSON 解析异常/格式漂移 (BT_7417)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%构建子任务失败%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%期望分配数量%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%与实际分配数量%'
      THEN '审核分配校验不一致卡 INIT (BT_7495)'
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%doCompleteMainTaskIfAllPersonalDone%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%审核完成不流转%'
      THEN '审核回调三条件缺失 (BT_7485)'
    ELSE CONCAT('其他: ', LEFT(JSON_EXTRACT(a.extra_info, '$.errorMsg'), 60))
  END AS error_type,
  COUNT(*) AS cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.node_type = '{node_type}'
  AND a.id > 4000000
GROUP BY error_type
ORDER BY cnt DESC
```

注意：治理-3（RESOURCE_EXHAUSTED）已被前面的 "Quota 耗尽 (429)" 分支覆盖，口径与 f88-clustering-service 治理打标一致。

## 获取 strategy_id

```sql
SELECT DISTINCT b.strategy_id, b.workflow_instance_id,
       JSON_EXTRACT(b.common_variable, '$.seller_id') AS seller_id
FROM workflow_record_log a
JOIN g_workflow_instance b ON a.workflow_instance_id = b.workflow_instance_id
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.node_type = '{node_type}'
  AND a.id > 4000000
LIMIT 10
```

注意：JOIN 可能导致超时，如果超时可先单独查 workflow_record_log 拿到 workflow_instance_id 列表，再单独查 g_workflow_instance。

## 策略配置提取

```sql
SELECT id, name,
       JSON_EXTRACT(workflow_def, '$.innerNodes[*].type') AS node_types,
       JSON_EXTRACT(workflow_def, '$.innerNodes[*].name') AS node_names,
       JSON_EXTRACT(workflow_def, '$.innerNodes[*].modelType') AS model_types
FROM g_strategy
WHERE id = {strategy_id}
```

提取完整节点配置（含 imageSize、outputRatio 等）：

```sql
SELECT id, name, workflow_def
FROM g_strategy
WHERE id = {strategy_id}
```

然后用 Python 解析完整 JSON：

```python
import json
# 从 dms-alibaba 结果文件读取
with open("{result_file_path}") as f:
    data = json.load(f)
for row in data.get("rows", []):
    wf = json.loads(row.get("workflow_def", "{}"))
    for node in wf.get("innerNodes", []):
        print(f"节点: {node.get('name')} | 类型: {node.get('type')} | 模型: {node.get('modelType')} | 尺寸: {node.get('imageSize')} | 比例: {node.get('outputRatio')}")
```

## 视频 URL 提取

```sql
SELECT a.id, a.gmt_create, a.batch_id,
       JSON_EXTRACT(a.extra_info, '$.strategyName') AS strategy_name,
       JSON_EXTRACT(a.output_json, '$.outputVideo') AS output_video
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.node_type = 'gen_video'
  AND a.status = 'SUCCESS'
  AND a.id > 4000000
ORDER BY a.id DESC
```

## 策略维度分析

```sql
SELECT JSON_EXTRACT(a.extra_info, '$.strategyName') AS strategy_name,
       COUNT(*) AS cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.node_type = '{node_type}'
  AND a.id > 4000000
GROUP BY JSON_EXTRACT(a.extra_info, '$.strategyName')
ORDER BY cnt DESC
```

## 时间维度分析

```sql
SELECT MIN(a.gmt_create) AS earliest,
       MAX(a.gmt_create) AS latest,
       COUNT(*) AS total
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.node_type = '{node_type}'
  AND a.id > 4000000
```

## 批次 execMode 查询

查询批次关联的执行模式配置（BATCH / STREAM）：

```sql
SELECT a.batch_id,
       JSON_EXTRACT(c.common_variable, '$.execMode') AS exec_mode,
       b.strategy_id,
       b.workflow_instance_id
FROM workflow_record_log a
JOIN g_workflow_instance b ON a.workflow_instance_id = b.workflow_instance_id
LEFT JOIN g_workflow_instance c ON c.workflow_instance_id = b.workflow_instance_id
WHERE a.batch_id = '{batch_id}'
  AND a.id > 4000000
LIMIT 5
```

如果 execMode 不在 common_variable 中，需从 g_strategy.extra_info 或链路配置中获取。

## BATCH vs STREAM URL 对比

对同一 workflow_instance，分别提取 BATCH 模式读取的快照 URL 和 STREAM 模式读取的实时 URL：

```sql
SELECT rj.id AS review_job_id,
       rj.workflow_instance_id,
       JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') AS snapshot_url,
       m.id AS material_id,
       m.url AS current_url,
       rj.gmt_create AS review_job_created,
       m.gmt_modified AS material_modified
FROM g_afd_review_job rj
LEFT JOIN g_afd_material m ON rj.workflow_instance_id = m.workflow_instance_id
WHERE rj.workflow_instance_id = '{workflow_instance_id}'
```

如果 `snapshot_url != current_url` → replaceImage 未回写 review_job.info（BT_6148 类问题）。

## material 操作记录查询

查询指定 workflow_instance 的素材操作历史：

```sql
SELECT m.id,
       m.url,
       m.material_type,
       m.operation_type,
       m.sub_job_id,
       m.gmt_create,
       m.gmt_modified,
       JSON_EXTRACT(m.extra_info, '$.operationDetail') AS operation_detail
FROM g_afd_material m
WHERE m.workflow_instance_id = '{workflow_instance_id}'
ORDER BY m.gmt_modified DESC
```

重点关注：是否存在 `operation_type = 'replaceImage'` 的记录，以及其 `gmt_modified` 是否晚于 `g_afd_review_job.gmt_create`。

## subJobId 传递检查

检查素材操作是否传递了 subJobId：

```sql
SELECT m.operation_type,
       COUNT(*) AS total,
       SUM(CASE WHEN m.sub_job_id IS NOT NULL AND m.sub_job_id != '' THEN 1 ELSE 0 END) AS has_sub_job_id,
       SUM(CASE WHEN m.sub_job_id IS NULL OR m.sub_job_id = '' THEN 1 ELSE 0 END) AS missing_sub_job_id
FROM g_afd_material m
WHERE m.workflow_instance_id IN (
    SELECT a.workflow_instance_id
    FROM workflow_record_log a
    WHERE a.batch_id = '{batch_id}' AND a.id > 4000000
)
GROUP BY m.operation_type
ORDER BY total DESC
```

如果某类操作 `missing_sub_job_id` 占比接近 100% → 链路追踪断裂（BT_5976 类问题）。

## 跨表 URL 一致性检查

对指定 workflow_instance 检查 g_afd_material.url 与 g_afd_review_job.info 快照中的 URL 是否一致：

```sql
SELECT rj.id AS review_job_id,
       rj.workflow_instance_id,
       JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') AS review_job_url,
       m.url AS material_url,
       CASE
           WHEN JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') = m.url THEN 'CONSISTENT'
           ELSE 'MISMATCH'
       END AS consistency,
       rj.gmt_create AS review_job_created,
       m.gmt_modified AS material_modified,
       TIMESTAMPDIFF(SECOND, rj.gmt_create, m.gmt_modified) AS time_diff_seconds
FROM g_afd_review_job rj
JOIN g_afd_material m ON rj.workflow_instance_id = m.workflow_instance_id
WHERE rj.workflow_instance_id = '{workflow_instance_id}'
```

`MISMATCH` 且 `time_diff_seconds > 0` → 素材在审核任务创建后被更新，快照未同步。

## 批量跨表一致性扫描

对整个批次做跨表一致性扫描：

```sql
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') != m.url THEN 1 ELSE 0 END) AS mismatch_count,
    SUM(CASE WHEN JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') = m.url THEN 1 ELSE 0 END) AS consistent_count
FROM g_afd_review_job rj
JOIN g_afd_material m ON rj.workflow_instance_id = m.workflow_instance_id
WHERE rj.workflow_instance_id IN (
    SELECT a.workflow_instance_id
    FROM workflow_record_log a
    WHERE a.batch_id = '{batch_id}' AND a.id > 4000000
)
```

如果 `mismatch_count / total > 0` → 存在系统性回写缺失。

## 不一致时间窗口分析

分析不一致记录的时间分布，定位 replaceImage 操作发生的时间窗口：

```sql
SELECT rj.id AS review_job_id,
       rj.workflow_instance_id,
       JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') AS review_job_url,
       m.url AS material_url,
       rj.gmt_create AS review_job_created,
       m.gmt_modified AS material_modified,
       TIMESTAMPDIFF(SECOND, rj.gmt_create, m.gmt_modified) AS lag_seconds
FROM g_afd_review_job rj
JOIN g_afd_material m ON rj.workflow_instance_id = m.workflow_instance_id
WHERE rj.workflow_instance_id IN (
    SELECT a.workflow_instance_id
    FROM workflow_record_log a
    WHERE a.batch_id = '{batch_id}' AND a.id > 4000000
)
AND JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl') != m.url
ORDER BY m.gmt_modified ASC
```

`lag_seconds > 0` → 素材在审核任务创建后被更新。集中时间段 → 批量 replaceImage 操作导致。

## 素材操作 subJobId 覆盖率

按操作类型统计 subJobId 的传递率：

```sql
SELECT m.operation_type,
       COUNT(*) AS total_ops,
       SUM(CASE WHEN m.sub_job_id IS NOT NULL AND m.sub_job_id != '' THEN 1 ELSE 0 END) AS with_sub_job_id,
       SUM(CASE WHEN m.sub_job_id IS NULL OR m.sub_job_id = '' THEN 1 ELSE 0 END) AS without_sub_job_id,
       ROUND(SUM(CASE WHEN m.sub_job_id IS NOT NULL AND m.sub_job_id != '' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS coverage_pct
FROM g_afd_material m
WHERE m.workflow_instance_id IN (
    SELECT a.workflow_instance_id
    FROM workflow_record_log a
    WHERE a.batch_id = '{batch_id}' AND a.id > 4000000
)
GROUP BY m.operation_type
ORDER BY total_ops DESC
```

`coverage_pct` 为 0 的操作类型 → 该操作的链路追踪完全断裂，需修复参数传递。

## 批次实际执行策略

查询批次中实际触发过的 node_type 与策略（工作流 6 第 1 步）：

```sql
SELECT a.node_type,
       JSON_UNQUOTE(JSON_EXTRACT(a.extra_info, '$.strategyName')) AS strategy_name,
       COUNT(*) AS cnt,
       MIN(a.gmt_create) AS first_seen,
       MAX(a.gmt_create) AS last_seen
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.id > 4000000
GROUP BY a.node_type, strategy_name
ORDER BY first_seen
```

整理出该批次实际触发了哪些阶段，与链路配置的完整阶段列表对比，找出"配置了但未触发"的阶段。

## 策略存在性检查

验证链路配置中引用的策略是否存在于 g_strategy（工作流 6 第 2 步浏览器不可用时的兜底）：

```sql
SELECT id, name, gmt_modified
FROM g_strategy
WHERE id IN ({strategy_ids})
```

配置引用了但查询不到的策略 ID → 链路配置错误（策略已删除或 ID 填错）。

## 出参完整性检查

检查未触发阶段的前一阶段 strategy 节点 output_json 是否缺失关键出参（工作流 6 第 4 步）：

```sql
SELECT a.id, a.workflow_instance_id, a.node_type, a.status,
       LEFT(a.output_json, 800) AS output_json
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.node_type IN ('strategy', 'approve')
  AND a.id > 4000000
ORDER BY a.id DESC
LIMIT 20
```

用 Python 解析结果文件，重点检查：
- approve 节点 `passedImg` 是否为 `[null, null]`（出参丢失）
- 前一阶段 strategy 输出是否包含后阶段所需入参
- 字段名是否匹配（如 `main_img_url` vs `mainImgUrl`）

## URL 提取

从失败记录中提取素材 URL 用于有效性检测（工作流 7 第 1 步）：

```sql
SELECT a.id,
       JSON_UNQUOTE(JSON_EXTRACT(a.extra_info, '$.mainImgUrl')) AS main_img_url,
       JSON_UNQUOTE(JSON_EXTRACT(a.extra_info, '$.imageUrl')) AS image_url,
       JSON_UNQUOTE(JSON_EXTRACT(a.output_json, '$.outputVideo')) AS output_video,
       JSON_UNQUOTE(JSON_EXTRACT(a.output_json, '$.passedImg')) AS passed_img
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.id > 4000000
LIMIT 50
```

视具体节点类型选取对应字段；提取后用 curl 批量检测 HTTP 状态码（200/403/404/000）。

## 数据源时间对比

对比 URL 签名时间与记录创建时间，判断入队时 URL 是否已接近过期（工作流 7 第 4 步）：

```sql
SELECT a.id, a.gmt_create,
       JSON_UNQUOTE(JSON_EXTRACT(a.extra_info, '$.imageUrl')) AS url_with_sign
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.id > 4000000
LIMIT 20
```

用 Python 从 URL 的 `Expires`/`OSSAccessKeyId` 等参数解析签名时间，与 `gmt_create` 对比：
gmt_create 远晚于签名时间 → 数据源在入队列时 URL 已接近过期。

## 阶段任务数统计

按 node_type 统计各阶段任务总数，对比是否存在任务丢失（工作流 8 第 1 步）：

```sql
SELECT a.node_type,
       COUNT(*) AS total,
       SUM(a.status = 'SUCCESS') AS success_cnt,
       SUM(a.status = 'FAIL') AS fail_cnt,
       SUM(a.status = 'HANDLING') AS handling_cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.id > 4000000
GROUP BY a.node_type
ORDER BY MIN(a.id)
```

下游阶段任务数明显少于上游 → 存在任务丢失，进入"任务丢失追踪"定位具体实例。

## 任务丢失追踪

找出"上游有记录但下游完全无记录"的 workflow_instance（工作流 8 第 2 步）：

```sql
SELECT up.workflow_instance_id,
       up.status AS upstream_status,
       JSON_UNQUOTE(JSON_EXTRACT(up.extra_info, '$.errorMsg')) AS upstream_error
FROM workflow_record_log up
WHERE up.batch_id = '{batch_id}'
  AND up.node_type = '{upstream_node}'
  AND up.id > 4000000
  AND up.workflow_instance_id NOT IN (
      SELECT dn.workflow_instance_id
      FROM workflow_record_log dn
      WHERE dn.batch_id = '{batch_id}'
        AND dn.node_type = '{downstream_node}'
        AND dn.id > 4000000
  )
LIMIT 50
```

上游 FAIL → 部分失败阻断下游（确认是否预期行为）；上游 SUCCESS 但下游无记录 → 流转逻辑 bug；上游 HANDLING → 任务卡住。

## TPP 回调检查

对比 gen_img 节点发起的 TPP 任务数与收到回调的数量（工作流 8 第 5 步）：

```sql
SELECT a.status, COUNT(*) AS cnt
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.node_type = 'gen_img'
  AND a.id > 4000000
GROUP BY a.status
```

```sql
SELECT t.task_status, COUNT(*) AS cnt,
       MIN(t.gmt_create) AS earliest, MAX(t.gmt_create) AS latest
FROM g_admin_task t
WHERE t.job_id IN (
    SELECT a.id FROM workflow_record_log a
    WHERE a.batch_id = '{batch_id}'
      AND a.node_type = 'gen_img'
      AND a.id > 4000000
)
GROUP BY t.task_status
```

HANDLING 记录数 > task_status 非终态数 → 存在回调丢失（task_status=10 且 gmt_modified=gmt_create 表示 TPP 从未回调），任务永远停在 HANDLING。

## SharedArrayBuffer 错误统计

统计批次中跨域隔离相关失败（工作流 11 第 1 步）：

```sql
SELECT a.node_type,
       COUNT(*) AS cnt,
       MIN(a.gmt_create) AS first_seen,
       MAX(a.gmt_create) AS last_seen
FROM workflow_record_log a
WHERE a.batch_id = '{batch_id}'
  AND a.status = 'FAIL'
  AND a.id > 4000000
  AND (JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%SharedArrayBuffer%'
    OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Cross-Origin Isolated%'
    OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%COOP%'
    OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%COEP%'
    OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%FFmpeg 引擎加载失败%')
GROUP BY a.node_type
```

有命中 → 按工作流 11 后续步骤用 curl 检查预发/生产响应头差异（关联 Bug：BT_6149）。
