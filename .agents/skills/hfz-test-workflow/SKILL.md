---
name: hfz-test-workflow
description: F88/i-FASHION + 原创保护 双域提测自动化 QA 工作流（唯一编排器）。域识别：自动检测 F88（审核/策略/主图/种草/视频/模板/买手）或原创保护（原创/首发/保护/黑标/千牛标/结算/apply/seller/yc）关键词路由到对应子流程。双通道入口：机器人通道（钉钉群消息/IM 转发）+ 用户直接操作。F88 按十步流程执行，原创保护按八阶段流程执行。触发词：测一下、测试、提测、F88 测试、原创保护测试、BT_ 验证、结算测试、主图/种草审核。
version: 3.0.0
---

# hfz-test-workflow：F88 + 原创保护 双域测试编排器

双域统一入口。识别用户输入中的业务关键词，自动选择 F88 十步流程或原创保护八阶段流程，调用对应子 skill 完成从需求到知识沉淀的端到端测试。

## 1. 入口与通道

| 通道 | 说明 |
|------|------|
| 用户直接操作 | 用户在当前会话输入测试请求 |
| 机器人通道 | 钉钉群 / IM 转发，仅限白名单消息触发 |

## 2. 域路由表

| 域 | 命中关键词（任一即命中） | 目标流程 |
|----|-------------------------|---------|
| F88 / i-FASHION | F88、i-FASHION、主图、种草、审核、策略、模板包、BT_、batch、workflow、stylespot、生图、视频、买手、商详拼接、盗图整改 | F88 十步流程 |
| 原创保护 | 原创保护、yc、YCBH、千牛标、首发、保护、黑标、结算、退款、确收、apply、seller、快审、初审、TTYCBH | 原创保护八阶段流程 |

> 若同时命中两类关键词，按用户最后明确指定的域执行；未明确则优先询问。

## 3. F88 十步流程

| 步骤 | 名称 | 说明 | 调用子 skill |
|------|------|------|-------------|
| S1 | 需求分析 | 解析 PRD / 提测单 / 代码 diff，提取测试范围 | `PRD用例生成`、`统一用例生成` |
| S2 | 用例生成 | 输出结构化用例 + 钉钉文档，执行覆盖度评估 | `PRD用例生成`、`统一用例生成`、`测试用例评估` |
| S3 | 数据构造 | 产出真实 BT_ 批次、模板包、审核数据 | `f88-strategy-test-run`、`f88-template-package-create`、`审核数据构造` |
| S4 | 环境检查 | 检查链路配置、模型可用性、执行模式、容量限流 | `f88-link-config-check`、`f88-pipeline-monitor` |
| S5 | 用例执行 | CDP 浏览器 / API / harness 执行用例 | `web-automation`、`harness-runner`、`f88-test-mode` |
| S6 | DB/日志验证 | 验证批次状态、审核层级、跨表一致性、日志 | `f88-data-query`、`f88-approve-verify-sql`、`f88-log-analysis` |
| S7 | 缺陷定位 | 失败归因、错误聚类、根因定位 | `f88-failure-analysis`、`f88-clustering-service` |
| S8 | 测试报告 | 生成双报告并回填 AOne。**截图关联检查**：P0 用例必须有 `screenshotPaths`，否则阻断报告生成，提示补截图 | `qa-test-report`、`att-report` |
| S9 | Bug 提报 | 生成 Bug 草稿并提交 AOne | `f88-bug-drafter`、`aone-bug-submit` |
| S10 | 知识沉淀 | 更新知识库、失败模式、回归用例集 | `f88-clustering-service`、`F88测试知识库` |

## 4. 原创保护八阶段流程

| 阶段 | 名称 | 说明 | 调用子 skill |
|------|------|------|-------------|
| P1 | 用例生成 | 从 PRD 输出 XMind 大纲 + pytest 脚本 | `原创保护用例生成` |
| P2 | 规则校验 | 状态机、补贴、首发窗口、保护期规则校验 | `原创保护规则校验`、`yc-settlement-analyser` |
| P3 | 数据构造 | 快审/初审申请、改状态/时间/补贴、模拟审核 | `yc-quick-audit-data-create`、`yc-data-factory` |
| P4 | 执行助手 | API/UI 执行与实时断言 | `原创保护执行助手` |
| P5 | 结算/异步验证 | ScheduleX 触发、DB 状态机、资金流向验证 | `yc-data-factory`、`yc-db-verification` |
| P6 | 缺陷排查 | DB / MetaQ / ScheduleX / 代码多源根因定位 | `yc-defect-diagnosis` |
| P7 | 测试报告 | 输出双报告并回填 AOne | `qa-test-report`、`att-report` |
| P8 | 千牛标打标/入驻 | TTYCBH 打标、商家入驻 | `原创保护千牛标打标`、`yc-data-factory` |

## 5. 群消息白名单

机器人通道仅允许以下两类消息触发本 skill：

1. **收到提测消息**：消息包含 "提测"、"提测单"、"测试"、"PRD"、"需求" 等，且命中 F88 / 原创保护关键词。
2. **测试完成结果摘要**：由子 skill 或 att-report 生成的标准化结果摘要，用于群通知。

其余群消息（日常讨论、非测试需求、未命中域关键词）一律不触发，也不回复。

## 6. 安全规则

| 规则 | 说明 |
|------|------|
| env='staging' | 所有 DB 查询必须带 `env='staging'` 过滤；生产数据只读 |
| 禁止 DML | 测试流程内禁止 INSERT / UPDATE / DELETE；`createDataChangeOrder` 仅用户显式要求时使用 |
| att-start 声明 | 每个测试会话必须先调用 `att-start` 声明身份与采证规范 |
| env 预检 | 任何 HSF Tool / 数据工厂写操作前，必须执行 `SELECT id, env FROM yc_right_apply WHERE id = {applyId}` 确认 env='staging' |
| 生产数据告警 | 命中 env='production' / 'prod' 时立即中止并告警 |

## 7. MCP 三级降级协议

| 级别 | 名称 | 动作 |
|------|------|------|
| L1 | 重试 | MCP 调用失败时自动重试 1 次，并记录错误 |
| L2 | 同能力 CLI | 降级到等价 CLI：DMS MCP → `dms-alibaba`；SLS MCP → `normandy log` / `aliyun sls`；ScheduleX → 预发控制台 / `a1` CLI |
| L3 | BLOCKED_MCP + IM 私聊 | L2 仍失败时标记 `BLOCKED_MCP`，通过钉钉/IM 私聊用户说明阻塞点，等待人工处理 |

## 8. 关联资源

- 详细流程步骤与子 skill 调用格式见 [references/orchestration-flow.md](references/orchestration-flow.md)
- F88 数据库连接与安全规则见 `f88-data-query` 及 `F88测试知识库/references/shared/`
- 原创保护数据构造与结算 E2E 见 `yc-data-factory/references/`
