---
name: yc-quick-audit-data-create
description: 在原创保护平台预发环境通过商家端MTOP API构造快审(QUICK)和初审(PRE)测试数据。支持服务次数不足时半自动充值（UI建单+API取支付链接）。适用于测试账号（见 test-accounts.md）。触发词：造快审数据、造初审数据、构造PRE数据、原创保护造数、充值服务次数。
version: 1.4.0
---

> 📋 测试商家 seller_id 统一维护入口：[test-accounts.md](../yc-protection-qa-workbench/test-accounts.md)（插件根目录）

# 原创保护测试数据构造

在预发环境为指定商家构造快审（QUICK）或初审（PRE）类型专利申请记录，支持商家端MTOP API直调和服务次数充值。

## 前置检查

### 1. 服务次数校验
- **快审(QUICK)：不消耗服务次数**，可直接构造，无需充值
- **初审(PRE)：消耗1次/条**，构造前必须先确认剩余次数：
```
打开 https://pre-fsyc.taobao.com/ → 查看左侧面板"剩余服务次数"
```
- **PRE次数=0**：商家端MTOP会返回 `BIZ_ERROR::可用权益数不足`，必须先充值
- **充值入口**：商家端页面"去充值"按钮，或通过HSF工具 `SellerToolService` 增加次数
- **小二端不受此限制**：小二端cobweb API可以绕过服务次数校验直接构造数据

### 2. 测试图片准备
需要至少一张主视图图片（JPG/PNG）。复用已有OSS图片：
```
https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png
```
或通过OSS签名上传新图片（先调 `getosssignature` 获取签名，再POST到OSS）。

## 路径A：商家端MTOP API（推荐，走完整业务流程）

### API信息
- **API Key**: `taobao.industry.yc.right.apply`
- **Endpoint**: `//h5api.wapa.taobao.com/h5/taobao.industry.yc.right.apply/1.0/`
- **环境**: 预发（hostname含pre自动切预发MTOP）
- **认证**: 千牛登录态（httpOnly cookie，必须浏览器内执行）
- **调用方式**: 必须通过 `window.lib.mtop.request()` 调用，**不可用 raw fetch**（会返回 `FAIL_SYS_ILLEGAL_ACCESS`）
- **服务次数**: **快审不消耗服务次数**，可直接构造

### 请求Payload（已验证成功）
```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'QUICK',
    category: '服装',
    productImg: [{
      type: '主视图',
      urls: [ossUrl]
    }],
    expectedOnshelfDate: '2026-07-15'
  };

  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0',
      method: 'POST',
      data: {request: JSON.stringify(payload)}
    }, function(res) {
      resolve('SUCCESS: ' + JSON.stringify(res));
    }, function(err) {
      resolve('ERROR: ' + JSON.stringify(err));
    });
  });
})()
```

### 关键字段
| 字段 | 必填 | 说明 |
|------|------|------|
| saveOrApply | 是 | "apply"=正式提交，"save"=保存草稿 |
| category | 是 | 固定"服装" |
| productImg | 是 | 数组，至少包含主视图，type中文值（主视图/立体图/后视图等） |
| expectedOnshelfDate | 是 | 预计上架日期，格式YYYY-MM-DD |
| applyType | 是 | "QUICK"=快审，"PRE"=初审，"REGULAR"=普通 |

### 成功响应
```json
{"api": "taobao.industry.yc.right.apply", "data": {}, "ret": ["SUCCESS::调用成功"]}
```

### 失败响应
```json
{"ret": ["BIZ_ERROR::可用权益数不足"]}
```

## 路径B：小二端cobweb API（不受服务次数限制）

### API信息
- **API Key**: `bzb.api.sceneplatform.tbyc.right.apply.submit`
- **Endpoint**: `//pre-xiaoer.alibaba-inc.com/cobweb/api/bzb.api.sceneplatform.tbyc.right.apply.submit`
- **认证**: 小二SSO（httpOnly cookie）

