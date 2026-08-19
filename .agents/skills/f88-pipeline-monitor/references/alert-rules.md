# 告警规则详细定义

## R001: 节点失败率过高

- **维度**: D1 批次健康度
- **条件**: 某 `node_type` 的 FAIL 占比 > 30%（基于最近 100 条记录）
- **级别**: P1 WARNING（30%-50%）/ P0 CRITICAL（>50%）
- **SQL**:
```sql
SELECT node_type, status, COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = '{env}'
GROUP BY node_type, status
```
- **计算**: `fail_rate = FAIL_cnt / (SUCCESS_cnt + FAIL_cnt + HANDLING_cnt)`
- **通知模板**: "批次 {batch_id} 的 {node_type} 失败率达 {fail_rate}%，共 {fail_cnt} 条失败记录"

## R002: 阶段未触发

- **维度**: D2 阶段衔接
- **条件**: 链路配置的下一阶段在 `g_workflow_batch` 中无任何 `workflow_instance` 记录
- **级别**: P0 CRITICAL
- **检测方法**:
  1. 从 `g_workflow_batch` 获取当前批次的所有 `workflow_instance_id`
  2. 关联 `g_workflow_instance` 获取 `strategy_id` 列表
  3. 对比链路配置的各阶段策略 ID，找出缺失的阶段
- **通知模板**: "批次 {batch_id} 的阶段 '{stage_name}' 未触发，链路配置了 {total_stages} 个阶段但仅执行了 {executed_stages} 个"

## R003: HANDLING 停滞超时

- **维度**: D1 批次健康度
- **条件**: `status = 'HANDLING'` 且 `gmt_modified` 距今 > 30 分钟
- **级别**: P1 WARNING（30-60 分钟）/ P0 CRITICAL（>60 分钟）
- **SQL**:
```sql
SELECT id, node_type, gmt_modified,
       TIMESTAMPDIFF(MINUTE, gmt_modified, NOW()) AS stuck_minutes
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'HANDLING'
  AND id > 4000000
  AND env = '{env}'
  AND TIMESTAMPDIFF(MINUTE, gmt_modified, NOW()) > 30
```
- **通知模板**: "批次 {batch_id} 有 {stuck_cnt} 条 HANDLING 记录停滞超过 {max_minutes} 分钟"

## R004: LLM 429 Quota 耗尽

- **维度**: D3 LLM 资源
- **条件**: `errorMsg` 包含 "429" 或 "RESOURCE_EXHAUSTED"
- **级别**: P1 WARNING（偶发 <10 条）/ P0 CRITICAL（批量 >10 条 / 5 分钟内）
- **SQL**:
```sql
SELECT COUNT(*) AS cnt, MIN(gmt_create) AS first_seen, MAX(gmt_create) AS last_seen
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND id > 4000000
  AND env = '{env}'
  AND (JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%429%'
       OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%RESOURCE_EXHAUSTED%')
```
- **通知模板**: "批次 {batch_id} 出现 {cnt} 条 LLM 429 错误，时间范围 {first_seen} ~ {last_seen}"

## R005: 审核超时

- **维度**: D2 阶段衔接
- **条件**: 审核阶段（approve）记录创建后 > 2 小时仍未更新状态
- **级别**: P2 INFO（2-6 小时）/ P1 WARNING（>6 小时）
- **检测方法**: 查询 `node_type` 包含 "approve" 且 `status = 'HANDLING'` 的记录，检查时间差
- **通知模板**: "批次 {batch_id} 审核已等待 {hours} 小时，建议推送提醒审核人"

## R006: 输出参数丢失

- **维度**: D2 阶段衔接
- **条件**: 审核通过但 `passedImg` 字段包含 `null` 值
- **级别**: P0 CRITICAL
- **检测方法**: 检查 `approve` 节点的 `output_json` 中 `passedImg` 数组
- **背景**: BT_5621 案例中发现 `passedImg = [null, null]` 导致下一阶段无法启动
- **通知模板**: "批次 {batch_id} 审核输出参数异常：passedImg 包含 null 值，将导致下一阶段无法启动"

