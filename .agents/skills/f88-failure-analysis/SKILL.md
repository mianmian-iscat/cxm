---
name: f88-failure-analysis
description: i-FASHION 策略平台失败分析路由器。通过 dms-alibaba SQL 查询分析任意环节的失败数据，覆盖状态分布、错误分类、策略配置核查、输出物验证、阶段衔接、URL 过期、任务丢失、BATCH/STREAM 差异、跨表一致性、SharedArrayBuffer 环境排查、批次轨迹效率分析、Bad Case 回流等 13 个工作流。当用户说"分析某批次失败原因""查失败数据""核查策略模型配置""gen_img 失败""阶段间没有流转""图片URL过期""JSON解析失败""模型下线""BATCH和STREAM结果不一样""SharedArrayBuffer报错""审核任务卡INIT""批次效率分析""鬼打墙重试""Bad Case 回流"时触发。
version: 0.6.3
x-source: aone-open
install_source: aone-kit
install_method: cli
name_zh: f88-failure-analysis
---

# i-FASHION 策略平台失败分析（路由层）

> 本 skill 是**分析路由器**：定位用户问题属于哪个分析工作流，然后读取知识库对应 .md 文档执行排查。
> 详细工作流步骤、表结构、陷阱全部在知识库 .md 文档中。

## 知识库路径

```
f88-failure-analysis/references/
├── workflows.md        ← WF1~WF13 工作流详细步骤
├── sql-templates.md    ← SQL 查询模板
├── db-schema.md        ← 数据库表结构速查（5 张核心表）
└── result-reading.md   ← 结果文件读取 + Stage 3 归因报告增强
```

## 分析入口路由

| 用户输入 | 读取文档 |
|----------|----------|
| 批次失败概况/状态分布 | `workflows.md` → WF1 |
| 错误分类/errorMsg 统计 | `workflows.md` → WF2 |
| 策略配置核查/模型下线 | `workflows.md` → WF3 |
| 视频分辨率/输出物验证 | `workflows.md` → WF4 |
| 按策略/时间段维度分析 | `workflows.md` → WF5 |
| 为什么没进入XX阶段/阶段断裂 | `workflows.md` → WF6 |
| URL 过期/CDN 403/图片不可访问 | `workflows.md` → WF7 |
| 任务丢失/部分商品没到下游 | `workflows.md` → WF8 |
| BATCH/STREAM 结果不一样/replaceImage | `workflows.md` → WF9 |
| 跨表数据一致性/g_afd_material vs review_job | `workflows.md` → WF10 |
| SharedArrayBuffer/COOP/COEP/ffmpeg-wasm | `workflows.md` → WF11 |
| 批次效率分析/鬼打墙重试/收敛度/重试热点 | `workflows.md` → WF12 |
| Bad Case 回流/失败批次转回归用例 | `workflows.md` → WF13 |
| 审核任务卡INIT/审核任务创建失败（BT_7495） | 错误签名库审核平台类 + `F88测试知识库/references/patterns/review-platform/review-assignment-mismatch.md` |
| 审核完成但不流转/审核回调缺失（BT_7485） | 错误签名库审核平台类 + `F88测试知识库/references/patterns/review-platform/approve-callback-missing.md` |
| 需要查 SQL | `sql-templates.md` |
| 表结构/字段说明 | `db-schema.md` |
| 结果文件读取/Stage 3 归因报告 | `result-reading.md` |

