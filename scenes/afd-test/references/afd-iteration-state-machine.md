# AFD 迭代状态机规则

> 视觉迭代的 10 态完整流转定义，含转换矩阵、Guard 条件和 Side Effects。

## 状态定义

| 状态 | 含义 | 处理角色 | 可执行操作 |
|------|------|---------|-----------|
| DRAFT_BRIEF | Brief草稿中 | 买手 | 保存/提交 |
| PENDING_BRIEF | 待产运确认 | 产运 | 确认/驳回 |
| REJECTED_BRIEF | Brief被驳回 | 买手 | 重新编辑(fork新版本)/提交 |
| IN_PRODUCTION | 产运上传试拍中 | 产运 | 上传/导入/发起评审 |
| IN_REVIEW | 买手审核中 | 买手 | 逐组审核/弃用/提交结论 |
| PENDING_LEADER | Leader复核 | Leader | 确认通过/确认驳回/打回买手 |
| RETURNED_TO_BUYER | Leader打回买手 | 买手 | 重新调整/提交 |
| RETURNED | Leader确认驳回 | 产运 | 补充上传/重新发起评审 |
| ARCHIVED | 已归档(终态) | 无 | 只读查看 |
| CANCELLED | 已终止(终态) | 无 | 只读查看 |

## 合法转换矩阵

| 从＼到 | DRAFT | PENDING_BRIEF | REJECTED | IN_PROD | IN_REVIEW | PENDING_LDR | RT_BUYER | RETURNED | ARCHIVED | CANCELLED |
|--------|-------|---------------|----------|---------|-----------|-------------|----------|----------|----------|-----------|
| DRAFT_BRIEF | - | ✓ | - | - | - | - | - | - | - | - |
| PENDING_BRIEF | - | - | ✓ | ✓ | - | - | - | - | - | - |
| REJECTED_BRIEF | - | ✓ | - | - | - | - | - | - | - | - |
| IN_PRODUCTION | - | - | - | - | ✓ | - | - | - | - | - |
| IN_REVIEW | - | - | - | - | - | ✓ | - | - | - | - |
| PENDING_LEADER | - | - | - | - | - | - | ✓ | ✓ | ✓ | - |
| RETURNED_TO_BUYER | - | - | - | - | - | ✓ | - | - | - | - |
| RETURNED | - | - | - | - | ✓ | - | - | - | - | - |
| ARCHIVED | - | - | - | - | - | - | - | - | - | - |
| CANCELLED | - | - | - | - | - | - | - | - | - | - |

> 非 ARCHIVED/CANCELLED 状态均可转换为 CANCELLED（终止操作）。

## Guard 条件

| 转换 | Guard |
|------|-------|
| → PENDING_BRIEF | Brief必填字段校验通过 |
| → IN_PRODUCTION | 产运确认Brief |
| → REJECTED_BRIEF | 产运驳回，弹窗填写驳回原因 |
| → IN_REVIEW | 试拍最小集校验通过（≥5组达标） |
| → PENDING_LEADER | 买手提交审核结论 |
| → ARCHIVED | Leader确认通过 |
| → RETURNED_TO_BUYER | Leader打回，填写调整意见(10-500字) |
| → RETURNED | Leader确认驳回 |
| → CANCELLED | 权限校验通过 + 终止原因必填 |

## Side Effects

| 转换 | Side Effects |
|------|-------------|
| → ARCHIVED | 生成视觉基准包，标记为"应用中" |
| → CANCELLED | 释放店铺迭代名额，允许创建新迭代 |
| PENDING_BRIEF → REJECTED_BRIEF | 买手侧出现"重新编辑Brief"按钮，fork新版本 |
| RETURNED → IN_REVIEW | 试拍版本号追加（v2/v3），合并图池 |

## 终态规则

- ARCHIVED 和 CANCELLED 为终态，不允许任何状态变更操作
- 终态页面只读展示，底部操作栏隐藏
- 终止后店铺可在列表页重新"新增视觉"，从 DRAFT_BRIEF 开始
- 归档后基准包自动标记为"当前应用"，可手动切换到历史基准包

## 测试要点

1. 验证每个合法转换能正确触发状态变更
2. 验证非法转换（如 ARCHIVED → DRAFT_BRIEF）被阻止
3. 验证 Guard 条件未满足时操作被拒绝（如最小集未达标时发起评审）
4. 验证 Side Effects 正确执行（如归档时基准包生成）
5. 验证终态页面只读（无操作按钮）
6. 验证终止后名额释放（可创建新迭代）
