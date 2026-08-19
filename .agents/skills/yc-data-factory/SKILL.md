---
name: yc-data-factory
description: 原创保护平台测试数据工厂 — 封装 6 个 HSF Tool 服务 + MetaQ 消息模拟 + ScheduleX 手动触发，输入 applyId/sellerId + 操作类型 → 自动选服务 → 执行 → DB 验证。触发词：造数据、改状态、改时间、触发退款、改补贴时间、改到期时间、数据工厂、yc-data-factory、模拟审核结果（回归专用）、模拟审核（回归专用）、绕过审核（回归专用）。
version: 0.1.0
---

> 📋 测试商家 seller_id 统一维护入口：[test-accounts.md](../yc-protection-qa-workbench/test-accounts.md)（插件根目录）

# 原创保护测试数据工厂（yc-data-factory）

封装原创保护平台 6 个 HSF Tool 服务，提供统一的数据构造和状态操作能力。所有 HSF 调用涉及数据修改，**必须经用户确认后执行**（USER.md 红线）。

## 安全红线

⚠️ **HSF Tool 调用会直接修改数据库记录**，属于高风险操作。执行前必须：
1. 向用户明确展示：将调用的服务名、方法名、参数值、目标申请编号
2. **强制前置校验（2026-08-04 新增，不可跳过）**：任何写操作 HSF 调用前，必须先确认目标记录的 `env` 字段为 `staging`。
   - **推荐方式（脚本校验）**：调用统一前置校验脚本，零手工 SELECT：
     ```bash
     python3 ~/.qoderwork/skills/yc-data-factory/scripts/env_check.py --apply-id {applyId}
     ```
     - 退出码 `0`：env='staging'，可继续。
     - 退出码 `2`：生产/未知/missing env，**立即中止**并提示用户。
     - 退出码 `1`：工具/参数错误，按脚本提示修复。
   - **等价 SQL（脚本不可用时手工执行）**：
     ```sql
     SELECT id, env FROM yc_right_apply WHERE id = {applyId};
     ```
   - 完整操作清单见 [references/write-safety-checklist.md](references/write-safety-checklist.md)。
   **⚠️ 每次调用都要重新执行此校验**：造数时执行、测试执行时执行、每一个环节都再次加载执行——禁止复用上一次/上一环节/上一用例的校验结果，禁止"这批数据刚才查过就跳过"。一次会话内即使同一个 applyId 被操作 N 次，也要在每次写操作前重新 SELECT 一次（env 可能被他人/他流程改变，唯一可信的是当次查询结果）。
   - 只有 `env = 'staging'` 才允许继续执行写操作
   - `env = 'prod'` 或 `env = 'production'` → 🚨 **报警提示并立即中止**，明确告知用户"目标数据为生产数据，禁止写操作"，绝不执行
   - env 为空、为其他任何值、或查不到记录 → 同样报警中止（env 实测取值：production 1067 条 / staging 255 条 / 空 1 条，2026-08-04；prod 与 production 一律按生产对待）
   - HSF Tool 服务按 ID 直接更新、不校验 env，预发单元调用传错生产 ID 同样会改生产数据，此校验是唯一防线
3. 等待用户确认后才执行
4. 执行后立即通过 DB 验证确认结果

🚫 **生产数据只读铁律**：生产环境（env='production'）数据只允许 SELECT 查询，严禁通过 HSF、DMS 工单或任何方式写入/更新/删除。造数和状态操作仅限 env='staging' 数据。

🚫 **SQL 过滤铁律**：所有 DB SQL 查询必须加 `env='staging'` 过滤（yc_right_apply / yc_right / yc_right_settle_order 均有 env 列）；无 env 列的表（yc_right_apply_op_record / yc_tort_record / yc_right_product）必须通过已核实的 staging applyId/rightId 间接过滤，禁止无过滤裸查。

## 前置条件

1. **a1 CLI 可用**：`a1 --version` 返回版本号
2. **HSF Tool 服务可用**：通过 a1 repo 确认 taobao-yc-serverless 的 HSF Tool 服务地址
3. **seller_id 已确认**：默认测试账号（见 test-accounts.md，当前默认: isv项目测试专用 2213249110271）
4. **DB 验证能力**：DMS MCP 可用（scenario 库 db_id=975919）

## 6 个 HSF Tool 服务目录

### 1. RightApplyToolHsfService — 申请记录操作

