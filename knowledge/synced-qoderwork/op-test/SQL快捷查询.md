<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护执行助手/references/SQL快捷查询.md -->
<!-- synced-at: 2026-07-11T03:52:34.999541 -->
<!-- skill: 原创保护执行助手 -->

# 原创保护 SQL 快捷查询

> 库名：scenario (实际DB名=prod) | 主机：33.9.212.198:3011 | db_id：975919
> 使用方式：复制 SQL 到 DMS MCP `mcp__dms-mcp-server__executeScript`，替换 `{参数}` 为实际值

---

## 1. 申请查询

### 1.1 按 apply_id 查申请
```sql
SELECT a.id, a.right_id, a.outer_apply_id AS yc_no, a.seller_id, a.status,
       a.apply_type, a.apply_time, a.to_regular_status, a.to_regular_suggest_time,
       a.gmt_create, a.gmt_modified
FROM yc_right_apply a
WHERE a.id = {apply_id};
```

### 1.2 按 YC编号 查申请
```sql
SELECT a.id, a.right_id, a.outer_apply_id AS yc_no, a.seller_id, a.status,
       a.apply_type, a.apply_time, a.to_regular_status,
       a.gmt_create, a.gmt_modified
FROM yc_right_apply a
WHERE a.outer_apply_id = '{yc_no}';
```

### 1.3 按 seller_id 查全部申请
```sql
SELECT a.id, a.outer_apply_id AS yc_no, a.status, a.apply_type,
       a.to_regular_status, a.gmt_create, a.gmt_modified
FROM yc_right_apply a
WHERE a.seller_id = {seller_id}
ORDER BY a.gmt_create DESC
LIMIT 50;
```

### 1.4 查申请状态变更历史
```sql
SELECT op.id, op.operate_type, op.operator, op.operator_name,
       op.before_status, op.after_status, op.gmt_create
FROM yc_right_apply_op_record op
WHERE op.right_apply_id = {apply_id}
ORDER BY op.gmt_create;
```

---

## 2. Right（专利权）查询

### 2.1 按 right_id 查 Right
```sql
SELECT r.id, r.seller_id, r.status, r.first_publish,
       r.protect_start_time, r.protect_expire_time, r.submit_protect_expire_time,
       r.gmt_create, r.gmt_modified
FROM yc_right r
WHERE r.id = {right_id};
```

### 2.2 按 seller_id 查全部 Right
```sql
SELECT r.id, r.status, r.first_publish,
       r.protect_start_time, r.protect_expire_time, r.submit_protect_expire_time,
       DATEDIFF(r.protect_expire_time, CURDATE()) AS days_until_expire,
       CASE
         WHEN CURDATE() >= r.submit_protect_expire_time AND CURDATE() <= r.protect_expire_time THEN 'IN_20DAY_WINDOW'
         WHEN CURDATE() > r.protect_expire_time THEN 'EXPIRED'
         ELSE 'OUTSIDE_WINDOW'
       END AS window_status
FROM yc_right r
WHERE r.seller_id = {seller_id} AND r.protect_expire_time IS NOT NULL
ORDER BY r.protect_expire_time ASC;
```

### 2.3 查20天窗口内的 Right
```sql
SELECT r.id, r.seller_id, r.status, r.first_publish,
       r.protect_expire_time, r.submit_protect_expire_time,
       DATEDIFF(r.protect_expire_time, CURDATE()) AS days_until_expire
FROM yc_right r
WHERE r.seller_id = {seller_id}
  AND r.protect_expire_time IS NOT NULL
  AND CURDATE() >= r.submit_protect_expire_time
  AND CURDATE() <= r.protect_expire_time
ORDER BY r.protect_expire_time;
```

### 2.4 查 Right 状态分布（按 seller）
```sql
SELECT r.status, COUNT(*) AS cnt
FROM yc_right r
WHERE r.seller_id = {seller_id}
GROUP BY r.status;
```

---

## 3. 结算单查询

### 3.1 按 apply_id 查结算单
```sql
SELECT so.id, so.right_apply_id, so.settle_status, so.total_amount,
       so.init_allowance_start_time, so.init_allowance_amount,
       so.serv_finish_refund_status, so.serv_finish_refund_amount,
       so.serv_finish_income_status, so.serv_finish_income_amount,
       so.balance_income_amount, so.gmt_create, so.gmt_modified
FROM yc_right_settle_order so
WHERE so.right_apply_id = {apply_id};
```

### 3.2 查结算单状态分布（按 seller）
```sql
SELECT so.settle_status, COUNT(*) AS cnt
FROM yc_right_settle_order so
JOIN yc_right_apply a ON a.id = so.right_apply_id
WHERE a.seller_id = {seller_id}
GROUP BY so.settle_status;
```

### 3.3 查补贴发放情况
```sql
SELECT so.id, so.right_apply_id, so.settle_status,
       so.init_allowance_start_time, so.init_allowance_amount,
       a.outer_apply_id AS yc_no, a.status AS apply_status
FROM yc_right_settle_order so
JOIN yc_right_apply a ON a.id = so.right_apply_id
WHERE a.seller_id = {seller_id}
  AND so.init_allowance_start_time IS NOT NULL
ORDER BY so.gmt_create DESC;
```

