---
name: f88-data-query
description: F88/i-FASHION 策略平台数据查询统一入口（dms-alibaba 收口）。预配 stylespot 数据库组、核心表结构本地缓存、15+ 高频 SQL 模板（批次状态/失败分析/节点流转/审核任务三层结构/策略链路配置/跨表一致性）。其他 skill 需要查 F88 数据时统一用本 skill 的模板与约定，不再各自内联 SQL。触发词：查 F88 数据、查批次 SQL、stylespot 查询、workflow_record_log、g_afd_review_job、F88 表结构、F88 SQL 模板。只读 SELECT，禁写操作。
version: 1.0.0
---

# F88 数据查询统一入口

F88/i-FASHION 策略平台所有 DB 查询的**唯一收口**：连接约定、表结构、SQL 模板、陷阱清单集中在此。其他 skill（失败分析、链路检查、审核验证、巡检）查数据时引用本 skill，不再各自维护 SQL。

## 强制规则

> **执行前必读**：涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，**必须先读取** `quderwork/f88素材生产/常用地址手册.md` 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。本 skill 内嵌的连接信息是缓存副本，以手册为准。

## 连接速查

### stylespot 库（审核/工作流/批次）

| 项 | 值 |
|----|----|
| DMS 组 | `stylespot` |
| 实例 | `rm-lgay0v5lor8396yka` |
| dbId | `5335708` |
| 覆盖表 | g_afd_review_job, g_afd_material, g_workflow_batch, workflow_record_log, g_strategy 等 |
| 环境约束 | 只查 `env='staging'` 测试数据；生产数据只读且须谨慎 |

### scenario 库（F88 素材生产表）

| 项 | 值 |
|----|----|
| 数据库名 | `scenario` |
| 实例 | `rm-8vb6631b89ix0qkwl` |
| dbId | `975919` |
| 覆盖表 | f88_ai_process_record, f88_agent_batch_job, f88_item_apply_record 等 f88_* 表 |
| 注意 | 与原创保护共用同一物理库，查询 f88_* 表时不需要 env='staging' 过滤（f88_* 表无 env 列） |

**路由判断**：查表名前缀决定用哪个库。`f88_` 开头 → scenario（975919）；`g_afd_`/`g_workflow_` 开头 → stylespot（5335708）。完整连接信息见 [shared/db-connections.md](../F88测试知识库/references/shared/db-connections.md)。

```bash
# 快速查询（≤200 行，直接输出）— stylespot 库
~/dms-alibaba/bin/dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ...（单行，无尾分号）"

# 快速查询 — scenario 库（f88_* 表）
~/dms-alibaba/bin/dms-alibaba sql query scenario --db rm-8vb6631b89ix0qkwl --sql "SELECT ...（单行，无尾分号）"

# 大批量（>200 行，结果落盘到 _results/ 再读文件）
~/dms-alibaba/bin/dms-alibaba sql run stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."
```

EBADF/环境异常时降级：`env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin /bin/zsh -c '...'`

结果文件路径：`~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{日期}/{时间}_rm-lgay0v5lor8396yka.json`，取 rows 用 `d.get('rows') or d.get('data',{}).get('rows') or []`。

## 查询铁律（违反即超时/误判）

1. `workflow_record_log` 是超大表：**必须**加 `id >= {id_threshold}`，否则 20s 超时。`{id_threshold}` 通过下方脚本动态获取，不可用硬编码 4000000/6400000
2. 失败状态值是 `'FAIL'` 不是 `FAILED`；错误信息是 `$.errorMsg` 不是 `$.errorMessage`
3. `g_strategy` 主键是 `id` 不是 `strategy_id`
4. `JSON_EXTRACT` 结果带引号，比较/输出用 `JSON_UNQUOTE()` 包裹
5. 只允许 SELECT；SQL 单行、引号内无尾分号
6. JOIN 超时拆两步单表查；>200 行走 `sql run` 读文件

## 动态 id 阈值获取

`workflow_record_log` 的 id 与 `gmt_create` 基本单调，脚本基于主键索引二分查找，返回最近 N 天（或指定时间）的最小安全 id，避免扫描无索引的 `gmt_create` 列。

```bash
# 仅打印阈值 id（默认最近 7 天）
python3 ~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py --days 7

# 获取 SQL 片段并嵌入查询
THRESHOLD=$(python3 ~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py --days 7 --output sql)
~/dms-alibaba/bin/dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ... WHERE ... AND ${THRESHOLD} ..."

# JSON 输出（含 threshold_id / cutoff / max_id）
python3 ~/.qoderwork/skills/f88-data-query/scripts/get_workflow_log_threshold.py --days 7 --output json
```