| 方法 | 用途 | 参数 | 风险等级 |
|------|------|------|---------|
| `updateExtraInfo` | 修改申请扩展信息 | applyId, key, value | 中 |
| `updateStatus` | 修改申请状态 | applyId, targetStatus | **高** — 非法状态跳转可能破坏状态机 |
| `updateProtectExpiredTime` | 修改保护到期时间 | applyId, newExpireTime(yyyy-MM-dd) | 高 — 影响 20 天禁发期计算 |
| `updateApplyTime` | 修改申请时间 | applyId, newApplyTime(yyyy-MM-dd HH:mm:ss) | 高 — 影响保护到期日计算（取早规则） |

**典型场景**：
- 构造"即将到期"测试数据：`updateProtectExpiredTime(applyId, today+20days)`
- 构造"已到期"测试数据：`updateProtectExpiredTime(applyId, today-1day)`
- 测试不同申请时间的到期日计算：`updateApplyTime(applyId, specificTime)`

### 2. RightToolHsfService — 专利权主表操作

| 方法 | 用途 | 参数 | 风险等级 |
|------|------|------|---------|
| `updateExtraInfo` | 修改权益扩展信息 | rightId, key, value | 中 |
| `initProtectExpiredTime` | 初始化保护到期时间 | rightId, expireTime | 高 |

**典型场景**：
- 初始化保护期：`initProtectExpiredTime(rightId, targetDate)`

### 3. RightSettleToolHsfService — 结算单操作

| 方法 | 用途 | 参数 | 风险等级 |
|------|------|------|---------|
| `initSettleOrder` | 初始化结算单 | applyId | 中 |
| `updateSettleStatus` | 修改结算状态 | settleOrderId, targetStatus | **高** — 可能破坏结算流程 |
| `querySettleOrders` | 查询结算单列表 | sellerId | 低（只读） |
| `getSettleOrderByApplyId` | 按申请ID查结算单 | applyId | 低（只读） |
| `updateInitAllowanceStartTimeWithApplyId` | 修改补贴起始时间 | applyId, startTime(yyyy-MM-dd HH:mm:ss) | 高 — 直接影响补贴发放判定 |

**典型场景**：
- 触发补贴发放：`updateInitAllowanceStartTimeWithApplyId(applyId, now)`
- 查询结算单状态：`getSettleOrderByApplyId(applyId)` → DB 验证
- 构造"完结待退款"：`updateSettleStatus(settleOrderId, "FINISH_REFUNDING")`

### 4. ServiceTradeToolService — 服务交易操作

| 方法 | 用途 | 参数 | 风险等级 |
|------|------|------|---------|
| `triggerRefund` | 触发退款 | orderId/sellerId | **高** — 实际触发退款流程 |

**典型场景**：
- 测试退款流程：先确认结算单状态为 PROCESSING，再 `triggerRefund`
- ⚠️ 退款金额必须等于剩余全量（不可部分退），否则校验失败

### 5. SellerEnterToolService — 商家入驻操作

| 方法 | 用途 | 参数 | 风险等级 |
|------|------|------|---------|
| `enterSeller` | 商家入驻 | sellerId | 中 — 幂等操作 |

**典型场景**：
- 重新触发入驻流程（入驻后已有记录则幂等）
- 配合千牛标打标 Skill 使用：先打标 TTYCBH → 再 enterSeller

### 6. TortToolService — 侵权记录操作

| 方法 | 参数类型 | 用途 | 风险等级 |
|------|---------|------|---------|
| `initStatus` | `List<Long>` | 批量重置侵权记录状态 | 中 |
| `autoProtectForManual` | `List<Long>` | 手动触发自动保护（生成侵权记录） | 中 |
| `syncStatusFromProtectRecord` | `List<Long>` | 从保护记录同步侵权状态 | 中 |
| `updateGoodsUrl` | `Long;String` | 修改商品URL | 低 |
| `fillSellerIdForProtectRecord` | `List<Long>` | 填充保护记录的 sellerId | 低 |
| `fillSellerIdForTortRecord` | `List<Long>` | 填充侵权记录的 sellerId | 低 |
| `deleteByIds` | `List<Long>;String` | 按ID批量删除 | **高** |

⚠️ **`batchUpdateStatus` 方法不存在**。TortToolService 没有直接设置侵权记录为 PROTECT_SUCCESS 的方法。如需构造特定下架率数据，可通过 DMS 变更工单修改 `yc_tort_record` 表（需申请 DML 权限）。

