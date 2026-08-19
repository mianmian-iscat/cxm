---
name: f88-log-analysis
description: >
  F88/i-FASHION 全链路日志分析路由器。通过 DMS 数据库查询 + SLS 日志联合排查，定位策略平台跑批、审核节点、素材生产、种草发布、纵横回流等端到端问题根因。
  当用户提到"查日志"、"排查问题"、"为什么失败"、"根因分析"、"数据异常"、"批次异常"、"审核卡住"、"素材没回流"、"发布失败"，或提供 BT_xxxx 批次号 / item_id / seller_id 要求排查时使用。
  排除：纯测试用例生成请用 hfz-test-workflow；纯造数据请用 qa-testing-workbench:审核数据构造。
version: 1.1.0
---

# F88/i-FASHION 全链路日志分析

> 本 skill 是 F88 端到端问题排查的**统一入口**。主通道为 DMS 数据库查询（`dms-alibaba` CLI），辅通道为 SLS 日志。按"定场景→选数据源→执行查询→交叉验证→输出结论"五步走。

## 整体流程

```
用户输入（BT_xxxx / item_id / seller_id / 现象描述）
        │
        ▼
  Step 1：确定排查场景（按路由表匹配 → 确定查询模板编号）
        │
        ▼
  Step 2：执行查询（主表查全貌 → 明细表追链路 → 跨表交叉验证）
        │
        ▼
  Step 3：分析归因（错误分类 → 根因定位 → 影响范围评估）
        │
        ▼
  Step 4：输出结论（结构化报告：现象/根因/证据链/建议）
```

## 基本要求

- 仅处理 F88/i-FASHION 相关问题，超出职责范围的请求礼貌拒绝
- 所有数据必须通过工具查询获取，不得假设不存在的数据
- SQL 查询**必须**加 `env='staging'` 过滤，禁止触碰生产数据
- `workflow_record_log` 查询**必须**加 `id > 9000000`（避免超时）
- 使用中文回答

## Step 1：场景路由表

| 用户输入关键词 | 排查场景 | 主查表 | 辅查表 | 查询模板 |
|---|---|---|---|---|
| BT_xxxx + 失败/报错 | 批次失败分析 | `workflow_record_log` | `g_admin_task`, `g_strategy` | T1 |
| BT_xxxx + 审核/卡住/驳回 | 审核节点排查 | `g_afd_review_job` | `workflow_record_log`, `g_afd_material` | T2 |
| item_id + 素材/图片/视频 | 素材生产排查 | `g_afd_material` | `workflow_record_log`, `g_afd_material_prod_record` | T3 |
| item_id + 种草/发布/回流 | 种草发布排查 | `g_afd_recommend_material_pool_record` | `workflow_record_log` | T4 |
| seller_id + 推送/上架 | 卖家维度排查 | `g_afd_recommend_material_pool_record` | `g_afd_material_prod_record` | T5 |
| BT_xxxx + 阶段/衔接/流转 | 阶段衔接排查 | `workflow_record_log` | `g_workflow_batch`, `g_workflow_instance` | T6 |
| link/链路 + 配置/检查 | 链路配置检查 | `g_link`, `g_strategy` | — | T7 |
| 报错 + traceId/trace | 链路追踪排查 | SLS | `workflow_record_log` | T8 |
| 视频 + 格式/编码/播放 | 视频产出校验 | `workflow_record_log` | ffprobe 验证 | T9 |

用户输入不完整时主动追问：无批次号也无商品ID → "请提供批次号（BT_xxxx）或商品ID（item_id）"；有批次号但无现象 → "请问具体是什么现象？"

**查询模板和 SQL 详见 [docs/sql-templates.md](docs/sql-templates.md)**

## 数据库与工具

> **强制规则**：涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，**必须先读取** `quderwork/f88素材生产/常用地址手册.md` 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。本 skill 内嵌的连接信息是缓存副本，以手册为准。

### 数据库连接

| 属性 | 值 |
|---|---|
| 数据库组 | `stylespot` |
| 物理实例 | `rm-lgay0v5lor8396yka` |
| DMS dbId | `5335708` |
| 环境过滤 | **必须** `env='staging'` |

### CLI 工具

**主通道：dms-alibaba CLI**

```bash
# 快速查询（结果 ≤ 200 行）
cd ~/dms-alibaba && bin/dms-alibaba sql query stylespot \
  --db rm-lgay0v5lor8396yka --sql "SELECT ..."

# 大批量查询（结果 > 200 行，自动保存到文件）
~/dms-alibaba/bin/dms-alibaba sql run stylespot \
  --db rm-lgay0v5lor8396yka --sql "SELECT ..."

# 环境异常时的降级写法
env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin \
  /bin/zsh -c 'dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "..."'
```

**辅通道：SLS 日志（需要 traceId 或精确时间窗口时）**

| 环境 | Project | LogStore | 用途 |
|---|---|---|---|
| 线上 | `stylespot-admin-log` | `stylespot-admin-online` | 线上应用日志 |
| 预发 | `stylespot-admin-log` | `stylespot-admin-pre` | 预发应用日志 |

