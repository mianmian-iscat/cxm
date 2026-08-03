---
title: "OP 系统配置"
type: infra
domain: op
last_updated: "2026-08-03"
tags: [原创保护, 系统配置, URL, API, MTOP]
---

# OP 系统配置

## 平台 URL

| 环境 | 商家端 | 小二端 |
|------|--------|--------|
| 预发 | `pre-fsyc.taobao.com` | `pre-xiaoer.alibaba-inc.com` |
| 线上 | `fsyc.taobao.com` | `xiaoer.alibaba-inc.com` |

## API 清单

| 端 | API 数量 | 协议 |
|----|---------|------|
| 商家端 | 21 个 | MTOP |
| 小二端 | 10 个 | HSF |

## 关联系统

| 系统 | 职责 |
|------|------|
| 快维 | 维权下架 |
| YC | 专利权管理 |
| 汇金 | 结算处理 |
| e签宝 | 电子签章 |

## 数据库

| 数据库组 | 库名 | 用途 |
|---------|------|------|
| scenario | prod | 原创保护核心业务表 |

## 登录方式

- 小二端: BUC/SSO 内网登录
- 商家端: 淘宝商家账号登录（需 TTYCBH 千牛标）