**典型场景**：
- 构造侵权记录：`autoProtectForManual([[rightId]])` → 生成侵权记录
- 重置侵权状态：`initStatus([[id1, id2]])` → 状态回到初始
- 同步保护记录状态：`syncStatusFromProtectRecord([[rightId]])`

**HSF List\<Long\> 参数格式**：`List<Long>` 类型的参数必须用双括号 `[[id1, id2]]`，而非单括号 `[id1, id2]`。单括号会导致参数解析错误。

## 调用方式

### 方式 A：通过 mw CLI 调用 HSF Tool（已验证可用）

> ✅ `mw hsf service invoke` 已在 2026-07-13 验证通过，是当前 HSF Tool 调用的**主要方式**。

**前置条件**：
1. `mw` CLI 已安装（`which mw` 返回路径）
2. 已登录（`mw login` 返回工号）
3. 需要 `SERVICE_TEST_INVOKE` 权限

**6 个 Tool 服务的精确接口名**：

| 服务 | 接口全名 |
|------|---------|
| RightApplyToolHsfService | `com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0` |
| RightSettleToolHsfService | `com.taobao.industry.yc.serverless.service.hsf.tool.RightSettleToolHsfService:1.0.0` |
| RightToolHsfService | `com.taobao.industry.yc.serverless.service.hsf.tool.RightToolHsfService:1.0.0` |
| SellerEnterToolService | `com.taobao.industry.yc.serverless.service.hsf.tool.SellerEnterToolService:1.0.0` |
| ServiceTradeToolService | `com.taobao.industry.yc.serverless.service.hsf.tool.ServiceTradeToolService:1.0.0` |
| TortToolService | `com.taobao.industry.yc.serverless.service.hsf.tool.TortToolService:1.0.0` |

**命令模板**：

```bash
mw hsf service invoke "<接口全名>" \
  --method "<方法名>~<参数类型1>;<参数类型2>" \
  --args '[<参数值1>, "<参数值2>"]' \
  --app taobao-yc-serverless --unit pre
```

**已验证的方法签名**（通过 `mw hsf metadata methods` 获取）：

