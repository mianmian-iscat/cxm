---
name: yc-db-verification
description: 通过DMS MCP查询原创保护scenario DB验证测试数据，分析操作流水(yc_right_apply_op_record)还原业务流程，并根据验证结果更新XMind用例。适用于用已有测试数据验证补贴逻辑、转普通流程、状态机流转、首发编辑权限、快审扣减时机(settle_order)等场景。触发词：DB验证、查DB验证用例、数据库验证、scenario DB验证、DMS验证、op_record分析、操作流水还原、更新用例验证结果、快审扣减验证、settle_order查询、新旧代码驳回对比。
version: 1.0.0
---

# 原创保护 DB 数据验证

通过 DMS MCP 直接查询 scenario 数据库，验证原创保护测试数据的状态机流转、补贴逻辑、首发编辑权限等业务规则，并根据 DB 查询结果更新 XMind 测试用例状态。

## 前置条件

1. **DMS MCP 已连接**：确认 `mcp__dms-mcp-server__executeScript` 工具可用
2. **数据库 ID**：scenario 库 = `975919`（预发/生产共用）
3. **用户输入**：至少提供以下之一
   - 申请编号（`yc_right_apply.id`）
   - seller_id
   - 需求编号（关联 XMind 用例文件）

## 核心表与字段速查

> 详细表结构和业务规则见 [references/tables-and-rules.md](references/tables-and-rules.md)

| 表名 | 核心字段 | 验证用途 |
|------|----------|----------|
| `yc_right_apply` | id, outer_apply_id, status, apply_type, category, to_regular_status, gmt_create, gmt_modified | 申请状态机、转普通流程 |
| `yc_right` | id, first_publish, category, protect_expire_time | 首发标记、保护期 |
| `yc_right_settle_order` | id, settle_status, total_amount, init_allowance_start_time, init_allowance_amount | 补贴触发判定 |
| `yc_right_apply_op_record` | id, op_type, op_detail, gmt_create | 操作流水还原 |

## 工作流

### Phase 1: 明确验证目标

询问用户：
1. 要验证哪些申请编号？（如 200000747, 200000752, 200000755）
2. 要验证哪些业务规则？（补贴逻辑 / 首发权限 / 转普通 / 状态机 / 全量）
3. 是否有关联的 XMind 用例文件需要更新？

### Phase 2: DB 查询

使用 `mcp__dms-mcp-server__executeScript` 执行查询。SQL 模板见 [references/query-templates.md](references/query-templates.md)。

> 🚨 **SQL 过滤铁律（2026-08-04）**：所有查询必须加 `env='staging'` 过滤（yc_right_apply / yc_right / yc_right_settle_order 均有 env 列）；无 env 列的表（yc_right_apply_op_record 等）必须通过已核实的 staging applyId/rightId 间接过滤；禁止无过滤裸查。scenario 库预发与生产共用同一物理库，漏过滤会命中生产数据。

**查询顺序**：
1. 申请记录基础信息（`yc_right_apply`）
2. 关联权益记录（JOIN `yc_right`）
3. 关联结算单（JOIN `yc_right_settle_order`）
4. 操作流水时间线（`yc_right_apply_op_record`）

**多表 JOIN 全量查询模板**：
```sql
SELECT a.id AS apply_id, a.outer_apply_id, a.status AS apply_status,
       a.apply_type, a.category, a.to_regular_status,
       a.gmt_create AS apply_create,
       r.id AS right_id, r.status AS right_status, r.first_publish,
       r.protect_expire_time, r.category AS right_category,
       s.id AS settle_id, s.settle_status, s.total_amount,
       s.init_allowance_start_time, s.init_allowance_amount
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id
WHERE a.id IN (/* 申请编号列表 */)
ORDER BY a.id;
```

### Phase 3: 业务规则比对

将 DB 查询结果与预期规则逐条比对，判定每条用例状态：

| 状态标记 | 含义 |
|----------|------|
| ✅ PASS | DB 数据与预期一致 |
| ❌ FAIL | DB 数据与预期不符 |
| ⏳ PENDING | 需等待 Job 执行/外部操作后才能验证 |
| ⏭ BLOCKED | 缺少测试数据，无法验证 |

**补贴逻辑判定规则**：
- `init_allowance_start_time IS NULL` → 补贴未触发
- `init_allowance_start_time IS NOT NULL` → 补贴已触发（此时 `init_allowance_amount` 必有值）
- 非 9 类商家：settle_order 可存在，但 init_allowance_start_time 必须保持 NULL
- 9 类商家：settle_order 存在且 init_allowance_start_time 应被赋值

**首发编辑权限规则**：
- 运营端可编辑 = 9 类商家 **且** 未转普通（`to_regular_status ≠ DONE`）
- 非 9 类商家：两端均不可编辑（disabled，无 tooltip）
- 转普通后：即使 9 类也不可编辑

**转普通流程规则**：
- `to_regular_status = DONE` → 已转普通
- 转普通后 settle_order 可能重建（旧单 CANCEL，新单 PROCESSING）

### Phase 4: 更新 XMind 用例

根据验证结果更新 XMind txt 文件中对应用例的状态：

1. **定位用例**：在用例文件中搜索申请编号或用例编号（如 F3.6, F5.1）
2. **更新状态标记**：将 ⏭SKIP/⏳待Job 改为 ✅PASS/❌FAIL/⏳PENDING
3. **补充数据验证说明**：在对应用例下添加/更新数据验证行，格式：
   ```
   数据验证：申请编号200000752，主营=124484008∉9类 → settle_id=430(PROCESSING)，init_allowance_start_time=NULL
   ```
4. **排除脏数据**：如用户标记某条数据为脏数据，从所有用例中移除并添加排除说明

