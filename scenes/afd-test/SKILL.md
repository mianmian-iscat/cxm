---
name: web-automation/afd-test
description: AFD 风格店铺协作平台测试（M4 新增模块）。覆盖店铺列表、迭代详情（Brief/试拍评审/归档）、角色权限矩阵。触发词：AFD、风格店铺、协作平台、迭代、Brief、试拍、买手、Leader。
parent: web-automation
---

# AFD 风格店铺协作平台 - 测试场景

> 场景化 Skill。页面结构、API 信息 → `knowledge/afd-style-shop-collab.json`；
> 状态机/Brief/试拍/权限详情 → `references/` 目录下参考文档。

## 环境信息

| 项目 | 值 |
|------|---|
| 平台 | AFD 风格店铺协作平台 |
| 预发域名 | `pre-aifashion-xiaoer.alibaba-inc.com` |
| UI 框架 | react-antd（class 前缀 `ant-`） |
| Knowledge ID | `afd-style-shop-collab` |
| 认证 | 阿里内网 SSO（BUC） |
| 租户验证 | 左上角必须显示"AFD"，通过 `X-AFD-Emp-Identity` 租户头切换 |

## 与 F88 的关系

| 维度 | F88 | AFD |
|------|-----|-----|
| 代码库 | stylespot-admin（共享） | stylespot-admin（共享） |
| 域名 | `pre-aifashion-xiaoer.alibaba-inc.com` | 同左（租户隔离） |
| 路由前缀 | `/review/*`, `/strategy/*` | `/styleShopCollab/*` |
| 驱动模式 | AI 工作流引擎 | 人工协作流程 |
| 状态机 | WorkflowStatusEnum | 10态迭代状态机 |
| 左上角标识 | "F88–运营平台" | "AFD" |

## 页面入口

| 页面 | 导航路径 | URL |
|------|---------|-----|
| 风格店铺协作入口 | 默认 | `https://pre-aifashion-xiaoer.alibaba-inc.com/styleShopCollab` |
| 店铺列表工作台 | 协作入口 > 店铺列表 | `https://pre-aifashion-xiaoer.alibaba-inc.com/styleShopCollab/shopList` |
| 迭代详情 | 店铺列表 > 点击进入 | `https://pre-aifashion-xiaoer.alibaba-inc.com/styleShopCollab/iteration/:iterationId` |

## 迭代状态机（10态）

```
DRAFT_BRIEF → PENDING_BRIEF → IN_PRODUCTION → IN_REVIEW → PENDING_LEADER → ARCHIVED
     ↑              |                              |              |
     |              ↓                              |              ↓
     +← REJECTED_BRIEF ←←←←←←←←←←←←←←←←←←←←←←←←←←    RETURNED_TO_BUYER
                                                     ↓
                                                  RETURNED → IN_REVIEW
                                                 CANCELLED（终态）
```

| 状态 | 含义 | 处理角色 | 可执行操作 |
|------|------|---------|-----------|
| DRAFT_BRIEF | Brief草稿中 | 买手 | 保存/提交 |
| PENDING_BRIEF | 待产运确认 | 产运 | 确认/驳回 |
| REJECTED_BRIEF | Brief被驳回 | 买手 | 重新编辑(fork新版本)/提交 |
| IN_PRODUCTION | 产运上传试拍 | 产运 | 上传/导入/发起评审 |
| IN_REVIEW | 买手审核中 | 买手 | 逐组审核/弃用/提交结论 |
| PENDING_LEADER | Leader复核 | Leader | 确认通过/确认驳回/打回买手 |
| RETURNED_TO_BUYER | Leader打回买手 | 买手 | 重新调整/提交 |
| RETURNED | Leader确认驳回 | 产运 | 补充上传/重新发起评审 |
| ARCHIVED | 已归档(终态) | 无 | 只读查看 |
| CANCELLED | 已终止(终态) | 无 | 只读查看 |

## 角色权限矩阵（5类角色）

