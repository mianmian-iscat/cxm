# 知识库索引（OKF Bundle）

> `knowledge/okf/` 是按消费方分层的结构化知识库。
> 每个 concept 一个 markdown 文件，**文件路径即 concept 身份**。
> 执行阶段按角色渐进式披露，不全量加载。

---

## 架构原则

| 原则 | 说明 |
|------|------|
| **权威源 / 派生视图分离** | `knowledge/okf/*.md` = 权威源（可 diff、可审计）；`knowledge/index.json` = URL 路由派生视图 |
| **按消费方分层** | features → 用例设计阶段；execution → 执行阶段；infra → 数据构造阶段；learnings → 全阶段 |
| **路径 = 身份** | `features/f88/审核状态机.md` 就是唯一身份，不依赖额外 ID |

---

## 分层导航

| 目录 | 职责 | 消费方 | 规模 |
|------|------|--------|------|
| [features/](features/) | 业务规则：测什么、边界、构造前置 | 用例设计、rule-hunter | 按域分目录 |
| [execution/](execution/) | 执行知识：UI 验证点、造数约束、断言规则 | test-executor、data-builder | 按域分目录 |
| [infra/](infra/) | 工程注册表：ID、配置、账号、维表、DB | data-builder、verifier | flat 文件 |
| [learnings/](learnings/) | 历史教训：执行踩坑、造数陷阱、环境问题 | 全阶段 | 按时间 |
| [regression/](regression/) | 回归基线、UI ref、前台 taxonomy | 回归阶段 | 按域 |

---

## Agent 读取规则

1. 先读当前目录 `index.md`（本文件）— 渐进式披露
2. 按任务打开对应层的 **concept 文件**（一文件一 concept）
3. 同主题多 concept → 优先 `last_updated` 较新
4. 关键结论引用 **来源路径** `knowledge/okf/<路径>`
5. 改 bundle → 同步 `log.md`

### 按角色速查

| 角色 / 阶段 | 先读 | 再读 |
|-------------|------|------|
| 用例设计 | [features/](features/) 域匹配 | [execution/](execution/) 验证点 |
| 数据构造 | [execution/](execution/) 造数约束 | [infra/](infra/) 账号/配置/维表 |
| UI 执行 | [execution/](execution/) UI 验证清单 | [features/](features/) 业务规则 |
| DB/SLS 验证 | [infra/](infra/) DB 表结构 | [execution/](execution/) 断言规则 |
| 回归测试 | [regression/](regression/) 基线用例 | [learnings/](learnings/) 历史教训 |

---

## 与现有知识的关系

| 层 | 路径 | 说明 |
|----|------|------|
| URL 路由 | `knowledge/index.json` | 页面级知识（按 URL 匹配），保持不变 |
| 页面知识 | `knowledge/<domain>/*.json` | 页面结构详情，被 index.json 引用 |
| 同步知识 | `knowledge/synced-qoderwork/` | 从 qoderwork 同步的原始文档 |
| **OKF Bundle** | **`knowledge/okf/`** | **按消费方分层的结构化知识（本次新增）** |
| Harness 知识 | `harness/knowledge/` | 引擎内部使用的 JSON 知识（features/infra/patterns） |

> OKF Bundle 与 `harness/knowledge/` 互补：harness 侧是机器可读的 JSON，OKF 侧是人+Agent 可读的 Markdown。
