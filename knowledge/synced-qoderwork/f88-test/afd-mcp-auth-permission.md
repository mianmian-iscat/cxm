<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/afd-mcp-auth-permission.md -->
<!-- synced-at: 2026-07-11T03:52:35.004321 -->
<!-- skill: F88测试知识库 -->

---
id: infra/afd-mcp-auth-permission
title: taobao-cloth-afd-mcp授权与权限机制
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
tags: [MCP, 授权, SSO, taobao-cloth-afd-mcp, 权限]
trigger_examples:
  - "MCP工具报'不在开放范围内'权限不足"
  - "taobao-cloth-afd-mcp重授权方法"
  - "内部MCP URL格式是什么"
source_sessions: [6/1配置, 6/2测试, 6/10权限问题, 6/16审核创建skill]
promotion_count: 1
promotion_score: 0.64
---

# taobao-cloth-afd-mcp授权与权限机制

## 概述

taobao-cloth-afd-mcp是F88平台的核心MCP服务，其授权机制和权限控制有若干注意事项，包括重授权触发方式、常见权限错误、以及内部MCP URL模式。

## 详细内容

### 重授权方法

当MCP授权过期或失效时，通过以下方式触发重授权：

```
execute operation=auth
```

执行后浏览器会弹出SSO登录页面，完成OAuth授权流程。

### 常见权限问题

1. **"不在开放范围内"错误**: MCP工具可能报此错误，表示当前用户无该工具的访问权限
2. **OAuth重授权无效**: 有时重授权后仍然报权限错误
3. **disable/enable无效**: 重启MCP服务（先disable再enable）有时也无法解决权限问题

### 内部MCP URL模式

内部MCP服务的URL格式为：

```
https://mcp.alibaba-inc.com/{name}/mcp
```

例如：`https://mcp.alibaba-inc.com/taobao-cloth-afd-mcp/mcp`

### 排障步骤

1. 先尝试 `execute operation=auth` 触发重授权
2. 如果仍然报错，检查MCP服务配置中的权限白名单
3. 联系MCP服务负责人确认当前用户是否在授权范围内
4. 必要时重新安装MCP服务

## 验证方法

1. 执行 `execute operation=auth` 确认SSO弹窗正常
2. 授权后调用一个基础MCP工具，验证返回成功
3. 故意调用无权限的工具，确认错误信息为"不在开放范围内"

## 关联知识

- [[environment-matrix]] — 预发/线上环境配置
- [[api-contracts]] — API接口契约
