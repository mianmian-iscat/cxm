---
title: "F88 系统配置"
type: infra
domain: f88
last_updated: "2026-08-03"
tags: [F88, 系统配置, URL, API, HSF]
---

# F88 系统配置

## 平台 URL

| 环境 | URL |
|------|-----|
| 预发 | `pre-aifashion-xiaoer.alibaba-inc.com` |
| 线上 | `aifashion-xiaoer.alibaba-inc.com` |

## API 前缀

- 策略平台: `bzb.api.fsyx_quality_guard.f88`
- 审核平台: `bzb.api.fsyx_quality_guard.review`

## HSF 服务

| 服务 | 版本 | 用途 |
|------|------|------|
| `com.alibaba.f88.material.MaterialAuditService` | 1.0.0 | 素材审核 |
| `com.alibaba.f88.strategy.StrategyService` | 1.0.0 | 策略管理 |

## 租户头

```
X-AFD-Emp-Identity: f88    # F88 身份
X-AFD-Emp-Identity: afd    # AFD 风格店铺身份
```

## UI 框架

- React + Ant Design
- SPA 路由，页面无刷新跳转
- 关键选择器: `[data-testid]`、`.ant-*` class

## 登录方式

- BUC/SSO 内网登录
- 登录态失效时跳转到 `login.alibaba-inc.com`
