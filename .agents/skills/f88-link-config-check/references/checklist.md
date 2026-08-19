# F88 链路配置检查清单（A-M 61 项）

## A. 阶段编排检查（6 项）

### A1. 阶段数量合理性
- 期望：stages 数量 >= 2
- 异常：单阶段链路（stage_count == 1）可能是未完成配置或特殊用途
- 操作：标记告警，列出单阶段链路的 id/name 供人工确认

### A2. 阶段 UID 唯一性
- 期望：所有 stage.id 在链路内无重复
- 异常：UID 重复会导致参数流转引用错乱
- 操作：遍历 stages 数组，检查 id 集合是否有重复

### A3. 阶段顺序合理性
- 期望：生图类阶段（gen_img/DESIGN）在审核（approve/VIEW）前，审核在上传（INFO_SUP/SET）前
- 典型正确模式：刷标签 → 首图生图 → 首图审核 → 套图生图 → 套图审核 → 上传
- 操作：检查阶段类型序列是否符合业务逻辑

### A4. 阶段类型覆盖
- 期望：包含 VIEW/DESIGN/SET/INFO_SUP 等关键类型
- 参考分布（56 条 prod 链路）：VIEW 70%, DESIGN 16%, SET 7%
- 操作：统计各 type 占比，缺少关键类型时标记

### A5. 单阶段链路审查
- 期望：无单阶段链路，或单阶段链路有明确业务说明
- 操作：stage_count == 1 时标记告警并列出详情

### A6. 生命周期状态
- 期望：prod 环境不应存在大量 test 链路
- 参考分布：mass_prod 9, test 29, gray 1（2026-07-18 数据）
- 操作：prod + test 组合标记告警，建议清理或迁移 staging
- **v3.2.2 新增状态**：`suspend`（挂起，LifeCycleEnum.SUSPEND，来源 features/15-strategy-platform-v3.2.2.md，分支 feature/20260812_30719664_v3.2_sp_1）。发布后 life_cycle 出现 suspend 属合法值，不要误判为异常；但挂起链路若仍关联活跃批次（g_workflow_batch.relation_id 指向该链路且 status=PROCESSING）应标记告警。按 life_cycle 过滤的 SQL 模板（见 sql-templates.md）需将 suspend 纳入合法枚举。

---

## B. 模板匹配（template_match）检查（5 项）

### B1. matchScene 配置 `[mass_prod]`
- 期望：matchScene 有明确值（"通用"/"COMMON"/"MODEL"）
- 异常：空字符串 = 走默认场景，匹配范围可能过大
- 生产现状（20 节点）：全部为空 — 已知风险
- 操作：列出所有 matchScene 为空的策略 id/name

### B2. targetMatchCount 配置 `[mass_prod]`
- 期望：targetMatchCount > 0
- 异常：0 可能导致匹配行为不符合预期
- 生产现状（20 节点）：全部为 0 — 已知风险
- 操作：列出所有 targetMatchCount = 0 的策略 id/name

### B3. mustMatchFields 严格度
- 期望：非空数组（至少包含 seller_id 去重）
- 异常：空数组 = 不做字段级去重，同商家模板可能重复使用
- 操作：列出 mustMatchFields = [] 的策略

### B4. templateMaxUseCount 限制
- 期望：根据业务需求在 1~10 范围
- 操作：列出各策略的配置值，标记极端值

### B5. templatePkgCondition 绑定
- 期望：有绑定条件（如 F88_MAIN_IMAGE/VIEW）或确认走默认模板包
- 操作：列出 templatePkgCondition 为空的策略，确认是否预期

---

## C. 生图节点（gen_img）检查（4 项）

### C1. modelType 配置
- 期望：非空，属于已知模型列表
- 已知模型：gemini-3.1-flash-image-preview, gpt-image-2-0421-global, gemini-2.5-flash-06-17, gemini-2.5-flash-image, gemini-3-pro-image-preview
- 操作：列出不在已知列表中的 modelType

### C2. imageSize / outputRatio
- 期望：与下游审核/上传要求一致
- 常见配置：2K / 3:4
- 操作：列出各策略配置，标记与链路其他阶段不匹配的情况

### C3. outputModel（单图/多图）
- 期望：single/multi 与下游审核策略匹配
- 操作：multi 输出时确认下游审核 approveType 能处理多图

