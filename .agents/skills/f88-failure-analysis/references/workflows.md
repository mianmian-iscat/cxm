# 失败分析工作流详细定义

> 本文件是 f88-failure-analysis 的工作流知识库，包含 WF1~WF13 的完整步骤。
> SKILL.md 只做路由，具体执行时读取本文件获取步骤详情。

## 三层归因模型（v2.0 新增）

> 借鉴《从聊天到驾驭：Agent 时代的工作设计》课程——"AI 任务失败，先别急着改提示词"。
> 只有知道错误发生在能力、信息还是机制，失败才会告诉我们下一次究竟应该改变什么。

每个 WF 执行完毕后，必须输出 `attribution_layer` 和 `recommended_action`，让失败分析直接告诉执行者"该改什么"。

| 归因层 | 含义 | 典型修复动作 |
|--------|------|-------------|
| **capability** | 模型/算法无法稳定完成核心判断（能力锯齿） | 更新 Skill 方法、增加边界规则、补充模型约束 |
| **information** | 完成任务所需的条件没有进入上下文（信息缺口） | 补充 Context 信息、更新知识库、增加入参校验 |
| **mechanism** | 运行方式没有给错误留下暴露和纠正的机会（机制缺失） | 增加检查点、调整重试策略、修改 CP 协议、增加超时补偿 |

诊断型 WF（WF1/WF2/WF5）本身不直接定位根因层，但它们的输出帮助缩小归因范围。

## 三孤岛分类模型（评测体系对标）

> 借鉴《AI 应用评测方法与实践》——三孤岛理论：理解鸿沟（开发者↔数据）、具象鸿沟（开发者↔AI应用）、泛化鸿沟（AI应用↔数据）。
> 与三层归因模型互补：三层归因聚焦"该改什么"（能力/信息/机制），三孤岛聚焦"失败源自哪里"（数据/指令/工程）。

每个 WF 执行完毕后，除输出 `attribution_layer` 外，还须输出 `gapType`，让失败分析同时具备"修复方向"和"来源定位"两个维度。

| 鸿沟 | gapType | 含义 | F88 典型场景 | 优化方向 |
|------|---------|------|-------------|---------|
| 理解鸿沟 | `data` | 喂给系统的数据本身有问题 | 输入素材 URL 过期/403、商品数据缺失、图片质量不达标、离线数据未同步 | 数据清洗、数据源治理、输入校验前置 |
| 具象鸿沟 | `prompt` | 系统意图未能正确传达给 AI 模型 | 策略配置错误、Prompt 导致幻觉、模板匹配逻辑错误、模型参数不当 | Prompt 工程、策略配置校验、模型参数调优 |
| 泛化鸿沟 | `engineering` | 面对多样化输入时系统行为不稳定 | BATCH/STREAM 不一致、边界格式解析失败、并发任务丢失、SharedArrayBuffer 环境差异 | 工程加固、异常处理、兼容性适配 |

### 与三层归因模型的映射

| 归因层 \ 鸿沟 | data | prompt | engineering |
|--------------|------|--------|-------------|
| capability | 模型处理脏数据失败 | Prompt 超出模型能力 | 边界 case 触发模型不稳定 |
| information | 数据未进入上下文 | 配置信息缺失 | 环境信息未传递 |
| mechanism | 数据源同步机制缺失 | 无 Prompt 校验检查点 | 重试/降级/兼容机制缺失 |

### WF 输出格式增强

每个 WF 执行完毕后，输出以下增强格式：
```json
{
  "attribution_layer": "capability | information | mechanism | diagnostic",
  "gapType": "data | prompt | engineering",
  "recommended_action": "具体修复建议",
  "optimization_direction": "数据治理 | Prompt工程 | 工程加固"
}
```

**判定规则**：
- errorMsg 含 URL 过期/403/资源不存在/数据缺失 → gapType = `data`
- errorMsg 含模型下线/配置错误/Prompt 幻觉/匹配逻辑错误 → gapType = `prompt`
- errorMsg 含 超时/限流/解析失败/SharedArrayBuffer/不一致/并发丢失 → gapType = `engineering`
- 多因素混合时，取占比最高的 gapType，并在 detail 中注明混合因素

## WF1：状态分布总览

目标：快速了解批次整体失败情况，不预设具体环节。

