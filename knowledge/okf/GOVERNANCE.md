# 知识治理规则（OKF Bundle）

> 本文件定义 `knowledge/okf/` 知识库的读写治理规则。

---

## 一、Concept 文件规范

### Frontmatter（每个 concept 文件必须包含）

```yaml
---
title: "概念名称"
type: feature | execution | infra | learning | regression
domain: f88 | op | afd | common
last_updated: "2026-08-03"
related_infra:
  - infra/f88-system-config.md   # 可选：关联的 infra 文件
tags: [审核, 状态机, F88]
---
```

### 文件命名

- 使用中文或有意义的英文短语
- 路径即身份：`features/f88/审核状态机.md`
- 同主题更新：覆盖原文件，更新 `last_updated`

---

## 二、分层写入规则

| 层 | 谁写 | 写什么 | 禁止 |
|----|------|--------|------|
| features/ | 用例设计阶段 / rule-hunter | 业务规则、边界条件、构造前置 | 禁止写执行步骤 |
| execution/ | 执行阶段 / test-executor | UI 验证点、造数约束、断言规则 | 禁止写业务 ID 的 source of truth |
| infra/ | 数据构造阶段 / data-builder | ID 映射、配置、账号、DB 表 | 禁止写业务规则 |
| learnings/ | Phase 4 / 失败分析后 | 踩坑记录、环境问题、修复方案 | 禁止写未验证的猜测 |
| regression/ | 回归阶段 | 基线用例、UI 截图 manifest | 禁止覆盖历史基线 |

---

## 三、知识晋升链

```
执行失败 → badcase_collector 采集
  → failure_classifier 分类（自愈/脚本/真Bug）
  → 提取模式 → 写入 learnings/
  → 下次执行时 Agent 提前规避
```

### 晋升触发条件

| 触发 | 动作 |
|------|------|
| 同一 pattern 失败 ≥ 2 次 | 写入 `learnings/` |
| 新业务规则发现 | 写入 `features/` |
| 新 UI 验证点确认 | 写入 `execution/` |
| 新 ID/配置/表结构 | 写入 `infra/` |

---

## 四、变更日志

所有对 `knowledge/okf/` 的修改必须记录到 [log.md](log.md)：

```markdown
## 2026-08-03
- [新增] features/f88/审核状态机.md — 审核状态枚举与流转规则
- [更新] execution/f88/审核操作验证点.md — 补充驳回必填校验
```

---

## 五、证据分层

检索返回的知识按可信度分层：

| Tier | 说明 | 使用方式 |
|------|------|---------|
| **strong** | 经过 3+ 次执行验证的规则 | 直接作为断言依据 |
| **supporting** | 经过 1-2 次验证 | 参考使用，需结合上下文 |
| **weak** | 仅从文档/代码推断 | 仅作为探索方向 |