### 请求Payload
```javascript
fetch('/cobweb/api/bzb.api.sceneplatform.tbyc.right.apply.submit', {
  method: 'POST',
  credentials: 'include',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    _bzb_format: "json",
    _bzb_data: {
      sellerId: 2213249110271,
      productImg: [{
        type: "main",
        urls: ["https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png"]
      }],
      expectedOnshelfDate: "2026-06-19"
    }
  })
}).then(r => r.json()).then(d => window.__result = d);
```

### 关键字段
| 字段 | 必填 | 说明 |
|------|------|------|
| sellerId | 是 | 商家ID，数字类型 |
| productImg | 是 | type用英文"main"（非中文"主视图"） |
| expectedOnshelfDate | 是 | 格式YYYY-MM-DD |

## 路径C：商家端MTOP API创建初审(PRE)数据

### API信息
与快审共用同一API：
- **API Key**: `taobao.industry.yc.right.apply`
- **认证**: 千牛登录态（httpOnly cookie，必须浏览器内执行）
- **调用方式**: 必须通过 `window.lib.mtop.request()` 调用，**不可用 raw fetch**（会返回 `FAIL_SYS_ILLEGAL_ACCESS`）

### PRE完整Payload（已验证成功）
```javascript
(function() {
  const ossUrl = 'https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/dc6cb247-7580-4a49-8b88-ca672d70749a.png';
  const payload = {
    saveOrApply: 'apply',
    applyType: 'PRE',
    category: '服装',
    productName: 'QA测试初审外套0629A',
    productUsage: '用于日常穿着外套',
    remark: '独特的剪裁设计结合经典元素，体现现代解构主义风格',
    designers: [{
      name: '测试设计师A',
      identityNumber: '330102199001011234',
      nationality: '中国',
      identityPictures: [ossUrl, ossUrl]  // 扁平URL数组，第1张=正面，第2张=反面
    }],
    contacts: [{
      name: '测试联系人',
      address: '',
      zipCode: '',
      phone: '13800138000',
      email: ''
    }],
    designElements: ['A'],  // ⚠ 必须用复数 designElements，不能用 designElement
    designViews: ['A', 'B'],  // ⚠ 必须用复数 designViews，不能用 designView
    productImg: [
      {type: '立体图', urls: [ossUrl]},
      {type: '主视图', urls: [ossUrl]}
    ],
    expectedOnshelfDate: '2026-07-15'
  };

  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'taobao.industry.yc.right.apply',
      v: '1.0',
      method: 'POST',
      data: {request: JSON.stringify(payload)}
    }, function(res) {
      resolve('SUCCESS: ' + JSON.stringify(res));
    }, function(err) {
      resolve('ERROR: ' + JSON.stringify(err));
    });
  });
})()
```

### PRE与QUICK字段差异
| 字段 | QUICK | PRE | 说明 |
|------|-------|-----|------|
| applyType | "QUICK" | "PRE" | 申请类型 |
| productName | 不需要 | **必填** | 商品名称 |
| productUsage | 不需要 | **必填** | 商品用途 |
| remark | 不需要 | **必填** | 原创描述/设计要点说明 |
| designers[] | 不需要 | **必填** | 设计师信息数组 |
| designers[].identityNumber | — | **必填** | 身份证号（非idNumber） |
| designers[].identityPictures | — | **必填** | 证件正反面URL扁平数组（非idCardFront/idCardBack） |
| designers[].nationality | — | **必填** | 国籍 |
| contacts[] | 不需要 | **必填** | 联系人数组，格式[{name,phone,address,zipCode,email}] |
| designElements | 不需要 | **必填** | 设计要素，数组A~F（⚠ 用复数，非designElement） |
| designViews | 不需要 | **必填** | 设计视图，数组A~G（⚠ 用复数，非designView） |
| productImg[].type | "main"(英文) | "主视图"等**中文** | 商家端PRE用中文type |
| expectedOnshelfDate | 必填 | 必填 | 格式YYYY-MM-DD |

