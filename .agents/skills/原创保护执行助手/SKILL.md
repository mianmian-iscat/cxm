---
name: 原创保护执行助手
version: 1.0.0
description: 淘天服饰原创保护平台测试执行层 Skill。优先通过 MTOP/HSF API 完成申请创建、模拟审核、商品绑定、补贴触发、退款触发、状态查询等操作；API 不可行时降级到 CDP 浏览器自动化。执行中做实时 API + DB 断言，并按 att-tf 规范采集截图与 cases.json。触发词：原创保护执行、yc执行、跑原创保护用例、API执行、UI执行、绑定商品、触发补贴、触发退款、查询状态。
---

# 原创保护执行助手

> 本 Skill 位于执行层，负责把用例/编排层下达的指令转化为对原创保护预发环境的真实操作，并返回可验证的结果。
> 上游调用方：`原创保护测试编排`、`原创保护用例生成`、`yc-quick-audit-data-create`、`yc-data-factory`。
> 下游验证方：`yc-db-verification`、`yc-defect-diagnosis`、`att-report`。

## 职责边界

- 执行原创保护相关 API/UI 动作，覆盖：创建申请、模拟审核、绑定商品、触发补贴、触发退款、查询状态。
- 实时断言：接口返回、DB 状态、页面表现三者至少校验两层。
- 采证：每次关键操作后截图，最终生成 `cases.json` 供 `att-report` 上报。
- 不替代上游用例设计；不替代下游根因诊断；不直接操作生产数据。

## 执行路径：API 优先，UI 兜底

```
收到执行指令
  ├─ 能走 MTOP/HSF API → 直接调用 API
  │     ├─ API 成功 + DB 断言通过 → PASS，采证
  │     └─ API 失败/不可调用 → 进入 MCP 三级降级
  └─ API 不可行 → CDP 浏览器自动化（web-automation）
        ├─ 成功 → PASS，采证
        └─ 失败 → BLOCKED，记录证据，IM 私聊用户
```

| 路径 | 场景 | 工具/协议 |
|------|------|-----------|
| API 首选 | 申请创建、模拟审核、绑品、补贴、退款、状态查询 | MTOP (`lib.mtop.request`)、HSF Tool (`mw hsf service invoke`)、DMS MCP/CLI |
| UI 兜底 | 需要千牛登录态、文件上传、支付扫码、ScheduleX 手动触发等无法纯 API 完成的步骤 | puppeteer CDP 9222，遵循 web-automation 规范 |

## 关键操作速查

| 操作 | 首选方式 |  fallback | 验证点 |
|------|----------|-----------|--------|
| 创建申请(QUICK/PRE) | MTOP `taobao.industry.yc.right.apply` | 商家端/小二端 UI | `yc_right_apply` 新增记录 status 正确 |
| 模拟审核通过 | HSF `RightApplyToolHsfService.updateStatus` | 小二端审核 UI | DB status 跳转正确 |
| 绑定商品 | HSF `RightToolHsfService.bindItem` | 商家端绑品 UI | `yc_right_product` 写入 + right status |
| 触发补贴 | HSF `RightSettleToolHsfService.updateInitAllowanceStartTimeWithApplyId` | UI 触发首发标签 | 结算单状态 + 补贴时间更新 |
| 触发退款 | HSF `ServiceTradeToolService.triggerRefund` / `startRefund` | UI 发起退款 | 结算单子状态、退款流水 |
| 查询状态 | DMS MCP/CLI 查询 + API 查询 | UI 页面断言 | 多源一致 |

> 具体命令模板、参数格式、状态值见 [references/execution-recipes.md](references/execution-recipes.md)。

## 流程推进：YC 回调处理

> 原创保护流程中，**YC 回调必须由第三方（YC 机构）触发**，不能自动或手动触发。
> 当用例执行到需要 YC 推进的节点时，按以下流程操作：联系目民 001 → 等待回调 → DB+UI 双重验证 → 进入下一节点。

### 完整流程节点

```
节点1: 初审通过 (PRE_PRE_AUDITED)
  ↓ 联系目民 001 → YC 机构审核通过
节点2: YC 回调受理（下发申请号）
  ↓ 商家绑定商品
节点3: 商家绑定商品
  ↓ YC 审核商品-专利一致性
节点4: YC 确认一致性 ← 关键节点（黑标权益在此生效）
  ↓ 下发专利证书
节点5: 下发专利证书 (CERT_AUTHED)
```

### 各节点检查点（DB + UI 双重验证）

#### 节点 1：初审通过

**DB 验证：**
```sql
SELECT id, outer_apply_id, seller_id, status, apply_type, free, extra_info
FROM yc_right_apply WHERE id = {applyId};
```
- status = 'PRE_PRE_AUDITED'
- extra_info 包含 prePreAuditInfo
- free：黑标商家应为 1，非黑标应为 0

