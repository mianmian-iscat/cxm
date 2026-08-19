# 常用工作流

> 从 SKILL.md 提取的详细工作流。执行具体运维操作时按需读取。

## 工作流 1：批次进度查询

最高频操作，用户问"XX批次跑到哪了？"

```
第 1 步：workflow_batch_query({batchId: "BT_xxxx"})
         → 获取批次状态 + stageProgress 数组
第 2 步：找到 status === "PROCESSING" 的环节 → 即当前所在环节
第 3 步：汇总："批次 XX 正在运行 '视觉生图' 环节，已完成 120/200，失败 5"
```

stageProgress 关键字段：`stageName`、`status`（"INIT"/"PROCESSING"/"FINISHED"）、`totalCount`、`successCount`、`failedCount`、`runningCount`。

**重要：多个环节可以同时处于 PROCESSING 状态**（例如视觉生图和视觉审核并行运行）。扫描时不要只取第一个 PROCESSING 环节，要遍历所有 PROCESSING 环节。

**不要止步于此。** 环节级汇总是用户在产品界面上已能看到的信息，真正的价值在于继续执行工作流 2 的深度调查。对所有 PROCESSING 环节，都应主动往下查。

## 工作流 2：活跃环节深度调查

对每个 PROCESSING 环节，**并行**执行以下查询：

```
并行 A：query_llm_running_progress()
        → 确认该批次是否有 LLM 任务在运行
        → 查看使用的模型及占用 slot 数量
        → 检查其他批次是否在同一模型上竞争资源

并行 B：node_progress_query({getReq: {batchId, stageNodeId}})
        → 获取节点级拆分（按策略和节点类型）
        → 找出 failCount > 0 的节点
        → 注意：节点按 strategyName 分组，多个策略可能并行运行

并行 C：query_fail_reason({getReq: {batchId, stageNodeId}})
        → 获取整个环节的失败原因分布
        → 解析错误信息，识别根因类别（见下表）
```

`stageNodeId` 直接从 stageProgress 的 `stageUid` 字段取得，无需额外调用 `get_stage_node_id`。

**套图生产环节额外查询**：当 PROCESSING 环节为「套图生产」时，在并行查询基础上额外调用：

```
workflow_get_map_gen_info({batchId})
  → 查看各 MAP 生图 job 的完成情况
  → 汇报重点：job 总数、各 job 成功率（successCount/targetCount）、有无失败
```

汇报示例：
```
【MAP生图】共 5 个 job，2 个未完成 ⚠️
  - job #1113984：16/18（89%），failCount=2
  - job #1113986：12/18（67%），failCount=6
  - 其余 3 个 job 已完成（100%）
```

**失败原因分类：**

| 错误信息特征 | 类别 | 处置建议 |
|-------------|------|---------|
| `429` / `RESOURCE_EXHAUSTED` / `Resource has been exhausted` | Quota 耗尽 | 正常现象，但已 fail 的任务不会自动恢复，需调用 `workflow_fail_retry` 重置 |
| `500` / `INTERNAL` / `Internal error encountered` | 模型内部错误 | 少量可接受，大量需关注上报 |
| `无法解析 Gemini API 响应格式` / `Failed to parse response` | 响应解析失败 | 通常伴随 429，少量可忽略 |
| `CutEdgeExceedRange` / 其他业务逻辑错误 | 数据质量问题 | 需人工排查具体数据 |

**LLM 状态与失败原因交叉验证：**
- 批次有 running 任务 + 主要是 429 失败 → **Quota 压力，正常，重试后可恢复**
- 批次有 running 任务 + 主要是 500 失败 → **模型侧异常，需关注上报**
- 批次无 running 任务 + 有失败 → **被其他批次抢占，或任务卡住**

**汇报格式：**

```
【LLM资源】BT_xxxx 占用 gemini-3.1-flash-image-preview 共 3138 slots（占总量 84%）
【节点进展】视觉生图 · 两个策略并行：
  - 首图整身tryon · 生图：running 1515，成功 655，失败 1034
  - 首图三图tryon · 生图：running 1623，成功 113，失败 953
【失败原因】99% 为 429 Quota 耗尽，需手动重试重置失败任务
```

## 工作流 3：重试失败任务

进入 `fail` 状态的任务不会自动恢复，包括 429 导致的失败——必须手动调用重试接口重置。

