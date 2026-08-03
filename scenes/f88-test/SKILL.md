---
name: web-automation/f88-test
description: F88 素材生产审核管理模块测试（策略平台）。覆盖 4 个页面：人工审核、审核标准管理、审核节点管理、任务管理。触发词：F88、素材审核、审核管理、人工审核、审核标准、审核节点、任务管理、策略平台。
parent: web-automation
---

# F88 素材生产 - 审核管理模块

> 场景化 Skill。页面结构、选择器、API 信息、坑点 → `knowledge/f88-material-audit.json`；
> 操作动线详情 → `references/audit-operations.md`。

## 环境信息

| 项目 | 值 |
|------|---|
| 平台 | F88运营平台 |
| 预发域名 | `pre-aifashion-xiaoer.alibaba-inc.com` |
| UI 框架 | react-antd（class 前缀 `ant-`） |
| Knowledge ID | `f88-material-audit` |
| 认证 | 阿里内网 SSO（BUC） |
| 租户验证 | 左上角必须显示“F88–运营平台”，当前身份= F88 |

## 页面入口

| 页面 | 导航路径 | URL |
|------|---------|-----|
| 个人任务中心 | 默认页 | `https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center` |
| 审核标准管理 | 审核管理 > 审核标准管理 | `https://pre-aifashion-xiaoer.alibaba-inc.com/review/standard-management` |
| 审核节点管理 | 审核管理 > 审核节点管理 | `https://pre-aifashion-xiaoer.alibaba-inc.com/review/node-management` |
| 任务管理 | 审核管理 > 任务管理 | `https://pre-aifashion-xiaoer.alibaba-inc.com/review/task-management` |
| 链路列表 | 策略平台 > 链路列表 | `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkList` |
| 链路详情 | 链路列表 > 点击链路名 | `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id=20180` |
| 策略列表 | 策略平台 > 策略列表 | `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/list` |
| 生产看板 | 策略平台 > 生产看板 | `https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/productionDashboard` |
| 模版包管理 | 模版库 > 模版包管理 | `https://pre-aifashion-xiaoer.alibaba-inc.com/templateManagement` |
| 淘内资源池 | 模版库 > 淘内资源池 | `https://pre-aifashion-xiaoer.alibaba-inc.com/templateLibrary` |
| 优质模板库 | 模版库 > 优质模板库 | `https://pre-aifashion-xiaoer.alibaba-inc.com/selfTemplateLibrary_f88` |

## 测试用例清单

### 基础页面用例

| 用例 | 页面 | 覆盖场景 |
|------|------|--------|
| `tc01_manual_audit_list.json` | 个人任务中心 | 租户验证 + 审核/抽检/埋雷Tab切换 + 任务搜索 |
| `tc02_audit_standard.json` | 审核标准管理 | 导航切换 + 标准列表 + 新增表单 + 字段验证 |
| `tc03_audit_node.json` | 审核节点管理 | 导航切换 + 节点列表 + 新增表单 + 字段验证 |
| `tc04_task_management.json` | 任务管理 | 任务列表 + 多条件筛选 + 查看详情 |
| `tc05_audit_flow.json` | 审核操作 | 审核按钮 → 审核详情 → 通过/驳回 → 通过率验证 |

### 图片编辑后 CopyURL / 下载 / 导出场景（Bug复现）

| 用例 | 场景 | 关联用例ID | 优先级分布 |
|------|------|---------|----------|
| `tc06_replace_copyurl.json` | 图片替换后 CopyURL 验证 | RP-01~06 | P0×5, P1×1 |
| `tc07_replace_download_excel.json` | 替换后下载 + Excel导出 | RP-07~13 | P0×4, P1×3 |
| `tc08_crop_operations.json` | 裁剪操作场景 | RP-C01~C12 | P0×5, P1×4, P2×3 |
| `tc09_reject_regenerate.json` | 驳回重生场景 | RP-27~36, NEW-I29~I35 | P0×5, P1×7, P2×2 |
| `tc10_compare_api_boundary.json` | 编辑对比 + API状态 + 边界异常 | RP-14~26 | P0×4, P1×5, P2×4 |
| `tc11_downstream_flow.json` | 下游流转验证 | RP-D01~D14 | P0×7, P1×7 |

### 策略平台用例