**UI 验证（小二端）：** pre-xiaoer.alibaba-inc.com → 筛选申请编号
- 申请状态列 = "初审已审核通过"（蓝色标签）
- 是否首发列 = "未..." + "确认"按钮（灰色置灰）

#### 节点 2：YC 回调受理

**DB 验证：**
```sql
SELECT id, outer_apply_id, status FROM yc_right_apply WHERE id = {applyId};
```
- outer_apply_id 有值（格式：YCxxxxxxxxxx）
- status 变为 'PRE_AUDITING' 或后续状态

**UI 验证（小二端）：**
- 申请编号列显示 YC 编号
- 专利申请状态 = "专利申请中"

#### 节点 3：商家绑定商品

**DB 验证：**
```sql
SELECT id, right_id, item_id FROM yc_right_product WHERE right_id = {rightId};
```
- yc_right_product 表有绑定记录，item_id 不为空

**UI 验证（商家端）：** pre-fsyc.taobao.com → 申请详情
- 显示已绑定商品图片和名称

#### 节点 4：YC 确认一致性 ← 核心验证点

**DB 验证：**
```sql
SELECT id, seller_id, free, status FROM yc_right_apply WHERE id = {applyId};
```
- 黑标商家：free = 1
- 非黑标商家：free = 0

**UI 验证（小二端）← 黑标权益关键证据：**

| 商家类型 | "是否首发"列 | "确认"按钮 |
|---------|-------------|-----------|
| 黑标商家 | "未..." | **灰色置灰（不可点击）** — 前端硬编码禁用 |
| 非黑标商家 | "未..." | **可点击**（需满足后端 firstPublishAvailable 条件） |

> **首发编辑权限规则（代码已验证 RightDomainServiceImpl.firstPublishAvailable）：**
>
> 前置条件（全部满足才可编辑）：
> 1. 商品已绑定（itemDO != null）
> 2. 主营类目在 9 类白名单中
> 3. 未走过转普通流程（toRegularStatus == null）
> 4. 有一致性确认时间（itemAuditPassTime != null）
>
> 编辑窗口：
> - 基准时间 T = min(首次上架时间 firstStartsTime, 一致性确认时间 itemAuditPassTime)
> - **从未编辑过**（firstPublish == null）→ 始终可编辑（不受时间窗口限制）
> - **已编辑过** → T+3 天 0:00 前可编辑，超过后锁定
>
> 黑标商家：后端方法内无黑标判断，但前端 FirstLaunchCell 组件对黑标商家硬编码 disabled

**UI 验证（商家端）：**
- 黑标商家：显示"IFASHION 专属权益"，首发标签始终不可编辑
- 非黑标商家：首发标签在满足前置条件后可编辑，已编辑过的在 T+3 天 0:00 后锁定

#### 节点 5：下发专利证书

**DB 验证：**
```sql
SELECT id, status, extra_info FROM yc_right_apply WHERE id = {applyId};
```
- status = 'CERT_AUTHED'
- extra_info 包含证书文件 URL

**UI 验证（商家端）：**
- 显示"下载证书"按钮，专利状态 = "已授权"

**UI 验证（小二端）：**
- 权利状态 = "专利已授权"（绿色标签）

### 联系目民 001 推进流程

**触发时机：** 当前节点 DB+UI 验证通过后，需要 YC 机构推进到下一节点时。

**消息格式（纯文本，通过 delegate_to_im 发送到目民钉钉私聊）：**

```
以下{N}条记录已{当前状态} 麻烦{审核通过/审核驳回} 一直到环节{目标环节}

申请编号        YC 编号
{applyId1}    {outerApplyId1}
{applyId2}    {outerApplyId2}
```

**示例：**
```
以下两条记录已初审通过 麻烦审核通过 一直到环节下发专利证书

申请编号        YC 编号
200001458     YC31889588136
200001462     YC31889686312
```

**格式规则：**
- 只包含申请编号 + YC 编号，**不含**商家 ID、黑标标识、环境等冗余信息
- 指令必须明确：写明"审核通过"还是"审核驳回"，以及目标环节
- 目标环节根据测试用例需要选择（如"下发专利证书"、"YC 确认一致性"）

**发送后操作：**
1. 等待目民 001 回复确认已联系 YC 机构
2. YC 回调是异步的，不能立即验证
3. 收到回调完成通知后，按上述检查点逐步验证每个节点
4. **每个节点验证通过后截图留存**，再进入下一节点

## 安全红线：HSF 写前 env 预检

⚠️ 任何 HSF Tool 写操作前，**必须**先执行只读 SELECT 校验目标记录 `env`：

```sql
SELECT id, env FROM yc_right_apply WHERE id = {applyId};
```