### Phase 5: 输出验证报告

以表格形式汇总验证结果：

| 申请编号 | 主营类目 | 9类？ | 验证项 | 预期 | 实际 | 结果 |
|----------|----------|-------|--------|------|------|------|
| 200000752 | 124484008 | 否 | init_allowance_start_time | NULL | NULL | ✅PASS |
| 200000747 | 16 | 是 | init_allowance_start_time | ≠NULL | NULL | ⏳PENDING |

## 常见验证场景

### 场景1: 补贴逻辑验证（init_allowance_start_time）

**目标**：验证 9 类白名单商家获得补贴，非 9 类不获得

**关键查询**：
```sql
SELECT s.id AS settle_id, s.right_apply_id, s.settle_status,
       s.total_amount, s.init_allowance_start_time, s.init_allowance_amount
FROM yc_right_settle_order s
WHERE s.right_apply_id IN (/* 申请编号 */);
```

**判定逻辑**：
- 9 类商家 → `init_allowance_start_time IS NOT NULL`（Job 执行后）
- 非 9 类商家 → `init_allowance_start_time IS NULL`（永远保持 NULL）

**注意**：`total_amount` 是基础结算金额（测试环境=10，生产=50000），不代表补贴金额。补贴看 `init_allowance_start_time`。

### 场景2: 首发编辑权限验证

**目标**：验证首发编辑权限 = 9 类 + 未转普通

**关键查询**：
```sql
SELECT a.id, a.to_regular_status, a.category, r.first_publish
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
WHERE a.id IN (/* 申请编号 */);
```

**判定逻辑**：
- `to_regular_status IS NULL` + 主营∈9 类 → 运营端可编辑
- `to_regular_status = DONE` + 主营∈9 类 → 运营端不可编辑
- 主营∉9 类 → 两端均不可编辑

### 场景3: 转普通流程验证

**目标**：验证转普通申请的状态机流转

**关键查询**：
```sql
SELECT a.id, a.status, a.to_regular_status, a.gmt_create, a.gmt_modified
FROM yc_right_apply a
WHERE a.id IN (/* 申请编号 */);
```

**操作流水还原**：
```sql
SELECT op_type, op_detail, gmt_create
FROM yc_right_apply_op_record
WHERE right_apply_id = /* 申请编号 */
ORDER BY gmt_create ASC;
```

通过 op_record 时间线还原：申请创建 → 快审通过 → 商品一致性确认 → 转普通 → 结算单创建/取消/重建

### 场景4: 状态机流转验证

**目标**：验证申请状态变更链路是否符合预期

**正常流转**：
```
AUDITING → QUICK_AUDITING → QUICK_AUDIT_PASS → CERT_FILE_SYNCED → YC_PROTECTING
```

**转普通分支**：
```
CERT_FILE_SYNCED → (触发转普通) → to_regular_status=DONE → settle_order 重建
```

### 场景5: 结算端到端验证（SchedulerX Job 链）

**目标**：验证专利到期后结算单按下架率正确分流并完成退款/确收

**触发词**：结算验证、退款验证、确收验证、失效扫描、settlement e2e

**完整流程**：详见 `yc-data-factory` 的 [references/settlement-e2e.md](../yc-data-factory/references/settlement-e2e.md)

**关键 SQL**：
```sql
-- 查 settle_order 子状态（退款路径）
SELECT id, settle_status,
       serv_finish_refund_status, serv_finish_refund_amount,
       serv_finish_income_status, serv_finish_income_amount
FROM yc_right_settle_order
WHERE right_apply_id = {applyId} AND env = 'staging'
AND settle_status != 'CANCEL'
ORDER BY id DESC LIMIT 1;

-- 查侵权记录计算下架率
SELECT status, COUNT(*) AS cnt
FROM yc_tort_record
WHERE right_id = {rightId} AND env = 'staging'
GROUP BY status;
```

**判定逻辑**：
- 下架率 < 70% → `serv_finish_refund_status` 流转（TO_DO → PROCESSING → FINISH），`serv_finish_income_status` 保持 NULL
- 下架率 ≥ 70% → `serv_finish_income_status` 流转，`serv_finish_refund_status` 保持 NULL
- `yc_right.status` 从 YC_PROTECTING 变为 YC_PROTECT_INVALID（Task 399576024 执行后）

**SchedulerX Task ID**：
- 399576024（专利保护定时失效）→ 719211870（退款）/ 721504806（确收）

## 踩坑与注意事项

1. **total_amount ≠ 补贴金额**：是结算单基础金额（测试环境=10，生产=50000），不代表补贴金额。补贴是否触发看 `init_allowance_start_time`。
2. **补贴校验时间点**：取 `SYNC_CERT_FILE`（确认商品一致性）时的 ODPS 主营类目快照，非申请创建时，也非当前时刻。
3. **首发编辑权限双条件**：9 类 + 未转普通，两个条件同时满足才可在运营端编辑。
4. **DMS 安全规则**：生产环境不能直接 UPDATE/DELETE（DMS 禁止直接 DML），需提交变更工单。
5. **脏数据排除**：用户标记为脏数据的申请编号，从所有用例中移除并明确标注。
6. **主营类目变更**：同一商家可能跨越主营变更前后，补贴判定结果不同（取 SYNC_CERT_FILE 时的快照）。
7. **settle_order 重建**：转普通后旧结算单 CANCEL，新结算单 PROCESSING，验证时注意区分。

## 验证

验证成功的标志：
- 所有申请编号的 DB 查询结果已返回
- 每条用例的预期 vs 实际已比对并标注状态
- XMind 用例文件已更新（如用户提供）
- 验证报告表格已输出
