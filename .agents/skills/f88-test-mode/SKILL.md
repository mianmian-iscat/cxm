---
name: f88-test-mode
version: 1.1.0
description: F88 审核平台测试模式入口 — 自动加载相关技能并注入上下文。适用于非全流程的 F88 测试场景（单点验证、浏览器自动化、接口测试）。触发词：F88测试、F88验证、审核测试、首图审核、套图审核、模板审核、视频审核、F88造数。
description_zh: F88 审核平台测试模式入口，自动加载相关技能并注入上下文
---

# F88 测试模式入口

> 一句话：本技能是 F88 测试的**轻量级入口**，检测到 F88 测试意图时自动加载相关技能并注入上下文。不是全流程编排（那是 `hfz-test-workflow` 的职责）。

## 触发条件

检测到以下任一条件时激活：
- 用户说"F88测试"、"F88验证"、"审核测试"、"首图审核"、"套图审核"、"模板审核"、"视频审核"
- 任务涉及 F88 审核平台（关键词：F88、审核、aifashion-xiaoer）
- 浏览器自动化目标为 F88 审核页面
- 需要构造 F88 审核测试数据

**不激活的场景**：
- 用户明确要求"全流程测试"、"从 PRD 开始" → 路由到 `hfz-test-workflow`
- 非 F88 的测试任务

## 核心职责

### 1. 技能自动加载

检测到 F88 测试后，**主动加载以下技能**（按需，非强制全加载）：

| 技能 | 加载时机 | 用途 |
|------|---------|------|
| `att-start` | **必须** | 测试会话声明（SessionStart hook 已建议） |
| `审核数据构造` | 需要造数时 | 策略试运行（10833/10834）或手动创建 API |
| `qa-data-preflight` | 执行前检查数据就绪状态 | 扫描数据需求、发现缺口、自动造数 |
| `f88-failure-analysis` | 测试失败后 | 三层分类（逻辑/环境/数据）、根因分析 |
| `test-case-generator` | 需要生成用例时 | PRD → 测试用例 |
| `test-case-executor` | 需要执行用例时 | 用例 → 执行结果 |

**加载方式**：
- 通过 `Skill` 工具调用技能
- 或在回复中明确提及技能名称，让 agent 自动加载

### 2. F88 上下文注入

自动注入以下上下文，无需用户重复提供：

#### 环境配置

| 环境 | URL | 用途 |
|------|-----|------|
| 沙箱 | `https://sandbox-aifashion-xiaoer.alibaba-inc.com` | 接口测试默认 BASE_URL |
| 预发 | `https://pre-aifashion-xiaoer.alibaba-inc.com` | 预发验证 |
| 线上 | `https://aifashion-xiaoer.alibaba-inc.com` | 线上巡检（只读） |

**浏览器身份持久化=f88（强制，会话开始第一步，2026-08-04 实测）**：
平台左上角「当前身份」是服务端缓存，多身份时前端硬编码默认 afd，导致 f88 任务在个人任务中心显示"暂无数据"（易误判任务不存在）。**任何涉及浏览器 UI 的 F88 测试，先调一次切换接口把默认身份落库为 f88**：
```javascript
fetch('/api/tenant/cacheEmployeeIdentity', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-AFD-Emp-Identity': 'f88' },
  body: JSON.stringify({ tenantId: 'f88' })
}).then(function(r) { return r.json(); }).then(function(d) { document.title = JSON.stringify(d); });
// 返回 data:true 即落库（服务端缓存有数秒传播延迟，勿立即复查误判）
```
验证：刷新页面左上角显示 F88，或 `POST /api/tenant/queryEmployeeIdentityList` 返回 `cachedIdentity:"f88"`。**不要靠 UI 点下拉切换**（自动化不稳）。详见 `审核数据构造` 前置条件#4、`F88测试知识库/infra/api-contracts.md` 租户隔离接口。

#### ⚠️ API 验证铁律（2026-08-18 教训）

**页面 axios 拦截器机制**：前端代码 `m.interceptors.request.use(t => { var e = a.h.getState().tenant.currentIdentity; return e ? {...t, headers: {...t.headers, "X-AFD-Emp-Identity": e}} : t })`。每个请求自动从 Redux store 读取 `tenant.currentIdentity` 并注入 `X-AFD-Emp-Identity` header。

**手动 fetch/XMLHttpRequest 不会经过此拦截器**，不带该 header 时 API 返回默认租户（afd）数据，与 UI 显示的 F88 数据完全不同。曾因此误判生产看板 Bug（UI 显示 278 vs 手动 fetch 返回 78，实际是不同租户数据）。

**验证 API 数据一致性时的正确做法**：
1. **首选**：打开 DevTools Network 面板，查看页面实际 XHR 请求的 Response 体，与 UI 对比
2. **如果必须手动调 API**：必须带上 `X-AFD-Emp-Identity: F88` header，且先确认 API 返回的实体（链路/记录）和 UI 渲染的是同一批，再比数值
3. **禁止**：直接手动 fetch 不带 header 就和 UI 数值对比下结论

