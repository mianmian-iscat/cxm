---
title: "环境矩阵"
type: infra
domain: common
last_updated: "2026-08-03"
tags: [环境, 预发, 日常, 线上, 矩阵]
---

# 环境矩阵

## F88 平台

| 环境 | URL | 用途 |
|------|-----|------|
| 预发 | `pre-aifashion-xiaoer.alibaba-inc.com` | 日常测试 |
| 线上 | `aifashion-xiaoer.alibaba-inc.com` | 生产验证 |

## 原创保护平台

| 环境 | 商家端 | 小二端 |
|------|--------|--------|
| 预发 | `pre-fsyc.taobao.com` | `pre-xiaoer.alibaba-inc.com` |
| 线上 | `fsyc.taobao.com` | `xiaoer.alibaba-inc.com` |

## Chrome CDP 配置

| 配置项 | 值 |
|--------|-----|
| 默认调试端口 | 9222 |
| 多实例端口 | 9223, 9224... |
| viewport | 1280×720 |

## 数据库环境

| 环境 | DB 组 | 库名 | 访问方式 |
|------|-------|------|---------|
| 预发/线上 | scenario | prod | DMS MCP |

## 注意事项

- 预发数据与线上隔离
- 预发环境可能不稳定，需确认服务可用
- CDP 端口不可冲突