### SLS 查询方式（normandy CLI 为主路径）

**主通道：normandy CLI**（已安装 v1.4.0，AIT 自动认证，无需额外凭证）

```bash
# 查询预发日志
normandy log list --source sls \
  --project stylespot-admin-log \
  --logstore stylespot-admin-pre \
  --query "<关键词或SLS查询语句>" \
  --from "YYYY-MM-DD HH:MM:SS+0800" \
  --to "YYYY-MM-DD HH:MM:SS+0800" \
  --size 50 --reverse --output json

# 查询线上日志
normandy log list --source sls \
  --project stylespot-admin-log \
  --logstore stylespot-admin-online \
  --query "<关键词>" \
  --from "YYYY-MM-DD HH:MM:SS+0800" \
  --to "YYYY-MM-DD HH:MM:SS+0800" \
  --size 50 --reverse --output json
```

**辅通道：CC 平台浏览器**（仅用于截图确认，不可搜索）

CC 平台 SLS 入口：`https://cc.alibaba-inc.com/resource/app/stylespot-admin?identityType=APPLICATION&filterType=own_app&resourceType=ALIYUN_SLS_LOGSTORE`
- 可以点击左侧日志库切换 LogStore（父页面元素，可操作）
- **不可**在 iframe 内输入搜索词或读取日志（跨域限制）
- 用途：截图确认 LogStore 切换成功、查看日志条数概览

**禁止行为**：
- ❌ 在 CC 平台 iframe 内反复尝试 type/click 搜索 → 永远不会成功
- ❌ 用 JavaScript 访问 `iframe.contentDocument` → 跨域报错
- ❌ 打开新标签页直接访问 SLS 控制台 → ticket 已消费/需独立登录

**环境检查工具**

```bash
# COOP/COEP 跨域隔离检查
curl -sI https://pre-aifashion-xiaoer.alibaba-inc.com/ | grep -iE 'cross-origin-(opener|embedder)-policy'

# 视频产出物校验
ffprobe -v quiet -print_format json -show_streams -show_format "{url}"
```

## 反模式表

| 反模式 | 正确做法 | 原因 |
|---|---|---|
| `SELECT * FROM workflow_record_log WHERE node_type = 'gen_img'` | 必须加 `id > 9000000` | `node_type` 无索引，裸查全表扫描超时 |
| 用 `$.errorMessage` 取错误信息 | 用 `$.errorMsg` | 字段名是 `errorMsg`，不是 `errorMessage` |
| 查 `g_strategy` 用 `WHERE strategy_id = X` | 用 `WHERE id = X` | PK 是 `id`，不是 `strategy_id` |
| 用 `g_workflow_batch.relation_id` 当批次号 | `relation_id` 是链路 ID | 批次号是 `batch_id`（BT_xxxx 格式） |
| 用 `g_afd_review_job.info` 当实时 URL | `info` 是创建时快照 | replaceImage 不更新 `info`，实时值看 `g_afd_material.url` |
| 用 `g_afd_material.type` 当素材类型 | `type` 永远是"图片" | 该字段是媒体格式，不是素材业务类型 |
| 查询不带 `env='staging'` | 必须加环境过滤 | 防止触碰生产数据 |
| 状态值写 `'FAILED'` | 写 `'FAIL'` | 数据库值是 `FAIL`，不是 `FAILED` |
| `JSON_EXTRACT` 结果直接比较 | 用 `JSON_UNQUOTE()` 包裹 | `JSON_EXTRACT` 返回带引号的字符串 |
| 在 CC 平台 SLS iframe 内 type 搜索词 | 点击左侧 LogStore 切换，搜索走降级策略 | iframe 跨域，自动化无法操作内部元素 |
| 反复尝试不同方式操作 SLS iframe | 识别到跨域后立即降级 | 避免死循环浪费 token |
| 打开新标签页访问 SLS 控制台 | 用 CC 平台入口或降级到 DB 验证 | ticket 已消费/需独立登录 |

## 边界条件

| 场景 | 处理方式 |
|---|---|
| DMS 查询超时 | 检查是否遗漏 `id > 9000000` 或 `env='staging'`；缩小查询范围 |
| DMS 返回 0 行 | 确认 batch_id/item_id 拼写；扩大时间范围；检查是否在预发环境 |
| DMS 结果 > 200 行 | 改用 `sql run` 模式（结果保存到文件）；或加 LIMIT |
| 需要 MQ 消息追踪 | 路由到 SLS 辅通道，搜索 `sendWorkflowRecordFinishMsg` |
| 需要视频参数校验 | 使用 ffprobe 工具校验产出物 |
| 超出 F88 范围 | 礼貌拒绝，说明职责定位为 F88/i-FASHION 全链路日志分析 |
| 需要造数据 | 引导用户使用 `qa-testing-workbench:审核数据构造` |
| 需要生成测试用例 | 引导用户使用 `hfz-test-workflow` 编排器 |

## 输出格式与交互样例

详见 [docs/output-format.md](docs/output-format.md)