```bash
# RightApplyToolHsfService
updateStatus~java.lang.Long;java.lang.String           # 修改申请状态
updateExtraInfo~java.lang.Long;com.taobao.industry.yc.serverless.domain.entity.RightApplyExtraInfo  # 修改扩展信息
updateProtectExpiredTime~java.lang.Long;java.util.Date  # 修改保护到期时间
updateApplyTime~java.lang.Long;java.util.Date           # 修改申请时间
updateToRegularStatus~java.lang.Long;java.lang.String   # 修改转普通状态
updateCertApplyTime~java.lang.Long;java.lang.String     # 修改发证申请时间
initEnvAndTest~java.util.List<java.lang.Long>;java.lang.String  # 初始化环境测试数据

# RightSettleToolHsfService
getSettleOrderByApplyId~java.lang.Long                  # 按 applyId 查结算单（只读）
onFirstPublish~java.lang.Long                           # 首发处理
initSettleOrderWithApply~java.util.List<java.lang.Long> # 按申请初始化结算单
updateInitAllowanceStartTimeWithApplyId~java.lang.Long;java.util.Date  # 修改补贴起始时间
updateInitAllowanceStartTime~java.lang.Long;java.util.Date             # 修改补贴起始时间（按结算单ID）
initSettleOrderWithSeller~java.util.List<java.lang.Long>               # 按商家初始化结算单
deleteById~java.lang.Long                               # 删除结算单
updateStatus~java.lang.Long;java.lang.String            # 修改结算状态

# RightToolHsfService
updateItemAuditPassTime~java.lang.Long;java.util.Date   # 修改商品审核通过时间
initProtectExpiredTime~java.util.List<java.lang.Long>   # 批量初始化保护到期时间
initProtectExpiredTime~java.lang.Long;java.util.Date    # 初始化保护到期时间
updateProtectStartTime~java.lang.Long;java.util.Date    # 修改保护开始时间
updateItemName~java.lang.Long;java.lang.Long            # 修改商品名称
refreshProtectInfo~java.lang.Long                       # 刷新保护信息
refreshTortInfo~java.lang.Long                          # 刷新侵权信息
updateExtraInfo~java.lang.Long;com.taobao.industry.yc.serverless.domain.entity.RightExtraInfo  # 修改扩展信息
updateStatus~java.lang.Long;java.lang.String            # 修改权益状态
bindItem~java.lang.Long;java.lang.Long;java.lang.Boolean # 绑定商品

# SellerEnterToolService
initTestFlag~java.util.List<java.lang.Long>             # 初始化测试标记
updateServiceInfo~java.lang.Long;com.taobao.industry.yc.serverless.domain.entity.SellerServiceInfo  # 修改服务信息
unEnter~java.lang.Long                                  # 取消入驻
saveSellerAndShopName~java.util.List<java.lang.Long>    # 保存商家和店铺名
enter~java.lang.Long                                    # 入驻

# ServiceTradeToolService
updateBizScene~java.util.List<java.lang.Long>;java.lang.String  # 修改业务场景
initTradeBizAndAmount~java.util.List<java.lang.Long>            # 初始化交易业务和金额
rebuildUseCount~java.lang.Long                          # 重建使用次数
startRefund~java.lang.Long;java.lang.String;java.lang.Long      # 开始退款
initTradeBizAndAmountBySeller~java.util.List<java.lang.Long>    # 按商家初始化交易
rebuildServiceTradeCount~java.lang.Long;java.lang.String        # 重建服务交易次数
finishRefund~java.lang.Long;java.lang.String;boolean            # 完成退款
trade~java.lang.Long;java.lang.Integer                  # 交易
trade~com.taobao.industry.yc.serverless.application.service.request.ServiceBuyReq  # 交易（复杂参数）
delete~java.lang.Long;java.lang.String                  # 删除

# TortToolService
updateGoodsUrl~java.lang.Long;java.lang.String          # 修改商品URL
initStatus~java.util.List<java.lang.Long>               # 批量初始化状态
syncStatusFromProtectRecord~java.util.List<java.lang.Long>  # 从保护记录同步状态
fillSellerIdForProtectRecord~java.util.List<java.lang.Long> # 填充保护记录的 sellerId
fillSellerIdForTortRecord~java.util.List<java.lang.Long>    # 填充侵权记录的 sellerId
autoProtectForManual~java.util.List<java.lang.Long>     # 手动自动保护
deleteByIds~java.util.List<java.lang.Long>;java.lang.String # 按ID批量删除
```

**已验证的调用示例**（2026-07-13）：

```bash
# 模拟审核通过：QUICK_AUDITING → QUICK_AUDITED
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[200000874, "QUICK_AUDITED"]' \
  --app taobao-yc-serverless --unit pre

# 返回：{"success": true, "data": true, "fail": false}
# DB 验证：status 已从 QUICK_AUDITING 变为 QUICK_AUDITED，gmt_modified 更新
```

**常用状态值**：
- PASS：`QUICK_AUDITED`（快审通过）、`PRE_AUDITED`（初审通过）
- REJECT：`QUICK_REJECT`（快审驳回）、`PRE_AUDIT_REJECT`（初审驳回，待验证）

**查方法签名**（遇到未记录的方法时）：

```bash
mw hsf metadata methods "com.taobao.industry.yc.serverless.service.hsf.tool.<ServiceName>:1.0.0" --unit pre
```

### 方式 B：通过浏览器内 JS 调用（备选）

当 a1 CLI 不可用时，在千牛预发页面内执行：

```javascript
// 通过 MTOP 间接调用 HSF（部分 Tool 服务暴露为 MTOP 接口）
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.apply',
  v: '1.0',
  method: 'POST',
  data: { /* ... */ }
}, onSuccess, onError);
```

### 方式 C：通过 DMS MCP 验证结果

所有 HSF 调用后，**必须**通过 DB 查询验证结果：

```sql
-- 验证申请状态变更
SELECT id, status, gmt_modified
FROM yc_right_apply
WHERE id = {applyId} AND env = 'staging';

-- 验证结算单变更
SELECT id, settle_status, total_amount, init_allowance_start_time
FROM yc_right_settle_order
WHERE right_apply_id = {applyId} AND env = 'staging';

-- 验证操作流水（该表无 env 列，须经已核实 staging 的 applyId 间接过滤；
-- 真实列名 operate_type/operator_name/operate_time/extra_info，无 op_type/op_detail）
SELECT operate_type, operator_name, operate_time, extra_info
FROM yc_right_apply_op_record
WHERE right_apply_id = {applyId}
ORDER BY operate_time DESC LIMIT 5;
```

