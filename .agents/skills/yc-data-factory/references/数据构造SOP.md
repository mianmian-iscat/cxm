# 原创保护测试数据构造 SOP

> 覆盖 6 大主要测试场景的数据准备步骤。每个场景标注前置条件、操作步骤、验证方式和常见坑点。

---

## 场景 1：签约入驻

### 前置条件
- 测试账号 seller_id 已知（默认 2213249110271）
- 千牛标 TTYCBH 已打上（否则入驻会被 BizException 拦截）
- 千牛预发登录态有效（https://pre-fsyc.taobao.com/ 能正常访问）

### 操作步骤

**步骤 1：确认千牛标 TTYCBH**
```
打开 https://qn.alibaba-inc.com/qndev-data-app/management#/
→ 名单管理 → 名单操作=打标 → 上传 sellerId TXT
```
TXT 格式：每行一个纯数字 sellerId，无空格无逗号。

**步骤 2：触发入驻**
- 方式 A（UI）：打开 https://pre-fsyc.taobao.com/ → 点击"签约" → 勾选协议 → 确认
- 方式 B（HSF Tool）：`SellerEnterToolService.enterSeller(sellerId)`

**步骤 3：DB 验证**
```sql
SELECT seller_id, status, gmt_create
FROM seller_enter_info
WHERE seller_id = 2213249110271;
```
预期：status = ENTERED

### 常见坑点
- TTYCBH 未打标 → 入驻失败，提示"该服务面向具备高原创能力要求的商家"
- 千牛登录态过期 → 页面跳转登录，需重新扫码

---

## 场景 2：快审申请（QUICK）

### 前置条件
- 商家已入驻（seller_enter_info.status = ENTERED）
- 快审**不消耗服务次数**，无需充值
- 测试图片 OSS URL 可用

### 操作步骤

**步骤 1：商家端 MTOP 调用**
在千牛预发页面(https://pre-fsyc.taobao.com/)内执行：
```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'QUICK',
    category: '服装',
    productImg: [{ type: '主视图', urls: [ossUrl] }],
    expectedOnshelfDate: '2026-07-15'
  };
  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0', method: 'POST',
      data: { request: JSON.stringify(payload) }
    }, function(res) { resolve('SUCCESS: ' + JSON.stringify(res)); },
    function(err) { resolve('ERROR: ' + JSON.stringify(err)); });
  });
})()
```

**步骤 2：DB 验证**
```sql
SELECT id, status, apply_type, expected_onshelf_date
FROM yc_right_apply
WHERE seller_id = 2213249110271 AND apply_type = 'QUICK'
ORDER BY id DESC LIMIT 3;
```
预期：status = QUICK_AUDITING, apply_type = QUICK

### 常见坑点
- 不可用 raw fetch 调用 MTOP → 返回 FAIL_SYS_ILLEGAL_ACCESS
- productImg type 商家端用中文"主视图"，小二端用英文"main"

---

## 场景 3：初审申请（PRE）

### 前置条件
- 商家已入驻
- **PRE 消耗 1 次/条**，必须先确认剩余次数 ≥ 1
- 剩余次数 = 0 时先走充值流程

### 操作步骤

**步骤 1：确认剩余次数**
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.common.statistics',
  v: '1.0', method: 'GET', data: {}
}, function(res) { console.log('剩余次数:', res.data.remainRightCount); });
```

**步骤 2：次数不足时充值**
1. 打开 https://pre-fsyc.taobao.com/ → 点击"去充值"
2. 服务市场页面"立即订购" → "立即购买" → 勾选协议 → "同意并付款"
3. 进入支付页后**停止**，记录 URL 中的 orderId
4. 调用 order.pay API 获取支付宝链接（详见 yc-quick-audit-data-create Skill）
5. 扫码支付 → 刷新确认次数 +1

**步骤 3：商家端 MTOP 创建 PRE**
```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'PRE',
    category: '服装',
    productName: 'QA测试初审外套',
    productUsage: '用于日常穿着外套',
    remark: '独特的剪裁设计体现现代解构主义风格',
    designers: [{
      name: '测试设计师',
      identityNumber: '330102199001011234',
      nationality: '中国',
      identityPictures: [ossUrl, ossUrl]
    }],
    contacts: [{ name: '测试联系人', phone: '13800138000', address: '', zipCode: '', email: '' }],
    designElements: ['A'],      // ⚠ 必须复数
    designViews: ['A', 'B'],    // ⚠ 必须复数
    productImg: [
      { type: '立体图', urls: [ossUrl] },
      { type: '主视图', urls: [ossUrl] }
    ],
    expectedOnshelfDate: '2026-07-15'
  };
  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0', method: 'POST',
      data: { request: JSON.stringify(payload) }
    }, function(res) { resolve('SUCCESS: ' + JSON.stringify(res)); },
    function(err) { resolve('ERROR: ' + JSON.stringify(err)); });
  });
})()
```

**步骤 4：DB 验证**
```sql
SELECT id, status, apply_type, category, product_name
FROM yc_right_apply
WHERE seller_id = 2213249110271 AND apply_type = 'PRE'
ORDER BY id DESC LIMIT 1;
```
预期：status = PRE_PRE_AUDITING, apply_type = PRE

### 常见坑点
- designElements/designViews 必须用**复数**形式（单数报错"设计元素不能为空"）
- identityNumber（非 idNumber），identityPictures（扁平 URL 数组，非分字段）
- 小二端 cobweb 不支持 PRE，只能通过商家端 MTOP 创建

---

## 场景 4：商品绑定与发布

### 前置条件
- 已有一条状态为 QUICK_AUDITED 或 PRE_PRE_PASS 的申请
- 有待绑定的商品 ID

### 操作步骤

**步骤 1：获取可绑定商品列表**
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.item.page',
  v: '1.0', method: 'GET',
  data: { rightId: '{rightId}', pageNo: 1, pageSize: 10 }
}, function(res) { console.log(JSON.stringify(res.data)); });
```