---

## 4. 入驻查询

### 4.1 查商家入驻状态
```sql
SELECT seller_id, status, gmt_create, gmt_modified
FROM yc_seller_enter_info
WHERE seller_id = {seller_id};
```

### 4.2 查全部入驻商家
```sql
SELECT seller_id, status, gmt_create
FROM yc_seller_enter_info
ORDER BY gmt_create DESC
LIMIT 50;
```

---

## 5. 维权与侵权查询

### 5.1 按 right_id 查维权记录
```sql
SELECT p.id, p.tort_record_id, p.protect_way, p.status AS protect_status,
       p.start_time, p.end_time, p.gmt_create
FROM yc_right_protect_record p
WHERE p.tort_record_id IN (
  SELECT t.id FROM tort_record t WHERE t.right_id = {right_id}
);
```

### 5.2 按 right_id 查侵权记录
```sql
SELECT t.id, t.right_id, t.status, t.outer_tort_id,
       t.gmt_create, t.gmt_modified
FROM tort_record t
WHERE t.right_id = {right_id}
ORDER BY t.gmt_create DESC;
```

### 5.3 查维权状态汇总（按 seller）
```sql
SELECT t.status AS tort_status, p.protect_way, p.status AS protect_status, COUNT(*) AS cnt
FROM tort_record t
LEFT JOIN yc_right_protect_record p ON p.tort_record_id = t.id
JOIN yc_right r ON r.id = t.right_id
WHERE r.seller_id = {seller_id}
GROUP BY t.status, p.protect_way, p.status;
```

---

## 6. 白名单查询

### 6.1 查商家白名单
```sql
SELECT id, seller_id, shop_name, gmt_create, gmt_modified
FROM inspect_whitelist
WHERE seller_id = {seller_id};
```

---

## 7. 服务交易查询

### 7.1 查服务交易记录（按 seller）
```sql
SELECT id, seller_id, trade_type, trade_amount, trade_time,
       gmt_create, gmt_modified
FROM service_trade_record
WHERE seller_id = {seller_id}
ORDER BY gmt_create DESC
LIMIT 30;
```

---

## 8. 退款查询

### 8.1 按 apply_id 查退款单
```sql
SELECT ro.id, ro.right_apply_id, ro.refund_status, ro.refund_amount,
       ro.refund_reason, ro.gmt_create, ro.gmt_modified
FROM refund_apply_order ro
WHERE ro.right_apply_id = {apply_id};
```

---

## 9. 综合诊断查询

### 9.1 一键查申请全貌（apply_id 入口）
```sql
SELECT
  a.id AS apply_id, a.outer_apply_id AS yc_no, a.seller_id, a.status AS apply_status,
  a.apply_type, a.to_regular_status, a.apply_time,
  r.id AS right_id, r.status AS right_status, r.first_publish,
  r.protect_expire_time, r.submit_protect_expire_time,
  so.id AS settle_id, so.settle_status, so.total_amount,
  so.init_allowance_start_time, so.init_allowance_amount,
  sei.status AS enter_status
FROM yc_right_apply a
LEFT JOIN yc_right r ON r.id = a.right_id
LEFT JOIN yc_right_settle_order so ON so.right_apply_id = a.id
LEFT JOIN yc_seller_enter_info sei ON sei.seller_id = a.seller_id
WHERE a.id = {apply_id};
```

### 9.2 一键查商家全貌（seller_id 入口）
```sql
SELECT
  a.id AS apply_id, a.outer_apply_id AS yc_no, a.status AS apply_status, a.apply_type,
  r.status AS right_status, r.first_publish, r.protect_expire_time,
  so.settle_status, so.init_allowance_start_time,
  sei.status AS enter_status
FROM yc_right_apply a
LEFT JOIN yc_right r ON r.id = a.right_id
LEFT JOIN yc_right_settle_order so ON so.right_apply_id = a.id
LEFT JOIN yc_seller_enter_info sei ON sei.seller_id = a.seller_id
WHERE a.seller_id = {seller_id}
ORDER BY a.gmt_create DESC
LIMIT 30;
```

### 9.3 查快审未校验入驻的异常数据
```sql
SELECT a.id, a.outer_apply_id, a.seller_id, a.status, a.apply_type,
       sei.status AS enter_status
FROM yc_right_apply a
LEFT JOIN yc_seller_enter_info sei ON sei.seller_id = a.seller_id
WHERE a.apply_type = 'QUICK'
  AND (sei.status IS NULL OR sei.status != 'ENTERED')
ORDER BY a.gmt_create DESC;
```

---

## 参数说明

| 参数 | 含义 | 示例 |
|---|---|---|
| `{apply_id}` | 申请ID | 200001005 |
| `{yc_no}` | YC编号 (outer_apply_id) | YC31647667296 |
| `{seller_id}` | 商家ID | 2213249110271 |
| `{right_id}` | 专利权ID | 100001071 |

## 金额单位提醒

`yc_right_settle_order` 所有金额字段（total_amount, init_allowance_amount, serv_finish_refund_amount 等）单位为 **分**，非元。
- 测试环境: total_amount=10 (0.10元), 首发补贴=6 (0.06元)
- 生产环境: total_amount=50000 (500元), 首发补贴=30200 (302元)