## R007: Mock 错误污染

- **维度**: D1 批次健康度
- **条件**: `errorMsg` 包含 "mock" 关键字
- **级别**: P0 CRITICAL（生产环境不应出现 mock 错误）
- **SQL**:
```sql
SELECT COUNT(*) AS cnt, node_type
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND id > 4000000
  AND env = '{env}'
  AND JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%mock%'
GROUP BY node_type
```
- **背景**: BT_5819 案例中发现 "mock llm error" 阻塞了全部 105 条 gen_img
- **通知模板**: "批次 {batch_id} 检测到 mock 错误 {cnt} 条（{node_type}），疑似测试配置未清理"

## R008: 单策略集中失败

- **维度**: D1 批次健康度
- **条件**: 某策略的失败数占该节点总失败数 > 80%
- **级别**: P1 WARNING
- **SQL**:
```sql
SELECT JSON_EXTRACT(extra_info, '$.strategyName') AS strategy_name,
       COUNT(*) AS cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND status = 'FAIL'
  AND node_type = '{node_type}'
  AND id > 4000000
  AND env = '{env}'
GROUP BY JSON_EXTRACT(extra_info, '$.strategyName')
ORDER BY cnt DESC
```
- **通知模板**: "批次 {batch_id} 的 {node_type} 失败集中在策略 '{strategy_name}'（{cnt}/{total} 条）"

## R009: ScheduleX 调度失败

- **维度**: D5 应用健康
- **条件**: ScheduleX 定时任务执行失败
- **级别**: P0 CRITICAL
- **检测方法**: 通过 Sunfire 或 ScheduleX 控制台检查定时任务执行状态
- **通知模板**: "ScheduleX 任务 '{job_name}' 执行失败，可能影响批次自动推进"

## R010: 上游服务不可达

- **维度**: D1 批次健康度
- **条件**: `errorMsg` 包含 "upstream request failed" 或 "Cannot fetch content"
- **级别**: P1 WARNING（偶发）/ P0 CRITICAL（批量 >20 条 / 10 分钟）
- **通知模板**: "批次 {batch_id} 上游服务不可达 {cnt} 条，最近 10 分钟 {recent_cnt} 条"

## R011: 输出物可访问性异常

- **维度**: D1 批次健康度
- **条件**: `output_json` 中的 URL（outputVideo / outputImage）HTTP 状态码非 200
- **级别**: P1 WARNING
- **检测方法**: 抽样检查 SUCCESS 记录的输出 URL，curl 验证可访问性
- **通知模板**: "批次 {batch_id} 抽样 {sample_cnt} 条输出物中有 {fail_cnt} 条 URL 不可访问"

## R012: 批次整体进度异常

- **维度**: D1 批次健康度
- **条件**: 批次创建 > 4 小时但 SUCCESS 率 < 50%
- **级别**: P1 WARNING
- **SQL**:
```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_cnt,
  SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_cnt,
  SUM(CASE WHEN status = 'HANDLING' THEN 1 ELSE 0 END) AS handling_cnt
FROM workflow_record_log
WHERE batch_id = '{batch_id}' AND id > 4000000 AND env = '{env}'
```
- **通知模板**: "批次 {batch_id} 创建已 {hours} 小时，成功率仅 {success_rate}%"

## R013: 机器 CPU / GC 异常

- **维度**: D6 机器健康（WF5）
- **条件**: `system.cpu.usage` > 80% 持续 5 分钟，或 `jvm.gc.pause` P99 > 500ms
- **级别**: P1 WARNING（CPU 80%-90% 或 GC P99 500-1000ms）/ P0 CRITICAL（CPU > 90% 或 GC P99 > 1000ms）
- **检测方法**: `sf metric query -a stylespot-admin -m 'system.cpu.usage' --range 5m`
- **降级**: sf CLI 不可用时，通过 DMS 查询 1h 内无 op_record 写入间接判断服务异常
- **通知模板**: "stylespot-admin 机器 CPU 使用率 {cpu_usage}%（阈值 80%），GC P99 {gc_p99}ms"

