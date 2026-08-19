---
name: stylespot-prod-troubleshoot
description: i-FASHION/stylespot-admin 线上问题排查入口。当用户提到裁头节点异常、审核回调丢失、审核任务全部INIT/前台看不到审核任务、审核完成但批次不流转、workflow记录卡住、TPP任务无回调、批次异常、节点HANDLING、驳回重生失败、crop_head、approve卡住、COMPOSITION_ANALYSIS、任务滞留、replaceImage后下游旧URL、BATCH和STREAM结果不一样、SharedArrayBuffer报错、subJobId没传、trace丢失、跨表数据不一致时触发。五大排查路径 + 两项环境级检查，详见 docs/ 按需加载。
version: 2.2.4
---

# stylespot-admin 线上问题排查

## 核心数据库

数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md。查询安全规则（env 语义/写操作红线/ScheduleX 只读）见 F88测试知识库/references/shared/query-safety-rules.md。涉及 ScheduleX、Switch、HSF、平台入口等地址时，先读 quderwork/f88素材生产/常用地址手册.md，禁止自行推理。关键表：

| 表 | 用途 | 关键字段 |
|---|---|---|
| g_admin_task | 算法任务（TPP） | task_type(非type), task_status(10=HANDLING), job_id(关联workflow_record_log.id), tpp_task_id, scene_code |
| workflow_record_log | workflow节点执行记录 | status(HANDLING/SUCCESS/FAIL), node_type, batch_id, extra_info(JSON: notPass/reproductionIds/errorMsg) |
| g_workflow_batch | 批次 | batch_id, status(PROCESSING/FINISHED/TERMINATED), relation_id(非link_id), relation_type, source_type |
| g_afd_review_job | 审核任务 | job_type(0=主任务,1=正常审核子任务,2=埋雷子任务,3=抽检子任务,4=个人审核主任务,5=个人抽检主任务), job_status双语义:主任务1=待处理2=处理中3=待抽检4=抽检中5=已完成6=暂停;子任务0=待审核1=通过2=不通过, relation_id(关联workflow_record_log.id), info(JSON) |
| g_afd_material | 素材替换记录 | url(替换后URL), relation_id(关联workflow_record_log.id), env, cate_id, gmt_create(替换时间) |

## 路由表：症状 → 排查路径

根据用户描述的症状，读取对应文档获取详细步骤和 SQL 模板。

| 症状关键词 | 排查路径 | 文档 |
|-----------|---------|------|
| 节点永久 HANDLING、TPP 无回调、task_status=10 | 路径一：TPP 算法任务无回调 | [docs/troubleshooting-paths.md](docs/troubleshooting-paths.md) § 路径一 |
| 审核已操作但 workflow 未更新、回调丢失、审核任务全部 INIT/前台无任务（BT_7495）、审核完成但批次不流转（BT_7485） | 路径二：审核平台→workflow 回调丢失 | [docs/troubleshooting-paths.md](docs/troubleshooting-paths.md) § 路径二 |
| 批次异常、节点状态不符预期、重生不触发 | 路径三：workflow 节点生命周期异常 | [docs/troubleshooting-paths.md](docs/troubleshooting-paths.md) § 路径三 |
| replaceImage 后下游旧 URL、BATCH/STREAM 不一致 | 路径四：素材替换副作用 | [docs/troubleshooting-paths.md](docs/troubleshooting-paths.md) § 路径四 |
| BATCH 模式卡住、execMode 异常、SchedulerX | 路径五：执行模式异常 | [docs/troubleshooting-paths.md](docs/troubleshooting-paths.md) § 路径五 |
| SharedArrayBuffer 报错、ffmpeg-wasm 加载失败 | 环境检查一：COOP/COEP 响应头 | [docs/env-checks.md](docs/env-checks.md) § 检查一 |
| subJobId 缺失、trace 丢失、回调无法关联 | 环境检查二：subJobId 链路追踪 | [docs/env-checks.md](docs/env-checks.md) § 检查二 |

## 关联技能

- `f88-failure-analysis`：系统性失败归因与错误模式分类（13 个工作流）。SQL 级深度排查、errorMsg 聚类、策略配置核查、BATCH/STREAM 模式差异分析、跨表数据一致性验证、SharedArrayBuffer/COOP/COEP 环境排查；批次效率异常（"鬼打墙"式重试/为什么慢）转 WF12 批次轨迹效率分析，失败批次沉淀回归用例转 WF13 Bad Case 回流。
- `f88-approve-verify-sql`：approve 节点替换验证与端到端 URL 正确性校验。
- `harness-runner`：预置诊断 Pipeline 自动化执行（cross-table-consistency-check、batch-stream-mode-verify、subjobid-coverage-audit、sharedarraybuffer-env-check）。
- `strategy-platform`：批次级实时运维（MCP 工具），本 skill 在 SQL/数据库层做离线排查。

## 监控建议

1. Diamond 超时配置：所有 taskType+sceneCode 组合必须配置 timeoutSec
2. TaskStuckPatrolProcessor：定时巡检滞留任务
3. TPP 机器监控：关注在线机器数=0 的场景
4. 审核回调对账：主任务完成后 N 分钟检查关联 workflow 记录是否更新
5. 跨表一致性巡检：定期扫描 g_afd_material.url 与 g_afd_review_job.info 快照 URL 不一致
6. subJobId 覆盖率监控：缺失率应趋近 0
7. COOP/COEP 头部巡检：预发/日常环境定期 curl 检查

## Pitfalls

- g_admin_task 的列是 task_type 不是 type，没有 fail_message 列
- workflow_record_log 的 notPass/reproductionIds/errorMsg 在 extra_info JSON 里，不是独立列
- g_workflow_batch 的列是 relation_id 不是 link_id，没有 reproduction_status 列
- workflow_record_log 的 node_type 无索引，按 node_type 查会超时
- workflow_record_log 查询必须带 `id > 4000000` 否则超时（近期批次建议 `id > 6400000` 进一步缩小扫描范围，与 f88-failure-analysis / f88-approve-verify-sql 口径一致）
- 禁止基于代码分支推断部署状态，必须查 DB 实际数据验证。**当 DB 查询仍无法确认时（如分支路径不匹配、配置来源不明），必须自行到预发环境实操验证（跑一遍流程看实际行为），禁止停下来反问用户"要不要我去预发验证？"**——验证是义务不是选项，直接去验证，不要问
- TaskConfigV2 从 Diamond 动态加载，没有 timeoutSec 配置 = 超时机制失效
- replaceImage 只写 g_afd_material.url，不回写 g_afd_review_job.info 快照（BT_6148）
- 预发 BATCH 模式依赖 SchedulerX，预发 SchedulerX 可能不运行，测试优先用 STREAM 模式
- SharedArrayBuffer 依赖 COOP/COEP 响应头，预发 Nginx 配置可能与线上不一致
- subJobId 缺失导致回调后无法关联 workflow 记录（BT_5976）
