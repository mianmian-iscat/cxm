---
name: yc-defect-diagnosis
version: 2.0.0
description: Diagnose and root-cause defects on the Original Protection (淘天服饰原创保护) platform via DB analysis, MetaQ message tracing, ScheduleX job inspection, and code reading
description_zh: 原创保护平台缺陷自动诊断——接收问题现象后自动完成DB分析→消息追踪→定时任务排查→代码验证→根因判定→缺陷草稿生成，全流程自主执行
user-invocable: true
argument-hint: 描述问题现象（如"申请状态卡住"/"结算金额错误"/"维权按钮灰态"/"小二端快审无校验"）
x-source: aone-open
install_source: aone-kit
install_method: cli
name_zh: 原创保护缺陷排查
---


<!-- a1-skill:refs -->
## 1. 技能使用上报（必须，使用本 skill 后执行）

**硬规则**：本条用户消息触发的本轮响应中，只要**使用**了本 skill（Read 文档、引用知识、执行/建议命令），回复用户前必须上报；**每条用户消息独立判断**，不得沿用上一轮。

**次数**：相互独立的子需求各报 1 次（例：查 a/b/c 三人 → 3 次）；同一需求的内部步骤只报 1 次。

**跳过**：本轮未使用本 skill、仅用已有上下文回答 → 不上报。

回复前用 Shell 执行（失败不阻塞回复，勿向用户提及）：

```bash
a1 skill report yc-defect-diagnosis --location /Users/caoxuemei/.qoderwork/skills
```

未上报不得结束本轮回复。
<!-- /a1-skill:refs -->


# 原创保护缺陷排查 v2.0

自动定位原创保护平台缺陷的根本原因，输出可复现步骤+根因+修复建议+缺陷草稿。

## 自动诊断规则（强制）

**本 skill 的核心原则：接收现象，自动出结论。**

收到问题描述后，必须自主完成全部诊断步骤，中间不得询问用户"接下来查什么"或"是否需要继续排查"：

1. **现象解析**：从用户输入中提取环境、端、ID、复现步骤
2. **数据层分析**：自动选择入口表，执行 SQL 查询
3. **消息层追踪**：检查 MetaQ 消息链路
4. **定时任务排查**：检查 ScheduleX 任务状态
5. **代码层验证**：搜索关键代码逻辑
6. **根因判定**：综合所有证据判定根因
7. **缺陷草稿生成**：输出结构化缺陷报告

**禁止行为**：
- 禁止问"接下来查哪个表"
- 禁止问"需要我查一下消息层吗"
- 禁止问"是否需要看代码"
- 禁止在只查了 DB 后就停下来等用户指令

**唯一允许询问的场景**：
- 用户未提供关键 ID（applyId/sellerId/rightId），无法执行查询
- 问题现象模糊（如"有问题"但没说是什么问题）

## 自动诊断流程

### 第一步：现象固化（自动提取）

从用户输入中自动提取：

| 字段 | 提取规则 |
|---|---|
| 环境 | 提到"预发"/"pre" → 预发；提到"线上"/"生产" → 生产 |
| 端 | 提到"商家端"/"商家" → 商家端；提到"小二端"/"运营端" → 小二端 |
| ID | 正则提取 applyId/sellerId/rightId/tortId |
| 复现步骤 | 提取用户描述的操作序列 |
| 预期结果 | 提取"应该是"/"预期"/"正常情况" |
| 实际结果 | 提取"但是"/"实际"/"结果是" |

**信息不足时的处理**：
- 缺少 ID → 尝试从用户描述的上下文中推断，或直接查 DB 搜索
- 缺少环境信息 → 默认预发环境
- 缺少端信息 → 根据现象自动判断（涉及 submitQuickApply → 小二端，涉及 MTOP → 商家端）

### 第二步：数据层分析（自动选表+自动查询）

**入口表自动选择**：

