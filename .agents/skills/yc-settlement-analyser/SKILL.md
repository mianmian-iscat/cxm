---
name: yc-settlement-analyser
description: 原创保护平台结算链路分析器。输入 PRD / 需求文档 / 技术方案，自动输出资金流向图（Mermaid）、费用科目表、结算状态机、账期规则、风险评估和测试策略建议。当用户提到结算分析、结算链路、资金流向、退款分析、确收分析、补贴分析、settlement analysis、fund flow、结算测试、费用科目、账期规则、结算状态机、下架率分流、退款路径、确收路径、服务完结时触发。也可用于评审已有结算方案、发现设计盲区。
version: 1.0.0
---

# 原创保护结算链路分析器

分析原创保护平台（淘天服饰原创保护）业务需求中的结算逻辑与资金链路，自动输出 6 类结构化产物，帮助 QA / PM / 开发快速理解结算全貌、发现设计盲区、制定测试策略。

## 前置条件

1. **输入来源**（至少提供一项）：
   - PRD 文档（钉钉文档链接 / 语雀链接 / 本地 .md 文件）
   - 技术方案文档
   - 口头描述的需求变更点
   - 或直接指定"分析当前版本结算链路"（使用内置知识）

2. **领域知识来源**（自动加载，无需用户提供）：
   - 本 Skill 内置的结算领域模型（见 references/）
   - 关联 Skill：`yc-data-factory`（HSF 造数）、`yc-db-verification`（DB 验证）

## 工作流

### Phase 1: 输入解析

读取用户提供的 PRD / 需求文档，提取与结算相关的字段：

| 提取维度 | 关注点 |
|----------|--------|
| 结算触发条件 | 什么事件触发结算（到期、驳回、终止、取消） |
| 资金流向 | 谁付钱、谁收钱、金额如何计算 |
| 分流规则 | 下架率阈值、首发/非首发、9类/非9类 |
| 状态流转 | 结算单状态机、子状态定义 |
| 定时任务 | SchedulerX Job 配置、cron 表达式 |
| 异常场景 | 退款失败、重复结算、脏数据处理 |

**如果用户只说"分析结算链路"没给文档**：直接使用内置领域知识（references/），输出当前版本的完整分析。

### Phase 2: 资金流向图

用 Mermaid flowchart 输出资金在各角色间的流向，详见 references/fund-flow-model.md。

**输出要求**：
- 标注每条流向的金额（或金额计算公式）
- 用颜色区分路径：退款=蓝色、确收=绿色、补贴=黄色
- 标注触发条件（如下架率 < 70%）

### Phase 3: 费用科目表

输出结构化表格，列出所有资金科目，详见 references/fee-schedule.md。

**关键公式**（源码 `RightSettleConstant.java` 确认）：
- 退款金额 = total_amount - 已发放补贴（受余额限制）
- 首发补贴 = 302元（INIT_ALLOWANCE=30200分），非首发补贴 = 202元（NOT_INIT_ALLOWANCE=20200分）
- 确收金额 = Switch 配置值（从 SERV_FINISH_INCOME_FEE_CODE 读取）

### Phase 4: 结算状态机

输出结算单状态机图（Mermaid stateDiagram），详见 references/state-machine.md。

**补充输出**：
- settle_status 主状态与 4 个子状态的关系
- 每个状态转换的触发条件、对应 SchedulerX Task ID
- 转普通时的 CANCEL + 重建逻辑

### Phase 5: 账期规则

输出定时任务编排和时效规则：

| 维度 | 规则 |
|------|------|
| Job 链 | Task 715618497(01:00) → 399576024(02:00) → 719211870(04:00) / 721504806(06:00) |
| 触发前置 | protect_expire_time 已过期（Task 399576024 扫描） |
| 退款耗时 | 需触发 2 次（TO_DO → PROCESSING → FINISH），依赖支付回调 |
| 补贴窗口 | SYNC_CERT_FILE 时快照判定，非申请时 |
| 保护期 | protect_expire_time 到期后 20 天禁发期 |

### Phase 6: 风险评估

输出结构化风险矩阵：

| 风险项 | 严重度 | 影响范围 | 当前防护 | 残余风险 |
|--------|--------|----------|----------|----------|
| 退款只触发1次未到FINISH | 高 | 资金滞留 | 需人工再次触发Job | 中 — 缺少自动重试 |
| 下架率在阈值边界(69%/71%) | 中 | 分流错误 | 70% 硬编码 | 低 — 可通过 Switch Mock 验证 |
| settle_order 多条记录 | 中 | 验证混淆 | 取最新非CANCEL记录 | 低 |
| 补贴发放时机错误 | 高 | 多发/漏发 | SYNC_CERT_FILE 快照 | 低 |
| ScheduleX 按钮无法自动化 | 低 | 测试效率 | 用户手动触发 | 低 |
| 退款金额 > 剩余余额 | 高 | 资损 | 校验失败拦截 | 低 |
| 转普通后旧结算单未CANCEL | 中 | 重复结算 | 状态机约束 | 需验证 |
| 确收路径未验证 | 中 | 覆盖缺失 | 无 | 高 — 需构造≥70%数据 |

### Phase 7: 测试策略建议

基于以上分析，输出测试策略：

#### 7.1 必测场景（P0）