## R014: Heap / 线程池异常

- **维度**: D6 机器健康（WF5）
- **条件**: `jvm.memory.heap.used / jvm.memory.heap.max` > 85%，或活跃线程 > 线程池上限 90%
- **级别**: P1 WARNING（85%-95%）/ P0 CRITICAL（>95%）
- **检测方法**: `sf metric query -a stylespot-admin -m 'jvm.memory.heap.used' --range 5m`
- **通知模板**: "stylespot-admin Heap 使用率 {heap_pct}%（阈值 85%），线程池水位 {thread_pct}%"

## R015: HSF / MTOP 接口成功率下降

- **维度**: D7 服务接口（WF6）
- **条件**: HSF provider 成功率 < 99.5%，或 MTOP 成功率 < 99%
- **级别**: P1 WARNING（99%-99.5%）/ P0 CRITICAL（<99%）
- **检测方法**:
  - HSF: `sf metric query -a stylespot-admin -m 'hsf.provider.success_rate' --range 15m`
  - MTOP: `sf metric query -a stylespot-admin -m 'mtop.success_rate' --range 15m`
- **关键服务**: TemplatePoolToolService / MaterialProdRecordService / WorkflowBatchService
- **SQL 降级**:
```sql
SELECT COUNT(*) AS total,
       SUM(CASE WHEN status = 'FAIL' AND JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%HSF%' THEN 1 ELSE 0 END) AS hsf_fail
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
```
- **通知模板**: "stylespot-admin HSF 成功率 {hsf_rate}%（阈值 99.5%），MTOP 成功率 {mtop_rate}%（阈值 99%）"

## R016: TOP 接口（天工 / 知衣）异常

- **维度**: D7 服务接口（WF6）
- **条件**: 天工 8 项接口或知衣接口调用失败率 > 5%
- **级别**: P1 WARNING（5%-20%）/ P0 CRITICAL（>20%）
- **检测方法**: 通过 workflow_record_log 统计 node_type 包含外部调用标识的 FAIL 记录
- **SQL**:
```sql
SELECT node_type,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS fail_cnt,
       ROUND(SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS fail_rate
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND node_type IN ('tiangong_call', 'zhiyi_call', 'external_api')
GROUP BY node_type
HAVING fail_rate > 5
```
- **通知模板**: "外部 TOP 接口 {node_type} 失败率 {fail_rate}%（{fail_cnt}/{total}），阈值 5%"

## R017: 算法网关成功率下降

- **维度**: D8 算法依赖（WF7）
- **条件**: 算法网关调用成功率 < 95%（基于 workflow_record_log 中算法相关节点）
- **级别**: P1 WARNING（90%-95%）/ P0 CRITICAL（<90%）
- **SQL**:
```sql
SELECT node_type,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_cnt,
       ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS success_rate
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND node_type IN ('gen_img', 'gen_video', 'strategy', 'algo_filter', 'quality_score', 'style_transfer')
GROUP BY node_type
HAVING success_rate < 95
```
- **通知模板**: "算法节点 {node_type} 成功率 {success_rate}%（阈值 95%），最近 1h {fail_cnt} 条失败"

## R018: 算法节点处理超时

- **维度**: D8 算法依赖（WF7）
- **条件**: 节点平均处理时间超过阈值（gen_img ≤5min, gen_video ≤10min, strategy ≤3min）
- **级别**: P1 WARNING（1.5x 阈值）/ P0 CRITICAL（2x 阈值）
- **SQL**:
```sql
SELECT node_type,
       COUNT(*) AS total,
       AVG(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)) AS avg_seconds,
       MAX(TIMESTAMPDIFF(SECOND, gmt_create, gmt_modified)) AS max_seconds
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging'
  AND status = 'SUCCESS'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND node_type IN ('gen_img', 'gen_video', 'strategy')
GROUP BY node_type
```
- **阈值映射**: gen_img=300s, gen_video=600s, strategy=180s
- **通知模板**: "算法节点 {node_type} 平均耗时 {avg_seconds}s（阈值 {threshold}s），最大耗时 {max_seconds}s"

