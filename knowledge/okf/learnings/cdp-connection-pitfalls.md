---
title: "CDP 连接稳定性踩坑"
type: learning
domain: common
last_updated: "2026-08-03"
tags: [CDP, Chrome, 连接, 稳定性]
---

# CDP 连接稳定性踩坑

## 端口隔离

- **问题**: 多个自动化实例共用同一 Chrome 调试端口导致会话冲突
- **规则**: 每个实例必须使用独立端口（默认 9222，多实例递增）
- **验证**: `lsof -i :9222` 确认端口占用

## 会话恢复

- **问题**: Chrome 重启后 CDP 连接丢失，需要重新建立
- **规则**: 连接失败时自动重试 3 次，间隔 2 秒
- **自愈**: 检测到连接断开 → 尝试重连 → 重连失败则重新打开页面

## 超时处理

- **问题**: `waitForSelector` 在 SPA 路由切换时超时
- **规则**: 设置合理超时（默认 10s），SPA 跳转后等待 DOM 稳定
- **模式**: 路由切换 → 等待 `networkidle0` → 再等待目标元素

## React 受控组件

- **问题**: Ant Design Select/Input 等受控组件，直接设置 value 不触发 React 状态更新
- **规则**: 使用 `type` + `pressKey` 模拟真实输入，而非直接设置 DOM value
- **验证**: 输入后检查 React 组件 state 是否同步更新

## Drawer/Modal 动画

- **问题**: Ant Design Drawer 打开动画期间点击无效
- **规则**: 等待 `.ant-drawer-content` 出现且 `offsetWidth > 0` 后再操作
- **超时**: 动画超时设为 3s（比默认 0.3s 留足余量）
