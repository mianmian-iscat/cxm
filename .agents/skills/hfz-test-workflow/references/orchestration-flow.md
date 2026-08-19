# hfz-test-workflow 详细编排流程

> 本文档是 `hfz-test-workflow` 的 references 补充，包含 F88 十步流程与原创保护八阶段流程的详细步骤、触发时机、执行动作、bash/CLI 模板及 PASS/FAIL 分支。
> 主 SKILL.md 保持精简；详细步骤统一维护在此。

## 通用开场指令

每个测试会话开始时，bot 必须先输出：

```
你现在必须执行：att-start 声明（触发时机=会话开始；动作=调用 att-start skill 登记身份/采证规范；bash=无；PASS=继续路由；FAIL=中止并提示用户）
```

## 一、F88 十步流程

### S1 需求分析

```
你现在必须执行：F88 需求解析（触发时机=用户输入含 F88/主图/种草/审核/BT_/策略/模板/视频/买手；动作=读取 PRD/提测单/代码 diff，提取测试范围、执行模式、关键点位；bash=无；PASS=输出需求摘要进入 S2；FAIL=向用户澄清需求）
```

- 输入：PRD 链接 / 提测单 / AOne 需求号 / 代码分支 / 用户描述
- 动作：
  1. 读取 PRD / 提测单；必要时用 `a1 code` 查代码 diff。
  2. 提取业务域（主图/种草/视频/审核/模板包/商详拼接/盗图整改）。
  3. 确认执行模式（BATCH / STREAM / 混合）。
- PASS：输出 `需求摘要.md`（范围、风险、依赖）。
- FAIL：缺少 PRD/提测单 → 询问用户补充。

### S2 用例生成

```
你现在必须执行：F88 用例生成与评估（触发时机=S1 完成；动作=调用 PRD用例生成 / 统一用例生成 生成结构化用例，调用 测试用例评估 执行八维覆盖度检查；bash=无；PASS=用例集 + 钉钉文档链接；FAIL=启动最多 2 轮缺口补齐，仍不足则标记 BLOCKED）
```

- 子 skill：`PRD用例生成`、`统一用例生成`、`测试用例评估`
- 输出：用例集（Markdown / 钉钉文档）、覆盖度评分、未覆盖项。

### S3 数据构造

```
你现在必须执行：F88 测试数据构造（触发时机=S2 用例集就绪；动作=按业务域调用策略试运行/模板包创建/审核数据构造；bash=~/dms-alibaba/bin/dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."；PASS=拿到 BT_xxxx / 模板包 ID / 审核任务；FAIL=调用 qa-self-healing 诊断造数失败）
```

- 子 skill：`f88-strategy-test-run`、`f88-template-package-create`、`审核数据构造`
- 约束：
  - 必须全量构造新数据，禁止复用存量。
  - 审核数据需带 `X-AFD-Emp-Identity: f88` 租户头。
  - formal 语义验证场景使用手动创建 API。

### S4 环境检查

```
你现在必须执行：F88 链路环境检查（触发时机=S3 数据就绪；动作=检查链路配置 13 大类 61 项、模型可用性、容量限流、执行模式；bash=无；PASS=环境 OK 进入执行；FAIL=输出风险清单，用户确认后降级或修复）
```

- 子 skill：`f88-link-config-check`、`f88-pipeline-monitor`
- 覆盖：阶段编排、模板匹配、生图节点、审核节点、参数流转、多套上传、LLM 节点、模型可用性、容量与限流、执行模式等。

### CP1 造数后门禁（F88：S3→S5）

```
你现在必须执行：CP1 造数后门禁（触发时机=F88 S3 数据构造完成；动作=调用 qa-adversarial-agent 审计造数产物存在性、初始态、黄金数据集前置条件；bash=无；PASS=进入 S5 用例执行；FAIL=中止执行，退回造数自愈）
```

