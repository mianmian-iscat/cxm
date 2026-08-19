---
name: 原创保护规则校验
version: 1.0.0
description: 原创保护业务规则批量校验器。输入申请编号/权益编号/seller_id，自动执行9类白名单、补贴资格、首发编辑权限、转普通、结算分流、退款状态机等规则校验，输出 pass/fail 证据与所用 SQL。触发词：原创保护规则校验、规则校验、9类校验、补贴校验、首发编辑权限校验、转普通校验、结算状态机校验、下架率校验、退款规则校验、yc rule check。
---

# 原创保护规则校验

对淘天服饰原创保护核心业务流程做只读规则校验，覆盖 9 类白名单、补贴发放资格、首发/编辑权限、转普通、结算分流与退款/确收规则。输出结构化判定结果（pass/fail）、证据字段与所使用 SQL 模板编号。

## 前置条件

1. **DMS MCP 已连接**：`mcp__dms-mcp-server__executeScript` 可用。
2. **目标数据库**：scenario 库，固定 `database_id = 975919`（预发/生产共用同一物理库）。
3. **用户输入**：至少提供以下之一
   - 申请编号 `yc_right_apply.id`（推荐，如 200000885）
   - 权益编号 `yc_right.id`
   - `seller_id`
4. **已知关联 Skill**：
   - `yc-db-verification`：DB 验证与 XMind 用例更新
   - `yc-settlement-analyser`：结算链路分析与风险矩阵
   - `yc-data-factory`：HSF 造数 / ScheduleX 触发

## 安全约束（强制）

```
【只读】所有查询必须是 SELECT，禁止 INSERT/UPDATE/DELETE/TRUNCATE。
【环境隔离】所有带 env 列的表必须加 env = 'staging' 过滤。
【预检】执行 DMS SQL 前，先对 yc_right_apply / yc_right / yc_right_settle_order 执行 SELECT id, env FROM ... WHERE id = {id}，仅 env='staging' 可继续。
【拒绝生产】若 env = 'production' / 'prod'，立即拒绝并告警，不执行后续查询。
【DML 红线】测试流程中禁止 DML；createDataChangeOrder 仅在用户显式要求时使用。
```

## 核心表与规则速查

| 表名 | 关键字段 | 校验用途 |
|------|----------|----------|
| `yc_right_apply` | id, status, apply_type, category, to_regular_status, right_id, seller_id, env | 申请状态机、转普通 |
| `yc_right` | id, first_publish, category, protect_expire_time, status, env | 首发标记、保护期、权益状态 |
| `yc_right_settle_order` | id, settle_status, total_amount, init_allowance_start_time, init_allowance_amount, serv_finish_refund_status, serv_finish_refund_amount, serv_finish_income_status, serv_finish_income_amount, env | 补贴、结算状态机、退款/确收 |
| `yc_tort_record` | id, right_id, status, env | 下架率计算 |
| `yc_right_apply_op_record` | id, right_apply_id, op_type, op_detail, gmt_create | 操作流水还原 |

### 9 类白名单类目

```
{16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001}
```

对应类目：女装/女士精品、男装、童装/亲子装、童鞋/亲子鞋、女士内衣/男士内衣/家居服、服饰配件/皮带/帽子/围巾、运动鞋/休闲鞋、运动服/休闲服、箱包。

### 关键规则摘要

| 规则 | 判定条件 |
|------|----------|
| 补贴发放 | SYNC_CERT_FILE 时主营类目 ∈ 9 类白名单；`init_allowance_start_time IS NOT NULL` |
| 首发编辑权限 | 9 类商家 **且** `to_regular_status ≠ DONE` |
| 转普通 | `to_regular_status = DONE`；旧 settle_order CANCEL，新 settle_order PROCESSING |
| 下架率分流 | 下架率 < 70% → 退款；≥ 70% → 确收 |
| 退款金额 | `total_amount - init_allowance_amount`（已发补贴时） |

## 校验工作流

### Phase 1: 输入解析与安全预检

1. 提取 applyId / rightId / sellerId。
2. 若按 applyId 查询，先执行：
   ```sql
   SELECT id, env FROM yc_right_apply WHERE id = {applyId};
   ```
   仅 `env = 'staging'` 继续。
3. 通过 `yc_right_apply.right_id` 拿到 rightId，确认 `yc_right.env = 'staging'`。

### Phase 2: 执行规则校验

按以下顺序执行 6 组规则，每组输出 pass/fail、证据与 SQL 模板编号。

| 编号 | 规则组 | SQL 模板 |
|------|--------|----------|
| R1 | 9 类白名单校验 | SQL-T1 / SQL-T7 |
| R2 | 补贴发放资格校验 | SQL-T2 / SQL-T3 |
| R3 | 首发/编辑权限校验 | SQL-T4 |
| R4 | 转普通流程校验 | SQL-T5 / SQL-T6 |
| R5 | 结算状态机校验 | SQL-T3 / SQL-T8 |
| R6 | 下架率分流与退款/确收校验 | SQL-T8 / SQL-T9 |

### Phase 3: 输出校验报告

固定输出格式见下节。

## 规则校验清单

### R1. 9 类白名单校验

**规则**：SYNC_CERT_FILE 时商家主营类目 ∈ 9 类白名单才具备补贴资格。

