<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/features/12-Caption离线同步链路.md -->
<!-- synced-at: 2026-07-21T19:00:02.959615 -->
<!-- skill: F88测试知识库 -->

# Caption 离线同步链路

## 概述

Caption 离线同步链路负责将线上 MySQL 中的 caption 产出数据（`g_afd_caption_output`）每日增量同步至 ODPS 离线表（`taobao_tec_platform.s_g_afd_caption_output_df`），供下游数据分析、模型训练、效果评估使用。

## 架构

```
[Caption 服务] → 写入 MySQL g_afd_caption_output
                         ↓ (每日 T+1)
[AfdCaptionOutputRefreshJob / DataWorks 数据集成] → 增量同步至 ODPS
                         ↓
[taobao_tec_platform.s_g_afd_caption_output_df] (按 ds 分区)
```

## 关键组件

| 组件 | 说明 |
|------|------|
| `g_afd_caption_output` (MySQL) | 线上 caption 结果表，stylespot 库 |
| `AfdCaptionOutputRefreshJob` (SchedulerX) | Caption 输出刷新定时任务 |
| DataWorks 数据集成节点 | MySQL → ODPS 增量同步 |
| `s_g_afd_caption_output_df` (ODPS) | 离线 caption 全量表，按日分区 |

## 数据特征

- 分区键：`ds`（格式 YYYYMMDD）
- 正常情况：每日分区 count 应递增（线上持续有新图刷 caption）
- 异常情况：连续多日 count 不变 → 增量同步中断

## 已知风险点

1. **增量条件失效**：同步 SQL 的 `gmt_modified > T-1` 条件如果上游不再更新该字段，增量查询返回空集，任务"成功"但无新数据
2. **上游写入中断**：Caption 服务停止写入新结果（如模型下线、服务异常），但同步任务不感知
3. **DataWorks 节点暂停/报错**：节点被手动暂停或依赖断裂，但不触发告警
4. **SchedulerX 调度异常**：`AfdCaptionOutputRefreshJob` 未按时执行

## 监控规则

- **R021**（pipeline-monitor）：Caption 离线分区数量停滞检查
  - 连续 3 天 count 不变 → P1 WARNING
  - 连续 5 天 count 不变 → P0 CRITICAL
  - 辅助验证：线上 MySQL 近 3 天是否有新增 caption 记录

## 排查 SOP

1. 查 ODPS 最近 5 个分区 count 是否持平
2. 查线上 `g_afd_caption_output` 近 3 天 `gmt_create` 新增数
3. 若线上有新增但 ODPS 不变 → 同步链路断裂：
   - 检查 DataWorks 数据集成节点最近执行状态
   - 检查 `AfdCaptionOutputRefreshJob` SchedulerX 调度记录
   - 检查同步 SQL 的增量条件是否正确
4. 若线上也无新增 → 上游 Caption 服务问题：
   - 检查 Caption 服务健康状态
   - 检查是否有模型/算法变更导致不再产出

## 关联测试用例

- TC-CAPTION-OFFLINE-001：分区数量递增验证
- TC-CAPTION-OFFLINE-002：增量同步条件有效性
- TC-CAPTION-OFFLINE-003：上游中断感知
- TC-CAPTION-OFFLINE-004：空增量与异常区分
