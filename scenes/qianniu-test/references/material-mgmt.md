# 千牛素材管理页面测试

## 概述

千牛素材管理页面分为 **三个核心区域**，从上到下依次排列。每个区域的交互方式和测试关注点不同。

## 页面 URL

```
https://qn.wapa.taobao.com/home.htm/material-center/material-management?tab={tab}&subTab={subTab}
```

### URL 参数映射

| 二级 Tab | `tab` 参数 | `subTab` 参数 |
|---------|-----------|-------------|
| 基础素材 | `basic` | - |
| 活动素材 | `activity` | - |
| 搜推素材 | `recommend` | `SCU`（搭配） / `singleProduct`（单品） / `multiProduct`（多品） |
| 商详素材托管 | `detailMaterial` | - |

---

## 页面三区域总览

```
┌──────────────────────────────────────────────────────────┐
│ 千牛 Header + 二级 Tab（基础素材 | 活动素材 | 搜推素材 | 商详） │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 区域一：搜推素材质量诊断（顶部固定）                   │  │
│  │ · 经营情况周报                                       │  │
│  │ · 固定展示，不可交互操作                              │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 区域二：搜推素材拿量效果（中间数据面板）               │  │
│  │ · 筛选条件：消费场域 / 素材类型 / 统计时间             │  │
│  │ · 数据指标卡片（4个主指标 + 来源分解）                │  │
│  │ · 展开数据趋势                                       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 区域三：素材管理列表（底部列表）                       │  │
│  │ · 三级筛选 + 创建/批量操作                            │  │
│  │ · 表格数据 + 行操作（查看/编辑/删除）                  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 区域一：搜推素材质量诊断（顶部固定）

### 特点
- **静态展示区**，无可交互操作
- 每周一更新，显示上周经营情况总结
- 内容包括诊断建议（如"发布一条精选素材后最多可获得 3000 曝光扶持"）

### 结构
```
┌──────────────────────────────────────────┐
│ · 每周一更新你的专属智能诊断+素材建议      │
│ 上周素材经营情况总结                       │
│ 2026.04.06 - 2026.04.12                  │
│ 诊断内容文本...                           │
└──────────────────────────────────────────┘
```

### 测试关注点
| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 周报日期 | 日期范围是否正确对应上一周 |
| 2 | 诊断内容 | 文案是否正常显示，不为空 |
| 3 | 扶持信息 | 曝光扶持数值是否合理 |

### 数据读取

```javascript
const diagInfo = await page.evaluate(() => {
  const text = document.body.innerText;
  const weekMatch = text.match(/(\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})/);
  const diagText = text.includes('上周素材经营情况总结');
  return {
    weekRange: weekMatch ? `${weekMatch[1]} - ${weekMatch[2]}` : null,
    hasDiagContent: diagText
  };
});
```

---

## 区域二：搜推素材拿量效果（中间数据面板）

### 特点
- **核心交互区**，涉及 **点击操作** 和 **日期组件切换**
- 操作后需要 **检查数据变化**
- 包含筛选条件 → 数据指标卡片 → 来源分解 → 趋势展开

### 结构
```
┌──────────────────────────────────────────────────────────┐
│ 消费场域: [推荐] [搜索]                                    │
│ 素材类型: [全部] [图文] [视频]                               │
│ 统计时间 2026-03-31: [日] [近7日] [近30日]                  │
├──────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│ │猜你喜欢   │ │全屏页     │ │推荐首触   │ │推荐首触   │     │
│ │曝光人数   │ │浏览人数   │ │支付订单数  │ │支付金额   │     │
│ │    0     │ │    0     │ │    0     │ │  0.00   │     │
│ │较前1日    │ │较前1日    │ │较前1日    │ │较前1日    │     │
│ │同行平均 10│ │同行平均 18│ │同行平均 2 │ │同行平均   │     │
│ └──────────┘ └──────────┘ └──────────┘ │163.00   │     │
│                                        └──────────┘     │
│ 曝光来源分解:                                             │
│   千牛素材中心=0 | 光合平台=0 | 商品视频=0 | 其他=0          │
│                                                          │
│ [展开数据趋势]                                            │
└──────────────────────────────────────────────────────────┘
```

### 交互操作

#### 1. 消费场域切换（点击操作）

切换"推荐"/"搜索"场域，数据指标会联动变化。

```javascript
// 点击"搜索"场域
await page.evaluate(() => {
  const items = Array.from(document.querySelectorAll('[class*="filter-content-item"]'));
  const target = items.find(el => el.innerText?.trim() === '搜索');
  if (target) target.click();
});
await new Promise(r => setTimeout(r, 2000)); // 等待数据刷新
```

> CSS class 前缀：`ContentFilter_filter-content-item__`，带 `active` 后缀表示选中态

#### 2. 素材类型切换（点击操作）

切换"全部"/"图文"/"视频"类型筛选。

```javascript
await page.evaluate((typeName) => {
  const items = Array.from(document.querySelectorAll('[class*="filter-content-item"]'));
  const target = items.find(el => el.innerText?.trim() === typeName);
  if (target) target.click();
}, '图文');
await new Promise(r => setTimeout(r, 2000));
```

#### 3. 日期组件切换（点击操作 — 重点）

三个选项：日 / 近7日 / 近30日。点击后统计时间和指标数据会联动变化。

```javascript
// 切换到"近7日"
await page.evaluate(() => {
  const items = Array.from(document.querySelectorAll('[class*="filter-content-item"]'));
  const target = items.find(el => el.innerText?.trim() === '近7日');
  if (target) target.click();
});
await new Promise(r => setTimeout(r, 2000));

