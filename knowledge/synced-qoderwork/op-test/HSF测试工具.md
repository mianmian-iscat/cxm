<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护执行助手/references/HSF测试工具.md -->
<!-- synced-at: 2026-07-14T01:00:04.570141 -->
<!-- skill: 原创保护执行助手 -->

# HSF 测试工具服务

后端通过HSF Tool Service暴露测试数据构造能力，仅测试环境可用。

## RightApplyToolHsfService

| 方法 | 用途 |
|------|------|
| updateExtraInfo | 更新申请的扩展信息JSON |
| updateStatus | 直接改申请状态（跳过状态机） |
| updateApplyTime | 改申请时间 |
| updateProtectExpiredTime | 改保护到期时间（用于T+4/到期前20天测试） |

## RightSettleToolHsfService

| 方法 | 用途 |
|------|------|
| initSettleOrder | 初始化结算单 |
| updateSettleStatus | 更新结算状态 |
| querySettleOrders | 查询结算单 |
| getSettleOrderByApplyId | 按申请ID查结算单 |
| updateInitAllowanceStartTimeWithApplyId | 改补贴起始时间（关键：必须早于到期） |

## RightToolHsfService

| 方法 | 用途 |
|------|------|
| updateExtraInfo | 更新Right扩展信息 |
| initProtectExpiredTime | 初始化保护到期时间 |

## ServiceTradeToolService

| 方法 | 用途 |
|------|------|
| triggerRefund | 触发退款 |

## SellerEnterToolService

| 方法 | 用途 |
|------|------|
| enterSeller | 模拟商家入驻 |

## TortToolService

| 方法 | 用途 |
|------|------|
| batchUpdateStatus | 批量更新侵权状态 |

## 模拟审核结果（模板4，推荐）

通过 `RightApplyToolHsfService.updateStatus` **直接改申请状态**，绕过第三方审核人员，实现全流程零人工。

### 调用方式（mw CLI，已验证可用）

```bash
# 模拟快审通过：QUICK_AUDITING → QUICK_AUDITED
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[<applyId>, "QUICK_AUDITED"]' \
  --app taobao-yc-serverless --unit pre

# 模拟快审驳回：QUICK_AUDITING → QUICK_REJECT
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[<applyId>, "QUICK_REJECT"]' \
  --app taobao-yc-serverless --unit pre

# 模拟初审通过：PRE_AUDITING → PRE_AUDITED
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[<applyId>, "PRE_AUDITED"]' \
  --app taobao-yc-serverless --unit pre

# 模拟初审驳回：PRE_AUDITING → PRE_AUDIT_REJECT
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[<applyId>, "PRE_AUDIT_REJECT"]' \
  --app taobao-yc-serverless --unit pre
```

**验证记录**（2026-07-13）：applyId=200000874，QUICK_AUDITING → QUICK_AUDITED，返回 `{"success": true, "data": true, "fail": false}`，DB 确认 status 已更新。

### 常用状态值

| 目标 | status 值 |
|------|-----------|
| 快审通过 | `QUICK_AUDITED` |
| 快审驳回 | `QUICK_AUDIT_REJECT` |
| 初审通过 | `PRE_AUDITED` |
| 初审驳回 | `PRE_AUDIT_REJECT` |

## TopRightHsfService (TOP开放平台-给YC机构) — 已弃用

| 方法 | 用途 |
|------|------|
| syncAuditOperation | 同步审核操作（仅写 op_record，不推进 DB 状态） |

### ⚠ 弃用说明
- `syncAuditOperation` 调用成功仅写入 `yc_right_apply_op_record`，**不推进 DB 状态**
- DB 状态仍为 QUICK_AUDITING，gmt_modified 不更新
- **已被 RightApplyToolHsfService.updateStatus 替代**，后者可直接改状态，无需第三方审核人员操作

## 关键时序（务必遵守）

1. **结算补贴**：先 `updateInitAllowanceStartTimeWithApplyId` 设补贴时间，再 `updateProtectExpiredTime` 设到期时间。反序会导致补贴不发。

2. **首发标签测试**：用 `updateApplyTime` 调整申请时间，模拟 T+3 / T+4 边界。

3. **到期前20天测试**：用 `updateProtectExpiredTime` 把到期时间改到 NOW()+20天内。

## 调用示例（结算场景，mw CLI）

```bash
# 1. 改申请时间到过去
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateApplyTime~java.lang.Long;java.util.Date" \
  --args '[<applyId>, "2026-01-01 00:00:00"]' \
  --app taobao-yc-serverless --unit pre

# 2. 设补贴起始时间（必须早于到期）
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightSettleToolHsfService:1.0.0" \
  --method "updateInitAllowanceStartTimeWithApplyId~java.lang.Long;java.util.Date" \
  --args '[<applyId>, "2026-06-01 00:00:00"]' \
  --app taobao-yc-serverless --unit pre

# 3. 设保护到期时间（必须晚于补贴）
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateProtectExpiredTime~java.lang.Long;java.util.Date" \
  --args '[<applyId>, "2026-09-01 00:00:00"]' \
  --app taobao-yc-serverless --unit pre

# 4. 等定时任务 ServFinishIncomeJob / InitAllowanceRefundJob 触发
# 或手动触发 ScheduleX 任务
```

完整方法签名见 `yc-data-factory` Skill（`~/.qoderwork/skills/yc-data-factory/SKILL.md`）。

## QA 实战踩坑

### 浏览器调用模式
导航到 hsf.alibaba-inc.com 测试页 → 用 JS `ace.edit(el).setValue()` 设参数 → 点"测试"按钮。

### updateProtectExpiredTime 状态
- `initProtectExpiredTime` 曾返回 success=true 但实际未更新（历史问题）
- `updateProtectExpiredTime(applyId, Date)` 在 2026-07 验证可正常更新 yc_right.protect_expire_time

### TortToolService 限制
- 仅 `initStatus` → TO_PROTECT，无改终态(PROTECT_SUCCESS/FAIL)方法
- 改 tort 终态只能 DMS 或等维权机构回传/定时任务

### RightSettleToolHsfService.updateStatus 捷径
- `updateStatus(id, "FINISH")` 可直接改结算单状态，跳过所有前置校验（下架率/收入/退款）
- 用于绕过正常结算流程造数

## 原创保护结算 Job 链（pre 环境 SchedulerX）

| 时间 | Task ID | 名称 |
|------|---------|------|
| 01:00 | 715618497 | 首发补贴退款 |
| 02:00 | 399576024 | 专利保护定时失效（按下架率分流） |
| 04:00 | 719211870 | 服务完结退款 |
| 06:00 | 721504806 | 服务完结确收 |
| — | 935953096 | 转普通申请超时扫描 |

SchedulerX 控制台手动"运行一次"触发。

## SchedulerX 访问限制
schedulerx.alibaba-inc.com 从 Chrome 扩展/QoderWork 浏览器侧无法访问（连接超时），触发定时任务需用户在浏览器手动点"运行一次"或通过内网 curl。
