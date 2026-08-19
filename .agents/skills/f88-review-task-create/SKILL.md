---
name: f88-review-task-create
description: ⚠️ 已被 `审核数据构造` skill 的方式一（手动创建API+固定Excel模板）取代。日常造审核数据请直接使用 `qa-testing-workbench:审核数据构造`，不要使用本 skill。本 skill 仅保留作为方式一的 API 细节参考。唯一触发词：手动创建审核任务API参考。
version: 2.0.0
---

# F88 手动创建审核任务（首图审核）

## 概述

在 F88 审核标注平台上，通过「手动创建」入口（顶部导航 tab：策略平台-F88 / 策略平台-测试 / **手动创建** / 模版库）创建审核任务测试数据。可走前端4步向导，也可通过 API 一次调用完成创建。典型场景：在预发环境构造首图审核测试数据用于 QA 验证。

## 前端入口路径

F88 页面 → 顶部 tab 切换到「**手动创建**」→ 进入4步向导：
1. 选择审核节点（如"首图审核"）
2. 上传 xlsx 数据文件
3. 配置审核人、分配方式、抽检/埋雷等
4. 确认并提交

以下步骤描述通过 API 绕过向导直接创建的方法。

## 前置条件

1. 浏览器已登录目标环境（预发：`pre-aifashion-xiaoer.alibaba-inc.com`，线上：`aifashion-xiaoer.alibaba-inc.com`）
2. **所有 API 调用必须带 `X-AFD-Emp-Identity: f88` header（写死）**。测试数据只能建在 f88 租户下，永不建在 afd 租户；header 值 `f88` 是固定常量，直接写死。
3. 已获取 nodeId（审核节点ID）和 standardIds（审核标准ID）

## 步骤

### 0. 新开浏览器 tab 并导航到平台（必须）

**每次创建任务都必须新开一个 tab**，导航到平台以建立登录 session。

```
1. tabs_create_mcp → 新建一个 tab
2. navigate → https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center
3. 确认页面加载成功（标题为 i-FASHION运营工作台）
```

**⚠️ 租户控制靠 `X-AFD-Emp-Identity` header，不靠页面下拉框**。页面左上角的身份下拉框只影响 UI 显示，不控制 API 的租户上下文。必须通过步骤 2/3 中的 header 来指定 F88 租户。

### 1. 准备 xlsx 数据文件

下载平台模板（"下载模版"按钮），按模板格式填写数据。

**模板结构（首图审核 questionType=4，11列）**：

| 列名 | 说明 | 必填 |
|------|------|------|
| img_url_list | 审核图URL（**单个URL字符串，非JSON数组**） | 必填 |
| img_url_reference_1~6 | 辅助审核图URL | 选填 |
| tao_cate | 淘系类目 | 必填 |
| seller_id | 商家ID | 必填 |
| shop_name | 商家名称 | 必填 |
| extra_info | 其他信息 | 选填 |

**关键坑点**：`img_url_list` 列必须是单个URL字符串。如果写成 JSON 数组 `["url1","url2"]`，后端会将整个 JSON 字符串当作 URL 解析，报"图片格式不支持"错误。

### 2. 上传 xlsx 文件

在浏览器页面上下文中通过 `fetch()` 上传：

```javascript
// 在浏览器控制台执行（需要先读取 xlsx 文件为 base64）
// 方式一：通过 input[type=file] 获取文件对象
// 方式二：从 OSS URL 获取（如果文件已在 OSS）

var formData = new FormData();
formData.append('file', fileObject); // fileObject 是 File 对象

fetch('/api/file/upload', {
  method: 'POST',
  credentials: 'include',
  body: formData
}).then(r => r.json()).then(d => {
  window.__uploadResult = d;
  // d.data 即为 OSS URL
});
```

**注意**：浏览器中异步操作需用 `window.__var` 全局变量模式读取结果，后续调用中读取 `window.__uploadResult`。

### 3. 调用创建 API

