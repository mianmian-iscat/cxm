---
name: op-test
version: 2.0.0
description: Execute test cases on the Original Protection (淘天服饰原创保护) platform pre-prod environment with API assertions, DB validations, and UI guidance
description_zh: 在原创保护预发环境自动执行测试用例——场景识别→API断言→DB校验→UI验证→结果判定→证据上报全流程自动闭环，禁止询问用户"下一步做什么"
user-invocable: true
argument-hint: 提供测试场景描述（如"测试结算金额计算"/"验证快审扣减时机"）或pytest脚本路径
---

# 原创保护执行助手 v2.0

在预发环境自动执行原创保护平台的测试用例，自动完成API断言、DB校验、UI验证、结果判定、证据上报。

> **Harness 框架驱动**：本 skill 基于 `core/` 目录下的 14 个 Harness 核心模块，提供状态机断言、结算计算、合规检查、智能自愈、知识沉淀、隐私脱敏、五维评估等自动化能力。

---

## 自动执行规则（强制）

本 skill 的核心原则：**自主执行，不问下一步。**

收到用户输入后，必须按以下流程自主完成全部步骤，中间不得询问用户"接下来做什么"或"是否需要继续"：

1. **场景识别**（30秒内）：从用户输入中提取测试目标、涉及的表、API、规则域
2. **环境准备**：打开预发页面、确认测试账号、检查山海关开关
3. **数据准备**：检查是否需要造数（HSF Tool），需要则自动执行
4. **API断言**：在浏览器内执行 MTOP 调用，捕获响应
5. **DB校验**：执行 SQL 查询，比对预期值
6. **UI验证**：检查页面组件状态
7. **结果判定**：自动判定 PASS / FAIL / BLOCKED
8. **证据上报**：通过 att-tf 上报测试结果

**禁止行为：**
- 禁止问"接下来要做什么"
- 禁止问"是否需要执行下一步"
- 禁止问"请确认是否继续"
- 禁止在完成一个步骤后等待用户指令

**唯一允许询问的场景：**
- 用户提供的测试场景信息不足以确定执行路径
- 测试执行遇到环境异常需要用户协助

---

## Harness 框架能力集成

本 skill 集成了以下 Harness 核心模块，测试执行过程中**自动调用**，无需手动指定：

### 状态机断言 (`core/state_machine.py`)

申请状态流转自动校验，基于 `harness/state_machines/patent_application.yaml` 定义：

```python
from core.state_machine import StateMachineEngine
sm = StateMachineEngine.from_yaml("harness/state_machines/patent_application.yaml")
result = sm.validate_transition("SAVING", "QUICK_AUDITING", context={"trigger": "submit"})
# result.valid → True/False, result.errors → 非法转换原因
```

**覆盖的状态流转：**
- 申请状态：SAVING→QUICK_AUDITING→PRE_PRE_AUDITING→PRE_PRE_AUDITED→CERT_AUTHED→CERT_FILE_SYNCED
- Right状态：APPLYING→YC_PROTECT_VALID→YC_PROTECT_INVALID
- 结算状态：TO_DO→PROCESSING→FINISH
- 转普通：to_regular_status: TO_DO→DONE/TIMEOUT

### 结算计算器 (`core/settlement_calc.py`)

效果对赌公式精确计算，Decimal 精度到分：

```python
from core.settlement_calc import SettlementCalculator, CaseData, EnforcementResults, ContractInfo
from decimal import Decimal
calc = SettlementCalculator()
result = calc.calculate_settlement(
    service_fee=Decimal("50000"),
    takedown_count=80,
    total_count=100,
)
# 下架率≥70%: 全额确收; 30-70%: 按比例; <30%: 全额退款
```

### 四层断言框架 (`core/assertion_framework.py`)

统一断言入口，一次调用完成全部校验：