**步骤 2：绑定商品**
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.binditem',
  v: '1.0', method: 'POST',
  data: { rightId: '{rightId}', itemId: '{itemId}' }
}, function(res) { console.log(JSON.stringify(res)); });
```

**步骤 3：DB 验证**
```sql
SELECT rp.right_id, rp.item_id, rp.gmt_create
FROM yc_right_product rp
WHERE rp.right_id = {rightId};
```
预期：绑定记录已创建

### 常见坑点
- 每个专利仅绑定 1 个商品，一致性确认后不可更换
- 从仓库下架再上架不算"首次上架"
- 到期前 20 天发布按钮置灰（publishItemGray: true）

---

## 场景 5：维权提交

### 前置条件
- 已有一条保护中的专利（yc_right.status = YC_PROTECT_VALID）
- 已绑定商品

### 操作步骤

**步骤 1：手动添加侵权线索**
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.tort.add',
  v: '1.0', method: 'POST',
  data: {
    rightId: '{rightId}',
    platform: '抖音',
    tortUrl: 'https://example.com/suspected-infringement',
    shopName: '疑似侵权店铺',
    shopUrl: 'https://shop.example.com'
  }
}, function(res) { console.log(JSON.stringify(res)); });
```

**步骤 2：提交维权请求**
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.protect.submit',
  v: '1.0', method: 'POST',
  data: {
    rightId: '{rightId}',
    tortRecordIds: ['{tortRecordId}'],
    platform: '抖音'
  }
}, function(res) { console.log(JSON.stringify(res)); });
```

**步骤 3：DB 验证**
```sql
SELECT tr.id, tr.status, tr.platform
FROM tort_record tr
WHERE tr.right_id = {rightId}
ORDER BY tr.id DESC;

SELECT rpr.id, rpr.protect_way, rpr.status
FROM yc_right_protect_record rpr
WHERE rpr.right_id = {rightId};
```

### 常见坑点
- 支持 6 个平台：淘宝/天猫/抖音/小红书/拼多多/京东
- 到期前 20 天维权按钮禁用
- 70% 下架率为服务承诺阈值，影响结算触发

---

## 场景 6：结算与退款

### 前置条件
- 已有一条保护中的专利，且已达成 70% 下架率
- 或已有 PROCESSING 状态的结算单

### 操作步骤

**步骤 1：查询现有结算单**
```bash
# 通过 DMS MCP 查询
SELECT s.id, s.right_apply_id, s.settle_status, s.total_amount,
       s.init_allowance_start_time, s.init_allowance_amount
FROM yc_right_settle_order s
WHERE s.right_apply_id = {applyId};
```

**步骤 2：触发补贴（9 类商家）**
```bash
# HSF Tool（需用户确认）
RightSettleToolHsfService.updateInitAllowanceStartTimeWithApplyId(
  applyId, '2026-06-30 10:00:00'
)
```

**步骤 3：构造退款场景**
```bash
# HSF Tool（需用户确认）
# 1. 先将结算状态改为完结待退款
RightSettleToolHsfService.updateSettleStatus(settleId, 'FINISH_REFUNDING')
# 2. 触发退款
ServiceTradeToolService.triggerRefund(orderId)
```

**步骤 4：DB 验证**
```sql
-- 结算单状态
SELECT id, settle_status FROM yc_right_settle_order WHERE id = {settleId};

-- 退款记录
SELECT id, status, amount FROM refund_apply_order
WHERE settle_order_id = {settleId};

-- 操作流水
SELECT op_type, op_detail, gmt_create
FROM yc_right_apply_op_record
WHERE right_apply_id = {applyId}
ORDER BY gmt_create DESC LIMIT 10;
```

### 常见坑点
- **total_amount ≠ 补贴金额**：total_amount 是基础结算金额，补贴看 init_allowance_start_time
- **必须先设补贴时间再设到期时间**：否则补贴不发
- **退款金额必须全量**：退款金额 = 剩余次数 × 500，不可部分退
- **并发锁**：提交时按商家加锁，选取未关联结算的订阅单

---

## 快速参考

| 场景 | 主要工具 | 消耗权益 | 核心 DB 表 |
|------|---------|---------|-----------|
| 签约入驻 | UI / HSF enterSeller | 否 | seller_enter_info |
| 快审申请 | MTOP (lib.mtop.request) | 否 | yc_right_apply |
| 初审申请 | MTOP (lib.mtop.request) | 是（1次/条） | yc_right_apply |
| 商品绑定 | MTOP binditem | 否 | yc_right_product |
| 维权提交 | MTOP tort.add + protect.submit | 否 | tort_record, yc_right_protect_record |
| 结算退款 | HSF RightSettleTool + ServiceTradeTool | 否 | yc_right_settle_order, refund_apply_order |
