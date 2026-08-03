# 原创保护 HSF 测试工具

> 用于在预发环境构造特定状态的测试数据  
> 调用方式：通过 HSF Tool MCP 或直接调用 HSF 服务

---

## 工具服务清单

### RightApplyToolHsfService — 申请记录操作

| 方法 | 参数 | 说明 | 使用场景 |
|------|------|------|---------|
| `updateApplyTime` | (applyId, newTime) | 修改申请时间 | 模拟申请提交在不同时间点 |
| `updateProtectExpiredTime` | (rightId, newTime) | 修改保护到期时间 | 测试禁发期（到期前20天） |
| `updateStatus` | (applyId, newStatus) | 修改申请状态 | 构造指定状态的申请记录 |
| `updateToRegularStatus` | (applyId, status) | 修改转普通状态 | 测试 TO_DO/DONE/TIMEOUT 流转 |

### RightSettleToolHsfService — 结算单操作

| 方法 | 参数 | 说明 | 使用场景 |
|------|------|------|---------|
| `initSettleOrder` | (rightId, serviceFee) | 初始化结算单 | 创建待结算状态的订单 |
| `updateSettleStatus` | (orderId, status) | 修改结算状态 | 测试 TO_DO→PROCESSING→FINISH |
| `updateInitAllowanceStartTimeWithApplyId` | (applyId, startTime) | 修改补贴起始时间 | 触发/取消补贴 |
| `updateTotalAmount` | (orderId, amount) | 修改结算金额 | 验证金额计算逻辑 |

### ServiceTradeToolService — 服务交易操作

| 方法 | 参数 | 说明 | 使用场景 |
|------|------|------|---------|
| `triggerRefund` | (orderId, amount) | 触发退款 | 测试退款流程 |
| `createTradeRecord` | (rightId, type, amount) | 创建交易记录 | 构造服务交易数据 |

### SellerEnterToolService — 商家入驻操作

| 方法 | 参数 | 说明 | 使用场景 |
|------|------|------|---------|
| `enterSeller` | (sellerId) | 商家入驻 | 构造已入驻状态 |
| `exitSeller` | (sellerId) | 商家退出 | 构造未入驻状态 |
| `updateEnterStatus` | (sellerId, status) | 修改入驻状态 | 测试各种入驻状态 |

### TortToolService — 侵权记录操作

| 方法 | 参数 | 说明 | 使用场景 |
|------|------|------|---------|
| `batchUpdateStatus` | (ids, status) | 批量改侵权状态 | 测试下架率计算 |
| `createTortRecord` | (rightId, url, type) | 创建侵权记录 | 构造维权数据 |

---

## 关键时序规则

### 补贴触发时序

**必须先设补贴时间，再设到期时间，否则补贴不发。**

正确顺序：
```
1. updateInitAllowanceStartTimeWithApplyId(applyId, startTime)  // 先设补贴时间
2. updateProtectExpiredTime(rightId, expiredTime)                // 再设到期时间
3. 等待 ScheduleX 任务执行结算                                    // 触发结算
```

错误顺序：
```
1. updateProtectExpiredTime(rightId, expiredTime)                // ❌ 先设到期时间
2. updateInitAllowanceStartTimeWithApplyId(applyId, startTime)  // 补贴不会触发！
```

### 转普通触发时序

```
1. 构造预审/证书驳回状态的申请
2. updateToRegularStatus(applyId, "TO_DO")  // 标记待转普通
3. 等待系统自动执行转普通                      // 或手动触发
4. 验证 to_regular_status = "DONE"
```

> **注意**：快审驳回不触发转普通，只有预审/证书驳回才触发。

---

## 典型造数场景

### 场景 A：下架率 ≥ 70% + 首发

```
1. createTortRecord × 100（创建100条侵权记录）
2. batchUpdateStatus(1-70, "TAKEDOWN")（70条下架）
3. updateInitAllowanceStartTimeWithApplyId(applyId, now)（触发补贴）
4. updateProtectExpiredTime(rightId, now + 365天)
5. 等待 ScheduleX → 验证 total_amount = 302
```

### 场景 B：到期前20天禁发期

```
1. updateProtectExpiredTime(rightId, now + 15天)（15天后到期）
2. 验证发布按钮灰态（publishItemGray: true）
3. 验证维权按钮禁用
4. 验证上报线索入口关闭
```

### 场景 C：快审入驻校验

```
1. exitSeller(sellerId)（确保未入驻）
2. 小二端提交快审 → 预期被拦截
3. enterSeller(sellerId)（入驻）
4. 小二端提交快审 → 预期成功
```

---

## HSF 调用示例

```json
{
  "service": "com.taobao.industry.yc.tool.RightSettleToolHsfService",
  "method": "updateInitAllowanceStartTimeWithApplyId",
  "version": "1.0.0",
  "group": "HSF",
  "args": [
    {"type": "java.lang.Long", "value": "12345"},
    {"type": "java.util.Date", "value": "2026-06-20 00:00:00"}
  ]
}
```

---

## 环境信息

| 环境 | HSF 注册中心 | 版本 |
|------|-------------|------|
| 预发 | configserver://pre | 1.0.0.pre |
| 日常 | configserver://daily | 1.0.0.daily |
