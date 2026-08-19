# 排查路径详细手册

本文档包含五大排查路径的完整步骤、SQL 模板和常见根因。根据 SKILL.md 路由表定位后，读取对应章节。

---

## 路径一：TPP 算法任务无回调

症状：workflow 节点（crop_head/gen_img 等）永久 HANDLING，g_admin_task 的 task_status=10 且 gmt_modified=gmt_create。

### 排查步骤

1. 查 workflow 记录确认卡住：
```sql
SELECT id, batch_id, node_type, status, gmt_create, gmt_modified,
  JSON_EXTRACT(extra_info, '$.errorMsg') as error_msg
FROM workflow_record_log WHERE id = {recordId}
```

2. 查关联的 g_admin_task：
```sql
SELECT task_id, task_type, task_status, job_id, tpp_task_id, scene_code,
  gmt_create, gmt_modified
FROM g_admin_task WHERE job_id = {workflowRecordLogId}
```
- task_status=10 且 gmt_modified=gmt_create → TPP 从未回调

3. 确认是否全局性问题：
```sql
SELECT task_type, scene_code, task_status, COUNT(*) as cnt,
  MIN(gmt_create) as earliest, MAX(gmt_create) as latest
FROM g_admin_task
WHERE task_type = {taskType}
GROUP BY task_type, scene_code, task_status
```

4. **检查 TPP 机器状态**（最常见根因）：
   - 打开 TPP 平台：https://tppnext.alibaba-inc.com/web/v1/pyinfer/scene/{sceneId}/machine
   - 查看"在线机器数/目标机器数"，如果是 0/0 → 线上没部署机器，任务永远无法执行
   - 查看集群状态是否为"运行中"

5. 检查 Diamond 超时配置：
   - dataId=algo-admin-task-config, groupId=stylespot-admin
   - 确认对应 taskType + sceneCode 有 timeoutSec 配置
   - 没有配置 → TaskTimeoutProcessor 永远不会触发超时（canSetTimeout 返回 false）

### 常见根因

| 根因 | 表现 | 修复 |
|---|---|---|
| TPP 场景无机器 | 在线机器数=0/0 | TPP 平台扩容机器 |
| Diamond 无超时配置 | task_status=10 永不超时 | 添加 timeoutSec 配置 |
| TPP 算法服务异常 | 有机器但任务失败 | 查 TPP 日志 |
| 回调地址不可达 | TPP 执行完但回调失败 | 检查回调 URL 配置 |

### 关键代码

- 任务提交：ImageCropProcessor.process() → taskService.submitTask()
- 超时判断：BaseTaskHandler.canSetTimeout() → TaskConfigV2.getTaskConfigDTO(taskType, sceneCode)
- 超时处理：TaskTimeoutProcessor（SchedulerX 定时任务）→ trySetTimeout() → callback(TIMEOUT)
- 回调分发：TaskCallbackProcessor → @TaskCallback 注解按 taskType+sceneCode+taskStatus 路由

---

## 路径二：审核平台→workflow 回调丢失

症状：审核平台已驳回/通过，但 workflow_record_log 的 approve 记录仍为 HANDLING。

> **先区分两类"审核不流转"**（2026-08-05 新增）：
> - **审核任务根本无法创建**（记录全部 INIT、runningCount=0、前台无任务）→ 可能是分配算法整除/取余校验不一致（BT_7495，errorMsg 含"构建子任务失败...期望分配数量(N)与实际分配数量(M)不一致"，常见于待分配总量不能被参与人数整除时）。当日已修复，回归方式：构造不能整除的记录数验证子任务可创建。
> - **审核已完成但不流转下游** → 回调三条件框架（BT_7485）：`TOPIC_AFD_WORKFLOW2_ENGINE_RECORD_FINISH` 消息发送需同时满足 ① 所有个人审核+抽检任务完成（`doCompleteMainTaskIfAllPersonalDone`；审核人=抽检人时抽检 totalCount=0 直接完成，审核人≠抽检人时需等 job_type=5 抽检任务）② runMode 对应回调开关开启（runMode=test 与 formal 行为可能不同）③ MQ 消息发送成功。任一缺失即不流转。
> - **排查顺序**：主任务 status=4（抽检中）→ 查抽检任务是否完成，属预期等待非故障；status=5（已完成）但下游没动 → 查 MQ 发送与消费；卡 PROCESSING → 查 runMode 与个人审核完成度。

### 回调链路

```
审核员提交 → submitTaskResult() → updateTaskProgress()
→ 审核员点"完成审核" → InspectionTaskAppService 检查所有子任务完成
→ completeMainTaskAndTriggerDownstream() → approveProcessor.finishMainTaskApprove()
→ MAIN_TASK_FINISH MQ → handleMainTaskFinished() 遍历子任务
→ SUB_TASK_FINISH MQ → handleSubTaskFinished()
→ sendSuccessMessage() → buildOutputData() → WorkflowRecordFinishMsg MQ
→ Workflow2EngineRecordFinishListener → onNodeFinish() → 更新 workflow_record_log
```

