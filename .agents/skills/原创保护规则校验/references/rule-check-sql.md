# 原创保护规则校验 SQL 模板

> 目标库：scenario（`database_id = 975919`）。所有查询只读，禁止 DML。
> 环境铁律：对 `yc_right_apply` / `yc_right` / `yc_right_settle_order` / `yc_tort_record` 等带 env 列的表，必须加 `env = 'staging'`。

## 调用方式

使用 `mcp__dms-mcp-server__executeScript`：

```
database_id: "975919"
script: "<SQL>"
```

---

## SQL-T1: 9 类白名单校验（按申请）

判断申请/权益类目是否在 9 类白名单内。

```sql
SELECT a.id AS apply_id,
       a.category AS apply_category,
       r.id AS right_id,
       r.category AS right_category,
       CASE WHEN a.category IN (16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001)
            THEN 'YES' ELSE 'NO' END AS is_9class_apply,
       CASE WHEN r.category IN (16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001)
            THEN 'YES' ELSE 'NO' END AS is_9class_right
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
WHERE a.id = {applyId}
  AND a.env = 'staging'
  AND r.env = 'staging';
```

**适用规则**：R1

---

## SQL-T2: 补贴发放资格校验（单申请全链路）

查询申请、权益、结算单 JOIN，判断补贴字段是否与 9 类/首发一致。

```sql
SELECT a.id AS apply_id,
       a.category AS apply_category,
       CASE WHEN a.category IN (16,30,50006843,50011740,1625,50010404,50006842,28,50468001)
            THEN 'YES' ELSE 'NO' END AS is_9class,
       r.first_publish,
       s.id AS settle_id,
       s.settle_status,
       s.total_amount,
       s.init_allowance_start_time,
       s.init_allowance_amount,
       CASE
         WHEN s.init_allowance_start_time IS NULL THEN 'NOT_TRIGGERED'
         WHEN r.first_publish = 1 THEN 'INIT_ALLOWANCE'
         WHEN r.first_publish = 0 THEN 'NOT_INIT_ALLOWANCE'
         ELSE 'UNKNOWN'
       END AS allowance_type_expected
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id
   AND s.env = 'staging'
WHERE a.id = {applyId}
  AND a.env = 'staging'
  AND r.env = 'staging'
ORDER BY s.id DESC
LIMIT 1;
```

**适用规则**：R2

---

## SQL-T3: 申请 + 权益 + 结算单 全量 JOIN（批量）

批量校验补贴与结算状态。

```sql
SELECT a.id AS apply_id, a.outer_apply_id, a.status AS apply_status,
       a.apply_type, a.category, a.to_regular_status,
       r.id AS right_id, r.status AS right_status,
       r.first_publish, r.protect_expire_time,
       s.id AS settle_id, s.settle_status,
       s.total_amount, s.init_allowance_start_time, s.init_allowance_amount,
       s.serv_finish_refund_status, s.serv_finish_income_status
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id AND s.env = 'staging'
WHERE a.id IN (/* applyId list */)
  AND a.env = 'staging'
  AND r.env = 'staging'
ORDER BY a.id, s.id;
```

**适用规则**：R2 / R4 / R5

---

## SQL-T4: 首发编辑权限校验

校验首发编辑权限 = 9 类且未转普通。

```sql
SELECT a.id AS apply_id,
       a.category,
       CASE WHEN a.category IN (16,30,50006843,50011740,1625,50010404,50006842,28,50468001)
            THEN 'YES' ELSE 'NO' END AS is_9class,
       a.to_regular_status,
       r.first_publish,
       CASE
         WHEN a.category IN (16,30,50006843,50011740,1625,50010404,50006842,28,50468001)
              AND (a.to_regular_status IS NULL OR a.to_regular_status != 'DONE')
         THEN 'EDITABLE'
         ELSE 'DISABLED'
       END AS expected_edit_permission
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
WHERE a.id = {applyId}
  AND a.env = 'staging'
  AND r.env = 'staging';
```

**适用规则**：R3

---

## SQL-T5: 转普通流程校验（结算单生命周期）