```python
from core.assertion_framework import AssertionFramework
fw = AssertionFramework(
    state_machine_path="harness/state_machines/patent_application.yaml",
    contracts_path="harness/contracts/cross_system_contracts.yaml",
)
report = fw.run_all_assertions(
    case_id="OP-TC-0001",
    from_state="CERT_AUTHED", to_state="CERT_FILE_SYNCED",
    settlement_case=case_data,
    captured_responses={"快维": {...}, "YC": {...}},
)
# report.passed → True/False, report.to_summary() → 四层结果汇总
```

### 合规检查器 (`core/compliance_checker.py`)

四维合规校验：电子签章 / 商家资质 / 保护期时效 / 数据脱敏。

### 智能自愈 (`core/self_healing.py`)

失败自动分类 + 分级放行 + 自愈引擎：

```python
from core.self_healing import SelfHealingEngine
engine = SelfHealingEngine()
classification = engine.classify(error_msg="element not found: selector timeout")
# → FailureCategory.SCRIPT_ISSUE
heal_result = engine.heal(classification, context={"selector": ".btn"})
# → HealingResult(action="cdp_relocate", success=True)
release = engine.grade_release(severity="P1", case_id="OP-TC-0001")
# → P1: 警告 + 建议复测
```

**自愈策略：**
- 元素定位漂移 → CDP 重定位
- Schema 变更 → 从 Spec 重新生成
- 数据失效 → 沙箱重置
- 环境不可用 → 等待重试（指数退避）

**熔断阈值：** 连续 3 个用例失败 或 失败率 > 40% 触发熔断。

### 知识沉淀 (`core/knowledge_base.py` + `core/feedback_loops.py`)

每次执行自动沉淀 BadCase 到知识库：

```python
from core.knowledge_base import KnowledgeBase
from core.feedback_loops import FeedbackHookRegistry, setup_default_hooks
kb = KnowledgeBase(root="harness/knowledge")
registry = FeedbackHookRegistry()
setup_default_hooks(registry)  # 注册四大闭环 Hook
# Pipeline 执行时自动触发：失败用例 → patterns/ 沉淀
```

### 隐私脱敏 (`core/privacy_guard.py`)

DB 查询结果和上报数据自动脱敏：

```python
from core.privacy_guard import PrivacyGuard
guard = PrivacyGuard()
safe_text = guard.sanitize("手机13812345678，身份证330102199001011234")
# → "手机138****5678，身份证3301***********234"
```

### 五维评估 (`core/evaluation.py`)

执行完成后自动生成评估报告：

```python
from core.evaluation import EvaluationEngine
engine = EvaluationEngine()
report = engine.evaluate({
    "pass_rate": 0.95,
    "assertion_coverage": 0.88,
    "efficiency_ratio": 3.5,
    "avg_duration_ms": 2000,
    # ... 更多指标
})
# report.total_score → 78.5, report.rating.level → RatingLevel.B (灰度上线)
```

### 审计轨迹 (`core/audit_trail.py`)

所有状态变更和资金操作记录不可篡改的 SHA256 链式哈希日志。

---

## 场景自动路由

收到用户输入后，按以下规则自动识别执行路径：

| 用户输入关键词 | 自动路由 | Harness 模块 |
|--------------|---------|-------------|
| 结算、金额、补贴、退款 | 结算金额计算校验流程 | `settlement_calc.py` |
| 首发、标签、first_publish | 首发标签5种时间组合校验 | `compliance_checker.py` |
| 快审、初审、PRE、QUICK | 申请状态机流转校验 | `state_machine.py` |
| 到期、20天、禁发期 | 到期与禁发期规则校验 | `compliance_checker.py` |
| 维权、侵权、下架率 | 维权流程与平台覆盖校验 | `settlement_calc.py` |
| 入驻、seller_enter | 入驻校验流程（含小二端快审） | `state_machine.py` |
| 转普通、TO_REGULAR | 转普通申请流程校验 | `pipeline_dsl.py` (to_regular_full_flow) |
| 千牛标、TTYCBH | 千牛标打标流程 | `tool_registry.py` |

路由后自动执行：识别场景后，直接跳到对应的"执行清单"开始执行。

---

## 执行流程

### 第一步：环境确认（自动完成）

