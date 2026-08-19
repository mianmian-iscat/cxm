# SQL 查询模板

## DMS MCP 调用方式

```
工具: mcp__dms-mcp-server__executeScript
参数:
  database_id: "975919"   # scenario 库
  script: "<SQL语句>"
```

---

## 模板1: 申请记录基础信息

查询指定申请编号的基本状态和类型信息。

```sql
SELECT a.id, a.outer_apply_id, a.status, a.apply_type,
       a.category, a.to_regular_status,
       a.gmt_create, a.gmt_modified
FROM yc_right_apply a
WHERE a.id IN (/* 申请编号列表 */);
```

**适用场景**：验证申请状态机、转普通状态、申请类型

---

## 模板2: 申请 + 权益记录 JOIN

查询申请及其关联的权益记录（含首发标记、保护期）。

```sql
SELECT a.id AS apply_id, a.outer_apply_id, a.status AS apply_status,
       a.apply_type, a.category AS apply_category,
       a.to_regular_status,
       r.id AS right_id, r.status AS right_status,
       r.first_publish, r.category AS right_category,
       r.protect_expire_time
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
WHERE a.id IN (/* 申请编号列表 */)
ORDER BY a.id;
```

**适用场景**：验证首发编辑权限、保护期状态

---

## 模板3: 申请 + 权益 + 结算单 全量 JOIN

查询申请的完整链路信息，包括结算单和补贴状态。

```sql
SELECT a.id AS apply_id, a.outer_apply_id, a.status AS apply_status,
       a.apply_type, a.category AS apply_category,
       a.to_regular_status,
       a.gmt_create AS apply_create,
       r.id AS right_id, r.status AS right_status,
       r.first_publish, r.category AS right_category,
       r.protect_expire_time,
       s.id AS settle_id, s.settle_status,
       s.total_amount,
       s.init_allowance_start_time,
       s.init_allowance_amount
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id
WHERE a.id IN (/* 申请编号列表 */)
ORDER BY a.id;
```

**适用场景**：补贴逻辑验证（最常用模板）

---

## 模板4: 结算单专项查询

查询指定申请的结算单详情。

```sql
SELECT s.id AS settle_id, s.right_apply_id,
       s.settle_status, s.total_amount,
       s.init_allowance_start_time,
       s.init_allowance_amount,
       s.serv_finish_refund_status,
       s.gmt_create, s.gmt_modified
FROM yc_right_settle_order s
WHERE s.right_apply_id IN (/* 申请编号列表 */)
ORDER BY s.id;
```

**适用场景**：验证补贴触发状态、结算金额

---

## 模板5: 操作流水还原

查询指定申请的操作流水，按时间排序还原业务流程。

```sql
SELECT id, op_type, op_detail, gmt_create
FROM yc_right_apply_op_record
WHERE right_apply_id = /* 申请编号 */
ORDER BY gmt_create ASC;
```

**适用场景**：还原业务操作时间线、追踪状态变更历史

---

## 模板6: 按 seller_id 查询所有申请

查询指定商家的所有申请记录。

```sql
SELECT a.id, a.outer_apply_id, a.status, a.apply_type,
       a.category, a.to_regular_status,
       a.gmt_create, a.gmt_modified,
       r.first_publish, r.category AS right_category
FROM yc_right_apply a
JOIN yc_right r ON a.right_id = r.id
WHERE a.seller_id = /* seller_id */
ORDER BY a.id DESC;
```

**适用场景**：查看商家维度的所有申请

---

## 模板7: 补贴状态批量检查

批量检查指定申请的补贴状态。

```sql
SELECT s.id AS settle_id, s.right_apply_id, a.outer_apply_id,
       s.settle_status, s.total_amount,
       s.init_allowance_start_time,
       s.init_allowance_amount
FROM yc_right_settle_order s
JOIN yc_right_apply a ON s.right_apply_id = a.id
WHERE s.id IN (/* 结算单ID列表 */)
ORDER BY s.id;
```

**适用场景**：已知结算单 ID 时快速检查补贴状态

---

## 模板8: 脏数据排查

查询指定商家的历史记录，排查可能的脏数据（6.20 之前的旧数据等）。

```sql
SELECT a.id, a.outer_apply_id, a.status, a.apply_type,
       a.category, a.gmt_create,
       s.id AS settle_id, s.settle_status,
       s.init_allowance_start_time
FROM yc_right_apply a
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id
WHERE a.seller_id = /* seller_id */
  AND a.gmt_create < '2026-06-20'
ORDER BY a.id DESC;
```

**适用场景**：排查 6.20 之前的旧数据（init_allowance_start_time 可能已被赋值，属于旧代码无类目校验时的预期行为）

---

## 模板9: 快审扣减验证 [需求#83368125]

验证快审全程不扣减、初审提交时才扣减的核心查询组合。

```sql
-- 9a. 结算单检查（核心证据）
SELECT s.id AS settle_id, s.right_apply_id, s.settle_status,
       s.total_amount, s.gmt_create, s.gmt_modified
FROM yc_right_settle_order s
WHERE s.right_apply_id IN (/* 申请编号列表 */)
ORDER BY s.right_apply_id, s.id;
-- 预期: 快审阶段无新增; 初审提交后新增TO_DO; ~50min后变DONE

-- 9b. 交易记录检查（应无快审相关记录）
SELECT t.id, t.trade_type, t.biz_scene, t.amount, t.gmt_create
FROM yc_service_trade_record t
WHERE t.seller_id = /* seller_id */
  AND t.is_deleted = 0
  AND t.gmt_create >= '/* 快审发起时间 */'
ORDER BY t.gmt_create DESC;
-- 预期: 无DEDUCT/CONSUME类型; 快审阶段rowCount=0

-- 9c. 操作流水还原（确认API调用成功）
SELECT id, operate_type, operate_time, operator_name
FROM yc_right_apply_op_record
WHERE right_apply_id IN (/* 申请编号列表 */)
ORDER BY right_apply_id, gmt_create ASC;
-- 预期链路: SUBMIT_QUICK_APPLY → QUICK_AUDIT_AGREE/REJECT → SUBMIT_APPLY

-- 9d. 商家权益次数统计
SELECT seller_id, total_count, used_count, remain_count
FROM yc_seller_right_statistics
WHERE seller_id = /* seller_id */;
-- 注意: remainRightCount由服务市场侧计算,当已购次数消耗完显示0
```

**适用场景**：快审扣减时机验证（#83368125），新旧代码驳回行为对比

---

## 模板10: 新旧代码驳回对比

对比新代码（快审不扣减）和旧代码（快审扣减→驳回返还）的结算单差异。

```sql
SELECT a.id AS apply_id, a.status, a.apply_type,
       a.gmt_create, a.gmt_modified,
       s.id AS settle_id, s.settle_status, s.total_amount,
       s.gmt_create AS settle_create
FROM yc_right_apply a
LEFT JOIN yc_right_settle_order s ON s.right_apply_id = a.id
WHERE a.id IN (
  /* 新代码驳回: 如200000758 */
  /* 旧代码驳回: 如200000731 */
)
ORDER BY a.id;
-- 新代码预期: settle_id=NULL(无结算单)
-- 旧代码预期: settle_status=CANCEL(提交时扣→驳回返还)
```

**适用场景**：快审驳回行为差异验证