## 组合操作模板

### 模板 1：构造"快审通过 → 绑定商品 → 首发标签"全链路数据

```
步骤 1: yc-quick-audit-data-create → 创建 QUICK 申请（拿到 applyId）
步骤 2: HSF RightApplyToolHsfService.updateStatus(applyId, 'QUICK_AUDITED') → 模拟快审通过
步骤 3: 商家端 MTOP binditem → 绑定商品
步骤 4: HSF RightSettleToolHsfService.updateInitAllowanceStartTimeWithApplyId(applyId, now) → 触发补贴
步骤 5: DB 验证 → 确认全链路状态正确
```

### 模板 2：构造"即将到期"测试数据

```
步骤 1: 选择一条已发证申请（status=CERT_FILE_SYNCED）
步骤 2: HSF RightApplyToolHsfService.updateProtectExpiredTime(applyId, today+20days)
步骤 3: DB 验证 protect_expire_time 已更新
步骤 4: UI 验证 → 发布按钮置灰 + 线索提交限制
```

### 模板 3：构造"退款"测试数据

```
步骤 1: 选择一条 PROCESSING 结算单
步骤 2: HSF RightSettleToolHsfService.updateSettleStatus(settleId, 'FINISH_REFUNDING')
步骤 3: HSF ServiceTradeToolService.triggerRefund(orderId) → 触发退款
步骤 4: DB 验证 settle_status 已更新 + refund_apply_order 已创建
```

### 模板 4：模拟审核结果（回归测试专用）

> **⚠️ 仅限回归测试使用。** 正式测试默认走真实第三方审核流程：汇总 applyId + yc_right id 通过钉钉发给目民001，等待实际审核完成后再继续。仅当用户明确说"回归测试"或"模拟审核"时才使用本模板。

用 HSF updateStatus 直接把申请推到目标状态，跳过第三方审核环节，用于回归用例快速验证。

**输入**：applyId + expectedResult（PASS / REJECT）

**PASS 路径**：
```
步骤 1: HSF RightApplyToolHsfService.updateStatus(applyId, 'QUICK_AUDITED')  -- QUICK 快审通过
        或 updateStatus(applyId, 'PRE_AUDITED')  -- PRE 初审通过
步骤 2: DB 验证 → SELECT status FROM yc_right_apply WHERE id = {applyId}
步骤 3: 可选 → 继续模板 1 的绑品/补贴流程
```

**REJECT 路径**：
```
步骤 1: HSF RightApplyToolHsfService.updateStatus(applyId, 'QUICK_REJECT')  -- QUICK 快审驳回
        或 updateStatus(applyId, 'PRE_AUDIT_REJECT')  -- PRE 初审驳回
步骤 2: DB 验证 → SELECT status FROM yc_right_apply WHERE id = {applyId}
步骤 3: 可选 → 验证申诉窗口是否打开
```

**适用场景（回归测试）**：
- 回归用例全流程自动化时消除第三方审核依赖，实现零人工闭环
- 批量造不同审核结果数据（PASS/REJECT 各 N 条）
- 测试驳回后的申诉/重新提交逻辑

**注意**：
- updateStatus 只改 status 字段，不触发 MetaQ 消息和下游消费者
- 如需完整流转（含通知商家、下游消费），应通过 MTOP API 走正常业务流程或等 MetaQ 权限开通后用消息模拟
- 状态值需与状态机一致，非法状态跳转会失败

## MetaQ 消息模拟（Phase 1.4 扩展）

> ⚠ 当前为文档记录，待 MetaQ 预发 topic 发送权限开通后可直接执行

### 可用 Topic 列表

| Topic | Tag 示例 | 触发效果 |
|-------|---------|---------|
| TOPIC_YC_PATENT | apply_submit | yc_right_apply 状态 → pending_review |
| TOPIC_YC_PATENT | approval | 状态 → approved + 通知商家 |
| TOPIC_YC_PATENT | reject | 状态 → rejected + 触发申诉窗口 |
| TOPIC_YC_BIND | bind | yc_right_product 写入 + 维权能力上线 |
| TOPIC_YC_TORT | detect | 监听跨平台爬虫扫描结果 |
| TOPIC_YC_SETTLE | calc | 70% 下架率达成触发结算计算 |