## R019: 离线数据链路时效异常

- **维度**: D9 离线数据链路（WF8）
- **条件**: 企划案产出 / 商品数据 / 潜力预估数据最新分区时间 > 预期（T+1 应在次日 10:00 前就绪）
- **级别**: P1 WARNING（延迟 2-6h）/ P0 CRITICAL（延迟 >6h）
- **检测方法**: 查询 `ads_g_item_profile_shop_gene` 等表最新分区日期
- **SQL**:
```sql
SELECT MAX(ds) AS latest_partition,
       DATEDIFF(CURDATE(), MAX(ds)) AS delay_days
FROM ads_g_item_profile_shop_gene
WHERE ds >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 DAY), '%Y%m%d')
```
- **通知模板**: "离线数据 {table_name} 最新分区 {latest_partition}，延迟 {delay} 天（预期 T+1）"

## R020: 素材日产出量异常

- **维度**: D9 离线数据链路（WF8）
- **条件**: 当日素材产出量较 7 日均值下降 > 30%
- **级别**: P2 INFO（下降 30%-50%）/ P1 WARNING（下降 >50%）
- **SQL**:
```sql
SELECT
  COUNT(*) AS today_output,
  (SELECT COUNT(*) / 7
   FROM workflow_record_log
   WHERE id > 4000000 AND env = 'staging'
     AND status = 'SUCCESS'
     AND node_type IN ('gen_img', 'gen_video')
     AND gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
  ) AS avg_7d_output
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging'
  AND status = 'SUCCESS'
  AND node_type IN ('gen_img', 'gen_video')
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 24 HOUR)
```
- **通知模板**: "今日素材产出 {today_output} 条，7 日均值 {avg_7d_output} 条，下降 {drop_pct}%"

## R021: Caption 离线分区数量停滞

- **维度**: D9 离线数据链路（WF8）
- **条件**: `taobao_tec_platform.s_g_afd_caption_output_df` 最近 3 个分区的总数量完全相同（增量为 0），且线上有新增图片流入
- **级别**: P1 WARNING（连续 3 天不变）/ P0 CRITICAL（连续 5 天不变）
- **检测方法**: 对比最近 3~5 个分区的 count，若完全持平则判定增量同步链路中断
- **SQL**:
```sql
-- 查询最近 5 个分区的记录数
SELECT ds, COUNT(*) AS partition_count
FROM taobao_tec_platform.s_g_afd_caption_output_df
WHERE ds >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 7 DAY), '%Y%m%d')
GROUP BY ds
ORDER BY ds DESC
LIMIT 5
```
- **判定逻辑**:
  - 取最近 5 个分区的 count 值
  - 若最近 3 个 count 完全相同 → P1 WARNING（Caption 离线增量同步疑似中断）
  - 若最近 5 个 count 完全相同 → P0 CRITICAL（Caption 离线增量同步确认中断）
  - 辅助验证：查线上 MySQL `g_afd_caption_output` 表最近 3 天是否有新增记录（有新增但 ODPS 不变 = 同步链路断裂）
- **辅助 SQL（线上增量验证）**:
```sql
SELECT COUNT(*) AS recent_new_count
FROM g_afd_caption_output
WHERE gmt_create > DATE_SUB(NOW(), INTERVAL 3 DAY)
```
- **通知模板**: "Caption 离线表 s_g_afd_caption_output_df 最近 {stagnant_days} 个分区数量均为 {count}，增量同步疑似中断。线上近 3 天新增 {recent_new_count} 条 caption 记录未同步至 ODPS。"
- **根因排查方向**:
  1. `AfdCaptionOutputRefreshJob`（SchedulerX）是否正常调度、最近执行状态
  2. ODPS 同步任务的增量 SQL 条件（gmt_modified 时间窗口）是否正确
  3. 上游 caption 服务是否停止写入新结果
  4. DataWorks 数据集成节点是否报错/被暂停