- 子 skill：`qa-adversarial-agent`
- 审计内容：
  1. **造数产物存在性**：BT_ 批次在 `g_workflow_batch` 可查；模板包 ID 在对应表可查；审核任务在 `g_afd_personal_task` 可查。
  2. **初始态正确性**：批次/任务状态为预期初始态（非终态），`env='staging'` 必须成立。
  3. **黄金数据集前置条件**：若当前用例集命中 `golden-dataset/manifest.json`，验证对应策略/链路/批次在 DB 可查且为初始态。
  4. **数据源合法性**：禁止复用存量数据替代造数；所有验证数据必须来自当前会话造数记录。
- PASS：进入 S5 用例执行。
- FAIL：中止执行，退回 `qa-self-healing` 或造数 skill 修复，修复后重新触发 CP1。

### S5 用例执行

```
你现在必须执行：F88 用例执行（触发时机=S4 通过；动作=CDP 浏览器 / API / harness 执行用例并采证；bash=无；PASS=所有用例执行完成，进入 S6；FAIL=记录失败用例，进入 S7 缺陷定位）
```

- 子 skill：`web-automation`、`harness-runner`、`f88-test-mode`
- 要求：截图、接口返回、traceId 归档到 artifacts/。

#### CP2 执行中拦截（F88：S5 内）

```
你现在必须执行：CP2 执行中对抗拦截（触发时机=F88 S5 用例关键操作完成且执行者声称阶段性结果；动作=调用 qa-adversarial-agent 快速审计阶段性声称；bash=无；PASS=允许继续下一步；FAIL=当场拦截，携带 failureDetail 纠正/重做）
```

- 子 skill：`qa-adversarial-agent`
- 触发点：用例执行过程中，完成关键操作并声称阶段性结果后、进入下一步之前。
- 审计内容：
  1. **直接矛盾检测**：页面当前状态与执行者声称是否一致。
  2. **存在性验证**：声称创建/修改的数据在 DB 中是否真实存在。
  3. **状态合理性**：状态转换是否符合业务状态机。
- 信息隔离：`dbHints` 只给表名和字段名，不给具体 ID；ID 由对抗 agent 自己从页面提取。
- PASS：允许执行者进入下一步。
- FAIL：当场拦截，该用例 `retryCount += 1`，携带 `failureDetail` 要求纠正或重做；不继续采证。

### S6 DB/日志验证

```
你现在必须执行：F88 数据库与日志验证（触发时机=S5 执行完成；动作=查 stylespot/scenario DB、SLS 日志、审核层级、跨表一致性；bash=~/dms-alibaba/bin/dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."；PASS=DB/日志与预期一致；FAIL=提取异常进入 S7）
```

- 子 skill：`f88-data-query`、`f88-approve-verify-sql`、`f88-log-analysis`
- DB 约束：
  - `workflow_record_log` 必须带 `id > 6400000`。
  - 只查 `env='staging'`（f88_* 表除外）。
  - BATCH/STREAM 差异、subJobId 覆盖率、三层审核结构必查。

### CP3 采证前完整审计（F88：S6→S8）

```
你现在必须执行：CP3 采证前完整对抗审计（触发时机=F88 S6 DB/日志验证完成、att-tf 采证前；动作=调用 qa-adversarial-agent 执行完整六维审计与四链证据检查；bash=无；PASS=att-tf 采证并进入 S8 报告生成；FAIL=按 retryCount 重跑或标记 BLOCKED）
```

- 子 skill：`qa-adversarial-agent`
- 审计范围：完整六维审计 + 四链证据检查。
  - **D1 直接矛盾检测**：页面与 DB 是否一致。
  - **D2 时间合理性审计**：结果时间、截图时间、DB 时间是否在执行窗口内。
  - **D3 数据链完整性**：上游产出 ID 与下游使用 ID 是否一致。
  - **D4 存在性验证**：声称存在的数据、截图、任务是否真实存在。
  - **D5 状态合理性判断**：状态转换、数量、关联数据是否符合业务规则。
  - **D6 证据链真实性审计**：四链证据（UI 操作 + 截图 + API + DB）是否真实、新鲜、可追溯。
