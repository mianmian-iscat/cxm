# 环境级检查手册

本文档包含两项环境级检查的完整步骤和修复方向。

---

## 检查一：COOP/COEP 响应头（SharedArrayBuffer）

症状：前端页面报 `SharedArrayBuffer is not defined`、FFmpeg WASM 加载失败、视频处理功能不可用。关联 Bug：BT_6149。

根因：SharedArrayBuffer 要求页面响应头包含 `Cross-Origin-Opener-Policy: same-origin` 和 `Cross-Origin-Embedder-Policy: require-corp`（或 `credentialless`，可避免 CDN 资源缺少 CORP 头的问题，与 f88-failure-analysis 工作流 11 口径一致）。Nginx 配置缺失或被子配置覆盖导致头部丢失。若 COEP=require-corp 但 CDN 资源（如 alicdn 上的 ffmpeg-core.wasm.gz）缺少 `Cross-Origin-Resource-Policy: cross-origin` 头，跨域 WASM 文件仍会被阻止，需一并检查 CDN 响应头。

### 检查步骤

1. curl 检查预发环境响应头：
```bash
curl -sI https://pre-aifashion-xiaoer.alibaba-inc.com/ | grep -iE 'cross-origin-(opener|embedder)-policy'
```
- 期望输出：
  ```
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
  ```
- 缺失任一项 → SharedArrayBuffer 不可用

2. 检查多个路径（不同路径可能由不同 Nginx location 块处理）：
```bash
for path in "/" "/api/health" "/static/js/main.js"; do
  echo "=== $path ==="
  curl -sI "https://pre-aifashion-xiaoer.alibaba-inc.com${path}" | grep -iE 'cross-origin|HTTP/'
done
```

3. 线上环境对比：
```bash
curl -sI https://aifashion-xiaoer.alibaba-inc.com/ | grep -iE 'cross-origin-(opener|embedder)-policy'
```
- 线上正常、预发缺失 → 预发 Nginx 配置未同步

### 修复方向

- Nginx 配置添加：`add_header Cross-Origin-Opener-Policy "same-origin" always;` + `add_header Cross-Origin-Embedder-Policy "require-corp" always;`
- 注意 `always` 关键字，否则错误响应不带头部
- 检查是否有 `proxy_hide_header` 或上层配置覆盖了这些头

---

## 检查二：subJobId 链路追踪

症状：审核任务回调后 trace 丢失、无法关联到原始 workflow 记录、SLS 日志中搜不到对应 traceId。关联 Bug：BT_5976。

根因：部分操作类型在创建审核任务时未传 subJobId，导致回调时无法通过 subJobId 反查 workflow_record_log。

### 检查步骤

1. 按操作类型统计 subJobId 覆盖率：
```sql
SELECT rj.job_type,
  COUNT(*) as total,
  SUM(CASE WHEN JSON_EXTRACT(rj.info, '$.subJobId') IS NOT NULL THEN 1 ELSE 0 END) as has_sub_job_id,
  SUM(CASE WHEN JSON_EXTRACT(rj.info, '$.subJobId') IS NULL THEN 1 ELSE 0 END) as missing_sub_job_id
FROM g_afd_review_job rj
WHERE rj.gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY rj.job_type
ORDER BY rj.job_type
```
- missing_sub_job_id > 0 → 该 job_type 的审核任务缺少 subJobId

2. 查具体缺失记录：
```sql
SELECT rj.id, rj.job_type, rj.job_status, rj.relation_id,
  rj.gmt_create,
  JSON_EXTRACT(rj.info, '$.subJobId') as sub_job_id,
  JSON_EXTRACT(rj.info, '$.questionType') as question_type
FROM g_afd_review_job rj
WHERE JSON_EXTRACT(rj.info, '$.subJobId') IS NULL
  AND rj.gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY rj.gmt_create DESC
LIMIT 20
```

3. 验证回调链路完整性（有 subJobId 的记录能否关联到 workflow）：
```sql
SELECT rj.id as review_job_id,
  JSON_EXTRACT(rj.info, '$.subJobId') as sub_job_id,
  wrl.id as workflow_record_id,
  wrl.batch_id, wrl.node_type, wrl.status
FROM g_afd_review_job rj
LEFT JOIN workflow_record_log wrl
  ON JSON_EXTRACT(rj.info, '$.subJobId') = wrl.id
WHERE ((rj.job_type IN (1,2,3) AND rj.job_status IN (1,2)) OR rj.job_status = 5) -- 终态记录：子任务(1=通过/2=不通过)或主任务已完成(5)；job_status 为双重语义
  AND rj.gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
  AND wrl.id IS NULL
LIMIT 20
```
- 结果非空 → 有 subJobId 但关联不到 workflow 记录，可能是数据不一致
