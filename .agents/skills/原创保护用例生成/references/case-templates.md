# 原创保护用例模板示例

> 本文件提供 3 个核心场景的完整用例示例，作为 `原创保护用例生成` 的参考模板。实际生成时，应根据具体需求调整字段、状态和断言。

---

## 场景 1：快审通过 → 商品绑定 → 首发标 → 补贴发放

### 用例编号
YC-S01-001

### 用例标题
9 类商家快审通过后绑定商品并触发首发补贴

### 前置条件
- 测试商家 seller_id = 2213249110271 已打标 TTYCBH
- 商家主营类目 ∈ 9 类白名单
- 测试环境为预发（staging）

### 四段式用例

| 阶段 | 步骤 | 预期结果 |
|------|------|---------|
| 操作 | 1. 调用 MTOP 创建 QUICK 申请 | 返回 applyId，状态为 QUICK_AUDITING |
| 操作 | 2. HSF RightApplyToolHsfService.updateStatus(applyId, "QUICK_AUDITED") | HSF 返回 success |
| 即时验证 | 3. 查询 yc_right_apply.status | status = QUICK_AUDITED |
| 即时验证 | 4. 查询 yc_right_apply_op_record | 存在 QUICK_AUDIT_AGREE 流水 |
| 操作 | 5. MTOP 绑定商品 itemId = 12345 | 绑定成功 |
| 等待 | 6. 等待 SYNC_CERT_FILE 完成 | 最长 120 秒 |
| 阶段验证 | 7. 查询 yc_right.first_publish | first_publish = 1（首发标已打） |
| 阶段验证 | 8. 查询 yc_right_settle_order | settle_status = PROCESSING，init_allowance_start_time 有值 |
| 阶段验证 | 9. 查询 yc_service_trade_record | 存在补贴发放记录，金额 = init_allowance_amount |

### pytest 脚本片段

```python
def test_yc_s01_001_quick_first_publish_allowance(self, seller_id):
    apply_id = create_quick_apply(seller_id)
    hsf_update_status(apply_id, "QUICK_AUDITED")
    assert get_apply_status(apply_id) == "QUICK_AUDITED"
    assert op_record_exists(apply_id, "QUICK_AUDIT_AGREE")

    bind_item(apply_id, item_id=12345)
    wait_for_sync_cert_file(apply_id, timeout=120)

    right = get_right_by_apply(apply_id)
    assert right["first_publish"] == 1
    settle = get_settle_order(apply_id)
    assert settle["settle_status"] == "PROCESSING"
    assert settle["init_allowance_start_time"] is not None
    assert trade_record_exists(seller_id, trade_type="ALLOWANCE")
```

### att-tf cases.json

```json
{
  "caseTitle": "YC-S01-001 9类商家快审通过后绑定商品并触发首发补贴",
  "description": "验证快审通过后绑定商品可正确打首发标并触发9类商家补贴",
  "status": 1,
  "priority": "P0",
  "groupPath": "原创保护/快审/补贴发放",
  "errorMessage": "",
  "execLog": "applyId={applyId}, first_publish=1, allowance_amount={amount}"
}
```

---

## 场景 2：保护到期 → 下架率分流 → 退款 / 确收

### 用例编号
YC-S02-001

### 用例标题
保护到期且下架率 < 70% 时触发服务完结退款

### 前置条件
- 存在已发证并在保护期的申请（status = YC_PROTECTING）
- 已构造侵权记录，下架率 < 70%
- 结算单状态为 PROCESSING

### 四段式用例

| 阶段 | 步骤 | 预期结果 |
|------|------|---------|
| 操作 | 1. HSF 修改 protect_expire_time 为昨天 | updateProtectExpiredTime 成功 |
| 即时验证 | 2. 查询 yc_right.protect_expire_time | 已更新为过期时间 |
| 操作 | 3. 触发 ScheduleX Task 399576024（专利保护定时失效） | 任务执行成功 |
| 等待 | 4. 等待 Job 扫描完成 | 最长 60 秒 |
| 阶段验证 | 5. 查询 yc_right.status | status = YC_PROTECT_INVALID |
| 阶段验证 | 6. 查询 yc_right_settle_order | serv_finish_refund_status = TO_DO |
| 操作 | 7. 触发 ScheduleX Task 719211870（服务完结退款） | 任务执行成功 |
| 等待 | 8. 等待退款处理 + 支付回调 | 最长 180 秒 |
| 阶段验证 | 9. 查询 yc_right_settle_order | serv_finish_refund_status = FINISH |
| 阶段验证 | 10. 查询退款流水 | 退款金额等于非首发 33 元 / 首发 133 元 |

