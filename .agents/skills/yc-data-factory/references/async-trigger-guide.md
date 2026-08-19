# 原创保护异步链路触发指南

> 目标：把需要等待凌晨定时任务或异步消息消费的场景，变成可手动/自动触发的测试能力。
> 适用范围：预发环境（`env='staging'`），生产禁止手动触发。

---

## 一、ScheduleX 定时任务触发

### 1.1 结算 Job 链

原创保护结算由 4 个定时任务串联，**必须按顺序执行**：

| 顺序 | Task ID | 业务名 | 代码类名 | 触发效果 |
|------|---------|--------|---------|---------|
| 1 | **715618497** | 首发补贴退款 | — | 处理首发补贴退款 |
| 2 | **399576024** | 专利保护定时失效 | `RightProtectExpiredJob` | 扫描 `protect_expire_time` 已过期的申请 → 标记 `yc_right.status = YC_PROTECT_INVALID` → 按下架率分流结算单 |
| 3 | **719211870** | 服务完结退款 | `ServFinishRefundJob` | 下架率 < 70%：执行退款（`serv_finish_refund_status: TO_DO → PROCESSING → FINISH`） |
| 4 | **721504806** | 服务完结确认收 | `ServFinishIncomeJob` | 下架率 ≥ 70%：执行确收（`serv_finish_income_status` 流转） |

**下架率分流规则**：
- 下架率 ≥ 70% → 确收路径（付供应商 335 元，退商家 0）
- 下架率 < 70% → 退款路径（付供应商 0，退商家 33 元非首发 / 133 元首发的比例）

### 1.2 控制台入口

- **预发 ScheduleX**：`https://pre.schedulerx2.alibaba-inc.com/#/JobList?regionId=cn-hangzhou&namespace=system_namespace&source=schedulerx`

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

### 1.3 自动化脚本

```bash
# 生成完整 Job 链操作计划（dry-run）
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000874 --job-chain full --data-time 2026-08-18 --dry-run

# 仅触发"专利保护定时失效"并验证 DB
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000874 --job-chain expire --data-time 2026-08-18 --verify-db

# 仅输出手动操作指南
python3 ~/.qoderwork/skills/yc-data-factory/scripts/schedulex_trigger.py \
  --apply-id 200000874 --job-chain full --manual
```

脚本行为：
1. **env 校验**：调用 `env_check.py` 确认 `applyId` 为 staging（写操作安全红线）。
2. **自动触发尝试**：
   - 优先尝试 `a1 schedulerx job run --jobId {id} --dataTime {date}`（当前 a1 未暴露该子命令，作为未来就绪路径）。
   - CLI 不可用时降级为浏览器自动化提示（目前受 React 按钮/安全脚本限制，成功率低）。
3. **失败即停**：任一任务触发失败立即输出后续手动指南，避免半触发状态。
4. **DB 轮询验证**：`--verify-db` 下轮询 `yc_right` / `yc_right_settle_order` 状态，直到状态流转或超时。

### 1.4 降级路径

| 层级 | 路径 | 说明 |
|------|------|------|
| L1 | `a1 schedulerx job run` | 如果 a1 未来暴露该命令，最稳定 |
| L2 | 浏览器自动化（实验性） | 受 baxia/sufei_data/AWSC 安全脚本 + React span 点击限制，不推荐 |
| L3 | 手动控制台触发 | 当前最可靠路径，脚本失败时自动生成操作清单 |
| L4 | BLOCKED_ENV | 脚本/CLI/浏览器均不可用时，IM 私聊用户并标记 BLOCKED |

### 1.5 验证 SQL

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

---

## 二、MetaQ 消息模拟

### 2.1 可用 Topic

| Topic | Tag 示例 | 触发效果 |
|-------|---------|---------|
| TOPIC_YC_PATENT | apply_submit | `yc_right_apply` 状态 → pending_review |
| TOPIC_YC_PATENT | approval | 状态 → approved + 通知商家 |
| TOPIC_YC_PATENT | reject | 状态 → rejected + 触发申诉窗口 |
| TOPIC_YC_BIND | bind | `yc_right_product` 写入 + 维权能力上线 |
| TOPIC_YC_TORT | detect | 监听跨平台爬虫扫描结果 |
| TOPIC_YC_SETTLE | calc | 70% 下架率达成触发结算计算 |

