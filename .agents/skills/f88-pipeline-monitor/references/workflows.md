# 监控工作流详细定义

> 本文件是 f88-pipeline-monitor 的工作流知识库，包含 WF1~WF11 的完整步骤。
> SKILL.md 只做路由，具体执行时读取本文件获取步骤详情。

## 子 Agent 隔离矩阵

| 工作流 | 隔离方式 | 子 Agent 返回（判定级） | 主 Agent 保留 |
|---|---|---|---|
| WF1 批次健康 | 每个批次一个子 Agent | 判定信封（verdict + ruleHit + failureRate + topError） | 仅 verdict ≠ OK 的批次 |
| WF2 阶段衔接 | 数据采集子 Agent | 判定信封（verdict + brokenStages + missingField） | 仅断裂阶段诊断文本 |
| WF3 LLM 资源 | 数据采集子 Agent | 判定信封（verdict + utilization + error429Pct） | 仅异常模型指标 |
| WF4 队列积压 | 扫描子 Agent | 判定信封（verdict + stallRecords + selfHealable） | 仅 P0/P1 告警 |
| WF5 机器健康 | sf CLI 子 Agent | 判定信封（verdict + cpuPct + heapPct + gcCount） | 仅异常指标 |
| WF6 服务接口 | sf CLI 子 Agent | 判定信封（verdict + serviceName + successRate + rt） | 仅成功率低于阈值的接口 |
| WF7 算法依赖 | sf CLI 子 Agent | 判定信封（verdict + gatewaySuccessRate + asyncRate + timeoutCnt） | 仅异常指标 |
| WF8 离线数据链路 | DMS 子 Agent | 判定信封（verdict + missingOutputs + staleHours） | 仅未产出/过期项 |
| WF9 报告生成 | **不隔离**（汇总决策） | — | 完整报告 |
| WF10 交付时效 SLA | DMS 子 Agent | 判定信封（verdict + milestoneHours + remainingBudget） | 仅超阈值批次 |
| WF11 环节对账 | DMS 子 Agent | 判定信封（verdict + gapPct + missingCount） | 仅偏差 >5% 的对账点 |

## 通用判定信封格式

每个子 Agent 返回时遵循以下信封格式：

```json
{
  "verdict": "P0_CRITICAL | P1_WARNING | P2_INFO | OK",
  "ruleHit": "R001 | R002 | ... | null",
  "env": "staging | production | unknown",
  "selfHealable": true | false,
  "recommendedAction": "S1_RETRY | S2_RESTART | S3_PUSH | S4_BALANCE | null",
  "evidence": "一句话概括判定依据（≤30字）",
  "details": { /* 各 WF 自定义字段 */ }
}
```

> **`env` 字段必填**。子 Agent 查询时必须从数据中提取 env 值；若 `workflow_record_log.env` 为 NULL 则填 `"unknown"`，等同 production 处理（禁止自愈）。

### 各 WF 的 details 字段规范

**WF1 批次健康**：batchId, nodeType, failureRate, topError, topErrorPct, failCount, totalCount, selfHealableCount

**WF2 阶段衔接**：batchId, configuredStages, executedStages, brokenStages[{stageName, strategyId, missingField, upstreamNode}]

**WF3 LLM 资源**：modelName, utilization, error429Pct, runningTasks, capacity, periodOverPeriodDeviation

**WF4 队列积压**：stallRecords[{recordId, batchId, nodeType, stallMinutes, status}], selfHealableRecords[{recordId, action, retriesLeft}]

### 主 Agent 判定消费逻辑

1. **🔴 环境隔离前置检查**（自愈决策前必执行）：
   - `env == "staging"` → 允许进入自愈判断
   - `env == "production"` → 强制 `selfHealable=false`, `recommendedAction=null`
   - `env == "unknown"` → 同 production 处理
2. `verdict == OK` → 直接丢弃
3. `verdict == P2_INFO` → 仅记录到日报缓冲区
4. `verdict == P1_WARNING` → 进入告警队列
5. `verdict == P0_CRITICAL` → 立即进入告警队列
6. `env == "staging" AND selfHealable == true` → 按 `recommendedAction` 执行自愈
7. `selfHealable == false` → 标记为"需人工介入"
8. `env != "staging" AND selfHealable == true` → 标记为"需人工介入（生产环境禁止自愈）"

> **公式**：`实际可自愈 = selfHealable == true AND env == "staging"`

### 心理测试（判断是否该 spawn 子 Agent）

- "这个 SQL 结果集我还要逐行看吗？" → 不需要 → 子 Agent
- "这个页面 DOM 我要完整保留吗？" → 不需要 → 子 Agent
- "这个比对结果我要二次审查吗？" → 需要 → 主 Agent

---

## WF1：批次健康巡检