- 四链证据要求：
  - UI 操作：在预发环境真实执行操作。
  - UI 截图：每步关键操作截图保存至文件系统。
  - API 验证：捕获请求体 + 响应体 + HTTP 状态码。
  - DB 核对：独立查询验证实际落库数据。
- PASS：进入 S8 测试报告生成，`att-tf` 采证并 `att-report` 上报。
- FAIL：
  - `retryCount < 2`：携带 `failureDetail` 重跑该用例（回到 CP2/CP3 起点）。
  - `retryCount >= 2`：标记 `BLOCKED`，记入 `blocked_cases.json`，不采集证据，不上报，必须强制重测。

### S7 缺陷定位

```
你现在必须执行：F88 失败根因定位（触发时机=S5/S6 发现 FAIL；动作=调用 f88-failure-analysis 13 个工作流 + f88-clustering-service 聚类；bash=~/dms-alibaba/bin/dms-alibaba sql run stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."；PASS=定位根因并输出修复建议；FAIL=标记为待人工排查，IM 私聊用户）
```

- 子 skill：`f88-failure-analysis`、`f88-clustering-service`

### S8 测试报告

```
你现在必须执行：F88 测试报告生成（触发时机=S6/S7 完成；动作=调用 qa-test-report 生成双报告，att-report 逐条上报 testflow；截图关联检查=P0 用例必须有 screenshotPaths，否则阻断报告生成，提示补截图；bash=无；PASS=报告链接回填 AOne；FAIL=提示用户手动回填）
```

- 子 skill：`qa-test-report`、`att-report`
- **截图关联检查**：`att report --dry-run` 复核时，P0 用例若 `截图×0` 则阻断真发。浏览器/GUI 测试必须有 UI 截图；纯接口测试需在 description 中注明"纯接口验证，无 UI 截图"；截图已拍但未关联时检查 seq 区间是否覆盖。

### S9 Bug 提报

```
你现在必须执行：F88 Bug 草稿与提交（触发时机=S7 定位到真实缺陷；动作=调用 f88-bug-drafter 生成草稿，aone-bug-submit 提交；bash=无；PASS=AOne Bug 链接；FAIL=保存草稿待用户确认）
```

- 子 skill：`f88-bug-drafter`、`aone-bug-submit`

### CP4 Bug 复验对抗审计（F88：S9→S10）

```
你现在必须执行：CP4 Bug 复验对抗审计（触发时机=F88 S9 Bug 草稿生成后、AOne 提报前；动作=调用 qa-adversarial-agent 对每条 Bug 执行重新造数 + 页面复验；bash=无；PASS=允许提交 AOne；FAIL=移除该 Bug，返回缺陷定位）
```

- 子 skill：`qa-adversarial-agent`
- 审计内容：
  1. **复验数据新鲜度**：复验用的新数据在 DB 可查，且 `gmt_create` 在复验窗口内。
  2. **截图真实性**：复验截图文件存在，内容与 Bug 描述相关，时间戳在复验窗口内。
  3. **复现一致性**：复验观察到的问题与 Bug 描述一致。
  4. **排除数据污染**：确认复验失败不是由过期/错误测试数据导致的假性失败。
- PASS：允许提交 AOne Bug。
- FAIL：该 Bug 从草稿中移除，不允许提报；返回 S7 缺陷定位阶段重新排查。

### S10 知识沉淀

```
你现在必须执行：F88 知识沉淀（触发时机=S8/S9 完成；动作=更新 web-automation 页面知识、F88测试知识库、失败模式库、回归用例集；bash=无；PASS=知识库更新完成；FAIL=记录待更新项，进入下次迭代）
```