### 排查步骤

1. 查审核任务状态：
```sql
SELECT id, job_type, job_status, parent_job_id, relation_id,
  gmt_create, gmt_modified,
  JSON_EXTRACT(info, '$.questionType') as question_type
FROM g_afd_review_job WHERE id = {taskId}
```

2. 查关联的 workflow 记录：
```sql
SELECT id, batch_id, node_type, status, gmt_create, gmt_modified,
  JSON_EXTRACT(extra_info, '$.notPass') as not_pass,
  JSON_EXTRACT(extra_info, '$.reproductionIds') as reproduction_ids
FROM workflow_record_log WHERE id = {relationId}
```

3. 查主任务和所有子任务：
```sql
SELECT id, job_type, job_status, relation_id, gmt_create, gmt_modified
FROM g_afd_review_job WHERE parent_job_id = {parentJobId}
```

4. 对比时间线：主任务完成时间 vs 子任务提交时间 vs workflow 记录更新时间

### 常见根因

| 根因 | 表现 | 修复 |
|---|---|---|
| questionType 不支持 | fillOutputDataByQuestionType 只处理 1/2/3 | 增加对应 questionType 分支 |
| 主任务提前完成 | 有子任务仍 PENDING 时主任务已 COMPLETED | 修复完成判断逻辑 |
| 子任务晚于主任务完成 | 子任务提交时主任务已完成，不触发回调 | 补发 SUB_TASK_FINISH 或手动回调 |
| MQ 消息丢失 | SUB_TASK_FINISH 发送但消费失败 | 查 SLS 日志，补发消息 |
| ReviewJobNormalSubTaskInfo 缺字段 | 反序列化丢失审核数据 | 增加对应字段 |
| 分配校验不一致（BT_7495） | 记录全部 INIT、errorMsg 含"期望分配数量与实际分配数量不一致"、triggerApprove 也失败 | 修分配算法整除/取余校验（2026-08-05 已修复），临时可调整参与人配置绕过 |
| 回调三条件缺失（BT_7485） | 审核完成但批次不流转；抽检未完成/runMode 开关关闭/MQ 发送失败 | 按三条件逐项排查：等抽检完成、核对 runMode、查 MQ 发送消费日志 |

### 关键代码

- 回调入口：ApproveProcessor.handleMainTaskFinished() / handleSubTaskFinished()
- 输出构建：ApproveProcessor.fillOutputDataByQuestionType() — 只支持 questionType 1/2/3
- 子任务信息：ReviewJobNormalSubTaskInfo — 只有 singleImage/multiImage/video 三种内容
- 超时 guard：Workflow2EngineImpl.onNodeFinish() line 496 — OVER_STATUS_LIST=[SUCCESS,FAIL,PERM_FAIL]

---

## 路径三：workflow 节点生命周期异常

症状：节点状态不符合预期（永久 HANDLING、意外 FAIL、重生不触发等）。

### 排查步骤

1. 查批次状态：
```sql
SELECT id, batch_id, status, relation_id, relation_type, source_type,
  gmt_create, gmt_modified
FROM g_workflow_batch WHERE batch_id = '{batchId}'
```
- TERMINATED → 批次被终止，所有未完成节点会 FAIL（errorMsg="批次终止"）

2. 查节点执行统计：
```sql
SELECT node_type, status, COUNT(*) as cnt
FROM workflow_record_log WHERE batch_id = '{batchId}' AND id > 4000000
GROUP BY node_type, status ORDER BY node_type, status
```

3. 查失败节点详情：
```sql
SELECT id, node_type, status, gmt_create, gmt_modified,
  JSON_EXTRACT(extra_info, '$.errorMsg') as error_msg
FROM workflow_record_log
WHERE batch_id = '{batchId}' AND status = 'FAIL' AND id > 4000000
ORDER BY gmt_create
```

4. 查重生状态（approve 驳回后）：
```sql
SELECT id, status, gmt_create, gmt_modified,
  JSON_EXTRACT(extra_info, '$.notPass') as not_pass,
  JSON_EXTRACT(extra_info, '$.reproductionIds') as reproduction_ids,
  JSON_EXTRACT(extra_info, '$.reproductionStatus') as reproduction_status
FROM workflow_record_log
WHERE batch_id = '{batchId}' AND node_type = 'approve'
  AND JSON_EXTRACT(extra_info, '$.notPass') = true
  AND id > 4000000
```

### 重生机制

- 触发条件：approve 节点 SUCCESS + extraInfo.notPass=true
- trySetReproductionStatus()：找上游节点（GET_IMG/MAP_GEN_IMG/CROP_HEAD/FABRIC_TRYON），设 reproductionStatus=AVAILABLE
- 用户提交 POST /reproduction → execReproduction() → 克隆 workflow instance 重新执行
- 支持重生的节点类型：GET_IMG, MAP_GEN_IMG, CROP_HEAD, FABRIC_TRYON

---

## 路径四：素材替换副作用（replaceImage 跨表不一致）

