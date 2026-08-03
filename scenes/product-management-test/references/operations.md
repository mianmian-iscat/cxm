# 操作说明

> 完整操作知识 → `knowledge/xiaoer-product-mgmt.json`

## 一、行内操作按钮分布

| 按钮 | 位置 | 说明 |
|------|------|------|
| 查看详情 | 主操作列 | ⚠️ 打开「商品运营周期」Modal，不是 SKU 详情 |
| 试销完成 | 主操作列 | 标记试销阶段完成 |
| 查看商品信息 | 主操作列 | 查看平台商品信息面板 |
| 商品下架 | 主操作列 | SKC 级别下架 |
| 查看库存 | 主操作列 | 展开 SKU 库存面板 |
| **更多** | 主操作列 | 展开下拉菜单，含以下操作 |
| 查看sku详情 | 更多菜单 | SKU 级别详情 + 上下架开关 |
| 提报价调价 | 更多菜单 | 修改提报价 |
| 日销价调价 | 更多菜单 | 修改日销价，触发调价接口 |
| 开启复色 | 更多菜单 | 开启复色 |
| 淘汰 | 更多菜单 | 标记淘汰 |

## 二、调价接口（实测数据，2026-04-21）

### 2.1 checkTriggerApprove

```json
POST /cobweb/api/...adjustPrice.checkTriggerApprove
请求体示例：
{
  "itemId": 1043532365715,
  "contentDTO": [
    { "skuId": 6066032844176, "offerPrice": 23, "dailySellTargetPrice": 43.75 }
  ]
}
响应：{ "data": { "needApprove": false } }
```

### 2.2 startAdjustdailySellPrice

```json
POST /cobweb/api/...adjustPrice.startAdjustdailySellPrice
请求体示例：
{
  "itemId": 1043532365715,
  "contentDTO": [
    { "skuId": 6066032844176, "dailySellTargetPrice": 43.75 }
  ]
}
响应：{ "code": "OK", "data": { "data": 3912 } }  ← data.data 为调价任务 ID
```

## 三、SKU 上下架接口（实测数据，2026-04-22）

```json
POST /cobweb/api/...fsShopItem.submitSkuShelf
响应：HTTP 200，页面 toast 显示「SKU上下架操作成功」
提交后页面自动刷新列表（searchSkcV2 重新请求）
```

## 四、操作流程模板

### 4.1 搜索商品

```javascript
async function searchProduct(page, { fieldLabel, value }) {
  // 清空已有筛选
  const resetBtn = await page.$('button:has-text("重置")');
  if (resetBtn) await resetBtn.click();
  await new Promise(r => setTimeout(r, 300));

  // 填写筛选条件
  await fillSearchField(page, fieldLabel, value);

  // 点击搜索
  const searchBtn = await page.$('button:has-text("搜索")');
  await searchBtn.click();

  // 等待表格加载
  await page.waitForSelector('[class*="tbd-table-row"]', { visible: true, timeout: 10000 });
}
```

### 4.2 日销价调价完整流程

```javascript
async function adjustDailySellPrice(page, { productId, newPrice }) {
  // 1. 搜索商品
  await searchProduct(page, { fieldLabel: '平台商品ID', value: productId });

  // 2. 展开「更多」菜单
  const row = await findRow(page, productId);
  const moreBtn = findRowAction(row, '更多');
  await moreBtn.click();
  await new Promise(r => setTimeout(r, 300));

  // 3. 点击「日销价调价」
  const menuItem = [...document.querySelectorAll('.ant-dropdown-menu-item')]
    .find(el => el.innerText.trim() === '日销价调价');
  await menuItem.click();

  // 4. Drawer 内填写新价格
  await page.waitForSelector('.ant-drawer-content', { visible: true });
  const priceInput = await page.$('.ant-drawer-content input[placeholder*="日销价"]');
  await priceInput.click({ clickCount: 3 });
  await priceInput.type(String(newPrice));

  // 5. 提交
  const submitBtn = await page.$('.ant-drawer-content button:has-text("确定")');
  await submitBtn.click();

  // 6. 验证
  await page.waitForFunction(
    () => document.body.innerText.includes('操作成功'),
    { timeout: 10000 }
  );
}
```

### 4.3 SKU 上下架完整流程

```javascript
async function toggleSkuShelf(page, { productId, skuId, action }) {
  // action: 'on' | 'off'
  await searchProduct(page, { fieldLabel: '平台商品ID', value: productId });

  // 展开更多菜单 → 查看sku详情
  const row = await findRow(page, productId);
  await findRowAction(row, '更多').click();
  await new Promise(r => setTimeout(r, 300));
  const menuItem = [...document.querySelectorAll('.ant-dropdown-menu-item')]
    .find(el => el.innerText.trim() === '查看sku详情');
  await menuItem.click();

  // Modal 内找到目标 SKU 行
  await page.waitForSelector('.ant-modal-content', { visible: true });
  const skuRow = await page.evaluateHandle((sid) => {
    const rows = document.querySelectorAll('.ant-modal-content tr');
    return [...rows].find(r => r.innerText.includes(sid));
  }, skuId);

  // 切换开关
  const toggle = await skuRow.$('.ant-switch');
  const isChecked = await toggle.evaluate(el => el.classList.contains('ant-switch-checked'));
  if ((action === 'on' && !isChecked) || (action === 'off' && isChecked)) {
    await toggle.click();
  }

  // 等待 toast
  await page.waitForFunction(
    () => document.body.innerText.includes('SKU上下架操作成功'),
    { timeout: 10000 }
  );
}
```

## 五、常见坑点总结

| 场景 | 问题 | 解决方案 |
|------|------|----------|
| 筛选字段 | 两个相同 placeholder 输入框 | 用 label 定位而非 index |
| 更多菜单 | dropdown 挂在 body | 必须从 document 级查找 |
| 调价 | 提交后可能需审批 | 先调 checkTriggerApprove |
| 表格行 | loading 未完成时操作 | 先 waitForFunction 等 spin 消失 |
| SKU开关 | 开关状态未检查 | 先读 ant-switch-checked 再决定是否点击 |
