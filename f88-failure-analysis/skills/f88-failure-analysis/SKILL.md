---
name: f88-failure-analysis
version: 1.1.0
description: Deep SQL-based failure analysis for i-FASHION strategy platform via dms-alibaba CLI
description_zh: 通过dms-alibaba SQL查询深度分析i-FASHION策略平台任意环节的失败数据，覆盖状态分布、错误分类、策略配置核查、输出物验证（ffprobe 视频校验）
---

# i-FASHION 策略平台失败分析

通过 `dms-alibaba` CLI 对 `workflow_record_log` 等表做 SQL 深度分析，定位失败根因。实时运维（查进度、重试、推审核）请使用「策略平台运维」skill，本 skill 专注离线归因（errorMsg 分类、策略配置核查、输出物验证）。

## 前置条件

- `dms-alibaba` CLI 已安装并配置，能访问 stylespot 数据库组
- 数据库：`rm-lgay0v5lor8396yka`（stylespot 组）
- Python 3 可用（用于 JSON 解析和视频参数检查）
- `ffmpeg` / `ffprobe` 已安装（视频输出物校验，通过 `pip3 install --user static-ffmpeg`，symlink 在 `~/.local/bin/`）

## 关键陷阱（必读）

在执行任何查询前，务必注意以下坑点：

1. **状态值是 `FAIL` 不是 `FAILED`**。第一次查失败数据时几乎必踩，用 `WHERE status = 'FAIL'`。
2. **错误信息字段是 `$.errorMsg` 不是 `$.errorMessage`**。两个字段名都存在但内容不同，`errorMsg` 包含实际错误详情，`errorMessage` 通常为空。
3. **`workflow_record_log` 是超大表**。查询必须加 `id > N` 过滤条件（N 通常取 4000000 或更高），否则会超时。
4. **`g_strategy` 主键是 `id` 不是 `strategy_id`**。关联时用 `g_strategy.id = g_workflow_instance.strategy_id`。
5. **`JSON_EXTRACT` 返回带引号的字符串**。在 SQL 结果中值会被双引号包裹，Python 解析时需 strip。
6. **`extra_info` 和 `output_json` 内容可能被截断**。dms-alibaba 返回的 JSON 文件可能比终端显示更完整，优先读取 JSON 结果文件。

## 工作流 1：状态分布总览

目标：快速了解批次整体失败情况，不预设具体环节。

```
第 1 步：查询批次全部状态分布

  SQL 模板见 [references/sql-templates.md](references/sql-templates.md) → "状态分布查询"
  
  关键：按 status + node_type 分组，一次看到所有环节的成功/失败/处理中数量。
  
第 2 步：识别主要失败环节

  从结果中找出 FAIL 数量最多的 node_type。
  常见环节：gen_img（生图）、gen_video（生视频）、llm_text（文本生成）、strategy（策略层）。
  
第 3 步：向用户汇报总览

  格式示例：
  "BT_xxxx 共 N 个环节有失败：gen_img 654 条、strategy 151 条、llm_text 8 条。"
```

## 工作流 2：错误信息分类统计

目标：对指定环节的 FAIL 记录，提取 errorMsg 并按类型分组统计。

```
第 1 步：提取原始错误信息样本

  先拉少量记录（LIMIT 10）看 errorMsg 的内容模式，用于设计 CASE WHEN 分组条件。
  SQL 模板见 references/sql-templates.md → "错误信息样本提取"

第 2 步：用 CASE WHEN + LIKE 分组统计

  根据第 1 步看到的错误模式，编写 CASE WHEN 语句。
  SQL 模板见 references/sql-templates.md → "错误分类统计"
  
  常见错误模式（持续积累）：
  - "Error 404" / "was not found on this server" → API 路径错误
  - "upstream request failed" → 上游服务不可达
  - "算法返回结果为空" → 算法层返回空
  - "RESOURCE_EXHAUSTED" / "429" → Quota 耗尽
  - "Internal error encountered" / "500" → 模型内部错误
  - "unexpected end of stream" → 流截断
  - "Cannot fetch content" → URL 不可访问
  - "算法处理失败" → 算法处理异常

第 3 步：汇报错误分布

  格式示例：
  "gen_img 654 条失败中：Gemini API 404（386 条，59%）、上游服务请求失败（299 条，46%）、unexpected end of stream（6 条）。"
```

## 工作流 3：策略配置核查

目标：从 `g_strategy.workflow_def` 提取模型配置，判断失败是否与配置有关。

