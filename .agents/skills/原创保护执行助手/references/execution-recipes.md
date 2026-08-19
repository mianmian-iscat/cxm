# 原创保护执行助手 — 操作菜谱

> 本文件汇总原创保护测试执行中的具体命令模板。执行前务必先完成 `SKILL.md` 中的 env 预检。

---

## 一、MTOP API 菜谱

### 1.1 创建快审(QUICK)申请

```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'QUICK',
    category: '服装',
    productImg: [{type: '主视图', urls: [ossUrl]}],
    expectedOnshelfDate: '2026-08-20'
  };
  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0',
      method: 'POST',
      data: {request: JSON.stringify(payload)}
    }, function(res) { resolve('SUCCESS: ' + JSON.stringify(res)); },
       function(err) { resolve('ERROR: ' + JSON.stringify(err)); });
  });
})()
```

**断言**：`ret[0]` 包含 `SUCCESS::调用成功`；DB 出现 `status='QUICK_AUDITING'` 新记录。

### 1.2 创建初审(PRE)申请

```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'PRE',
    category: '服装',
    productName: 'QA测试初审外套A',
    productUsage: '用于日常穿着外套',
    remark: '独特的剪裁设计结合经典元素',
    designers: [{
      name: '测试设计师A',
      identityNumber: '330102199001011234',
      nationality: '中国',
      identityPictures: [ossUrl, ossUrl]
    }],
    contacts: [{name: '测试联系人', address: '', zipCode: '', phone: '13800138000', email: ''}],
    designElements: ['A'],
    designViews: ['A', 'B'],
    productImg: [
      {type: '立体图', urls: [ossUrl]},
      {type: '主视图', urls: [ossUrl]}
    ],
    expectedOnshelfDate: '2026-08-20'
  };
  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0',
      method: 'POST',
      data: {request: JSON.stringify(payload)}
    }, function(res) { resolve('SUCCESS: ' + JSON.stringify(res)); },
       function(err) { resolve('ERROR: ' + JSON.stringify(err)); });
  });
})()
```

**断言**：`data.result` 为申请编号；DB 新记录 `status='PRE_AUDITING'`、`apply_type='PRE'`。

### 1.3 查询剩余服务次数

```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.common.statistics',
  v: '1.0',
  method: 'GET',
  data: {}
}, function(res) { console.log('remainRightCount:', res.data.remainRightCount); });
```

### 1.4 获取支付链接（PRE 充值）

```javascript
window.lib.mtop.request({
  api: 'mtop.alibaba.topservice.order.pay',
  v: '1.0',
  method: 'POST',
  data: {
    orderId: '{orderId}',
    payType: 'aliPay',
    callBackUrl: '//pre-fuwu.taobao.com/serv/new_order_callback.htm'
  }
}, function(res) { console.log(JSON.stringify(res)); });
```

---

## 二、HSF Tool 菜谱（mw CLI）

### 2.1 通用命令模板

```bash
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.<ServiceName>:1.0.0" \
  --method "<method>~<参数类型1>;<参数类型2>" \
  --args '[<arg1>, "<arg2>"]' \
  --app taobao-yc-serverless --unit pre
```

> `List<Long>` 类型参数必须用双括号 `[[id1, id2]]`。

### 2.2 模拟审核通过

```bash
# QUICK 快审通过
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[{applyId}, "QUICK_AUDITED"]' \
  --app taobao-yc-serverless --unit pre

# PRE 初审通过
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[{applyId}, "PRE_AUDITED"]' \
  --app taobao-yc-serverless --unit pre
```

### 2.3 模拟审核驳回

```bash
# QUICK 驳回
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[{applyId}, "QUICK_REJECT"]' \
  --app taobao-yc-serverless --unit pre

# PRE 初审驳回
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[{applyId}, "PRE_AUDIT_REJECT"]' \
  --app taobao-yc-serverless --unit pre
```

### 2.4 绑定商品

```bash
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightToolHsfService:1.0.0" \
  --method "bindItem~java.lang.Long;java.lang.Long;java.lang.Boolean" \
  --args '[{rightId}, {itemId}, true]' \
  --app taobao-yc-serverless --unit pre
```

### 2.5 触发补贴

```bash
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightSettleToolHsfService:1.0.0" \
  --method "updateInitAllowanceStartTimeWithApplyId~java.lang.Long;java.util.Date" \
  --args '[{applyId}, "2026-08-20 00:00:00"]' \
  --app taobao-yc-serverless --unit pre
```

### 2.6 触发退款

```bash
# 方式A：直接触发退款
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.ServiceTradeToolService:1.0.0" \
  --method "startRefund~java.lang.Long;java.lang.String;java.lang.Long" \
  --args '[{orderId}, "REFUND_REASON", {sellerId}]' \
  --app taobao-yc-serverless --unit pre

# 方式B：先构造完结待退款状态，再触发
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightSettleToolHsfService:1.0.0" \
  --method "updateStatus~java.lang.Long;java.lang.String" \
  --args '[{settleOrderId}, "FINISH_REFUNDING"]' \
  --app taobao-yc-serverless --unit pre
```