### PRE成功响应
```json
{"api":"taobao.industry.yc.right.apply","data":{"result":"200000873"},"ret":["SUCCESS::调用成功"]}
```
`data.result` = 申请编号

### PRE常见错误
| 错误 | 原因 | 修复 |
|------|------|------|
| `BIZ_ERROR::设计元素不能为空` | 用 `designElement`(单数) 而非 `designElements`(复数) | 改为 `designElements` |
| `BIZ_ERROR::设计人身份证不能为空` | 用 `idCardFront`/`idCardBack` 字段 | 改为 `identityPictures` 扁平数组 |
| `BIZ_ERROR::联系人不能为空` | 用扁平 `contactName`/`contactPhone` 字段 | 改为 `contacts` 数组格式 |
| `BIZ_ERROR::可用权益数不足` | 剩余服务次数=0 | 走充值流程（见下方） |
| `FAIL_SYS_ILLEGAL_ACCESS` | 用 raw fetch 而非 lib.mtop.request | 改用 `window.lib.mtop.request()` |

## 路径D：批量构造 PRE 数据（推荐用于 ≥10 条）

当需要为同一个或多个商家一次性构造大量初审（PRE）记录时，使用 `scripts/batch_pre_recharge.py`。该脚本封装了 CDP 连接、服务次数检查与充值兜底、MTOP 批量调用、DB 验证和 att-tf cases.json 输出。

### 前置条件
- Chrome 已以 remote debugging 模式启动，例如 `chrome --remote-debugging-port=9223 --user-data-dir=~/.chrome-debug-9223`
- 浏览器已完成千牛登录，且页面已加载 `lib.mtop`
- 本地已安装 `websocket-client`：`pip install websocket-client`

### 常用命令

```bash
# 单个商家构造 10 条并验证落库
python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 10 --verify-db

# 多商家批量（JSON 文件）
python3 scripts/batch_pre_recharge.py --seller-file sellers.json --verify-db

# 开启半自动 UI 充值兜底
python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 10 --manual-recharge --verify-db

# 演练模式，不实际调用 MTOP/DB
python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 3 --dry-run
```

`sellers.json` 支持两种格式：
```json
["2213249110271", "2213249110272"]
```
或
```json
[
  {"seller_id": "2213249110271", "count": 10},
  {"seller_id": "2213249110272", "count": 5}
]
```

### 主要 CLI 参数

| 参数 | 说明 |
|------|------|
| `--seller` | 商家 seller_id，逗号分隔多个 |
| `--seller-file` | 商家列表 JSON 文件 |
| `--count` | 每个商家构造条数（默认 1） |
| `--cdp-port` | CDP 端口，默认自动探测 9223-9230 |
| `--dry-run` | 演练模式，只输出执行计划 |
| `--verify-db` | 构造后通过 dms-alibaba 查询 `yc_right_apply` 验证落库 |
| `--manual-recharge` | 次数不足时允许半自动 UI 充值兜底 |
| `--auto-recharge` | 尝试 HSF 直充（需团队提供接口并配置） |
| `--onshelf-days` | 预计上架日期偏移天数（默认 7） |
| `--output` | cases.json 输出路径 |

### 输出与退出码
- 终端打印每个商家的创建结果、apply_id、DB 验证结果
- 生成 `pre_batch_cases_YYYYMMDD_HHMMSS.json`，可直接作为 att-tf cases.json 片段上报
- 退出码：`0` 全部成功 / `1` 参数或环境错误 / `2` 部分成功 / `3` 全部失败

## 服务次数充值流程（半自动）

当商家剩余服务次数=0时，需先充值再创建数据。服务市场商品：`FW_GOODS-1001291504`（0.1元/次）。