- 子 skill：`f88-clustering-service`、`F88测试知识库`

---

## 二、原创保护八阶段流程

### P1 用例生成

```
你现在必须执行：原创保护用例生成（触发时机=用户输入含原创保护/yc/首发/保护/结算/apply/seller；动作=读取 PRD，调用 原创保护用例生成 输出 XMind 大纲 + pytest 脚本；bash=无；PASS=用例文件就绪；FAIL=向用户澄清需求范围）
```

- 子 skill：`原创保护用例生成`

### P2 规则校验

```
你现在必须执行：原创保护规则校验（触发时机=P1 完成；动作=校验状态机 21 态、补贴 9 类白名单、首发编辑权限、保护期/转普通流程、结算状态机；bash=无；PASS=规则清单与预期一致；FAIL=标记风险并询问用户是否继续）
```

- 子 skill：`原创保护规则校验`、`yc-settlement-analyser`

### P3 数据构造

```
你现在必须执行：原创保护测试数据构造（触发时机=P2 通过；动作=调用 yc-quick-audit-data-create 创建 QUICK/PRE 申请，yc-data-factory 改状态/时间/补贴/模拟审核；bash=mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0" --method "updateStatus~java.lang.Long;java.lang.String" --args '[{applyId}, "QUICK_AUDITED"]' --app taobao-yc-serverless --unit pre；PASS=拿到 applyId/rightId/settleId；FAIL=启动自愈或标记 BLOCKED）
```

- 子 skill：`yc-quick-audit-data-create`、`yc-data-factory`
- 安全约束：
  - 每次写操作前执行 `SELECT id, env FROM yc_right_apply WHERE id = {applyId}`。
  - 仅 `env='staging'` 继续；prod/production 立即中止并告警。
  - PRE 初审服务次数不足时半自动充值。

### CP1 造数后门禁（原创保护：P3→P4）

```
你现在必须执行：CP1 造数后门禁（触发时机=原创保护 P3 数据构造完成；动作=调用 qa-adversarial-agent 审计造数产物存在性、初始态、黄金数据集前置条件；bash=无；PASS=进入 P4 用例执行；FAIL=中止执行，退回造数自愈）
```

- 子 skill：`qa-adversarial-agent`
- 审计内容：
  1. **造数产物存在性**：`applyId` 在 `yc_right_apply` 可查；`rightId` 在 `yc_right` 可查；`settleId` 在 `yc_right_settle_order` 可查。
  2. **初始态正确性**：申请/权利/结算状态为预期初始态（非终态），`env='staging'` 必须成立。
  3. **黄金数据集前置条件**：若当前用例集命中 `golden-dataset/manifest.json`，验证对应申请/权利/结算在 DB 可查且为初始态。
  4. **数据源合法性**：禁止复用存量数据替代造数；所有验证数据必须来自当前会话造数记录。
- PASS：进入 P4 用例执行。
- FAIL：中止执行，退回 `qa-self-healing` 或造数 skill 修复，修复后重新触发 CP1。

### P4 执行助手

```
你现在必须执行：原创保护用例执行（触发时机=P3 数据就绪；动作=调用 原创保护执行助手 执行 API/UI 用例并实时断言；bash=无；PASS=用例执行完成；FAIL=记录失败进入 P6）
```

- 子 skill：`原创保护执行助手`

#### CP2 执行中拦截（原创保护：P4 内）

```
你现在必须执行：CP2 执行中对抗拦截（触发时机=原创保护 P4 用例关键操作完成且执行者声称阶段性结果；动作=调用 qa-adversarial-agent 快速审计阶段性声称；bash=无；PASS=允许继续下一步；FAIL=当场拦截，携带 failureDetail 纠正/重做）
```

