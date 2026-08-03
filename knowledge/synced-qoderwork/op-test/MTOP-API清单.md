<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护执行助手/references/MTOP-API清单.md -->
<!-- synced-at: 2026-07-11T03:52:34.999834 -->
<!-- skill: 原创保护执行助手 -->

# MTOP API 清单

## 商家端 MTOP API（21个）

| API Key | 功能 | 服务文件 |
|---------|------|---------|
| taobao.industry.yc.right.apply | 提交/更新专利申请(草稿save/正式apply) | patentApply.ts |
| taobao.industry.yc.right.category.list | 获取商品类目列表 | patentApply.ts |
| taobao.industry.yc.right.page | 专利列表分页查询 | patentList.ts |
| taobao.industry.yc.inneryc.getyclink | 获取平台原创保护申请链接 | patentList.ts |
| taobao.industry.yc.right.apply.get | 获取申请详情 | patentList.ts |
| taobao.industry.yc.right.apply.terminate | 终止申请 | patentList.ts |
| taobao.industry.yc.right.apply.cancel | 取消申请 | patentList.ts |
| taobao.industry.yc.right.item.page | 可绑定商品列表 | patentList.ts |
| taobao.industry.yc.right.binditem | 绑定商品到专利 | patentList.ts |
| taobao.industry.yc.inneryc.page | 平台原创保护记录列表 | originalProtection.ts |
| taobao.industry.yc.right.protect.page | 维权记录列表 | rightsProtection.ts |
| taobao.industry.yc.seller.sign | 签约服务合同 | contract.ts |
| taobao.industry.yc.common.statistics | 仪表盘统计数据 | statistics.ts |
| taobao.industry.yc.tort.page | 侵权巡检记录列表 | inspection.ts |
| taobao.industry.yc.tort.add | 手动添加侵权记录 | inspection.ts |
| taobao.industry.yc.right.protect.submit | 提交维权请求(批量) | inspection.ts |
| taobao.industry.yc.tort.whitelist.page | 白名单店铺列表 | whitelist.ts |
| taobao.industry.yc.tort.whitelist.save | 添加/编辑白名单店铺 | whitelist.ts |
| taobao.industry.yc.tort.whitelist.delete | 删除白名单店铺 | whitelist.ts |
| taobao.industry.yc.common.allenum | 获取所有枚举值(缓存) | enum.ts |
| taobao.industry.yc.common.oss.getsignature | OSS上传签名 | upload.ts |

## 商家端 REST API（4个）

| Endpoint | Method | 功能 |
|----------|--------|------|
| /api/seller/apply/submitToRegular | POST | 快审转普通申请 |
| /api/file/upload | POST | 文件上传 |
| /api/tort/statistic | GET | 侵权状态统计 |
| /api/common/parseItemInfoByUrl | GET | URL解析商品信息 |

## 小二端 MTOP API（10个）

| API Key | 功能 |
|---------|------|
| bzb.api.sceneplatform.tbyc.right.page | 专利列表分页(9个筛选字段) |
| bzb.api.sceneplatform.tbyc.common.allenum | 枚举配置 |
| bzb.api.sceneplatform.tbyc.right.apply.get | 申请详情 |
| bzb.api.sceneplatform.tbyc.right.protect.page | 维权记录 |
| bzb.api.sceneplatform.tbyc.right.tort.statistics | 侵权统计(含下架率) |
| bzb.api.sceneplatform.tbyc.right.firstpublish.set | 设置是否首发 |
| bzb.api.sceneplatform.tbyc.right.whitelist.page | 白名单店铺 |
| bzb.api.sceneplatform.tbyc.right.tort.page | 侵权巡检记录 |
| bzb.api.sceneplatform.tbyc.seller.get | 商家信息(sellerId→shopName) |
| bzb.api.sceneplatform.tbyc.right.apply.submit | 小二发起快审 |

## MTOP 调用模式

### 商家端

```javascript
// 必须在浏览器内执行（预发SSO是httpOnly cookie）
window.lib.mtop.request({
  api: 'taobao.industry.yc.right.page',
  v: '1.0',
  data: {
    page: 1,
    pageSize: 20,
    status: 'YC_PROTECT_VALID'
  },
  needLogin: true
}).then(res => {
  window.__var_yc_result = res;
});

// 异步等待
await new Promise(r => setTimeout(r, 2000));
console.log(JSON.stringify(window.__var_yc_result));
```

### 小二端

```javascript
// 通过 @ali/bzb-request 包装
// hostname含'pre'自动切预发
fetch('/mtop/bzb.api.sceneplatform.tbyc.right.page', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    page: 1, pageSize: 20,
    status: ['YC_PROTECTING'],
    applyStatus: ['CERT_FILE_SYNCED']
  })
}).then(r => r.json()).then(d => window.__var = d);
```

## 响应结构（MTOP通用）

```json
{
  "success": true,
  "code": "SUCCESS",
  "msg": "",
  "data": {
    "success": true,
    "data": {
      "content": [...],
      "totalElements": 100,
      "pageNo": 1,
      "pageSize": 20,
      "totalPages": 5,
      "hasMore": true
    },
    "errorMessage": null
  }
}
```

实际业务数据在 `data.data`，分页用 Spring `PageImpl` 格式。

## 环境识别

- 生产MTOP: `h5api.m.taobao.com`
- 预发MTOP: `h5api.wapa.taobao.com`
- 切换条件: hostname含"pre" 或 URL参数 `usePreMtop=true`

## 已知非浏览器环境调用问题

类似F88：以下API在 requests/curl 易返HTML登录页（参考已知踩坑）：
- 任何依赖 SSO httpOnly cookie 的endpoint
- POST /api/seller/apply/submitToRegular

**解决方案**：浏览器内 `fetch` + `window.__var` 全局变量异步取值。