| 用例 | 页面 | 覆盖场景 |
|------|------|--------|
| `tc12_strategy_link_list.json` | 链路列表 | 导航 + 搜索 + 筛选 + 新建/编辑/复制 |
| `tc13_link_detail.json` | 链路详情 | 链路名称 + 阶段 + 环节展示 + 试运行 + 起点入参 |
| `tc14_strategy_list.json` | 策略列表 + 详情 | 导航 + 搜索 + 筛选 + 打开策略 → 详情页(节点编排/落库配置) |
| `tc15_production_dashboard.json` | 生产看板 | 整体推送进度(4项统计) + 链路生产进度(批次/状态/进度条) + 任务展开/下载 |
| `tc16_add_node.json` | 新增节点 | 打开策略 → 点击新增节点 → 弹窗节点类型(20种) + 节点编排验证 |
| `tc17_create_link.json` | 新建链路 | 链路列表 → 新建链路 → 详情页(起点入参/添加环节) → 返回列表 |
| `tc18_view_run_results.json` | 查看运行结果 | 链路详情 → 点击“查看运行结果” → 弹窗(5环节/任务列表/状态/出参/终止/添加策略) |
| `tc19_trial_run.json` | 试运行弹窗 | 链路详情 → 点击“试运行” → 弹窗(下载模板/上传Excel/任务名称/运行类型/发起运行) |

### 知识库补充用例（高清化/局部修改）

| 用例 | 场景 | 知识库模块 | 关联用例ID |
|------|------|---------|----------|
| `tc20_hd_enhance.json` | 高清化操作 CopyURL/下载/导出/API | I-C | NEW-I15~I21 (7条) |
| `tc21_local_modify.json` | 局部修改操作 CopyURL/下载/导出/API | I-D | NEW-I22~I28 (7条) |

### 后端 API/DB 级测试（pytest）

| 用例 | 场景 | 知识库模块 | 关联用例ID | 用例数 |
|------|------|---------|----------|-------|
| `tc22_stream_cover_reject.json` | STREAM审核+封面图Type=4+全不通过 | A-C | NEW-A1~A3, B1~B4, C1~C3 | 10 |
| `tc23_idempotent_trigger_callback.json` | 幂等并发+触发机制+回调链 | D-F | NEW-D1~D4, E1~E4, F1~F4 | 12 |
| `tc24_output_vars_error_paths.json` | 输出变量传递+错误路径 | G-H | NEW-G1~G4, H1~H3 | 7 |
| `tc25_dataflow_downstream.json` | 编辑下游流转+首图/套图/视频数据流转 | I-F+J-L | NEW-I36~I43, J1~J6, K1~K4, L1~L4 | 22 |
| `tc26_cross_node_reject_feedback.json` | 跨节点一致性+驳回重生+hasFeedback | M-O | M1~M5, N1~N6, O1~O8 | 19 |

### 端到端集成测试

| 用例 | 场景 | 流程 | 步骤数 |
|------|------|------|-------|
| `tc27_e2e_integration.json` | 全链路集成测试 | 参考链路20180 → 新建策略(生图+人工审核+高清化) → 新建链路+添加环节+绑定策略 → 试运行(测试) → 各环节状态监控 → API/DB端到端数据流验证 | 29条(E2E-01~29) |

### 模版库用例