```
第 1 步：查询批次全部状态分布
  SQL 模板见 references/sql-templates.md → "状态分布查询"
  关键：按 status + node_type 分组，一次看到所有环节的成功/失败/处理中数量

第 2 步：识别主要失败环节
  从结果中找出 FAIL 数量最多的 node_type
  常见环节：gen_img（生图）、gen_video（生视频）、llm_text（文本生成）、strategy（策略层）

第 3 步：向用户汇报总览
  格式："BT_xxxx 共 N 个环节有失败：gen_img 654 条、strategy 151 条、llm_text 8 条。"

第 4 步：输出归因提示（诊断型，缩小归因范围）
  attribution_layer: "diagnostic"（本 WF 为总览，不直接定位根因层）
  attribution_hint: 根据 FAIL 集中环节预判——
    - 集中在 gen_img/gen_video/llm_text → 倾向 capability 或 information
    - 集中在 strategy → 倾向 information（配置缺失）或 mechanism（流转问题）
    - 多环节均匀分布 → 倾向 mechanism（全局性环境问题）
  recommended_action: 根据 attribution_hint 路由到对应 WF 深入排查
```

## WF2：错误信息分类统计

目标：对指定环节的 FAIL 记录，提取 errorMsg 并按类型分组统计。

```
第 1 步：提取原始错误信息样本
  先拉少量记录（LIMIT 10）看 errorMsg 的内容模式，用于设计 CASE WHEN 分组条件
  SQL 模板见 references/sql-templates.md → "错误信息样本提取"

第 2 步：用 CASE WHEN + LIKE 分组统计
  根据第 1 步看到的错误模式，编写 CASE WHEN 语句
  SQL 模板见 references/sql-templates.md → "错误分类统计"

  ⚠️ 错误签名库唯一归属（勿在本文件维护副本）：
  ~/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/error-signatures.md
  编写 CASE WHEN 前先读取该文件获取最新签名全集

第 3 步：汇报错误分布
  格式："gen_img 654 条失败中：Gemini API 404（386 条，59%）、上游服务请求失败（299 条，46%）"

第 4 步：输出归因提示（诊断型，缩小归因范围）
  attribution_layer: "diagnostic"（本 WF 为错误分类，不直接定位根因层）
  attribution_hint: 根据错误类型分布预判——
    - API 404/429/500/模型下线 → 倾向 capability（模型能力不足）或 information（配置指向错误模型）
    - URL 过期/资源不存在 → 倾向 information（数据源失效）
    - JSON 解析失败/字段缺失 → 倾向 capability（LLM 输出不稳定）或 mechanism（缺少校验）
    - 超时/限流/队列积压 → 倾向 mechanism（容量或重试策略缺失）
  recommended_action: 根据错误类型路由——
    - capability 倾向 → WF3（核查策略配置）+ WF4（验证输出物质量）
    - information 倾向 → WF7（URL 有效性）+ WF3（配置完整性）
    - mechanism 倾向 → WF5（时间维度分析）+ WF8（任务完整性）
```

## WF3：策略配置核查

目标：从 `g_strategy.workflow_def` 提取模型配置，判断失败是否与配置有关。

```
第 1 步：获取失败记录关联的 strategy_id
  从 workflow_record_log 关联 g_workflow_instance，拿到 strategy_id
  SQL 模板见 references/sql-templates.md → "获取 strategy_id"

第 2 步：查询 g_strategy 的 workflow_def 配置
  从 workflow_def JSON 提取 innerNodes 数组中各节点的 modelType、imageSize、outputRatio 等
  SQL 模板见 references/sql-templates.md → "策略配置提取"

第 3 步：对比正常策略与异常策略
  重点关注：modelType 是否为有效模型名 / imageSize / outputRatio 是否合理 / 缺失的必填字段

第 4 步：检查 API 路径错误
  errorMsg 中出现 URL 路径异常（如 publishers//models 双斜杠）→ modelType 到 API 路径映射 bug

第 5 步：检查模型是否已下线/废弃
  errorMsg 中出现 "model was deprecated"、"model not found"、"Claude" → 策略引用了已下线模型
  a) 从 workflow_def 提取当前 modelType 值
  b) 确认该模型是否仍在可用模型列表中
  c) 对比同链路其他正常策略的 modelType
  结论模板："策略 {id} 的 {node_name} 节点配置了已下线模型 {modelType}，需更新"

第 6 步：输出归因结论
  attribution_layer: "capability | information"
  判定规则：
    - 模型配置无效/已下线/不存在 → capability（模型能力边界）
    - 必填字段缺失（imageSize/outputRatio 等）→ information（配置信息不完整）
    - API 路径映射错误（双斜杠等）→ capability（代码映射逻辑缺陷）
  recommended_action:
    - capability → 更新模型配置 / 修复 API 路径映射 → 通知后端负责人
    - information → 补充策略必填字段 → 通知配置人员
```

