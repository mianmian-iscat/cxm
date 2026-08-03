# CHANGELOG

## [2.2.0] — 2026-04-23

### 新增

- **`navigate` step 类型升级**：从原来的 `Page.navigate + sleep(2)` 硬等，改为真正等待 `Page.loadEventFired` / `Page.domContentEventFired` 事件，支持 `waitUntil`（load/domcontentloaded/networkidle）、`timeout`、`waitText` 字段
- **`waitForUrl` step 类型**（新）：轮询当前 URL 直到包含指定字符串，用于确认跨页面跳转已完成，避免在上一页继续操作
- **`_node_bridge.js` 新增 `navigate` 命令**：启用 Page 域事件转发（`Page.loadEventFired`、`Page.domContentEventFired`、`Page.frameNavigated`），Python 侧可订阅
- **`input.schema.json` 更新**：`navigate` 补全字段定义，新增 `waitForUrl` schema

### 使用场景

- **用例前重置**：每个用例第一个 step 用 `{ "type": "navigate", "url": "...", "waitUntil": "networkidle" }` 回到干净入口页
- **跨页面锚点**：点击跳转后紧跟 `{ "type": "waitForUrl", "urlContains": "/detail" }` 确认到达目标页再继续操作

---

## [2.1.0] — 2026-04-22

### 新增

- **`core/knowledge_updater.py`**：Knowledge 自动更新组件（第五个 core 组件）
  - FINALIZE 阶段自动调用，把执行结果反哺回 knowledge 文件
  - `lastVerified` 更新：全部通过时记录验证时间和 run_id
  - 坑点沉淀：失败步骤的可识别错误自动追加到 `knownIssues[]`（去重）
  - `staleFields` 标记：selector 找不到元素时标记对应字段为失效
  - CHANGELOG 追加：有变更时写一行到 `history/CHANGELOG.md`
  - 支持跨 skill 目录写入（通过全局 index.json 定位 knowledge 文件）

- **`scripts/init-scene.js`**：场景化 Skill 初始化脚本
  - 探索目标页面 DOM（inputs/buttons/iframes）
  - 监听 5s 网络请求，发现 API
  - 坑点预检（水印/引导弹窗/React input/iframe/overlay）
  - 自动生成：`SKILL.md` + `knowledge/{scene}.json` + `references/overview.md`
  - 自动更新全局 `web-automation/knowledge/index.json`
  - confidence 机制：高置信度字段标 `high`，ambiguous 字段标 `low` 并提示人工补充

- **`impl.py`**：FINALIZE 阶段新增 KNOWLEDGE UPDATE 钩子
  - 调用 `KnowledgeUpdater.apply()`，失败不影响主流程
  - 变更摘要写入 `output.artifacts.knowledgeUpdate`

- **全局 `knowledge/index.json`**：升级为所有场景页面的统一入口
  - 新增字段：`host`、`route`、`skill`、`file`（支持跨目录引用）
  - 登记 6 个页面：xiaoer-product-mgmt / tpp-bucket / tpp-time-travel / qianniu-material / safety-code-whitelist / aifashion-style-selection

---

## [2.0.0] — 2026-04-21

### 重构（Breaking Change）

- **新增 `core/` 层**：将底层能力拆分为 4 个独立组件
  - `cdp_client.py`：CDP 连接封装，Node.js 桥接
  - `event_listener.py`：Network/Console/DOM 事件监听器
  - `video_recorder.py`：基于 screencast 的视频录制引擎
  - `artifact_manager.py`：产物管理，每次执行独立目录

- **新增 `impl.py`**：替代 `scripts/run-browser-test.js`
  - 状态机编排（INIT → CONNECT → CAPTURE_START → STEPS → FINALIZE → DONE）
  - 不写业务逻辑，只做流程编排
  - 支持视频录制（`video.enabled=true` + ffmpeg）

- **新增 `manifest.yaml`**：工程元数据
  - Chrome 版本要求、Node/Python 依赖
  - 产物配置（保留天数、类型）
  - 资源配额（最大步骤数、超时时间）

- **新增 `scripts/normalize_input.py`**：输入预处理
  - URL 格式校验、敏感信息脱敏、默认值补充

- **新增 `scripts/score_eval.py`**：质量评分
  - 4 个维度：步骤通过率、断言通过率、抓包完整性、证据完整性
  - 综合评分 0~100，≥80 且无 error 为通过

- **新增 `artifacts/`**：每次执行产物隔离目录
  - 包含 input.json / output.json / capture.json / capture.har / screenshots/ / manifest.json

- **新增 `eval/`**：离线评测框架
  - `thresholds.yaml`：上线门槛
  - `cases/smoke_*.json`：冒烟测试用例

- **新增 `tests/test_core.py`**：core 组件单测
  - 覆盖 normalize_input / score_eval / artifact_manager

- **新增 `references/boundary_cases.md`**：边界场景统一索引

- **新增 `prompts/rubric.txt`**：判定规则（元素定位优先级、等待策略、断言原则）

### 保留（向前兼容）

- `scripts/run-browser-test.js`：Node.js 版执行框架，仍可直接调用
- `schema/input.schema.json` / `schema/output.schema.json`：契约不变
- `prompts/system.txt`：硬约束不变
- `references/`：所有文档保留

---

## [1.0.0] — 2026-04-20

- 初始版本：SKILL.md + references/ 8 个文档
- 连接模板、截图规范、网络抓包（CDP Network）
- React 表单填写、iframe 操作、弹窗处理、文件上传

## 2026-04-25 - 场景化 skill 内化迁移
- 将 qianniu-test、tpp-test、safety-code-whitelist、product-management-test 移入 scenes/ 子目录
- 更新 knowledge/index.json 所有 file 路径
- 删除原独立 skill 目录，web-automation 现为唯一安装包
