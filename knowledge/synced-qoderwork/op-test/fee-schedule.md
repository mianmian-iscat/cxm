<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护结算分析/references/fee-schedule.md -->
<!-- synced-at: 2026-07-14T01:00:04.601510 -->
<!-- skill: 原创保护结算分析 -->

# 费用科目表

## 完整科目清单

> 数据来源：`RightSettleConstant.java` 源码（2026-07-14 确认）

| 科目名称 | 方向 | 测试金额 | 生产金额 | 触发条件 | 收款方 | 付款方 | DB字段 | 备注 |
|----------|------|----------|----------|----------|--------|--------|--------|------|
| 服务费(TOTAL) | 收入 | 10 分 | 500 元 | 申请提交 | 平台 | 商家 | total_amount | 结算总额 |
| 基础服务费(BASE_FEE) | 平台留存 | 2 分 | 165 元 | 申请提交 | 平台 | — | — | 平台实际留存部分 |
| 首发补贴(INIT_ALLOWANCE) | 支出 | 6 分 | **302 元** | 首发 + 9类 + SYNC_CERT_FILE | 商家 | 平台 | init_allowance_amount | first_publish=1 |
| 非首发补贴(NOT_INIT_ALLOWANCE) | 支出 | 4 分 | **202 元** | 非首发 + 9类 + SYNC_CERT_FILE | 商家 | 平台 | init_allowance_amount | first_publish=0 |
| 完结退款 | 支出 | 动态(见公式) | 动态(见公式) | 到期/驳回/终止 + 下架率<70% | 商家 | 平台 | serv_finish_refund_amount | 退剩余金额 |
| 完结确收 | 支出 | — | Switch配置值 | 到期 + 下架率≥70% | 供应商 | 平台 | serv_finish_income_amount | 从SERV_FINISH_INCOME_FEE_CODE读取 |

## 金额计算规则（源码确认）

### 代码常量

```java
// RightSettleConstant.java
public static final Long TOTAL_AMOUNT = 50000L;           // 500元
public static final Long INIT_ALLOWANCE_AMOUNT = 30200L;  // 302元（首发补贴）
public static final Long NOT_INIT_ALLOWANCE_AMOUNT = 20200L; // 202元（非首发补贴）
public static final Long BASE_FEE = 16500L;               // 165元（基础服务费）

public static final Long TEST_TOTAL_AMOUNT = 10L;
public static final Long TEST_INIT_ALLOWANCE_AMOUNT = 6L;
public static final Long TEST_NOT_INIT_ALLOWANCE_AMOUNT = 4L;
public static final Long TEST_BASE_FEE = 2L;
```

### 退款金额公式（源码确认）

**完结退款**（`applyTerminated` + `doServFinishRefund`）：
```
退款金额 = total_amount - init_allowance_amount
```

**驳回/终止时**（`applyTerminated` 方法）：
- 未发过补贴 → 直接 CANCEL 结算单，不退款
- 已发过补贴 → 设 `serv_finish_refund_status = TO_DO`，退款金额 = `total_amount - init_allowance_amount`

**测试环境实测**（total_amount=10 分）：
- 首发：补贴 6 分 → 退款 10-6 = 4 分
- 非首发：补贴 4 分 → 退款 10-4 = 6 分

**生产环境预期**（total_amount=500 元）：
- 首发：补贴 302 元 → 退款 500-302 = **198 元**
- 非首发：补贴 202 元 → 退款 500-202 = **298 元**

### 补贴金额规则（源码确认）

| 条件 | 补贴金额（生产） | 补贴金额（测试） |
|------|------------------|------------------|
| 9类 + 首发(first_publish=1) | **302 元** | 6 分 |
| 9类 + 非首发(first_publish=0) | **202 元** | 4 分 |
| 非9类 | 0（不发放） | 0 |

### 确收金额

从 `RightSettleSwitch.SERV_FINISH_INCOME_FEE_CODE` 读取（Switch 配置值），非硬编码。

## 9类白名单类目

| 类目ID | 类目名称 |
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

**判定时间点**：SYNC_CERT_FILE（确认商品一致性）时的 ODPS 主营类目快照。
**ODPS 表**：`cco_busi.dplan_dim_tb_slr_mx_d_1`（按 ds 分区）

## 资金平衡验证

结算完结后，资金应满足以下等式：

```
商家缴费 = 平台留存 + 商家退款 + 供应商确收 + 补贴发放
```

### 退款路径示例（首发，下架率<70%）

```
500(缴费) = 平台留存 + 198(退款) + 0(确收) + 302(首发补贴)
平台留存 = 500 - 198 - 302 = 0 元
```

### 退款路径示例（非首发，下架率<70%）

```
500(缴费) = 平台留存 + 298(退款) + 0(确收) + 202(非首发补贴)
平台留存 = 500 - 298 - 202 = 0 元
```

### 确收路径示例（下架率≥70%）

```
500(缴费) = 平台留存 + 0(退款) + Switch配置值(确收) + 补贴
平台留存 = 500 - 确收金额 - 补贴
```

> ⚠️ 以上为推测，实际资金平衡公式需与 PM/财务确认。

## DB 验证 SQL

```sql
-- 查结算单全部金额字段
SELECT id, right_apply_id, settle_status,
       total_amount,
       init_allowance_start_time, init_allowance_amount,
       serv_finish_refund_status, serv_finish_refund_amount,
       serv_finish_income_status, serv_finish_income_amount
FROM yc_right_settle_order
WHERE right_apply_id = {applyId} AND env = 'staging'
AND settle_status != 'CANCEL'
ORDER BY id DESC LIMIT 1;
```