查询同一申请下的全部结算单，验证旧单 CANCEL + 新单 PROCESSING。

```sql
SELECT s.id AS settle_id,
       s.right_apply_id,
       s.settle_status,
       s.total_amount,
       s.init_allowance_start_time,
       s.init_allowance_amount,
       s.gmt_create,
       s.gmt_modified
FROM yc_right_settle_order s
WHERE s.right_apply_id = {applyId}
  AND s.env = 'staging'
ORDER BY s.id;
```

**适用规则**：R4

---

## SQL-T6: 操作流水还原（转普通/状态变更）

还原申请操作时间线，确认 SYNC_CERT_FILE、转普通、结算单创建/取消等事件。

```sql
SELECT id, op_type, op_detail, gmt_create
FROM yc_right_apply_op_record
WHERE right_apply_id = {applyId}
ORDER BY gmt_create ASC;
```

**适用规则**：R4 / R5

---

## SQL-T7: 按 seller_id 批量 9 类/补贴一致性扫描

扫描同一商家近期申请，批量发现 9 类与补贴不一致的数据。

```sql
SELECT a.id AS apply_id,
       a.category,
       CASE WHEN a.category IN (16,30,50006843,50011740,1625,50010404,50006842,28,50468001)
            THEN 'YES' ELSE 'NO' END AS is_9class,
       r.first_publish,
       s.id AS settle_id,
       s.init_allowance_start_time,
       s.init_allowance_amount
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id AND s.env = 'staging'
WHERE a.seller_id = {sellerId}
  AND a.env = 'staging'
  AND r.env = 'staging'
ORDER BY a.id DESC
LIMIT 100;
```

**适用规则**：R1 / R2

---

## SQL-T8: 结算状态机完整校验（最新非 CANCEL 结算单）

查询退款/确收子状态与金额，用于状态机与分流判定。

```sql
SELECT id,
       settle_status,
       total_amount,
       init_allowance_start_time,
       init_allowance_amount,
       serv_finish_refund_status,
       serv_finish_refund_amount,
       serv_finish_income_status,
       serv_finish_income_amount
FROM yc_right_settle_order
WHERE right_apply_id = {applyId}
  AND env = 'staging'
  AND settle_status != 'CANCEL'
ORDER BY id DESC
LIMIT 1;
```

**适用规则**：R5 / R6

---

## SQL-T9: 侵权记录下架率计算

计算指定权益的侵权下架率，用于下架率分流判定。

```sql
SELECT
    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) AS taken_down_cnt,
    COUNT(*) AS total_cnt,
    ROUND(COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) * 100.0 / COUNT(*), 2) AS take_down_rate_pct,
    GROUP_CONCAT(DISTINCT status) AS status_list
FROM yc_tort_record
WHERE right_id = {rightId}
  AND env = 'staging';
```

**适用规则**：R6

---

## SQL-T10: 退款金额公式校验

验证退款金额是否等于 total_amount - init_allowance_amount。

```sql
SELECT id,
       total_amount,
       init_allowance_amount,
       serv_finish_refund_amount,
       (total_amount - COALESCE(init_allowance_amount, 0)) AS expected_refund_amount,
       CASE WHEN serv_finish_refund_amount = (total_amount - COALESCE(init_allowance_amount, 0))
            THEN 'PASS' ELSE 'FAIL' END AS refund_amount_check
FROM yc_right_settle_order
WHERE right_apply_id = {applyId}
  AND env = 'staging'
  AND settle_status != 'CANCEL'
ORDER BY id DESC
LIMIT 1;
```

**适用规则**：R6

---

## SQL-T11: 环境预检（执行任何规则前必须调用）

确认 applyId / rightId 属于 staging 环境，防止误查生产数据。

```sql
-- apply 预检
SELECT id, env FROM yc_right_apply WHERE id = {applyId};

-- right 预检
SELECT id, env FROM yc_right WHERE id = {rightId};

-- settle 预检（如已知 settleId）
SELECT id, env FROM yc_right_settle_order WHERE id = {settleId};
```

**适用规则**：所有规则前置安全检查