## R022: 审核回调消息链路断裂

- **维度**: D2 阶段衔接（WF2 第 6 步）
- **条件**: 含 approve 节点的批次，审核完成超 1h 但阶段未流转，且链路断在消息未发送/未消费
- **级别**: P0 CRITICAL
- **检测方法**: 三点链路逐段核查——① doCompleteMainTaskIfAllPersonalDone 是否执行（抽检未完成属预期等待，不告警）② normandy CLI 检索 sendWorkflowRecordFinishMsg（`normandy log list --source sls --project stylespot-admin-log --logstore stylespot-admin-online --query "sendWorkflowRecordFinishMsg"`）确认 TOPIC_AFD_WORKFLOW2_ENGINE_RECORD_FINISH (tag: approve) 是否发送 ③ Workflow2EngineRecordFinishListener.onNodeFinish 是否消费
- **注意**: runMode=test/formal 流转开关行为不同，告警前先核对 runMode（真实案例 BT_7485：runMode=test + 抽检未完成，属预期等待非故障）
- **通知模板**: "{batch} 审核完成已超 1h 未流转，断点定位：{断点位置}。runMode={mode}，抽检状态={inspection}。"

## R023: LLM 文本节点 JSON 解析失败率

- **维度**: D3 LLM 资源（WF3）
- **条件**: errorMsg 匹配 `FASTJSON.*error, offset` 的记录占比超阈值
- **级别**: P1 WARNING（单批次 > 5%）/ P0 CRITICAL（> 20%）
- **检测方法**: 按链路/策略/模型维度统计解析失败记录数占比
- **SQL**:
```sql
SELECT batch_id, COUNT(*) AS parse_fail_cnt
FROM workflow_record_log
WHERE id > 4000000 AND env = 'staging' AND status = 'FAIL'
  AND error_msg REGEXP 'FASTJSON.*offset'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY batch_id
```
- **根因排查方向**: 模型输出格式漂移（模型版本变更/prompt 变更），真实案例 BT_7417（offset 20 char &）

## R024: 模型队列 priority 分档饿死

- **维度**: D4 队列积压（WF4）
- **条件**: 某模型队列全局积压（running > 1000）且 priority 最低档批次连续零产出
- **级别**: P1 WARNING（零产出 > 2h）/ P0 CRITICAL（零产出 > 4h）
- **检测方法**: 在现有模型积压监控上按 priority 区间（如 7/9/15）拆分 running 数与等待时长
- **处置建议**: 调高批次 priority 或错峰提交（真实案例 BT_7495：priority=15 批次 1548 条任务卡 4h 零产出）

## R025: 首图生成时效超时

- **维度**: D10 交付时效 SLA（WF10）
- **条件**: 批次创建后，首图生成阶段首批记录 SUCCESS 的耗时 > T1
- **级别**: P1 WARNING（> T1）/ P0 CRITICAL（> T1×2）
- **默认阈值**: T1 = 4h（待业务校准）
- **检测方法**: SQL 模板见 sql-templates.md → "阶段时效统计（WF10）"
- **说明**: 业务保时效目标 48h 的分解指标之一，来源《生产链路稳定性提升方案》时效预警

## R026: 首图审核时效超时

- **维度**: D10 交付时效 SLA（WF10）
- **条件**: 首图进入审核后，审核完成耗时 > T2
- **级别**: P1 WARNING（> T2）/ P0 CRITICAL（> T2×2）
- **默认阈值**: T2 = 8h（待业务校准）
- **检测方法**: 同"阶段时效统计（WF10）"
- **说明**: 审核时效不仅取决于系统，还取决于审核人力排班；告警时附当前待审核任务量辅助判断

## R027: 套图生成时效超时