目标：扫描所有活跃批次，识别失败集中的环节和错误模式。

**子 Agent 策略**：spawn 一个子 Agent 执行步骤 1-4，按判定信封返回结论。所有批次正常则返回 `{ "verdict": "OK" }`。

```
第 1 步：获取活跃批次列表
  通过 MCP 工具 workflow_batch_query 查询最近 24h 内创建的批次。
  无 MCP 则 DMS SQL：references/sql-templates.md → "活跃批次查询"

第 2 步：对每个活跃批次执行状态分布统计
  SQL 模板见 references/sql-templates.md → "批次状态分布"
  计算每个 node_type 的失败率：FAIL / (SUCCESS + FAIL)

第 3 步：触发告警规则评估
  对照 references/alert-rules.md：
  - R001: 任一 node_type 失败率 > 50% → P0 CRITICAL
  - R002: 任一 node_type 失败率 > 20% → P1 WARNING
  - R009: 批次创建 > 24h 未完成 → P1 WARNING

第 4 步：对高失败率节点提取错误分类
  SQL 模板见 references/sql-templates.md → "错误分类统计"
  识别是否为已知可自愈错误（429/RESOURCE_EXHAUSTED → S1 重试）
```

## WF2：阶段衔接检测

目标：检测链路配置的各阶段是否按序触发，识别"配置了但未执行"的阶段断裂。

**子 Agent 策略**：spawn 一个子 Agent 执行步骤 1-4（含浏览器页面抓取 + SQL + 配置对比 + 出参检查），按判定信封返回。步骤 5-6 留在主 Agent。

```
第 1 步：获取批次的链路配置
  浏览器打开 https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id={link_id}
  提取所有阶段的策略 ID 列表。浏览器不可用则 DMS SQL 查 g_strategy

第 2 步：查询批次实际执行的策略集合
  SQL 模板见 references/sql-templates.md → "批次实际执行策略"

第 3 步：对比配置 vs 执行
  - 配置有 + 执行有 = 正常
  - 配置有 + 执行无 = 阶段未触发（触发 R003 告警）
  - 配置无 + 执行有 = 额外策略（正常，可能是重跑）

第 4 步：对未触发阶段执行出参检查
  SQL 模板见 references/sql-templates.md → "出参完整性检查"
  检查前一阶段 output_json 是否包含后阶段所需入参字段
  approve 节点的 passedImg 是否为 null → 触发 R010 告警（P0 CRITICAL）

第 5 步：生成阶段衔接诊断报告
  格式："BT_xxxx 链路配置了 N 个阶段，实际执行了 M 个。
         未触发阶段：[阶段名]（策略ID: xxx）
         原因：[前一阶段] 的 output_json 缺少 [字段名]"

第 6 步：审核回调消息链路核查（来源 BT_7485）
  针对含 approve 节点的批次，当发现"审核已完成但阶段不流转"时，
  按三点链路逐段核查：
  1. doCompleteMainTaskIfAllPersonalDone 是否执行
     （有抽检配置且抽检未完成属预期等待，不告警）
  2. TOPIC_AFD_WORKFLOW2_ENGINE_RECORD_FINISH (tag: approve) 消息是否发送
     （normandy CLI: `normandy log list --source sls --project stylespot-admin-log --logstore stylespot-admin-online --query "sendWorkflowRecordFinishMsg"`）
  3. Workflow2EngineRecordFinishListener.onNodeFinish 是否被消费执行
  判定：审核完成超 1h 且链路断在消息未发送/未消费 → R022 告警（P0 CRITICAL）
  注意：runMode=test/formal 的流转开关行为不同，告警前先核对 runMode
```

## WF3：LLM 资源监控

目标：实时监控 LLM 模型资源使用率，预防配额耗尽导致的批量失败。

**子 Agent 策略**：spawn 一个子 Agent 执行步骤 1-3，正常指标完全丢弃。

```
第 1 步：获取 LLM 资源实时快照
  调用 MCP 工具 query_llm_running_progress，获取各模型运行任务数/容量/利用率

第 2 步：获取任务进度统计
  调用 MCP 工具 query_gemini_task_progress，获取各状态任务数 + 环比

第 3 步：触发告警规则评估
  - R006: 利用率 > 95% 或 429 错误 > 20% → P0 CRITICAL
  - R007: 利用率 > 80% → P1 WARNING
  - R011: 完成量环比偏差 > 30% → P1 WARNING
  - R023: LLM 文本节点 JSON 解析失败率（来源 BT_7417）
    按链路/策略/模型维度统计 errorMsg 匹配 FASTJSON.*error, offset 的记录数
    单批次 > 5% → P1 WARNING；> 20% → P0 CRITICAL

第 4 步：执行自愈策略
  429 错误占比高 → S1（429 智能重试）
  利用率持续 > 90% → S4（队列调配建议）
```