### 消息发送模板（待权限开通后使用）

```bash
# 发送 MetaQ 消息（预发环境）
a1 metaq send --topic TOPIC_YC_PATENT --tag approval \
  --body '{"applyId": 200000752, "status": "approved"}'
```

## ScheduleX 手动触发（Phase 1.5 已落地）

> ⚠ 仅预发环境支持手动触发，生产需走变更。当前自动化触发受 CLI/浏览器能力限制，脚本提供 `auto → cli → browser → manual` 四级降级，详见 [references/async-trigger-guide.md](references/async-trigger-guide.md)。

### 推荐脚本入口

```bash
# 自动触发完整结算 Job 链（先校验 env，再按顺序触发 4 个任务，最后 DB 验证）
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000752 --job-chain full --verify-db

# 仅触发单个任务（如专利保护定时失效）
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000752 --job-id 399576024 --verify-db

# 只输出控制台操作指引（CLI/浏览器都不可用时的人工兜底）
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000752 --job-chain full --method manual

# 演练模式：不实际触发任何任务，仅打印执行计划
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000752 --job-chain full --dry-run
```

脚本会自动执行：
1. `env_check.py` 前置校验，只有 `env='staging'` 才继续；
2. 按正确时序串行触发 Job；
3. 任务完成后轮询 DB 验证状态变更（`yc_right.status`、`yc_right_settle_order.serv_finish_*_status` 等）。

### 控制台入口（人工兜底）

- **预发 ScheduleX**：`https://pre.schedulerx2.alibaba-inc.com/?spm=ata.21736010.0.0.6775216263obdM#/JobList?regionId=cn-hangzhou&namespace=system_namespace&source=schedulerx`

**前置准备**

- 步骤 0.1：打开浏览器，访问上方控制台地址。
- 步骤 0.2：确认本次处理日期 `dataTime`（格式 `yyyy-MM-dd`）：`{dataTime}`。

**任务 1：715618497 首发补贴退款**

- 步骤 1：在控制台右上角搜索框输入 `715618497`。
- 步骤 2：按 Enter 键触发搜索，等待任务列表出现对应任务行。
- 步骤 3：点击任务行右侧的「运行一次」按钮。
- 步骤 4：在弹出的参数输入框中填写 `dataTime = {dataTime}`。
- 步骤 5：点击弹窗中的「确定」按钮。
- 步骤 6：等待页面提示「触发成功」或任务状态变为 RUNNING/SUCCESS。
- 步骤 7：确认该任务执行完成后，再继续下一个任务。

**任务 2：399576024 专利保护定时失效**

- 步骤 8：在控制台右上角搜索框输入 `399576024`。
- 步骤 9：按 Enter 键触发搜索，等待任务列表出现对应任务行。
- 步骤 10：点击任务行右侧的「运行一次」按钮。
- 步骤 11：在弹出的参数输入框中填写 `dataTime = {dataTime}`。
- 步骤 12：点击弹窗中的「确定」按钮。
- 步骤 13：等待页面提示「触发成功」或任务状态变为 RUNNING/SUCCESS。
- 步骤 14：确认该任务执行完成后，再继续下一个任务。

**任务 3：719211870 服务完结退款**

- 步骤 15：在控制台右上角搜索框输入 `719211870`。
- 步骤 16：按 Enter 键触发搜索，等待任务列表出现对应任务行。
- 步骤 17：点击任务行右侧的「运行一次」按钮。
- 步骤 18：在弹出的参数输入框中填写 `dataTime = {dataTime}`。
- 步骤 19：点击弹窗中的「确定」按钮。
- 步骤 20：等待页面提示「触发成功」或任务状态变为 RUNNING/SUCCESS。
- 步骤 21：确认该任务执行完成后，再继续下一个任务。

**任务 4：721504806 服务完结确认收**

- 步骤 22：在控制台右上角搜索框输入 `721504806`。
- 步骤 23：按 Enter 键触发搜索，等待任务列表出现对应任务行。
- 步骤 24：点击任务行右侧的「运行一次」按钮。
- 步骤 25：在弹出的参数输入框中填写 `dataTime = {dataTime}`。
- 步骤 26：点击弹窗中的「确定」按钮。
- 步骤 27：等待页面提示「触发成功」或任务状态变为 RUNNING/SUCCESS。
- 步骤 28：确认该任务执行完成后，进入结果验证。

