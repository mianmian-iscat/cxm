# 边界场景处理口径

遇到问题先查这里，再查具体 reference 文件。

---

## 元素交互类

### 点击无效 / 被遮挡
**现象**：click() 执行但无响应，或元素不可见  
**原因**：通知面板、引导弹窗、Modal 遮挡  
**处理**：
```javascript
// 检测遮挡并清除
const blocker = document.elementFromPoint(x, y);
if (blocker !== targetEl) blocker.style.display = 'none';
```
→ 详见 [popup-handling.md](popup-handling.md)

### checkbox/hover 元素不可见
**现象**：querySelector 找到元素但 click 无效  
**原因**：元素仅 hover 时可见  
**处理**：先 `page.mouse.move(x, y)` 再 `click()`

### React input 填值不生效
**现象**：输入框显示值，但提交时为空或触发"请填写"校验  
**原因**：绕过了 React onChange  
**处理**：使用 native setter + dispatchEvent，见 [react-form.md](react-form.md)

### 下一步/提交按钮点击无跳转
**现象**：点击后页面无变化，仍停留在当前步骤  
**原因 1**：表单有未填项（有隐藏的 error 提示）  
**排查**：`document.querySelectorAll('[class*="error-help"]')` 查看错误数  
**原因 2**：React 状态未更新（填值方式错误）  
**处理**：确认所有输入框都用 native setter 填值

---

## 页面生命周期类

### iframe detach
**现象**：操作 iframe 内元素时报 `Execution context was destroyed`  
**原因**：iframe 在操作后被销毁（常见于表单提交/路由跳转）  
**处理**：iframe 操作完成后不保存 frame 引用，需要时重新获取  
→ 详见 [iframe-ops.md](iframe-ops.md)

### SPA 路由跳转后元素消失
**现象**：点击操作后 DOM 结构完全变化，之前的选择器失效  
**原因**：SPA 路由变化，不重新加载页面  
**处理**：等待新路由渲染后重新 querySelector，不要复用旧引用

### 引导弹窗遮挡
**现象**：页面刷新/进入新页面后有多步引导遮挡操作区域  
**处理**：循环关闭，直到没有弹窗
```javascript
while (true) {
  const btn = document.querySelector('[class*="guide"] button, [class*="tour"] button');
  if (!btn) break;
  btn.click();
  await new Promise(r => setTimeout(r, 500));
}
```

### 登录态检测与处理
**现象**：页面跳转到登录页（`login.alibaba-inc.com` / `login.taobao.com`）  
**处理**：`connect()` 完成后自动调用 `check_login()` 检测，分两类处理：

| 登录类型 | 可否自动 | 处理方式 |
|---|---|---|
| 淘宝登录页 | 可以 | `context.loginCredentials` 传入 `{type:"taobao", username, password}` |
| BUC（阿里 SSO） | 不可以 | `output.status="login_required"`，提示人工登录 |

详见 [login-guard.md](login-guard.md)

---

## 网络抓包类

### getResponseBody 报错
**现象**：`Protocol error: No resource with given identifier found`  
**原因 1**：在 loadingFinished 之前调用  
**原因 2**：requestId 已被浏览器回收（操作间隔太长）  
**处理**：必须在 `Network.loadingFinished` 回调内调用，加 try/catch 兜底

### 拦截后页面卡死
**现象**：启用 setRequestInterception 后页面无响应  
**原因**：某个请求没有调用 continueInterceptedRequest  
**处理**：检查拦截回调，确保所有分支都有 continue 或 fulfill

### Service Worker 缓存导致请求不可见
**现象**：页面正常工作但 CDP Network 没有捕获到预期请求  
**原因**：请求被 SW 从缓存直接返回，不走网络  
**处理**：
```javascript
await page.evaluateOnNewDocument(() => {
  Object.defineProperty(navigator, 'serviceWorker', { get: () => undefined });
});
```

---

## 截图类

### 截图只有部分区域
**现象**：截图内容是页面局部，不是全屏  
**原因**：用了 page.screenshot() 且 viewport 与实际窗口不匹配  
**处理**：改用 CDP `Page.captureScreenshot`，见 [screenshot.md](screenshot.md)

### 截图有水印条纹
**现象**：截图上有半透明文字覆盖  
**原因**：阿里内网系统水印 div（class=wm_div_id）  
**处理**：截图前执行 `document.querySelectorAll('.wm_div_id').forEach(w => w.remove())`
