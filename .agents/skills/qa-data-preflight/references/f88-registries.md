# F88/i-FASHION Data Registry 条目

> 📋 F88 测试商家 seller_id 统一维护入口：[test-accounts.md](../../web-automation/knowledge/synced-qoderwork/f88-test/test-accounts.md)

本文件注册 F88 业务域下所有可自动造数的数据类型，供 qa-data-preflight 的 Stage 0-1 消费。

---

## 1. template_package — 模板包

```yaml
data_type: template_package
display_name: 模板包
domain: f88

create_skill: f88-template-package-create
create_method: skill
params_template:
  applyRange: "{gap.requirement.applyRange}"
  applyScene: "{gap.requirement.applyScene}"
  cateId: "auto_diverse"
  styleTags: "auto_diverse"
  count: "{gap.deficit.cateId}"

verify_query: |
  SELECT
    COUNT(DISTINCT cate_id) as cate_cnt,
    COUNT(DISTINCT style_tags) as tag_cnt
  FROM template_package
  WHERE env='staging'
    AND status IN (3, 4)
    AND apply_range = '{gap.requirement.applyRange}'
    AND apply_scene = '{gap.requirement.applyScene}'
verify_method: sql
min_threshold:
  cate_cnt: "{gap.requirement.cateId.min_distinct}"
  tag_cnt: "{gap.requirement.styleTags.min_distinct}"

depends_on: []
cooldown_ms: 5000
max_retries: 3
backoff_ms: [30000, 60000, 120000]

description: F88 模板包数据，需保证 cateId 和 styleTags 的多样性
affected_cases_hint: 模板匹配相关用例（风格排序/CTR排序/Clone去重/排序组合）
```

### 造数要点

- 通过浏览器自动化在 `pre-aifashion-xiaoer.alibaba-inc.com/templateManagement` 创建
- 必须带 `X-AFD-Emp-Identity: f88` header，否则落到 AFD 租户
- 测试店铺 `sellerId = 2219662018344`
- `skipReview: true` 直接到 IDLE(3) 状态
- 命名规范 `mmtest_{场景中文}{环节中文}{月日}`
- 每次创建需多样化 cateId 和 styleTags，避免数据单一

### 枚举映射

环节 (applyRange): COLLOCATION(搭配) / VIEW(视觉) / SET(套图) / VIDEO(视频)
场景 (applyScene): F88_MAIN_IMAGE(主图) / F88_SEEDING(种草)

---

## 2. strategy_config — 策略配置

```yaml
data_type: strategy_config
display_name: 策略配置
domain: f88

create_skill: f88-link-config-check
create_method: skill
params_template:
  nodeType: "{gap.requirement.nodeType}"
  action: "verify_and_report"

verify_query: |
  SELECT COUNT(DISTINCT id) as cnt
  FROM g_strategy
  WHERE env='staging'
    AND status = 1
    AND workflow_def LIKE '%{gap.requirement.nodeType}%'
verify_method: sql
min_threshold:
  cnt: "{gap.requirement.count.min}"

depends_on: [template_package]
cooldown_ms: 3000
max_retries: 2
backoff_ms: [10000, 30000]

description: F88 策略配置，需保证特定 nodeType 的策略存在且可用
affected_cases_hint: 策略执行相关用例（节点配置/模型类型/输出参数）
```

### 造数要点

- 策略配置通常已存在（配置型数据），优先验证而非创建
- 如果不存在，说明链路配置缺失，需通过 `f88-link-config-check` 诊断
- 真正的"创建策略"需通过 UI 操作（策略平台页面），不在自动造数范围内
- 此条目的核心作用是**验证策略配置就绪**，发现缺失后标记 BLOCKED_LOGIC

### 常见检查项

- modelType 是否为有效模型（已下线模型会导致 gen_img 持续失败）
- workflow_def 中 innerNodes 是否包含目标 nodeType
- imageSize / outputRatio 是否在合理范围

---

## 3. batch_data — 批次数据

