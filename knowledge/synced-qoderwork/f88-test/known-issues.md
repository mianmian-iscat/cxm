<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/patterns/known-issues.md -->
<!-- synced-at: 2026-07-22T15:00:02.875281 -->
<!-- skill: F88测试知识库 -->

---
id: patterns/known-issues
title: F88 审核平台已知问题
owner: 目民
version: 1.1.0
created: 2026-06-29
updated: 2026-07-02
tags: [审核平台, known-issues, bug, 图片编辑, 数据流转, 局部修改回传, hasFeedback]
trigger_examples:
  - "审核图片下载/替换/局部修改异常"
  - "accuracyRate 显示 0%"
  - "inspection API 参数名错误"
source_sessions: []
promotion_count: 0
---

# 已知问题库

## 系统级已知问题

### 1. 局部修改下载问题
- **现象**：局部修改/替换后点下载，下载的是修改前原图
- **影响**：审核功能中的图片编辑
- **状态**：已知系统问题
- **临时方案**：提醒用户此为已知问题

### 2. ~~块式单图审核替换问题~~（已随单图审核下线废弃）

### 3. accuracyRate 恒为 0.00%
- **现象**：抽检正确率始终显示为 0.00%
- **根因**：
  - `consistency` 字段（isReReviewed）后端始终未填充（null）
  - 仅 `auditOption=1/2` 触发 `checkInspectionTaskConsistency`
  - `auditOption=3`（重新审核）不触发且会清除该字段
  - `accuracyRate` 计算依赖此字段
- **影响**：抽检结果统计不准确
- **临时方案**：关注 questionType=3 的不通过原因列表

### 4. inspection/list API 参数名
- **现象**：使用 `taskId` 参数查询无结果
- **正确用法**：参数名为 `mainTaskId`（非 `taskId`）
- **影响**：API调用时参数使用错误

### 5. 导航导致表单重置
- **现象**：AOne质量报告填写中，导航离开页面再返回，表单全部重置
- **影响**：测试报告生成流程
- **临时方案**：必须在同一页面完成所有填写，中途不离开

### 6. 图片编辑操作后toolbar需「编辑后+✅确认」才可见（预期行为）
- **现象**：局部修改、替换、高清化等图片编辑操作完成后，底部工具栏（copyURL、下载、替换、裁剪、高清化、负反馈、复位等按钮）不可见或不可用
- **正确流程**：编辑操作完成 → 点击「编辑后」tab切换视图 → 点击 ✅ 确认按钮 → 底部工具栏才出现
- **适用范围**：所有图片编辑操作——局部修改（布局修改）、替换、高清化，均需要确认后才能使用工具栏
- **性质**：**预期行为，非 bug**。编辑期间 toolbar 隐藏/禁用是防止用户在修改过程中操作图片的设计机制
- **根因（局部修改场景）**：
  - 前端 `shouldShowTab` 在 `localAdjustStatus` 非空（INIT/SUCCESS/FAILED）时为 `true`
  - toolbar 渲染条件为 `!shouldShowTab`，因此编辑期间 toolbar 不渲染
  - checkbox disabled 条件包含 `shouldShowTab`，因此编辑期间 checkbox 禁用
  - 用户确认后 `localAdjustStatus` 清零，`shouldShowTab = false`，toolbar 恢复
- **前端copyURL逻辑**：`handleCopyUrl(img.originUrl || img.url)`，`originUrl`优先
  - 局部修改成功后，后端仅更新`localAdjustUrl`，**不更新**`originUrl`和`url`
  - 确认后后端将`localAdjustUrl`写入`material entity.url`，`url`字段更新为修改后URL
  - 确认后`localAdjustStatus`从3(REPAIR_SUCCESS)重置为0
- **API数据变化（局部修改场景）**：
  - 确认前：`url=原始URL`，`localAdjustUrl=修改后URL`，`localAdjustStatus=3`，copyURL返回原始URL（预期行为）
  - 确认后：`url=修改后URL`，`localAdjustStatus=0`，copyURL返回修改后URL
- **三种组件行为一致**：
  - **CoverImageReview (qt=4/首图审核)**：`shouldShowTab = inLocalAdjustMode || inRegenerateMode || (showSharpen?.showTab || false)` → toolbar 隐藏 + checkbox 禁用 → 确认后恢复
  - **SetImageReview (qt=2/套图审核)**：`shouldShowTab = inLocalAdjustMode || (showSharpen?.showTab || false)` → toolbar 隐藏 + checkbox 禁用 → 确认后恢复
