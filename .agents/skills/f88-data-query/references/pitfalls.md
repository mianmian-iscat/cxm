# F88 查询陷阱清单

> 全部来自各 skill 文档的实战沉淀。写 SQL 前扫一遍，能避免 90% 的超时与误判。

## 字段名/取值陷阱

| 陷阱 | 正确写法 |
|------|---------|
| 失败状态写成 FAILED | `status = 'FAIL'` |
| 错误信息字段写成 errorMessage | `JSON_EXTRACT(extra_info, '$.errorMsg')` |
| g_strategy 用 strategy_id 查 | 主键是 `id` |
| workflow_record_log 用 search_key/node_name | 用 `batch_id` + `node_type`，否则 Unknown column |
| g_afd_review_job 找 node_id 列 | 不存在；用 `parent_job_id` + `relation_id` |
| 把 relation_id 当批次号 | relation_id 是链路 ID；批次号是 `batch_id`（BT_xxxx） |
| g_afd_material.type 当业务类型 | type 恒为"图片"（媒体格式）；业务类型看 `material_type` |

## 性能/超时陷阱

| 陷阱 | 对策 |
|------|------|
| workflow_record_log 裸查 20s 超时 | 必加 `id >= {id_threshold}`，阈值由 `get_workflow_log_threshold.py` 动态获取；node_type 无索引 |
| JOIN 超时 | 拆两步单表查（先拿 workflow_instance_id 列表再查实例表） |
| 结果 >200 行被截断 | 改 `sql run` 读结果文件，或聚合 COUNT/GROUP BY，或确定性分页 |
| 超时不知从何查起 | 检查是否漏 `id >= {id_threshold}` / `env='staging'`，阈值用脚本动态获取，禁止硬编码 4000000/6400000 |

## JSON 处理陷阱

| 陷阱 | 对策 |
|------|------|
| JSON_EXTRACT 比较不相等 | 返回带引号，用 `JSON_UNQUOTE()` 包裹 |
| 终端输出被截断当真值 | 优先读 JSON 结果文件（_results/ 目录） |

## 语义陷阱（最容易误判成 bug 的场景）

| 现象 | 正确解读 |
|------|---------|
| review_job.info 里是老 URL | info 是创建时快照，replaceImage 不回写；实时 URL 看 g_afd_material.url |
| approve.input_json 是老 URL | 输入快照允许老 URL；判断 bug 看 `output_json.passedImg` |
| approve 节点 HANDLING | 不代表卡死：先查 review_job 抽检子任务（job_type=3/5, status=1）是否在等 |
| STREAM 模式快照不一致 | 不影响 approve，非 bug；BATCH 下 mismatch 才是 bug（参考 BT_6148） |
| 记录永远 HANDLING | 查 g_admin_task：task_status=10 且 gmt_modified=gmt_create → TPP 从未回调（真 bug） |
| CDN/OSS URL 下载失败 | 区分 URL 本身无效 vs 签名过期：重查 DB 拿新 URL 再验 |
| 策略引用已下线模型 | 模型下线不会自动更新策略配置；必须查 DB 确认，禁止凭代码分支推断预发部署 |

## 安全/环境约束

| 约束 | 说明 |
|------|------|
| 只 SELECT | 禁止 INSERT/UPDATE/DELETE |
| env 过滤 | 主动查询加 `env='staging'`；生产数据只读且须谨慎 |
| 写操作红线 | 所有主动操作只允许作用于 staging 测试数据；env=production 或为空只读 |
| 通道选择 | 失败分析/跨表验证统一 dms-alibaba CLI（f88-failure-analysis 明确禁用 MCP 查询通道） |
