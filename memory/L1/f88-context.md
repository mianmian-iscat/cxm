# L1 上下文 — F88 素材生产与审核

> 当前活跃的 F88 项目上下文。执行 F88 相关测试时加载。

## 当前测试范围

- F88 审核管理模块（个人任务中心、审核标准、任务管理）
- F88 策略平台（策略配置、批次管理、模板匹配）
- F88 素材生产链路（17 种节点类型）

## 关键知识引用

- 业务规则: `knowledge/okf/features/f88/审核状态机.md`
- 执行验证: `knowledge/okf/execution/f88/审核操作验证点.md`
- 系统配置: `knowledge/okf/infra/f88-system-config.md`
- 踩坑记录: `knowledge/okf/learnings/cdp-connection-pitfalls.md`

## 活跃风险

- 审核驳回按钮 disabled 校验容易遗漏
- CDP 连接在 SPA 路由切换时可能超时
- 租户头 `X-AFD-Emp-Identity` 必须正确设置