- **易踩坑点**：测试时如果跳过"编辑后+✅确认"步骤，会误判为BUG；实际上这是设计行为——未确认的修改不算生效，工具栏不会出现
- **2026-06-19 代码分析复测结论**：
  - 三个历史 BLOCKED 问题（qt=4 toolbar禁用、qt=1 toolbar消失、qt=2 copyURL返回旧URL）经代码分析确认均为**预期行为**
  - toolbar 隐藏/禁用是 `shouldShowTab` 机制的正常表现，确认后自动恢复
  - copyURL 在确认前返回原始 URL 是因为 `originUrl` 和 `url` 均未更新，确认后才更新
  - 之前的测试报告误判为 bug，已纠正
- **状态**：预期行为 ✅（2026-06-19 确认）

## 数据流转已知问题

### 7. 审核局部修改回传 passedImg 取 originUrl（已修复 — BT_5976 验证）
- **现象**：审核员在首图审核中使用"局部修改"功能后确认通过，approve 节点 output_json.passedImg 返回 originUrl（修改前图片），而非 localAdjustUrl（修改后图片）
- **根因**：approve 回调逻辑从 `selectedImgUrls[].originUrl` 取值，忽略了 `localAdjustUrl` 字段
- **影响链路**：首图审核 → strategy(main_img_url_1) → 套图审核(imrUrlReference1) → 套图生成 —— 全链路使用修改前的图
- **复现**：BT_5967，approve record id=5771288，审核任务 1223595
  - originUrl: `afd_image_1782910571755_32779298.jpg`
  - localAdjustUrl: `afd_image_1782959037358.jpg`
  - 实际 passedImg = originUrl（错误）
- **修复验证**：BT_5976 确认修复，passedImg = `localUpload/d28db499c3c948a8b1bb935bd1325d6e.png`（修改后图）
- **回归用例**：test_approve_regression.py J1-J6, K1-K2, M1-M3（共 11 条）
- **状态**：已修复 ✅（2026-07-01 确认）

### 8. hasFeedback=true 图片出现在 passedImg（脏数据 — 非代码 Bug）
- **现象**：套图审核中 selectedImgUrls 某张图片 hasFeedback=true 且有 notPassReasonList=["模特未改变"]，但该图仍出现在 approve output.passedImg 中
- **性质**：**脏数据（测试数据问题）**，非代码缺陷。BT_5976 测试数据构造时 hasFeedback 标记不规范，不代表线上真实场景
- **发现**：BT_5976 套图审核 AFD_RT15993914
- **状态**：脏数据，已确认非 Bug ✅（2026-07-02 用户确认）
- **回归用例**：test_approve_regression.py O1-O2（已调整为脏数据校验，非 Bug 断言）

### 9. 审核回传延迟（38-52 分钟）
- **现象**：approve 节点提交审核后等待 38-52 分钟才收到回调，期间 60 个 approve 节点全部卡在 HANDLING
- **根因**：审核平台侧处理延迟，非工作流调度器问题
- **影响**：批次整体进度被阻塞，下游节点等待
- **复现**：BT_5853，2026-06-28 20:00 提交，20:38-20:52 陆续回传
- **最终结果**：全部 SUCCESS（延迟回传，非永久失败）
- **回归用例**：test_approve_regression.py N4
- **状态**：已知问题，已自愈 ✅

### 10. gen_video 节点卡死 12h+
- **现象**：gen_video 节点提交视频生成任务后卡在 HANDLING 状态超过 12 小时
- **根因**：视频生成服务丢失了任务（可能是消息队列消费失败或超时未回调）
- **影响**：2 条 gen_video 记录从 2026-06-28 23:27 卡到 2026-06-30 11:00+
- **复现**：BT_5853
- **临时方案**：手动重试（workflow_fail_retry）
- **回归用例**：test_approve_regression.py L3
- **状态**：需手动重试 ⚠️

