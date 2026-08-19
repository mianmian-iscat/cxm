# 重复 Skill 合并说明

## 背景

原创保护结算链路分析器原本存在两个高度重复的 Skill 入口：

| Skill | 状态 | 说明 |
|-------|------|------|
| `yc-settlement-analyser` | **保留并维护** | 完整版，包含 `references/` 领域模型与状态机文档 |
| `yc-settlement-analysis` | **已废弃** | 仅保留 SKILL.md 壳，内容与 `yc-settlement-analyser` 早期版本一致 |

重复入口容易导致文档更新不同步、触发词分散，因此从改进方案 Task 5 开始统一收敛到 `yc-settlement-analyser`。

## 迁移指引

所有结算链路分析需求，统一使用：

```
yc-settlement-analyser
```

触发词不变：结算分析、结算链路、资金流向、退款分析、确收分析、补贴分析、settlement analysis、fund flow、结算测试、费用科目、账期规则、结算状态机、下架率分流、退款路径、确收路径、服务完结。

## 对旧入口的处理

- `yc-settlement-analysis` 目录下的 `SKILL.md` 已改为重定向提示，不再输出完整分析流程。
- 如通过旧入口被触发，应提示调用方迁移到 `yc-settlement-analyser`，并继续完成分析任务。

## 关联 Skill

| Skill | 用途 |
|-------|------|
| `yc-data-factory` | HSF 造数 + ScheduleX 触发 |
| `yc-db-verification` | DB 验证 + SQL 模板 |
| `yc-quick-audit-data-create` | 构造快审/初审申请 |

## 变更记录

- 2026-08-19：发布本合并说明，将 `yc-settlement-analysis` 标记为 deprecated。