## 核心约束

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
查询安全规则（env 过滤铁律/写操作红线/ScheduleX 只读）— 见 F88测试知识库/references/shared/query-safety-rules.md
工具：统一用 dms-alibaba CLI（禁用 taobao-cloth-afd-mcp / strategy-platform MCP / db-query-tool MCP）
workflow_record_log：必须带 id > 4000000 否则超时（近期批次建议 id > 6400000 进一步缩小扫描范围，与 f88-approve-verify-sql / f88-ffmpeg 口径一致）
status 失败值是 'FAIL'，不是 'FAILED'
错误字段是 $.errorMsg，不是 $.errorMessage
g_strategy 主键是 id，不是 strategy_id
JSON_EXTRACT 返回带引号的字符串，Python 解析时需 strip
extra_info / output_json 可能被截断，优先读取 JSON 结果文件
CDN 签名 URL 有时效性，注意区分"URL 本身无效"和"URL 签名过期"
模型下线不会自动更新策略配置
TPP 回调可能静默丢失，记录永远停在 HANDLING
SharedArrayBuffer 报错是环境问题不是代码 bug（预发 Nginx 未配置跨域隔离头）
禁止基于代码分支推断预发部署状态，必须先查 DB 实际数据验证。**当 DB 查询仍无法确认时（如分支路径不匹配、配置来源不明），必须自行到预发环境实操验证（跑一遍流程看实际行为），禁止停下来反问用户"要不要我去预发验证？"**——验证是义务不是选项，直接去验证，不要问
```

## 排查流程

1. 识别用户输入属于哪个路由（见上表）
2. 读取对应知识库 .md 文档
3. 按文档中的步骤执行 SQL 查询 / 验证 / 判读
4. 输出排查结论

## 知识→工具自动路由（3.3 MCP 工具链打通）

> 匹配到已知问题模式后，自动推荐工具链执行顺序，减少 Agent 自行决策的盲目尝试。

### 路由规则

| 匹配模式 | 推荐工具链（按顺序执行） | 来源 |
|----------|------------------------|------|
| 批次失败/状态异常 | ① DMS 查 g_workflow_batch → ② DMS 查 workflow_record_log → ③ SLS 查日志 | WF1-WF3 |
| 审核节点卡住 | ① DMS 查 workflow_record_log(approve) → ② Diamond 查配置 → ③ SLS 查回调日志 | WF6 |
| URL 过期/CDN 403 | ① DMS 查 g_afd_material(url) → ② curl 验证 URL 可达性 → ③ 对比签名时间戳 | WF7 |
| 任务丢失/部分没到下游 | ① DMS 查 g_workflow_batch(inputInfo) → ② DMS 查 workflow_record_log(按 batch_id) → ③ 对比预期 vs 实际 | WF8 |
| 模板匹配失败 | ① DMS 查 g_strategy → ② DMS 查模板包配置 → ③ 检查 seller_id 关联 | WF3 |
| 视频输出物异常 | ① DMS 查 gen_video 节点输出 → ② ffprobe 校验 → ③ 对比策略配置 | WF4 |
| 审核任务全 INIT | ① Diamond 查 supplier.seller.template.pkg.config → ② DMS 查模板包状态 → ③ 检查策略关联 | learned-solutions |

### 使用方式

1. 匹配到 learned-solutions.jsonl 中的 pattern 后，查上表获取推荐工具链
2. 按推荐顺序执行，前一步的输出作为后一步的输入
3. 推荐工具链不是硬约束——如果某一步工具不可用，走 qa-self-healing 的 MCP 三级降级协议
4. 排查结束后，将新的 pattern → 工具链映射追加到上表（如果发现了新的常见模式）

### 与 learned-solutions.jsonl 的协作

```
用户问题 → 知识匹配（learned-solutions.jsonl）→ 推荐工具链（上表）→ 按顺序执行
```

示例：
```
"BT_7817 卡在 approve 节点"
  → 匹配 learned-solutions：审核节点卡住
  → 工具链：DMS 查 workflow_record_log(approve) → Diamond 查配置 → SLS 查回调日志
  → 自动按顺序执行
```

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 实时查批次进度/重试节点 | `strategy-platform` |
| 自动化巡检(9维度) | `f88-pipeline-monitor` |
| 失败数据聚类分析 | `f88-clustering-service` |
| 审核节点替换验证 | `f88-approve-verify-sql` |
| 链路配置正确性检查 | `f88-link-config-check` |
| 视频输出物 ffprobe 校验 | `f88-ffmpeg` |
| 审核测试数据构造 | `审核数据构造` |
| 素材域问题排查 | `f88-mainimg-material` |
| 种草素材链路排查 | `f88-seeding-material` |
