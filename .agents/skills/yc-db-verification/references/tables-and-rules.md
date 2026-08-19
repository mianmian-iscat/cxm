# 核心表结构与业务规则速查

## scenario 数据库 (database_id: 975919)

---

## 表: yc_right_apply (权益申请记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 申请ID（主键） |
| outer_apply_id | VARCHAR | 外部申请编号（如 YC31570248680） |
| seller_id | BIGINT | 商家ID |
| status | VARCHAR | 申请状态（AUDITING / QUICK_AUDITING / QUICK_AUDIT_PASS / CERT_FILE_SYNCED / YC_PROTECTING 等） |
| apply_type | VARCHAR | 申请类型（QUICK / PRE / REGULAR） |
| category | VARCHAR | 申请类目（如"服装"） |
| to_regular_status | VARCHAR | 转普通状态（NULL=未转 / DONE=已转普通） |
| right_id | BIGINT | 关联的权益记录ID |
| gmt_create | DATETIME | 创建时间 |
| gmt_modified | DATETIME | 最后修改时间 |

### 申请状态机

```
AUDITING → QUICK_AUDITING → QUICK_AUDIT_PASS → CERT_FILE_SYNCED → YC_PROTECTING
```

转普通分支：
```
CERT_FILE_SYNCED → (触发转普通) → to_regular_status=DONE
```

---

## 表: yc_right (权益记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 权益记录ID（主键） |
| first_publish | INT | 是否首发（NULL=未设置 / 1=是 / 0=否） |
| category | VARCHAR | 权益类目（如"服装"） |
| protect_expire_time | DATETIME | 保护期到期时间 |
| status | VARCHAR | 权益状态（APPLYING / YC_PROTECTING 等） |

---

## 表: yc_right_settle_order (结算单)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 结算单ID（主键） |
| right_apply_id | BIGINT | 关联的申请ID |
| settle_status | VARCHAR | 结算状态（PROCESSING / CANCEL / COMPLETED） |
| total_amount | DECIMAL | 基础结算金额（测试环境=10，生产=50000）⚠️ **不是补贴金额** |
| init_allowance_start_time | DATETIME | 补贴起始时间（NULL=未触发补贴，NOT NULL=已触发） |
| init_allowance_amount | DECIMAL | 补贴金额（补贴触发后必有值） |

### 补贴判定规则

| 场景 | total_amount | init_allowance_start_time | init_allowance_amount | 结论 |
|------|-------------|--------------------------|----------------------|------|
| 非9类商家 | 有值（如10） | NULL | NULL | 补贴未触发 |
| 9类商家(Job未执行) | 有值（如10） | NULL | NULL | 补贴待触发 |
| 9类商家(Job已执行) | 有值（如10） | 有值 | 有值（如6） | 补贴已触发 |
| 转普通(旧单) | 有值 | - | - | settle_status=CANCEL |
| 转普通(新单) | 有值 | NULL/有值 | NULL/有值 | settle_status=PROCESSING |

---

## 表: yc_right_apply_op_record (操作流水)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 操作记录ID |
| right_apply_id | BIGINT | 关联的申请ID |
| op_type | VARCHAR | 操作类型 |
| op_detail | TEXT | 操作详情 |
| gmt_create | DATETIME | 操作时间 |

### 常见操作类型与时间线还原

通过 op_record 可还原完整业务流程：
- 申请创建
- 快审提交/通过
- 商品一致性确认（SYNC_CERT_FILE）
- 转普通触发
- 结算单创建/取消/重建

---

## 业务规则速查

### 9类白名单

9类白名单类目ID集合：
```
{16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001}
```

| 类目ID | 对应类目 |
|--------|----------|
| 16 | 女装/女士精品 |
| 30 | 男装 |
| 50006843 | 童装/亲子装 |
| 50011740 | 童鞋/亲子鞋 |
| 1625 | 女士内衣/男士内衣/家居服 |
| 50010404 | 服饰配件/皮带/帽子/围巾 |
| 50006842 | 运动鞋/休闲鞋 |
| 28 | 运动服/休闲服 |
| 50468001 | 箱包 |

### 补贴发放判定

- **校验时间点**：SYNC_CERT_FILE（确认商品一致性）时的 ODPS 主营类目快照
- **ODPS 主营类目表**：`cco_busi.dplan_dim_tb_slr_mx_d_1`（按 ds 分区）
- **判定逻辑**：
  - SYNC_CERT_FILE 时商家主营类目 ∈ 9 类白名单 → 发放补贴（Job 执行后 init_allowance_start_time 赋值）
  - SYNC_CERT_FILE 时商家主营类目 ∉ 9 类白名单 → 不发放补贴（init_allowance_start_time 保持 NULL）
- **关键**：total_amount 是基础结算金额，不代表补贴。补贴看 init_allowance_start_time。

### 首发编辑权限

| 条件 | 运营端可编辑？ | 商家端可编辑？ |
|------|---------------|---------------|
| 9类 + 未转普通 | ✅ 可编辑 | ✅ 可编辑 |
| 9类 + 已转普通 | ❌ 不可编辑 | ❌ 不可编辑 |
| 非9类 | ❌ 不可编辑（disabled） | ❌ 不可编辑（disabled） |

**规则**：首发编辑权限 = 9 类商家 **且** 未转普通（`to_regular_status ≠ DONE`），两个条件同时满足。

### 转普通流程

- `to_regular_status IS NULL` → 未转普通
- `to_regular_status = DONE` → 已转普通
- 转普通后旧结算单状态变为 CANCEL，新结算单创建（PROCESSING）
- 转普通后即使 9 类商家也不可编辑首发