### C4. 输入字段命名一致性
- 期望：统一使用 seed_image_url
- 异常：redesign_style_url 与 seed_image_url 并存
- 操作：列出使用非标准命名的策略

---

## D. 审核节点（approve）检查（8 项）

### D1. approveType 配置
- 期望：1（单选）/ 2（多选/二选一）/ 4（三路多选）之一
- 操作：列出非标准 approveType 值

### D2. passedImg 输出字段
- 期望：字段存在且可被下游引用
- 风险：审核全部驳回时 passedImg=[]，导致下游上传节点 FAIL（BT_6629 案例）
- 操作：确认 passedImg 字段存在，建议增加空值容错

### D3. imgUrlReviewList 完整性
- 期望：审核输入图片列表来自上游 gen_img 输出
- 操作：检查 imgUrlReviewList 的数据源引用是否正确

### D4. 审核不通过原因字段命名
- 期望：统一命名（如 notpassreason）
- 已知变体：notpassreason / notpassreason1 / notpassreason2
- 操作：列出使用非标准命名的策略

### D5. imgUrlReview 字段存在性
- 期望：approve 节点必须配置 `imgUrlReview` 字段（或 `imgUrlReviewList`）
- 异常：缺失 → 审核平台返回"图片素材错误"（BT_6888 案例）
- 操作：检查每个 approve 节点的 innerNode 配置，确认 imgUrlReview 字段存在

### D6. 图片来源映射有效性
- 期望：`imgUrlReview.dataSourceConfig` 必须指向有效数据源
- 有上游节点时：dataSourceType = `PARENT_NODE` + 有效 nodeId/fieldCode
- 无上游（首节点）时：dataSourceType = `WORKFLOW_INPUT_PARAM` + workflowInputParamCode 必须存在于策略 inputParams 中
- 操作：验证 dataSourceConfig 引用链完整性

### D7. 首节点 approve 图片必填
- 期望：当 approve 是策略的第一个 innerNode（parentNodeUids 为空或 []）时，imgUrlReview 的 dataSourceType 必须为 `WORKFLOW_INPUT_PARAM`，且对应的 workflowInputParamCode（如 template_url/template_new_url/seed_image_url）必须在策略 inputParams 列表中存在
- 异常：首节点无上游输出可引用，若未配置 WORKFLOW_INPUT_PARAM 取图 → 审核输入为空
- 操作：识别首节点 approve，检查其图片数据源配置

### D8. approve 数据源与 execMode 一致性
- 期望：approve 节点读取的 URL 来源与批次 execMode 匹配
  - execMode=BATCH → 读 `g_afd_review_job.info` 快照 URL（创建审核任务时固化）
  - execMode=STREAM → 读 `g_afd_material.url` 实时值
- 异常：链路中存在 replaceImage 等只更新 `g_afd_material.url` 但不回写 `g_afd_review_job.info` 的操作时，BATCH 模式会输出旧图（过期快照，BT_6148）
- **BATCH 模式 + replaceImage 节点 = ❌ 严重告警**
- 操作：查询 `g_workflow_batch.exec_mode`，结合链路中是否有 replaceImage 类操作判断风险；建议切换 STREAM 模式或确认回写逻辑已修复
- 关联：f88-failure-analysis 工作流 9/10、f88-approve-verify-sql Step 5

---

## E. 参数流转与命名规范（5 项）

### E1. 跨阶段引用完整性
- 期望：STAGE_OUTPUT 类型参数引用的 stageUid 和 fieldCode 必须存在
- 操作：遍历所有 inputParams，检查 dataSourceType=STAGE_OUTPUT 的引用是否有效

### E2. 输出参数编号风格
- 期望：统一编号风格（如下划线分隔 main_img_url_1）
- 已知变体：main_img_url / main_img_url_1 / main_img_url1（3 种风格并存）
- 操作：列出编号风格不一致的参数

### E3. 高频参数命名变体
- 期望：同类参数命名一致
- 已知变体：template_image_url / template_image_url_1 / template_image_url1
- 操作：列出命名变体

### E4. 通用输入参数覆盖率
- 期望：seller_id / tao_cate / item_id 覆盖所有链路
- 操作：统计覆盖率，标记缺失的通用参数

