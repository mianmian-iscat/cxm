---
name: harness-runner
description: F88 AI Test Harness Pipeline 执行器。当用户说"跑Pipeline""执行诊断Pipeline""Harness跑批""用Harness分析""跑batch-failure-diagnosis"时触发。加载Pipeline YAML → 逐步调用真实MCP/DMS工具 → HEXL表达式求值 → 变量自动绑定 → 证据链归档。支持MCP→SQL自动降级，无MCP权限也能跑诊断Pipeline。
version: 2.3.0
---

# Harness Runner — Pipeline 执行 Skill (v2.3)

让 Agent 成为 Harness Pipeline 的 tool_callback：Python 负责编排逻辑（HEXL求值/DAG调度/变量绑定/证据采集），Agent 负责调用真实工具（MCP/DMS）。

**v2.0 核心变更**：引入 fallback_chain 适配器，读操作自动从 MCP 降级到 SQL（via dms-mcp-server），无需 taobao-cloth-afd-mcp 权限也能跑诊断 Pipeline。

## 前置条件

- Python 3.12+ 可用
- `~/.harness/harness/` 包已部署（Phase 0 MVP）
- `dms-mcp-server` MCP 已接入（SQL 回退通路）
- `taobao-cloth-afd-mcp` MCP 已接入（可选，有则优先使用）

## 核心工作流

### 第 1 步：初始化 Pipeline

```bash
cd ~/.harness && python3 run_pipeline.py init <pipeline_yaml_path> '<initial_context_json>'
```

示例：
```bash
python3 run_pipeline.py init ~/.harness/pipelines/batch-failure-diagnosis.yaml \
  '{"alert": {"batch_id": "BT_4251", "failure_rate": 0.28, "timeout": false, "timestamp": "20260706-143000"}}'
```

输出 JSON 包含 `adapter` 字段，指示如何调用真实工具：
```json
{
  "action": "execute_tool",
  "step_id": "query_status",
  "tool": "strategy_platform.query_batch",
  "params": {"batch_id": "BT_4251"},
  "adapter": {
    "adapter_type": "fallback_chain",
    "chain": [
      {"id": "mcp", "type": "mcp", "server": "taobao-cloth-afd-mcp", "tool": "workflow_batch_query", ...},
      {"id": "sql", "type": "dms_sql", "db_id": 5335708, "sql_resolved": "SELECT ... WHERE batch_id = 'BT_4251' ..."}
    ]
  },
  "trace_id": "diag-BT_4251-20260706-143000"
}
```

### 第 2 步：根据 adapter_type 调用真实工具

输出的 `adapter.adapter_type` 决定调用方式：

#### adapter_type = "fallback_chain"

**优先尝试 chain[0]（MCP）**，如果 MCP 无权限或失败，**自动降级到 chain[1]（SQL）**。

调用 MCP：
```
qw_mcp_call → mcp__{chain[0].server}__{chain[0].tool}
参数用 params_mapped（已做 dot-path 映射）
```

如果 MCP 返回权限错误（"缺少工具调用权限"/"permission denied"），降级到 SQL：
```
qw_mcp_call → mcp__dms-mcp-server__executeScript
参数: { dbId: chain[1].db_id, sql: chain[1].sql_resolved }
```

SQL 结果格式为 JSON rows 数组，直接作为 step result 喂给下一步。

#### adapter_type = "composite"

复合工具包含多个子步骤（通常是多条 SQL + Agent 分析）：

1. 按 `steps` 顺序执行每个子步骤：
   - `tool_type: "dms_sql"` → 用 `dms-mcp-server.executeScript` 执行 `sql_resolved`
   - `tool_type: "agent_analysis"` → Agent 根据 `input_keys` 的结果做分析判断
2. 最终把 Agent 分析结果作为 step result 喂给下一步

示例（f88_failure_analysis.analyze）：
```
Step 1: dms-mcp-server.executeScript(dbId=5335708, sql="SELECT status, node_type, COUNT(*) ...")
Step 2: dms-mcp-server.executeScript(dbId=5335708, sql="SELECT CASE WHEN ... END AS error_type ...")
Step 3: Agent 分析两步 SQL 结果，输出 {root_cause, confidence, suggestion}
```

#### adapter_type = "skill"

调用 QoderWork Skill（如 dws 发钉钉消息）：
```
调用 skill_name 对应的 Skill，用 param_mapping 转换参数
```

#### adapter_type = "mcp"

