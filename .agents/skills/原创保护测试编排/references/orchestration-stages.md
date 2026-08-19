# 原创保护测试编排 - 八阶段 Bot 指令

> 本文件是 `原创保护测试编排` Skill 的阶段级执行指令。每个阶段以 Bot 指令格式描述：目标、调度 Skill、输入、输出、跳过条件、安全门与失败处理。

---

## Stage 1 - 用例生成

**目标**：把 PRD / 需求文档 / 代码变更转换为原创保护可执行的测试资产。

**调度 Skill**：`原创保护用例生成`

**输入**：
- PRD 钉钉文档 / 语雀链接 / 本地 `.md` 路径
- 技术方案 / 系分文档（可选）
- 代码 diff 或关键接口说明（可选）

**核心动作**：
1. 解析需求中的申请类型（QUICK / PRE / REGULAR）、结算规则、千牛标入驻、首发/转普通、维权等测试点。
2. 输出 XMind 结构化用例大纲（功能/异常/边界/性能/安全五维）。
3. 输出 pytest 可执行脚本，覆盖商家端 MTOP、小二端 cobweb、HSF Tool、DB 断言。

**预期输出**：
- `cases/yc-{需求号}-outline.xmind.txt`
- `cases/yc-{需求号}-test.py`
- 用例覆盖度说明（P0/P1/P2 数量）

**默认跳过条件**：
- 用户已提供现成用例集或 XMind 文件。
- 用户明确说「只排查/只跑已有用例」。

**安全门**：仅读取文档/代码，不写 DB。

**失败处理**：PRD 不可读 → 提示用户补充文档链接或切换到单阶段「规则校验」。

---

## Stage 2 - 规则校验

**目标**：在造数执行前确认业务规则、状态机、费用计算被用例覆盖且无冲突。

**调度 Skill**：`原创保护规则校验`

**输入**：
- Stage 1 输出的用例大纲或用户提供的规则关注点
- PRD 中关于补贴、退款、确收、首发、转普通的条款

**核心动作**：
1. 状态机完整性检查：申请 21 种状态、权益状态、结算单子状态是否闭环。
2. 补贴规则：9 类白名单判定、首发/非首发补贴金额、SYNC_CERT_FILE 快照时点。
3. 结算分流：下架率 70% 阈值、退款/确收金额计算、Job 链触发条件。
4. 输出规则缺口与风险项。

**预期输出**：
- 规则覆盖清单（✅/❌/⏳）
- 状态机缺口列表
- 高风险规则项（如「确收路径未验证」「边界下架率 70%」）

**默认跳过条件**：
- 用户未提及规则/状态机/补贴等校验诉求。
- 已提供通过评审的规则校验报告。

**安全门**：只读分析，不调用任何写操作。

**失败处理**：发现重大规则缺口 → 暂停 Stage 3，提示用户补充规则说明或修改 PRD。

---

## Stage 3 - 数据构造

**目标**：为后续执行准备符合 `env='staging'` 的测试数据。

**调度 Skill**：
- `yc-quick-audit-data-create`（创建 QUICK / PRE 申请）
- `yc-data-factory`（HSF Tool 改状态/改时间/触发退款/模拟审核）

**输入**：
- 申请类型（QUICK / PRE / REGULAR）
- seller_id（默认 2213249110271，以 `../yc-protection-qa-workbench/test-accounts.md` 为准）
- 目标状态或场景（如「快审通过 + 已绑品 + 即将到期」）

**核心动作**：
1. 若 PRE，先检查并半自动充值服务次数。
2. 调用 MTOP / cobweb 创建申请，获取 applyId。
3. 通过 HSF Tool 把申请推到目标状态（如 `QUICK_AUDITED`、`CERT_FILE_SYNCED`）。
4. 每次 HSF 写操作前执行 `SELECT id, env FROM yc_right_apply WHERE id = {applyId}` 确认 `env='staging'`。

**预期输出**：
- applyId / rightId / settleOrderId
- 当前状态快照
- 数据构造清单（含每一步 HSF 调用与 DB 验证结果）

**默认跳过条件**：
- 用户已提供有效 applyId 且明确无需新数据。
- Stage 2 因规则缺口被阻塞。