### E5. 种子图字段命名
- 期望：统一为 seed_image_url
- 已知：seed_image_url（25 次）vs redesign_style_url（14 次）
- 操作：列出使用 redesign_style_url 的策略，建议新链路统一

---

## F. 环境与运维检查（5 项）

### F1. 生产环境 test 链路清理
- 期望：prod 环境不应有 test 链路
- 操作：列出 env=prod AND life_cycle=test 的链路

### F2. mass_prod 链路活跃度
- 期望：mass_prod 链路有实际跑批记录
- 操作：查 g_workflow_batch 最近批次，标记长期无跑批的链路

### F3. 策略一致性
- 期望：同链路内策略配置风格一致
- 操作：检查 strategy_consistency 字段

### F4. 修改人追溯
- 期望：submitter_name 字段非空
- 操作：列出 submitter_name 为空的链路

### F5. COOP/COEP 响应头检查
- 期望：预发环境域名响应头包含 `Cross-Origin-Opener-Policy: same-origin` 和 `Cross-Origin-Embedder-Policy: require-corp`（或 `credentialless`）
- 异常：缺少任一头部 → 依赖 SharedArrayBuffer 的功能（WASM 视频处理、多线程图像计算）在预发失败，而生产可能正常（Nginx 配置不一致，BT_6149）
- 操作：`curl -I https://{pre-prod-domain}` 检查响应头；生产/预发对比
- 关联：f88-failure-analysis 工作流 11、f88-ffmpeg Step 5

---

## G. 多套上传出参拆分检查（4 项）

### G1. 审核阶段出参是否按套拆分 `[mass_prod]`
- 期望：多套上传时，审核输出为 pic_urls_pass1~N（非单一 pic_urls）
- 操作：检查含上传阶段的链路，审核输出参数是否已拆分

### G2. 上传策略与审核出参的一一映射
- 期望：N 套审核出参 = N 个上传策略，每个 imageList 绑定对应 pic_urls_passN
- 操作：检查上传策略数量与审核出参数量是否匹配

### G3. inputParams code 与链路 Stage input 对齐
- 期望：策略 workflowInputParamCode 与 Stage inputParams code 完全一致
- 风险：BT_6629 根因 — 策略期望 pic_urls，链路传入 pic_urls_pass1
- 操作：对比策略 inputParams 和 Stage inputParams，标记不匹配

### G4. 其他含上传阶段的链路排查
- 期望：所有含 image_text_upload 的链路均遵循 N→N 模式
- 操作：扫描所有含上传节点的链路，确认无单出参+单上传策略的旧模式

---

## H. LLM 文本节点检查（5 项）

### H1. outputText.type=JSON 时 outputFields 非空
- 期望：当 `llm_text` 节点的 `outputText.type` 为 "JSON" 时，`outputFields` 数组必须非空
- 异常：空 outputFields → JSON 解析无意义，下游取不到拆分字段
- 操作：检查所有 llm_text 节点，outputText.type=JSON 时确认 outputFields 非空

### H2. JSON 输出时 prompt 含格式约束
- 期望：`outputText.type = "JSON"` 时，systemPrompt 或 userPrompt 中包含 JSON 格式要求关键词
- 关键词列表：JSON、单行、合法、转义、不得包含换行
- 异常：缺失约束 → 模型可能输出含原始 `\n` 的非法 JSON，`parseObject` 失败
- 操作：检查 prompt 文本是否包含格式约束关键词

### H3. prompt 禁止原始换行声明
- 期望：JSON 输出模式下 prompt 应明确禁止原始换行符
- 关键词：换行、\\n、单行、one line
- 操作：检查 prompt 是否包含换行禁止声明

### H4. modelType 有效性
- 期望：llm_text 节点的 modelType 不为空，且为已知模型标识
- 已知模型：qwen-max、qwen-plus、gpt-4o 等
- 操作：列出不在已知列表中的 modelType

### H5. userPrompt 变量引用有效性
- 期望：`{{variable}}` 引用的变量在上游节点输出或策略 inputParams 中存在
- 异常：引用不存在的变量 → 运行时替换为空字符串
- 操作：提取所有 `{{...}}` 变量，对比上游输出和 inputParams

---

## I. 模型可用性检查（4 项）

### I1. modelType 非已停用模型
- 期望：gen_img/gen_video 节点的 modelType 不得为已知停用模型
- 已知停用：gemini-pro-vision、gemini-1.0-pro 等已下线模型
- 异常：命中 → 线上全量失败
- 操作：比对已知停用模型列表