使用原则：
- 所有模板中的 `{id_threshold}` 在执行前替换为上述脚本输出。
- 脚本失败时自动回退到 `--fallback-id`（默认 6400000），并打印警告；cron 子任务建议显式指定 `--fallback-id` 防止波动。
- 不指定 `--env` 时阈值基于全表计算；若查询带 `env='staging'`，建议脚本也加 `--env staging` 以缩小阈值。

## 模板路由速查

| 想查什么 | 模板编号 |
|---------|---------|
| 批次状态分布（node_type × status） | T-01 |
| 批次链路总览（走到哪个节点） | T-02 |
| 批次元信息（execMode/status） | T-03 |
| 阶段任务数（检测任务丢失） | T-04 |
| 失败错误样本/分类统计/策略时间维度 | T-05 / T-06 / T-07 |
| 任务丢失追踪 / trace 断裂 / TPP 回调 | T-08 / T-09 / T-10 |
| 日志反查 strategy_id / 策略配置 / 链路配置 | T-11 / T-12 / T-13 |
| 审核任务层级（job_type × job_status） | T-14 |
| 跨表一致性（快照 vs 实时 URL）/ subJobId 覆盖率 | T-15 / T-16 |

完整 SQL 见 [references/sql-templates.md](references/sql-templates.md)；表结构与语义陷阱见 [references/table-schema.md](references/table-schema.md) 和 [references/pitfalls.md](references/pitfalls.md)。

**表链路关系与查询条件（必读）**：涉及多表关联、链路流转、节点状态等查询时，**必须先读取**总览文档定位业务域，再跳转详细文档 drill-down：
- **总览**：`quderwork/f88素材生产/F88全链路表速查手册.md` — 全域链路地图 + 表汇总 + 跨域关联
- **主图素材**：`quderwork/f88素材生产/主图素材数据链路速查表.md` — link 20188/20143/20206，16 张表
- **种草图文**：`quderwork/f88素材生产/种草图文数据链路速查表.md` — link 20205/20259，13 张表
- **审核**：`quderwork/f88素材生产/审核链路数据链路速查表.md` — 三层审核结构，9 张表
- **模板库**：`quderwork/f88素材生产/模板库数据链路速查表.md` — Hologres/ODPS/MySQL 三层，10 张表
- **Caption**：`quderwork/f88素材生产/Caption离线同步数据链路速查表.md` — MySQL→ODPS 同步，3 张表
- **盗图整改**：`quderwork/f88素材生产/盗图数据链路速查表.md` — ODPS→Hologres→ScheduleX，15 张表

禁止凭推理写 SQL。

## 与其他通道的分工

| 场景 | 用什么 |
|------|--------|
| 批次进度/节点重试等运维操作 | `strategy-platform` skill（MCP 主路径） |
| 失败分析、跨表一致性、配置核查、证据链 DB 验证 | 本 skill（DMS SQL；f88-failure-analysis 明确禁用 MCP 走此通道） |
| 应用日志/消费链路 | SLS：project `stylespot-admin-log`，logstore `stylespot-admin-pre`（预发）/`stylespot-admin-online`（线上），normandy CLI（`normandy log list --source sls`） |
| COOP/COEP 环境头检查 | `curl -sI https://pre-aifashion-xiaoer.alibaba-inc.com/ \| grep -iE 'cross-origin-(opener\|embedder)-policy'` |

## DMS MCP ↔ CLI 参数映射表（改造五）

> MCP 工具与 CLI 工具的参数语义不同，混用易出错。此表统一映射关系，调用前必查。

| 维度 | DMS MCP (`dms-mcp-server::executeScript`) | dms-alibaba CLI |
|------|------------------------------------------|-----------------|
| **数据库指定** | `database_id`（逻辑库 ID） | `--db`（实例名/组名） |
| **stylespot** | `database_id: 30417`（逻辑库）或 `6369910`（物理 dev） | `--db stylespot`（组名），实例 `rm-lgay0v5lor8396yka` |
| **scenario** | `database_id: 975919` | `--db scenario`（组名），实例 `rm-8vb6631b89ix0qkwl` |
| **SQL 传递** | `script` 参数，多行 SQL 直接传 | `--sql` 参数，**单行**、无尾分号 |
| **结果格式** | JSON，`columnNames` + `rows` 数组 | JSON，`rows` 数组（或 `data.rows`） |
| **大批量** | 无分页参数，结果截断 | `sql run` 子命令落盘到 `_results/` |
| **超时** | MCP 默认 60s | CLI 默认 30s，大查询可能需 `--timeout` |

**常见错误**：
- MCP 用 `database_id=5335708`（物理库）→ 应使用 `30417`（逻辑库）
- CLI 用 `--db rm-lgay0v5lor8396yka`（实例名）→ 应使用 `--db stylespot`（组名）
- CLI `--sql` 传多行 SQL → 必须压成单行