### 2.2 发送方式

**当前状态（2026-08-18）**：
- `mw mq` 命令只有 `topic/consumer/subscription/message/qos` 子命令，**没有 `send`**。
- `a1 metaq` 子命令**不存在**。
- 因此 CLI 直接发送 MetaQ 消息暂不可行。

**可行的未来路径**：
```bash
# 期望命令（待权限/CLI 支持后启用）
a1 metaq send --topic TOPIC_YC_PATENT --tag approval \
  --body '{"applyId": 200000752, "status": "approved"}'
```

### 2.3 替代方案

在 MetaQ CLI 发送不可用时，通过以下方式模拟异步效果：

1. **HSF Tool 直接改状态**：
   - 用 `RightApplyToolHsfService.updateStatus` 把申请推到目标状态。
   - 缺点：不触发消息和下游消费者；仅用于纯状态验证。

2. **页面/API 走完整业务流程**：
   - 通过商家端/小二端页面提交，触发正常 MetaQ 生产和消费。
   - 优点：最接近真实链路；缺点：依赖页面可用性和测试账号。

3. **手动发送（需 MetaQ 预发 topic 发送权限）**：
   - 预发 MetaQ 控制台：`https://pre-ons.alibaba-inc.com/region/pre/topics`
   - 找到 Topic → 选择 Tag → 填写 body → 发送。

### 2.4 降级路径

| 层级 | 路径 | 说明 |
|------|------|------|
| L1 | `a1 metaq send` / `mw mq send` | CLI 直接发送，最自动化 |
| L2 | MetaQ 控制台手动发送 | 需预发 topic 发送权限 |
| L3 | HSF Tool 直接改状态 | 跳过消息层，仅验证 DB 状态 |
| L4 | 页面/API 走完整流程 | 最接近真实，但成本高 |

---

## 三、端到端验证流程

以"到期 → 退款"场景为例：

```
步骤 1: HSF RightApplyToolHsfService.updateProtectExpiredTime(applyId, today-1day)
         → 把 protect_expire_time 改到昨天
步骤 2: 触发 ScheduleX 399576024（专利保护定时失效）
         → yc_right.status 变为 YC_PROTECT_INVALID
步骤 3: 根据下架率选择路径：
         - 下架率 < 70% → 触发 719211870（服务完结退款）
         - 下架率 >= 70% → 触发 721504806（服务完结确认收）
步骤 4: DB 验证 yc_right_settle_order.settle_status 流转
步骤 5: 如需验证资金流，查询相关退款/确收明细
```

完整 SQL 与状态机对照见 [settlement-e2e.md](settlement-e2e.md)。

---

## 四、踩坑记录

1. **ScheduleX 域名**：只有 `pre.schedulerx2.alibaba-inc.com` 可用；`scx.alibaba-inc.com` / `schedulerx2.alibaba-inc.com` 为 NXDOMAIN；`schedulerx.alibaba-inc.com` 从 QoderWork 浏览器连接超时。
2. **React 按钮**：控制台「运行一次」是 React 渲染的 span，`JS .click()` 不触发事件，需真实鼠标事件或坐标点击。
3. **安全脚本拦截**：控制台加载 baxia / sufei_data / AWSC，浏览器自动化易被验证码/风控拦截。
4. **dataTime 格式**：通常为 `yyyy-MM-dd`，以任务实际要求为准。
5. **Job 顺序**：必须等前一个 Job 执行完成再触发下一个，尤其是 399576024 会改 `yc_right.status`，否则 719211870/721504806 无法正确分流。
6. **MetaQ 权限**：发送消息需要预发 topic 写入权限，当前未开通，需走权限申请。

---

## 五、安全红线

- 所有操作仅限 `env='staging'`。
- ScheduleX 仅允许操作预发；生产定时任务禁止手动触发。
- 任何 HSF 写操作前必须通过 `env_check.py` 校验。
- 不向任何钉钉群发送执行过程消息；结果/阻塞仅 IM 私聊用户。
