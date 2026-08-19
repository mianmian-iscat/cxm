# 审核节点替换验证 SQL 详细手册

> 本文件包含 Step 1~8 的完整 SQL 步骤、修复验证工作流、已知问题模式。
>
> `{id_threshold}` 通过 `~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py` 动态获取，禁止硬编码 4000000/6400000。

## Step 1：查批次链路总览

```sql
SELECT id, node_type, stage_type, status, gmt_modified,
       LEFT(output_json, 500) AS output_json
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
ORDER BY id DESC
LIMIT 20
```

看链路走到了哪个节点，重点关注 approve 是 HANDLING 还是 SUCCESS。

## Step 2：拉 approve + 下游 gen_video 的完整 JSON

```sql
SELECT id, node_type, status, output_json, input_json
FROM workflow_record_log
WHERE id IN ({approve_id}, {downstream_gen_id})
```

用 Python 解析 JSON 结果文件（避免终端截断）：

```python
import json
with open('/Users/caoxuemei/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{DATE}/{TIME}_rm-lgay0v5lor8396yka.json') as f:
    d = json.load(f)
rows = d.get('rows') or d.get('data', {}).get('rows') or []
for r in rows:
    print('===', r.get('id'), r.get('node_type'), r.get('status'), '===')
    for k in ['output_json', 'input_json', 'extra_info']:
        v = r.get(k)
        if v:
            print(f'--- {k}:')
            print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
```

## Step 3：判断 bug 是否复现（一锤定音）

**视频链路（passedImg 字段名，type 是 mp4）**：
```
approve.input_json.imgUrlReview        # 快照，允许是老 seedance URL
approve.output_json.passedImg          # 关键：应该是替换后的 localUpload URL
下游 gen_video.input_json.inputImgs    # 应该 = approve.output.passedImg
```

**图片链路（passedImg 是数组）**：
```
approve.input_json.imgUrlReviewList0   # 快照，允许是原始 alicdn URL
approve.output_json.passedImg          # 数组，应该是替换后的 localUpload URL
下游 gen_video.input_json.inputImgList0 # 数组，应该 = approve.output.passedImg
```

**判定**：approve.output.passedImg = localUpload URL 且下游 input = 同一 localUpload URL → **修复生效**。反之 = bug 复现。

## Step 4：审核任务层级（approve 卡 HANDLING 时诊断）

```sql
SELECT id, job_type, job_status, parent_job_id, relation_id, gmt_modified
FROM g_afd_review_job
WHERE id IN ({main_id}, {sub_ids...})
```

或按 relation_id 反查：

```sql
SELECT id, job_type, job_status, parent_job_id, relation_id
FROM g_afd_review_job
WHERE relation_id = '{approve_workflow_record_id}' OR relation_id LIKE '{batch_id}_%'
```

只要有 job_type=3 或 5（抽检类）status=1（待处理），approve 就一定卡住。

## Step 5：review_job.info 快照 vs g_afd_material.url + execMode 上下文

```sql
-- 5a. 确认批次 execMode
SELECT id, name, exec_mode, gmt_create
FROM g_workflow_batch
WHERE batch_id = '{batch_id}'
```

execMode=BATCH → 快照与 material 不一致 = approve 拿老 URL（bug 必现）。
execMode=STREAM → 快照不一致不影响 approve。

```sql
-- 5b. 拉 review_job 快照里的 URL
SELECT id, LEFT(info, 2000) AS info
FROM g_afd_review_job
WHERE id = {sub_review_job_id}
```

info 里 `videoAuditContent.videoUrlReview.videoUrl` 是快照值。

```sql
-- 5c. 拉 material 表最新 URL
SELECT id, afd_mid, url, gmt_modified
FROM g_afd_material
WHERE afd_mid = '{afdMid}'
ORDER BY gmt_modified DESC LIMIT 5
```

## Step 6：批次级跨表一致性扫描

```sql
-- 6a. 批量扫描：review_job 快照 URL vs material 当前 URL
SELECT
  rj.id AS review_job_id, rj.relation_id,
  JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) AS snapshot_url,
  m.url AS material_url, m.gmt_modified AS material_modified,
  rj.gmt_create AS review_job_created,
  CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) = m.url
    THEN 'CONSISTENT' ELSE 'MISMATCH' END AS consistency
FROM g_afd_review_job rj
JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE rj.relation_id LIKE '{batch_id}_%' AND rj.job_type IN (1, 3)
ORDER BY rj.gmt_create DESC LIMIT 100
```