打开预发环境：

- 商家端：`https://pre-fsyc.taobao.com/`（hostname含pre自动切预发MTOP）
- 小二端：`https://pre-xiaoer.alibaba-inc.com/bzb/noone/taotian-apparel-original-protection-xiaoer/list`

测试账号选择：
- 主账号：isv项目测试专用
- 备账号：测试账号八载02

> **重要**：新开tab防止租户串扰

山海关开关：预发环境数据操作必须开启山海关开关

### 第二步：API断言执行（自动完成）

预发SSO是httpOnly cookie，**必须在浏览器内执行JS fetch**。

参考 `references/MTOP-API清单.md` 调用商家端21个API + 小二端10个API。

```javascript
// 商家端MTOP调用模式
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.page',
  v: '1.0',
  data: { /* 参数 */ },
  needLogin: true
}).then(res => { window.__var_result = res; });

await new Promise(r => setTimeout(r, 2000));
console.log(JSON.stringify(window.__var_result));
```

> **已知问题**：`/api/seller/apply/submitToRegular`（POST）等非浏览器fetch易返HTML。

**Harness 集成点**：API 响应自动经过 `assertion_framework.py` 的 Layer 3（跨系统契约断言）校验，对照 `harness/contracts/cross_system_contracts.yaml` 中定义的快维/YC/汇金/e签宝字段契约。

### 第三步：DB状态断言（自动完成）

核心连接：
- 库名：scenario（实际DB名=prod）
- 主机：33.9.212.198:3011
- db_id：975919

**方式 A：DMS MCP（推荐）**

```
调用 mcp__dms-mcp-server__executeScript
database_id: "975919"
script: SQL 语句
```

**方式 B：dms-alibaba CLI**

结果落盘在 `~/dms-alibaba/db-groups/{group}/sql/quick_{db}/_results/{date}/`，JSON 取 rows 字段。

**Harness 集成点**：DB 查询结果自动经过 `privacy_guard.py` 脱敏处理，敏感字段（手机号/身份证/银行卡）在写入证据前自动掩码。

#### 12张核心表速查

详见 `references/原创保护-DB表速查.md`。

| 表 | 用途 |
|---|------|
| yc_right | 专利权主表（status, applyTime, protectExpiredTime, first_publish） |
| yc_right_apply | 申请记录（status, applyType, applyTime, to_regular_status） |
| yc_right_settle_order | 结算单（settleStatus, init_allowance_start_time, init_allowance_amount） |
| yc_right_apply_op_record | 操作审计日志 |
| yc_right_protect_record | 维权记录 |
| tort_record | 侵权记录 |
| inspect_whitelist | 巡检白名单 |
| yc_seller_enter_info | 商家入驻 |
| yc_service_trade_record | 服务交易 |
| refund_apply_order | 退款申请单 |

> **注意**：`yc_seller_enter_info`、`yc_service_trade_record` 带 `yc_` 前缀，其余表无。

#### 补贴校验核心规则

`total_amount` 不是补贴金额——它是结算单基础金额（测试环境=10，生产=50000）。补贴是否发放看 `init_allowance_start_time`：

| 字段 | 含义 |
|------|------|
| `init_allowance_start_time IS NULL` | 补贴未触发 |
| `init_allowance_start_time IS NOT NULL` | 补贴已触发，此时 `init_allowance_amount` 必有值 |

9类白名单：`{16, 30, 50006843, 50011740, 1625, 50010404, 50006842, 28, 50468001}`

#### 首发编辑权限规则

运营端可编辑"是否首发"需同时满足：
1. 商家主营类目 ∈ 9类白名单
2. 该申请 `to_regular_status ≠ DONE`

| 端 | 9类商家 + 未转普通 | 非9类商家 | 9类但已转普通 |
|----|-------------------|----------|-------------|
| 运营端 | 可编辑 | 不可编辑 | 不可编辑 |
| 商家端 | 不可编辑 | 不可编辑 | 不可编辑 |

运营端确认首发后自动赋值：选"是"→ 点击"确认" → 系统自动赋值 `init_allowance_start_time`。

