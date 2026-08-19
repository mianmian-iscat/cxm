# 种草素材排查常用 SQL

> 库：stylespot，DMS database_id=5335708（共享实例，env 列区分环境）
> 铁律：所有查询带 `env='staging'`（生产数据只读）；workflow_record_log 必须带 id 范围或 batch_id 窄窗口。
> dms-alibaba workaround：`env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin /bin/zsh -c 'dms-alibaba ...'`；CLI 记得带 `--db 5335708`。

## 1. 图文上传节点执行记录（workflow_record_log）

```sql
-- 按批次查图文上传节点（batch_id 走索引，推荐）
SELECT id, batch_id, node_type, status, input_json, output_json,
       extra_info, gmt_create, gmt_modified
FROM workflow_record_log
WHERE batch_id = 'BT_xxxx'
  AND node_type = 'image_text_upload'
  AND env = 'staging'
ORDER BY id;
```

判读：
- `status`：SUCCESS / FAIL / HANDLING
- `extra_info` JSON：`errorMsg`（失败原因）、`nodeName`（图文上传）、`strategyName`（定位策略）
- `input_json`：title / text / item_id / image_list；商家模式含 `sellerId`，达人模式不应含
- `output_json` 通常为 `{}`（发布结果不落此表，见 §2）

```sql
-- 无批次号时按 node_type 扫（必须带 id 范围，否则超时）
SELECT id, batch_id, status, extra_info, gmt_create
FROM workflow_record_log
WHERE node_type = 'image_text_upload'
  AND id > 8000000
  AND env = 'staging'
  AND gmt_create > '2026-08-01'
ORDER BY id DESC
LIMIT 50;
```

## 2. 发布回流表（g_afd_recommend_material_pool_record）

```sql
-- 商家模式：按 seller_id 查
SELECT id, seller_id, item_id, status, biz_scene, ext_info, gmt_create
FROM g_afd_recommend_material_pool_record
WHERE seller_id = '{sellerId}' AND env = 'staging'
ORDER BY id DESC LIMIT 10;

-- 达人模式：seller_id 为空，按 item_id 查
SELECT id, seller_id, item_id, status, biz_scene, ext_info, gmt_create
FROM g_afd_recommend_material_pool_record
WHERE item_id = '{itemId}' AND env = 'staging'
ORDER BY id DESC LIMIT 10;
```

判读：
- `status=6` 成功；`status=7` 失败（原因在 `ext_info.publishFailReason`）
- `biz_scene=cyz`（种草场景）
- `ext_info`：contentId（发布成功才有）、userId（达人模式）、publishTime、title/text、picUrls
- 节点 SUCCESS 但此表无记录 → 回流未落/同步延迟，查 MySQL→ODPS 同步任务

## 3. 商品 → 批次映射（g_afd_material_prod_record）

```sql
-- item_id 有 MUL 索引，20s 内返回
SELECT id, batch_id, item_id, source_type, process_mode, status,
       dispatch_status, gmt_create
FROM g_afd_material_prod_record
WHERE item_id = '{itemId}' AND env = 'staging'
ORDER BY gmt_create DESC LIMIT 20;
```

判读：`process_mode=seedGenerate`（种草生成，历史成功率约 77%）；0 行 → 商品未进入素材生产，转调度层排查（SKILL.md R3）。

## 4. 批次状态（g_workflow_batch）

```sql
SELECT id, batch_id, relation_id, source_type, status, env,
       try_run, creator, gmt_create
FROM g_workflow_batch
WHERE batch_id = 'BT_xxxx' AND env = 'staging';
```

判读：`relation_id` 是链路 ID（如 20259）；env='staging' 查不到 → 生产批次（生产只读，另行评估）。

## 5. 素材坑位统计（ODPS，调度层排查用）

```sql
-- 生产实际 SQL（注意表名拼写 ouput 是历史遗留；COUNT(id) 非 COUNT(*)）
SELECT feeds_item_id, COUNT(id) AS material_cnt
FROM tb_middle_layer.v_feeds_industry_offline_ouput_fashion
WHERE ds = '${bizdate}' AND feeds_publish_scene = 'item_self_content'
GROUP BY feeds_item_id;
```

判读：material_cnt ≥ 6 → 坑位已满不进 P2 队列；只统计 `item_self_content` 场景。

## 6. F0 爆款潜爆取数（ODPS，入池条件核对）

```sql
-- P2 入池口径（简化示意，以 PRD 为准）
SELECT a.item_id
FROM dim_tb_fashion_88_itm a
JOIN ads_tb_fashion_f88_itm_agg b ON a.item_id = b.item_id
WHERE b.ds = MAX_PT('ads_tb_fashion_f88_itm_agg')
  AND b.f_level = 'F0' AND b.is_online = 'Y'
  AND (b.is_pop_30d = 'Y' OR b.is_pop_7d = 'Y');
```

## 7. 链路/策略配置核对（API，优先于 DB）

```
GET /api/workflow2/strategy/get?id={strategyId}   # workflowDef.innerNodes 看节点配置
GET /api/workflow2/common/getNodeTypeEnums         # 确认 image_text_upload 已注册
POST /api/workflow2/node/tryRun                    # 节点独立试运行复现失败
```

注意：预发 API 走 httpOnly SSO cookie，requests 裸调会返回登录页 HTML，须用浏览器 fetch 预取。

## 8. 历史成功批次基准（对照数据流用）

| 批次 | 模式 | 结果 | 说明 |
|------|------|------|------|
| BT_7000 | 商家（10791 链路 20259 全链路） | 15 节点全 SUCCESS | 5 阶段数据流基准 |
| BT_7074 | 商家 strategy/run | status=6, contentId=13081409837850 | 商家落表基准 |
| BT_7075 | 达人 strategy/run（10767） | status=6, ext_info.userId=2583875942 | 达人落表基准 |
| BT_7072 | 商家，1 张图 | FAIL [LESS_PHOTO_MIN] | 校验正确非 bug |
| BT_7073 | 商家，image_list 为逗号字符串 | FAIL contentId 为空 | 入参格式问题 |