- **维度**: D10 交付时效 SLA（WF10）
- **条件**: 批次创建后，套图生成阶段完成的耗时 > T3
- **级别**: P1 WARNING（> T3）/ P0 CRITICAL（> T3×2）
- **默认阈值**: T3 = 24h（待业务校准）
- **检测方法**: 同"阶段时效统计（WF10）"

## R028: 套图审核时效超时与 48h 交付红线

- **维度**: D10 交付时效 SLA（WF10）
- **条件**: 套图审核完成耗时 > T4，或批次总耗时逼近/突破 48h 交付红线
- **级别**: P1 WARNING（> T4）/ P0 CRITICAL（批次创建超 44h 仍未完成全部阶段，或已超 48h）
- **默认阈值**: T4 = 36h（待业务校准）
- **检测方法**: 同"阶段时效统计（WF10）"
- **说明**: 48h 是业务保时效硬指标（来源《生产链路稳定性提升方案》），超 44h 即提前预警留出干预窗口

## R029: 套图审核 → 内容上传数量缺口

- **维度**: D11 环节对账（WF11）
- **条件**: 套图审核 SUCCESS 数（trace_id 关联 map_gen_img SUCCESS 筛选）与 image_text_upload 总数偏差超阈值
- **级别**: P1 WARNING（gap > 5%）/ P0 CRITICAL（gap > 20%）
- **检测方法**: SQL 模板见 sql-templates.md → "环节对账（WF11）"，trace_id 自关联区分首图/套图审核
- **真实案例**: BT_7324 套图审核 231 → 内容上传 145，gap 37.2%（策略2-6未设默认策略，上传未全量执行）
- **通知模板**: "【F88 数据对账告警】批次 {batch}，对账点：套图审核→内容上传，上游 {up} / 下游 {down}，偏差 {gap} 条（{pct}）。可能原因：部分策略未设默认策略。建议：检查策略默认配置，补推遗漏数据。"

## R030: 内容上传失败率

- **维度**: D11 环节对账（WF11）
- **条件**: image_text_upload 节点 FAIL 率超阈值
- **级别**: P1 WARNING（> 10%）/ P0 CRITICAL（> 20%）
- **检测方法**: 按 batch 统计 image_text_upload 的 FAIL/总数，FAIL 原因分布见 sql-templates.md → "环节对账（WF11）"
- **真实案例**: BT_7324 上传失败率 15.9%（23/145）

## R031: 套图生成 → 套图审核覆盖缺口

- **维度**: D11 环节对账（WF11）
- **条件**: approve 中套图审核 SUCCESS 数 < map_gen_img SUCCESS × 90%
- **级别**: P1 WARNING
- **检测方法**: 同"环节对账（WF11）" trace_id 关联
- **说明**: 套图生成成功但未进入审核 = 审核任务创建链路断裂，需排查 approve 建单逻辑

## R032: 批次收敛度分数过低

- **维度**: D12 轨迹效率（新增维度）
- **条件**: 批次收敛度分数 < 0.6（实际步数比最优步数多 67%+）
- **级别**: P1 WARNING（0.4~0.6）/ P0 CRITICAL（<0.4）
- **SQL**: Use T-22 template. Calculate convergence_score = distinct_node_types / total_exec_count
- **通知模板**: "批次 {batch_id} 收敛度分数 {score}（实际 {total_steps} 步 / 最优 {optimal_steps} 步），存在冗余执行"
- **自愈建议**: 检查是否有重试循环或无效节点调用

## R033: 节点重试率过高

- **维度**: D12 轨迹效率
- **条件**: 同一 node_type 执行次数 > 预期次数 × 2（重试率 > 100%）
- **级别**: P1 WARNING（2x~3x）/ P0 CRITICAL（>3x）
- **SQL**: Use T-22 template. Check exec_count per node_type against expected count (from workflow_def)
- **通知模板**: "批次 {batch_id} 的 {node_type} 执行 {exec_count} 次（预期 {expected_count} 次），重试率 {retry_rate}%"
- **自愈建议**: 检查节点失败原因，可能是模型不稳定或输入数据问题