// 验证统计时间已更新
const dateAfter = await page.evaluate(() => {
  const text = document.body.innerText;
  const match = text.match(/统计时间\s*(\d{4}-\d{2}-\d{2})/);
  return match?.[1];
});
console.log('切换后日期:', dateAfter);
```

#### 4. 展开数据趋势（点击操作）

```javascript
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('span, div, a'))
    .find(el => el.innerText?.trim()?.includes('展开数据趋势') && el.offsetParent);
  if (btn) btn.click();
});
await new Promise(r => setTimeout(r, 2000));
// 展开后会显示折线图/趋势图
```

### 数据检查

操作筛选条件后，需要验证数据指标是否正确刷新：

```javascript
async function readStatsPanel(page) {
  return await page.evaluate(() => {
    const text = document.body.innerText;
    const extract = (label) => {
      // 匹配指标: 值 + 环比 + 同行均值
      const regex = new RegExp(label + '\\n([\\d,.]+)\\n较前1日\\n同行同层平均\\n([^\\n]+)\\n([\\d,.]+)');
      const m = text.match(regex);
      return m ? { value: m[1], trend: m[2], average: m[3] } : null;
    };
    
    const metrics = {
      exposure: extract('猜你喜欢曝光人数'),
      pageView: extract('全屏页浏览人数'),
      orders: extract('推荐首触支付订单数'),
      gmv: extract('推荐首触支付金额')
    };
    
    // 来源分解
    const sources = {};
    ['千牛素材中心', '光合平台', '商品视频', '其他'].forEach(name => {
      const m = text.match(new RegExp(name + '\\n(\\d+)'));
      if (m) sources[name] = parseInt(m[1]);
    });
    
    // 当前筛选状态
    const dateMatch = text.match(/统计时间\s*(\d{4}-\d{2}-\d{2})/);
    
    return { metrics, sources, statsDate: dateMatch?.[1] };
  });
}
```

### 测试场景

| # | 场景 | 操作 | 验证点 |
|---|------|------|--------|
| 1 | 场域切换 | 点击"推荐"→"搜索" | 指标数据刷新，指标名称可能变化 |
| 2 | 素材类型切换 | 点击"全部"→"图文"→"视频" | 数据按类型过滤 |
| 3 | 日期切换-日 | 点击"日" | 统计时间显示具体日期，指标为单日数据 |
| 4 | 日期切换-7日 | 点击"近7日" | 统计时间变化，指标为7日汇总 |
| 5 | 日期切换-30日 | 点击"近30日" | 统计时间变化，指标为30日汇总 |
| 6 | 组合筛选 | 切换场域+类型+日期 | 多条件组合后数据正确 |
| 7 | 环比数据 | 查看"较前1日" | 趋势方向（持平/上升/下降）正确 |
| 8 | 同行对比 | 查看同行同层平均 | 均值数据合理 |
| 9 | 来源分解 | 查看曝光来源 | 各来源之和 ≈ 总曝光（并集关系） |
| 10 | 展开趋势 | 点击"展开数据趋势" | 趋势图/折线图正确展示 |

---

## 区域三：素材管理列表（底部列表）

### 特点
- 涉及 **查询/筛选** 操作
- 行操作会触发 **同页跳转**（编辑搭配）或 **弹窗**（查看商品及预览）
- 编辑页面涉及 **文件上传**（图片上传）
- 页面是 SPA，"编辑搭配"通过路由跳转，不会新开 tab

### 结构
```
┌──────────────────────────────────────────────────────────┐
│ 素材类型: [搜推] [单品素材] [多品素材] [店铺装修] [搭配素材]  │
│ [清除条件]                                                │
├──────────────────────────────────────────────────────────┤
│ [创建图文搭配] [创建视频搭配]  已选 0 条 [批量删除] [批量导出] │
├──────────────────────────────────────────────────────────┤
│ ☐ | 封面 | 搭配标题/ID | 搭配商品ID | 时间 | 类型 | 状态   │
│   | 同步渠道 | 操作                                       │
├──────────────────────────────────────────────────────────┤
│ ☐ | 📷 | 黑名单测试04  | 941371...  | 2025-07-04 | 图文  │
│   |     | ID 3260821.. | 944851...  |            | 搭配  │
│   |     |              | 947032...  |            |       │
│   | 完整/已下架 | 商品详情 | [查看] [编辑搭配] [删除]        │
├──────────────────────────────────────────────────────────┤
│                    上一页 1 下一页                         │
└──────────────────────────────────────────────────────────┘
```

### 交互操作

#### 1. 三级筛选（查询操作）

素材类型筛选：搜推 / 单品素材 / 多品素材 / 店铺装修 / 搭配素材

```javascript
// 切换筛选
await page.evaluate((filterName) => {
  const items = Array.from(document.querySelectorAll('div, span'));
  const target = items.find(el =>
    el.innerText?.trim() === filterName && el.offsetParent &&
    el.getBoundingClientRect().y > 600  // 确保是列表区域的筛选，不是上方的
  );
  if (target) target.click();
}, '搭配素材');
await new Promise(r => setTimeout(r, 2000));
```

#### 2. 查看商品及预览（弹窗操作）

点击后弹出 `next-dialog` 弹窗，显示搭配详情：

```javascript
// 点击查看
await page.evaluate((title) => {
  const rows = Array.from(document.querySelectorAll('table tbody tr'));
  for (const row of rows) {
    if (row.innerText?.includes(title)) {
      const btn = Array.from(row.querySelectorAll('button'))
        .find(b => b.innerText?.trim() === '查看商品及预览');
      if (btn) btn.click();
      break;
    }
  }
}, '黑名单测试04');
await new Promise(r => setTimeout(r, 2000));

