---
name: f88-pipeline-monitor
description: F88/i-FASHION 素材生产链路自动化监控路由器。定时巡检批次健康、阶段衔接、LLM资源、队列积压、机器健康、服务接口、算法依赖、离线数据链路、SchedulerX任务共9大维度，通过规则引擎生成4级告警，支持自愈策略。当用户说"F88巡检""链路监控""批次监控""监控报告""查下当前批次状态""服务成功率""算法监控""离线链路"时触发。
version: 0.3.0
---

# F88 素材生产链路监控（路由层）

> 本 skill 是**监控路由器**：根据用户指定的监控维度，读取知识库对应 .md 文档执行巡检。
> 详细工作流步骤、判定信封格式、子 Agent 隔离策略全部在知识库 .md 文档中。

## 知识库路径

```
f88-pipeline-monitor/references/
├── workflows.md            ← WF1~WF11 工作流详细步骤 + 子Agent隔离矩阵 + 判定信封格式
├── alert-rules.md          ← 告警规则全集（R001~R031，唯一归属）
├── self-healing-playbook.md ← 自愈策略操作手册（S1~S5）
└── sql-templates.md        ← SQL 查询模板
```

## 监控维度路由

| 用户输入 | 读取文档 |
|----------|----------|
| 批次失败/失败率/错误分布 | `workflows.md` → WF1 |
| 阶段没触发/阶段断裂/审核不流转 | `workflows.md` → WF2 |
| LLM 资源/模型利用率/429 | `workflows.md` → WF3 |
| 队列积压/HANDLING 滞留/审核等待 | `workflows.md` → WF4 |
| 机器健康/CPU/内存/GC | `workflows.md` → WF5 |
| 服务接口/HSF/MTOP/成功率 | `workflows.md` → WF6 |
| 算法依赖/网关/异步回调 | `workflows.md` → WF7 |
| 离线数据/企划案/素材产出 | `workflows.md` → WF8 |
| 生成监控报告/汇总告警 | `workflows.md` → WF9 |
| 交付时效/SLA/48h | `workflows.md` → WF10 |
| 数据对账/环节对账/数量偏差 | `workflows.md` → WF11 |
| 查告警规则/阈值 | `alert-rules.md` |
| 自愈操作/重试/重启/推送 | `self-healing-playbook.md` |
| 需要查 SQL | `sql-templates.md` |

## 核心约束

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
env 过滤：所有查询必须带 env='staging'（线上数据只能查看不能动）
workflow_record_log：必须带 id > 4000000 否则超时
status 失败值是 'FAIL'，不是 'FAILED'
错误字段是 $.errorMsg，不是 $.errorMessage
g_strategy 主键是 id，不是 strategy_id
写操作（重试/推送/触发）需记录审计日志，不得超过最大重试次数
Mock 错误（"mock llm error"）不触发自动重试，直接告警
```

## 执行策略

1. 识别用户输入属于哪个监控维度（见路由表）
2. 读取 `workflows.md` 中对应 WF 的详细步骤
3. 遵循**主 Agent 只看结论，子 Agent 做脏活**原则
4. 子 Agent 按通用判定信封格式返回 verdict
5. 主 Agent 根据 verdict 决策：OK→丢弃 / P2→日报 / P1→告警 / P0→立即告警
6. `env == "staging" AND selfHealable == true` → 执行自愈；否则标记人工介入

## 自愈策略速查

| ID | 策略 | 触发条件 | 最大次数 |
|---|---|---|---|
| S1 | 429 智能重试 | RESOURCE_EXHAUSTED/429 | 4 次（指数退避） |
| S2 | 滞留重启 | HANDLING > 2h | 2 次 |
| S3 | 审核推送 | approve 等待 > 4h | 3 次 |
| S4 | 队列调配 | LLM 利用率 > 90% 持续 30min | — |
| S5 | 阶段补偿 | 阶段衔接断裂 | 1 次 |

详细操作手册见 `references/self-healing-playbook.md`

## 回溯优先规则

- 当某个工作流走了错误路径，**不要在错误结果上打补丁**
- 应回到决策分叉点，带着"这条路不通"的认知重新选择方向

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 深度 SQL 归因（11 个工作流） | `f88-failure-analysis` |
| 失败数据聚类分析 | `f88-clustering-service` |
| 链路配置正确性检查 | `f88-link-config-check` |
| 审核节点替换验证 | `f88-approve-verify-sql` |
| 实时查批次进度/重试节点 | `strategy-platform` |
| 视频输出物 ffprobe 校验 | `f88-ffmpeg` |
| 素材域问题排查 | `f88-mainimg-material` |
| 种草素材链路排查 | `f88-seeding-material` |