### 步骤1：UI创建订单（必须走UI，order.create需服务端sign）
1. 打开 `https://pre-fsyc.taobao.com/` → 点击"去充值"
2. 在服务市场页面点击"立即订购"按钮
3. 在"选择规格"弹窗中点击"立即购买"
4. 在订单确认页勾选协议，点击"同意并付款"
5. 进入支付页(orderPayNew.htm)后停止，**不要点"确认并支付"**
6. 记录URL中的 `orderId` 参数

### 步骤2：API获取支付链接
```javascript
(function() {
  return new Promise((resolve) => {
    window.lib.mtop.request({
      api: 'mtop.alibaba.topservice.order.pay',
      v: '1.0',
      method: 'POST',
      data: {
        orderId: '{orderId}',  // 从步骤1获取
        payType: 'aliPay',
        callBackUrl: '//pre-fuwu.taobao.com/serv/new_order_callback.htm'
      }
    }, function(res) {
      resolve(JSON.stringify(res));
    }, function(err) {
      resolve(JSON.stringify(err));
    });
  });
})()
```

### 步骤3：截取二维码
API返回 `returnData` 为支付宝网关URL，在浏览器中打开该URL会自动跳转到：
```
https://excashier.alipay.com/standard/auth.htm?payOrderId={payOrderId}
```
截取该页面的二维码发给用户扫码支付。

### 步骤4：确认充值成功
支付后刷新商家端页面，调用统计API确认：
```javascript
window.lib.mtop.request({
  api: 'taobao.industry.yc.common.statistics',
  v: '1.0', method: 'GET', data: {}
}, function(res) { console.log(res.data.remainRightCount); });
```

### 已知限制
- `order.create` API 需要服务端生成的 `sign` 参数，无法纯API调用，必须通过UI触发
- `order.pay` API 可直接调用，返回完整支付宝网关URL
- 每次充值1次服务次数（0.1元），创建1条PRE数据消耗1次

## 图片上传流程（OSS签名上传）

当需要使用新图片而非复用已有OSS URL时：

1. **获取OSS签名**：
```javascript
fetch('/cobweb/api/bzb.api.sceneplatform.tbyc.common.getosssignature', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({_bzb_format: 'json', _bzb_data: {}})
}).then(r => r.json()).then(d => window.__ossSign = d);
```

2. **上传图片到OSS**：使用返回的签名信息，POST到 `https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/`

3. **获取图片URL**：上传成功后返回的OSS路径即为可用图片URL

## DB验证

### 确认新记录创建（6 字段标准汇报）
构造完成后，必须查询以下 6 个字段并汇报：
```bash
dms-alibaba sql run scenario --db prod --sql "SELECT id, outer_apply_id, right_id, seller_id, apply_type, status FROM yc_right_apply WHERE id = {申请编号}"
```

| 字段 | DB 列名 | 说明 |
|------|---------|------|
| 申请编号 | `id` | 主键，MTOP 返回的 `data.result` |
| YC 编号 | `outer_apply_id` | 格式 YC + 数字，外部申请编号 |
| 权益 ID | `right_id` | 关联 yc_right 表的权益记录 |
| 商家 seller_id | `seller_id` | 商家 ID |
| 类型 | `apply_type` | QUICK / PRE / REGULAR |
| 状态 | `status` | 如 PRE_PRE_AUDITING、QUICK_AUDITING 等 |

### 预期状态
- **新创建 QUICK 记录**: status=`QUICK_AUDITING`, apply_type=`QUICK`
- **新创建 PRE 记录**: status=`PRE_PRE_AUDITING`, apply_type=`PRE`
- **关联 Right 记录**: yc_right 表中 status=`APPLYING`

### 结果路径
JSON 结果在 `~/dms-alibaba/db-groups/scenario/sql/quick_prod/_results/{date}/`，取 `rows` 字段。

## 已知限制与踩坑

