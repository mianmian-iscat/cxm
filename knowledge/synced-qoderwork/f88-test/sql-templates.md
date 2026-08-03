<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88失败分析/references/sql-templates.md -->
<!-- synced-at: 2026-07-11T03:52:35.003323 -->
<!-- skill: F88失败分析 -->

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

根据实际错误模式调整 CASE WHEN 条件，以下为通用模板：

```sql
SELECT
  CASE
    WHEN JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%Error 404%'
      OR JSON_EXTRACT(a.extra_info, '$.errorMsg') LIKE '%was not found%'
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