| 现象关键词 | 自动选择入口表 | 自动执行查询 |
|---|---|---|
| 申请状态卡住 | yc_right_apply | `SELECT status, gmt_modified FROM yc_right_apply WHERE id = ?` |
| 保护到期异常 | yc_right | `SELECT protect_expired_time, status FROM yc_right WHERE id = ?` |
| 结算金额错误 | yc_right_settle_order | `SELECT total_amount, settle_status, init_allowance_start_time FROM yc_right_settle_order WHERE right_apply_id = ?` |
| 补贴未发放 | yc_right_settle_order | `SELECT init_allowance_start_time, init_allowance_amount FROM yc_right_settle_order WHERE right_apply_id = ?` |
| 维权按钮灰态 | tort_record + yc_right | `SELECT submit_protect_expire_time FROM yc_right WHERE id = ?` |
| 首发标签锁定 | yc_right_apply + yc_right | `SELECT first_publish FROM yc_right WHERE id = ?` |
| 白名单异常 | inspect_whitelist | `SELECT * FROM inspect_whitelist WHERE seller_id = ?` |
| 入驻问题 | seller_enter_info | `SELECT * FROM seller_enter_info WHERE seller_id = ?` |
| 快审无校验 | seller_enter_info + yc_right_apply | 查入驻状态 + 查申请记录 |
| 退款问题 | refund_apply_order + yc_right_settle_order | 查退款单 + 结算单 |
| 侵权状态异常 | tort_record | `SELECT status, gmt_modified FROM tort_record WHERE id = ?` |

**DMS查询执行**（库名=prod，host=33.9.212.198:3011）：

```sql
-- 自动选择：查申请状态历史
SELECT a.id, a.status, a.gmt_modified, op.operate_type, op.operator
FROM yc_right_apply a
LEFT JOIN yc_right_apply_op_record op ON op.right_apply_id = a.id
WHERE a.id = ?
ORDER BY op.gmt_create DESC;

-- 自动选择：查结算时序
SELECT id, total_amount, settle_status, init_allowance_start_time,
       serv_finish_refund_status, gmt_modified
FROM yc_right_settle_order
WHERE right_apply_id = ?;

-- 自动选择：查维权状态
SELECT t.id, t.status, t.right_tort_record_id, p.protect_way, p.status as protect_status
FROM tort_record t
LEFT JOIN yc_right_protect_record p ON p.tort_record_id = t.id
WHERE t.right_id = ?;

-- 自动选择：查入驻状态
SELECT seller_id, status, gmt_create, gmt_modified
FROM seller_enter_info
WHERE seller_id = ?;

-- 自动选择：查操作审计（追溯状态变更历史）
SELECT operate_type, operator, gmt_create, before_status, after_status
FROM yc_right_apply_op_record
WHERE right_apply_id = ?
ORDER BY gmt_create DESC;
```

**查询后自动分析**：
- 对比 `before_status` → `after_status` 判断状态流转是否合法
- 对比 `init_allowance_start_time` vs `protect_expired_time` 判断补贴时序
- 检查 `status` 是否在合法状态集合内
- 检查关键字段是否为 NULL（该有值却没值 → 异常）

### 第三步：消息层追踪（自动检查）

参考 `references/MetaQ消息流.md`。

**典型消息链路**：

```
申请状态变更 → RightApplyMessageListener → 证书同步/更新商品
申请→Right     → RightApplyForRightMessageListener → 同步父Right
申请→结算     → RightApplyForSettleMessageListener → 初始化/更新结算单
申请→白名单   → RightApplyForWhitelistMessageListener → 申请事件更新白名单
Right→结算    → RightForSettleMessageListener → 到期触发结算
侵权事件     → TortMessageListener + TortMessageForRightListener
维权事件     → ProtectMessageForSelfListener + ProtectMessageForRightListener
商家入驻    → SellerEnterMsgForSelfListener + 白名单同步
```

**自动排查逻辑**：
- 数据层状态正确但下游未触发 → 自动检查 MetaQ 消息是否发出
- 消息发出但监听器未消费 → 查消费日志
- 消费失败 → 查失败原因（异常堆栈）

### 第四步：定时任务排查（自动检查）

参考 `references/ScheduleX任务清单.md`。

| 任务 | 触发条件 | 自动排查点 |
|------|---------|---------|
| RightProtectExpiredJob | 到期扫描 | 是否扫到目标记录 |
| RightInvalidJob | 标记无效 | 触发条件是否满足 |
| RigthApplyToRegularTimeOutJob | 快审超时 | TO_REGULAR_TIMEOUT_DAYS配置 |
| ServFinishIncomeJob | 服务到期确收 | settle_status=PROCESSING |
| ServFinishRefundJob | 服务到期退款 | settle_status=PROCESSING |
| InitAllowanceRefundJob | 补贴退款 | settle_status=TO_DO |