**安全门**：
- HSF Tool 写操作前必须 env 预检。
- 仅操作 `env='staging'` 记录；生产数据直接拒绝。

**失败处理**：
- 服务次数不足 → 走半自动充值流程并提示用户扫码。
- HSF 调用失败 → 进入 Stage 6 缺陷排查。

---

## Stage 4 - 执行助手

**目标**：执行 API / UI 测试用例并实时断言。

**调度 Skill**：`原创保护执行助手`

**输入**：
- Stage 3 构造的 applyId / sellerId
- Stage 1 的 pytest 脚本或用户指定的用例

**核心动作**：
1. 商家端 MTOP 接口调用（`taobao.industry.yc.right.apply` 等）。
2. 小二端 cobweb 页面操作（如需）。
3. DB 断言：状态、操作流水、结算单字段。
4. 截图/抓包/录屏归档到 `~/.att-tf/cases/`。

**预期输出**：
- 每条用例的 PASS/FAIL/SKIP 状态
- 断言失败时的 traceId / 截图 / 响应原文
- `cases.json` 供 `att-report` 上报

**默认跳过条件**：
- 用户仅要求 DB 验证、结算分析或缺陷排查。
- 缺少可执行用例且无明确执行目标。

**安全门**：
- 所有 DB 断言必须带 `env='staging'`。
- UI 自动化仅操作预发域名（`pre-fsyc.taobao.com`、`pre-xiaoer.alibaba-inc.com`）。

**失败处理**：
- 用例 FAIL → 先走 `qa-self-healing` 自愈重试一次。
- 仍失败 → 进入 Stage 6 缺陷排查。

---

## Stage 5 - 结算/异步验证

**目标**：验证原创保护结算链路、异步 Job、资金流向是否正确。

**调度 Skill**：
- `yc-settlement-analyser`（PRD 结算分析、资金流向、状态机、测试策略）
- `yc-data-factory`（ScheduleX Job 手动触发、HSF 改到期时间、改结算状态）
- `yc-db-verification`（结算单子状态、退款金额、操作流水验证）

**输入**：
- applyId / rightId / settleOrderId
- 测试场景（退款路径 / 确收路径 / 补贴发放 / 转普通后结算）

**核心动作**：
1. 若用户给 PRD，先用 `yc-settlement-analyser` 输出资金图、状态机、风险矩阵。
2. 用 HSF Tool 设置 `protect_expire_time` 为过去日期，构造到期场景。
3. 按顺序触发 ScheduleX Job：
   - `399576024`（专利保护定时失效）
   - `719211870`（服务完结退款）或 `721504806`（服务完结确收）
4. `yc-db-verification` 验证 `settle_status`、`serv_finish_refund_status`、`serv_finish_income_status`、退款金额。

**预期输出**：
- 资金流向图（Mermaid）
- 结算状态机图
- Job 触发与 DB 验证报告
- 风险项与未验证场景标注

**默认跳过条件**：
- 当前需求不涉及结算、退款、确收、补贴、下架率等异步链路。
- 用户仅要求 DB 验证而不触发 Job。

**安全门**：
- ScheduleX 触发仅允许预发环境。
- HSF 改时间/改状态前必须 env 预检。
- 退款金额必须等于剩余全量，否则拦截。

**失败处理**：
- Job 触发后状态未流转 → 进入 Stage 6 查 MetaQ / ScheduleX / 代码。
- 金额不符 → 直接标记 FAIL 并生成缺陷草稿。

---

## Stage 6 - 缺陷排查

**目标**：对 FAIL/BLOCKED/异常现象进行根因定位。

**调度 Skill**：`yc-defect-diagnosis`

**输入**：
- 问题现象描述
- applyId / sellerId / rightId / settleOrderId（如有）
- Stage 4/5 的失败日志、traceId、截图

**核心动作**：
1. 现象固化：环境、端、ID、复现步骤、预期/实际结果。
2. 数据层分析：自动选表查询 `yc_right_apply`、`yc_right`、`yc_right_settle_order`、`yc_tort_record`、`yc_right_apply_op_record`。
3. 消息层追踪：检查 MetaQ 是否发出/消费。
4. 定时任务排查：确认 ScheduleX 是否触发、分片是否命中。
5. 代码层验证：用 `a1 repo search` 定位关键代码逻辑。
6. 输出根因分类与 Aone Bug 草稿。