## WF4：队列积压检查

目标：检测 HANDLING 状态滞留和审核等待超时。

**子 Agent 策略**：spawn 一个子 Agent 执行步骤 1-3，仅 P0/P1 告警返回判定信封。

```
第 1 步：扫描 HANDLING 滞留记录
  SQL 模板见 references/sql-templates.md → "HANDLING 滞留扫描"
  筛选：status = 'HANDLING' AND (now - gmt_modified) > 30min

第 2 步：扫描审核等待超时
  SQL 模板见 references/sql-templates.md → "审核等待扫描"
  筛选：node_type = 'approve' AND status = 'HANDLING' AND (now - gmt_create) > 4h

第 3 步：触发告警规则评估
  - R004: HANDLING > 30min → P1 WARNING
  - R005: HANDLING > 2h → P0 CRITICAL
  - R008: approve 等待 > 4h → P1 WARNING
  - R024: 模型队列按 priority 分档饿死检测（来源 BT_7495）
    按 priority 区间拆分统计 running 数与等待时长
    全局积压 > 1000 且最低档批次连续 2h 零产出 → P1 WARNING
    零产出 > 4h → P0 CRITICAL

第 4 步：执行自愈策略
  HANDLING > 2h → S2（滞留重启，最多 2 次）
  approve 等待 > 4h → S3（审核推送，最多 3 次）
  自愈操作记录见 references/self-healing-playbook.md
```

## WF5：机器健康巡检

目标：检查 F88 应用服务器的 CPU、内存、GC、线程池指标。

**子 Agent 策略**：spawn 一个子 Agent 执行 sf CLI 查询。

```
第 1 步：查询应用 CPU 使用率
  sf metric query -a stylespot-admin -m 'system.cpu.usage' --range 1h
  sf metric query -a aifashion-xiaoer -m 'system.cpu.usage' --range 1h

第 2 步：查询 JVM 堆内存和 GC
  sf metric query -a stylespot-admin -m 'jvm.memory.heap.used' --range 1h
  sf metric query -a stylespot-admin -m 'jvm.gc.count' --range 1h

第 3 步：查询线程池
  sf metric query -a stylespot-admin -m 'thread.pool.active' --range 1h

第 4 步：触发告警规则评估
  - R013: CPU > 80% 持续 5min → P1 WARNING；> 95% → P0 CRITICAL
  - R014: 堆内存 > 85% → P1 WARNING；Full GC > 5次/h → P0 CRITICAL
  - R014: 线程池活跃/最大 > 90% → P1 WARNING
```

**降级方案**：sf CLI 不可用时跳过，在报告中标注「Sunfire CLI 不可用，需人工检查 Sunfire 大盘」。

## WF6：服务接口监控

目标：检查 HSF/MTOP/HTTP 服务成功率和 RT。

**子 Agent 策略**：spawn 一个子 Agent 执行 sf CLI 查询。

```
第 1 步：查询 HSF Provider 成功率
  核心服务：TemplatePoolToolService / MaterialProdRecordService / WorkflowBatchService
  sf metric query -a stylespot-admin -m 'hsf.provider.success_rate' --tag 'service={serviceName}' --range 1h

第 2 步：查询 MTOP 接口成功率
  sf metric query -a stylespot-admin -m 'mtop.success_rate' --range 1h

第 3 步：查询对外 TOP 接口（天工 1 项 + 知衣 7 项）

第 4 步：触发告警规则评估
  - R015: HSF 成功率 < 99% → P1；< 95% → P0
  - R015: MTOP 成功率 < 98% → P1；RT P99 > 3000ms → P1
  - R016: TOP 接口成功率 < 99% → P1；< 95% → P0
```

**降级方案**：sf CLI 不可用时通过 DMS SQL 间接推断最近 1h workflow_record_log 写入量。

## WF7：算法依赖监控

目标：检查算法网关接口成功率、异步结果处理成功率、数据处理超时。

**子 Agent 策略**：spawn 一个子 Agent 执行 sf CLI + DMS 查询。

```
第 1 步：查询算法网关接口成功率
  sf metric query -a stylespot-admin -m 'algo.gateway.success_rate' --range 1h
  sf 不可用时 DMS SQL：references/sql-templates.md → "算法网关错误统计"

第 2 步：查询异步结果处理成功率
  SQL 模板见 references/sql-templates.md → "异步回调成功率"

第 3 步：查询数据处理超时
  gen_img 预期 ≤5min / gen_video ≤10min / strategy ≤3min
  SQL 模板见 references/sql-templates.md → "节点处理超时统计"

第 4 步：触发告警规则评估
  - R017: 算法网关成功率 < 95% → P0；< 99% → P1
  - R017: 异步回调成功率 < 90% → P1
  - R018: 超时记录 > 10条/h → P1；> 30条/h → P0
```

