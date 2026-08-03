---
name: web-automation/qianniu-test
description: 千牛商家工作台预发环境测试。用于：(1) 素材管理页面测试（三区域交互验证），(2) 搭配素材创建/编辑/删除，(3) 图片上传与裁剪，(4) 商品关联与锚点设置。触发词：千牛、素材管理、搭配、图文搭配、搭配素材、编辑搭配、创建搭配。
parent: web-automation
---

# 千牛商家工作台测试

> 场景化 Skill。页面结构、选择器、坑点 → `knowledge/qianniu-material.json`；
> 操作动线详情 → `references/material-mgmt.md`。

## 环境信息

| 项目 | 值 |
|------|---|
| 预发域名 | `qn.wapa.taobao.com` |
| 线上域名 | `qn.taobao.com`（⚠️ 不要用线上） |
| UI 框架 | `@alifd/next`（class 前缀 `next-`） |
| Knowledge ID | `qianniu-material` |

## 页面入口

```
素材管理（搜推素材-搭配）：
https://qn.wapa.taobao.com/home.htm/material-center/material-management?tab=recommend&subTab=SCU
```

## 操作动线（速查）

### 搭配创建（完整 4 步）

```
进入创建页 → 关引导弹窗（循环）
  → 步骤一：上传图片（素材选择器 iframe → 本地上传 → 裁剪）
  → 步骤二：添加商品（锚点弹窗自动出现 → 切「按商品ID」→ 搜索 → 勾选）
  → 步骤三：填写标题/正文（React setter）
  → 步骤四：保存草稿 / 发布
```

### 搭配编辑 / 删除

见 `references/material-mgmt.md` 区域三第 3、5 节。

## 最关键的坑（不看 knowledge 也要知道）

1. **React input/textarea 必须用 native setter**，`page.type()` 会卡死
2. **文件上传没有标准 `input[type="file"]`**，必须走素材选择器 iframe → 本地上传
3. **checkbox 仅 hover 时可见**，先 `mouse.move` 到坐标再 click
4. **裁剪是必须步骤**，否则保存按钮永远 disabled
5. **裁剪后 iframe detach**，不要再操作 selectorFrame
6. **notify_bg 通知面板会遮挡按钮**，操作前先隐藏
7. **引导弹窗需循环关闭**（下一个 → 关闭，可能多步）
8. **截图用 CDP `Page.captureScreenshot`**，不用 `page.screenshot()`

## 参考文档

| 文档 | 说明 |
|------|------|
| `knowledge/qianniu-material.json` | 结构化页面知识（优先查这里） |
| `references/material-mgmt.md` | 完整操作动线 + 代码片段 |
| `references/login.md` | 登录流程 |
