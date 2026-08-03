# 千牛工作台预发环境测试

## 概述

千牛工作台（`qn.wapa.taobao.com`）是淘宝商家管理后台的预发环境。常用测试页面：

1. **素材管理**：管理商品图片/视频素材、搜推素材、搭配素材
2. **出售中商品**：查看/管理在售商品列表

## 登录信息

| 项目 | 值 |
|------|---|
| 登录页 | `https://pre-loginmyseller.taobao.com/...` （自动跳转） |
| 账号 | `isv项目测试专用` |
| 密码 | `yangsiyi.ysy\|Asteria1016#` |
| 登录表单位置 | iframe `#alibaba-login-box`（`havanalogin.taobao.com/mini_login.htm`） |
| 账号输入框 | `#fm-login-id` |
| 密码输入框 | `#fm-login-password` |
| 登录按钮 | `button[type="submit"]` |

> ⚠️ 登录成功后 iframe 会 detach（Frame detached），这是正常行为，不要在点击登录后继续操作 iframe。

## 页面 URL

| 页面 | URL |
|------|-----|
| 素材管理 | `https://qn.wapa.taobao.com/home.htm/material-center/material-management?tab=recommend&subTab=SCU` |
| 出售中商品 | `https://qn.wapa.taobao.com/home.htm/SellManage/on_sale?current=1&pageSize=20` |

## 登录流程

```javascript
const puppeteer = require('/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core');

async function loginQianniu(page) {
  // 等待登录 iframe 加载
  await new Promise(r => setTimeout(r, 3000));
  
  const frame = page.frames().find(f =>
    f.url().includes('mini_login') || f.url().includes('havanalogin')
  );
  if (!frame) throw new Error('找不到登录 iframe');

  // 输入账号（用 React setter 方式确保触发 onChange）
  await frame.evaluate(() => {
    const el = document.querySelector('#fm-login-id');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, 'isv项目测试专用');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });

  // 输入密码
  await frame.evaluate(() => {
    const el = document.querySelector('#fm-login-password');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, 'yangsiyi.ysy|Asteria1016#');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });

  await new Promise(r => setTimeout(r, 1000));

  // 点击登录
  const btn = await frame.$('button[type="submit"]');
  await btn.click();

  // 等待跳转（iframe 会 detach，页面会跳到目标 URL）
  await new Promise(r => setTimeout(r, 5000));
  
  // 验证登录成功
  const url = page.url();
  if (url.includes('loginmyseller')) {
    throw new Error('登录失败，仍在登录页');
  }
  return true;
}
```

## 页面一：素材管理

### 页面结构

```
千牛工作台 Header（消息、客服、用户信息）
├── 左侧导航：商品素材管理 / 图片生产 / 视频生产 / 素材测试 / 主图打标 / 我的图片视频
├── 通知栏（可关闭的轮播通知）
├── Tab 切换：基础素材 / 活动素材 / 搜推素材 / 商详素材托管
├── 数据统计面板
│   ├── 猜你喜欢曝光人数
│   ├── 全屏页浏览人数
│   ├── 推荐首触支付订单数
│   └── 推荐首触支付金额
└── 素材管理列表
    ├── 筛选：素材类型（搜推/单品/多品/店铺装修/搭配）
    └── 表格：搭配封面 / 搭配标题ID / 搭配商品ID / 发布时间 / 搭配类型 / 状态 / 操作
```

### 常见测试操作

| 操作 | 说明 |
|------|------|
| 查看搭配素材 | Tab 切换到"搜推素材" → 选择"搭配素材" |
| 创建搭配 | 点击"创建图文搭配"或"创建视频搭配" |
| 编辑搭配 | 列表中某行 → "编辑搭配" |
| 删除搭配 | 列表中某行 → "删除" |
| 查看数据统计 | 统计面板区域，可切换日/近7日/近30日 |

### 关键选择器（参考，可能随版本变化）

UI 频繁变动时，建议使用 [adaptive-locator.md](adaptive-locator.md) 中的语义定位工具。

```javascript
// Tab 切换 — 按文本匹配
const tab = await findElement(page, { text: '搜推素材', tag: 'span' });

// 素材类型筛选
const filter = await findElement(page, { text: '搭配素材' });

// 创建按钮
const createBtn = await findElement(page, { textContains: '创建图文搭配', tag: 'button' });

// 表格行操作
const editBtn = await findElement(page, { text: '编辑搭配', tag: 'a' });
```

## 页面二：出售中商品

### 页面结构