### I2. 单模型依赖风险
- 期望：生图/生视频节点有 fallback 方案
- 异常：仅单一 modelType 且无 fallback → 模型方故障 = 全链路瘫痪
- 操作：标记仅配置单一模型的链路

### I3. 模型与任务类型匹配
- 期望：gen_video 不使用图片模型，gen_img 不使用视频模型
- 已知：Seedance 只能用于 gen_video
- 操作：检查模型类型与节点类型是否匹配

### I4. 活跃策略模型白名单校验
- 期望：所有 ACTIVE 策略引用的模型在当前可用白名单内
- 异常：命中 = ❌ 严重（真实案例 BT_20260801_003：claude-sonnet-4-6 下线后策略未同步，生图全量失败 32 条）
- 操作：`SELECT id, strategy_name, model FROM g_strategy_config WHERE status = 'ACTIVE' AND model NOT IN ({可用模型列表})`
- 注意：白名单随模型上下线变化，执行前先通过 f88-pipeline-monitor 模型可用性巡检获取当前实际可用模型列表，不要硬编码历史清单

---

## J. 容量与限流检查（4 项）

### J1. gen_video 并发配置
- 期望：视频生成节点并发数 ≤ 50
- 异常：未配置或 > 100 → Seedance 平台上限 200 并发，多链路共享
- 操作：列出并发配置值，标记异常

### J2. 模板包体积预估
- 期望：模板包模板数量 ≤ 500，预估 body ≤ 800KB
- 异常：超限 → 算法接口 body 上限 1MB，报 REQUEST_TOO_LARGE
- 操作：查询模板包大小，标记超限风险

### J3. 前置数据准备完整性
- 期望：本地导入类链路（source_type=LOCAL_IMPORT）有对应前置节点
- 操作：检查构图标/洗图/刷标签等前置步骤是否有对应节点或人工确认标记

### J4. 批次优先级与模型队列负载匹配
- 期望：批次 priority 与所用模型队列实时负载匹配（priority 数值越小优先级越高）
- 异常：模型队列积压（running > 1000）而批次 priority 处于最低档（如 15）→ ⚠️ 告警，任务被无限期排后，出现"创建数小时零产出"（真实案例 BT_7495：1548 条任务卡 LLM 文本节点 4 小时，gemini-3.5-flash 全局积压 2448 条，批次 priority=15 为队列最低）
- 操作：大促/高并发场景建批次前核对模型队列负载，必要时调高 priority

---

## K. 阶段流转与容错检查（3 项）

### K1. 节点间流转依赖完整性
- 期望：下游节点 inputParams 引用的上游 outputParams 存在且类型匹配
- 异常：引用断裂 → 重试后无法流转（常见根因）
- 操作：遍历节点间引用关系，验证存在性

### K2. 单张失败容错配置
- 期望：多套图场景（outputModel=multi）配置"单张失败不终止整批"策略
- 异常：未配置 → 1 张失败整批消失（33→32）
- 操作：检查多套图链路的容错配置

### K3. 重试后下游触发机制
- 期望：approve 重试后 sendSuccessMessage 被重新调用
- 已知：questionType=4 不支持回调
- 操作：检查重试配置与下游触发逻辑

---

## L. 逆向操作与生命周期联动检查（5 项）

### L1. 参数双向引用完整性 `[脚本自动化]`
- 期望：参数引用的双向一致性
- **正向检查**（确定性判断）：任意节点通过 WORKFLOW_INPUT_PARAM 引用某参数时，该参数必须存在于策略 inputParams 中（缺失 = ❌ 严重）
- **反向检查**（三层递进判断，按优先级依次执行，命中即停）：
  - **第一层——节点类型固有需求**（硬规则，无需基线）：approve 节点必须能拿到 item_id/seller_id/tao_cate，image_text_upload 节点必须能拿到 item_id/seller_id（缺失 = ❌ 严重）
  - **第二层——节点内部配置声明**：节点 inputParams 中 dataSourceType=WORKFLOW_INPUT_PARAM 的引用，若 workflowInputParamCode 指向的参数在策略 inputParams 中不存在 = ❌ 严重
  - **第三层——同业务链路基线对比**：>50% 同业务链路引用了某参数而当前未引用 = ⚠️ 告警