### 2.7 修改保护到期时间（构造到期场景）

```bash
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" \
  --method "updateProtectExpiredTime~java.lang.Long;java.util.Date" \
  --args '[{applyId}, "2026-08-01"]' \
  --app taobao-yc-serverless --unit pre
```

### 2.8 商家入驻

```bash
mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.SellerEnterToolService:1.0.0" \
  --method "enter~java.lang.Long" \
  --args '[{sellerId}]' \
  --app taobao-yc-serverless --unit pre
```

---

## 三、DB 验证 SQL 模板

### 3.1 申请状态

```sql
SELECT id, status, apply_type, env, gmt_modified
FROM yc_right_apply
WHERE id = {applyId} AND env = 'staging';
```

### 3.2 权益状态

```sql
SELECT id, status, protect_expire_time, init_allowance_start_time
FROM yc_right
WHERE right_apply_id = {applyId} AND env = 'staging';
```

### 3.3 商品绑定

```sql
SELECT id, item_id, status
FROM yc_right_product
WHERE right_id = {rightId};
```

### 3.4 结算单状态

```sql
SELECT id, settle_status, total_amount, init_allowance_start_time,
       serv_finish_refund_status, serv_finish_income_status
FROM yc_right_settle_order
WHERE right_apply_id = {applyId} AND env = 'staging';
```

### 3.5 操作流水

```sql
SELECT operate_type, operator_name, operate_time, extra_info
FROM yc_right_apply_op_record
WHERE right_apply_id = {applyId}
ORDER BY operate_time DESC LIMIT 5;
```

### 3.6 dms-alibaba CLI 示例

```bash
dms-alibaba sql run scenario --db prod \
  --sql "SELECT id, status, apply_type FROM yc_right_apply WHERE seller_id = 2213249110271 AND env = 'staging' ORDER BY id DESC LIMIT 3"
```

---

## 四、CDP UI 兜底菜谱

### 4.1 连接浏览器

```javascript
const puppeteer = require('puppeteer-core');
const browser = await puppeteer.connect({
  browserURL: process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222',
  defaultViewport: null
});
```

### 4.2 商家端创建 QUICK 申请

```javascript
const page = await browser.newPage();
await page.goto('https://pre-fsyc.taobao.com/', {waitUntil: 'networkidle2'});
// 点击"新增专利申请"
await page.click('新增专利申请按钮selector');
// 使用 native setter 设置文件 input
const input = await page.$('input[type="file"]');
await input.evaluateHandle((el, file) => {
  const dt = new DataTransfer(); dt.items.add(file);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'files').set;
  setter.call(el, dt.files);
  el.dispatchEvent(new Event('change', {bubbles: true}));
}, testFile);
await page.click('提交按钮selector');
await page.waitForResponse(r => r.url().includes('taobao.industry.yc.right.apply'));
```

### 4.3 小二端创建 QUICK 申请

关键顺序：
1. 填 sellerId + Enter 触发 `bzb.api.sceneplatform.tbyc.seller.get`
2. 等待 `.shopNameValue--vCMXLqTf` 回显 `u[xxx]`
3. 上传主视图（Canvas 生成小图）
4. 填预计上架日期
5. 点提交（请求走 `fetch`，需 hook `window.fetch` 或看 Network）

---

## 五、状态值速查

| 类型 | 状态值 |
|------|--------|
| QUICK 快审通过 | `QUICK_AUDITED` |
| QUICK 快审驳回 | `QUICK_REJECT` |
| PRE 初审通过 | `PRE_AUDITED` |
| PRE 初审驳回 | `PRE_AUDIT_REJECT` |
| 权益失效 | `YC_PROTECT_INVALID` |
| 结算完结待退款 | `FINISH_REFUNDING` |

---

## 六、常见错误与修复

| 错误 | 原因 | 修复 |
|------|------|------|
| `FAIL_SYS_ILLEGAL_ACCESS` | raw fetch 调用 MTOP | 改用 `window.lib.mtop.request` |
| `BIZ_ERROR::可用权益数不足` | PRE 服务次数为 0 | 先充值 |
| `BIZ_ERROR::设计元素不能为空` | `designElement` 单数 | 改为 `designElements` |
| HSF 参数解析错误 | `List<Long>` 用了单括号 | 改为 `[[id1, id2]]` |
| 小二端上传失败，提示"请先确认商家信息" | sellerId 未校验 | 按 4.3 顺序重试 |
| 退款失败 | 非全量退款 | 确认退款金额等于剩余全部金额 |

---

## 七、ScheduleX 手动触发（UI 兜底）

预发控制台：`https://pre.schedulerx2.alibaba-inc.com/`

结算 Job 链：
1. `715618497` 首发补贴退款（01:00）
2. `399576024` 专利保护定时失效（02:00）
3. `719211870` 服务完结退款（04:00）
4. `721504806` 服务完结确认收（06:00）

> React "运行一次" 按钮需通过坐标点击或用户手动触发，普通 `.click()` 无效。