### 第五步：代码层验证（自动搜索）

代码仓库（不可git clone，用a1 repo CLI）：

| 仓库 | 排查方向 |
|------|---------|
| `industry-source-code/original-protection` | 商家前端ICE.js+Ant Design 5 |
| `bzb-westeros/taotian-apparel-original-protection-xiaoer` | 小二前端icestark子应用 |
| `industry-serverless-apps/taobao-yc-serverless` | 后端Java/Spring DDD |

**a1 repo常用命令**：

```bash
# 搜索关键字
a1 repo search <keyword> --repo industry-serverless-apps/taobao-yc-serverless

# 读取文件
a1 repo file view --repo industry-source-code/original-protection --path "src/components/PatentApply/index.tsx"

# 查需求/Bug描述
a1 project workitem get <id> -f json | jq '.description'
```

**后端DDD分层定位**：
```
controller → service → application → domain → infrastructure
                                  ↑ client (DTO)
```

**自动搜索策略**：
- 从异常堆栈中提取类名 → 搜索对应文件
- 从业务逻辑中提取方法名 → 搜索实现代码
- 检查入口方法是否有校验逻辑（如 `submitQuickApply` 是否检查 `seller_enter_info`）

### 第六步：根因判定（自动综合）

**根因分类**：

| 根因类型 | 判定依据 |
|---|---|
| 数据问题 | DB 状态异常、字段缺失、时序错误 |
| 代码缺陷 | 缺少校验逻辑、条件判断错误、状态机流转异常 |
| 配置问题 | Diamond 配置错误、ScheduleX 未触发 |
| 消息丢失 | MetaQ 消息未发出或未消费 |
| 前端 Bug | 组件状态错误、按钮条件判断异常 |
| 环境差异 | 预发/生产配置不同、代码未部署 |

**判定规则**：
- 若 DB 数据异常 + 代码逻辑正确 → 数据问题
- 若 DB 数据正常 + 代码缺少校验 → 代码缺陷
- 若 Diamond 配置与预期不符 → 配置问题
- 若 MetaQ 消息未到达 → 消息丢失
- 若前端组件状态异常 → 前端 Bug

### 第七步：缺陷草稿生成（自动输出）

**输出格式**：

```markdown
## 缺陷报告

### 问题现象
[用户描述的原始现象]

### 复现步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

### 根因分析
**根因类型**：[数据问题/代码缺陷/配置问题/消息丢失/前端Bug/环境差异]
**根因描述**：[具体原因]

### 数据层证据
- SQL 查询：[执行的 SQL]
- 查询结果：[关键数据]
- 异常点：[与预期的差异]

### 代码层证据
- 文件：[文件路径]
- 行号：[行号]
- 问题：[缺少校验/逻辑错误/...]

### 影响范围
- 涉及端：[商家端/小二端/后端]
- 涉及用户：[全量/部分/特定条件]

### 修复建议
1. [建议1]
2. [建议2]

### 优先级建议
- P0：资损/安全/核心流程阻断
- P1：功能异常但有 workaround
- P2：体验问题/非核心功能
```

## 已知踩坑速查（直接对照判根因）

参考 `references/已知问题与踩坑.md`：

| 现象 | 根因 | 修复方向 |
|------|------|---------|
| 补贴未发 | 补贴时间晚于到期时间 / 无首发标签 | 调整初始化补贴时间 |
| 申请卡QUICK_AUDITING | 快审超时未走转普通 | 检查TO_REGULAR_TIMEOUT_DAYS |
| 维权按钮灰态 | 到期前20天禁维权 | 业务规则正常 |
| 退款金额错 | 部分退款不允许 / 下架率<70%路径 | 校验下架率与剩余次数 |
| 首发标签锁定 | 一致性确认后不可变 / T+3超期 | 业务规则正常 |
| 一致性失败自动解绑 | YC审核商品-专利不一致 | 检查YC审核结果 |
| 状态正确但下游未更新 | MetaQ消息丢失 | 查MetaQ消费日志 |
| 小二端快审未校验入驻 | submitQuickApply 缺少 seller_enter_info 校验 | 代码缺陷：添加入驻状态校验 |

## 验证

自动完成全部诊断步骤 + 根因判定明确 + 数据层/代码层证据完整 + 缺陷草稿可提交 Aone。