```sql
-- 6b. 统计不一致数量和占比
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) != m.url THEN 1 ELSE 0 END) AS mismatch_cnt,
  ROUND(SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) != m.url THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS mismatch_pct
FROM g_afd_review_job rj
JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE rj.relation_id LIKE '{batch_id}_%' AND rj.job_type IN (1, 3)
```

## Step 7：subJobId 覆盖率审计

```sql
-- 7a. 按操作类型统计 subJobId 传递率
SELECT
  operation_type, COUNT(*) AS total,
  SUM(CASE WHEN sub_job_id IS NOT NULL AND sub_job_id != '' THEN 1 ELSE 0 END) AS with_subjobid,
  SUM(CASE WHEN sub_job_id IS NULL OR sub_job_id = '' THEN 1 ELSE 0 END) AS without_subjobid,
  ROUND(SUM(CASE WHEN sub_job_id IS NOT NULL AND sub_job_id != '' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS coverage_pct
FROM g_afd_material
WHERE workflow_instance_id IN (
  SELECT workflow_instance_id FROM workflow_record_log
  WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
)
GROUP BY operation_type
```

```sql
-- 7b. 查看缺失 subJobId 的具体记录
SELECT id, afd_mid, operation_type, sub_job_id, url, gmt_modified
FROM g_afd_material
WHERE (sub_job_id IS NULL OR sub_job_id = '')
  AND workflow_instance_id IN (
    SELECT workflow_instance_id FROM workflow_record_log
    WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
  )
ORDER BY gmt_modified DESC LIMIT 20
```

## Step 8：replaceImage 后快照校验

> 专门验证 `replaceImage` 操作发生后，`g_afd_review_job.info` 中的快照 URL 是否随 `g_afd_material.url` 一起更新。BT_6148 的根因是 replaceImage 只更新了 material 表，未回写 review_job.info，导致 BATCH 模式下 approve 仍拿老 URL。

### 8a. 定位批次内发生过 replaceImage 的素材

```sql
SELECT
  m.id AS material_id,
  m.afd_mid,
  m.operation_type,
  m.url AS material_url_after_replace,
  m.sub_job_id,
  m.workflow_instance_id,
  m.gmt_modified AS material_modified
FROM g_afd_material m
WHERE m.operation_type = 'replaceImage'
  AND m.workflow_instance_id IN (
    SELECT workflow_instance_id FROM workflow_record_log
    WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
  )
ORDER BY m.gmt_modified DESC
LIMIT 50
```

### 8b. 逐条对比 replaceImage 后的快照与当前 material URL

```sql
SELECT
  m.id AS material_id,
  m.afd_mid,
  m.url AS material_url,
  rj.id AS review_job_id,
  rj.job_type,
  rj.job_status,
  JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) AS snapshot_video_url,
  JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoAuditContent.videoUrlReview.videoUrl')) AS snapshot_video_audit_url,
  JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.imageUrlReviewList[0]')) AS snapshot_image_url,
  m.gmt_modified AS material_modified,
  rj.gmt_modified AS snapshot_modified,
  CASE
    WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoAuditContent.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.imageUrlReviewList[0]')) = m.url
    THEN 'CONSISTENT'
    ELSE 'MISMATCH'
  END AS consistency
FROM g_afd_material m
LEFT JOIN g_afd_review_job rj
  ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE m.operation_type = 'replaceImage'
  AND m.workflow_instance_id IN (
    SELECT workflow_instance_id FROM workflow_record_log
    WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
  )
ORDER BY m.gmt_modified DESC
LIMIT 50
```

### 8c. 统计 replaceImage 后快照未更新的数量与占比

```sql
SELECT
  COUNT(*) AS total_replace,
  SUM(CASE
    WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoAuditContent.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.imageUrlReviewList[0]')) = m.url
    THEN 0 ELSE 1
  END) AS stale_snapshot_cnt,
  ROUND(SUM(CASE
    WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoAuditContent.videoUrlReview.videoUrl')) = m.url
      OR JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.imageUrlReviewList[0]')) = m.url
    THEN 0 ELSE 1
  END) / COUNT(*) * 100, 1) AS stale_pct
FROM g_afd_material m
LEFT JOIN g_afd_review_job rj
  ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
WHERE m.operation_type = 'replaceImage'
  AND m.workflow_instance_id IN (
    SELECT workflow_instance_id FROM workflow_record_log
    WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging'
  )
```

