# 原创保护-ScheduleX定时任务清单

> **[命名映射]** 本文使用业务语义命名（如 PatentExpireScanJob），后端代码实际 @JobHandler 类名见 `系统架构与API参考.md` 的 ScheduleX 部分。主要映射：
> - PatentExpireScanJob → RightProtectExpiredJob
> - SettlementCalcJob → ServFinishIncomeJob（已知问题与踩坑.md 中也引用了 SettlementCalcJob，等同于此）
> - SubsidyAuditJob → InitAllowanceRefundJob
> - FirstLaunchExpireJob / TortDetectJob / ContractRenewalReminderJob → 代码清单中无对应项（可能为外部系统调度或合并处理）
> - 完整映射表见 `yc-naming-mapping.json`

后端 6 个定时任务，是慢同步链路。排查"延时类"问题（如到期未摘标、补贴未拨付）须先看任务执行历史。

## 6 个核心定时任务

### 1. PatentExpireScanJob

- **频率**：每天 00:30
- **作用**：扫描 yc_right_apply.expire_time，到期前 30 天发出续签通知
- **关键表**：yc_right_apply, yc_notify_record
- **测试要点**：
  - 边界日：到期前 30 天 00:00:00 是否被扫到
  - 续签后 expire_time 更新，下次扫描应忽略
  - 失败重试 3 次后写入 yc_job_failed_log

### 2. SettlementCalcJob

- **频率**：每天 02:00
- **作用**：扫描达成 70% 下架率的维权记录，计算结算金额并创建 yc_right_settle_order
- **关键表**：yc_tort_record, yc_right_settle_order
- **测试要点**：
  - 70% 阈值精确比较（69.99% 不应触发）
  - 重复扫描幂等（同一个 right_id 不应创建多个 settle_order）
  - 跨平台维权数据汇总（6个平台的下架率合并计算）

### 3. FirstLaunchExpireJob

- **频率**：每天 03:00
- **作用**：扫描首发标到期商品，调用商品中台摘除标签
- **关键表**：yc_right_apply（first_launch_expire_time 字段）
- **测试要点**：
  - 5种时间组合的到期判断（已沉淀知识库）
  - T+3/T+4 编辑窗口期内不应摘除
  - 摘标失败回滚事务

### 4. TortDetectJob

- **频率**：每天 04:00
- **作用**：触发跨平台爬虫扫描，结果写入 yc_tort_detect_record
- **关键表**：yc_tort_detect_record, yc_right_product
- **测试要点**：
  - 6 个平台覆盖（淘宝/天猫/拼多多/抖音/小红书/京东）
  - 爬虫超时不应阻塞其他平台
  - 误报过滤规则（如关联商家自有店铺）

### 5. SubsidyAuditJob

- **频率**：每天 09:00
- **作用**：审核昨日产生的补贴申请，符合规则自动通过
- **关键表**：yc_subsidy_apply
- **测试要点**：
  - 首发判断（302 vs 202 档位）
  - 官费扣减（首发不扣 165，非首发扣）
  - 黑名单商家自动驳回

### 6. ContractRenewalReminderJob

- **频率**：每周一 10:00
- **作用**：发送签约即将到期的提醒（短信 + 站内信）
- **关键表**：yc_contract, yc_notify_record
- **测试要点**：
  - 频次去重（同一商家一周不重复发）
  - 通知失败降级（短信失败走站内信）

---

## 任务运行查看

### 通过 a1 repo 查找配置
```bash
a1 repo file search --repo taobao-yc-serverless --keyword "ScheduleX"
a1 repo file search --repo taobao-yc-serverless --keyword "@JobHandler"
```

### 通过日志查看

ScheduleX 控制台：scx.alibaba-inc.com（搜索任务名 → 查看运行历史）

关键字段：
- `executeStatus`：SUCCESS / FAIL / TIMEOUT
- `executeTime`：实际执行耗时
- `errorMsg`：失败原因

### 手动触发

仅预发环境支持手动触发（生产需走变更）：
```
ScheduleX 控制台 → 选择任务 → 点击"立即触发" → 选择参数（dataTime / shardingItems）
```

---

## 排查 SQL 模板

### 任务漏跑类问题
```sql
-- 检查最近7天是否有缺失
SELECT DATE(gmt_create) as run_date, COUNT(*) as exec_count
FROM yc_job_execute_log
WHERE job_name = 'SettlementCalcJob'
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(gmt_create)
ORDER BY run_date DESC;
```

### 任务执行慢
```sql
SELECT job_name, AVG(cost_ms), MAX(cost_ms)
FROM yc_job_execute_log
WHERE gmt_create > DATE_SUB(NOW(), INTERVAL 1 DAY)
GROUP BY job_name
ORDER BY MAX(cost_ms) DESC;
```

### 任务结果异常
```sql
-- 比对任务输入输出（应处理数 vs 实际处理数）
SELECT job_name, expected_count, actual_count, error_count
FROM yc_job_execute_log
WHERE gmt_create > DATE_SUB(NOW(), INTERVAL 1 DAY)
  AND (expected_count != actual_count OR error_count > 0);
```

---

## 时序敏感测试场景

| 场景 | 触发时机 | 测试方法 |
|------|---------|---------|
| 到期当天续签 | 00:30 任务前完成续签 | 设置 expire_time = 今日，凌晨前调用续签接口 |
| 70% 阈值刚达成 | 02:00 前最后一笔维权完成 | 控制 yc_tort_record 数量在 69.x% → 70.0% |
| 首发标到期边界 | 03:00 任务前 1 分钟在 T+3 编辑窗口内 | HSF Tool 设置 first_launch_expire_time |
| 跨日补贴 | 09:00 前一晚提交申请 | 验证 23:59 提交是否被次日 09:00 任务扫到 |