简单 MCP 工具（无回退链）：
```
qw_mcp_call → mcp__{server}__{tool}
参数用 params_mapped
```

### 第 3 步：喂结果拿下一步

```bash
python3 run_pipeline.py next <trace_id> <step_id> '<tool_result_json>'
```

循环直到 `action = "done"`。

### 第 4 步：报告结果

DONE 输出包含诊断结论、证据链路径和所有变量值。向用户汇报结论和关键变量。

---

## Stage 0-1 集成（qa-data-preflight）

harness-runner 遵循 5-Stage Test Resilience Pipeline 模型，在测试执行流水线中，于 `init` 之后、`execute` 之前插入两个前置阶段，由 `qa-data-preflight` skill 实现：

```
harness-runner init
    ↓
Stage 0: qa-data-preflight → 数据就绪检查
    ↓ 输出 DataGap 列表
Stage 1: qa-data-preflight → 造数自愈子链
    ↓ 填补缺口 / 标记 BLOCKED_DATA
Stage 2: 测试执行（qa-self-healing 管辖）
    ↓
Stage 3: 归因报告（f88-failure-analysis 管辖）
    ↓
Stage 4: 自愈流程验证（qa-self-healing 管辖）
    ↓ 故意制造故障 → 七步诊断 → 修复 → 重触发验证
```

### 集成方式

Stage 0-1 不是 harness-runner 的内部逻辑，而是通过 `adapter_type: "skill"` 调用 `qa-data-preflight`：

### Stage 3 归因报告格式（同步自 f88-failure-analysis，2026-08）

Stage 3 由 `f88-failure-analysis` 产出，报告除常规结论外包含以下增强字段，Pipeline 最终汇报（第 4 步）时应一并呈现：

- `attribution_layer`：capability / information / mechanism / diagnostic（三层归因模型，回答"该改什么"）
- `gapType`：data / prompt / engineering（三孤岛分类，回答"失败源自哪里"）
- `recommended_action` / `optimization_direction`：具体修复建议与优化方向
- BLOCKED 子分类消费：BLOCKED_DATA / BLOCKED_ENV / BLOCKED_DEP / BLOCKED_LOGIC（来自 Stage 0-2 的标签，Stage 3 按子分类输出造数恢复率、潜在覆盖率）
- 三孤岛分布统计：FAIL/BLOCKED 用例按 data/prompt/engineering 归类的占比与优化建议

详见 `f88-failure-analysis/references/result-reading.md`。

```yaml
# Pipeline YAML 中的 Stage 0-1 步骤示例
- step_id: preflight_check
  tool: qa_data_preflight.check
  adapter:
    adapter_type: skill
    skill_name: qa-data-preflight
    param_mapping:
      case_set: "$context.case_set"
      data_requirements: "$context.data_requirements"
  output_key: data_gaps

- step_id: data_self_healing
  tool: qa_data_preflight.heal
  adapter:
    adapter_type: skill
    skill_name: qa-data-preflight
    param_mapping:
      gaps: "$steps.preflight_check.output.gaps"
  output_key: healing_result
  condition: "$steps.preflight_check.output.gaps | length > 0"
```

### 执行规则

1. **Stage 0 无 DataGap** → 跳过 Stage 1，直接进入 Stage 2
2. **Stage 1 全部 GAP_FILLED** → 所有用例正常进入 Stage 2
3. **Stage 1 部分 GAP_FAILED** → 失败对应的用例标记 `BLOCKED_DATA`，其余用例正常进入 Stage 2
4. **Stage 1 全部 GAP_FAILED** → 报告造数恢复率 0%，建议人工介入

### 与 fallback_chain 的关系

Stage 0-1 的查询操作（verify_query）同样支持 fallback_chain 降级：
- 优先用 `db-query-tool` MCP 执行 SQL
- MCP 不可用时降级到 `dms-alibaba` CLI

造数操作（create_skill）不走 fallback_chain，直接调用对应 skill。

### 造数后置验证（post_verify）— 三层验证体系

每个步骤可配置 `post_verify`，在工具执行成功后自动验证结果。验证未通过时，runner 输出 `rebuild_and_retry` 动作，触发 **执行→验证→失败→重建→再验证** 的自动闭环（最多 N 轮）。

支持三种验证类型，通过 `type` 字段区分：