```
第 1 步：（来自工作流 2）找出 failCount > 0 的节点
         → 从 node_progress_query 结果取 nodeId
         → 执行前确认 stageProgress.supportRetry === true
第 2 步：workflow_fail_retry({batchId, nodeId})
         → 不要将返回值（null）告知用户
         → 立即跟查 node_progress_query({getReq: {batchId, nodeId}})
第 3 步：通过 node_progress_query 结果确认重试是否生效
         → 成功：failCount 归零，initCount 增加相同数量
         → 告知用户："已重试，原 X 条失败任务已重新入队"
         → 若 failCount 未变化：重试未被接受，告知用户失败
```

**注意**：重试仅重置指定节点的失败任务，多个节点有失败时需逐个 nodeId 分别调用。如需确认 `workflow_fail_retry` 的入参格式，查阅 [tool-reference.md](../tool-reference.md)。

**重试确认成功后，主动询问用户：**

```
"是否需要设置定时重试？可以每隔一段时间自动将失败任务重新入队，直到该环节完成。
请确认：
1. 要重试的节点（当前为：[nodeName] / [nodeId]）
2. 重试间隔（建议 10~30 分钟）"
```

用户确认后，使用 CronCreate 工具按约定间隔创建定时重试任务。当 node_progress_query 显示 failCount === 0 且 runningCount === 0 时，自动调用 CronDelete 取消定时任务。

## 工作流 4：审核环节操作

**触发时机**：遍历所有 PROCESSING 环节，找到 `supportTriggerApprove === true` 的环节。

**生图环节永远不支持审核触发**（`supportTriggerApprove` 恒为 false），审核操作只会出现在 stageName 含「审核」的环节（如改款审核、视觉审核）。

**用户意图映射**：用户说"视觉生图能审核了不""生图审核一下"等模糊表达，真实指向是与生图配套的「视觉审核」环节，而非生图环节本身。遇到此类表达，应直接定位 stageName 含「审核」且 PROCESSING 的环节，而不是去看生图环节。

两个工具是**顺序关系**，必须依次执行：

```
第 1 步（询问用户）：确认触发范围
  → node_progress_query({getReq: {batchId, stageNodeId}})
  → 找到所有 nodeType === "approve" 的节点
  → 向用户展示各策略的任务量：
      策略A（首图整身tryon）：682 条
      策略B（首图多模板）：114 条
  → 询问："是否全部触发切块审核，还是跳过任务量少的策略？"
  → 等待用户确认，拿到要触发的 nodeId 列表

第 2 步（必选·打标）：workflow_trigger_approve
  → 标记哪些节点走切块审核，必须在生成任务前完成
  → workflow_trigger_approve({batchId, nodeIds: [用户确认的 nodeId 列表]})
  → 返回 null 为正常

第 2 步（必选·生成任务）：workflow_try_push_approve_task
  → 立即为批次生成审核任务，跳过定时器
  → workflow_try_push_approve_task({batchId})
  → 返回 null 为正常

第 3 步（验证）：查询环节状态确认提交成功
  → workflow_batch_query({batchId})
  → 找到审核环节，确认 supportTriggerApprove 变为 false
  → supportTriggerApprove === false 表示审核任务已提交至系统，操作窗口关闭
  → 告知用户："审核任务已提交，稍后去审核平台查看是否已产生任务"
  → 注意：审核平台存在时间差，不要断言任务已在审核平台可见
```

## 工作流 5：平台任务健康巡检（定时巡逻）

用时间窗口切片评估平台整体任务健康状况，适合每日定时巡检。

```
第 1 步：query_gemini_task_progress({
          createTimeStart: "昨天 00:00:00",
          createTimeEnd: "今天 00:00:00"
        })
         → 获取昨日任务统计作为基线

第 2 步：query_gemini_task_progress({
          createTimeStart: "今天 00:00:00",
          createTimeEnd: "当前时间"
        })
         → 获取今日任务统计

第 3 步：对比两个时间窗口的 progressPercent 和 statusCountList
         → 整体消耗速率是否正常？
         → 某模型的 submitFail（状态码 33）比例是否在飙升？
         → 是否有大量任务卡在 DRAFT（状态码 0）？

第 4 步：query_llm_running_progress()
         → 交叉验证：当前哪些批次在消耗资源？
         → 是否有某个批次独占某模型的容量？

第 5 步：生成健康报告：
         → 整体进度趋势（推进中 / 停滞 / 恶化）
         → 各模型健康状况（错误率、吞吐量）
         → 资源竞争分析（哪些批次在抢占）
         → 可操作的建议
```

