---
name: f88-template-package-create
description: Creates F88 tenant template packages on pre-aifashion-xiaoer platform via browser automation. Use when the user asks to create/新建 F88 模板包 / template package test data, or constructs F88 (not AFD) test data on stylespot-admin. Handles tenant header injection, naming convention, env/scene selection, and post-creation verification.
version: 1.0.0
---

# F88 模板包创建技能

> 📋 F88 测试商家 seller_id 统一维护入口：[test-accounts.md](../web-automation/knowledge/synced-qoderwork/f88-test/test-accounts.md)

## 适用场景
用户要求在 `pre-aifashion-xiaoer.alibaba-inc.com/templateManagement` 下为 F88 租户构造模板包测试数据。**AFD 租户不适用本技能**。

## 关键事实（必读）
- **多租户机制**：后端通过 HTTP Header `X-AFD-Emp-Identity` 区分租户，缺失时默认 `afd`。即使 UI 切到了 F88，手工 fetch 不带 header 仍会落到 AFD 租户。
- **测试店铺**：`sellerId = 2219662018344`（库 5300 万+图）。
- **模板包 = 环节 × 场景**的排列组合。
- **状态枚举**：0=删除 / 1=DRAFT / 2=REVIEWING / 3=IDLE / 4=IN_USE / 5=REJECTED；同 `sellerId+applyRange+applyScene` 仅允许一个 IN_USE。`skipReview:true` 直接落到 IDLE(3)。

## F88 枚举映射
环节 (applyRange)：
- 搭配 → `COLLOCATION`
- 视觉 → `VIEW`
- 套图 → `SET`
- 视频 → `VIDEO`

场景 (applyScene)：
- 主图（F88主图素材）→ `F88_MAIN_IMAGE`
- 种草（F88种草素材）→ `F88_SEEDING`

## 命名规范
`mmtest_{场景中文}{环节中文}{月日}`，例：`mmtest_主图搭配622`。

## 工作流（每次创建必走）

### Step 1 — 询问环节与场景
**默认值**：环节=搭配，场景=主图。
若用户未明确，使用 AskUserQuestion 让用户从环节×场景下拉项中选择，或确认采用默认。

### Step 2 — 切身份到 F88 并校验
打开 `https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement`，确认右上角身份切到 F88。**不要只看 UI**，下一步发请求时强制带 header。

### Step 3 — 通过浏览器 javascript_tool 创建
必须使用 builtin_browser 的 `javascript_tool` (action=`javascript_exec`)，且：
1. fetch headers 必含 `'X-AFD-Emp-Identity':'f88'`、`'Content-Type':'application/json'`。
2. Promise 结果用 `window.__pkg_create_result` 暂存，下一次调用读出（javascript_tool 直接 return Promise 会拿到 undefined）。
3. body 关键字段：
   - `sellerId: 2219662018344`
   - `applyRange`: 见映射
   - `applyScene`: 见映射
   - `skipReview: true`（跳过审核直接到 IDLE）
   - `packageName`: 按命名规范（**注意：字段名是 packageName，不是 name**）
   - `templateIds`: 模板 UUID 字符串数组（从 queryTemplatesByConditions 获取 templateId）
   - `templateList`: 完整模板对象数组（从 queryTemplatesByConditions 获取的完整记录）
   - **templateIds 和 templateList 必须同时提供，否则报"模板ID列表不能为空"或"模板内容列表不能为空"**

示例骨架（先获取模板数据，再创建）：
```js
// Step A: 获取模板数据
window.__tpl_data = null;
fetch('/api/template/library/queryTemplatesByConditions', {
  method: 'POST', credentials: 'include',
  headers: {'Content-Type':'application/json','X-AFD-Emp-Identity':'f88'},
  body: JSON.stringify({sellerId: 2219662018344, pageNo:1, pageSize:5})
}).then(r=>r.json()).then(d=>{ window.__tpl_data = d.data.content||[]; });
'started';
```
下一次调用读取 `window.__tpl_data`，然后：
```js
// Step B: 创建模板包
var tpls = window.__tpl_data;
var ids = tpls.map(t=>t.templateId);
window.__pkg_create_result = null;
fetch('/api/template/package/create', {
  method: 'POST', credentials: 'include',
  headers: {'Content-Type':'application/json','X-AFD-Emp-Identity':'f88'},
  body: JSON.stringify({
    sellerId: 2219662018344,
    packageName: 'mmtest_主图搭配622',
    applyRange: 'COLLOCATION',
    applyScene: 'F88_MAIN_IMAGE',
    skipReview: true,
    templateIds: ids,
    templateList: tpls
  })
}).then(r=>r.json()).then(d=>{ window.__pkg_create_result = d; });
'started';
```
下一次调用：`JSON.stringify(window.__pkg_create_result)`。

### Step 4 — 创建后验证
强制带 `X-AFD-Emp-Identity: f88` 调 `/api/template/package/list` 或 `queryTemplatesByConditions`，断言新建记录 `tenantId === 'f88'`。若返回 `tenantId === 'afd'`，说明 header 没生效，必须立刻删除并重建。

## 常见坑
- **租户错位**：不带 header → 落到 AFD。必排查项。
- **删错租户记录**：用 F88 header 删 AFD 创建出来的脏数据会得到「模板包不存在」，需切回 `X-AFD-Emp-Identity: afd` 删。
- **Ant Select 不张开**：必须 `dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}))`，单纯 `.click()` 无效。
- **同唯一键冲突**：同 sellerId+applyRange+applyScene 已存在 IN_USE 时新建会被拒。

## 验证清单
- [ ] 创建返回 success 且拿到 packageId
- [ ] list 接口回查 `tenantId === 'f88'`
- [ ] `name` 命名符合 `mmtest_{场景}{环节}{月日}`
- [ ] `status` 为 3（IDLE，若 skipReview=true）