```yaml
data_type: batch_data
display_name: 批次数据
domain: f88

create_skill: strategy-platform
create_method: skill
params_template:
  action: "trigger_batch"
  linkId: "{gap.requirement.linkId}"

verify_query: |
  SELECT COUNT(*) as cnt
  FROM g_workflow_batch
  WHERE env='staging'
    AND relation_id = '{gap.requirement.linkId}'
    AND status IN ('SUCCESS', 'FAIL', 'HANDLING')
verify_method: sql
min_threshold:
  cnt: 1

depends_on: [strategy_config]
cooldown_ms: 60000
max_retries: 1
backoff_ms: [120000]

description: F88 策略批次数据，通过触发链路生产
affected_cases_hint: 端到端流转用例（阶段衔接/出参传递/任务完整性）
```

### 造数要点

- 批次通过触发策略链路生产，不是直接创建
- 必须先确保 strategy_config 就绪（depends_on 约束）
- 触发入口：`pre-aifashion-xiaoer.alibaba-inc.com/strategy/list` 触发策略执行
- 批次执行耗时较长（cooldown_ms=60000），需等待足够时间
- 禁止手动 API 创建批次——手动任务不接 workflow 管线

### 触发后验证

1. 查 `g_workflow_batch` 确认批次已创建
2. 查 `workflow_record_log` 确认各节点有执行记录
3. 查各节点 status 分布，确认有 SUCCESS 记录

---

## 4. review_task — 审核任务

```yaml
data_type: review_task
display_name: 审核任务
domain: f88

create_skill: qa-testing-workbench:审核数据构造   # 方式一：策略试运行+固定模板（首选，产出真实BT_批次）；UI需显示图片用方式二手动API
create_method: skill
params_template:
  taskType: "{gap.requirement.taskType}"
  excel_template: "/Users/caoxuemei/qoder/f88素材生产/审核专用模板.xlsx"   # 固定模板，每次直接使用，不重新找图片

verify_query: |
  SELECT COUNT(*) as cnt
  FROM g_afd_review_main_task
  WHERE env='staging'
    AND job_type = '{gap.requirement.jobType}'
    AND status > 0
verify_method: sql
min_threshold:
  cnt: "{gap.requirement.count.min}"

depends_on: [batch_data]
cooldown_ms: 10000
max_retries: 2
backoff_ms: [15000, 30000]

description: F88 审核任务数据（首图审核/套图审核/视频审核）
affected_cases_hint: 审核流程用例（审核判定/抽检/驳回重生）
```

### 造数要点

- **首选**：`审核数据构造` 方式一（策略试运行 + 固定模板 `f88素材生产/审核专用模板.xlsx`），产出真实 BT_ 批次、走完整 workflow 管线
- **备选**：方式二（手动创建 API），dataFileUrl 有值、UI 正常显示图片，用于 UI 单点验证（无批次）
- job_type 枚举：1=首图审核 / 2=套图审核 / 4=视频审核
- 抽检需显式调用 `/api/afd/review/task/main/inspection/create`

---

## 5. template_match_result — 模板匹配结果

```yaml
data_type: template_match_result
display_name: 模板匹配结果
domain: f88

create_skill: strategy-platform
create_method: skill
params_template:
  action: "trigger_node"
  nodeType: "template_match"
  batchId: "{gap.requirement.batchId}"

verify_query: |
  SELECT COUNT(*) as cnt
  FROM workflow_record_log
  WHERE id > 4000000
    AND batch_id = '{gap.requirement.batchId}'
    AND node_type = 'template_match'
    AND status = 'SUCCESS'
verify_method: sql
min_threshold:
  cnt: 1

depends_on: [template_package, strategy_config]
cooldown_ms: 30000
max_retries: 2
backoff_ms: [30000, 60000]

description: 模板匹配节点的执行结果
affected_cases_hint: 匹配结果验证用例（matchedImgGroupList/排序/去重）
```

### 造数要点

- 模板匹配结果通过触发 template_match 节点生产
- 依赖 template_package（匹配数据源）和 strategy_config（匹配策略）
- 当前所有 template_match 策略走 V1 路径，V2 路径无策略启用

---

## 扩展指南

添加新的 F88 数据类型时：

1. 在本文件末尾新增一个条目，编号递增
2. 填写所有必填字段（data_type / create_skill / verify_query / min_threshold）
3. 确认 `create_skill` 对应的 skill 已安装
4. 确认 `verify_query` 的 SQL 在 dms-alibaba 中已验证可执行
5. 如果新类型依赖已有类型，在 `depends_on` 中声明
6. 添加"造数要点"段落说明关键注意事项

不需要修改 qa-data-preflight 的逻辑——Registry 是纯配置驱动的。