// 读取弹窗内容
const dialogContent = await page.evaluate(() => {
  const dialog = document.querySelector('.next-dialog-body');
  return dialog?.innerText;
});

// 弹窗结构：搭配标题 + 搭配ID + 商品个数 + 二维码 + 商品列表
// 操作按钮：确定 / 取消

// 关闭弹窗
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('.next-dialog-btn'))
    .find(b => b.innerText?.trim() === '取消' || b.innerText?.trim() === '确定');
  if (btn) btn.click();
});
```

**弹窗内容结构：**
```
┌──────────────────────────┐
│ 当前搭配                  │  ← 标题
├──────────────────────────┤
│ 搭配标题：黑名单测试04     │
│ 搭配id：326082100271      │
│ 商品个数：3               │
│ 手机淘宝扫码查看 [二维码]  │
│                          │
│ 1. 商品名称 ID 商品已下架  │
│ 2. 商品名称 ID 商品已下架  │
│ 3. 商品名称 ID 商品已下架  │
├──────────────────────────┤
│         [确定] [取消]     │
└──────────────────────────┘
```

#### 3. 编辑搭配（同页跳转 + 文件上传）

点击后 **SPA 路由跳转**到编辑页，不新开 tab。

```javascript
// 点击编辑 → 跳转到编辑页
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '编辑搭配' && b.offsetParent);
  if (btn) btn.click();
});
await new Promise(r => setTimeout(r, 3000));