| 用例 | 页面 | 覆盖场景 |
|------|------|--------|
| `ui_f88_template_management.json` | 模版包管理 | 页面加载 + 店铺卡片列表 + 筛选项 + 查看详情入口 |
| `normal_f88_template_mgmt_filter.json` | 模版包管理 | 筛选专项: 店铺名称/ID/买手/使用状态(AntD Select)+重置 (39步) |
| `normal_f88_template_mgmt_card.json` | 模版包管理 | 卡片字段完整性(店铺名/ID/买手/包数量/状态标签) |
| `normal_f88_template_mgmt_detail.json` | 模版包管理 | 查看详情入口 + 详情页渲染 + 返回列表 |
| `boundary_f88_template_mgmt_status.json` | 模版包管理 | 使用状态筛选(使用中/未使用) + 空结果边界 |
| `ui_f88_template_library.json` | 淘内资源池 | 页面加载 + 标签筛选 + 基础信息筛选 |
| `normal_f88_template_library_filter.json` | 淘内资源池 | 筛选专项: 4筛选(Seller ID/店铺/Item/图片ID)+7标签点击+重置 (42步) |
| `ui_f88_quality_template.json` | 优质模板库 | 页面加载 + 标签筛选 + 批量操作/创建任务入口 |
| `normal_f88_quality_template_filter.json` | 优质模板库 | 筛选专项: 4筛选+洗图状态+应用场景+7标签+重置 (53步) |
| `boundary_f88_template_pkg_status.json` | 模板包管理 | 风险点#15/#16/#20: 并发激活/缓存失效/状态回退 |
| `boundary_f88_tair_count_reset.json` | 资源池+模版包管理 | 风险点#17: Tair计数全超限清除后轮转恢复验证 |
| `boundary_f88_season_match_asymmetry.json` | 资源池+模版包管理 | 风险点#18: 季节组合匹配不对称 + 模板包覆盖率 |
| `boundary_f88_crop_y2_validation.json` | 审核任务+策略列表 | 风险点#19: 裁头y2无边界校验 + 5种极端坐标场景 |
| `normal_f88_template_pkg_create.json` | 模版包管理 | 新建模版包3步向导: Step1基础信息(名称max30/应用环节[搭配/视觉/套图]/应用场景[主图素材/种草素材]/描述max300) + Step2选择模版图 + Step3配置确认 (实测2026-07-09) |
| `normal_f88_template_pkg_import.json` | 模版包管理 | 导入模板包3步向导: Step1基础信息(选择源模板包/名称/应用环节/场景/描述) + Step2预览模板图 + Step3确认导入 (实测: 不是文件上传，是从其他店铺复制) |
| `normal_f88_template_pkg_toggle.json` | 模版包管理 | 立即使用/置为闲置: 无确认弹窗直接API调用+toast, setValid/setIdle, 进入店铺详情操作 (实测2026-07-09) |
| `normal_f88_template_pkg_detail_ops.json` | 模版包管理 | 模板包卡片列表+筛选(名称ID/应用环节/应用场景/状态)+搜索+分页+查看详情 (实测2026-07-09) |
| `normal_f88_template_library_preview.json` | 淘内资源池 | 预览+分页(筛选在filter专项用例) (33步) |
| `normal_f88_quality_create_task.json` | 优质模板库 | 创建任务4步+查看任务进度(深度探查+数据提取+fallback) (45步) |
| `normal_f88_quality_batch_ops.json` | 优质模板库 | 批量操作全流程+查看任务进度(深度探查+数据提取+fallback) (41步) |

### 审核管理/商家管理/策略平台 CRUD 用例

> 全部 5 条含 capture 抓包 + evaluate DOM 探查 + preconditions + data-test-target

| 用例 | 页面 | 覆盖场景 |
|------|------|--------|
| `normal_f88_audit_standard_edit.json` | 审核标准管理 | 编辑表单探查+Switch启用禁用+操作结果提示 (21步) |
| `normal_f88_audit_node_edit.json` | 审核节点管理 | 编辑表单+关联审核标准字段+列名探查 (17步) |
| `normal_f88_merchant_config_edit.json` | 店铺信息配置 | 编辑表单字段探查+批量下载+表格结构探查 (20步) |
| `normal_f88_link_list_ops.json` | 链路列表 | AntD Select生命周期筛选+复制确认弹窗+fallback (23步) |
| `normal_f88_strategy_list_filter.json` | 策略列表 | 双Select阶段/环节筛选+重置+选项获取 (26步) |

### 原子级功能点用例（180条，v3.2更新，基于浏览器实际操作验证）

> 每个页面每个功能点独立一条用例，不打包。前缀 `atomic_f88_`。**所有用例均通过浏览器实际操作页面验证功能点完整性**。