- 子 skill：`qa-adversarial-agent`
- 触发点：用例执行过程中，完成关键操作并声称阶段性结果后、进入下一步之前。
- 审计内容：
  1. **直接矛盾检测**：页面当前状态与执行者声称是否一致。
  2. **存在性验证**：声称创建/修改的数据在 DB 中是否真实存在。
  3. **状态合理性**：状态转换是否符合业务状态机。
- 信息隔离：`dbHints` 只给表名和字段名，不给具体 ID；ID 由对抗 agent 自己从页面提取。
- PASS：允许执行者进入下一步。
- FAIL：当场拦截，该用例 `retryCount += 1`，携带 `failureDetail` 要求纠正或重做；不继续采证。

### P5 结算/异步验证

```
你现在必须执行：原创保护结算与异步验证（触发时机=涉及到期/退款/确收/补贴场景；动作=手动触发 ScheduleX Job 链，调用 yc-db-verification 验证状态机与资金流向；bash=a1 schedulerx job run --jobId 399576024 --dataTime {yyyy-MM-dd}；PASS=状态按预期流转；FAIL=进入 P6 缺陷排查）
```

- 子 skill：`yc-data-factory`、`yc-db-verification`
- Job 链：399576024（专利保护定时失效）→ 719211870（退款）/ 721504806（确收）。
- 下架率分流：≥70% 确收，<70% 退款。

### P6 缺陷排查

```
你现在必须执行：原创保护缺陷排查（触发时机=P4/P5 发现 FAIL；动作=从 DB / MetaQ / ScheduleX / 代码多源定位根因；bash=~/dms-alibaba/bin/dms-alibaba sql query scenario --db rm-8vb6631b89ix0qkwl --sql "SELECT ..."；PASS=输出根因与修复建议；FAIL=IM 私聊用户并标记 BLOCKED）
```

- 子 skill：`yc-defect-diagnosis`

### CP3 采证前完整审计（原创保护：P6→P7）

```
你现在必须执行：CP3 采证前完整对抗审计（触发时机=原创保护 P6 缺陷排查完成、att-tf 采证前；动作=调用 qa-adversarial-agent 执行完整六维审计与四链证据检查；bash=无；PASS=att-tf 采证并进入 P7 报告生成；FAIL=按 retryCount 重跑或标记 BLOCKED）
```

- 子 skill：`qa-adversarial-agent`
- 审计范围：完整六维审计 + 四链证据检查。
  - **D1 直接矛盾检测**：页面与 DB 是否一致。
  - **D2 时间合理性审计**：结果时间、截图时间、DB 时间是否在执行窗口内。
  - **D3 数据链完整性**：上游产出 ID 与下游使用 ID 是否一致。
  - **D4 存在性验证**：声称存在的数据、截图、任务是否真实存在。
  - **D5 状态合理性判断**：状态转换、数量、关联数据是否符合业务规则。
  - **D6 证据链真实性审计**：四链证据（UI 操作 + 截图 + API + DB）是否真实、新鲜、可追溯。
- 四链证据要求：
  - UI 操作：在预发环境真实执行操作。
  - UI 截图：每步关键操作截图保存至文件系统。
  - API 验证：捕获请求体 + 响应体 + HTTP 状态码。
  - DB 核对：独立查询验证实际落库数据。
- PASS：进入 P7 测试报告生成，`att-tf` 采证并 `att-report` 上报。
- FAIL：
  - `retryCount < 2`：携带 `failureDetail` 重跑该用例（回到 CP2/CP3 起点）。
  - `retryCount >= 2`：标记 `BLOCKED`，记入 `blocked_cases.json`，不采集证据，不上报，必须强制重测。

### P7 测试报告

```
你现在必须执行：原创保护测试报告生成（触发时机=P5/P6 完成；动作=调用 qa-test-report 生成双报告，att-report 逐条上报；bash=无；PASS=报告链接回填 AOne；FAIL=提示用户手动回填）
```

- 子 skill：`qa-test-report`、`att-report`