| 场景 | 验证点 | 已有数据 | 造数方式 |
|------|--------|----------|----------|
| 退款路径全流程 | settle_status=FINISH, refund_status=FINISH | 200000885, 200001005 | 已验证 |
| 补贴发放(9类) | init_allowance_start_time ≠ NULL | 200001005 | 已验证 |
| 补贴不发(非9类) | init_allowance_start_time = NULL | 200000885 | 已验证 |
| 下架率分流(<70%) | refund_status 流转, income_status = NULL | 200000885 | 已验证 |
| 转普通后结算单重建 | 旧单CANCEL + 新单PROCESSING | — | 需构造 |

#### 7.2 高风险场景（P1）

| 场景 | 验证点 | 当前状态 |
|------|--------|----------|
| 确收路径(≥70%) | income_status 流转, refund_status = NULL | **未验证** — 需构造≥70%下架率数据 |
| 退款2次触发 | 第1次PROCESSING → 第2次FINISH | 已验证但需回归 |
| 边界下架率(恰好70%) | 分流到确收路径 | 未验证 |
| 零侵权记录 | 下架率=0% → 退款路径 | 200001005已验证 |

#### 7.3 边界场景（P2）

- 同时满足首发 + 9类 + 高下架率
- 转普通 + 到期同时触发
- settle_order 有 CANCEL + PROCESSING 双记录
- protect_expire_time 恰好等于 Job 扫描时间

#### 7.4 推荐执行顺序

1. 用本 Skill 理解全貌 → 2. 用 `yc-quick-audit-data-create` 造申请数据 → 3. 用 `yc-data-factory` HSF 操作状态 → 4. 用 `yc-db-verification` SQL 验证 → 5. 手动触发 SchedulerX Job

## 内置领域模型

当用户未提供 PRD 时，直接使用以下内置知识输出分析：

### 结算全景图

```
申请提交(商家缴费500元)
  → 快审/初审通过
  → SYNC_CERT_FILE(补贴判定快照)
  → 保护期运行(protect_expire_time)
  → 到期触发 RightProtectExpiredJob
  → 下架率分流(70%阈值)
    → <70%: 退款路径(ServFinishRefundJob)
    → ≥70%: 确收路径(ServFinishIncomeJob)
  → 结算完结(settle_status=FINISH)
```

### 核心表关系

```
yc_right_apply(申请) --1:1--> yc_right(权益)
yc_right_apply(申请) --1:N--> yc_right_settle_order(结算单)
yc_right(权益)     --1:N--> yc_tort_record(侵权记录)
yc_right_apply(申请) --1:N--> yc_right_apply_op_record(操作流水)
```

### 金额速查（详见 references/fee-schedule.md）

| 科目 | 测试环境 | 生产环境 |
|------|----------|----------|
| 服务费(total_amount) | 10 分 | 500 元 |
| 首发补贴(INIT_ALLOWANCE) | 6 分 | **302 元** |
| 非首发补贴(NOT_INIT_ALLOWANCE) | 4 分 | **202 元** |
| 基础服务费(BASE_FEE) | 2 分 | 165 元 |
| 非首发退款 | 4 分(total-补贴) | **198 元**(500-302) |
| 首发退款 | 6 分(total-补贴) | **298 元**(500-202) |
| 确收 | — | Switch 配置值 |

## 输出格式

所有产物输出为单个 Markdown 文件，包含：
1. 资金流向图（Mermaid flowchart）
2. 费用科目表（Markdown table）
3. 结算状态机（Mermaid stateDiagram）
4. 账期规则表（Markdown table）
5. 风险矩阵（Markdown table）
6. 测试策略（分 P0/P1/P2 的场景表 + 推荐执行顺序）

如用户要求 HTML 报告，可额外生成带 Mermaid 渲染的自包含 HTML。

## 关联 Skill

| Skill | 用途 | 调用时机 |
|-------|------|----------|
| `yc-data-factory` | HSF 造数 + SchedulerX 触发 | 测试执行阶段 |
| `yc-db-verification` | DB 验证 + SQL 模板 | 结果验证阶段 |
| `yc-quick-audit-data-create` | 构造快审/初审申请 | 数据准备阶段 |
| `qa-test-engineering` | 通用测试流程 | 全流程编排 |

## 踩坑记录

1. **total_amount ≠ 补贴金额**：total_amount 是服务费基数（测试=10分，生产=500元），补贴看 init_allowance_start_time。
2. **下架率计算分母**：包含所有侵权记录（含 PROTECTING 状态），不只是已处理的。
3. **退款需2次触发**：TO_DO → PROCESSING → FINISH，不要期望一次完成。
4. **补贴快照时点**：取 SYNC_CERT_FILE 时的 ODPS 主营类目，不是申请创建时。
5. **确收路径未验证**：截至 2026-07-13，确收路径（下架率≥70%）尚未在测试环境完成 E2E 验证。
6. **ScheduleX 只能手动触发**：浏览器自动化不稳定，建议用户手动点「运行一次」。

## 验证

Skill 执行完成后检查：
- [ ] 6 类产物全部输出
- [ ] Mermaid 图可正常渲染
- [ ] 费用科目金额与 DB 实际数据一致
- [ ] 风险评估覆盖了所有已知踩坑点
- [ ] 测试策略中标注了已验证/未验证场景