**端点**：`POST /api/afd/review/task/main/create`

**完整 payload 结构**（从 JS bundle `dt()` 函数逆向还原）：

```javascript
fetch('/api/afd/review/task/main/create', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-AFD-Emp-Identity': 'f88'    // ⚠️ 必须！f88 租户写死（永不建 afd）
  },
  body: JSON.stringify({
    // 基础字段
    taskName: '任务名称',
    nodeId: 169,                    // 审核节点ID，从节点列表API获取
    dataFileUrl: 'https://...',     // 步骤2上传返回的OSS URL
    standardIds: [140],             // 审核标准ID数组
    priority: 0,                    // 0=P0
    expectedDeliveryTime: '2026-06-17 12:00:00',
    difficulty: 2,
    efficiency: 500,

    // 嵌套对象：任务分配配置
    allocation: {
      roles: ['reviewer'],
      requiredTagIds: [],
      participants: [{ userId: '421225', userName: '宗育', count: 5 }],
      allocationMethod: 2           // 1=均匀分配, 2=按比例, 3=自动分配
    },

    // 嵌套对象：抽检配置
    inspectionConfig: {
      enabled: false,
      participantUserIds: [],
      distributionType: 1,
      sampleSourceUserIds: [],
      ratio: 0,
      maxCountPerUser: 0,
      perPersonCount: 0
    },

    // 嵌套对象：埋雷配置
    buryConfig: {
      enabled: false,
      ratio: 0,
      maxCountPerUser: 0,
      perPersonCount: 0
    },

    distributionLogic: 1
  })
}).then(r => r.json()).then(d => {
  // d.data = 新创建的 taskId
});
```

### 4. 验证创建结果

**API 验证**（同样需要带 `X-AFD-Emp-Identity` header）：
```javascript
// 在浏览器中用 fetch 验证时，同样必须带 header
fetch('/api/afd/review/task/main/parentReviewTaskDetail?taskId={taskId}', {
  credentials: 'include',
  headers: { 'X-AFD-Emp-Identity': 'f88' }
}).then(r => r.json()).then(d => { window.__detail = d; });

fetch('/api/afd/review/task/main/detail?taskId={taskId}', {
  credentials: 'include',
  headers: { 'X-AFD-Emp-Identity': 'f88' }
}).then(r => r.json()).then(d => { window.__detail2 = d; });
```

**数据库验证**（g_afd_review_job 表，3层结构）：

| job_type | 含义 | 示例 |
|----------|------|------|
| 0 | 主任务 | 对应 taskId |
| 4 | 子任务组 | 分配给审核人的子任务 |
| 1 | 审核条目 | xlsx 中每行数据对应一条 |

```sql
SELECT id, job_type, parent_job_id,
       JSON_EXTRACT(info, '$.coverImageAuditContent.taoCate') AS tao_cate
FROM g_afd_review_job
WHERE id = {taskId} OR parent_job_id = {taskId};
```

## 常用 API 速查

> **所有 `/api/afd/` 开头的请求都必须在 headers 中携带 `X-AFD-Emp-Identity: f88`（写死）**。测试数据只建在 f88 租户、永不建 afd 租户。

| API | 方法 | 用途 |
|-----|------|------|
| `/api/file/upload` | POST multipart | 上传文件，返回 OSS URL（无需 header） |
| `/api/afd/review/task/main/create` | POST JSON | 创建审核任务（**需要 header**） |
| `/api/afd/review/task/main/list` | POST JSON | 任务列表（支持分页和筛选，**需要 header**） |
| `/api/afd/review/task/main/detail` | GET | 任务详情（**需要 header**） |
| `/api/afd/review/task/main/parentReviewTaskDetail` | GET | 主任务+子任务详情（**需要 header**） |
| `/api/afd/review/node/list` | POST | 审核节点列表，获取 nodeId（**需要 header**） |
| `/api/afd/review/standard/list` | POST | 审核标准列表，获取 standardIds（**需要 header**） |
| `/api/afd/review/permission/users` | POST | 可分配用户列表（**需要 header**） |