### CP4 Bug 复验对抗审计（原创保护：P7→P8）

```
你现在必须执行：CP4 Bug 复验对抗审计（触发时机=原创保护 P7 Bug 草稿生成后、AOne 提报前；动作=调用 qa-adversarial-agent 对每条 Bug 执行重新造数 + 页面复验；bash=无；PASS=允许提交 AOne；FAIL=移除该 Bug，返回缺陷定位）
```

- 子 skill：`qa-adversarial-agent`
- 审计内容：
  1. **复验数据新鲜度**：复验用的新数据在 DB 可查，且 `gmt_create` 在复验窗口内。
  2. **截图真实性**：复验截图文件存在，内容与 Bug 描述相关，时间戳在复验窗口内。
  3. **复现一致性**：复验观察到的问题与 Bug 描述一致。
  4. **排除数据污染**：确认复验失败不是由过期/错误测试数据导致的假性失败。
- PASS：允许提交 AOne Bug。
- FAIL：该 Bug 从草稿中移除，不允许提报；返回 P6 缺陷排查阶段重新排查。

### P8 千牛标打标/入驻

```
你现在必须执行：原创保护千牛标打标与入驻（触发时机=遇到"抱歉，该服务现面向具备高原创能力要求的商家开放"或需要 TTYCBH 入驻；动作=调用 原创保护千牛标打标 打标 TTYCBH，yc-data-factory enterSeller 完成入驻；bash=mw hsf service invoke "com.taobao.industry.yc.serverless.service.hsf.tool.SellerEnterToolService:1.0.0" --method "enter~java.lang.Long" --args '[{sellerId}]' --app taobao-yc-serverless --unit pre；PASS=入驻成功；FAIL=记录失败原因）
```

- 子 skill：`原创保护千牛标打标`、`yc-data-factory`

---

## 三、群消息处理规则

```
你现在必须执行：群消息白名单过滤（触发时机=消息来自钉钉群/IM 转发；动作=判断消息是否匹配白名单；bash=无；PASS=进入域路由；FAIL=忽略消息）
```

白名单仅允许：
1. 收到提测消息：含 "提测" / "提测单" / "测试" / "PRD" / "需求" 且命中 F88 / 原创保护关键词。
2. 测试完成结果摘要：由子 skill 或 att-report 生成的标准化结果摘要。

---

## 四、MCP 三级降级协议执行

```
你现在必须执行：MCP 三级降级（触发时机=MCP 调用失败；动作=L1 重试 → L2 同能力 CLI → L3 BLOCKED_MCP + IM 私聊；bash=见各子 skill CLI 模板；PASS=工具执行成功；FAIL=标记 BLOCKED_MCP 并通知用户）
```

| 能力 | MCP 工具 | L2 CLI 降级 |
|------|---------|------------|
| DMS 查询 | `dms-mcp-server::executeScript` | `~/dms-alibaba/bin/dms-alibaba sql query/run` |
| 日志查询 | SLS MCP | `normandy log list --source sls` / `aliyun sls` |
| ScheduleX | MCP / 控制台 | 预发控制台「运行一次」/ `a1 schedulerx` |
| HSF Tool | MCP | `mw hsf service invoke` |

---

## 五、安全红线执行清单

```
你现在必须执行：测试安全预检（触发时机=任何 DB/HSF/数据修改操作前；动作=确认 env='staging'、禁止 DML、完成 att-start；bash=SELECT id, env FROM yc_right_apply WHERE id = {applyId}；PASS=继续执行；FAIL=立即中止并告警）
```

1. env='staging'：所有 scenario/stylespot 查询必须带 env 过滤（f88_* 表除外）。
2. 禁止 DML：测试流程内不写库；`createDataChangeOrder` 仅用户显式要求。
3. att-start：每个会话先声明。
4. 生产数据误改保护：prod/production 直接拒绝并 IM 私聊告警。