- 自动化脚本：`scripts/l1-l5-param-check.py`

### L2. 批次撤回/取消联动配置
- 期望：含 approve 节点的链路配置撤回回调（cancelCallback / withdrawHook）
- 异常：无撤回联动 → 批次撤回后审核任务残留，人工清理成本高
- 操作：检查 struct 中是否配置撤回回调

### L3. 审核驳回后重生路径完整性
- 期望：approve 节点配置了 notPassReason 输出时，上游 gen_img/gen_video 配置了驳回重生触发条件
- 异常：有驳回输出但无重生路径 → 驳回后数据死锁
- 操作：检查 rejectRetry / regenerateOnReject 配置

### L4. 多阶段部分失败回滚策略
- 期望：阶段数 >= 3 的链路配置 skipOrRollback 策略
- 异常：未配置 → 部分成功部分失败时状态不一致
- 操作：检查多阶段链路的回滚策略配置

### L5. 跨策略参数流转一致性 `[脚本自动化]`
- 期望：同一链路内多个策略之间的参数传递完整
- **正向**：上游策略 outputParams 声明输出的参数，下游策略通过 STAGE_OUTPUT 引用时必须存在且名称匹配（缺失 = ❌ 严重）
- **反向**：上游策略 inputParams 新增必填参数后，下游消费策略（尤其 approve/image_text_upload）是否同步增加对应引用（缺失 = ❌ 严重）
- 已知案例：首图多选多策略新增 item_id 但审批环节未同步
- 自动化脚本：`scripts/l1-l5-param-check.py`

---

## M. 执行模式（execMode）检查（3 项）

### M1. execMode 字段存在性
- 期望：`g_workflow_batch.exec_mode` 非空且为合法枚举（BATCH / STREAM）
- 异常：字段为空或非法值 = ❌ 严重，批次无法正常调度
- 操作：`SELECT batch_id, exec_mode FROM g_workflow_batch WHERE relation_id = '{link_id}'`

### M2. BATCH 模式 SchedulerX 依赖告警
- 期望：execMode=BATCH 时，预发 SchedulerX 已配置并正常运行
- 异常：预发 SchedulerX 可能未运行或间隔极长 → 批次卡在 COLLOCATION/approve/HANDLING 无限期（参见 BT_6148 关联问题）
- 操作：确认预发 SchedulerX 状态；无法确认时标记 ⚠️ 告警并建议切换 STREAM 模式

### M3. BATCH/STREAM 数据源一致性
- 期望：approve 节点数据源与 execMode 匹配——BATCH 读 `g_afd_review_job.info` 快照，STREAM 读 `g_afd_material.url` 实时值
- 异常：同一链路混用 BATCH 和 STREAM 且 approve 数据源未适配 = ❌ 严重，approve 会读取过期或错误数据
- 操作：结合 D8 检查结果，对混用链路标记严重告警
- 关联：f88-failure-analysis 工作流 9、strategy-platform 工作流 6

---

## 已知问题模式速查

| 模式 | 根因 | 影响 | 关联检查项 |
|------|------|------|------------|
| BT_6629 上传失败 | 审核出参未拆分 + 参数名不匹配 | imageList=[] → 上传 FAIL | G1/G2/G3 |
| template_match 全空 | matchScene/targetMatchCount 未配置 | 匹配范围不可控 | B1/B2 |
| passedImg 空值传播 | 审核全驳回 → passedImg=[] → 下游 FAIL | 上传节点报错 | D2 |
| 参数命名不一致 | 历史迭代遗留多种命名风格 | 参数流转可能断裂 | E2/E3/E5 |
| BT_6148 replaceImage 跨表不一致 | replaceImage 只更新 g_afd_material.url，不回写 review_job.info | BATCH 模式 approve 拿旧 URL | D8/M2/M3 |
| BT_6149 SharedArrayBuffer 报错 | 预发 Nginx 未配置 COOP/COEP 响应头 | ffmpeg-wasm 加载失败，视频编辑器不可用 | F5 |
| BATCH 批次卡死 | 预发 SchedulerX 未运行 | 批次无限期卡在 HANDLING | M2 |
| BT_20260801_003 模型下线 | claude-sonnet-4-6 下线后策略未同步 | 生图全量失败 | I1/I4 |
