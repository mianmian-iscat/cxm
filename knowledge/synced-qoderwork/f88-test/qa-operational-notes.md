<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/qa-operational-notes.md -->
<!-- synced-at: 2026-07-11T03:52:35.004070 -->
<!-- skill: F88测试知识库 -->

---
id: qa-operational-notes
title: F88 QA 实战操作要点
tags: [QA, 实战经验, 操作要点, 踩坑]
owner: QA
version: 1.0.0
created: 2026-07-09
updated: 2026-07-09
source_sessions: []
promotion_count: 0
---

# F88 QA 实战操作要点

> 从测试会话中沉淀的实操经验，覆盖 API 踩坑、自动化陷阱、数据构造等场景。

## createTask API 关键字段

- **taskMode 枚举**：NONE / REVIEW_ONLY / WASH_AND_REVIEW
- **审核策略字段名**：`reviewStrategyId`（非 auditNodeId），值从 `getReviewStrategyList` 获取
- **queryTemplatesByConditions**：须传 `mode="single"` 否则返回空结果
- **washStatus**：1=已洗图，0=未洗图
- **triggerApprove 推送审核**：`POST /api/workflow/batch/triggerApprove {batchId, nodeIds}`

## 洗图验证要点

- **策略**：biz_scene='策略平台' + strategyName='风荷测试洗图策略'(id=10577)
- **批次配对**：生产 BT_N → 审核 BT_N+1
- **washStatus 未落库**（GAP-004）：staging 全库无 washStatus/wash_status/is_wash 字段
- **验证起点**：应从策略平台任务创建开始，现有 skill 未覆盖此 UI 流程

## 审核策略成员陷阱

- 策略"风荷测试审核策略"(10578)仅风荷为成员时，创建审核任务子任务(job_type=4)自动分配给风荷
- **update API 只能改主任务**(job_type=0)，inspection/judge 对非分配人返回 data=false
- **解法**：先改策略成员再加目标人员

## i-FASHION 策略平台自动化要点

- **节点配置"双层保存"**：先抽屉内保存（校验节点表单），再页面保存（校验策略入参一致性）
- **抽屉打开**：accessibility tree 不显示 drawer，需用 JS `editIcon.closest('button').dispatchEvent(new MouseEvent('click',{bubbles:true}))` 触发
- **Ant Design Select**：用 mousedown 事件开下拉、.click() 选选项
- **试运行 API**：`POST /api/workflow2/strategy/run {strategyId, runType:'SINGLE', inputData:{...}}` → 返回 batchId
- **导出 API**：`/api/template/package/export` fetch 返回 HTML 而非 Excel，需 UI 点击触发浏览器下载
- **模板匹配第三模式**："复用上游"

## 优质模板库 CDP 注意

- 页面 reload 后身份可能切回 G 项目，需重新点 F88 logo 切回
- "查看任务进度"按钮无实际 API 调用（未实现）
- 模板数据通过 React Fiber f88Card 组件的 props.data 读取
- goutuTags 验证：React Fiber 提取卡片数据 → `__reactFiber$key` → return.memoizedProps.data，字段含 goutuTags/goutuZeyou/goutuQulie/washStatus

## AOne F88 缺陷创建（项目 2120437）

- 用 `--category bug`（`--type "大淘宝缺陷模版"` 偶发 "workitem init returned no result"）
- **必填 cfs 用 fieldIdentifier 数字 ID**：`--cfs "141538=81969803"`（关联需求）、`--cfs "47=测试阶段"`（发现阶段）
- 长描述用 `--body-file` 而非 `--body`/`--description`；severity 用数字 ID
