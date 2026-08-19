# 核心 API 细节（脚本失效时的浏览器兜底参考）

> 📋 F88 测试商家 seller_id 统一维护入口：[test-accounts.md](../../web-automation/knowledge/synced-qoderwork/f88-test/test-accounts.md)

> 首选 `scripts/f88_review_data.py`。本文档保留原始 API 与浏览器 fetch 兜底方式。

## 触发试运行

```
POST /api/workflow2/strategy/run
Headers:
  Content-Type: application/json
  X-AFD-Emp-Identity: f88    ← 必须！
Body:
{
  "strategyId": 10817,
  "inputDatas": [
    {"seller_id": "2219662018344", "seed_image_url": "https://...", "tao_cate": "xxx", ...}
  ],
  "runMode": "test"
}
Response:
  {"success": true, "data": "BT_7260"}   ← 返回批次号
```

**⚠️ 所有 `/api/afd/` 和 workflow 相关请求都必须带 `X-AFD-Emp-Identity: f88` header。**

## 获取策略 inputParams

```
GET /api/workflow2/strategy/get?id={strategyId}
Headers: X-AFD-Emp-Identity: f88
```

响应中 `data.workflowDef.inputParams` 数组定义该策略接受的输入参数：
```json
"inputParams": [
  {"code": "seller_id", "name": "商家ID"},
  {"code": "seed_image_url", "name": "种子图"},
  {"code": "tao_cate", "name": "类目"}
]
```

`inputDatas` 中每行对象的 key 必须与 `inputParams` 的 `code` 完全匹配。

## 查询批次状态

```
GET /api/workflow/batch/getRunDetail?batchId={batchId}
Headers: X-AFD-Emp-Identity: f88
```

响应结构：`data.workflowBatch.status` = PROCESSING / SUCCESS / FAIL

## 浏览器兜底：javascript_tool + fetch

```javascript
var payload = {strategyId: 10817, inputDatas: [...], runMode: "test"};
fetch('/api/workflow2/strategy/run', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-AFD-Emp-Identity': 'f88'
  },
  body: JSON.stringify(payload)
}).then(r => r.json()).then(d => {
  document.title = JSON.stringify(d);
});
```

**注意**：`javascript_tool` 始终返回 `undefined`，必须通过 `document.title` 中转结果，再用 `get_page_text` 或另一次 `javascript_tool` 读取 `document.title`。

## 手动创建审核任务（方式二，仅 formal 语义验证）

```
POST /api/afd/review/task/main/create
Headers: Content-Type: application/json, X-AFD-Emp-Identity: f88
```

关键参数：taskName / nodeId(168首图,139套图,144视频,138模板) / dataFileUrl(OSS) /
standardIds=[140] / allocation.participants=[{userId:'526043',userName:'目民',count:5}] /
inspectionConfig.enabled=false / buryConfig.enabled=false / distributionLogic=1。
响应 `data` = 新 taskId。回查：`GET /api/afd/review/task/main/parentReviewTaskDetail?taskId={taskId}`。

文件上传取 OSS URL：`POST /api/file/upload`（FormData，字段名 file），响应 `data` 即 OSS URL。

**操作人身份红线**：审核人必须填目民（emp 526043）。