**结果验证**

- 步骤 29：等待 1-2 分钟后，执行以下 SQL 验证状态流转：

```sql
-- 验证权益状态流转
SELECT id, status, protect_expire_time,
       serv_finish_refund_status, serv_finish_income_status
FROM yc_right
WHERE right_apply_id = {applyId} AND env = 'staging';

-- 验证结算单状态
SELECT id, settle_status, total_amount, init_allowance_start_time
FROM yc_right_settle_order
WHERE right_apply_id = {applyId} AND env = 'staging';
```

**注意事项**

- 必须等前一个 Job 执行完成再触发下一个，避免状态竞争。
- 严禁操作生产环境，所有验证 SQL 必须带 `env = 'staging'` 过滤。
- 「运行一次」按钮为 React 渲染的 span，JS `.click()` 不触发事件，请使用真实鼠标点击。

### 结算 Job 链（已验证 2026-07-08, 2026-07-10）

结算流程由 4 个定时任务串联，按时间顺序执行：

| Task ID | 业务名 | 代码类名 | Cron | 触发效果 |
|---------|--------|---------|------|---------|
| **715618497** | 首发补贴退款 | — | 01:00 | 处理首发补贴退款 |
| **399576024** | 专利保护定时失效 | RightProtectExpiredJob | 02:00 | 扫描 `protect_expire_time` 已过期的申请 → 标记 `yc_right.status = YC_PROTECT_INVALID` → 按下架率分流结算单 |
| **719211870** | 服务完结退款 | ServFinishRefundJob | 04:00 | 下架率 < 70%：执行退款（`serv_finish_refund_status: TO_DO → PROCESSING → FINISH`） |
| **721504806** | 服务完结确认收 | ServFinishIncomeJob | 06:00 | 下架率 ≥ 70%：执行确收（`serv_finish_income_status` 流转） |

**下架率分流规则**：
- 下架率 ≥ 70% → 走确收路径（`serv_finish_income_status` 流转，付供应商 335 元，退商家 0）
- 下架率 < 70% → 走退款路径（`serv_finish_refund_status` 流转，付供应商 0，退商家 33 元非首发 / 133 元首发的比例）

### 其他任务

| 任务（代码类名） | 业务名 | 触发效果 |
|----------------|--------|---------|
| InitAllowanceRefundJob | 补贴审核 | 审核补贴申请 |
| RightInvalidJob | 专利权无效 | 标记专利权无效 |
| RigthApplyToRegularTimeOutJob | 快审超时转普通 | 快审超时自动转普通 |

### 端到端验证流程

详见 [references/settlement-e2e.md](references/settlement-e2e.md) — 包含完整 DB 验证 SQL、预期状态变更和踩坑记录。

## 踩坑记录

1. **HSF Tool 调用无事务回滚**：状态变更是即时写入 DB 的，调用错误无法自动回滚，必须手动修复
2. **updateStatus 不等于状态机流转**：直接调用 updateStatus 只改 status 字段，不触发 MetaQ 消息和下游消费者。如需完整流转，应通过 MTOP API 走正常业务流程
3. **时间格式严格**：updateProtectExpiredTime 和 updateApplyTime 必须用 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss 格式，否则报错
4. **退款金额必须全量**：triggerRefund 时，退款金额必须等于订单剩余全部金额，否则校验失败
5. **补贴时间顺序**：必须先设 init_allowance_start_time 再设 protect_expire_time，否则补贴不发
6. **DB 验证是强制步骤**：每次 HSF 调用后必须查询 DB 确认结果，不可跳过
7. **生产数据误改事故（2026-07-14，永久警示）**：yc-batch-data.sh 的测试清单混入了 applyId=200001006（env='production'，真实商家 1820321760），HSF updateStatus 将其状态改为 PRE_AUDITED，污染了真实商家的初审流程。根因：挑选测试数据时未按 env 过滤，事后核查又只查了测试商家名下记录。教训：① 任何 ID 进入测试清单前必须逐条 SELECT 核实 env='staging'；② 核查覆盖面必须包含所有被操作的 ID，不能只查熟悉的商家。

## 验证

每次操作完成后验证：
- [ ] HSF 调用返回成功
- [ ] DB 查询确认目标字段已更新
- [ ] op_record 操作流水已记录
- [ ] UI 端展示与 DB 数据一致（如适用）