```
第 1 步：获取失败记录关联的 strategy_id

  从 workflow_record_log 关联 g_workflow_instance，拿到 strategy_id。
  SQL 模板见 references/sql-templates.md → "获取 strategy_id"

第 2 步：查询 g_strategy 的 workflow_def 配置

  从 workflow_def JSON 提取 innerNodes 数组中各节点的 modelType、imageSize、outputRatio 等。
  SQL 模板见 references/sql-templates.md → "策略配置提取"

第 3 步：对比正常策略与异常策略

  如果有同类正常策略，对比两者的配置差异，重点关注：
  - modelType 是否为有效模型名
  - imageSize / outputRatio 是否合理
  - 是否有缺失的必填字段

第 4 步：检查 API 路径错误

  如果 errorMsg 中出现 URL 路径异常（如 publishers//models 双斜杠），
  说明 modelType 到 API 路径的映射逻辑有 bug，需要告知开发排查代码中 publisher 字段的赋值逻辑。
```

## 工作流 4：输出物验证（可选）

目标：下载 gen_video / gen_img 的输出物，验证其实际属性。

### 4a. 视频参数校验（ffprobe）

```
第 1 步：提取视频 URL

  从 output_json 提取 $.outputVideo。
  SQL 模板见 references/sql-templates.md → "视频 URL 提取"

第 2 步：下载视频

  使用 curl 下载：
  curl -sL -o /tmp/vid_{record_id}.mp4 "{video_url}"

第 3 步：用 ffprobe 提取全量参数

  ~/.local/bin/ffprobe -v quiet -print_format json -show_format -show_streams /tmp/vid_{record_id}.mp4

  关键参数：
  - streams[video].width / height → 分辨率
  - streams[video].codec_name → 编码（h264/hevc）
  - streams[video].r_frame_rate → 帧率（24/1, 25/1, 30/1）
  - format.duration → 时长（应 ≤ 60s）
  - format.size → 文件大小

第 4 步：完整性校验

  ~/.local/bin/ffprobe -v error /tmp/vid_{record_id}.mp4
  无输出 = 文件完整，有输出 = 文件损坏。

  如果 ffprobe 未安装：
  pip3 install --user static-ffmpeg

  详细基线参数见知识库：infra/ffmpeg-verification.md
```

### 4b. 图片可访问性验证

```
第 1 步：提取图片 URL

  从 output_json 提取相关图片字段（视具体节点类型而定）。

第 2 步：检查 HTTP 状态码

  curl -sL -o /dev/null -w "%{http_code}" "{image_url}"
  
  200 = 可访问，404 = 不存在，403 = 权限问题。
```

## 工作流 5：时间与策略维度分析

目标：判断失败是全局性问题还是特定策略/时间段的问题。

```
第 1 步：按策略分组统计失败数

  SQL 模板见 references/sql-templates.md → "策略维度分析"
  
  如果各策略失败数均匀 → 全局性问题（如 API 服务不稳定）
  如果集中在某策略 → 该策略的配置或数据问题

第 2 步：查询失败时间范围

  SQL 模板见 references/sql-templates.md → "时间维度分析"
  
  集中在短时间段 → 服务瞬时故障
  持续分布 → 持续性配置或服务问题

第 3 步：综合判断并输出结论

  交叉验证：错误类型 × 策略分布 × 时间分布
  示例结论：
  "654 条 gen_img 失败集中在 20:30~20:40 约 10 分钟内，6 个策略均匀分布，
   99% 为 Gemini API 异常（404 + upstream failed），属于 Gemini 服务基础设施问题。"
```

## 数据库表结构速查

### workflow_record_log

| 字段 | 说明 |
|------|------|
| id | 自增主键，也用于范围过滤加速查询 |
| batch_id | 批次 ID（如 BT_5441） |
| workflow_instance_id | 关联 g_workflow_instance |
| node_type | 环节类型：gen_img / gen_video / llm_text / strategy / template_match / industry_tag / season_tag 等 |
| status | 状态：SUCCESS / FAIL / HANDLING / INIT |
| extra_info | JSON，包含 errorMsg、strategyName、nodeName 等 |
| output_json | JSON，包含输出物 URL（outputVideo 等） |
| gmt_create | 创建时间 |

### g_workflow_instance

| 字段 | 说明 |
|------|------|
| workflow_instance_id | 主键 |
| strategy_id | 关联 g_strategy.id |
| common_variable | JSON，包含 seller_id 等运行时变量 |

### g_strategy

| 字段 | 说明 |
|------|------|
| id | 主键（注意不是 strategy_id） |
| name | 策略名称 |
| workflow_def | JSON，包含 innerNodes 数组（各节点配置） |
| extra_info | JSON，策略级额外配置 |

innerNodes 中每个节点的常见字段：`UId`、`name`、`type`（对应 node_type）、`modelType`、`imageSize`、`outputRatio`、`outputModel`。

## 结果文件读取

dms-alibaba 查询结果保存在 `~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{日期}/{时间}_rm-lgay0v5lor8396yka.json`。

当终端输出被截断时（尤其是 extra_info、workflow_def 等大 JSON 字段），用 Python 读取完整结果文件：

```python
import json, os
result_path = os.path.expanduser("~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{日期}/{文件名}.json")
with open(result_path) as f:
    data = json.load(f)
for row in data.get("rows", []):
    print(row)
```
