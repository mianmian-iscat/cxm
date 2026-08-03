# F88 失败分析

通过 `dms-alibaba` CLI 对 i-FASHION 策略平台的 `workflow_record_log` 等表做 SQL 深度分析，快速定位批次失败根因。

## 功能

- **状态分布总览**：按批次/环节分组统计成功、失败、处理中数量
- **错误信息分类统计**：提取 errorMsg 并按 CASE WHEN 分组，识别主要错误类型
- **策略配置核查**：从 g_strategy.workflow_def 提取模型配置，对比正常/异常策略
- **输出物验证**：ffprobe 视频参数校验、图片可访问性检查
- **时间与策略维度分析**：判断失败是全局性还是特定策略/时间段问题

## 前置依赖

- `dms-alibaba` CLI（访问 stylespot 数据库组）
- Python 3（JSON 解析）
- `ffmpeg` / `ffprobe`（可选，视频输出物校验）

## 包含文件

- `skills/f88-failure-analysis/SKILL.md` — 主技能定义（5 个工作流 + 表结构速查）
- `skills/f88-failure-analysis/references/sql-templates.md` — SQL 查询模板集

## 来源

从本地 qoderwork 插件 `qa-testing-workbench/skills/F88失败分析` 提取并独立发布。
