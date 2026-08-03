# 原创保护 DB 表速查

> 库名：scenario（实际 DB 名 = prod）  
> 主机：33.9.212.198:3011  
> db_id：975919  
> 方式：DMS MCP（`mcp__dms-mcp-server__executeScript`）或 dms-alibaba CLI

---

## 12 张核心表

### 1. yc_right — 专利权主表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| seller_id | BIGINT | 商家 ID |
| status | VARCHAR | Right 状态：APPLYING / YC_PROTECTING / YC_PROTECT_INVALID |
| apply_time | DATETIME | 申请时间 |
| protect_expire_time | DATETIME | 保护到期时间 |
| first_publish | TINYINT | 是否首发：0=否 / 1=是 |
| right_no | VARCHAR | 专利权编号 |
| item_id | BIGINT | 绑定商品 ID |
| category | VARCHAR | 类目（文本） |
| gmt_create | DATETIME | 创建时间 |
| gmt_modified | DATETIME | 修改时间 |

**常用查询：**
```sql
-- 查商家所有专利权
SELECT id, status, apply_time, protect_expire_time, first_publish
FROM yc_right WHERE seller_id = ? ORDER BY apply_time DESC LIMIT 10;

-- 查即将到期的专利权（30天内）
SELECT id, seller_id, protect_expire_time
FROM yc_right WHERE status = 'YC_PROTECTING'
  AND protect_expire_time BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 30 DAY);
```

---

### 2. yc_right_apply — 申请记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_id | BIGINT | 关联 yc_right.id |
| seller_id | BIGINT | 商家 ID |
| status | VARCHAR | 申请状态（见状态机） |
| apply_type | VARCHAR | 申请类型：QUICK / PRE |
| apply_time | DATETIME | 提交时间 |
| to_regular_status | VARCHAR | 转普通状态：NULL / TO_DO / DONE / TIMEOUT |
| gmt_create | DATETIME | 创建时间 |

**申请状态枚举：**
- SAVING → QUICK_AUDITING → PRE_PRE_AUDITING → PRE_PRE_AUDITED → CERT_AUTHED → CERT_FILE_SYNCED
- 快审驳回：QUICK_AUDITING → QUICK_REJECTED
- 预审驳回：PRE_PRE_AUDITING → PRE_REJECTED

**常用查询：**
```sql
-- 查申请状态及转普通状态
SELECT id, right_id, status, apply_type, to_regular_status
FROM yc_right_apply WHERE right_id = ? ORDER BY apply_time DESC;

-- 查待转普通的申请
SELECT id, right_id, status, to_regular_status
FROM yc_right_apply WHERE to_regular_status = 'TO_DO';
```

---

### 3. yc_right_settle_order — 结算单

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_id | BIGINT | 关联 yc_right.id |
| seller_id | BIGINT | 商家 ID |
| settle_status | VARCHAR | 结算状态：TO_DO / PROCESSING / FINISH |
| total_amount | DECIMAL | 结算金额（分） |
| init_allowance_start_time | DATETIME | 补贴起始时间（NULL=未触发） |
| init_allowance_amount | DECIMAL | 补贴金额 |
| serv_finish_refund_status | VARCHAR | 退款状态 |
| gmt_create | DATETIME | 创建时间 |

**补贴校验核心逻辑：**
- `init_allowance_start_time IS NULL` → 补贴未触发
- `init_allowance_start_time IS NOT NULL` → 补贴已触发，`init_allowance_amount` 必有值
- `total_amount` 不是补贴金额，是结算单基础金额（测试环境=10，生产=50000）

**结算金额计算规则（效果对赌）：**

| 下架率 | 首发 | total_amount |
|--------|------|-------------|
| ≥70% | 是 | service_fee × 1.0 + 补贴 = 302（测试环境） |
| ≥70% | 否 | service_fee × 1.0 = 202 |
| 30%-70% | 是 | service_fee × 下架率 + 补贴 = 按比例 |
| 30%-70% | 否 | service_fee × 下架率 = 按比例 |
| <30% | 是 | 全额退款 → 33（仅退补贴部分） |
| <30% | 否 | 全额退款 → 133 |

**常用查询：**
```sql
-- 查结算单状态及补贴信息
SELECT id, settle_status, total_amount, init_allowance_start_time, init_allowance_amount
FROM yc_right_settle_order WHERE right_id = ?;

-- 查待结算的订单
SELECT id, right_id, seller_id FROM yc_right_settle_order WHERE settle_status = 'TO_DO';
```

