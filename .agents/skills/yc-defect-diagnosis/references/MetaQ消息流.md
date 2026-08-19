# 原创保护-MetaQ消息流

> **[命名映射] ** 本文使用业务语义命名（如 PatentApplySubmitConsumer），后端代码实际监听器类名见 `系统架构与API参考.md` 的 MetaQ 部分。映射关系：
> - 本文每个 Consumer 对应代码中一个 Listener + 特定 Tag 的组合
> - 例：PatentApplySubmitConsumer = RightApplyMessageListener + tag=apply_submit
> - 完整映射表见 `yc-naming-mapping.json`

后端通过 MetaQ 监听上下游事件，是异步链路的核心。排查时若发现"前端操作成功但状态未更新"，优先检查 MetaQ 监听是否正确执行。

## 19个核心 MetaQ 消费者（按业务模块分组）

### 签约模块（2个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| ContractSignConsumer | TOPIC_YC_CONTRACT | sign_success | 签约后区块链存证 |
| ContractRevokeConsumer | TOPIC_YC_CONTRACT | revoke | 解约清理 yc_right 关联 |

### 专利申请模块（4个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| PatentApplySubmitConsumer | TOPIC_YC_PATENT | apply_submit | yc_right_apply 状态 → pending_review |
| PatentApprovalConsumer | TOPIC_YC_PATENT | approval | 状态 → approved + 通知商家 |
| PatentRejectConsumer | TOPIC_YC_PATENT | reject | 状态 → rejected + 触发申诉窗口 |
| PatentExpireWarningConsumer | TOPIC_YC_PATENT | expire_warning | 到期前30天发送续签通知 |

### 商品绑定模块（3个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| ProductBindConsumer | TOPIC_YC_BIND | bind | yc_right_product 写入 + 维权能力上线 |
| ProductUnbindConsumer | TOPIC_YC_BIND | unbind | 维权能力下线 |
| ProductPriceChangeConsumer | TOPIC_YC_PRODUCT | price_change | 监听商品价格变化触发结算金额复算 |

### 维权模块（4个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| TortDetectConsumer | TOPIC_YC_TORT | detect | 监听跨平台爬虫扫描结果 |
| TortApplyConsumer | TOPIC_YC_TORT | apply | 维权申请提交 |
| TortTakedownConsumer | TOPIC_YC_TORT | takedown | 平台下架成功，更新 yc_tort_record |
| TortAppealConsumer | TOPIC_YC_TORT | appeal | 被投诉方申诉 |

### 结算模块（3个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| SettlementCalcConsumer | TOPIC_YC_SETTLE | calc | 70%下架率达成触发结算计算 |
| SettlementApprovalConsumer | TOPIC_YC_SETTLE | approval | 小二审核通过 → 财务系统拨付 |
| SettlementPaymentConsumer | TOPIC_YC_SETTLE | payment | 收到 ERP 拨付确认回调 |

### 首发标签模块（2个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| FirstLaunchTagConsumer | TOPIC_YC_FIRST_LAUNCH | tag | 商品打首发标 |
| FirstLaunchExpireConsumer | TOPIC_YC_FIRST_LAUNCH | expire | 首发标到期摘除 |

### 转正模块（1个）

| Consumer | Topic | Tag | 触发动作 |
|----------|-------|-----|---------|
| ToRegularConsumer | TOPIC_YC_REGULAR | apply | 专利转正申请处理 |

---

## 排查方法

### 1. 确认消息是否生产

DMS 查 metaq_message_log（如有）：
```sql
SELECT * FROM metaq_message_log
WHERE topic = 'TOPIC_YC_PATENT' AND tag = 'apply_submit'
  AND biz_key = '{apply_id}'
ORDER BY gmt_create DESC LIMIT 10;
```

### 2. 确认消息是否消费

查 yc_consume_log（业务表内自维护）或日志平台：
- 鹰眼 traceId 串联：从 MTOP 入口 traceId 一路追到 Consumer
- 关键日志关键字：`Consume success` / `Consume retry` / `Consume failed`

### 3. 重试与死信

- MetaQ 默认重试 16 次（间隔递增 1s/5s/10s/30s/...）
- 死信 Topic 命名：`%DLQ%TOPIC_YC_XXX`
- 死信不会自动重投，需要小二端手动触发

### 4. 监听不可靠的常见原因

参考 F88 经验：
- **Job 状态回调不可靠**：业务表状态正确但同步表未更新（已沉淀MEMORY）
- **Consumer 重复消费**：未做幂等导致 yc_right_settle_order 重复创建
- **Topic Tag 拼写错误**：tag 大小写敏感，常见 `apply_submit` 写成 `applySubmit`

---

## 排查 SQL 模板

### 消息丢失类问题
```sql
-- 业务方有动作但未触发MetaQ消费
SELECT a.id, a.gmt_create, a.status, l.consume_status
FROM yc_right_apply a
LEFT JOIN yc_consume_log l ON l.biz_key = CAST(a.id AS CHAR)
WHERE a.gmt_create > '2026-06-15'
  AND l.id IS NULL;
```

### 消费失败类问题
```sql
SELECT * FROM yc_consume_log
WHERE consume_status = 'FAIL'
  AND topic = 'TOPIC_YC_SETTLE'
ORDER BY gmt_create DESC LIMIT 100;
```