### pytest 脚本片段

```python
def test_yc_s02_001_expire_refund_low_takedown(self, apply_id):
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    hsf_update_protect_expired_time(apply_id, yesterday)
    assert get_right_expire_time(apply_id) < datetime.now()

    trigger_schedulerx_job(399576024)
    wait_for_status(apply_id, "right_status", "YC_PROTECT_INVALID", timeout=60)

    settle = get_settle_order(apply_id)
    assert settle["serv_finish_refund_status"] == "TO_DO"

    trigger_schedulerx_job(719211870)
    wait_for_status(apply_id, "serv_finish_refund_status", "FINISH", timeout=180)

    refund = get_refund_record(apply_id)
    first_publish = get_first_publish(apply_id)
    expected = 133 if first_publish else 33
    assert refund["amount"] == expected
```

### 用例编号
YC-S02-002

### 用例标题
保护到期且下架率 ≥ 70% 时触发服务完结确收

### 关键差异
- 触发 Task 721504806（服务完结确认收）
- 预期 `serv_finish_income_status` 流转为 FINISH
- 付供应商 335 元，退商家 0 元

---

## 场景 3：初审驳回 → 申诉/重新提交

### 用例编号
YC-S03-001

### 用例标题
PRE 初审驳回后商家重新提交并成功通过

### 前置条件
- 测试商家已充值 PRE 服务次数
- 商家主营类目 ∉ 9 类白名单（使用普通路径）

### 四段式用例

| 阶段 | 步骤 | 预期结果 |
|------|------|---------|
| 操作 | 1. MTOP 提交 PRE 申请 | 返回 applyId，状态为 PRE_AUDITING |
| 即时验证 | 2. 查询 yc_seller_right_statistics | used_count + 1，remain_count - 1 |
| 操作 | 3. HSF 模拟初审驳回 | updateStatus(applyId, "PRE_AUDIT_REJECT") |
| 即时验证 | 4. 查询 yc_right_apply.status | status = PRE_AUDIT_REJECT |
| 即时验证 | 5. 查询申诉入口 | 商家端展示申诉/重新提交按钮 |
| 操作 | 6. 商家补充材料后重新提交 | 重新进入 PRE_AUDITING |
| 等待 | 7. 等待初审完成 | 最长 60 秒 |
| 阶段验证 | 8. 查询 yc_right_apply.status | status = PRE_AUDITED |
| 阶段验证 | 9. 查询操作流水 | 存在 REJECT 和 RE_SUBMIT 记录 |

### pytest 脚本片段

```python
def test_yc_s03_001_pre_reject_and_resubmit(self, seller_id):
    stats_before = get_seller_right_stats(seller_id)
    apply_id = create_pre_apply(seller_id)
    assert get_apply_status(apply_id) == "PRE_AUDITING"

    stats_after = get_seller_right_stats(seller_id)
    assert stats_after["used_count"] == stats_before["used_count"] + 1

    hsf_update_status(apply_id, "PRE_AUDIT_REJECT")
    assert get_apply_status(apply_id) == "PRE_AUDIT_REJECT"
    assert appeal_entry_visible(apply_id)

    resubmit_pre_apply(apply_id)
    wait_for_status(apply_id, "apply_status", "PRE_AUDITED", timeout=60)
    assert op_record_exists(apply_id, "RE_SUBMIT")
    assert op_record_exists(apply_id, "PRE_AUDIT_PASS")
```

---

## 自检清单应用示例

以 YC-S02-001 为例逐项核对：

- [x] **waiting**：明确等待 Task 399576024 扫描（60s）+ Task 719211870 退款处理（180s）
- [x] **bloodline**：applyId 由场景 1 的绑定商品数据构造，rightId 通过 applyId JOIN 传递，结算单由 Job 自动创建
- [x] **triple-check**：即时验证 protect_expire_time → 阶段验证 right_status + settle_status → 退款流水金额
- [x] **immediate verification**：修改到期时间后立即查询 yc_right.protect_expire_time
- [x] **domain coverage**：覆盖保护期、维权（下架率）、结算/退款
- [x] **state machine**：YC_PROTECTING → YC_PROTECT_INVALID → FINISH_REFUNDING → FINISH
- [x] **settlement branch**：退款路径覆盖，确收路径由 YC-S02-002 覆盖
- [x] **env isolation**：脚本使用 staging 数据，HSF 写操作前执行 env 预检