## WF8：离线数据链路监控

目标：检查离线数据链路的产出是否按时、数据是否正确。

**子 Agent 策略**：spawn 一个子 Agent 执行 DMS SQL 查询。

```
第 1 步：检查企划案产出（爆款+企划）
  SQL 模板见 references/sql-templates.md → "企划案产出检查"
  判断：最近 24h 应有新的企划案关联批次创建

第 2 步：检查商品相关数据时效性
  SQL 模板见 references/sql-templates.md → "商品数据时效检查"
  判断：分区日期应为 T-1，超过 T-2 为异常

第 3 步：检查素材数据（模特、背景、姿势）
  SQL 模板见 references/sql-templates.md → "素材产出量检查"
  判断：对比最近 7 天日均产出，偏差 > 50% 为异常

第 4 步：检查潜力预估数据
  SQL 模板见 references/sql-templates.md → "潜力预估数据检查"

第 5 步：触发告警规则评估
  - R019: 离线数据未按时产出（超 T-2）→ P1；超 3 天 → P0
  - R020: 素材产出量环比偏差 > 50% → P1；为 0 → P0
```

## WF9：监控报告生成

目标：汇总巡检结果，生成结构化报告并推送告警。**不隔离**，在主 Agent 执行。

```
第 1 步：汇总所有告警（WF1-WF8），按严重等级排序 P0 > P1 > P2
第 2 步：汇总自愈动作记录（类型/目标/结果/剩余重试次数）
第 3 步：生成监控报告
  无告警 → 简要状态摘要
  有告警 → 结构化报告
第 4 步：推送告警（P0 立即 / P1 汇总 / P2P3 仅日报）
第 5 步：归档巡检记录
```

### 告警推送格式模板

```
[F88 监控告警] {等级} | {时间}
批次: {batch_id} | 链路: {link_name}
异常: {node_type} 失败率 {rate}% ({fail}/{total})
错误: {top_error} ({error_pct}%)
自愈动作: {action_result}
建议: {recommendation}
详情: 运行 `分析 {batch_id}` 查看完整诊断
```

## WF10：交付时效 SLA 监控（前置设计，待启用）

目标：对齐业务"保时效 48h"指标，对四个关键里程碑做超时预警。

| 里程碑 | 规则 | 默认阈值 | 升级条件 |
|--------|------|---------|---------|
| 首图生成完成 | R025 | T1 = 4h | 超 T1×2 → P0 |
| 首图审核完成 | R026 | T2 = 8h | 超 T2×2 → P0 |
| 套图生成完成 | R027 | T3 = 24h | 超 T3×2 → P0 |
| 套图审核完成 | R028 | T4 = 36h | 批次总耗时 > 44h → P0 |

```
第 1 步：拉取活跃批次清单
  SQL 模板见 references/sql-templates.md → "活跃批次列表"

第 2 步：计算各批次阶段里程碑耗时
  SQL 模板见 references/sql-templates.md → "阶段时效统计（WF10）"

第 3 步：触发时效规则评估（R025/R026/R027/R028）

第 4 步：时效告警处置建议
  生成侧超时 → 联动 WF3/WF4 核查模型队列积压与 priority
  审核侧超时 → 输出待审核任务量，提示审核人力排班
  逼近 48h 红线 → P0 推送，建议提升 priority 或拆批交付
```

启用前置条件：① 与业务确认 T1-T4 阈值 ② 确认各链路阶段名映射表。

## WF11：环节对账

目标：在批次相邻环节间建立数量对账，发现"上游产出正常、下游静默丢数据"。
来源：BT_7324（套图审核 231 → 内容上传 145，漏 86 条，根因策略 2-6 未设默认策略）。

| 对账点 | 规则 | 阈值 |
|--------|------|------|
| 套图审核 → 内容上传 gap | R029 | >5% P1 / >20% P0 |
| 内容上传 FAIL 率 | R030 | >10% P1 / >20% P0 |
| 套图生成 → 套图审核覆盖 | R031 | 覆盖 <90% P1 |

```
第 1 步：选取对账批次
  扫描最近 24h 进入终态的批次

第 2 步：逐批次执行对账
  SQL 模板见 references/sql-templates.md → "环节对账（WF11）"
  关键：approve 节点用 trace_id 关联 map_gen_img 区分首图/套图审核

第 3 步：触发对账规则评估（R029/R030/R031）
  ≤5% 记日志不告警；5-20% 警告；>20% 严重

第 4 步：生成对账告警
  模板：【F88 数据对账告警】批次/对账点/上游产出/下游接收/偏差/可能原因/建议操作
  建议操作默认含"检查策略默认配置，补推遗漏数据"（BT_7324 根因）
```
