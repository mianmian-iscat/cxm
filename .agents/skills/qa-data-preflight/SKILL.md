---
name: qa-data-preflight
description: 测试前置数据就绪检查与造数自愈。在测试批次执行前自动扫描用例集的数据需求，对比环境现状，发现数据缺口后自动调用造数 skill 补齐。作为 harness-runner Stage 0-1 或独立调用。触发词：数据就绪、pre-flight、前置检查、数据缺口、造数自愈、数据预检、数据准备。
version: 1.0.0
---

> 📋 测试商家 seller_id 统一维护入口：[test-accounts.md](../yc-protection-qa-workbench/test-accounts.md)（插件根目录）

# QA Data Preflight — 前置数据就绪检查与造数自愈

在测试执行前扫描用例集的数据需求，对比环境数据现状，发现缺口后自动调用造数 skill 补齐。把"跑起来才发现 SKIP"变成"跑之前就知道缺什么并提前补齐"。

## 核心定位

```
                    传统流程                              本 skill 流程
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│ 用例执行 → 发现数据不足 → SKIP   │    │ 预检 → 发现缺口 → 造数 → 验证    │
│ → BLOCKED → 事后分析为什么阻塞    │    │ → 通过 → 进入执行（无阻塞）       │
└──────────────────────────────────┘    └──────────────────────────────────┘
```

本 skill 解决的是**执行条件不满足**的问题，与 qa-self-healing 解决的**执行失败恢复**互补。

## 前置条件

- `dms-alibaba` CLI 或 `db-query-tool` MCP 可用（查询环境数据现状）
- 造数 skill 已安装（如 `f88-template-package-create`）
- Data Registry 已配置（见 references/data-registry-schema.md）

**数据库查询路由（重要）：**
- 执行 SQL 查询前，**必须先加载 `f88-data-query` skill**，该 skill 包含完整的数据库连接信息和查询模板
- 数据库实例/连接信息的权威来源：`F88测试知识库/references/shared/db-connections.md`（stylespot 生产库 dbId=5335708 / dev 库 dbId=6369910 无权限）
- CLI 格式：`dms-alibaba sql run stylespot --db rm-lgay0v5lor8396yka --sql "..."`（生产库，有权限）
- 禁止猜测数据库实例名，必须从 db-connections.md 获取

## 核心工作流

### Stage 0：Pre-flight 数据就绪检查

#### Step 0.1：解析用例集数据需求

从用例集元数据中提取 `data_requirements` 声明：

```yaml
# 用例元数据示例
- case_id: TC-001
  data_requirements:
    template_package:
      cateId: {min_distinct: 5}      # 至少5种不同类目
      styleTags: {min_distinct: 3}   # 至少3种不同风格标签
      applyRange: COLLOCATION
      applyScene: F88_MAIN_IMAGE
    strategy:
      count: {min: 2}
      nodeType: template_match
```

**如果用例没有显式声明 data_requirements**，从用例步骤和断言条件反推：
1. 扫描用例的 `given` 前置条件，识别引用的数据类型
2. 扫描 `when` 步骤中的 API/页面操作，推断需要什么数据
3. 扫描 `then` 断言，确定关键字段的多样性要求

#### Step 0.2：查询环境数据现状

对每个数据需求，执行 Data Registry 中配置的 `verify_query`：

```
数据类型: template_package
验证查询: SELECT COUNT(DISTINCT cate_id) as cate_cnt,
         COUNT(DISTINCT style_tags) as tag_cnt
         FROM template_package
         WHERE env='staging' AND status IN (3,4)
阈值要求: cate_cnt >= 5 AND tag_cnt >= 3
当前状态: cate_cnt=1, tag_cnt=1 → 不满足
```

使用 `dms-alibaba` CLI 或 `db-query-tool` MCP 执行查询。

> **路由提示**：执行查询前，先加载 `f88-data-query` skill 获取正确的数据库连接信息（db-connections.md）。不要尝试 DMS MCP 工具（cron 隔离 session 中不可用），直接用 CLI。

#### Step 0.3：生成 DataGap 列表

对比需求与现状，生成缺口清单：

```json
{
  "gaps": [
    {
      "data_type": "template_package",
      "requirement": {"cateId": {"min_distinct": 5}, "styleTags": {"min_distinct": 3}},
      "current": {"cateId": 1, "styleTags": 1},
      "deficit": {"cateId": 4, "styleTags": 2},
      "affected_cases": ["TC-001", "TC-002", "TC-015", "..."],
      "registry_entry": "f88-template-package"
    }
  ],
  "summary": {
    "total_requirements": 3,
    "satisfied": 1,
    "gaps": 2,
    "affected_case_count": 50
  }
}
```

#### Step 0.4：决策点

- **DataGap 为空** → 所有数据就绪，直接进入 Stage 2（执行）
- **DataGap 非空** → 进入 Stage 1（造数自愈子链）

---

### Stage 1：造数自愈子链

#### Step 1.1：拓扑排序

查 Data Registry 中每个 gap 的 `depends_on`，按依赖拓扑排序：

```
template_package (无依赖) → 先造
strategy_config (依赖 template_package) → 后造
```

