<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护用例生成/references/原创保护-DB表速查.md -->
<!-- synced-at: 2026-08-03T16:11:43.907987 -->
<!-- skill: 原创保护用例生成 -->

# 原创保护DB表速查

## 数据库连接信息

| 项 | 值 |
|----|-----|
| 库别名 | scenario |
| 实际DB名 | prod |
| 主机 | 33.9.212.198:3011 |
| db_id | 975919 |
| 权限 | 查询权限可用（owner=菜问授权） |

## DMS-alibaba CLI 使用

```bash
# 执行查询（必须 --db prod，不是scenario）
dms-alibaba sql exec --db prod --group <group> --sql "SELECT ..."

# 结果路径：~/dms-alibaba/db-groups/{group}/sql/quick_{db}/_results/{date}/
# JSON取 rows 字段，不是 data
```

## 12张核心表

### 1. yc_right - 专利权主表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键(rightId) |
| seller_id | bigint | 商家ID |
| status | varchar | RightStatusEnum: SAVING/APPLYING/REJECT/YC_PROTECT_VALID/YC_PROTECT_INVALID |
| apply_time | datetime | 申请时间 |
| protect_expired_time | datetime | 保护到期时间 |
| extra_info | text | 扩展JSON |

### 2. yc_right_apply - 申请记录

| 字段 | 说明 |
|------|------|
| id | 主键(applyId) |
| right_id | 关联yc_right |
| seller_id | 商家ID |
| status | RightApplyStatusEnum 21种状态 |
| apply_type | QUICK/PRE/REGULAR |
| apply_time | 申请时间 |
| outer_apply_id | 外部申请号(YC30683955232格式) |

**21种申请状态**：SAVING / QUICK_AUDITING / QUICK_AUDITED / PRE_PRE_AUDITING / PRE_PRE_AUDIT_SUPPLEMENT / PRE_PRE_AUDITED / PRE_PRE_AUDIT_REJECT / PRE_AUDIT_REJECT / CERT_AUTHED / CERT_SUPPLEMENT / CERT_FILE_SYNCED / APPLY_TERMINATED / 等

### 3. yc_right_settle_order - 结算单

| 字段 | 说明 |
|------|------|
| id | 主键 |
| right_apply_id | 关联申请 |
| settle_status | SettleStatusEnum: TO_DO/PROCESSING/FINISH |
| total_amount | 金额（元，测试环境0.06/0.04） |
| init_allowance_start_time | 补贴起始时间（关键字段，须早于到期） |
| serv_finish_refund_status | 服务完结退款状态 |

### 4. yc_right_apply_op_record - 操作审计

| 字段 | 说明 |
|------|------|
| right_apply_id | 关联申请 |
| operate_type | ApplyOperateTypeEnum 操作类型 |
| operator | 操作人 |
| gmt_create | 操作时间 |

### 5. yc_right_protect_record - 维权记录

| 字段 | 说明 |
|------|------|
| right_id | 关联Right |
| protect_way | RightProtectWayEnum: TAKE_DOWN |
| status | RightProtectStatusEnum: RUNNING/SUCCESS |
| start_time / finish_time | 时间 |

### 6. tort_record - 侵权记录

| 字段 | 说明 |
|------|------|
| right_id | 关联Right |
| status | RightTortStatusEnum: TO_PROTECT/PROTECTING |
| right_tort_record_id | 关联到具体维权记录 |

### 7. inspect_whitelist - 巡检白名单

| 字段 | 说明 |
|------|------|
| seller_id | 商家ID |
| shop_name | 店铺名 |
| shop_link | 店铺URL（格式: https://shop{shopId}.taobao.com） |
| platform | 平台 |

### 8. seller_enter_info - 商家入驻

| 字段 | 说明 |
|------|------|
| seller_id | 商家ID |
| status | SellerEnterStatusEnum: ENTERED |

### 9. seller_contract_info - 商家合同

签约状态、合同URL、签署时间。

### 10. seller_wechat_group - 商家企微群

群加入方式信息。

### 11. service_trade_record - 服务交易

trade_status: RUNNING；trade_type: BUY/REFUND。

### 12. refund_apply_order - 退款申请单

退款金额、状态。

## 常用查询模板

```sql
-- 查申请状态历史
SELECT a.id, a.status, a.gmt_modified, op.operate_type, op.operator
FROM yc_right_apply a
LEFT JOIN yc_right_apply_op_record op ON op.right_apply_id = a.id
WHERE a.id = ?
ORDER BY op.gmt_create DESC;

-- 查结算时序（重点：补贴时间 vs 到期时间）
SELECT s.id, s.total_amount, s.settle_status, s.init_allowance_start_time,
       s.serv_finish_refund_status, r.protect_expired_time
FROM yc_right_settle_order s
JOIN yc_right_apply a ON s.right_apply_id = a.id
JOIN yc_right r ON a.right_id = r.id
WHERE a.id = ?;

-- 查商家所有申请概况
SELECT status, COUNT(*) FROM yc_right_apply
WHERE seller_id = ? GROUP BY status;

-- 查侵权与维权关联
SELECT t.id as tort_id, t.status as tort_status,
       p.protect_way, p.status as protect_status
FROM tort_record t
LEFT JOIN yc_right_protect_record p ON p.tort_record_id = t.id
WHERE t.right_id = ?;

-- 查到期前20天禁发期内的Right
SELECT id, seller_id, protect_expired_time
FROM yc_right
WHERE status = 'YC_PROTECT_VALID'
  AND protect_expired_time BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 20 DAY);

-- 查未发补贴的结算单（排查）
SELECT s.id, s.right_apply_id, s.init_allowance_start_time, r.protect_expired_time
FROM yc_right_settle_order s
JOIN yc_right_apply a ON s.right_apply_id = a.id
JOIN yc_right r ON a.right_id = r.id
WHERE s.total_amount = 0
  AND (s.init_allowance_start_time IS NULL
       OR s.init_allowance_start_time > r.protect_expired_time);
```

## 排查注意

- `--db` 用实际DB名 `prod`，不是别名scenario
- node_type类无索引字段查询要加 id BETWEEN 防超时（参考F88经验）
- 失败状态: 'FAIL'（非'FAILED'）
- 错误信息从extra_info JSON中提取：JSON_EXTRACT(extra_info, '$.errorMsg')
