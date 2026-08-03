# F88 素材生产 - UI 自动化用例清单

> 场景：F88 素材生产（策略平台 / 批次管理 / 看板 / 生图节点 / 图片编辑）
> 环境：预发 `pre-aifashion-xiaoer.alibaba-inc.com`（UI 框架 react-antd）
> 知识库：`knowledge/f88-material-production.json`
> 统计：UI 自动化用例共 **14 条**

---

## 一、策略平台 UI 用例（`examples/f88-audit/`，Puppeteer JSON）

| 用例文件 | ID | 页面 / URL | 覆盖场景 | 关联用例ID |
|---|---|---|---|---|
| tc12_strategy_link_list.json | f88-strategy-tc12 | 链路列表 `/strategy/linkList` | 导航 + 搜索 + 筛选 + 新建/编辑/复制/删除链路 | RP-SL-01~08 |
| tc13_link_detail.json | f88-strategy-tc13 | 链路详情 `/strategy/linkDetail?id=20180` | 链路名称 + 阶段 + 环节展示 + 试运行 + 起点入参 | RP-LD-01~08 |
| tc14_strategy_list.json | f88-strategy-tc14 | 策略列表 `/strategy/list` | 导航 + 搜索 + 筛选 + 打开策略 → 详情(节点编排/落库配置) | RP-ST-01~06 |
| tc15_production_dashboard.json | f88-strategy-tc15 | 生产看板 `/strategy/productionDashboard` | 整体推送进度(总任务/生产中/已推送/未推送) + 链路生产进度 + 任务展开/下载 | RP-PD-01~12 |
| tc16_add_node.json | f88-strategy-tc16 | 新增节点 | 打开策略 → 新增节点 → 节点类型弹窗(20种) + 节点编排验证 | RP-ND-01~12 |
| tc17_create_link.json | f88-strategy-tc17 | 新建链路 | 新建链路 → 填写链路信息/起点入参/添加环节 → 详情验证 | RP-NL-01~08 |
| tc18_view_run_results.json | f88-strategy-tc18 | 查看运行结果 | 链路详情 → 查看运行结果弹窗(5环节/任务列表/状态/出参/终止/添加策略) | RP-RR-01~10 |
| tc19_trial_run.json | f88-strategy-tc19 | 试运行弹窗 | 链路详情 → 试运行弹窗(下载模板/上传Excel/任务名称/运行类型/发起运行) | RP-TR-01~08 |

## 二、图片编辑 UI 用例（高清化 / 局部修改）

| 用例文件 | ID | 场景 | 关联用例ID |
|---|---|---|---|
| tc20_hd_enhance.json | f88-audit-tc20 | 高清化 → CopyURL/下载/Excel导出/API验证（知识库模块 I-C） | NEW-I15~I21（7条） |
| tc21_local_modify.json | f88-audit-tc21 | 局部修改 → CopyURL/下载/Excel导出/API验证（知识库模块 I-D） | NEW-I22~I28（7条） |

## 三、端到端集成 UI 用例

| 用例文件 | ID | 流程 | 步骤数 |
|---|---|---|---|
| tc27_e2e_integration.json | f88-e2e-tc27 | 参考链路20180 → 新建策略(生图+人工审核+高清化) → 新建链路+绑定策略 → 试运行 → 各环节监控 → API/DB数据流验证 | 29条（E2E-01~29） |

## 四、回归 UI+API 混合用例（`eval/cases/`，可执行）

| 用例文件 | ID | 标题 | 优先级 | 子用例 |
|---|---|---|---|---|
| regression_f88_prod_strategy_trial.json | regression-f88-prod-strategy-trial | 策略配置节点+试运行（生图 gen_img / 文本 llm_text / 高清化 image_enhance） | P0 | MP-001/005/020/023/030 |
| regression_f88_prod_auto_review.json | regression-f88-prod-auto-review-ctr | 机审算法+CTR择优（AI_QUALITY / BAD_MATERIAL / CTR_RANKING） | P0 | MP-040/041/042 |
| regression_f88_prod_batch_stream.json | regression-f88-prod-batch-stream | 批次管理+流式生产+素材写入校验 | P0 | MP-070~072/090/100/101 |

---

## 场景组织规范

- `examples/f88-audit/` 中 **tc12–tc19** 为策略平台生产用例、**tc20/tc21** 为图片编辑、**tc27** 为端到端集成。
- `eval/cases/regression_f88_prod_*.json` 为可执行回归用例（UI 触发 + API 断言）。
- 页面结构 / 选择器 / API / 坑点详见 `knowledge/f88-material-production.json`。

## 未纳入说明

- **tc01–tc11**：属素材**审核**场景（人工审核 / 审核标准 / 审核节点 / 任务管理 / 图片编辑操作），不属于素材生产。
- **tc22–tc26**：后端 API/DB 级 pytest 用例，非 UI 自动化。