## WF4：输出物验证（可选）

目标：下载 gen_video / gen_img 的输出物，验证其实际属性。

### 4a. 视频分辨率检查

> **优先使用 `f88-ffmpeg` skill**：ffprobe 提供比 OpenCV 更完整的视频参数报告。

```
第 1 步：提取视频 URL
  从 output_json 提取 $.outputVideo
  SQL 模板见 references/sql-templates.md → "视频 URL 提取"

第 2 步：下载视频
  curl -sL -o /tmp/vid_{record_id}.mp4 "{video_url}"

第 3 步：用 OpenCV 读取分辨率（轻量兜底方案）
  python3 + cv2.VideoCapture 读取 w/h，计算比例
  如果 opencv-python-headless 未安装：pip3 install opencv-python-headless -q
```

完整校验（含编码、帧率、时长、文件完整性）请参考 `f88-ffmpeg` 能力一。

### 4b. 图片可访问性验证

```
第 1 步：提取图片 URL（从 output_json 提取相关图片字段）
第 2 步：检查 HTTP 状态码
  curl -sL -o /dev/null -w "%{http_code}" "{image_url}"
  200=可访问 / 404=不存在 / 403=权限问题

第 3 步（4b 末尾）：输出归因结论
  attribution_layer: "information | capability"
  判定规则：
    - 输出物 URL 不可访问（403/404）→ information（数据源失效/URL 过期）
    - 输出物分辨率/格式不符合策略配置 → capability（模型产出质量不达标）
    - 输出物正常但下游仍失败 → mechanism（流转环节问题，非输出物本身）
  recommended_action:
    - information → WF7（URL 过期排查）确认是否全局性问题
    - capability → WF3（核查策略配置中的模型/参数是否合理）
```

## WF5：时间与策略维度分析

目标：判断失败是全局性问题还是特定策略/时间段的问题。

```
第 1 步：按策略分组统计失败数
  SQL 模板见 references/sql-templates.md → "策略维度分析"
  各策略失败数均匀 → 全局性问题；集中在某策略 → 该策略配置或数据问题

第 2 步：查询失败时间范围
  SQL 模板见 references/sql-templates.md → "时间维度分析"
  集中在短时间段 → 服务瞬时故障；持续分布 → 持续性配置或服务问题

第 3 步：综合判断并输出结论
  交叉验证：错误类型 × 策略分布 × 时间分布

第 4 步：输出归因提示（诊断型，缩小归因范围）
  attribution_layer: "diagnostic"（本 WF 为维度分析，辅助其他 WF 定位根因层）
  attribution_hint: 根据交叉分析结果预判——
    - 失败集中在特定策略 + 特定时间段 → 倾向 information（该策略配置变更）
    - 失败均匀分布 across 策略 + 集中在短时间段 → 倾向 mechanism（全局服务故障）
    - 失败持续分布 across 时间 + 集中在某策略 → 倾向 capability（该策略模型能力边界）
  recommended_action: 根据交叉结论路由到 WF3/WF6/WF7 深入排查
```

## WF6：阶段衔接失败排查

目标：当用户问"为什么没有进入 XX 阶段"时，定位阶段间流转失败的根因。

```
第 1 步：确认批次已执行的阶段
  SQL 模板见 references/sql-templates.md → "批次实际执行策略"

第 2 步：读取链路配置，获取完整阶段列表
  浏览器打开 https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/linkDetail?id={link_id}
  浏览器不可用则 DMS SQL：references/sql-templates.md → "策略存在性检查"

第 3 步：对比配置 vs 实际执行
  构建对比表，找出"配置了但未触发"的阶段

第 4 步：检查出参完整性
  SQL 模板见 references/sql-templates.md → "出参完整性检查"
  重点：approve 节点的 passedImg 是否为 [null, null] / 字段名不匹配

第 5 步：综合判断
  常见根因：
  a) 批次未配置该阶段 → 需添加对应策略
  b) 出参丢失（如 passedImg=null）→ 平台参数映射 bug
  c) 前阶段未全部完成 → 检查 FAIL/HANDLING 阻塞
  d) 延迟触发 → 检查 strategy 节点状态更新时间

第 6 步：输出归因结论
  attribution_layer: "mechanism | information"
  判定规则：
    - 阶段配置了但未触发（出参丢失/字段名不匹配）→ mechanism（流转机制缺陷）
    - 批次未配置该阶段 → information（配置信息缺失）
    - 前阶段 FAIL/HANDLING 阻塞下游 → mechanism（缺少容错/补偿机制）
  recommended_action:
    - mechanism → 检查流转代码逻辑，增加出参校验/补偿重试 → 通知后端
    - information → 补充链路阶段配置 → 通知配置人员
```

