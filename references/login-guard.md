# 登录态处理规范

Web Automation 涉及两类登录体系，处理方式完全不同。

---

## 一、淘宝账号登录（买家侧页面）

**典型域名**：`taobao.com`、`pre-sellerhome-myseller.taobao.com`、`login.taobao.com`

### 1.1 免登（优先）

连接已有浏览器 Tab 时，若本地 Chrome 已登录淘宝账号，Cookie 自动复用，**无需任何操作**。

`connect()` 时用 `urlPattern` 直接定位目标 Tab：

```python
await cdp.connect(url_pattern="taobao.com")
```

若目标 Tab 不存在，`connect()` 会新开 Tab 并 `goto(url)`，此时 Cookie 也会自动带上（同浏览器实例共享）。

### 1.2 账号密码登录（Cookie 失效时）

检测到登录页（URL 含 `login.taobao.com` 或页面含登录表单）时，可自动填写账号密码：

```python
# impl.py 或调用方传入 context.loginCredentials
login_cfg = ctx.get("loginCredentials", {})
if login_cfg.get("type") == "taobao":
    await cdp._send_cmd("taobaoLogin", {
        "username": login_cfg["username"],
        "password": login_cfg["password"],
    })
```

`_node_bridge.js` 中 `taobaoLogin` 命令实现：

```javascript
case 'taobaoLogin': {
  // 填写账号
  await page.waitForSelector('#fm-login-id', { timeout: 10000 });
  await page.evaluate((u, p) => {
    const uSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const uEl = document.querySelector('#fm-login-id');
    const pEl = document.querySelector('#fm-login-password');
    uSetter.call(uEl, u); uEl.dispatchEvent(new Event('input', { bubbles: true }));
    uSetter.call(pEl, p); pEl.dispatchEvent(new Event('input', { bubbles: true }));
  }, params.username, params.password);
  await new Promise(r => setTimeout(r, 500));
  // 点登录
  await page.evaluate(() => {
    document.querySelector('button[type="submit"], .login-submit')?.click();
  });
  await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });
  return { loggedIn: true };
}
```

### 1.3 input.json 配置示例

```json
{
  "context": {
    "urlPattern": "taobao.com",
    "url": "https://pre-sellerhome-myseller.taobao.com/...",
    "loginCredentials": {
      "type": "taobao",
      "username": "your_taobao_id",
      "password": "your_password"
    }
  }
}
```

> ⚠️ 明文密码仅用于本地测试，**不要提交到代码仓库**。

---

## 二、阿里员工 BUC 登录（内网系统）

**典型域名**：`alibaba-inc.com`、`tppnext.alibaba-inc.com`、`xiaoer.alibaba-inc.com`

### 2.1 无法免登的原因

BUC 登录依赖：
1. 员工工号 + 密码 / 手机验证码
2. 或阿里郎扫码 / 手机确认
3. SSO Token 有时效（通常 8h），过期需重新认证

自动化工具**无法模拟**上述二次验证流程，因此：

- ✅ **已登录状态**：直接复用 Chrome 中已有的 SSO Cookie，免登自动生效
- ❌ **未登录 / Token 过期**：**必须人工登录**，工具无法代劳

### 2.2 登录态检测

`connect()` 完成后，`cdp_client.py` 会自动检测登录状态：

```python
login_status = await cdp.check_login()
# 返回:
# {
#   "isLoginPage": bool,      # 当前是否在登录页
#   "loginType": "buc"|"taobao"|"none",
#   "currentUrl": str,
#   "source": "redirect"|"knowledge"|"heuristic"
# }
```

**检测优先级（三段式，`_node_bridge.js` 中 `checkLogin` 命令）：**

| 优先级 | source | 判断方式 |
|---|---|---|
| 1 | `redirect` | 当前 URL 直接是登录页（`login.alibaba-inc.com` / `login.taobao.com`），`isLoginPage=true` |
| 2 | `knowledge` | 按 host 匹配 `knowledge/index.json` 中注册的 `auth.type`，`isLoginPage=false`，仅提供 loginType 供参考，不阻断执行 |
| 3 | `heuristic` | 检测页面内容（工号/Employee ID 字段、`#fm-login-id` 表单）猜测，未命中 knowledge 时兜底 |

### 2.3 BUC 登录被检测到时的处理流程

```
检测到 BUC 登录页
        ↓
抛出 LoginRequiredError（含当前 URL）
        ↓
impl.py 捕获，output.status = "login_required"
output.error.loginType = "buc"
output.error.message = "需要人工登录 BUC，请在浏览器中完成登录后重试"
        ↓
用户在浏览器中手动登录
        ↓
重新执行用例
```

### 2.4 output 结构（login_required 状态）

```json
{
  "status": "login_required",
  "error": {
    "stepIndex": -1,
    "loginType": "buc",
    "currentUrl": "https://login.alibaba-inc.com/...",
    "message": "需要人工登录 BUC，请在浏览器中完成登录后重试"
  }
}
```

---

## 三、connect() 登录检测时序

```
connect()
  ↓
定位 / 新开 Tab
  ↓
check_login()
  ├─ 淘宝登录页 + loginCredentials 存在 → 自动填账号密码登录
  ├─ 淘宝登录页 + 无 loginCredentials  → 抛出 LoginRequiredError（type=taobao）
  ├─ BUC 登录页                        → 抛出 LoginRequiredError（type=buc）
  └─ 非登录页                          → 正常继续
```

---

## 四、硬约束

- BUC 页面**禁止**尝试自动填写工号密码（无法通过验证，且可能触发安全告警）
- 淘宝账号密码**禁止**写入 knowledge 文件或 artifacts
- SSO Token 过期检测：若页面 URL 在操作中途跳转到登录页，应中止当前用例并报 `login_required`