| type | 验证器 | 验证方式 | 典型场景 |
|------|--------|---------|---------|
| `db` | DataSetupVerifier | SQL 查询 + 阈值比对 | 数据是否落池、记录数是否达标 |
| `ui` | UIVerifier | 浏览器自动化 + 元素断言 | 页面是否显示新任务、状态标签是否正确 |
| `code` | CodeVerifier | 步骤输出结构/值断言 | 返回字段存在性、状态值匹配、格式校验 |

#### type: db — 数据库验证

```yaml
post_verify:
  type: "db"
  db_id: "5335708"
  db_name: "stylespot"
  sql_template: >
    SELECT COUNT(*) as cnt FROM g_afd_material
    WHERE env = '$ctx{env}' AND cate_id = '12345'
  threshold:
    field: "cnt"
    operator: ">="
    value: 1
  max_retries: 3
  retry_interval_ms: 5000
  message: "DB 验证：模板包素材记录数应 >= 1"
```

#### type: ui — 页面 UI 验证

通过 `alijk-agent-browser` CLI 打开目标 URL，等待页面加载后逐项检查元素断言。

```yaml
post_verify:
  type: "ui"
  url: "https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-list"
  wait_for: ".task-list-container"
  page_timeout_ms: 15000
  assertions:
    - type: "element_exists"
      selector: ".task-item[data-id='$ctx{package_id}']"
    - type: "text_contains"
      selector: ".status-badge"
      value: "待审核"
    - type: "element_count"
      selector: ".task-item"
      operator: ">="
      value: 1
  max_retries: 2
  retry_interval_ms: 5000
  message: "UI 验证：审核任务列表应包含新建任务"
```

支持的 UI 断言类型：`element_exists`（元素存在）、`text_contains`（文本包含）、`element_count`（元素数量比较）。

#### type: code — 代码走查 / 输出断言

对步骤输出（output）做结构化断言，无需外部依赖，纯内存验证。

```yaml
post_verify:
  type: "code"
  assertions:
    - path: "workflow_id"
      operator: "exists"
    - path: "status"
      operator: "=="
      value: "SUCCESS"
    - path: "workflow_id"
      operator: "matches"
      value: "^WF_"
    - path: "created_count"
      operator: ">="
      value: 1
  max_retries: 1
  retry_interval_ms: 0
  message: "代码走查：输出应包含有效 workflow_id 和成功状态"
```

支持的 code 断言操作符：`exists`、`not_exists`、`==`、`!=`、`>`、`>=`、`<`、`<=`、`matches`（正则）、`type`（类型检查）、`length`（长度）、`contains`（包含）。

#### 闭环流程

1. 步骤执行成功 → PostVerifyDispatcher 按 `type` 路由到对应 Verifier
2. 验证通过 → 进入下一步
3. 验证不通过 → runner 输出 `action: "rebuild_and_retry"`
4. Agent 收到 rebuild_and_retry → 重新执行步骤
5. 重复 1-4，直到验证通过或达到 max_retries
6. max_retries 耗尽 → 标记步骤失败，pipeline 按 on_failure 策略处理

**实现位置**：
- `~/.harness/harness/executor.py` — `DataSetupVerifier` / `UIVerifier` / `CodeVerifier` / `PostVerifyDispatcher`
- `~/.harness/run_pipeline.py` — `cmd_next` 中的 rebuild_and_retry 逻辑

---

## 预置诊断 Pipeline（v2.2 新增）

以下 Pipeline YAML 已预置在 `~/.harness/pipelines/` 目录，可直接用 `init` 加载执行。

### Pipeline 1: cross-table-consistency-check

用途：对指定批次做 g_afd_material vs g_afd_review_job 跨表 URL 一致性检查，定位 replaceImage 回写缺失问题（BT_6148 类）。

