# L1 上下文 — AFD 风格店铺协作

> 当前活跃的 AFD 项目上下文。执行 AFD 相关测试时加载。

## 当前测试范围

- 风格店铺协作平台（店铺列表、迭代详情、Brief）
- 试拍上传与审核
- 买手审核 + Leader 复核
- 视觉归档与基准包

## 关键知识引用

- 业务规则: `knowledge/okf/features/afd/迭代状态机.md`
- 系统配置: `knowledge/okf/infra/f88-system-config.md`（共用 F88 基础设施）

## 活跃风险

- 租户头切换：AFD 使用 `X-AFD-Emp-Identity: afd`
- 迭代状态机 10 个状态，流转路径复杂
- 5 类角色权限矩阵，需按角色分别测试