// 跳转后 URL 变为:
// /home.htm/qianniu_dress_collocation/create?id={搭配ID}&bizFrom=myListEdit&source=sucaizhongxin&isNew=true
```

**编辑页结构：**
```
┌──────────────────────────────────────────┐
│ 搭配图片区域                              │
│ ┌────┐ ┌────┐ ┌──────────┐              │
│ │图片1│ │图片2│ │ 添加搭配图 │              │
│ │    │ │    │ │ [上传按钮] │              │
│ └────┘ └────┘ └──────────┘              │
│ 可上传1-9张，尺寸3:4，≥750x1000px         │
│ 支持JPG/PNG，<5MB                        │
├──────────────────────────────────────────┤
│ 所有涉及的宝贝                            │
│ · 商品名1                                │
│ · 商品名2                                │
│ · 商品名3                                │
├──────────────────────────────────────────┤
│ 搭配标题  [___________________] 7/20     │
│ 搭配正文  [___________________] 0/1000   │
│           [AI生成文案]                    │
├──────────────────────────────────────────┤
│ 素材同步说明：自动同步到商品详情、店铺        │
├──────────────────────────────────────────┤
│         [发布内容] [取消]                  │
└──────────────────────────────────────────┘
```

**编辑页字段：**

| 字段 | 类型 | 选择器 | 约束 |
|------|------|--------|------|
| 搭配标题 | textarea | `#title` (name="title") | 5-20 字 |
| 搭配正文 | textarea | `#description` (name="description") | 10-1000 字 |
| 搭配图片 | 文件上传 | 见下方 | 1-9 张，JPG/PNG，3:4，≥750×1000，<5MB |

**文件上传操作：**

> ⚠️ 编辑页**没有**标准的 `input[type="file"]`。点击"添加搭配图"后会打开一个**素材选择器弹窗**（iframe 内嵌 `sucai-selector-ng` 组件），在弹窗内再点"本地上传"才触发原生文件选择器。
>
> ⚠️ 上传按钮容易被"重要消息"通知面板遮挡，操作前必须先用 `closeAllPopups` + 遮挡清除。

**完整上传流程：**

```
编辑页 → 清除遮挡 → 点击"添加搭配图" → 素材选择器弹窗(iframe)
→ iframe 内点"本地上传" → 原生文件选择器 → 选择文件
→ 等待上传到CDN → 选择图片 → 点"确定" → 图片应用到编辑页
```

```javascript
// 步骤 1：清除遮挡层（关键！通知面板会挡住上传按钮）
await page.evaluate(() => {
  const btn = document.querySelector('[class*="restUploadCard"]');
  if (btn) {
    const r = btn.getBoundingClientRect();
    let topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    let attempts = 0;
    while (topEl && !btn.contains(topEl) && topEl !== btn && attempts < 10) {
      topEl.style.display = 'none';
      topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
      attempts++;
    }
  }
  document.querySelectorAll('[class*="notify_bg"],[class*="notify_body"]')
    .forEach(e => e.style.display='none');
  document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
});

// 步骤 2：点击"添加搭配图" → 打开素材选择器弹窗
await page.click('[class*="restUploadCard"]');
await new Promise(r => setTimeout(r, 3000));

// 步骤 3：找到素材选择器 iframe
const selectorFrame = page.frames()
  .find(f => f.url().includes('sucai-selector'));
if (!selectorFrame) throw new Error('未找到素材选择器 iframe');

// 步骤 4：iframe 内点"本地上传" + 拦截文件选择器
const [fileChooser] = await Promise.all([
  page.waitForFileChooser({ timeout: 8000 }),
  selectorFrame.evaluate(() => {
    Array.from(document.querySelectorAll('button'))
      .find(b => b.innerText?.trim() === '本地上传')?.click();
  })
]);

// 步骤 5：选择文件
await fileChooser.accept(['/path/to/image.jpg']);
await new Promise(r => setTimeout(r, 5000)); // 等上传到 CDN

// 步骤 6：选择图片（hover 显示 checkbox → click 选中）
// ⚠️ checkbox 仅 hover 时才可见，必须先 mouse.move 再 click
const targetRect = await selectorFrame.evaluate(() => {
  const items = document.querySelectorAll('[class*="PicturesShow_main-show"]');
  for (const item of items) {
    const text = item.innerText;
    if (!text.includes('不符合') && !text.includes('小于')) {
      const r = item.getBoundingClientRect();
      return { x: r.x + r.width/2, y: r.y + r.height/2 };
    }
  }
  return null;
});
const iframeRect = await page.evaluate(() => {
  const iframe = document.querySelector('iframe[src*="sucai-selector"]');
  const r = iframe.getBoundingClientRect();
  return { x: r.x, y: r.y };
});
// hover → click
await page.mouse.move(iframeRect.x + targetRect.x, iframeRect.y + targetRect.y);
await new Promise(r => setTimeout(r, 800));
await page.mouse.click(iframeRect.x + targetRect.x, iframeRect.y + targetRect.y);
await new Promise(r => setTimeout(r, 2000));

// 步骤 7：裁剪 → 确定（必须！即使已是 3:4 也要裁剪才能启用确定）
await selectorFrame.evaluate(() => {
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '裁剪')?.click();
});
await new Promise(r => setTimeout(r, 3000));
// 裁剪界面默认 3:4 裁剪框，直接点确定
await selectorFrame.evaluate(() => {
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '确定' && !b.disabled)?.click();
});
// ⚠️ 裁剪确定后 iframe 会 detach，不要再操作 selectorFrame
await new Promise(r => setTimeout(r, 5000));
```