### 第四步：UI步骤验证（自动完成）

商家端关键组件验证点（参考 `references/前端组件测试要点.md`）：

| 组件 | 验证 |
|------|------|
| PatentApply | 三种模式切换、内容安全、6角度图上传 |
| PatentDetail | 5阶段时间轴、证书下载/预览、按钮条件 |
| BindProductModal | 两个Tab过滤、批量选择 |
| InspectionDetail | 饼图下架率、URL自动解析 |
| ContractPage | 5图展示、协议iframe+复选框 |

小二端验证点：
- **FilterArea**：9个筛选字段，申请状态7项+专利申请状态21项
- **FirstLaunchCell**：内联编辑+确认弹窗+T+3/T+4边界
- **QuickAuditDrawer**：sellerId查商家+主视图必填

### 第五步：测试数据准备（自动完成）

需要构造特定状态/时间时，调用测试工具HSF服务：

| 工具 | 用途 |
|------|------|
| RightApplyToolHsfService::updateApplyTime | 改申请时间 |
| RightApplyToolHsfService::updateProtectExpiredTime | 改到期时间 |
| RightSettleToolHsfService::updateInitAllowanceStartTimeWithApplyId | 改补贴起始时间 |
| ServiceTradeToolService::triggerRefund | 触发退款 |
| RightSettleToolHsfService::initSettleOrder | 初始化结算单 |
| TortToolService::batchUpdateStatus | 批量改侵权状态 |

> **关键时序**：必须先设补贴时间再设到期时间，否则补贴不发。

### 第六步：结果判定与上报（自动完成）

结果判定规则（**Harness 增强**）：

| 场景 | 判定 | Harness 模块 |
|------|------|-------------|
| API响应符合预期 + DB状态正确 + UI显示一致 | PASS | `assertion_framework.py` 四层全通过 |
| API响应异常 或 DB状态与预期不符 | FAIL | `self_healing.py` 自动分类失败原因 |
| 测试数据不存在 | BLOCKED → 自动造数重试 | `self_healing.py` 自愈策略 |
| 预发环境异常 | BLOCKED → 提示用户 | `orchestrator.py` 熔断器 |

**FAIL 用例自动处理（Harness 驱动）：**

1. `self_healing.py` 分类失败原因（真Bug / 脚本问题 / 数据失效 / 环境问题）
2. `self_healing.py` P0/P1/P2 分级放行（P0 阻断+通知，P1 警告+复测，P2 跳过+计入指标）
3. `feedback_loops.py` 自动生成 BadCase 记录写入 `harness/knowledge/patterns/`
4. `privacy_guard.py` 脱敏证据数据
5. `audit_trail.py` 记录操作轨迹（SHA256 链式哈希）
6. 上报到 att-tf

**执行完成后自动评估：**

`evaluation.py` 生成五维评估报告（功能正确性30% + 业务价值性30% + 执行稳定性20% + 性能效率10% + 可扩展性10%），输出 A/B/C/D 上线评级。

---

## 场景执行清单

### 清单A：结算金额计算校验

**Harness 模块**：`settlement_calc.py` + `assertion_framework.py`

1. 查 `yc_right_settle_order` 获取当前结算状态
2. 若 `init_allowance_start_time IS NULL` → 先调用 HSF Tool 设置补贴时间
3. 调用 HSF Tool 设置到期时间（必须晚于补贴时间）
4. 触发首发标签（如需要）
5. 等待 ScheduleX 任务或手动触发
6. 查 DB 验证 `total_amount` 值
7. **Harness 断言**：`settlement_calc.verify_effect_gamble()` 自动计算预期金额

判定：
- 首发 + 下架率≥70% → total_amount = 302 → PASS
- 非首发 + 下架率≥70% → total_amount = 202 → PASS
- 下架率<70% → total_amount = 33(首发) / 133(非首发) → PASS
- 其他值 → FAIL

### 清单B：快审流程校验

**Harness 模块**：`state_machine.py` + `compliance_checker.py`