#### 数据库

- **DMS 组**：stylespot 生产库（dbId=5335708）— 连接详情/CLI格式/结果路径见 F88测试知识库/references/shared/db-connections.md
- **核心表**：`workflow_record_log`（任务执行日志）、`g_workflow_instance`（工作流实例）、`g_strategy`（策略配置）
- **CLI**：见 shared/db-connections.md 标准调用格式
- **注意**：`status = 'FAIL'`（不是 `FAILED`）、`errorMsg`（不是 `errorMessage`）、大表查询必须加 `id > N`

#### 审核节点速查

| 节点名 | approveNodeId | approveType | 说明 |
|--------|--------------|-------------|------|
| 模板审核 | 138 | 5 | 模板审核 |
| 首图审核 | 168 | 4 | 首图审核（多选多） |
| 套图审核 | 139 | 2 | 套图审核 |
| 视频审核 | 144 | 3 | 视频审核 |

#### 模块负责人

| 模块 | 后端 | 前端 |
|------|------|------|
| 数据对接 / MetaQ | 风荷 | — |
| 模板匹配 | 风荷 | 辰承 |
| LLM 生文 | 风荷 | — |
| 素材写入 | 风荷 | 辰承 |
| 审核平台 | 俨冰 | 辰承 |
| 视频生产 | 风荷 | — |
| 疲劳度/频控 | 风荷 | — |

### 3. 数据构造红线（强制执行）

**所有 F88 测试必须遵守**：

- **禁止复用存量数据**：不得在平台现有数据（jobType 列表、历史审核任务、存量批次等）中搜索"现成样本"作为测试依据。存量状态不可控（可能已被消费/修改/过期/过滤），基于存量数据得出的测试结论不可信。
- **必须全量造新**：需要测试数据时，必须调用造数 skill 构造 fresh 数据。首选 `审核数据构造` 方式一（策略试运行+固定模板，产出真实BT_批次），UI需显示图片时用方式二（手动创建API）。
- **判断标准**：只要你的验证逻辑依赖"平台上已存在某条数据"，就是在复用存量——立刻停止，改为造数。

### 4. 技能路由规则

根据任务性质路由到合适的技能：

```
F88 测试意图
  ├─ 全流程（PRD → 用例 → 执行 → 报告） → hfz-test-workflow
  ├─ 单点验证（测某个功能/接口） → 本技能 + att-start + 按需加载
  ├─ 造数（构造审核任务） → 审核数据构造
  ├─ 失败分析 → f88-failure-analysis
  └─ 浏览器自动化 → att-start + 本技能上下文 + 按需加载
```

## 使用示例

### 示例 1：单点功能测试

用户："帮我测一下首图审核功能"

本技能激活后：
1. 加载 `att-start`（测试会话声明）
2. 加载 `审核数据构造`（需要造数）
3. 注入 F88 上下文（环境、审核节点、数据库）
4. 提醒数据构造红线
5. 引导用户进入测试流程

### 示例 2：浏览器自动化

用户："打开预发环境，帮我审核一个任务"

本技能激活后：
1. 加载 `att-start`（测试会话声明）
2. 注入 F88 上下文（预发 URL、审核节点）
3. 提醒数据构造红线（禁止复用存量，必须先造数）
4. 引导浏览器自动化流程

### 示例 3：接口测试

用户："测一下审核任务创建接口"

本技能激活后：
1. 加载 `att-start`（测试会话声明）
2. 注入 F88 上下文（沙箱 URL、API 路径）
3. 提醒数据构造红线
4. 引导接口测试流程

## 与 hfz-test-workflow 的关系

| 维度 | f88-test-mode（本技能） | hfz-test-workflow |
|------|------------------------|--------|
| **定位** | 轻量级入口，单点测试 | 全流程编排，端到端 |
| **触发** | F88 测试关键词 | 明确要求"全流程"、"从 PRD 开始" |
| **技能加载** | 按需加载 | 10 阶段流水线 |
| **适用场景** | 浏览器自动化、接口测试、单点验证 | PRD → 用例 → 执行 → 报告 → 缺陷提报 |
| **复杂度** | 低 | 高 |

## 架构意义

本技能解决了**技能触发碎片化**的问题：
- 之前：技能靠关键词匹配，F88 测试场景可能漏加载关键技能
- 现在：检测到 F88 测试意图 → 本技能激活 → 自动加载相关技能 → 注入上下文 → 确保数据红线

本技能是 `att-start` 的补充：
- `att-start`：测试会话声明（通用）
- `f88-test-mode`：F88 测试入口（领域专属）

两者结合，确保所有 F88 测试都：
1. 声明了测试身份（att-start）
2. 加载了相关技能（f88-test-mode）
3. 遵守了数据构造红线（两者共同强制）
