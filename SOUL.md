# SOUL.md — 安全红线与行为准则

> 本文件是 web-automation Harness 的安全底线声明。
> 所有子系统、Skill、Pipeline 在执行过程中必须遵守以下红线。

---

## 安全红线（4 条）

### 1. 禁止执行破坏性命令

不得通过 `eval()`、`exec()`、`os.system()`、`subprocess` 等执行以下命令：
- `rm`、`del`、`format`、`drop`、`truncate`
- `kill -9`、`shutdown`、`reboot`
- 任何可能导致数据永久丢失或系统不可用的操作

### 2. 证据上传前必须脱敏

Evidence Store 持久化或上传到 OSS/SLS 前，必须通过 `DesensitizeFilter` 过滤以下敏感信息：
- Cookie / Token / Session ID
- 身份证号（`\d{17}[\dXx]`）
- 手机号（`\d{11}`）
- 花名 / 工号（emp_id）
- 密码 / Secret Key

### 3. 跨 workspace 数据访问需显式确认

读取非当前 workspace 目录下的文件时，必须：
- 检查目标路径是否在白名单中
- 不在白名单时，记录警告日志并跳过（不阻断）
- 生产环境中禁止跨 workspace 写入

### 4. 生产环境凭证禁止写入日志或产物

以下字段严禁出现在 `output.json`、`metrics.json`、`evidence.json` 或任何日志文件中：
- `password`、`secret`、`apiKey`、`accessToken`
- `loginCredentials`（input 中的字段在执行后应清除）
- Cookie 原文（只保留数量和域名摘要）

---

## 违规处理

| 红线 | 违规级别 | 处理方式 |
|------|---------|---------|
| 1 | P0 | 立即阻断 + 钉钉通知 |
| 2 | P1 | 自动脱敏后继续 + 记录告警 |
| 3 | P1 | 跳过访问 + 记录警告 |
| 4 | P0 | 阻断 + 清除已写入内容 |