```yaml
# ~/.harness/pipelines/cross-table-consistency-check.yaml
name: cross-table-consistency-check
description: 跨表数据一致性诊断（g_afd_material vs g_afd_review_job）
write_allowed: false
estimated_duration: 120s

steps:
  - step_id: query_review_job_urls
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: fallback_chain
      chain:
        - id: sql
          type: dms_sql
          db_id: 5335708
          sql_template: >
            SELECT rj.id AS review_job_id, rj.workflow_instance_id,
                   JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) AS snapshot_url,
                   rj.gmt_create AS snapshot_time
            FROM g_afd_review_job rj
            WHERE rj.workflow_instance_id IN (
              SELECT workflow_instance_id FROM workflow_record_log
              WHERE batch_id = '$ctx{batch_id}' AND id > 4000000
            )
    output_key: snapshot_urls

  - step_id: query_material_urls
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: fallback_chain
      chain:
        - id: sql
          type: dms_sql
          db_id: 5335708
          sql_template: >
            SELECT m.id AS material_id, m.workflow_instance_id,
                   m.url AS current_url, m.gmt_modified AS last_modified,
                   m.operation_type
            FROM g_afd_material m
            WHERE m.workflow_instance_id IN (
              SELECT workflow_instance_id FROM workflow_record_log
              WHERE batch_id = '$ctx{batch_id}' AND id > 4000000
            )
    output_key: material_urls

  - step_id: compare_urls
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.query_review_job_urls.output", "$steps.query_material_urls.output"]
          prompt: >
            对比 snapshot_urls 和 material_urls，按 workflow_instance_id 关联。
            输出：1) 总审核任务数 2) URL 一致数 3) URL 不一致数及占比
            4) 不一致记录的 material 最后修改时间 vs review_job 创建时间
            5) 不一致记录中 operation_type 分布
    output_key: consistency_result
    post_verify:
      type: code
      assertions:
        - path: "total_count"
          operator: ">="
          value: 0
        - path: "mismatch_count"
          operator: ">="
          value: 0
      message: "跨表一致性检查结果应包含有效的计数"

  - step_id: verdict
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.compare_urls.output"]
          prompt: >
            根据一致性检查结果，输出诊断结论：
            - 如果 mismatch_count > 0：判定为 replaceImage 回写缺失（BT_6148 类），
              建议修复 replaceImage 接口或切换为 STREAM 模式
            - 如果 mismatch_count = 0：数据一致性正常
    output_key: diagnosis
```

### Pipeline 2: batch-stream-mode-verify

用途：验证同一链路中 BATCH 和 STREAM 模式策略的 approve 节点数据源是否与 execMode 匹配。

```yaml
# ~/.harness/pipelines/batch-stream-mode-verify.yaml
name: batch-stream-mode-verify
description: BATCH/STREAM 执行模式数据源一致性验证
write_allowed: false
estimated_duration: 90s

steps:
  - step_id: query_exec_mode
    tool: strategy_platform.query_batch
    adapter:
      adapter_type: fallback_chain
      chain:
        - id: sql
          type: dms_sql
          db_id: 5335708
          sql_template: >
            SELECT b.id AS batch_id, b.exec_mode, b.relation_id AS link_id,
                   b.status, b.gmt_create
            FROM g_workflow_batch b
            WHERE b.relation_id = '$ctx{link_id}'
            ORDER BY b.gmt_create DESC LIMIT 10
    output_key: batch_modes

  - step_id: check_approve_data_source
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: dms_sql
          db_id: 5335708
          sql_template: >
            SELECT node_type, status,
                   JSON_EXTRACT(output_json, '$.videoUrlReview.videoUrl') AS approve_url,
                   workflow_instance_id
            FROM workflow_record_log
            WHERE batch_id = '$ctx{batch_id}'
              AND node_type = 'approve'
              AND id > 4000000
            LIMIT 20
        - tool_type: agent_analysis
          input_keys: ["$steps.query_exec_mode.output", "$step.output"]
          prompt: >
            对比各批次的 exec_mode 与 approve 节点实际使用的 URL 来源：
            - BATCH 模式：approve 应从 g_afd_review_job.info 快照读取
            - STREAM 模式：approve 应从 g_afd_material.url 实时读取
            检查是否存在模式与数据源不匹配的情况。
    output_key: mode_verify_result
    post_verify:
      type: code
      assertions:
        - path: "mode_check_passed"
          operator: "exists"
      message: "模式验证结果应包含检查状态"

  - step_id: verdict
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.check_approve_data_source.output"]
          prompt: >
            输出验证结论：
            - 如果所有批次 execMode 与数据源匹配 → 正常
            - 如果存在不匹配 → 标记风险批次，建议统一为 STREAM 模式
    output_key: diagnosis
```

### Pipeline 3: subjobid-coverage-audit

用途：审计 5 类素材操作的 subJobId 传递率，定位链路追踪断裂问题（BT_5976 类）。

