---
name: yc-settlement-analysis
description: 【已废弃】请使用 yc-settlement-analyser。本 Skill 仅保留重定向提示，不再维护完整分析流程。
version: 1.0.0-deprecated
---

# ⚠️ 该 Skill 已废弃

`yc-settlement-analysis` 已停止维护，其完整能力已合并到：

```
yc-settlement-analyser
```

## 请迁移到新入口

所有原创保护结算链路分析需求，请直接调用 `yc-settlement-analyser`。

触发词示例：结算分析、结算链路、资金流向、退款分析、确收分析、补贴分析、settlement analysis、fund flow、结算测试、费用科目、账期规则、结算状态机、下架率分流、退款路径、确收路径、服务完结。

## 为什么合并

- 两个 Skill 内容高度重复，维护时容易双写遗漏。
- `yc-settlement-analyser` 包含完整的 `references/` 领域模型（资金流向、费用科目、状态机），是当前唯一维护版本。

## 迁移记录

详见 `yc-settlement-analyser/references/deprecation-notice.md`。
