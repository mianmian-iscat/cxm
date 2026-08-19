# Tool Reference - taobao-cloth-afd-mcp

Detailed parameter documentation for all verified MCP tools.

## workflow_batch_query

Query production batch information including stage progress.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| batchId | string | No | Batch ID (e.g. `BT_2072`), exact match |
| batchName | string | No | Batch name, **fuzzy match**, may return multiple results |

At least one parameter must be provided.

**Output**: Array of batch objects.

Batch object fields:

| Field | Type | Description |
|-------|------|-------------|
| batchId | string | Batch ID (e.g. BT_2072) |
| batchName | string | Batch name |
| batchType / batchTypeName | string | Type code / name (e.g. `link` / `链路`) |
| status / statusDesc | string | Status code / description (e.g. `PROCESSING` / `进行中`) |
| submitterId / submitterName | string | Submitter ID / name |
| createTime | string | Creation time, format: `yyyy-MM-dd HH:mm:ss` |
| bandId | string | Brand/business line ID |
| stageProgress | array | Stage progress array (see below) |

stageProgress element fields:

| Field | Type | Description |
|-------|------|-------------|
| stageUid | string | Stage unique ID (**use as stageNodeId in other tools**) |
| stage / stageName | string | Stage code / name (e.g. `DESIGN`/`设计改款`, `VIEW`/`视觉生图`) |
| status / statusName | string | `INIT`(初始化) / `PROCESSING`(进行中) / `FINISHED`(已完成) |
| totalCount | number | Total task count |
| finishCount | number | Finished count (= successCount + failedCount) |
| successCount | number | Success count |
| failedCount | number | Failed count |
| initCount | number | Initializing count |
| runningCount | number | Running count |
| inputCount | number | Input count |
| supportRetry | boolean | Whether retry is supported |
| supportTriggerApprove | boolean | Whether approval trigger is supported |

---

## get_stage_node_id

Get the stageNodeId for a specific stage within a batch. Useful for narrowing queries in `node_progress_query` and `query_fail_reason`.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
| stageName | string | Yes | Stage name, **exact match only** (e.g. "设计改款", not "改款") |

**Output**: stageNodeId string, or null if no match.

**Known stage names**: 设计改款, 视觉生图, 算法过滤, etc. Must match exactly.

---

## node_progress_query

Query node-level progress within a batch.

**Input**: `getReq` object (required):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
| stageNodeId | string | No | Stage node ID, filters to specific stage |
| nodeId | string | No | Node ID, queries single node |
| nodeType | string | No | Node type filter |
| strategyNodeId | string | No | Strategy node ID filter |

Two usage modes:
- **Full query**: only `batchId` → returns all nodes across all stages
- **Filtered query**: `batchId` + `stageNodeId` → returns nodes for that stage only (recommended for context efficiency)

**Output**: Array of node objects.

Node object fields:

| Field | Type | Description |
|-------|------|-------------|
| nodeId | string | Node unique ID |
| nodeType | string | Type: strategy, llm_text, gen_img, approve, industry_tag, season_tag, template_match, crop_head, suggest_price, push_select, etc. |
| nodeName | string | Node name |
| strategyId / strategyName | string | Parent strategy ID / name |
| stageName | string | Parent stage name |
| initCount | number | Initializing tasks |
| toSubmitCount | number | Pending submission tasks |
| runningCount | number | Running tasks |
| successCount | number | Succeeded tasks |
| failCount | number | Failed tasks |

---

## query_fail_reason

Get categorized failure reason statistics for a node or stage.

**Input**: `getReq` object (required):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
| nodeId | string | No* | Node ID |
| stageNodeId | string | No* | Stage node ID |
| strategyNodeId | string | No* | Strategy node ID |

*Must provide at least one of: nodeId, stageNodeId, strategyNodeId. Calling with only batchId will fail with "未明确具体的环节或策略或节点".

**Recommended**: `batchId` + `stageNodeId` for stage-wide overview, or `batchId` + `nodeId` for specific node details.