1. 查 `seller_enter_info` 确认商家已入驻
2. 若未入驻 → 调用 HSF Tool 造数
3. 调用 MTOP API 提交快审
4. **Harness 断言**：`state_machine.validate_transition("SAVING", "QUICK_AUDITING")` 校验状态转换合法性
5. 查 `yc_right_apply_op_record` 验证操作日志

### 清单C：小二端快审入驻校验

**Harness 模块**：`state_machine.py` + `self_healing.py`

1. 查 `seller_enter_info` 确认目标商家入驻状态
2. 若未入驻 → 小二端提交快审 → 预期被拦截
3. 若已入驻 → 正常提交 → 预期成功

### 清单D：首发标签时间组合校验

**Harness 模块**：`compliance_checker.py` + `state_machine.py`

1. 查 `yc_right` 获取 `first_publish` 值
2. 查 `yc_right_apply` 获取 `to_regular_status`
3. 判断5种时间组合场景
4. **Harness 断言**：`compliance_checker.check_protection_period()` 校验保护期时效

### 清单E：到期前20天禁发期校验

**Harness 模块**：`compliance_checker.py`

1. 查 `yc_right` 获取 `protect_expired_time`
2. 计算禁发期边界
3. **Harness 断言**：验证发布/维权/上报入口全部禁用

### 清单F：转普通申请全流程

**Harness 模块**：`pipeline_dsl.py` + `state_machine.py` + `settlement_calc.py`

使用 `harness/pipelines/to_regular_full_flow.yaml` Pipeline 定义，自动编排：

```
触发转普通 → 状态机校验 → 结算金额重算 → 合规检查 → 断言汇总
```

---

## Harness 配置文件索引

| 文件 | 用途 |
|------|------|
| `harness/state_machines/patent_application.yaml` | 专利申请状态机（10状态×20+转换） |
| `harness/pipelines/to_regular_full_flow.yaml` | 转普通申请全流程 Pipeline |
| `harness/contracts/cross_system_contracts.yaml` | 跨系统契约（快维/YC/汇金/e签宝） |
| `harness/schemas/op_exec_assistant.json` | 执行助手 Schema |
| `harness/schemas/op_settlement_calc.json` | 结算计算器 Schema |
| `harness/schemas/op_compliance_check.json` | 合规检查 Schema |
| `harness/schemas/op_state_validator.json` | 状态校验器 Schema |
| `harness/schemas/op_evidence_collector.json` | 证据采集 Schema |
| `harness/registry.json` | 统一工具注册表（6个工具） |
| `harness/security/soul.md` | 安全红线声明（4条红线） |
| `harness/orchestrator_config.yaml` | 编排器配置（1M Token预算/5并发） |
| `harness/self_healing_rules.yaml` | 自愈规则（4类失败分类/P0/P1/P2） |
| `harness/evaluation_weights.yaml` | 五维评估权重与评级阈值 |
| `harness/knowledge/` | 四类目知识库（features/infra/patterns/contracts） |

---

## 安全红线（强制遵守）

详见 `harness/security/soul.md`：

1. **REDLINE-001**：群聊场景禁止读取个人敏感字段
2. **REDLINE-002**：MEMORY.md 仅可读取 [PUBLIC] 标签条目
3. **REDLINE-003**：BadCase 上传前必须脱敏（cookie/token/身份证/手机号/花名）
4. **REDLINE-004**：跨 workspace 数据访问需二次确认

---

## 知识库索引

| 文件 | 用途 |
|------|------|
| `references/原创保护-DB表速查.md` | 12张表+常用查询 |
| `references/MTOP-API清单.md` | 35个API速查 |
| `references/前端组件测试要点.md` | 关键组件验证点 |
| `references/HSF测试工具.md` | 测试数据准备工具 |

---

## 验证

自动执行完成全部步骤 + 结果判定 PASS/FAIL/BLOCKED + Harness 四层断言通过 + 上报到 att-tf 且未被拦截 + FAIL 用例自动沉淀到知识库 + 五维评估报告生成。