### 11. Azure OpenAI 安全过滤误拦截时尚产品提示词（套图生图）
- **现象**：套图生图（map_gen_img）某张图 FAIL，节点级 errorMsg="存在生成失败的图片，节点执行失败"，但看不到具体原因
- **根因**：提示词描述蕾丝面料/领口细节/前胸蝴蝶结绑带等服装微距摄影指令，被 Azure OpenAI content moderation 的 `sexual` 分类器误判
- **原始错误**：`{"error":{"message":"Your request was rejected by the safety system...safety_violations=[sexual]","type":"image_generation_user_error","code":"moderation_blocked"}}`
- **错误传播链**：GPT-Image API → HTTP 400 → MPE-001（模型提供方错误）→ 图片生成失败 → prod_record.error_message（有原始错误）→ workflow_record_log.extra_info.errorMsg（仅汇总"存在生成失败的图片"）→ 节点 FAIL
- **影响**：单张图被拦截导致整个 Map 生图节点 FAIL，进而套图策略节点级联 FAIL
- **复现**：BT_6033，2026-07-03
- **Request ID**：8447450f-2736-4789-8481-98e465772751（可向 Azure 提 support ticket 申诉）
- **排查要点**：节点级 extra_info 仅有汇总信息，必须下沉到 `prod_record` 表查 `error_message` 或查子节点的 `output_json` 才能看到具体原因
- **性质**：模型提供方 false positive，非代码 Bug
- **状态**：已知 false positive ⚠️

## 环境问题

### 1. ncs 后台更新失败
- **现象**：a1 CLI 后台自动更新 ncs 在沙箱环境失败（dial tcp bad file descriptor）
- **根因**：沙箱网络限制
- **解决方案**：使用 `ncs upgrade` 命令独立更新，走不同下载通道

### 2. ODPS ORDER BY 限制
- **现象**：SQL 查询报 ODPS-0130071 错误
- **根因**：ORDER BY 未带 LIMIT
- **解决方案**：所有 ORDER BY 必须加 LIMIT

### 3. DataWorks MCP 不可用
- **现象**：DataWorks MCP 返回 USER_NOT_LOGGED_IN
- **根因**：依赖浏览器 SSO，后端调用无法获取登录态
- **替代方案**：使用 maxc-cli（通过 ncs STS 凭证自动认证）

### 4. 钉钉文档访问限制
- **现象**：WebFetch 302 跳登录，浏览器加载超时
- **正确方式**：使用 `dws doc read --node <URL> --format json` 直接读取

### 5. Apple Mail AppleScript 超时
- **现象**：AppleScript 操作全部超时（-1712）
- **临时方案**：使用 `mailto:` URL 打开空白邮件窗口

## UI/前端已知问题

### 1. Prompt 字符限制显示不一致
- **PRD规范**：2000 字符
- **UI显示**：3000 字符
- **实际限制**：以 PRD 为准（2000 字符）
- **性质**：前端实现偏差

### 2. 列表页按钮不可见
- **现象**：off-screen 按钮直接点击无效
- **解决方案**：使用 JS click（btn.scrollIntoView + btn.click）

### 3. Tab 意外关闭
- **现象**：浏览器自动化过程中 tab 可能意外关闭
- **解决方案**：使用 `tabs_create_mcp` 重建 tab

## 季节标已知问题

### 1. seasonTagName为空导致FAIL（已修复 — 需求83728544）
- **现象**：season_tag 节点 FAIL，errorMsg="季节标未识别"
- **根因**：模型返回的 compositionNames 中无季节关键词（如真人模特图、休闲裤类目），`parseSeasonTag()` 返回 null，`buildFinishMessage()` 直接发 FAIL
- **修复**：需求 83728544 在 `buildFinishMessage()` 中增加兜底逻辑 —— `seasonTagName` 为空时默认赋值"春"（`fallbackSeasonTags` 默认值）
- **验证**：BT_5973 批次（休闲裤类目）全部 SUCCESS，season_tag="春"；对比 BT_5893（同图片）之前 7 条 FAIL
- **影响**：兜底后不再产生 FAIL，下游 strategy 节点正常消费 season_tag
- **回归用例**：见 [[features/11-季节标刷标]] 中 18 条必回归用例

### 2. workflow_record_log 无 node_type 索引
- **现象**：不带 batch_id 的 season_tag 查询全部超时（DMS 20s 限制）
- **根因**：`workflow_record_log` 只有 `batch_id` 索引，`node_type`/`gmt_create`/`status` 均无索引
- **规避**：所有查询必须用 `batch_id IN (...)` 走索引，禁止全表扫描
- **影响范围**：所有 node_type 的跨批次查询都受影响