- 仅 `env = 'staging'` 允许继续。
- `env = 'prod'` / `env = 'production'` / 空 / 查不到 → **立即中止并告警**，明确告知用户"目标为生产数据，禁止写操作"。
- 同一 applyId 在一次会话内被操作 N 次，也要在**每次写操作前重新 SELECT**，禁止复用上一环节结果。
- 结算单、权益表等通过 applyId/rightId 间接操作时，同样要先确认关联申请 env。

## MCP 三级降级 / CLI Fallback

当 MCP 工具调用失败时，按以下顺序降级，**不得在未尝试 L2 前私聊用户**。

| 级别 | 动作 | 示例 |
|------|------|------|
| L1 | 同 MCP 工具重试 + 参数校准 | DMS MCP 超时则缩短 SQL、增加 `env='staging'` 过滤重试 |
| L2 | 同能力 CLI 替代 | `dms-alibaba sql run scenario --db prod --sql "..."`；`mw hsf service invoke ...` |
| L3 | BLOCKED_MCP + IM 私聊用户 | 记录失败原因、已尝试路径、需要用户手动执行的步骤 |

降级记录必须写入执行日志：`{level, tool, fallback, reason, retryCount}`。

## att-tf 采证规范

每次执行产生独立 case 目录：

```
~/.att-tf/cases/{case-slug}-{timestamp}/
├── screenshots/
│   └── {step_index:02d}-{label}.png
├── case.json
└── exec.log
```

`case.json` 必须包含：

```json
{
  "caseTitle": "",
  "description": "",
  "status": 1,
  "priority": "P1",
  "groupPath": "原创保护/执行层/...",
  "errorMessage": "",
  "execLog": "",
  "artifacts": {
    "screenshots": ["/absolute/path/to/..."],
    "applyId": 0,
    "rightId": 0,
    "settleOrderId": 0
  }
}
```

- 关键操作（提交、审核、绑品、触发补贴/退款、最终状态）**必须截图**。
- API 执行时同步保留请求/响应摘要到 `exec.log`（脱敏，不出现真实商家敏感信息）。
- 用例失败时必须包含失败步骤截图 + 错误信息；成功时至少保留首尾两张。

## 群消息约束

- **禁止在测试执行过程中向钉钉群发送中间状态消息**（如"正在创建申请"、"正在查询 DB"）。
- 仅允许在以下场景发送群消息：
  1. 执行完全结束后的汇总报告（经 `qa-test-report` / `att-report` 格式化后）。
  2. 发现生产数据误操作风险时的即时告警。
  3. 用户显式要求广播进度。
- 日常交互、确认、降级提示使用 **IM 私聊**。

## 与周边 Skill 协作

| 场景 | 调用 Skill | 说明 |
|------|------------|------|
| 需要造数 | `yc-quick-audit-data-create` / `yc-data-factory` | 拿到 applyId 后再进入执行断言 |
| 需要 DB 验证 | `yc-db-verification` / `dms-alibaba` | 执行层自己也可做轻量断言，复杂校验交给验证层 |
| 需要 UI 兜底 | `web-automation` | 通过 CDP 操作已登录浏览器 |
| 失败根因 | `yc-defect-diagnosis` | 执行层只负责记录现象和证据 |
| 最终报告 | `qa-test-report` / `att-report` | 消费本 Skill 产出的 case.json |

## 输入输出契约

输入（最小集）：

```json
{
  "caseId": "yc-exec-001",
  "name": "快审通过-绑品-补贴",
  "sellerId": 2213249110271,
  "steps": [
    {"action": "createApply", "applyType": "QUICK", "mode": "MTOP"},
    {"action": "simulateAudit", "result": "PASS"},
    {"action": "bindItem", "itemId": 123456},
    {"action": "triggerAllowance"},
    {"action": "verifyStatus", "source": "DB"}
  ],
  "capture": {"screenshots": true, "caseJson": true}
}
```

输出：

```json
{
  "caseId": "yc-exec-001",
  "status": "PASS",
  "applyId": 200000999,
  "rightId": 0,
  "settleOrderId": 0,
  "steps": [{"step": 1, "action": "createApply", "status": "PASS", "screenshot": "..."}],
  "caseJsonPath": "~/.att-tf/cases/.../case.json",
  "errorMessage": ""
}
```

## 失败处理与自愈

1. API 失败先按 `references/execution-recipes.md` 检查参数格式（日期、`List<Long>` 双括号、复数字段等）。
2. 状态断言失败时，立即查 `yc_right_apply_op_record` 还原最近操作流水。
3. UI 兜底失败时，先查 `web-automation/references/error-pattern-map.json` 和 `boundary_cases.md`。
4. 连续 3 次无法恢复 → 状态置 `BLOCKED`，保留证据，IM 私聊用户决策。