**Output**: Array of failure reason objects.

| Field | Type | Description |
|-------|------|-------------|
| nodeName | string | Node name |
| nodeId | string | Node ID |
| stageName | string | Stage name |
| strategyName | string | Strategy name |
| failCounts | array | Failure reason breakdown |
| failCounts[].reason | string | Failure reason description (may be JSON) |
| failCounts[].count | number | Count for this reason |

---

## workflow_fail_retry

Retry failed tasks for a specific node.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
| nodeId | string | Yes | Node ID (from node_progress_query) |

**Precondition**: Check `supportRetry === true` in stageProgress before calling.

---

## workflow_trigger_approve

Mark specified approve nodes to use "slice approval" (切块审核) mode. This is a **pre-configuration step**, not the actual task generation trigger.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
| nodeIds | string[] | Yes | Array of approve node IDs (nodeType === "approve", from node_progress_query) |

**Precondition**: Check `supportTriggerApprove === true` in stageProgress before calling.

**Verification**: After calling both workflow_trigger_approve and workflow_try_push_approve_task, call `workflow_batch_query` and confirm the stage's `supportTriggerApprove` has flipped to `false`. This is the success signal — it means the slice approval has been submitted and the operation window is now closed.

**How to get nodeIds**: Call `node_progress_query({getReq: {batchId, stageNodeId}})`, filter results where `nodeType === "approve"`, collect their `nodeId` values.

**Output**: null (null return indicates accepted call, not failure)

**Relationship with `workflow_try_push_approve_task`** — these two tools are sequential, not alternatives:
1. `workflow_trigger_approve` (**Step 1, optional**): Marks nodes for slice approval mode. Skip if ordinary approval is sufficient.
2. `workflow_try_push_approve_task` (**Step 2, core**): Actually generates the approval tasks immediately, bypassing the scheduled timer.

Do NOT confuse: trigger_approve sets the approval mode flag; try_push_approve_task triggers task generation.

---

## workflow_try_push_approve_task

将批次中处于 `init` 状态的审核任务推进到 `toSubmit`（待提交），即触发排队提交至审核系统。

**入参**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| batchId | string | 是 | 批次 ID |

**出参**: null（返回 null 表示调用成功，不代表失败）

**调用后验证**：立即跟查 `node_progress_query({getReq: {batchId, stageNodeId}})`，确认审核环节的 `initCount` 归零、`toSubmitCount` 相应增加，即为成功。

**使用时机**：审核环节（`stageName` 含"审核"）出现 `initCount > 0` 且任务未推进时调用。调用前无需额外前置条件检查。

**注意**：审核节点 `nodeType` 为 `approve`，一个环节可能含多个审核节点（按策略拆分），`toSubmitCount` 之和即为本次推送的总任务数。

---

## workflow_get_map_gen_info

查询批次的 MAP 图片生成情况，返回每个 job 的完成状态。用于"套图生产"环节的进度核查。

**入参**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| batchId | string | 是 | 批次 ID |

**出参**: 数组，每条记录代表一个 MAP 生图 job。

| 字段 | 类型 | 说明 |
|------|------|------|
| nodeId | string | 节点 ID（同一批次通常为同一个节点） |
| nodeName | string | 节点名称（如"Map生图"） |
| strategyName | string | 所属策略名 |
| stageName | string | 所属环节（如"套图生产"） |
| targetCount | number | 该 job 的目标生图数量 |
| successCount | number | 该 job 的成功数量 |
| failCount | number | 该 job 的失败数量 |
| workflowRecordId | number | 工作流记录 ID |
| jobId | number | Job ID |

**核心分析方法**：
- **job 总数**：数组长度，即该批次共有多少个 MAP 生图 job
- **单 job 成功率**：`successCount / targetCount`，100% 表示该 job 全量完成
- **整体完成判断**：所有 job 的 `successCount === targetCount` 且 `failCount === 0`