#### Step 1.2：逐个填补缺口

对每个 DataGap（按拓扑序）：

1. **查 Data Registry** 获取 `create_skill` 和 `params`
2. **调用造数 skill**：
   - 如果是 `f88-template-package-create` → 调用该 skill 创建多样化模板包
   - 如果是其他 skill → 按 skill 文档执行
3. **等待 cooldown_ms**（数据生效延迟）
4. **执行 verify 查询** 验证数据是否满足阈值
5. **结果判定**：
   - 通过 → 标记 `GAP_FILLED`，继续下一个
   - 未通过 → 重试（最多 3 次，指数退避 30s/60s/120s）
   - 重试耗尽 → 标记 `GAP_FAILED`

#### Step 1.3：造数失败处理

`GAP_FAILED` 的数据类型：
1. 记录完整诊断：造数 skill 调用参数、响应结果、失败原因
2. 关联用例标记为 `BLOCKED_DATA`（真实阻塞，非简单 SKIP）
3. 继续执行未阻塞的用例

#### Step 1.4：Stage 1 输出

```json
{
  "stage1_result": {
    "total_gaps": 2,
    "filled": 1,
    "failed": 1,
    "details": [
      {
        "data_type": "template_package",
        "status": "FILLED",
        "created_count": 5,
        "verify_result": {"cateId": 6, "styleTags": 4}
      },
      {
        "data_type": "strategy_config",
        "status": "FAILED",
        "failure_reason": "造数 skill 返回权限不足",
        "affected_cases": ["TC-101", "TC-102"]
      }
    ]
  }
}
```

---

> **post_verify 三层验证（harness-runner v2.1）**：Stage 1 造数后可配置三层 post_verify 验证——`type: db`（DataSetupVerifier，SQL  via dms-alibaba）、`type: ui`（UIVerifier，浏览器自动化 via alijk-agent-browser）、`type: code`（CodeVerifier，输出结构/值断言），由 PostVerifyDispatcher 统一路由。

---

## Data Registry 查询协议

Data Registry 是本 skill 的核心配置，存储在 `references/` 目录下按业务域分文件。

### 查询流程

1. 根据 `data_type` 在 Registry 中查找匹配条目
2. 读取 `create_skill`、`verify_query`、`params`、`depends_on` 等字段
3. 按字段指引执行操作

### Registry 条目结构

详见 [references/data-registry-schema.md](references/data-registry-schema.md)。

核心字段：
- `data_type`：数据类型标识
- `create_skill`：调用的造数 skill 名称
- `verify_query`：验证数据就绪的 SQL 查询
- `min_threshold`：最低数据量/多样性阈值
- `cooldown_ms`：造数后等待生效的时间
- `depends_on`：前置依赖的数据类型列表
- `params_template`：传给造数 skill 的参数模板

### 已注册的 F88 数据类型

详见 [references/f88-registries.md](references/f88-registries.md)。

当前已注册：
- `template_package`：模板包（cateId + styleTags 多样性）
- `strategy_config`：策略配置（nodeType + modelType）
- `batch_data`：批次数据（触发链路生产）

---

## 与 harness-runner 集成

当作为 harness-runner 的 Stage 0-1 运行时：

```
harness-runner init
    ↓
Stage 0: qa-data-preflight（本 skill）
    ↓ 检查数据就绪
Stage 1: qa-data-preflight（本 skill）
    ↓ 造数补齐缺口
Stage 2: 测试执行（qa-self-healing 管辖）
    ↓
Stage 3: 归因报告（f88-failure-analysis 管辖）
    ↓
Stage 4: 自愈流程验证（qa-self-healing 管辖）
    ↓ 故意制造故障 → 七步诊断 → 修复 → 重触发验证
```

harness-runner 在 `init` 之后、`execute` 之前插入 Stage 0-1。
Stage 4 在 Stage 3 之后执行，用于验证自愈流程的实际可用性。
具体集成方式见 harness-runner SKILL.md 的 "Stage 0-1 集成" 章节。

---

## 与 qa-self-healing 的关系

| 维度 | qa-data-preflight（本 skill） | qa-self-healing |
|------|------------------------------|-----------------|
| 解决什么 | 执行条件不满足（数据缺失） | 执行失败恢复 |
| 何时触发 | 执行前（Stage 0-1） | 执行中（Stage 2） |
| 典型场景 | 模板包数据单一导致用例无法验证 | API 返回 500 重试恢复 |
| 输出 | 数据就绪 / BLOCKED_DATA | PASS / FAIL / BLOCKED_LOGIC |

两者互补，不重叠：
- 本 skill 在执行前尽量消除数据层阻塞
- qa-self-healing 在执行中处理运行时异常
- 如果执行中仍遇到数据不足（如造数遗漏），qa-self-healing 的规则一（七步诊断）会兜底

---

## Pipeline 验证结论（2026-07-29 全链路验证）

在 5-Stage Test Resilience Pipeline 全链路验证中，本 skill 的 Stage 0→1 预防性造数效果得到实证：

**验证对比**：