| 角色 | 说明 | 主要操作 |
|------|------|---------|
| buyer（买手） | 店铺关系角色 | 发起迭代/Brief/审核试拍 |
| operator（产运） | 角色组权限 | 确认Brief/上传试拍/补拍 |
| leader（Leader） | 角色组权限 | 复核买手结论(三选一) |
| admin（管理员） | 跨店管理 | 添加店铺/代操作/全权限 |
| viewer（其他人） | 只读 | 查看有权限范围信息 |

> 关键规则：买手是相对店铺的关系角色，同一个人在非负责店铺下按"其他人"处理。

## 测试用例清单（15个）

### 店铺管理
| ID | 用例名 | 优先级 | 描述 |
|----|--------|--------|------|
| tc01 | 店铺列表工作台 | P0 | 列表加载+筛选+租户验证+视觉状态 |
| tc02 | 添加风格店铺 | P0 | 管理员添加弹窗(SellerID+买手) |
| tc03 | 新增视觉迭代 | P0 | 创建迭代弹窗(迭代名称≤40字) |

### Brief 流程
| ID | 用例名 | 优先级 | 描述 |
|----|--------|--------|------|
| tc04 | Brief草稿+提交 | P0 | 5大区块表单填写+校验+提交 |
| tc05 | 产运确认/驳回 | P0 | 确认→IN_PRODUCTION / 驳回→REJECTED_BRIEF |
| tc06 | Brief驳回后重提 | P1 | fork新版本+版本侧栏+重新提交 |

### 试拍评审
| ID | 用例名 | 优先级 | 描述 |
|----|--------|--------|------|
| tc07 | 试拍上传+最小集 | P0 | 5坑位上传+最小集校验 |
| tc08 | Excel批量导入 | P1 | 模板下载+导入+行级校验 |
| tc09 | 买手审核 | P0 | 逐组大图审核+弃用+判定规则 |
| tc10 | Leader复核 | P0 | 三选一决策(确认通过/确认驳回/打回) |
| tc11 | 打回/补拍 | P1 | Leader打回→产运补拍→重新审核 |

### 归档/终止/权限
| ID | 用例名 | 优先级 | 描述 |
|----|--------|--------|------|
| tc12 | 视觉归档 | P1 | 确认通过→归档+基准包生成 |
| tc13 | 终止迭代 | P1 | 权限校验+弹窗+终态只读 |
| tc14 | 角色权限验证 | P1 | 5角色×多场景操作可见性 |
| tc15 | 统计指标验证 | P2 | 8项统计口径验证 |

## 关键坑点

1. **React受控Input** — `fill` 必须 `react: true`，否则值不会写入
2. **AntD Drawer动画** — 打开抽屉后等待 500ms 再操作
3. **租户头切换** — `X-AFD-Emp-Identity` 决定 AFD/F88 身份
4. **Brief字数校验** — 风格定位 20-200字，迭代名称 ≤40字
5. **最小集校验** — ≥5组达标，每组套图≥5张，标签≥3种
6. **买手判定规则** — 单组可用≥5张=组通过，迭代通过≥3组=买手通过
7. **Brief版本管理** — 首版无版本号，驳回后fork新版本（v1→v2）
8. **终止弹窗** — 必须填写终止原因+详细说明（危险操作）
9. **水印清除** — 截图前操作 `.wm_div_id` 清除水印

## 共享组件复用（与 F88 共用）

| 组件 | 坑点 | 解法 |
|------|------|------|
| React 受控 Input | 值不写入 | `fill` 加 `react: true` |
| AntD Drawer | 动画未完成就操作 | 等待 500ms |
| BUC SSO | 登录态失效 | 人工重新登录 |
| AntD Table 搜索 | 受控组件 | `react: true` + `selectorIndex` |
| AntD Select 搜索 | 下拉选项加载 | 输入后等待 1000ms |
| 水印清除 | 遮挡截图 | 操作前清除 `.wm_div_id` |
| CDP 截图 | 全屏截图 | 使用 `screenshot` 步骤 |
