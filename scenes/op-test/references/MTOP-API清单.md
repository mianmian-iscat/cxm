# 原创保护 MTOP API 清单

> 预发环境 MTOP 调用必须在浏览器内执行 JS fetch（SSO cookie 为 httpOnly）  
> 商家端：`https://pre-fsyc.taobao.com/`  
> 小二端：`https://pre-xiaoer.alibaba-inc.com/`  
> **重要**：小二端 `window.lib.mtop.request` 存在接口异常退出问题，cobweb fetch 因 CSRF 返回 HTML。小二端 API 优先走 UI 操作，商家端 API 可用 MTOP SDK 调用。

---

## 调用模式

```javascript
// 通用 MTOP 调用模板
window.lib.mtop.request({
  api: '<API_NAME>',
  v: '1.0',
  data: { /* 参数 */ },
  needLogin: true
}).then(res => { window.__var_result = res; });

// 等待结果
await new Promise(r => setTimeout(r, 2000));
console.log(JSON.stringify(window.__var_result));
```

---

## 商家端 API（21 个）

### 申请管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.right.page` | GET | 专利权列表分页 | pageNo, pageSize, status |
| `taobao.industry.yc.right.detail` | GET | 专利权详情 | rightId |
| `taobao.industry.yc.right.apply.submit` | POST | 提交申请 | applyType, certNo, images |
| `taobao.industry.yc.right.apply.save` | POST | 保存草稿 | applyType, certNo |
| `taobao.industry.yc.right.apply.detail` | GET | 申请详情 | applyId |
| `taobao.industry.yc.right.apply.submitToRegular` | POST | 转普通申请 | applyId |

### 证书管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.cert.upload` | POST | 上传证书文件 | file, certType |
| `taobao.industry.yc.cert.download` | GET | 下载证书 | certNo |
| `taobao.industry.yc.cert.preview` | GET | 预览证书 | certNo |

### 维权管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.protect.record.page` | GET | 维权记录分页 | rightId, pageNo, pageSize |
| `taobao.industry.yc.protect.record.detail` | GET | 维权记录详情 | recordId |
| `taobao.industry.yc.tort.report` | POST | 上报侵权线索 | rightId, tortUrl |
| `taobao.industry.yc.tort.record.page` | GET | 侵权记录分页 | rightId, pageNo |

### 结算管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.settle.order.page` | GET | 结算单分页 | rightId, pageNo |
| `taobao.industry.yc.settle.order.detail` | GET | 结算单详情 | orderId |
| `taobao.industry.yc.settle.refund.apply` | POST | 申请退款 | orderId |

### 巡检与白名单

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.inspect.whitelist.query` | GET | 查巡检白名单 | categoryId |
| `taobao.industry.yc.inspect.detail.page` | GET | 巡检详情分页 | rightId, pageNo |

### 其他

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.seller.enter.status` | GET | 商家入驻状态 | sellerId |
| `taobao.industry.yc.category.list` | GET | 类目列表 | parentId |

---

## 小二端 API（10 个）

### 审核管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.xiaoer.apply.page` | GET | 审核列表分页 | status, applyType, pageNo |
| `taobao.industry.yc.xiaoer.apply.detail` | GET | 审核详情 | applyId |
| `taobao.industry.yc.xiaoer.quick.audit` | POST | 快审操作（通过/驳回） | applyId, action, reason |
| `taobao.industry.yc.xiaoer.pre.audit` | POST | 预审操作 | applyId, action, reason |

### 首发管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.xiaoer.first.publish.update` | POST | 更新首发标签 | rightId, firstPublish |
| `taobao.industry.yc.xiaoer.first.publish.confirm` | POST | 确认首发（触发补贴） | rightId |

### 商家管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.xiaoer.seller.search` | GET | 搜索商家 | sellerId, keyword |
| `taobao.industry.yc.xiaoer.seller.enter.fast` | POST | 快审入驻 | sellerId |

### 结算管理

| API | 方法 | 说明 | 关键参数 |
|-----|------|------|---------|
| `taobao.industry.yc.xiaoer.settle.order.page` | GET | 结算单分页 | rightId, status |
| `taobao.industry.yc.xiaoer.settle.refund.approve` | POST | 审批退款 | refundId, action |

---

## 已知问题

| 问题 | 影响 API | 解决方案 |
|------|---------|---------|
| 非浏览器 fetch 返回 HTML | 所有 POST API | 必须在浏览器内执行 JS |
| 小二端 MTOP SDK 调用失败 | 小二端全部 API | `window.lib.mtop.request` 返回"接口异常退出"，改用 UI 操作 |
| 小二端 cobweb fetch 返回 HTML | 小二端全部 API | CSRF 拦截，不可用 fetch 直接调用 |
| SSO cookie httpOnly | 全部 | 无法直接读取 cookie，依赖浏览器 session |
| submitToRegular POST 问题 | `/api/seller/apply/submitToRegular` | 使用 MTOP 替代 REST |
| 预发环境延迟 | 全部 | 增加等待时间到 3-5 秒 |

---

## 错误码速查

| 错误码 | 含义 | 处理 |
|--------|------|------|
| `SUCCESS` | 成功 | 正常处理 |
| `FAIL_SYS_SESSION_EXPIRED` | session 过期 | 重新登录 |
| `FAIL_BIZ_PARAM_ERROR` | 参数错误 | 检查入参 |
| `FAIL_BIZ_NO_PERMISSION` | 无权限 | 检查账号权限 |
| `FAIL_BIZ_DATA_NOT_FOUND` | 数据不存在 | 检查数据是否已创建 |
| `FAIL_SYS_TRAFFIC_LIMIT` | 限流 | 等待后重试 |
