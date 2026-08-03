---
name: web-automation/product-management-test
description: 淘宝品质联盟运营工作台「商品中心：平台商品管理」页面的自动化测试操作。用于：(1) 查询商品列表（按状态/类目/买手等筛选），(2) 读取商品状态统计，(3) 执行商品操作（查看SKU详情、SKU上下架、调价、试销完成、商品下架等），(4) 调价接口抓包验证。触发词：品质联盟商品、平台商品管理、商品列表查询、商品状态、SKU详情、SKU上下架、提报价调价、日销价调价、试销完成、商品下架。
parent: web-automation
---

# 商品中心：平台商品管理

> 场景化 Skill。页面结构、字段选择器、API 信息、已知坑点均在
> `web-automation/knowledge/xiaoer-product-mgmt.json` 中，执行前必须先读取。

## 页面信息

| 项目 | 值 |
|------|---|
| URL | `https://xiaoer.alibaba-inc.com/bzb/fsyx_quality_guard/quality-pulse/product-management?opGroupId=2.61036.61036.0.61036` |
| Knowledge ID | `xiaoer-product-mgmt` |
| UI 框架 | tbd-formily（类名前缀 `tbd-`） |
| 认证 | 阿里内网 SSO |

## 标准操作动线

### 1. 搜索商品

```
取消「仅看我的」（默认勾选）
  → 填入筛选条件（平台商品ID / 供给商品ID / 买手等）
  → 点「搜索」
  → 等待 searchSkcV2 接口返回（约 3s）
  → 断言「总共 N 个 SKC」出现
```

⚠️ 「仅看我的」取消后才能搜到全量数据；重置会重新勾上，需再次取消。

### 2. 查看 SKU 详情 / SKU 上下架

```
定位目标商品行（用平台商品ID或标题）
  → 点「更多」按钮（行内操作列）
  → 等待 800-1000ms，菜单出现
  → 取「查看sku详情」li 的坐标点击（坐标必须在菜单渲染后获取）
  → 弹出 SKU 详情 Modal（[role="dialog"]）
  → 用 TreeWalker 定位目标 SKU 文本节点，找同行 switch（y 差值 < 60）
  → 点击 switch button 切换上/下架（不要点子 span）
  → 点弹窗底部「提交」
  → 等待 toast「SKU上下架操作成功」
  → 验证：重新打开弹窗，aria-checked 值符合预期
```

⚠️ 「查看详情」≠ SKU 详情，它打开的是商品运营周期 Modal。SKU 详情在「更多」菜单里。

### 3. 日销价调价

```
点目标行「更多」→「日销价调价」
  → 填写新价格
  → 点「下一步」，等待 checkTriggerApprove 接口（验证是否需要审批）
  → 点「提交」，等待 startAdjustdailySellPrice 接口
  → 断言响应中 data.data（调价任务ID）有值
```

### 4. 读取状态统计

顶部 Tab 显示各状态商品数，格式为「状态名 (N)」。用正则从 `document.body.innerText` 提取即可，无需特殊选择器。

## 断言规范

| 断言目标 | 方式 | 原因 |
|---------|------|------|
| 有搜索结果 | `target=page`，contains「总共」 | 可靠 |
| 买手名 | `target=api`，searchSkcV2 响应的 `content[].buyerName` | 商品标题可能含买手名，page 断言会误判 |
| SKU 上下架状态 | DOM 重新打开弹窗，验证 `aria-checked` | 提交后 DOM 已更新，但建议重开弹窗确认 |
| 调价成功 | `target=api`，startAdjustdailySellPrice 响应的 `data.data` 非空 | 最可靠 |

## 关键坑点（速查）

详细坑点见 `web-automation/knowledge/xiaoer-product-mgmt.json` 的 `knownIssues`。

1. 平台商品ID 是第 **1** 个（index=1）`placeholder='多个ID以英文逗号分隔'` 输入框，供给商品ID 是第 0 个
2. 「更多」菜单 li 坐标必须在菜单渲染后（等 800-1000ms）再取，否则拿到 (0,0)
3. 水印 `.wm_div_id` 每次操作前都要清除
4. SKU 详情 Modal 中 switch 定位用 TreeWalker 找 SKU 名 → 匹配相近 y 坐标的 switch