症状：replaceImage 后下游节点输出旧图片、BATCH 和 STREAM 模式结果不一致、审核任务快照与实际素材 URL 不匹配。关联 Bug：BT_6148。

根因：replaceImage 只更新 g_afd_material.url，不回写 g_afd_review_job.info 中的快照 URL。BATCH 模式从 review_job.info 读快照，STREAM 模式实时查 g_afd_material，导致两种模式拿到不同 URL。

### 排查步骤

1. 对比 g_afd_material.url 与 g_afd_review_job.info 快照 URL：
```sql
SELECT m.id as material_id, m.url as material_url, m.gmt_create as material_time,
  rj.id as review_job_id, rj.job_type, rj.job_status,
  JSON_EXTRACT(rj.info, '$.imageUrl') as snapshot_url,
  JSON_EXTRACT(rj.info, '$.questionType') as question_type
FROM g_afd_material m
JOIN g_afd_review_job rj ON m.relation_id = rj.relation_id
WHERE m.relation_id = {workflowRecordLogId}
  AND m.url != JSON_EXTRACT(rj.info, '$.imageUrl')
```
- 结果非空 → 存在跨表不一致，下游 BATCH 模式会拿到旧 URL

2. 查批次执行模式：
```sql
SELECT s.id as strategy_id, s.name as strategy_name, s.exec_mode
FROM g_strategy s
JOIN g_workflow_batch b ON b.relation_id = s.id
WHERE b.batch_id = '{batchId}'
```
- execMode=BATCH → 下游从 review_job.info 快照读 URL，replaceImage 后不会更新
- execMode=STREAM → 下游实时查 g_afd_material.url，replaceImage 后立即生效

3. 批量扫描受影响记录：
```sql
SELECT m.relation_id, m.url as new_url,
  JSON_EXTRACT(rj.info, '$.imageUrl') as old_url,
  rj.job_status, b.batch_id, b.status as batch_status
FROM g_afd_material m
JOIN g_afd_review_job rj ON m.relation_id = rj.relation_id
JOIN workflow_record_log wrl ON m.relation_id = wrl.id
JOIN g_workflow_batch b ON wrl.batch_id = b.batch_id
WHERE m.url != JSON_EXTRACT(rj.info, '$.imageUrl')
  AND b.status = 'PROCESSING'
ORDER BY m.gmt_create DESC
LIMIT 50
```

### 决策树

```
replaceImage 后下游输出异常？
├─ 查 execMode
│  ├─ BATCH → 快照未更新，需手动回写 review_job.info 或等待批次重跑
│  └─ STREAM → 实时查 material，检查 material.url 是否已更新
├─ 查下游节点类型
│  ├─ approve → 审核员看到的是快照 URL（BATCH）还是实时 URL（STREAM）
│  └─ gen_img/composition → 算法任务提交时取的哪个 URL
└─ 查时间线：replaceImage 时间 vs 下游节点创建时间 vs 下游节点读取 URL 时间
```

---

## 路径五：执行模式（execMode）异常

症状：同策略 BATCH 和 STREAM 结果不同、BATCH 模式 replaceImage 后不生效、批次卡在 approve/HANDLING 不推进。

### 排查步骤

1. 确认策略执行模式：
```sql
SELECT id, name, exec_mode, gmt_create, gmt_modified
FROM g_strategy WHERE id = {strategyId}
```

2. 查该策略下所有批次的执行模式分布：
```sql
SELECT b.batch_id, b.status, b.relation_id,
  s.exec_mode, s.name as strategy_name,
  COUNT(wrl.id) as record_count,
  SUM(CASE WHEN wrl.status = 'HANDLING' THEN 1 ELSE 0 END) as handling_count
FROM g_workflow_batch b
JOIN g_strategy s ON b.relation_id = s.id
LEFT JOIN workflow_record_log wrl ON wrl.batch_id = b.batch_id
WHERE b.relation_id = {strategyId}
  AND b.status = 'PROCESSING'
GROUP BY b.batch_id, b.status, b.relation_id, s.exec_mode, s.name
ORDER BY b.gmt_create DESC
```

3. BATCH 模式卡住时的特殊处理：
- 预发环境 BATCH 模式依赖 SchedulerX 定时任务触发批次累积提交
- 预发 SchedulerX 可能未运行或间隔极长，导致批次卡在 COLLOCATION/approve/HANDLING
- 手动触发 API（/api/workflow/batch/triggerAccumulate 等）在预发通常返回空
- **替代方案**：改用 STREAM 模式策略测试，STREAM 立即创建审核任务

### 常见根因

| 根因 | 表现 | 修复 |
|---|---|---|
| BATCH 快照未更新 | replaceImage 后下游仍用旧 URL | 手动回写 review_job.info 或切 STREAM |
| 预发 SchedulerX 未运行 | BATCH 批次永久卡住 | 切 STREAM 模式测试 |
| execMode 配置错误 | 预期 STREAM 实际 BATCH | 修改策略 execMode |