1. **服务次数**：快审(QUICK)**不消耗**服务次数，可直接构造；初审(PRE)消耗1次/条，次数不足时返回 `BIZ_ERROR::可用权益数不足`，需先充值
2. **小二端cobweb直接XHR会失败**：必须通过页面表单的内置请求机制发送，手动构造XHR/fetch会因CSRF/cookie问题返回error
3. **图片type字段差异**：商家端QUICK用中文（"主视图"），小二端用英文（"main"）；PRE也用中文
4. **React表单填写**：通过UI自动化填写时，React的synthetic event不响应普通DOM事件，需要使用nativeInputValueSetter模式
5. **【⚠️核心踩坑】Antd Upload 必须先通过 sellerId 校验**：小二端表单填写顺序强依赖——`sellerId 输入 → 按 Enter → seller.get API 200 → 店铺名称回显（.shopNameValue--vCMXLqTf 显示 u[xxx]）→ 才能上传主视图`。在 sellerId 未校验时上传，文件会立刻被标 `ant-upload-list-item-error`（页面提示「请先确认商家信息」）。这与文件大小、DataTransfer 注入方式无关，纯粹是组件状态门控。先前误判为「图片过大/注入问题」是错的。
6. **日期选择器**：Antd DatePicker需要特殊处理，直接设置value可能不触发React状态更新
7. **sellerId 校验会重置表单**：小二端 sellerId 输入并触发校验（Enter/blur）后，**表单内已填写的「主视图」「日期」字段会被清空**。所以正确顺序必须是：① 先填 sellerId + Enter ② 等店铺名称回显 ③ 再上传主视图 ④ 再填日期 ⑤ 最后提交。如果先填图/日期再填 sellerId，前面的全部白填。
8. **submit 走 fetch 不走 XHR**：小二端「提交」按钮内部用 `fetch` 发请求，安装 XHR 拦截器无法捕获。要拦截 submit 必须 hook `window.fetch`，或直接看浏览器 Network 面板。
9. **【PRE专项】MTOP必须用lib.mtop.request**：raw fetch调用MTOP会返回 `FAIL_SYS_ILLEGAL_ACCESS::非法请求`，因为缺少token/sign签名。`window.lib.mtop.request()` 自动处理签名
10. **【PRE专项】字段名单复数差异**：前端内部用 `designElement`/`designView`(单数)，MTOP API必须用 `designElements`/`designViews`(复数)。混用会返回 `BIZ_ERROR::设计元素不能为空`
11. **【PRE专项】身份证字段名**：MTOP API用 `identityNumber`（非idNumber），证件照用 `identityPictures`（扁平URL数组，非idCardFront/idCardBack分字段）
12. **【PRE专项】联系人格式**：MTOP API要求 `contacts` 数组格式 `[{name, phone, address, zipCode, email}]`，不能用扁平的 `contactName`/`contactPhone`
13. **【PRE专项】小二端cobweb不支持PRE**：`bzb.api.sceneplatform.tbyc.right.apply.submit` 仅支持QUICK快审（无applyType字段），PRE只能通过商家端MTOP创建
14. **充值order.create需UI**：`mtop.alibaba.topservice.order.create` 需要服务端生成的 `sign` 参数，无法纯API调用。`order.pay` 可直接调用返回支付宝网关URL

## 完整UI自动化流程（商家端）

1. 打开 `https://pre-fsyc.taobao.com/`
2. 点击"新增专利申请"按钮
3. 确认右侧面板打开，"快审"tab已激活
4. 通过JS设置文件到第一个file input（主视图）：
   - fetch图片→创建File→DataTransfer→nativeSetter→dispatchEvent('change')
5. 点击日期输入框（id=`patent_apply_expectedListDate`），输入日期，按Enter
6. 点击"提交"按钮
7. 设置网络拦截器捕获MTOP请求和响应
8. 验证响应ret包含"SUCCESS"
9. DB查询确认记录创建