## 链式调用模板（多步查询编排）

> 高频排查场景的参数化链式模板。每一步的输出作为下一步的输入参数。

### Chain-01: 批次全链路诊断

```
输入: batch_id
Step 1 → 查批次元信息（T-03）
  SQL: SELECT id, exec_mode, status, env, gmt_create FROM g_workflow_batch WHERE id = '{batch_id}' AND env = 'staging'
  输出: batch_status, exec_mode

Step 2 → 查节点流转状态（T-02）
  SQL: SELECT node_type, status, COUNT(*) as cnt FROM workflow_record_log WHERE batch_id = '{batch_id}' AND id >= {id_threshold} AND env = 'staging' GROUP BY node_type, status
  输出: 各节点状态分布

Step 3 → 失败节点详情（仅当 Step 2 有 FAIL）
  SQL: SELECT node_type, item_id, status, error_msg, gmt_create FROM workflow_record_log WHERE batch_id = '{batch_id}' AND status = 'FAIL' AND id >= {id_threshold} LIMIT 20
  输出: 失败样本（error_msg 用于根因分析）

Step 4 → 关联审核任务（仅当涉及审核节点）
  SQL: SELECT id, job_type, job_status, sub_job_id FROM g_afd_review_job WHERE batch_id = '{batch_id}' AND env = 'staging' LIMIT 50
  输出: 审核任务状态
```

### Chain-02: 策略配置验证

```
输入: strategy_id 或 batch_id
Step 1 → 查策略配置（T-12）
  SQL: SELECT id, name, config, status FROM g_strategy WHERE id = '{strategy_id}' AND env = 'staging'
  输出: 策略配置 JSON

Step 2 → 查使用该策略的批次
  SQL: SELECT id, exec_mode, status, gmt_create FROM g_workflow_batch WHERE JSON_UNQUOTE(JSON_EXTRACT(input_info, '$.strategyId')) = '{strategy_id}' AND env = 'staging' ORDER BY gmt_create DESC LIMIT 10
  输出: 关联批次列表

Step 3 → 最近批次执行详情（复用 Chain-01 Step 2-3）
```

### Chain-03: 素材生产追踪

```
输入: item_id 或 seller_id + item_id
Step 1 → 查素材记录
  SQL: SELECT id, item_id, seller_id, status, gmt_modified FROM g_afd_material_prod_record WHERE item_id = '{item_id}' AND env = 'staging' ORDER BY gmt_modified DESC LIMIT 10
  输出: 素材记录列表

Step 2 → 查关联工作流实例
  SQL: SELECT id, batch_id, stage_type, status, input_param FROM g_workflow_instance WHERE JSON_UNQUOTE(JSON_EXTRACT(input_param, '$.itemId')) = '{item_id}' AND env = 'staging' ORDER BY gmt_create DESC LIMIT 10
  输出: 工作流实例（注意 input_param 是 JSON）

Step 3 → 查 F88 处理记录（scenario 库）
  SQL: SELECT id, batch_id, status, error_msg FROM f88_ai_process_record WHERE item_id = '{item_id}' ORDER BY gmt_create DESC LIMIT 10
  注意: 此查询走 scenario 库（dbId=975919），不是 stylespot
```

## 大结果集保护

> 防止查询结果撑爆上下文或超时。

| 场景 | 策略 |
|------|------|
| 预估 ≤ 200 行 | `sql query` 直接输出 |
| 预估 > 200 行 | `sql run` 落盘 → 读文件取 `rows` |
| `workflow_record_log` | **必须**加 `id >= {id_threshold}`（通过脚本动态获取，禁止硬编码 4000000/6400000） |
| 任何表的全表扫描 | **禁止** `SELECT *`，必须指定列 + `LIMIT` |
| JOIN 查询超时 | 拆成两步单表查询，在 agent 内存中关联 |
| JSON 列输出 | 用 `JSON_UNQUOTE(JSON_EXTRACT(...))` 避免引号嵌套 |
| cron 子任务 | 一律走 CLI `sql run` 落盘，不依赖 MCP 返回 |

**结果集大小预判规则**：
- `workflow_record_log`：按 batch_id + node_type 过滤通常 < 200 行；仅按 batch_id 过滤可能 > 1000 行
- `g_afd_review_job`：按 batch_id 过滤通常 < 100 行
- `g_workflow_instance`：按 item_id 过滤通常 < 20 行
- `f88_ai_process_record`：按 item_id 过滤通常 < 50 行

## 错误签名

失败错误分类的签名库唯一归属：`F88测试知识库/references/patterns/error-signatures.md`（T-06 的 CASE WHEN 分支与其保持一致，勿复制两份）。