```yaml
# ~/.harness/pipelines/subjobid-coverage-audit.yaml
name: subjobid-coverage-audit
description: 素材操作 subJobId 覆盖率审计
write_allowed: false
estimated_duration: 60s

steps:
  - step_id: query_material_operations
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: fallback_chain
      chain:
        - id: sql
          type: dms_sql
          db_id: 5335708
          sql_template: >
            SELECT operation_type,
                   COUNT(*) AS total,
                   SUM(CASE WHEN sub_job_id IS NOT NULL AND sub_job_id != '' THEN 1 ELSE 0 END) AS with_subjobid,
                   SUM(CASE WHEN sub_job_id IS NULL OR sub_job_id = '' THEN 1 ELSE 0 END) AS without_subjobid
            FROM g_afd_material
            WHERE workflow_instance_id IN (
              SELECT workflow_instance_id FROM workflow_record_log
              WHERE batch_id = '$ctx{batch_id}' AND id > 4000000
            )
            GROUP BY operation_type
    output_key: coverage_stats

  - step_id: verdict
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.query_material_operations.output"]
          prompt: >
            按 operation_type 输出 subJobId 覆盖率：
            - 覆盖率 = with_subjobid / total * 100%
            - 覆盖率 < 50% 的操作类型标记为 ⚠️ 高风险
            - 覆盖率 = 0% 标记为 ❌ 链路追踪完全断裂
            输出修复建议：哪些操作类型需要优先补传 subJobId。
    output_key: diagnosis
```

### Pipeline 4: sharedarraybuffer-env-check

用途：验证目标环境是否返回 `Cross-Origin-Opener-Policy: same-origin` 和 `Cross-Origin-Embedder-Policy: require-corp` 响应头，定位 SharedArrayBuffer / FFmpeg WASM 加载失败问题（BT_6149 类）。对应 f88-failure-analysis Workflow 11。

```yaml
# ~/.harness/pipelines/sharedarraybuffer-env-check.yaml
name: sharedarraybuffer-env-check
description: SharedArrayBuffer 跨域隔离环境响应头检查（COOP/COEP）
write_allowed: false
estimated_duration: 30s

steps:
  - step_id: fetch_headers
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$context.target_url"]
          prompt: >
            对 $context.target_url 执行 HTTP HEAD 请求（可用 curl -sI 或等价工具），
            提取并返回 Cross-Origin-Opener-Policy 和 Cross-Origin-Embedder-Policy
            响应头的原始值（大小写不敏感）。
    output_key: headers

  - step_id: check_isolation
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.fetch_headers.output"]
          prompt: >
            判断响应头是否同时满足：
            - Cross-Origin-Opener-Policy 包含 same-origin（或 same-origin-allow-popups）
            - Cross-Origin-Embedder-Policy 包含 require-corp 或 credentialless（两者均合法；credentialless 可避免 CDN 资源缺少 CORP 头的问题）
            输出 {coop_ok, coep_ok, cross_origin_isolated, suggestion}。
    output_key: isolation_result
    post_verify:
      type: code
      assertions:
        - path: "cross_origin_isolated"
          operator: "=="
          value: true
      message: "COOP/COEP 检查：目标站点应处于跨域隔离状态"

  - step_id: verdict
    tool: f88_failure_analysis.analyze
    adapter:
      adapter_type: composite
      steps:
        - tool_type: agent_analysis
          input_keys: ["$steps.isolation_result.output"]
          prompt: >
            输出诊断结论：
            - cross_origin_isolated=true：环境正常，SharedArrayBuffer 可用
            - 否则：Nginx/网关未配置 COOP/COEP，FFmpeg WASM 将加载失败
            建议同步线上 Nginx 配置。
    output_key: diagnosis
```

### 新增 post_verify 模板（v2.2）

除已有的 db/ui/code 三种 post_verify 类型外，v2.2 新增两个组合验证模板，用于诊断 Pipeline 的关键步骤。

#### 模板：cross_table_url_verify

跨表 URL 一致性验证，用于确认 replaceImage 后两张表数据是否同步。

```yaml
post_verify:
  type: "db"
  db_id: "5335708"
  db_name: "stylespot"
  sql_template: >
    SELECT
      rj.id AS review_job_id,
      JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) AS snapshot_url,
      m.url AS material_url,
      CASE
        WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) = m.url
        THEN 'CONSISTENT' ELSE 'MISMATCH'
      END AS consistency
    FROM g_afd_review_job rj
    JOIN g_afd_material m ON rj.workflow_instance_id = m.workflow_instance_id
    WHERE rj.workflow_instance_id = '$ctx{workflow_instance_id}'
    LIMIT 1
  threshold:
    field: "consistency"
    operator: "=="
    value: "CONSISTENT"
  max_retries: 2
  retry_interval_ms: 3000
  message: "跨表 URL 一致性：g_afd_review_job.info 快照 URL 应与 g_afd_material.url 一致"
```