## R034: 节点平均耗时异常

- **维度**: D12 轨迹效率
- **条件**: 某节点平均耗时超过历史均值 × 2
- **级别**: P2 INFO（1.5x~2x）/ P1 WARNING（2x~3x）/ P0 CRITICAL（>3x）
- **SQL**: Use T-22 template. Compare avg_duration_sec against historical baseline
- **通知模板**: "批次 {batch_id} 的 {node_type} 平均耗时 {avg_sec}s（历史均值 {baseline_sec}s），性能下降 {ratio}x"
- **自愈建议**: 检查模型负载、网络延迟、输入数据大小

## 级别定义

| 级别 | 名称 | 响应时间 | 通知方式 |
|------|------|---------|---------|
| P0 | CRITICAL | 立即 | QoderWork IM + 钉钉群 |
| P1 | WARNING | 15 分钟内 | QoderWork IM |
| P2 | INFO | 下次巡检汇总 | QoderWork 消息 |
| P3 | DEBUG | 仅记录日志 | 不通知 |

## 判定信封 Schema（Verdict Envelope）

子 Agent 完成规则评估后，不返回原始数据，而是按以下信封格式返回结构化判定。主 Agent 仅消费信封字段，不做二次规则匹配。

### 通用信封

```json
{
  "verdict": "P0_CRITICAL | P1_WARNING | P2_INFO | OK",
  "ruleHit": "R001 | R002 | ... | R012 | null",
  "env": "staging | production | unknown",
  "selfHealable": true | false,
  "recommendedAction": "S1_RETRY | S2_RESTART | S3_PUSH | S4_BALANCE | S5_COMPENSATE | null",
  "evidence": "一句话概括判定依据（≤30字）",
  "details": { /* 各 WF 自定义字段，见下文 */ }
}
```

> **env 字段必填**：子 Agent 查询 SQL 中必须携带 `env` 列值并透传到信封。若 `env` 为 NULL 或缺失，填 `"unknown"`（按 production 处理）。

### verdict 与规则级别的映射

| verdict | 对应规则级别 | 主 Agent 处理 |
|---|---|---|
| `OK` | 无命中 | 直接丢弃，不进入上下文 |
| `P2_INFO` | P2 INFO | 记录到日报缓冲区，不推送 |
| `P1_WARNING` | P1 WARNING | 进入告警队列，汇总后推送 |
| `P0_CRITICAL` | P0 CRITICAL | 立即进入告警队列，优先推送 |

### ruleHit 与 selfHealable / recommendedAction 映射

> **环境覆盖规则**：下表中 `selfHealable=true` 仅在 `env="staging"` 时生效。若 `env="production"` 或 `env="unknown"`，无论 ruleHit 为何值，`selfHealable` 强制为 `false`，`recommendedAction` 强制为 `null`。

| ruleHit | selfHealable | recommendedAction | 说明 |
|---|---|---|---|
| R001 | true | S1_RETRY | 429/RESOURCE_EXHAUSTED 导致 |
| R001 | false | null | 其他错误类型，需人工分析 |
| R002 | false | null | 阶段未触发，需排查上游出参 |
| R003 | true | S2_RESTART | HANDLING 滞留，可重启 |
| R004 | true | S1_RETRY | 429 批量错误，指数退避重试 |
| R005 | true | S3_PUSH | 审核超时，可推送提醒 |
| R006 | false | null | 出参丢失，需人工修复 |
| R007 | false | null | Mock 错误，禁止自动重试 |
| R008 | false | null | 策略集中失败，需排查策略本身 |
| R009 | false | null | ScheduleX 失败，需人工介入 |
| R010 | true | S1_RETRY | 上游偶发不可达，可重试 |
| R010 | false | null | 上游批量不可达，需排查服务 |
| R011 | false | null | 输出物 URL 异常，需排查 CDN |
| R012 | false | null | 批次整体进度异常，需综合诊断 |
| R013 | false | null | CPU/GC 异常，需排查机器负载 |
| R014 | false | null | Heap/线程池异常，需排查内存泄漏 |
| R015 | false | null | HSF/MTOP 成功率下降，需排查服务 |
| R016 | true | S1_RETRY | TOP 接口偶发失败，可重试 |
| R016 | false | null | TOP 接口批量失败，需排查外部服务 |
| R017 | true | S1_RETRY | 算法网关偶发失败，可重试 |
| R017 | false | null | 算法网关批量失败，需排查算法服务 |
| R018 | false | null | 算法节点超时，需排查处理能力 |
| R019 | false | null | 离线数据延迟，需排查上游产出 |
| R020 | false | null | 素材产出量下降，需综合诊断 |
| R032 | false | null | 收敛度低，需排查重试循环或冗余节点 |
| R033 | true | S1_RETRY | 重试率过高，可能是模型不稳定 |
| R033 | false | null | 重试率过高且非偶发，需排查输入数据 |
| R034 | false | null | 耗时异常，需排查模型负载或网络 |