**素材选择器弹窗结构（iframe 内）：**
```
┌─────────────────────────────────────┐
│ 选择图片                             │
│ 图片要求：≥750x1000 3:4 JPG/PNG <5MB │
├─────────────────────────────────────┤
│ Tab: [全部图片] [批量导入] [智能创作]   │
│ [本地上传] [隐藏不可用图片]            │
├─────────────────────────────────────┤
│ 图片网格（已上传的素材库图片）          │
│ ┌───┐ ┌───┐ ┌───┐                   │
│ │📷 │ │📷 │ │📷 │ ...               │
│ └───┘ └───┘ └───┘                   │
├─────────────────────────────────────┤
│            [确定] [裁剪]             │
└─────────────────────────────────────┘
```

**关键标识：**
- iframe URL: `market.m.taobao.com/app/crs-qn/sucai-selector-ng/index`
- 上传按钮 class: `NewSmallSplitPicUpload_UploadAction_restUploadCard__`
- "添加搭配图"容器: `NewSmallSplitPicUpload_addButtonContaner__`

**表单填写：**

```javascript
// 填写搭配标题（React controlled textarea）
await page.evaluate((text) => {
  const el = document.querySelector('#title');
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(el, text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '测试搭配标题001');

// 填写搭配正文
await page.evaluate((text) => {
  const el = document.querySelector('#description');
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(el, text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '这是测试搭配的正文内容，需要至少10个字');

// 点击发布
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '发布内容');
  if (btn) btn.click();
});
```

**返回列表页：**

```javascript
// 方法一：点击"取消"回到列表
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '取消');
  if (btn) btn.click();
});

// 方法二：直接导航回去
await page.goto('https://qn.wapa.taobao.com/home.htm/material-center/material-management?tab=recommend&subTab=SCU', {
  waitUntil: 'networkidle2', timeout: 30000
});
```

#### 4. 创建图文搭配（完整流程）

SPA 路由跳转到创建页面。创建流程分 **4 大步**：上传图片 → 添加商品 → 填写文案 → 保存/发布。

```javascript
// 进入创建页
await page.evaluate(() => {
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.includes('创建图文搭配'))?.click();
});
await new Promise(r => setTimeout(r, 5000));
// URL: /home.htm/qianniu_dress_collocation/create?bizFrom=list_generator&source=sucaizhongxin&isNew=true
```

> ⚠️ **创建页进入后必须关闭引导弹窗**（"下一个"→"关闭"循环点击多次），否则后续操作被遮挡。