| 页面 | 用例数 | 功能点 |
|------|--------|--------|
| 个人任务中心 | 7 | 审核Tab/抽检Tab/埋雷Tab/搜索/列表字段/点击进详情/空状态 |
| 审核标准管理 | 5 | 页面加载文案/新增弹窗/编辑弹窗/启用禁用 |
| 审核节点管理 | 5 | 页面加载文案/新增弹窗/编辑弹窗/关联标准/排序 |
| 任务管理 | 42 | 批量导出/重试/表格列名/批次输入筛选/重置/环节统计/任务统计/进度条/分配明细(按钮/Tab/列名/数据行/转交/关闭)/详情(按钮/跳转/统计/筛选/表格/图片预览/分页/返回)/编辑(按钮/表单/预填充/任务名称/基础字段/分配/延期提示/抽检埋雷开关/确定/取消)/下载 |
| 链路列表 | 7 | 页面加载/新建/复制确认/生命周期筛选/搜索框/表格列名 |
| 链路详情 | 14 | 页面加载/试运行弹窗/下载模板/上传Excel/任务名称/运行类型/查看运行结果/阶段/环节/链路说明/起点入参/环节卡片/保存按钮/添加环节 |
| 策略列表 | 6 | 页面加载/新建/卡片操作/字段完整性/分页/表格列名 |
| 策略详情 | 11 | 页面加载/保存/新增节点/节点类型20种/入参出参/落库/策略说明+适配场景/阶段+环节下拉/节点编排/落库配置 |
| 店铺信息配置 | 14 | 表格8列/搜索sellerid/重置/批量下载/编辑表单/textarea字数计数/100字截断/添加参考竞店/sellerid自动带入/分页/面包屑返回/查看全部供应商/锁定字段 |
| 生产看板 | 7 | 页面加载/推送进度4指标/链路进度/任务展开/任务下载/批次展开环节/分页 |
| 模版包管理 | 16 | 页面加载/4筛选/新建弹窗/导入弹窗/编辑/激活停用/卡片菜单/详情列表/预览/停用/店铺详情列表/卡片翻页/闲置按钮 |
| 淘内资源池 | 10 | 页面加载/4筛选/7维度标签/卡片字段/预览/自然语言搜索/视图模式 |
| 优质模板库 | 17 | 页面加载/4筛选/7维度标签/洗图状态/应用场景/批量操作/创建任务/查看进度/卡片字段/风格簇模式/范围筛选/批量操作下拉/创建任务按钮/查看进度按钮 |
| 审核详情(审核任务Tab下) | 15 | 通过/驳回/驳回必填/驳回类型/图片放大/素材切换/复制URL/下载/编辑确认/编辑前后切换/负反馈/复位/驳回重生/视频播放/文本高亮 |

### 审核类型覆盖

| 审核类型 | 标识 | 覆盖用例 |
|---------|------|--------|
| 单图审核 | qt=1 | tc06, tc07, tc08, tc11 |
| 套图审核 | qt=2 | tc06, tc07, tc08, tc11 |
| 封面图审核 | qt=4 | tc06, tc07, tc08, tc09, tc11 |

## 人工审核页关键元素（来自截图）

```
页面标题：mmtest视频审核-BT_5943-人工审核

顶部操作区：
  [审核]（蓝色）  [通过率：0.00%]  [审核标准]（灰色）

搜索区：
  商家名称：[请输入]    商家ID：[请输入]

数据表格：
  任务ID | 商家名称 | 审核状态
  1212831 | u[2219635649153] (ID: 2219635649153) | 待审核（紫色标签）
```

## 最关键的坑

1. **身份选择器**：页面左上角需确认当前身份为 F88，否则数据权限不对
2. **搜索框是 React 受控组件**，`fill` 必须用 `react: true`（native setter + dispatchEvent）
3. **两个搜索框共用同一 selector** `input[placeholder='请输入']`，用 `selectorIndex` 区分（0=商家名称, 1=商家ID）
4. **搜索可能无明确按钮**，需确认是回车触发还是实时搜索
5. **审核状态标签为紫色圆角样式**（待审核），可能使用 ant-tag 或自定义组件
6. **水印 `.wm_div_id` 每次操作前清除**
7. **截图用 CDP `Page.captureScreenshot`**

## 待确认事项

- [x] 模版库子页面具体 URL（模版包管理 `/templateManagement` / 淘内资源池 `/templateLibrary` / 优质模板库 `/selfTemplateLibrary_f88`）
- [ ] 各页面 API 接口路径（需 CDP 抓包确认）
- [ ] 审核详情页交互形式（弹窗 vs 新页面）

## 参考文档

| 文档 | 说明 |
|------|------|
| `knowledge/f88-material-audit.json` | 结构化页面知识（优先查这里） |
| `references/F88-测试知识库总纲.md` | 业务模块全景 + 105条用例覆盖矩阵 |
| `references/F88-DB表速查.md` | 11张核心表 + 常用查询 |
| `references/F88-前端组件测试要点.md` | React+AntD 11个组件交互踩坑 |
| `references/audit-operations.md` | 操作动线 + 接口示例 + HSF 代码骨架 |
| `examples/f88-audit/tc01~tc27` | 27 个测试用例文件 |

## 知识库完整对齐矩阵

> 来源：`09-审核平台-业务规则.md`，105+ 条回归用例