## WF7：数据源有效性与 URL 过期排查

目标：当失败原因指向图片/素材 URL 不可访问时，系统性排查数据源有效性。

```
第 1 步：提取失败记录中的 URL
  常见字段：$.mainImgUrl / $.imageUrl / $.outputVideo / $.passedImg
  SQL 模板见 references/sql-templates.md → "URL 提取"

第 2 步：批量检测 URL 可访问性
  curl 并发检测 HTTP 状态码
  403=CDN签名URL过期 / 404=资源不存在 / 000=CDN节点不可达

第 3 步：判断 URL 过期模式
  大量 403 + SignatureDoesNotMatch → CDN 签名 URL 过期
  大量 404 → 原始资源已被删除或迁移

第 4 步：检查数据源时间戳
  SQL 模板见 references/sql-templates.md → "数据源时间对比"

第 5 步：综合判断
  a) CDN 签名 URL 过期 → 建议改用永久 URL 或增加 URL 刷新机制
  b) 商品图片被卖家更换 → 建议入队前增加 URL 有效性预检
  c) CDN 域名切换 → 检查是否全域受影响

第 6 步：输出归因结论
  attribution_layer: "information"
  判定规则：
    - CDN 签名 URL 过期（403 SignatureDoesNotMatch）→ information（数据源时效性失效）
    - 原始资源被删除/迁移（404）→ information（数据源已不存在）
    - CDN 域名切换/节点不可达 → information（基础设施信息变更未同步）
  recommended_action:
    - information → 改用永久 URL 或增加 URL 刷新机制 → 通知后端/运维
    - 若大量 URL 同时过期 → 检查是否存在系统性 URL 生命周期管理缺失
```

## WF8：任务完整性与部分失败影响排查

目标：当用户反馈"部分商品没有进入下游阶段"或"任务丢失"时排查。

```
第 1 步：统计批次各阶段任务数
  SQL 模板见 references/sql-templates.md → "阶段任务数统计"
  下游阶段任务数明显少于上游 → 存在任务丢失

第 2 步：追踪具体丢失的任务
  SQL 模板见 references/sql-templates.md → "任务丢失追踪"

第 3 步：分析上游失败模式
  FAIL → 部分失败导致下游未触发 / SUCCESS 但下游无记录 → 流转逻辑 bug / HANDLING → 任务卡住

第 4 步：检查 JSON 输出完整性
  常见问题：output_json 含未转义 \n → 下游 JSON 解析失败 → 任务静默丢失
  passedImg 为 [null, null] → 出参映射 bug

第 5 步：检查 TPP 回调完整性
  SQL 模板见 references/sql-templates.md → "TPP 回调检查"
  回调数 < 发起数 → TPP 回调丢失

第 6 步：综合判断
  a) 部分失败阻断下游 → 确认是否为预期行为
  b) JSON 格式异常 → 修复 LLM 输出转义
  c) TPP 回调丢失 → 增加超时重试或回调补偿
  d) 出参字段缺失 → 平台参数映射 bug

第 7 步：输出归因结论
  attribution_layer: "mechanism | information"
  判定规则：
    - SUCCESS 但下游无记录（流转逻辑 bug）→ mechanism（流转机制缺陷）
    - JSON 格式异常导致静默丢失 → mechanism（缺少输出校验机制）
    - TPP 回调丢失 → mechanism（缺少超时补偿/重试机制）
    - 出参字段缺失（passedImg=null 等）→ information（出参映射信息不完整）
  recommended_action:
    - mechanism → 增加输出校验 + 超时重试/回调补偿 → 通知后端
    - information → 修复参数映射配置 → 通知后端/配置人员
```

## WF9：配置模式对比排查（BATCH vs STREAM execMode）

目标：当用户反馈"BATCH 和 STREAM 跑出来结果不一样"或"approve 用了旧 URL"时排查。

