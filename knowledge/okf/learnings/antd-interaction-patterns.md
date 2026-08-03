---
title: "Ant Design 组件交互模式"
type: learning
domain: common
last_updated: "2026-08-03"
tags: [Ant Design, Select, Drawer, React, 受控组件]
---

# Ant Design 组件交互模式

## Select 下拉组件

- **问题**: 直接点击选项不触发 React 状态更新
- **规则**: 先点击 Select 容器 → 等待下拉面板出现 → 再点击目标选项
- **DOM 信号**: `.ant-select-dropdown` 出现且 `display !== 'none'`
- **陷阱**: 下拉面板可能渲染在 body 下（Portal），不在 Select 容器内

## Drawer 抽屉组件

- **问题**: 动画期间操作无效
- **规则**: 等待 `.ant-drawer-content` 出现且 `offsetWidth > 0` 后再操作
- **超时**: 动画超时设为 3s
- **关闭**: 点击关闭按钮或遮罩层，等待 Drawer 完全消失

## React 受控 Input

- **问题**: 直接设置 `input.value` 不触发 `onChange`
- **规则**: 使用 `page.type(selector, text)` 模拟真实键盘输入
- **验证**: 输入后检查 React DevTools 中组件 state 是否同步
- **备选**: 使用 `dispatchEvent(new Event('input', { bubbles: true }))` 触发

## Modal 弹窗

- **问题**: 确认按钮可能因表单校验 disabled
- **规则**: 先填写所有必填项，再检查按钮是否可点击
- **DOM 信号**: `.ant-modal` 出现，按钮无 `ant-btn-disabled` class

## Table 表格

- **问题**: 分页切换后 DOM 重新渲染
- **规则**: 分页操作后等待表格 loading 消失
- **DOM 信号**: `.ant-spin-spinning` 消失