---

### 4. yc_right_apply_op_record — 操作审计日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_apply_id | BIGINT | 关联 yc_right_apply.id |
| operate_type | VARCHAR | 操作类型（SUBMIT_QUICK_APPLY / QUICK_AUDIT_AGREE / SUBMIT_APPLY 等） |
| operate_time | DATETIME | 操作时间 |
| operator_name | VARCHAR | 操作人 |
| operator_phone | VARCHAR | 操作人手机（脱敏） |
| extra_info | TEXT | 扩展信息（JSON） |
| gmt_create | DATETIME | 创建时间 |

**常用查询：**
```sql
-- 查申请操作历史
SELECT operate_type, operator_name, operate_time, extra_info
FROM yc_right_apply_op_record WHERE right_apply_id = ? ORDER BY gmt_create;
```

---

### 5. yc_right_protect_record — 维权记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_id | BIGINT | 关联 yc_right.id |
| tort_id | BIGINT | 关联 tort_record.id |
| protect_status | VARCHAR | 维权状态 |
| takedown_status | VARCHAR | 下架状态 |
| gmt_create | DATETIME | 创建时间 |

---

### 6. tort_record — 侵权记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_id | BIGINT | 关联 yc_right.id |
| tort_url | VARCHAR | 侵权链接 |
| tort_type | VARCHAR | 侵权类型 |
| status | VARCHAR | 处理状态 |
| platform | VARCHAR | 平台来源 |

---

### 7. inspect_whitelist — 巡检白名单

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| category_id | BIGINT | 类目 ID |
| seller_id | BIGINT | 商家 ID（可选） |
| type | INT | 白名单类型 |

**9类白名单类目 ID：**
`16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001`

---

### 8. yc_seller_enter_info — 商家入驻

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| seller_id | BIGINT | 商家 ID |
| status | VARCHAR | 入驻状态：ENTERED / NOT_ENTERED |
| enter_time | DATETIME | 入驻时间 |
| gmt_create | DATETIME | 创建时间 |

---

### 9. yc_service_trade_record — 服务交易

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| right_id | BIGINT | 关联 yc_right.id |
| seller_id | BIGINT | 商家 ID |
| trade_type | VARCHAR | 交易类型 |
| amount | DECIMAL | 金额 |
| gmt_create | DATETIME | 创建时间 |

---

### 10. refund_apply_order — 退款申请单

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| settle_order_id | BIGINT | 关联 yc_right_settle_order.id |
| seller_id | BIGINT | 商家 ID |
| refund_amount | DECIMAL | 退款金额 |
| refund_status | VARCHAR | 退款状态 |
| gmt_create | DATETIME | 创建时间 |

---

## 关联关系

```
yc_right (专利权)
  ├── yc_right_apply (申请记录) 1:N
  │     └── yc_right_apply_op_record (操作日志) 1:N
  ├── yc_right_settle_order (结算单) 1:N
  │     └── refund_apply_order (退款单) 1:N
  ├── yc_right_protect_record (维权记录) 1:N
  │     └── tort_record (侵权记录) N:1
  └── yc_service_trade_record (服务交易) 1:N

yc_seller_enter_info (商家入驻) — 独立表
inspect_whitelist (巡检白名单) — 独立表
```

---

## 常用组合查询

```sql
-- 完整专利权信息（含申请+结算+入驻）
SELECT r.id, r.status AS right_status, r.apply_time, r.protect_expire_time, r.first_publish,
       a.status AS apply_status, a.apply_type, a.to_regular_status,
       s.settle_status, s.total_amount, s.init_allowance_start_time,
       e.status AS enter_status
FROM yc_right r
LEFT JOIN yc_right_apply a ON a.right_id = r.id
LEFT JOIN yc_right_settle_order s ON s.right_id = r.id
LEFT JOIN yc_seller_enter_info e ON e.seller_id = r.seller_id
WHERE r.seller_id = ?
ORDER BY r.apply_time DESC;

-- 下架率计算
SELECT COUNT(CASE WHEN t.takedown_status = 'TAKEDOWN' THEN 1 END) AS takedown_count,
       COUNT(*) AS total_count,
       ROUND(COUNT(CASE WHEN t.takedown_status = 'TAKEDOWN' THEN 1 END) / COUNT(*) * 100, 2) AS takedown_rate
FROM yc_right_protect_record p
JOIN tort_record t ON t.id = p.tort_id
WHERE p.right_id = ?;
```