**创建页结构（与编辑页相同）：**
```
┌──────────────────────────────────────────┐
│ 左侧：手机预览卡片（N件宝贝 + 搭配标题）    │
│ 右侧：                                    │
│   · 添加搭配图片（上传区域）                 │
│   · 所有涉及的宝贝（灰色占位，图片上传后激活） │
│   · 搭配标题 textarea#title  (5-20字)       │
│   · 搭配正文 textarea#description (10-1000字)│
│   · [保存草稿] [发布内容] [取消]              │
└──────────────────────────────────────────┘
```

##### 步骤一：上传图片

参见上方 **文件上传操作** 的 7 步流程。

> ⚠️ **裁剪确定后会自动弹出「添加宝贝和锚点」弹窗**，不需要额外触发。

##### 步骤二：添加商品（锚点弹窗内）

裁剪完成后自动弹出「添加宝贝和锚点」Dialog，在此弹窗内关联商品：

```
┌─────────────────────────────────────────────┐
│ 添加宝贝和锚点                                │
│ [更换搭配图片]                                │
│ 1. 可添加0-5个标签...                         │
│ 2. 锚点文案建议6字以内，不要加品牌名             │
│ 3. 需将标签放置在左侧图片合适的位置              │
│ 4. 商品关联需注意上传顺序，主推商品优先           │
│                                               │
│ [添加商品]  ← 点击打开商品选择弹窗               │
│                                               │
│ 所有提及的宝贝 | 锚点信息 | 操作                 │
│ ───────────────────────────────────────       │
│ （没有数据）                                   │
│                                               │
│ [保存] [取消]                                  │
└─────────────────────────────────────────────┘
```

```javascript
// 点击"添加商品" → 打开商品选择弹窗
await page.evaluate(() => {
  Array.from(document.querySelectorAll('*'))
    .find(e => e.innerText?.trim() === '添加商品' && e.offsetParent && e.children.length === 0)?.click();
});
await new Promise(r => setTimeout(r, 3000));
```

##### 商品选择弹窗

```
┌──────────────────────────────────────────┐
│ 商品选择                                  │
│ Tab: [全部商品] [上新] [预上新] [热门]       │
│ [按商品名 ▼] [___搜索框___]               │
│                                          │
│ ☐ 商品名1  ¥XX.XX                        │
│ ☐ 商品名2  ¥XX.XX                        │
│ ...                                      │
│                                          │
│ 最多选择 5 个、最少选择 1 个商品 (已选 N)    │
│ [确认] [取消]                              │
└──────────────────────────────────────────┘
```

> ⚠️ **搜索类型切换**：默认是"按商品名"，点击后弹出下拉菜单可切换为"按商品ID"。
> 切换后 placeholder 变为 "按商品ID搜索"。

```javascript
// 切换到"按商品ID"搜索
await page.evaluate(() => {
  // 点击"按商品名"打开下拉
  Array.from(document.querySelectorAll('*'))
    .find(e => e.innerText?.trim() === '按商品名' && e.children.length === 0)?.click();
});
await new Promise(r => setTimeout(r, 1000));

// 选择"按商品ID"
await page.evaluate(() => {
  Array.from(document.querySelectorAll('.next-menu-item'))
    .find(m => m.innerText?.trim().includes('按商品ID'))?.click();
});
await new Promise(r => setTimeout(r, 1000));

// 输入商品ID并搜索
// ⚠️ 不能用 page.type()（会卡住），必须用 React setter + 事件触发
await page.evaluate((itemId) => {
  const input = document.querySelector('input[placeholder*="按商品ID搜索"]');
  if (!input) return;
  input.focus();
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(input, itemId);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
}, '1041260929513');
await new Promise(r => setTimeout(r, 3000));

// 勾选商品 checkbox（value 就是商品ID）
await page.evaluate((itemId) => {
  const cb = document.querySelector(`input[type="checkbox"][value="${itemId}"]`);
  if (cb && !cb.checked) cb.click();
}, '1041260929513');
await new Promise(r => setTimeout(r, 1000));

// 点"确认"
await page.evaluate(() => {
  const dlg = Array.from(document.querySelectorAll('.next-dialog'))
    .find(d => d.innerText?.includes('商品选择'));
  Array.from(dlg?.querySelectorAll('button') || [])
    .find(b => b.innerText?.trim() === '确认')?.click();
});
await new Promise(r => setTimeout(r, 2000));
```

