---
name: f88-approve-verify-sql
description: F88/i-FASHION 策略平台"审核节点替换验证"SQL 路由器。验证 approve 节点在 BATCH/STREAM 模式下、替换素材后下游节点是否拿到正确 URL、审核任务层级完成情况、review_job.info 快照与 g_afd_material.url 对比等场景。当用户说"验证批次""BT_xxxx 数据库验证""approve 节点验证""替换后走流程验证""审核任务完成情况""下游拿到的是老 URL 还是新 URL""BATCH STREAM 修复验证"时触发。
version: 2.2.0
---

# F88 审核节点替换验证 SQL（路由层）

> 本 skill 是**验证路由器**：根据验证场景路由到对应 SQL 步骤。
> 详细 SQL 步骤、修复验证工作流、已知问题模式全部在知识库 .md 文档中。

## 知识库路径

```
f88-approve-verify-sql/references/
└── sql-verification.md  ← Step 1~7 SQL 步骤 + 修复验证工作流 + 已知问题 + Pitfalls
```

## 验证场景路由

| 用户输入 | 读取文档 |
|----------|----------|
| 批次总览/链路走到哪了 | `sql-verification.md` → Step 1 |
| approve + 下游完整 JSON | `sql-verification.md` → Step 2 |
| 判断 bug 是否复现（一锤定音） | `sql-verification.md` → Step 3 |
| approve 卡 HANDLING/审核任务层级 | `sql-verification.md` → Step 4 |
| review_job 快照 vs material URL/execMode | `sql-verification.md` → Step 5 |
| 批量跨表一致性扫描 | `sql-verification.md` → Step 6 |
| subJobId 覆盖率审计 | `sql-verification.md` → Step 7 |
| 验证 replaceImage 回写修复 | `sql-verification.md` → 修复验证（BT_6148） |
| 验证 subJobId 传递修复 | `sql-verification.md` → 修复验证（BT_5976） |
| 验证 SharedArrayBuffer 修复 | `sql-verification.md` → 修复验证（BT_6149） |
| 已知问题模式/问题编号 | `sql-verification.md` → 已知问题模式速查 |
| SQL 踩坑/Pitfalls | `sql-verification.md` → Pitfalls 汇总 |

## 核心约束

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
CLI：见 F88测试知识库/references/shared/db-connections.md 标准调用格式
查询安全规则（env 过滤铁律/写操作红线/ScheduleX 只读）：见 F88测试知识库/references/shared/query-safety-rules.md
workflow_record_log：必须带 id > 6400000（比通用阈值更高）
列名用 batch_id（不是 search_key）+ node_type（不是 node_name）
g_afd_review_job 无 node_id 列，用 parent_job_id + relation_id
approve.input_json 是快照（允许老 URL），判断 bug 要看 output_json.passedImg
status 语义：workflow_record_log 用 HANDLING/SUCCESS/FAIL
            g_afd_review_job.job_status 双语义：主任务 1=待处理 2=处理中 3=待抽检 4=抽检中 5=已完成 6=暂停；子任务 0=待审核 1=通过 2=不通过
            job_type 用 0=主 1=子审核 3=抽检子 4=主审核 5=抽检主
```

## 端到端验证规则

- 三处一致才算生效：`approve.input_json`（快照）→ `approve.output_json.passedImg`（真值）→ 下游 `input_json.inputImgs`
- **数据红线**：所有主动操作只允许作用于 env=staging 的测试数据；env=production 或为空的数据一律只读
- 进入 `/review/task-management` 前先确认是 staging 数据
- 遇 HANDLING 阻塞时（确认 env=staging 后）不询问用户，直接点掉阻塞任务

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 深度 SQL 归因（13 个工作流） | `f88-failure-analysis` |
| 自动化巡检(9维度) | `f88-pipeline-monitor` |
| 链路配置正确性检查 | `f88-link-config-check` |
| 失败数据聚类分析 | `f88-clustering-service` |
| 素材域问题排查 | `f88-mainimg-material` |
| 种草素材链路排查 | `f88-seeding-material` |