## 完整UI自动化流程（小二端，已验证 ✅）

> 已通过此流程成功创建 record id=200000747（seller=2213249110271）。**严格按以下顺序，调换会失败**。

### 步骤
1. 打开 `https://pre-xiaoer.alibaba-inc.com/...`（快审造数页面）
2. **第一步：填 sellerId 并触发校验**
   ```javascript
   var sellerInput = document.querySelector('input[placeholder*="商家"]'); // 或对应的 sellerId 输入框
   var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
   setter.call(sellerInput, '2213249110271');
   sellerInput.dispatchEvent(new Event('input', {bubbles:true}));
   // 必须按 Enter 触发校验，仅 input/change 不会触发 seller.get
   sellerInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
   sellerInput.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
   sellerInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
   sellerInput.dispatchEvent(new Event('change', {bubbles:true}));
   sellerInput.blur();
   ```
3. **第二步：等待店铺名称回显**
   - 监测 `.shopNameValue--vCMXLqTf` 元素，文本由空变为 `u[2213249110271]` 即可。
   - 同时网络面板会看到 `bzb.api.sceneplatform.tbyc.seller.get` 200。
   - 未回显前不要进行下一步，否则上传必失败。
4. **第三步：上传主视图**（用 Canvas 生成测试图，~33KB，避免大文件 OSS 拉取失败）
   ```javascript
   var canvas = document.createElement('canvas');
   canvas.width = 800; canvas.height = 800;
   var ctx = canvas.getContext('2d');
   ctx.fillStyle = '#3498db'; ctx.fillRect(0,0,800,800);
   ctx.fillStyle = '#fff'; ctx.font = 'bold 60px sans-serif'; ctx.textAlign = 'center';
   ctx.fillText('QA TEST', 400, 380);
   ctx.fillText('MAIN ' + new Date().toISOString().slice(0,10), 400, 460);
   var blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
   var file = new File([blob], 'qa_main_'+Date.now()+'.png', {type:'image/png'});
   var dt = new DataTransfer(); dt.items.add(file);
   var mainInput = document.querySelector('input[type="file"]'); // 主视图 input
   Object.defineProperty(mainInput, 'files', {value: dt.files, writable: false, configurable: true});
   mainInput.dispatchEvent(new Event('change', {bubbles:true}));
   ```
   - 成功标志：上传列表项 className 由 `ant-upload-list-item-uploading` 变 `ant-upload-list-item-done`，**不要看到** `ant-upload-list-item-error`。
5. **第四步：填预计上架日期**（今天 +7 天，YYYY-MM-DD）
6. **第五步：点提交**
   - 注意 submit 走 `fetch` 不是 XHR，要拦截需 hook `window.fetch`。
   - 或直接在 Network 面板看 `bzb.api.sceneplatform.tbyc.right.apply.submit` 的 200 响应。

### 失败排查
| 现象 | 根因 | 修复 |
|------|------|------|
| 上传图标红色 + 提示「请先确认商家信息」 | sellerId 未校验 / 店铺名未回显 | 重新做步骤 2-3，确认店铺名出现后再上传 |
| sellerId 输完店铺名仍空 | 仅触发了 input 事件，没触发 Enter | 必须 dispatch keydown+keypress+keyup `Enter` + blur |
| 已上传主视图，填完 sellerId 后图没了 | sellerId 校验会重置整个表单 | 调换顺序：sellerId 第一步，图片在店铺名回显之后 |
| 提交点了没反应 / 无 XHR 拦截到 | submit 用 fetch，XHR 拦截器看不到 | 改用 fetch 拦截，或直接看 Network 面板 |

## 验证

- API响应ret包含"SUCCESS"
- DB中新建记录status=QUICK_AUDITING
- 商家端列表刷新后可看到新申请
- 小二端列表同步显示新申请