> **关键标识：**
> - 搜索切换按钮 class: `DebouncedInput_searchApproach__`
> - 搜索输入框 class: `DebouncedInput_debouncedInput__`
> - 商品 checkbox: `input[type="checkbox"][value="{商品ID}"]`
> - 下拉菜单项: `.next-menu-item`

##### 保存锚点弹窗

```javascript
// 商品添加后，在锚点弹窗点"保存"
await page.evaluate(() => {
  const dlg = Array.from(document.querySelectorAll('.next-dialog'))
    .find(d => d.innerText?.includes('添加宝贝和锚点'));
  Array.from(dlg?.querySelectorAll('button') || [])
    .find(b => b.innerText?.trim() === '保存')?.click();
});
await new Promise(r => setTimeout(r, 3000));
// 弹窗关闭后，左侧预览区显示商品信息，"N件宝贝"数字更新
```

##### 步骤三：填写标题和正文

```javascript
// 标题（5-20字）
await page.evaluate((text) => {
  const el = document.querySelector('#title');
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(el, text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '春日清新穿搭分享');

// 正文（10-1000字）
await page.evaluate((text) => {
  const el = document.querySelector('#description');
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(el, text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, '春天来了，分享一组清新自然的穿搭灵感。简约舒适的搭配，适合日常出行。');
```

##### 步骤四：保存或发布

```javascript
// 保存草稿（不发布，安全选项）
await page.evaluate(() => {
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '保存草稿')?.click();
});
await new Promise(r => setTimeout(r, 5000));
// 保存成功后自动跳回素材管理列表页

// 发布内容（直接上线）
await page.evaluate(() => {
  Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '发布内容')?.click();
});
```

##### 创建流程注意事项汇总

| # | 注意事项 | 说明 |
|---|---------|------|
| 1 | 引导弹窗 | 进入创建页后必须循环关闭引导弹窗（"下一个""关闭"等） |
| 2 | 遮挡清除 | 上传按钮容易被"重要消息"通知面板遮挡，用 `elementFromPoint` 循环隐藏 |
| 3 | 裁剪必须 | 即使图片已是 3:4 比例，也必须走裁剪流程，否则"确定"按钮不可用 |
| 4 | 锚点弹窗自动弹出 | 裁剪确定后自动弹出「添加宝贝和锚点」弹窗 |
| 5 | 搜索框不能用 page.type() | React controlled input，page.type() 会卡死，必须用 setter |
| 6 | 商品搜索切换 | 默认"按商品名"，需先点下拉切换到"按商品ID"才能用 ID 搜索 |
| 7 | iframe detach | 裁剪确定后 iframe 销毁，不能再操作 selectorFrame |
| 8 | 保存后自动跳转 | 保存草稿/发布后自动跳回列表页 |

#### 5. 删除搭配（确认弹窗）

```javascript
await page.evaluate((title) => {
  const rows = Array.from(document.querySelectorAll('table tbody tr'));
  for (const row of rows) {
    if (row.innerText?.includes(title)) {
      const btn = Array.from(row.querySelectorAll('button'))
        .find(b => b.innerText?.trim() === '删除');
      if (btn) btn.click();
      break;
    }
  }
}, '目标搭配标题');
await new Promise(r => setTimeout(r, 1000));

// 确认删除弹窗
await page.evaluate(() => {
  const confirmBtn = Array.from(document.querySelectorAll('.next-dialog-btn'))
    .find(b => b.innerText?.trim() === '确定');
  if (confirmBtn) confirmBtn.click();
});
```

#### 6. 批量操作

```javascript
// 勾选行
await page.evaluate(() => {
  const checkboxes = document.querySelectorAll('table tbody input[type="checkbox"], table tbody [role="checkbox"]');
  checkboxes.forEach(cb => cb.click());
});
await new Promise(r => setTimeout(r, 500));

// 批量删除
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.innerText?.trim() === '批量删除');
  if (btn) btn.click();
});
```

### 表格数据读取