| 批次 | Stage 0→1 造数 | Stage 2 执行结果 | 是否需要自愈 |
|------|---------------|-----------------|------------|
| BT_7340 | Stage 0 检测到 COLLOCATION+F88_SEEDING 缺口 → Stage 1 创建模板包 id=1930 | 1 秒到达审核节点，0 失败 | 不需要 |
| BT_7350 | 跳过（故意传空输入） | 卡死 PROCESSING，0 条 workflow 记录 | 需要 → BT_7352 修复验证通过 |

**核心结论**：预防性造数（Stage 0→1）比事后自愈更高效。BT_7340 一次通过无需自愈；BT_7350 因输入缺陷卡死，需额外诊断+重触发。本 skill 的价值在于把"跑起来才发现 SKIP"变成"跑之前就知道缺什么并提前补齐"。

---

## BLOCKED 分类细化

本 skill 引入 BLOCKED 子分类，供 Stage 3 报告使用：

| 分类 | 含义 | 处理路径 | 是否可自愈 |
|------|------|---------|-----------|
| `BLOCKED_DATA` | 前置数据不满足 | Stage 1 造数自愈子链 | 可自愈（有造数 skill 时） |
| `BLOCKED_ENV` | 环境不可用 | 等待/切换环境 | 半自动 |
| `BLOCKED_DEP` | 外部依赖缺失 | 降级或等待 | 视依赖而定 |
| `BLOCKED_LOGIC` | 业务逻辑限制 | 人工介入 | 不可自愈 |

**判定规则**：
1. Stage 0 发现缺口 + Stage 1 造数成功 → 不 BLOCKED，继续执行
2. Stage 1 造数失败 → `BLOCKED_DATA`，记录失败原因
3. 环境不可用（预发宕机/网络不通）→ `BLOCKED_ENV`
4. 依赖外部系统（算法模型下线/第三方 API 不可用）→ `BLOCKED_DEP`
5. 业务逻辑限制（同唯一键冲突/状态流转限制）→ `BLOCKED_LOGIC`

---

## 报告增强

Stage 3 报告中 BLOCKED 条目按子分类展开：

```
测试报告摘要:
  总用例: 204
  PASS: 120 | FAIL: 15 | SKIP: 10
  BLOCKED: 59
    ├─ BLOCKED_DATA: 50 (84.7%)
    │   ├─ 造数恢复: 45 (Stage 1 自动补齐)
    │   └─ 仍阻塞: 5 (造数 skill 无法覆盖)
    ├─ BLOCKED_ENV: 3 (5.1%)
    ├─ BLOCKED_DEP: 4 (6.8%)
    └─ BLOCKED_LOGIC: 2 (3.4%)

  实际覆盖率: 135/204 = 66.2%
  潜在覆盖率(造数恢复后): 180/204 = 88.2%
  造数恢复率: 45/50 = 90.0%
```

---

## 独立调用

除了作为 harness-runner 的 Stage 0-1，也可以独立调用：

```
用户说："帮我检查模板包数据够不够跑回归测试"
→ 执行 Stage 0（检查）
→ 输出 DataGap 列表
→ 问用户是否进入 Stage 1（造数）

用户说："造一些多样化的模板包数据"
→ 跳过 Stage 0，直接执行 Stage 1
→ 调用 f88-template-package-create 创建
```

---

## 红线约束

继承 qa-self-healing 的红线规则：
- F88: staging + DB 只读（造数通过 API/UI，不直接写 DB）
- YC: seller_id（见 test-accounts.md，当前默认 2213249110271）+ staging
- 造数 skill 调用前确认环境正确

## 硬约束：禁止复用存量数据

- **必须全量造新数据**，禁止复用历史存量数据
- 存量状态不可控（可能已被消费/修改/过期），基于存量数据测出的结果不可信
- 即使环境中"看起来有数据"，也无法确认其新鲜度和完整性，必须重新构造

## 架构缺口：hfz-test-workflow 路径不自动触发预检

本 skill（Stage 0-1）仅在 **harness-runner 路径**自动触发。hfz-test-workflow 的十步闭环不经过 harness-runner，造数预检不会自动执行。

具体表现：
- hfz-test-workflow 的造数在 Step 6（SKIP 补数自愈）**反应性触发**——必须先失败(SKIP)才造数据
- 直接跑 pytest 完全没有数据预检
- **结论**：日常测试走 hfz-test-workflow 时，预防性造数（Stage 0→1）不生效，需手动调用 qa-data-preflight 或在 hfz-test-workflow Step 4 前插入

---

## 禁止的偷懒模式

| 禁止写法 | 正确做法 |
|----------|----------|
| "数据不够，SKIP" | 先查 Registry → 调造数 skill → 验证 → 仍失败才 BLOCKED_DATA |
| "预发数据单一" | 量化：当前几种？需要几种？差几种？调造数 skill 补齐 |
| "没有造数 skill" | 查路由表 → 没有则走 qa-self-healing 规则一七步诊断 → 找到造数入口 |
| BLOCKED 不分子类 | 必须标 BLOCKED_DATA / BLOCKED_ENV / BLOCKED_DEP / BLOCKED_LOGIC |