```
第 1 步：确认批次的 execMode
  SQL 模板见 references/sql-templates.md → "批次 execMode 查询"
  BATCH：ApproveProcessor 从 g_afd_review_job.info 快照读取 URL
  STREAM：ApproveProcessor 实时从 g_afd_material 读取当前 URL

第 2 步：对比 approve 节点使用的 URL 来源
  SQL 模板见 references/sql-templates.md → "BATCH vs STREAM URL 对比"
  两者不一致 → replaceImage 只更新了 g_afd_material.url 但未回写 g_afd_review_job.info

第 3 步：判断是否由 replaceImage 引起
  SQL 模板见 references/sql-templates.md → "material 操作记录查询"

第 4 步：检查 subJobId 传递情况
  SQL 模板见 references/sql-templates.md → "subJobId 传递检查"

第 5 步：综合判断
  a) BATCH + replaceImage 未回写 → ApproveProcessor 使用旧快照 URL（BT_6148）
  b) STREAM 正常但 BATCH 异常 → execMode 配置不一致
  c) subJobId 未传递 → 链路追踪断裂（BT_5976）

第 6 步：输出归因结论
  attribution_layer: "mechanism"
  判定规则：
    - BATCH 模式快照未刷新（replaceImage 未回写 review_job.info）→ mechanism（快照机制缺陷）
    - execMode 配置不一致（同链路不同批次用不同模式）→ mechanism（运行机制配置不统一）
    - subJobId 未传递 → mechanism（链路追踪机制缺失）
  recommended_action:
    - mechanism → 统一 execMode 配置 / 修复快照回写逻辑 / 补全 subJobId 传递 → 通知后端
    - 若 BATCH 为预期模式 → 增加 replaceImage 后自动刷新 review_job.info 快照
```

## WF10：跨表数据一致性验证

目标：验证 g_afd_material vs g_afd_review_job 的数据一致性。

```
第 1 步：提取目标记录的 URL 对比
  SQL 模板见 references/sql-templates.md → "跨表 URL 一致性检查"
  对比：g_afd_material.url vs g_afd_review_job.info → $.videoUrlReview.videoUrl

第 2 步：批量扫描不一致记录
  SQL 模板见 references/sql-templates.md → "批量跨表一致性扫描"

第 3 步：定位不一致的时间窗口
  SQL 模板见 references/sql-templates.md → "不一致时间窗口分析"

第 4 步：检查 5 类素材操作的 subJobId 覆盖情况
  SQL 模板见 references/sql-templates.md → "素材操作 subJobId 覆盖率"

第 5 步：验证修复效果（如已修复）

第 6 步：综合判断
  a) replaceImage 只更新 material 未回写 review_job → 代码 bug
  b) 审核任务创建后素材被更新 → 需增加快照刷新机制或改用 STREAM
  c) subJobId 未传递 → 前端/接口层 bug

第 7 步：输出归因结论
  attribution_layer: "capability | mechanism"
  判定规则：
    - replaceImage 只更新 material 未回写 review_job → capability（代码实现能力不足，未覆盖回写逻辑）
    - 审核任务创建后素材被更新（时序问题）→ mechanism（缺少快照刷新/同步机制）
    - subJobId 未传递 → capability（前端/接口层代码实现遗漏）
  recommended_action:
    - capability → 修复代码实现（补全回写逻辑/subJobId 传递）→ 通知后端/前端
    - mechanism → 增加审核任务创建后的快照刷新机制 → 通知后端
```

## WF11：SharedArrayBuffer/COOP/COEP 跨域隔离环境排查

目标：排查预发环境的跨域隔离配置缺失问题（环境运维问题，不是代码 bug）。关联 Bug：BT_6149。

```
第 1 步：确认错误模式
  SQL 模板见 references/sql-templates.md → "SharedArrayBuffer 错误统计"
  典型 errorMsg：SharedArrayBuffer / Cross-Origin Isolated / COOP / COEP / ffmpeg-wasm 加载失败

第 2 步：检查响应头（curl 快速验证）
  预发 vs 生产对比：
  curl -sI "https://pre-aifashion-xiaoer.alibaba-inc.com/" | grep -iE 'cross-origin|coop|coep'
  必须存在：Cross-Origin-Opener-Policy: same-origin + Cross-Origin-Embedder-Policy: require-corp/credentialless

第 3 步：检查 CDN 资源的 CORP 头
  FFmpeg WASM 二进制文件需要 CDN 返回 Cross-Origin-Resource-Policy: cross-origin

第 4 步：预发 vs 生产 Nginx 配置对比
  常见根因：生产 Nginx 已配置 COOP/COEP 头，但预发 Nginx 遗漏

第 5 步：浏览器 Console 验证

第 6 步：综合判断
  a) 预发 Nginx 未配置 COOP/COEP → 运维配置遗漏
  b) COEP=require-corp 但 CDN 无 CORP → 改为 credentialless
  c) 配置仅在部分路径生效 → 扩大 Nginx 配置作用范围

第 7 步：输出归因结论
  attribution_layer: "mechanism"
  判定规则：
    - 预发 Nginx 未配置 COOP/COEP → mechanism（运维配置机制遗漏，环境部署流程未覆盖）
    - COEP 与 CDN CORP 不兼容 → mechanism（跨域隔离策略配置机制不完善）
    - 配置仅部分路径生效 → mechanism（Nginx 配置作用范围机制缺失）
  recommended_action:
    - mechanism → 补全预发 Nginx COOP/COEP 配置 / 调整 COEP 为 credentialless / 扩大配置作用范围 → 通知运维
    - 建议将 COOP/COEP 配置纳入环境部署标准检查清单，避免后续环境遗漏
```