### 各 WF 的 details 字段规范

**WF1 批次健康**：
```json
{
  "batchId": "BT_xxxx",
  "nodeType": "gen_img | gen_video | approve | ...",
  "failureRate": 0.35,
  "topError": "RESOURCE_EXHAUSTED",
  "topErrorPct": 0.28,
  "failCount": 42,
  "totalCount": 120,
  "selfHealableCount": 38
}
```

**WF2 阶段衔接**：
```json
{
  "batchId": "BT_xxxx",
  "configuredStages": 8,
  "executedStages": 6,
  "brokenStages": [
    {
      "stageName": "套图生产",
      "strategyId": "S_20250601_003",
      "missingField": "passedImg",
      "upstreamNode": "approve"
    }
  ]
}
```

**WF3 LLM 资源**：
```json
{
  "modelName": "qwen-max | gemini-pro | ...",
  "utilization": 0.92,
  "error429Pct": 0.15,
  "runningTasks": 46,
  "capacity": 50,
  "periodOverPeriodDeviation": -0.35
}
```

**WF4 队列积压**：
```json
{
  "stallRecords": [
    {
      "recordId": 12345,
      "batchId": "BT_xxxx",
      "nodeType": "gen_img",
      "stallMinutes": 95,
      "status": "HANDLING"
    }
  ],
  "selfHealableRecords": [
    {
      "recordId": 12345,
      "action": "S2_RESTART",
      "retriesLeft": 2
    }
  ]
}
```

### 主 Agent 消费逻辑

```
收到判定信封 →
  🔴 环境隔离前置检查（自愈决策前必执行）：
    env == "staging"    → 允许进入自愈判断
    env == "production" → 强制 selfHealable=false, recommendedAction=null
    env == "unknown"    → 同 production 处理

  if verdict == OK → 丢弃
  elif verdict == P2_INFO → 写入日报缓冲区
  elif verdict == P1_WARNING → 入告警队列（等汇总）
  elif verdict == P0_CRITICAL → 入告警队列（优先推送）

  if env == "staging" AND selfHealable == true → 按 recommendedAction 执行自愈
  elif selfHealable == false → 标记"需人工介入"
  elif env != "staging" AND selfHealable == true → 标记"需人工介入（生产环境禁止自愈）"
```

### 示例：完整判定信封

**场景**：BT_5973 批次 gen_img 失败率 35%，top 错误为 429。

```json
{
  "verdict": "P1_WARNING",
  "ruleHit": "R001",
  "env": "staging",
  "selfHealable": true,
  "recommendedAction": "S1_RETRY",
  "evidence": "gen_img失败率35%>30%阈值，429占28%",
  "details": {
    "batchId": "BT_5973",
    "nodeType": "gen_img",
    "failureRate": 0.35,
    "topError": "RESOURCE_EXHAUSTED",
    "topErrorPct": 0.28,
    "failCount": 42,
    "totalCount": 120,
    "selfHealableCount": 38
  }
}
```