## 常见错误与排查

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| 任务分配配置不能为空 | allocation 字段未嵌套在 `allocation` 对象中 | 使用嵌套结构 `allocation: { roles, participants, allocationMethod }` |
| 数据文件URL不能为空 | 字段名错误（如用了 `excelFile`） | 正确字段名是 `dataFileUrl` |
| 图片格式不支持 | xlsx 中 img_url_list 列包含 JSON 数组 | 改为单个 URL 字符串 |
| 未知异常;null | payload 结构不正确或字段类型不匹配 | 检查嵌套对象结构是否完整 |
| 任务创建成功但在 F88 页面看不到 | fetch() 未带写死的 `X-AFD-Emp-Identity: f88` header，请求没落到 f88 租户 | 所有 `/api/afd/` 请求都加上写死的 `'X-AFD-Emp-Identity': 'f88'` header |

## 技术要点

1. **JS bundle 分析**：前端代码在 `https://dev.g.alicdn.com/industry-source-code/iFashion-tools/{version}/js/index.js`，可用 `curl` 下载后用 Python 搜索关键函数
2. **`dt()` 函数**：负责将表单 flat 字段转换为 API 嵌套结构，是理解 payload 格式的关键
3. **浏览器异步模式**：`fetch()` 在 javascript_tool 中无法直接返回值，必须存到 `window.__var` 后在后续调用中读取
4. **questionType 对照**：2=套图审核，3=视频审核，4=首图审核（多选多）
5. **`X-AFD-Emp-Identity` header 机制（v2.0.0 关键发现）**：前端 axios 实例 `Aq` 注册了全局请求拦截器，从 Redux store 的 `tenant.currentIdentity` 读取值并注入到每个请求的 header 中：
   ```javascript
   // JS bundle 中的拦截器源码
   Aq.interceptors.request.use(function(t) {
     var e = r1.getState().tenant.currentIdentity;
     return e ? {...t, headers: {...t.headers, "X-AFD-Emp-Identity": e}} : t;
   });
   ```
   直接用 `fetch()` 不经过 axios 拦截器，因此不会带这个 header。服务端根据此 header 判断租户归属——不带 header 的请求默认归入 afd 租户。注意：`cacheEmployeeIdentity` API 即使返回 `{success: true, data: true}` 也不能可靠地切换服务端租户上下文，**唯一可靠的控制方式是通过请求 header**。
6. **租户身份相关 API**：
   - `GET /api/tenant/queryEmployeeIdentityList` — 查询可用身份和 cachedIdentity
   - `POST /api/tenant/cacheEmployeeIdentity` — `{tenantId: "f88"}` — 返回 success 但不可靠
   - `POST /api/tenant/queryTenantMenu` — 查询当前租户菜单
   - 前端切换租户时 `Promise.all([queryTenantMenu(), cacheEmployeeIdentity()])` 并行调用，但真正控制 API 行为的是 header

## 视频审核模板结构（questionType=3，8列）

| 列名 | 说明 | 必填 |
|------|------|------|
| video_url | 待审核视频URL（单个URL字符串） | 必填 |
| video_cover_url | 视频封面URL | 选填 |
| img_url_reference_1~3 | 辅助审核图URL | 选填 |
| tao_cate | 淘系类目 | 必填 |
| seller_id | 商家ID | 选填 |
| extra_info | 其他信息 | 选填 |

**视频审核创建参数参考**：
- nodeId: 137（视频审核）
- standardIds: [143]（视频审核标准）
- roles: ["productOperations"]
- efficiency: 12, difficulty: 1

**xlsx 生成方式**：浏览器中加载 SheetJS（`https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js`），用 `XLSX.utils.aoa_to_sheet` 生成后通过 Blob + FormData 上传，避免 base64 传递导致的文件损坏问题。