```javascript
const tableData = await page.evaluate(() => {
  const rows = Array.from(document.querySelectorAll('table tbody tr'));
  return rows.map(row => {
    const cells = Array.from(row.querySelectorAll('td'));
    return {
      title: cells[2]?.innerText?.trim(),      // 搭配标题/ID
      productIds: cells[3]?.innerText?.trim(),  // 搭配商品ID
      publishTime: cells[4]?.innerText?.trim(), // 发布时间
      type: cells[5]?.innerText?.trim(),        // 搭配类型（图文/视频）
      status: cells[6]?.innerText?.trim(),      // 状态
      syncChannel: cells[7]?.innerText?.trim(), // 私域同步渠道
    };
  });
});
```

### 测试场景

| # | 场景 | 操作类型 | 验证点 |
|---|------|---------|--------|
| 1 | 三级筛选切换 | 点击查询 | 切换后列表数据正确过滤 |
| 2 | 清除条件 | 点击 | 重置后显示全部素材 |
| 3 | 查看商品及预览 | 点击→弹窗 | 弹窗显示搭配标题/ID/商品列表/二维码 |
| 4 | 编辑搭配 | 点击→同页跳转 | 跳转到编辑页，表单预填现有数据 |
| 5 | 编辑-修改标题 | 表单填写 | 标题 5-20 字限制 |
| 6 | 编辑-上传图片 | 文件上传 | 图片格式/尺寸/大小校验 |
| 7 | 编辑-发布 | 点击提交 | 保存后返回列表，数据已更新 |
| 8 | 创建图文搭配 | 点击→同页跳转 | 空表单，需上传图片+填写标题 |
| 9 | 创建视频搭配 | 点击→同页跳转 | 类似图文，但上传视频 |
| 10 | 删除搭配 | 点击→确认弹窗 | 确认后列表刷新，素材消失 |
| 11 | 批量删除 | 勾选+点击 | 多条同时删除 |
| 12 | 批量导出 | 勾选+点击 | 导出文件下载 |
| 13 | 分页 | 点击翻页 | 数据正确切换，页码更新 |

---

## 三个区域操作类型对比

| 区域 | 主要操作 | 交互特点 |
|------|---------|---------|
| 搜推素材质量诊断 | 无 | 纯展示，只需读取和验证数据 |
| 搜推素材拿量效果 | 点击切换 + 日期组件 | 操作后数据联动刷新，需等待加载后检查 |
| 素材管理列表 | 查询筛选 + 弹窗 + 同页跳转 + 文件上传 | 多种交互混合，编辑页涉及表单填写和文件上传 |

## 通用注意事项

1. **SPA 导航**：编辑/创建操作通过路由跳转，不新开 tab，操作后需 `page.goto()` 返回列表
2. **React controlled input**：textarea/input 需用 `Object.getOwnPropertyDescriptor` setter 写入，**不要用 `page.type()`**（会卡死）
3. **文件上传**：没有标准 `input[type="file"]`，必须通过素材选择器 iframe → 本地上传 → `page.waitForFileChooser()` 拦截
4. **弹窗组件**：使用 `@alifd/next` 的 Dialog，class 前缀 `next-dialog-`
5. **筛选条件组件**：使用自定义 CSS module，class 前缀 `ContentFilter_filter-content-item__`
6. **数据加载延迟**：切换筛选后等待 2 秒再读取数据
7. **图片上传限制**：3:4 比例，≥750×1000px，JPG/PNG，<5MB，最多 9 张
8. **裁剪是必须步骤**：无论图片是否已满足比例要求，都必须点裁剪 → 确定，否则"确定"按钮永远 disabled
9. **iframe 生命周期**：素材选择器/裁剪操作完成后 iframe 会 detach（销毁），后续不能再操作原 frame 引用
10. **遮挡检测**：操作按钮前用 `document.elementFromPoint()` 检测是否被通知面板等元素遮挡，循环隐藏遮挡元素
11. **引导弹窗**：页面刷新或进入新页面后，可能出现多步引导弹窗（"下一个"→"关闭"），必须循环关闭
12. **商品选择弹窗搜索**：默认"按商品名"搜索，需先点下拉切换到"按商品ID"才能用 ID 搜索商品
13. **截图方式**：使用 CDP `Page.captureScreenshot` 而非 `page.screenshot()`，后者在 viewport 不匹配时只截取部分区域
14. **锚点弹窗自动触发**：裁剪确定后自动弹出「添加宝贝和锚点」弹窗，不需要额外操作