**判定**：
- 从 ODPS 快照 `cco_busi.dplan_dim_tb_slr_mx_d_1` 取 SYNC_CERT_FILE 当天 ds 分区的主营类目；如无法查 ODPS，则以 `yc_right_apply.category` / `yc_right.category` 作为近似判断。
- `category_id IN (16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001)` → 9 类。

**Pass 证据**：`category` 值命中白名单集合。
**Fail 证据**：`category` 不在白名单，但 `init_allowance_start_time IS NOT NULL`。

### R2. 补贴发放资格校验

**规则**：9 类商家在 SYNC_CERT_FILE 后补贴触发；非 9 类永远保持 NULL。

**判定**：
- 非 9 类 → `init_allowance_start_time IS NULL` 且 `init_allowance_amount IS NULL`。
- 9 类 → Job 执行后 `init_allowance_start_time IS NOT NULL` 且金额匹配首发/非首发（首发 302 元/6 分，非首发 202 元/4 分）。

**Pass 证据**：实际值与预期一致。
**Fail 证据**：
- 非 9 类但补贴字段非 NULL。
- 9 类但补贴金额与 `first_publish` 不匹配。

### R3. 首发/编辑权限校验

**规则**：运营端可编辑首发 = 9 类商家且未转普通（`to_regular_status ≠ DONE`）。

**判定**：
- `to_regular_status IS NULL` + 9 类 → 可编辑。
- `to_regular_status = DONE` 或非 9 类 → 不可编辑。

**Pass 证据**：DB 状态与 UI 表现一致。
**Fail 证据**：DB 显示可编辑但 UI disabled，或 DB 显示不可编辑但 UI 可编辑。

### R4. 转普通流程校验

**规则**：转普通后旧结算单 CANCEL，新结算单 PROCESSING；且即使 9 类也不可编辑首发。

**判定**：
- `to_regular_status = DONE`。
- 存在旧 settle_order `settle_status = CANCEL`。
- 存在新 settle_order `settle_status = PROCESSING`。
- 新结算单 `init_allowance_start_time` 按当前规则重新判定。

**Pass 证据**：新旧结算单状态符合预期。
**Fail 证据**：旧单未 CANCEL、新单缺失或多条新单并存。

### R5. 结算状态机校验

**规则**：
- `settle_status` 主状态：PROCESSING → FINISH / CANCEL。
- 退款子状态：NULL → TO_DO → PROCESSING → FINISH。
- 确收子状态：NULL → TO_DO → PROCESSING → FINISH。
- 退款与确收互斥，未走的一侧子状态为 NO_NEED。

**判定**：
- 主状态终态为 FINISH 时，至少一个子状态为 FINISH 或 NO_NEED。
- 同一结算单 refund 与 income 不能同时处于非 NULL 的进行中状态。

**Pass 证据**：状态流转符合状态机图。
**Fail 证据**：出现非法组合，如 refund=PROCESSING 且 income=PROCESSING。

### R6. 下架率分流与退款/确收校验

**规则**：
- 下架率 = `SUCCESS` 侵权记录数 / 全部侵权记录数（含 PROTECTING）。
- 下架率 < 70% → 退款路径，`serv_finish_refund_status` 流转，`income` 终态为 NO_NEED。
- 下架率 ≥ 70% → 确收路径，`serv_finish_income_status` 流转，`refund` 终态为 NO_NEED。
- 退款金额 = `total_amount - init_allowance_amount`（已发补贴）。

**判定**：
- 计算 `yc_tort_record` 下架率，与 settle_order 子状态匹配。
- 校验退款金额是否等于公式结果。

**Pass 证据**：下架率与路径一致，金额与公式一致。
**Fail 证据**：分流方向与下架率矛盾，或金额错误。

## 输出格式

每条规则输出一张 Markdown 表格：

| 规则 | applyId | rightId | settleId | 预期 | 实际 | 证据 | 结果 | SQL 模板 |
|------|---------|---------|----------|------|------|------|------|----------|
| R1 9类白名单 | 200000885 | 10001 | 430 | 是9类 | 是9类 | category=16∈白名单 | PASS | SQL-T1 |
| R2 补贴资格 | 200000885 | 10001 | 430 | init_allowance_start_time≠NULL | 非NULL | 2026-07-07 | PASS | SQL-T2 |
| R6 下架率分流 | 200000885 | 10001 | 430 | 下架率0%→退款 | refund=FINISH | 侵权0条 | PASS | SQL-T8/T9 |

汇总：
- `PASS / FAIL / PENDING / BLOCKED` 计数
- 失败项高亮，附根因推断与下一步排查建议

## 关联 Skill 路由

| 场景 | 路由 |
|------|------|
| 需要造数或触发 ScheduleX | `yc-data-factory` |
| 结算链路分析/资金流向 | `yc-settlement-analyser` |
| 失败根因定位 / MetaQ / ScheduleX | `yc-defect-diagnosis` |
| 更新 XMind 用例验证结果 | `yc-db-verification` |
| 构造快审/初审申请 | `yc-quick-audit-data-create` |

## 验证

校验完成标志：
- [ ] 输入 ID 已做 env='staging' 预检
- [ ] R1~R6 至少执行了适用规则
- [ ] 每条规则输出 pass/fail、证据、SQL 模板编号
- [ ] 失败项已给出根因推断和下一步 Skill 路由