```
千牛工作台 Header
├── Tab 切换：全部(1716) / 出售中(90) / 仓库中(1626) / 草稿(890) / 回收站(1) / 违规(1)
├── 筛选区
│   ├── 商品标题搜索
│   ├── 商品ID搜索
│   ├── 商家编码
│   └── 质量分筛选
├── 操作栏：发布商品 / 商品装修 / 批量下架 / 更多批量操作
└── 商品列表表格
    ├── 商品名称 + ID
    ├── 价格
    ├── 库存
    ├── 累计销量 / 30日销量
    ├── 质量分（基础分 + 扶优分）
    ├── 创建时间 / 发布时间
    └── 操作：编辑商品 / 发布相似品 / 更多
```

### 常见测试操作

| 操作 | 说明 |
|------|------|
| 搜索商品 | 输入商品标题或ID → 点击"搜索" |
| 按ID查找 | 商品ID搜索框输入 → 搜索 |
| 编辑商品 | 商品行 → "编辑商品" |
| 下架商品 | 勾选商品 → "批量下架"，或单个商品 → "更多" → "下架" |
| 查看质量分 | 商品行的质量分列，显示基础分和扶优分 |
| 翻页 | 底部分页器，共 90 件 / 5 页 |

### 关键选择器（参考）

```javascript
// Tab 切换
const onSaleTab = await findElement(page, { textContains: '出售中', tag: 'span' });

// 搜索
const searchInput = await findElement(page, { tag: 'input', ariaLabel: '商品标题' });
const searchBtn = await findElement(page, { text: '搜索', tag: 'button' });

// 商品操作
const editBtn = await findElement(page, { text: '编辑商品' });
const moreBtn = await findElement(page, { text: '更多' });

// 翻页
const nextPage = await findElement(page, { ariaLabel: '下一页' });
```

## ⚠️ 注意事项

1. **预发环境**：URL 域名是 `qn.wapa.taobao.com`（预发），不是 `qn.taobao.com`（线上）
2. **登录态有效期**：登录后 cookie 会过期，再次访问时可能需要重新登录
3. **检测登录态**：如果 URL 跳转到 `loginmyseller.taobao.com`，说明需要重新登录
4. **页面是 SPA**：千牛是单页应用，导航不会完全刷新页面
5. **UI 版本迭代**：这是业务测试页面，UI 可能频繁变化。建议优先使用语义定位（文本匹配），CSS 选择器仅作兜底
6. **滑块验证码**：登录时可能触发滑块验证，当前测试账号暂未触发
7. **截图水印**：同 TPP 页面，可能有水印需要清除

## 关闭页面弹窗（必做）

页面加载后可能有多个弹窗遮挡内容（通知、引导、AI 助手等），操作前必须先关闭：

```javascript
async function closeAllPopups(page) {
  for (let round = 0; round < 3; round++) {
    await page.evaluate(() => {
      // 1. 点击所有“关闭”类按钮
      const closeTexts = ['关闭', '×', '✕', '我知道了', '知道了', '不再提示', '关 闭', 'Close'];
      Array.from(document.querySelectorAll('button, span, a, div')).forEach(btn => {
        const text = btn.innerText?.trim();
        if (text && closeTexts.includes(text) && btn.offsetParent !== null) {
          const rect = btn.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) btn.click();
        }
      });

      // 2. aria-label="Close"
      document.querySelectorAll('[aria-label="Close"], [aria-label="close"]').forEach(el => {
        if (el.offsetParent !== null) el.click();
      });

      // 3. 右下角“重要消息”通知面板（notify_bg / notify_body）
      document.querySelectorAll('[class*="notify_bg"], [class*="notify_body"]').forEach(el => {
        el.style.display = 'none';
      });

      // 4. 右下角 fixed 浮窗（反馈/客服等）
      Array.from(document.querySelectorAll('div')).forEach(el => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (style.position === 'fixed' && rect.right > 1100 && rect.bottom > 800 && rect.width < 200) {
          el.style.display = 'none';
        }
      });

      // 5. 移除遮罩/引导/水印
      document.querySelectorAll('[class*="guide"], [class*="tour"], [class*="onboard"]').forEach(el => el.remove());
      document.querySelectorAll('.wm_div_id').forEach(w => w.remove());
    });
    await new Promise(r => setTimeout(r, 500));
  }
}
```

## 登录态检查 & 自动登录模板

```javascript
async function ensureLoggedIn(page, targetUrl) {
  await page.goto(targetUrl, { waitUntil: 'networkidle2', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // 检查是否跳到了登录页
  if (page.url().includes('loginmyseller')) {
    console.log('需要登录...');
    await loginQianniu(page);
    // 登录后可能自动跳转，也可能需要手动导航
    if (!page.url().includes('qn.wapa.taobao.com/home.htm')) {
      await page.goto(targetUrl, { waitUntil: 'networkidle2', timeout: 30000 });
      await new Promise(r => setTimeout(r, 3000));
    }
  }
  
  console.log('已登录，当前页面:', page.url());
}
```