**注意**：同一个 nodeId 可能对应多条记录，MAP 生图按 job 维度拆分，一个节点可发起多次 job。

---

## query_gemini_task_progress

Query Gemini/LLM task generation progress — **cumulative statistics view**. Shows all-time task distribution across models and statuses. Use for assessing overall platform task health, comparing time-window trends, and identifying error-rate spikes.

**Input** (all optional):

| Parameter | Type | Description |
|-----------|------|-------------|
| taskStatusList | int[] | Task status codes: 0(DRAFT), 10(PRE_SUBMIT), 11(SUBMIT), 12(PROCESSING), 20(SUCCESS), 21(FINISH), 30(EXEC_FAIL), 31(CANCEL), 32(TIMEOUT), 33(SUBMIT_FAIL) |
| createTimeStart | string | Start time (inclusive), format: `yyyy-MM-dd HH:mm:ss` |
| createTimeEnd | string | End time (exclusive), format: `yyyy-MM-dd HH:mm:ss` |
| taskSceneList | string[] | Task scenes: STRATEGY_PLATFORM, LLM_TEXT, LLM_TEXT_TRY_RUN, GEN_IMG, GEN_IMG_TRY_RUN, GEN_IMG_MAP, GEN_IMG_MAP_TRY_RUN |

**Output**:

Top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| totalCount | number | Total task count across all models |
| totalSuccessCount | number | Total terminal tasks (status >= 20, **NOT pure success**) |
| overallProgressPercent | number | Overall progress: terminal / total * 100 |
| modelProgressList | array | Per-model breakdown (see below) |

modelProgressList element fields:

| Field | Type | Description |
|-------|------|-------------|
| modelName | string | Model name (e.g. gemini-3-pro-image-preview, gemini-3.1-flash-image-preview) |
| totalCount | number | Total tasks for this model |
| successCount | number | Terminal tasks for this model (status >= 20) |
| progressPercent | number | Progress: terminal / total * 100 |
| statusCountList | array | Status breakdown (see below) |

statusCountList element fields:

| Field | Type | Description |
|-------|------|-------------|
| statusCode | int | Status code (0/10/11/12/20/21/30/31/32/33) |
| statusDesc | string | Status description (e.g. 任务执行成功, 任务提交失败) |
| count | number | Number of tasks in this status |

**Important**: `successCount`/`totalSuccessCount` includes ALL terminal states (success + fail + cancel + timeout), not pure success. A model showing `progressPercent: 100` may still have thousands of failed/cancelled tasks — always check `statusCountList` for the real breakdown.

**Time-window usage**: Pass `createTimeStart`/`createTimeEnd` to compare different time periods for trend analysis (e.g. yesterday vs today throughput).

---

## query_llm_running_progress

Query current LLM production progress — **real-time snapshot view**. Shows which batches are actively consuming LLM resources right now, grouped by taskScene + modelType.

**Input**: None.

**Output**: Array of running task groups. Empty array if nothing is running.

Running task group fields:

| Field | Type | Description |
|-------|------|-------------|
| taskScene | string | Task scene (e.g. GEN_IMG, LLM_TEXT) |
| modelType | string | Model name (e.g. gemini-3.1-flash-image-preview) |
| runningCount | number | Total running tasks for this scene+model combination |
| batchCounts | array | Per-batch breakdown (see below) |

batchCounts element fields:

| Field | Type | Description |
|-------|------|-------------|
| batchId | string | Batch ID (e.g. BT_2218) |
| batchName | string | Batch name |
| runningCount | number | Running tasks from this batch |

**Key use case**: When a batch's progress appears stalled, check this tool to see if (a) the batch has running tasks (model may be slow) or (b) the batch has NO running tasks (may be preempted by other batches monopolizing capacity).

---

## stage_progress_query (DEPRECATED)

**Do not use.** Returns same data as `workflow_batch_query`'s stageProgress field but without batch metadata. Use `workflow_batch_query` instead.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| batchId | string | Yes | Batch ID |
