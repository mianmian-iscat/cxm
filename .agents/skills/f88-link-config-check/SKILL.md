---
name: f88-link-config-check
description: F88/i-FASHION 策略平台链路配置正确性检查路由器。覆盖 A(阶段编排) B(模板匹配) C(生图节点) D(审核节点) E(参数流转) F(环境运维) G(多套上传出参拆分) H(LLM文本节点) I(模型可用性) J(容量与限流) K(阶段流转与容错) L(逆向操作与生命周期联动) M(执行模式) 共 13 大类 61 项检查。只读数据库，不做任何写操作。当用户说"检查链路 XXXX""验证链路配置""新链路配置检查""link config check""查下链路 20XXX 有没有问题"时触发。
version: 2.3.2
x-source: aone-open
install_source: aone-kit
install_method: cli
name_zh: f88-link-config-check
---

# F88 链路配置检查（路由层）

> 本 skill 是**检查路由器**：根据链路 ID 执行 A~M 共 13 大类 61 项检查，输出结构化报告。
> 详细检查项定义和已知问题模式全部在知识库 .md 文档中。

## 知识库路径

```
f88-link-config-check/references/
├── checklist.md          ← A~M 共 61 项检查详细定义（唯一归属）
├── sql-templates.md      ← SQL 查询模板
├── report-template.md    ← 检查报告输出模板
├── known-issues.md       ← 已知问题模式速查（BT_6629/BT_6888 等）
└── scripts/
    └── l1-l5-param-check.py  ← L1/L5 三层递进判断自动化脚本
```

## 检查分类路由

| 检查分类 | 检查项数 | 关键场景 |
|----------|---------|----------|
| A. 阶段编排 | 6 | 阶段数量/UID唯一性/顺序/类型/生命周期 |
| B. 模板匹配 | 5 | matchScene/targetMatchCount/模板包条件 |
| C. 生图节点 | 4 | modelType/imageSize/outputRatio |
| D. 审核节点 | 8 | approveType/passedImg/imgUrlReview/数据源/execMode |
| E. 参数流转 | 5 | 跨阶段引用/编号/命名/通用参数 |
| F. 环境运维 | 5 | test链路清理/COOP/COEP响应头 |
| G. 多套上传 | 4 | 审核出参拆分/上传策略映射 |
| H. LLM文本节点 | 5 | JSON输出格式/prompt约束/modelType/变量引用 |
| I. 模型可用性 | 4 | 停用模型/单模型风险/类型匹配/白名单 |
| J. 容量与限流 | 4 | 并发配置/模板包体积/优先级负载 |
| K. 阶段流转 | 3 | 流转依赖/容错/重试触发 |
| L. 逆向操作 | 5 | 参数双向引用/撤回/驳回重生/回滚/跨策略一致性 |
| M. 执行模式 | 3 | execMode存在性/SchedulerX/BATCH/STREAM一致性 |

详细检查逻辑见 `references/checklist.md`。

## 检查流程

```
Step 0: 预检自检
  python3 scripts/l1-l5-param-check.py --self-test

Step 1: 获取链路基本信息
  SELECT id, name, env, life_cycle, struct FROM g_link WHERE id = {LINK_ID}
  从 struct JSON 解析 stages 数组

Step 2: 获取所有策略 workflow_def
  SELECT id, name, workflow_def FROM g_strategy WHERE id IN ({STRATEGY_IDS})
  解析 innerNodes 中的各节点配置

Step 3: 执行 A~M 检查项
  读取 references/checklist.md 获取每项检查的验证逻辑

Step 4: 生成检查报告
  输出格式：Markdown 表格，✅ 通过 / ⚠️ 告警 / ❌ 严重
  报告模板见 references/report-template.md
```

## 自动化脚本

L1（参数双向引用完整性）和 L5（跨策略参数流转一致性）已实现自动化：

```bash
python3 scripts/l1-l5-param-check.py <LINK_ID>            # 基础检查
python3 scripts/l1-l5-param-check.py <LINK_ID> --baseline  # 含基线对比
python3 scripts/l1-l5-param-check.py <LINK_ID> --json      # JSON 输出
```

## 核心约束

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
安全约束：只允许 SELECT 查询，禁止 INSERT/UPDATE/DELETE
workflow_record_log：查询必须带 id > 4000000 否则超时（近期批次建议 id > 6400000，与 f88-failure-analysis / f88-approve-verify-sql 口径一致）
查询安全规则（env 过滤铁律/写操作红线/ScheduleX 只读）：见 F88测试知识库/references/shared/query-safety-rules.md
CLI：见 F88测试知识库/references/shared/db-connections.md 标准调用格式
```

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 审核深度排查/SharedArrayBuffer 检查 | `strategy-platform` |
| 深度 SQL 归因（execMode/跨表一致性） | `f88-failure-analysis` |
| 自动化巡检(9维度) | `f88-pipeline-monitor` |
| 审核节点替换验证 | `f88-approve-verify-sql` |
| 失败数据聚类分析 | `f88-clustering-service` |
| 素材域问题排查 | `f88-mainimg-material` |