| 知识库模块 | 用例数 | 覆盖用例 | 类型 |
|-----------|-------|---------|------|
| A: STREAM模式审核 | 3 | tc22 | API/DB |
| B: 封面图审核Type=4 | 4 | tc22 | API/DB |
| C: 审核全不通过与重产 | 3 | tc22 | API/DB |
| D: 幂等性与并发 | 4 | tc23 | API/DB |
| E: 触发机制 | 4 | tc23 | API/DB |
| F: 审核完成回调链 | 4 | tc23 | API/DB |
| G: 输出变量传递 | 4 | tc24 | API/DB |
| H: 错误路径 | 3 | tc24 | API/DB |
| I-A: 替换→CopyURL/下载/导出 | 7 | tc06, tc07 | UI |
| I-B: 裁剪→CopyURL/下载/导出 | 7 | tc08 | UI |
| I-C: 高清化→CopyURL/下载/导出 | 7 | tc20 | UI |
| I-D: 局部修改→CopyURL/下载/导出 | 7 | tc21 | UI |
| I-E: 驳回重生→CopyURL/下载/导出 | 7 | tc09 | UI |
| I-F: 编辑后下游流转验证 | 8 | tc25 | API/DB |
| J: 首图审核数据流转 | 6 | tc25 | API/DB |
| K: 套图审核数据流转 | 4 | tc25 | API/DB |
| L: 视频审核数据流转 | 4 | tc25 | API/DB |
| M: 跨节点数据一致性 | 5 | tc26 | API/DB |
| N: 驳回重生&状态异常 | 6 | tc26 | API/DB |
| O: hasFeedback&边界场景 | 8 | tc26 | API/DB |
| **合计** | **105** | **tc06~tc26** | — |

## 图片编辑操作知识

| 操作 | 说明 | 流程 | 确认后验证 |
|------|------|------|----------|
| 替换 | 替换图片文件 | 替换 → 编辑后 → ✅确认 | ①CopyURL得到**替换后**URL ②下载得到**替换后**图片 |
| 裁剪 | 图片尺寸/比例裁剪 | 裁剪 → 编辑后 → ✅确认 | ①CopyURL得到**裁剪后**URL ②下载得到**裁剪后**图片 |
| 高清化 | 图片分辨率增强 | 高清化 → 编辑后 → ✅确认 | ①CopyURL得到**高清化后**URL ②下载得到**高清化后**图片 |
| 局部修改 | AI局部修改(prompt输入) | hover主图→点击edit图标→填写prompt→确定→编辑后→✅确认 | ①CopyURL得到**局部修改后**URL ②下载得到**局部修改后**图片 ③出现编辑前/编辑后切换Radio |
| 去背景 | 抠图处理（当前UI无此按钮） | — | — |

**关键机制**：所有编辑操作必须经过「编辑后 + ✅确认」才生效，确认后 toolbar 才可见。

**工具栏按钮清单**（2026-07-09 链路20180实证）：

| 审核类型 | 按钮数 | 按钮列表 | 显隐方式 |
|---------|--------|---------|----------|
| 首图审核 (SingleImageReview) | 9 | 局部修改、下载、替换、裁剪、高清化、负反馈、**驳回**、复位、复制URL | hover图片区域显示，默认display:none |
| 套图审核 (SetImageReview) | 8 | 局部修改、下载、替换、裁剪、高清化、负反馈、复位、复制URL | hover图片区域显示，默认display:none |

> 差异：首图审核多一个「驳回」按钮；套图审核无驳回。代码层面全部硬编码在同一div中，无链路级显隐条件。
> 去背景：toolbar中无独立按钮，可能在其他入口或旧版本中存在。

**确认前后URL变化**：
- 确认前：`material.url` = 原始URL（如`llm/afd_image_*.jpg`），`material.localAdjustUrl` = 编辑后URL（如`localUpload/afd_image_*.jpg`），`material.localAdjustStatus` ≠ 0
- 确认后：`material.url` = 编辑后URL（从localAdjustUrl写入），`material.localAdjustStatus` = 0
- URL路径变化：从`/llm/`变为`/localUpload/`

**CopyURL/下载验证要求**（每个操作都必须验证）：
- CopyURL：复制的URL必须是编辑后的（即localAdjustUrl写入material.url后的值），不能是originUrl
- 下载：下载的图片必须是编辑后的版本，不能是原始素材图
- 前端逻辑：`handleCopyUrl(img.originUrl || img.url)`，需确认此逻辑在确认后返回的是更新后的url