## WF12：批次轨迹效率分析

目标：评估批次执行效率，发现"鬼打墙"式重试和无效步骤。

```
第 1 步：获取批次执行轨迹
  使用 f88-data-query T-22 SQL 模板，输入 batch_id
  获取每个 node_type 的执行次数、平均耗时、失败次数

第 2 步：计算收敛度分数
  optimal_steps = COUNT(DISTINCT node_type) — 不同节点类型数
  actual_steps = SUM(exec_count) — 总执行次数
  convergence_score = optimal_steps / actual_steps
  判定：
    >= 0.8 → 高效（正常）
    0.6~0.8 → 轻度冗余（记录观察）
    0.4~0.6 → 明显冗余（P1 告警）
    < 0.4 → 严重冗余（P0 告警）

第 3 步：识别重试热点
  找出 exec_count > 1 的节点，按 exec_count DESC 排序
  对每个热点节点：
    a. 检查 fail_count，判断是否"失败→重试→失败"循环
    b. 检查 avg_duration_sec，判断是否存在超时重试
    c. 检查 errorMsg 分布，判断重试原因是否一致

第 4 步：对比历史基线
  查询同类型批次（相同 workflow_def）的历史平均耗时
  对比当前批次各节点耗时是否在正常范围

第 5 步：输出归因结论
  attribution_layer: "capability | information | mechanism"
  判定规则：
    - 模型调用失败导致重试 → capability
    - 配置错误导致无效执行 → information
    - 调度/并发问题导致重复执行 → mechanism
  recommended_action:
    - capability → 优化模型稳定性 / 增加重试间隔
    - information → 修正配置
    - mechanism → 修复调度逻辑 / 增加幂等检查
```

## WF13：Bad Case 回流分析

目标：从失败批次中提取关键证据，自动生成回归测试用例，沉淀为测试资产。

```
第 1 步：提取失败批次完整执行轨迹
  使用 f88-data-query T-21 SQL 模板，输入 batch_id
  获取所有节点的执行记录（按时间排序）

第 2 步：定位失败节点和关键证据
  从轨迹中筛选 status='FAIL' 的记录
  对每条失败记录提取：
    a. node_type（失败节点类型）
    b. errorMsg（失败原因）
    c. input_json（输入参数）
    d. output_json（输出状态）
    e. extra_info（额外信息）

第 3 步：生成回归测试用例 JSON
  对每个失败场景生成测试用例，格式符合 web-automation eval/cases 规范：
  {
    "caseId": "REG-{batch_id}-{node_type}-{seq}",
    "title": "回归：{node_type} {errorMsg摘要}",
    "source": "badcase_pipeline",
    "metadata": {
      "batchId": "{batch_id}",
      "date": "{YYYY-MM-DD}",
      "originalFailNode": "{node_type}",
      "gapType": "data | prompt | engineering"
    },
    "preconditions": [从 input_json 提取的前置条件],
    "steps": [从执行轨迹还原的操作步骤],
    "expectedResult": "修复后该节点应 SUCCESS",
    "verification": {
      "db": "SELECT status FROM workflow_record_log WHERE batch_id='{new_batch_id}' AND node_type='{node_type}'",
      "expectedCondition": "status = 'SUCCESS'"
    }
  }

第 4 步：写入回归用例目录
  输出到 web-automation/eval/cases/f88-test/regression-from-production/
  文件名：{batch_id}_{date}.json

第 5 步：输出回流报告
  回流用例数 / 失败节点数 / 覆盖的 gapType 分布
  建议下次测试时优先执行这些回归用例
```
