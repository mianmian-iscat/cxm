# 页面结构

> 详细 JSON 知识 → `knowledge/xiaoer-product-mgmt.json`

## 一、页面 URL 与路由

| 环境 | URL |
|------|-----|
| 预发 | `https://pre-xiaoer.alibaba-inc.com/quality-pulse/product-management` |
| 线上 | `https://xiaoer.alibaba-inc.com/quality-pulse/product-management` |

## 二、筛选区字段（重要：两个相同 placeholder 的输入框）

```javascript
// ⚠️ 两个输入框 placeholder 完全一样，必须用 index 区分
input[placeholder='多个ID以英文逗号分隔'][index=0]  // ← 供给商品ID
input[placeholder='多个ID以英文逗号分隔'][index=1]  // ← 平台商品ID
```

**坑点**：混淆这两个会把平台商品ID填到供给商品ID里，导致搜不到结果。

### 鲁棒定位方案

```javascript
async function fillSearchField(page, fieldLabel, value) {
  // 通过表单项 label 定位，避免 index 硬编码
  const labels = await page.$$('.ant-form-item-label');
  for (const label of labels) {
    const text = await label.evaluate(el => el.innerText.trim());
    if (text.includes(fieldLabel)) {
      const formItem = await label.evaluateHandle(el => el.closest('.ant-form-item'));
      const input = await formItem.$('input');
      if (input) {
        await input.click({ clickCount: 3 });
        await input.type(value);
        return true;
      }
    }
  }
  return false;
}
```

## 三、状态 Tab 选择器

```javascript
// Tab 列表
document.querySelectorAll('.ant-tabs-tab')
// 状态统计读取
document.body.innerText.match(/(全部|待可售|出售中|仓库中|已淘汰|核价中|调价中)\s*\((\d+)\)/g)
```

## 四、表格行选择器

```javascript
// 通用行定位
const rows = [...document.querySelectorAll('[class*="tbd-table-row"]')]
  .filter(el => el.offsetParent !== null); // 过滤不可见行

// 按商品ID/标题定位具体行
function findRow(rows, identifier) {
  return rows.find(row => row.innerText?.includes(identifier));
}

// 行内操作按钮定位
function findRowAction(row, buttonText) {
  const buttons = row.querySelectorAll('a, button, [role="button"]');
  return [...buttons].find(btn => btn.innerText.trim() === buttonText);
}
```

## 五、"更多"下拉菜单

```javascript
// 1. 找到行内「更多」按钮
const moreBtn = findRowAction(row, '更多');
await moreBtn.click();
await new Promise(r => setTimeout(r, 300));

// 2. 从 body 级 dropdown 中选择
const items = [...document.querySelectorAll('.ant-dropdown-menu-item')];
const target = items.find(el => el.innerText.trim() === '查看sku详情');
target.click();
```

**坑点**：dropdown 挂在 body 而非行内，必须从 document 级查找。

## 六、Modal / Drawer 组件

| 组件 | 场景 | 选择器 |
|------|------|--------|
| SKU 详情 Modal | 「更多→查看sku详情」 | `.ant-modal-content` 内含 SKU 表格 |
| 商品运营周期 Modal | 「查看详情」 | `.ant-modal-content` 内含时间轴 |
| 调价 Drawer | 「更多→日销价调价」 | `.ant-drawer-content` |

## 七、关键 DOM 状态检查

```javascript
// 等待表格加载完成
await page.waitForSelector('[class*="tbd-table-row"]', { visible: true, timeout: 10000 });

// 确认 loading 消失
await page.waitForFunction(() => {
  return !document.querySelector('.ant-spin-spinning');
}, { timeout: 10000 });

// Toast 消息捕获
page.on('console', msg => {
  if (msg.text().includes('操作成功')) { /* 验证通过 */ }
});
```