**与批次级巡检结合**：对特定批次进行每日巡检时，先执行工作流 1（进度查询）+ 工作流 2（失败调查），再用本工作流的平台级视角解释停滞原因。

## 工作流 6：approve 节点深度排查（execMode + 跨表分析）

**触发时机**：approve 节点 FAIL 或 HANDLING 卡住，或用户反馈"替换图片后下游还是旧数据"。

```
第 1 步：确认批次 execMode
  → 通过 dms-mcp-server 或 dms-alibaba 查询 g_workflow_batch：
    SELECT id, exec_mode, relation_id FROM g_workflow_batch WHERE batch_id = '{batch_id}'
  → execMode 取值：BATCH（快照模式）/ STREAM（实时模式）
  → 同一链路不同批次可能配置不同 execMode，不能假设一致

第 2 步：对比 approve 节点的 URL 来源
  → 对同一 workflow_instance，分别提取：
    a) g_afd_review_job.info → $.videoUrlReview.videoUrl（BATCH 模式读取的快照值）
    b) g_afd_material.url（STREAM 模式读取的实时值）
  → 两者不一致 → replaceImage 只更新了 material 未回写 review_job（BT_6148）

第 3 步：判断影响范围
  → execMode=BATCH + 快照不一致 → approve 使用旧 URL，下游拿到过期数据 ❌
  → execMode=STREAM + 快照不一致 → approve 实时读 material，不受影响 ✅
  → 批量扫描不一致占比：
    SELECT COUNT(*) AS total,
      SUM(CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.videoUrlReview.videoUrl')) != m.url THEN 1 ELSE 0 END) AS mismatch_cnt
    FROM g_afd_review_job rj
    JOIN g_afd_material m ON JSON_UNQUOTE(JSON_EXTRACT(rj.info, '$.afdMid')) = m.afd_mid
    WHERE rj.relation_id LIKE '{batch_id}_%' AND rj.job_type IN (1, 3)

第 4 步：检查 subJobId 传递率
  → 统计 g_afd_material 中各类操作的 subJobId 覆盖率
  → 覆盖率 < 100% → 链路追踪断裂（BT_5976），排查时无法通过 traceId 关联具体操作

第 5 步：汇报结论
  → 使用 f88-approve-verify-sql 技能的验证结论输出模板
  → 明确区分：URL 传递正确（审核替换修复生效）vs 算法/文件类型问题（与本排查无关）
```

**关键陷阱**：
- approve 的 `input_json` 是快照，允许包含旧 URL — 仅看 input_json 判断 bug 会产生假阳性
- approve 状态为 HANDLING 不代表卡死 — 应先查 review_job 抽检子任务状态（job_type=3/5, status=1）
- BATCH 模式在预发环境依赖 SchedulerX 定时任务触发批次累积提交，预发 SchedulerX 可能未运行，导致批次无限期卡住。替代方案：使用 STREAM 模式策略

## 工作流 7：SharedArrayBuffer / COOP/COEP 环境检查

**触发时机**：用户反馈"视频编辑器加载失败""ffmpeg-wasm 报错""SharedArrayBuffer 不可用"。

```
第 1 步：检查预发环境响应头
  → curl -sI https://pre-aifashion-xiaoer.alibaba-inc.com/ | grep -iE 'cross-origin-(opener|embedder)-policy'
  → 期望：Cross-Origin-Opener-Policy: same-origin + Cross-Origin-Embedder-Policy: require-corp 或 credentialless（两者均合法；credentialless 可避免 CDN 资源缺少 CORP 头的问题）
  → 缺失 → 预发 Nginx 未配置 COOP/COEP（BT_6149）

第 2 步：浏览器 Console 验证
  → 打开视频编辑页面，检查 Console 是否有 SharedArrayBuffer 相关报错
  → 有报错 + 第 1 步缺失 → 确认是环境问题，非代码 bug

第 3 步：汇报结论
  → 环境问题 → 联系运维在预发 Nginx 配置 COOP/COEP 响应头
  → 生产环境正常但预发异常 → 对比生产/预发 Nginx 配置差异
```