**预期输出**：
- 缺陷报告（含数据层/代码层证据）
- 根因分类（数据问题 / 代码缺陷 / 配置问题 / 消息丢失 / 前端 Bug / 环境差异）
- 修复建议
- Aone Bug 草稿

**默认跳过条件**：
- 所有前置阶段结果均为 PASS / 无异常，且用户未提问题现象。

**安全门**：
- 查询必须带 `env='staging'`；生产环境仅 SELECT。
- 不得通过 HSF/DMS 修改数据来「修复」缺陷。

**失败处理**：
- 缺少关键 ID → 向用户索取 applyId / sellerId / rightId。
- 根因不明确 → 输出待确认排查项，建议补充日志/SLS 查询。

---

## Stage 7 - 测试报告

**目标**：汇总执行结果，生成标准化报告并回填。

**调度 Skill**：
- `qa-test-report`（测试执行报告 + 知识指标报告）
- `att-report`（逐条用例 att-tf 上报）

**输入**：
- `~/.att-tf/cases/*/cases.json`
- Stage 1 用例的 caseTitle / description / priority / groupPath
- Stage 4/5 的执行结果与截图

**核心动作**：
1. 读取 att-tf cases，保持原始 caseTitle/description/priority/groupPath 不变，仅回填 status / errorMessage / execLog。
2. 生成「测试执行报告」与「知识指标报告」。
3. 发布到钉钉文档。
4. 回填 AOne 需求页。

**预期输出**：
- 钉钉文档链接
- AOne 回填结果
- PASS/FAIL/SKIP 分布与失败聚类摘要

**默认跳过条件**：
- 无 att-tf 执行记录且无手动执行结果可汇总。
- 用户仅要求缺陷排查/数据分析，未执行用例。

**安全门**：报告仅引用 staging 环境数据，不得泄露生产敏感信息。

**失败处理**：
- 钉钉文档发布失败 → 输出本地 Markdown 报告并提示用户手动上传。
- AOne 回填失败 → 保留报告链接供人工回填。

---

## Stage 8 - 千牛标打标/入驻

**目标**：解决商家因未打 TTYCBH 千牛标而无法入驻原创保护的问题。

**调度 Skill**：
- `原创保护千牛标打标`（打标操作）
- `yc-data-factory`（`SellerEnterToolService.enter` 触发入驻）

**输入**：
- seller_id（默认 2213249110271）
- 是否需要重新入驻（可选）

**核心动作**：
1. 查询 `seller_enter_info` 确认当前入驻状态。
2. 若未入驻或未打标，调用 `原创保护千牛标打标` Skill 完成 TTYCBH 打标。
3. 调用 `SellerEnterToolService.enter(sellerId)` 触发入驻（幂等）。
4. DB 验证 `seller_enter_info.status` 与千牛标状态。

**预期输出**：
- 千牛标打标结果
- `seller_enter_info` 入驻状态快照
- 入驻成功/失败的排查建议

**默认跳过条件**：
- 商家已入驻且千牛标已打，DB 确认状态正常。
- 当前任务与入驻/打标无关。

**安全门**：
- 仅对白名单测试 seller_id 执行。
- 入驻操作前确认 env='staging'。

**失败处理**：
- 打标失败 → 输出半自动脚本（TXT 上传模板）并提示用户手动完成。
- 入驻仍失败 → 进入 Stage 6 缺陷排查。

---

## 阶段间推进规则

1. **全链路模式**：Stage 1 → 8 顺序推进；前一阶段输出作为后一阶段输入。
2. **单阶段模式**：命中路由关键词时只执行该阶段，不自动推进。
3. **失败即排查**：Stage 1-5 任何 FAIL/BLOCKED 自动进入 Stage 6；Stage 6 完成后视结果决定是否进入 Stage 7。
4. **跳过不回头**：若某阶段被跳过，直接取上一有效阶段的输出继续推进。