#### 模板：exec_mode_match_verify

执行模式匹配验证，用于确认批次的 execMode 与 approve 节点数据源一致。

```yaml
post_verify:
  type: "db"
  db_id: "5335708"
  db_name: "stylespot"
  sql_template: >
    SELECT
      b.exec_mode,
      CASE
        WHEN b.exec_mode = 'STREAM' THEN 'STREAM reads g_afd_material.url (real-time)'
        WHEN b.exec_mode = 'BATCH' THEN 'BATCH reads g_afd_review_job.info (snapshot)'
        ELSE 'UNKNOWN exec_mode'
      END AS data_source_desc,
      CASE
        WHEN b.exec_mode IN ('BATCH', 'STREAM') THEN 'VALID'
        ELSE 'INVALID'
      END AS mode_validity
    FROM g_workflow_batch b
    WHERE b.id = '$ctx{batch_db_id}'
    LIMIT 1
  threshold:
    field: "mode_validity"
    operator: "=="
    value: "VALID"
  max_retries: 1
  retry_interval_ms: 0
  message: "execMode 验证：批次执行模式应为 BATCH 或 STREAM 合法值"
```

## 降级策略总览

| Pipeline Tool | MCP 优先 | SQL 回退 | 无需MCP |
|---------------|---------|---------|---------|
| `strategy_platform.query_batch` | workflow_batch_query | SELECT from workflow_record_log + g_workflow_batch | |
| `strategy_platform.query_node_progress` | node_progress_query | SELECT GROUP BY node_type, status | |
| `strategy_platform.query_fail_reason` | query_fail_reason | SELECT errorMsg GROUP BY | |
| `strategy_platform.query_gemini_progress` | query_gemini_task_progress | SELECT from g_llm_task GROUP BY model_type, status | |
| `strategy_platform.query_llm_running` | query_llm_running_progress | SELECT from g_llm_task WHERE status=12 | |
| `strategy_platform.query_map_gen_info` | workflow_get_map_gen_info | SELECT from workflow_record_log WHERE node_type IN (gen_img,map_gen) | |
| `f88_failure_analysis.analyze` | — | 纯 SQL + Agent 分析 | **是** |
| `f88_pipeline_monitor.check_llm_health` | — | 内部自动走 SQL 回退 | **是** |
| `notify_dingtalk.send` | — | — | **是**（走 dws Skill）|

**结论**：诊断 Pipeline（batch-failure-diagnosis）全部是读操作，无需 MCP 权限即可端到端执行。

## SQL 回退的关键配置

- **DB ID**: 5335708（stylespot 生产库）— 连接详情见 F88测试知识库/references/shared/db-connections.md
- **查询安全规则**: env 过滤铁律/写操作红线/ScheduleX 只读 — 见 F88测试知识库/references/shared/query-safety-rules.md
- **ID 过滤**: `workflow_record_log` 查询必须加 `id > 4000000`，否则超时（近期批次建议 `id > 6400000` 进一步缩小扫描范围，与 f88-approve-verify-sql / f88-ffmpeg 口径一致）
- **状态值**: FAIL（不是 FAILED）、SUCCESS、HANDLING、INIT
- **错误字段**: `$.errorMsg`（不是 `$.errorMessage`），用 `JSON_EXTRACT(extra_info, '$.errorMsg')`
- **JSON 引号**: `JSON_EXTRACT` 返回带引号字符串，用 `JSON_UNQUOTE()` 去除

## 错误处理

1. **MCP 权限不足**：自动降级到 SQL 回退，不需要人工干预
2. **SQL 查询超时**：检查是否遗漏 `id > 4000000` 过滤条件
3. **HEXL 求值失败**：run_pipeline.py 输出 `action: "error"` 和详细错误
4. **写操作无权限**：输出 `fallback_message`，引导用户通过浏览器 UI 手动操作

## 关键约束

- **所有数据操作仅限预发环境**（与 F88 巡检铁律一致）
- Pipeline 执行过程中不修改任何线上数据
- 写操作（重试/推送审核）必须在 schema.json 中声明 `write_allowed: true`
- 每步调用前先校验参数（Schema validate），校验失败不执行调用
