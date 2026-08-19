# 已知问题模式

> 链路配置检查中发现的典型问题模式，供排查时快速匹配。

## BT_6629 上传节点失败

- **根因**: 审核出参为单一 `pic_urls`，上传策略期望 `pic_urls_pass1`，参数名不匹配
- **修复**: 审核出参拆分为 pic_urls_pass1~5，上传策略扩展为 5 个独立绑定
- **检查项**: G1/G2/G3

## template_match 全空配置

- **现象**: 20 个 mass_prod template_match 节点 matchScene 和 targetMatchCount 均为空/0
- **影响**: 走默认场景，匹配范围不可控
- **检查项**: B1/B2

## BT_6888 审核节点图片映射缺失

- **根因**: approve 节点完全缺少 `imgUrlReview` 字段配置，审核平台收到空输入 → `rspCode=99999, toastMsg=图片素材错误`
- **关键特征**: approve 是策略首节点（无上游 gen_img），需要从 `WORKFLOW_INPUT_PARAM` 取图，但配置中完全没有 `imgUrlReview`
- **修复**: 补上 `imgUrlReview` → `WORKFLOW_INPUT_PARAM` → `template_new_url`，并补 `approveType`
- **检查项**: D5/D6/D7

## 生图模型停用导致全量失败

- **根因**: modelType 对应的模型被提供方停用，所有生图任务提交即失败
- **现象**: 批次生图环节 100% 失败，errorMsg 含"模型不可用"/"model not found"
- **修复**: 更换为可用模型
- **检查项**: I1

## 视频生成 429 平台限流

- **根因**: Seedance 视频生成平台并发上限 200，多链路共享配额
- **现象**: errorMsg 含"PL-002"/"当前已提交进行中的video generation任务已达到200个"
- **修复**: 降低并发 + 增加 429 自动重试 + 错峰提交
- **检查项**: J1

## 模板匹配 REQUEST_TOO_LARGE

- **根因**: 模板包内模板数量过多，序列化后 body 超过算法接口 1MB 限制
- **现象**: errorMsg 含"bodySize exceeds threshold:1048576"
- **修复**: 拆分模板包 / 减少单包模板数量
- **检查项**: J2

## 重试后下游不流转

- **根因**: 上游节点重试成功后，下游节点的触发消息未被重新发送
- **现象**: 倒数第二环节重试后，最后环节始终差几条
- **修复**: 修复 sendSuccessMessage 中的异常处理 + 确保 outputData 完整
- **检查项**: K1/K3

## LLM 节点 JSON 输出含原始换行导致解析失败

- **根因**: `llm_text` 节点 `outputText.type = "JSON"`，但 prompt 中未约束输出格式，模型输出原始 `\n`
- **现象**: task_result 中 text 字段包含多行中文指令，下游 JSON 解析报 `syntax error`
- **修复**: prompt 末尾追加"输出必须是严格合法的单行 JSON，禁止原始换行"
- **检查项**: H2/H3

## FASTJSON offset 错误（BT_7417）

- **根因**: LLM 文本生成节点偶发输出不规范 JSON——非法转义字符、响应截断
- **现象**: errorMsg 匹配 `FASTJSON.*error, offset \d+, char`
- **处置**: 单条 → 自愈重试；批量 → 告警并核查模型版本与 prompt 变更
- **检查项**: H2/H3/H4

## 审核节点类型变更后链路配置未同步

- **根因**: 审核节点自身 qt 类型被修改（如套图 qt=2 → 首图 qt=1），但引用该节点的链路/策略中 approveType 和 approveNodeId 未同步更新
- **现象**: 批次在审核环节集中失败，errorMsg 为 `CommonRspCode(rspType=1, rspCode=99999, toastMsg=图片素材错误)`，非标注审核不通过
- **影响**: ApproveProcessor 按旧类型（如套图）分支构建审核内容，取不到有效图片字段，storeMaterialsAndUpdateIds 收集图片为空/异常，catch 后统一抛"图片素材错误"
- **排查**: 对比策略 approveType 与审核节点实际 qt 类型；查 workflow_record_log.extra_info.errorMsg
- **修复**: 同步更新链路配置：approveType 与节点 qt 对齐，approveNodeId 指向正确节点
- **检查项**: D5/D6/D7（审核节点配置一致性）
- **案例**: 2026-08 种草批次，175 条首图审核失败，根因为节点从套图改首图后链路未同步

## 首图多选多策略新增 item_id 但审批环节未同步

- **根因**: 首图多选多策略新增 `item_id` 为必填参数，但种草链路的审批环节未同步增加引用
- **现象**: 批次在审核环节卡住，需人工逐批处理
- **修复**: 在审批环节的 inputParams 中补充 item_id 引用
- **检查项**: L1/L5