### 判定规则

| exec_mode | 快照与 material 一致 | 结论 |
|-----------|---------------------|------|
| BATCH | 一致 | ✅ replaceImage 回写正确 |
| BATCH | 不一致 | ❌ BT_6148 复现，approve 可能拿老 URL |
| STREAM | 不一致 | ⚠️ 不影响 approve，但建议记录 |

> 注意：先执行 Step 5a 确认 `exec_mode`。BATCH 模式下任何 `stale_snapshot_cnt > 0` 都应视为修复未生效。

---

## 修复验证工作流

### 验证 replaceImage 回写修复（BT_6148）

```
1. 对修复后的批次重新执行 Step 5b/5c
2. 确认 g_afd_review_job.info 中的 videoUrl 与 g_afd_material.url 一致
3. 重新执行 Step 6b，确认 mismatch_cnt = 0
4. 执行 Step 8c，确认 replaceImage 后的 stale_snapshot_cnt = 0
5. 执行 Step 3 端到端判定
```

### 验证 subJobId 传递修复（BT_5976）

```
1. 对修复后新建的批次执行 Step 7a
2. 确认所有 operation_type 的 coverage_pct = 100%
3. 执行 Step 7b，确认无缺失记录
```

### 验证 SharedArrayBuffer 修复（BT_6149）

```
1. curl -sI https://pre-aifashion-xiaoer.alibaba-inc.com/ | grep -iE 'cross-origin-(opener|embedder)-policy'
2. 确认响应头包含：Cross-Origin-Opener-Policy: same-origin + Cross-Origin-Embedder-Policy: require-corp
3. 浏览器打开视频编辑页面，Console 无 SharedArrayBuffer 相关报错
```

## 已知问题模式速查

| 问题编号 | 根因 | 关键特征 | 影响 |
|---------|------|---------|------|
| BT_6148 | replaceImage 只更新 material，未回写 review_job.info | BATCH 模式 approve 拿老 URL | 下游拿到过期 URL |
| BT_5976 | 5 类素材操作中约 4 类未传 subJobId | sub_job_id 为空 | 链路追踪断裂 |
| BT_6149 | 预发 Nginx 未配置 COOP/COEP | Console 报 SharedArrayBuffer | 客户端视频编辑器不可用 |
| BT_7495 | 审核任务分配算法整除/取余校验不一致 | 全部 INIT + errorMsg 含"期望分配数量" | 整批审核无法创建 |
| BT_7485 | 审核回调三条件缺失 | 任务已 FINISH 但 approve 仍 HANDLING | 批次不流转 |

## 常用 SQL 速查

```sql
-- 表结构自检
DESC workflow_record_log
DESC g_afd_review_job
DESC g_afd_material

-- extra_info 错误信息
SELECT id, status, LEFT(extra_info, 800) AS extra_info
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND status = 'FAIL' AND id >= {id_threshold} AND env = 'staging'
ORDER BY id DESC LIMIT 10
```

## 命令行模板

```bash
~/dms-alibaba/bin/dms-alibaba sql run stylespot --db rm-lgay0v5lor8396yka \
  --sql "{one-line SQL, no trailing semicolon inside quotes}"
```

结果文件路径：`~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{YYYY-MM-DD}/{HHMMSS}_rm-lgay0v5lor8396yka.json`

## Pitfalls 汇总

- 直接查全表不加 id 过滤 → 20s 超时
- 用 `search_key` / `node_name` 列名 → Unknown column
- 只看 approve.input_json 判断 bug → 假阳性（input 是快照允许老 URL）
- approve 是 HANDLING 就下结论 → 应先查 review_job 抽检子任务状态
- 忽略 dms 终端输出截断 → 用 Python 读结果 JSON 文件
- 假设 execMode 不影响结果 → 应先查 `g_workflow_batch.exec_mode`
- 快照不一致 = bug → 需结合 execMode：STREAM 模式下不影响 approve

## 验证结论输出模板

| 批次 | 类型 | approve.input（旧快照） | approve.output.passedImg | 下游 gen_video.input | 结果 |
|---|---|---|---|---|---|
| BT_xxxx | 视频/图片 | 老 URL | 新 localUpload URL | 新 localUpload URL | ✅ 生效 / ❌ bug 复现 |
