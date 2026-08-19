# hfz-test-workflow 对抗验证检查点清单（CP1-CP4）

> 本文档定义 `hfz-test-workflow` 双域编排器与 `qa-adversarial-agent` 的接入协议，明确 CP1~CP4 四个检查点的触发时机、审计维度、Default-False 判定规则及 PASS/FAIL 分支。

## 1. 设计目标

- **防止假结果流入报告**：拦截 AI 执行者可能产生的 hallucination（编造结果）、skip（跳过步骤但声称完成）、misread（看错页面状态）三类风险。
- **证据优先于结论**：用例初始状态为 `UNVERIFIED`，必须提交真实、新鲜、可追溯的证据才能翻转为 `PASS`。
- **执行中当场拦截**：CP2 在关键操作后立即介入，避免伪造结果进入采证和上报环节。
- **强制复验 Bug**：CP4 在 Bug 提报前独立复验，避免数据污染导致的假性失败进入 AOne。

## 2. 核心机制

### 2.1 Default-False 原则

| 项目 | 规则 |
|------|------|
| 初始状态 | 每条用例默认 `UNVERIFIED`，不是 `PASS` |
| 翻转条件 | 六维审计全部 `CLEAR` 且四链证据齐全，方可翻转为 `PASS` |
| 保持条件 | 任一审计维度 `VIOLATION` 或证据缺失，状态保持 `UNVERIFIED`，用例 verdict = `FAIL` |
| 重试上限 | 每条用例最多重跑 2 次（retryCount 0/1/2），3 次失败标记 `BLOCKED`，强制重测 |

### 2.2 六维审计

| 维度 | 简称 | 核心问题 |
|------|------|---------|
| D1 直接矛盾检测 | `directContradiction` | 页面说的和 DB 说的是否一致？ |
| D2 时间合理性审计 | `temporalConsistency` | 结果时间、截图时间、DB 时间是否在执行窗口内？ |
| D3 数据链完整性 | `dataChainIntegrity` | 上游产出 ID 与下游使用 ID 是否一致？ |
| D4 存在性验证 | `existenceVerification` | 声称存在的数据、截图、任务是否真实存在？ |
| D5 状态合理性判断 | `stateReasonability` | 状态转换、数量、关联数据是否符合业务规则？ |
| D6 证据链真实性审计 | `evidenceAudit` | 四链证据（UI 操作 + 截图 + API + DB）是否真实、新鲜、可追溯？ |

### 2.3 四链证据要求

每条用例必须四者兼备，缺失任何一环 = 证据不完整：

| 证据链 | 要求 | 验证方式 |
|--------|------|----------|
| UI 操作 | 在预发环境真实执行操作 | 页面状态变化、任务流转 |
| UI 截图 | 每步关键操作截图保存至文件系统 | `Bash ls -la` 检查文件存在性 + `Read` 核验内容 |
| API 验证 | 捕获请求体 + 响应体 + HTTP 状态码 | `javascript_tool` monkey-patch fetch 或直接调用 API |
| DB 核对 | 独立查询验证实际落库数据 | `dms-alibaba CLI` 或 `db-query-tool` |

## 3. 检查点总览

| 检查点 | 触发时机 | 审计范围 | 执行强度 | 失败动作 |
|--------|----------|----------|----------|----------|
| **CP1 造数后门禁** | 造数完成、用例执行前 | 造数产物存在性 + 初始态 + 黄金数据集前置条件 | 存在性 + 初始态 | 中止执行，退回造数自愈 |
| **CP2 执行中拦截** | 用例关键操作后、进入下一步前 | 阶段性声称（页面 + DB 快速取证） | 直接矛盾 + 存在性优先 | 当场拦截，停止继续，要求纠正/重做 |
| **CP3 采证前审计** | 用例完成、att-tf 采证前 | 完整六维审计 + 四链证据 | 完整六维 | FAIL → 重跑 ≤2 次 → BLOCKED 强制重测 |
| **CP4 Bug 复验** | Bug 草稿生成后、AOne 提报前 | 复验数据新鲜度 + 截图真实性 + 复现一致性 | 复验专用 | 移除该 Bug，不允许提报 |

## 4. CP1：造数后门禁

### 4.1 触发时机

- F88 S3 数据构造完成后、S5 用例执行前。
- 原创保护 P3 数据构造完成后、P4 用例执行前。
- 任何需要上游数据产出的用例执行前。

### 4.2 审计内容

1. **造数产物存在性**
   - F88：BT_ 批次在 `g_workflow_batch` 可查；模板包 ID 在对应表可查；审核任务在 `g_afd_personal_task` 可查。
   - 原创保护：`applyId` 在 `yc_right_apply` 可査；`settleOrderId` 在 `yc_settle_order` 可査（如适用）。
2. **初始态正确性**
   - 批次/任务状态是否为预期的初始状态（如 `status=0/1`，而非终态）。
   - `env='staging'` 必须成立。
3. **黄金数据集前置条件（如命中）**
   - 若当前用例集与 `golden-dataset/manifest.json` 有交集，验证对应策略/链路/批次在 DB 可查且状态为初始态。
   - 黄金前置数据缺失 = CP1 FAIL。
4. **数据源合法性**
   - 禁止复用存量数据替代造数；所有验证数据必须来自当前会话造数记录（exec-log 有记录）。

### 4.3 PASS/FAIL 分支

- **PASS**：进入 S5/P4 用例执行。
- **FAIL**：中止执行，退回造数自愈或 `qa-self-healing`，修复后重新触发 CP1。

### 4.4 与 hfz-test-workflow 的映射

```
你现在必须执行：CP1 造数后对抗门禁（触发时机=F88 S3 / 原创保护 P3 完成；动作=调用 qa-adversarial-agent 审计造数产物存在性、初始态、黄金数据集前置条件；bash=无；PASS=进入执行阶段；FAIL=中止执行，退回造数自愈）
```

## 5. CP2：执行中拦截

### 5.1 触发时机

- 用例执行过程中，执行者完成关键操作并声称阶段性结果后，进入下一步之前。
- 适用于长链路用例（如审核、抽检、结算状态流转），不适用于单步原子操作。

### 5.2 审计内容

1. **阶段性声称快速审计**
   - 页面当前状态与执行者声称是否一致（直接矛盾检测）。
   - 声称创建/修改的数据在 DB 中是否存在（存在性验证）。
   - 状态转换是否合理（状态合理性判断）。
2. **聚焦范围**
   - 只审计当前阶段声称的内容，不做全量六维审计。
   - 优先直接矛盾 + 存在性，时间合理性和数据链完整性视场景补充。

### 5.3 PASS/FAIL 分支

- **PASS**：允许执行者进入下一步。
- **FAIL**：当场拦截，执行者立即停止，不得进入下一步，不得采证；下发 `failureDetail`，要求纠正或重做。该失败计入该用例的 retryCount。

### 5.4 与 hfz-test-workflow 的映射

```
你现在必须执行：CP2 执行中对抗拦截（触发时机=用例关键操作完成且执行者声称阶段性结果；动作=调用 qa-adversarial-agent 快速审计阶段性声称；bash=无；PASS=允许继续下一步；FAIL=当场拦截，携带 failureDetail 纠正/重做）
```

### 5.5 CP2 典型拦截场景

| 场景 | 审计动作 | 结果 |
|------|----------|------|
| 执行者声称"5 条全部审核完成" | 查 DB 实际完成数 | 实际 2/5 → FAIL，当场拦截 |
| 执行者在批次 A 上操作，声称批次 B 结果 | 比对页面 batchId 与声称 batchId | 不一致 → FAIL |
| 执行者声称已创建下游任务 | 查下游表是否存在记录 | 无记录 → FAIL |

## 6. CP3：采证前审计

### 6.1 触发时机

- 用例全部操作完成后、`att-tf` 采集证据之前。
- 对应 hfz-test-workflow 的 S6（F88）/ P5~P6（原创保护）后、S8/P7 报告生成前。
- 任何用例进入 `att-report` 上报池之前。

### 6.2 审计内容

完整六维审计 + 四链证据检查：

| 检查项 | 审计维度 | 关键动作 |
|--------|----------|----------|
| 页面与 DB 是否一致 | D1 | 用对抗 agent 自己从页面提取 ID，独立查 DB，三方比对 |
| 时间与执行窗口是否匹配 | D2 | `stat` 截图文件、`gmt_create`/`gmt_modified` 与 `executionTimestamp` 比对 |
| ID 链是否连续 | D3 | 上游产出 ID 与下游输入 ID 一致；跨表关联记录存在 |
| 截图与数据是否存在 | D4 | `ls -la` 检查截图文件；DB 查 claimedRecords 存在性 |
| 状态转换是否合理 | D5 | status 跳转是否符合业务状态机；数量是否对得上 |
| 四链证据是否真实新鲜 | D6 | E1~E6 六项证据检查全部 CLEAR |

### 6.3 PASS/FAIL 分支

- **PASS**：`att-tf` 采集证据，`att-report` 上报，状态标记为 `PASS`。
- **FAIL**：
  - retryCount < 2：携带 `failureDetail` 重跑用例（回到 CP2/CP3 起点）。
  - retryCount >= 2：标记 `BLOCKED`，记入 `blocked_cases.json`，不采集证据，不上报，必须强制重测。

### 6.4 与 hfz-test-workflow 的映射

```
你现在必须执行：CP3 采证前完整对抗审计（触发时机=用例执行完成、att-tf 采证前；动作=调用 qa-adversarial-agent 执行完整六维审计与四链证据检查；bash=无；PASS=att-tf 采证并进入上报池；FAIL=按 retryCount 重跑或标记 BLOCKED）
```

### 6.5 批量执行适配

对以 pytest 批量执行用例的编排器，允许在执行与自愈轮次结束后，对所有声称 PASS 的用例统一跑 CP3 审计循环（对应 hfz-test-workflow S6），但红线不变：必须在 `att-tf` 采集、`att-report` 上报之前完成。FAIL 用例仍逐条重跑。

## 7. CP4：Bug 复验

### 7.1 触发时机

- Bug 草稿生成后、AOne 提报前。
- 对应 hfz-test-workflow 的 S9→S10 之间 / 原创保护 P7→P8 之间。

### 7.2 审计内容

每条 Bug 必须经重新造数 + 页面实际验证：

1. **复验数据新鲜度**：复验用的新数据在 DB 可查，且 `gmt_create` 在复验窗口内。
2. **截图真实性**：复验截图文件存在，内容与 Bug 描述相关，时间戳在复验窗口内。
3. **复现一致性**：复验观察到的问题与 Bug 描述一致。
4. **排除数据污染**：确认复验失败不是由过期/错误测试数据导致的假性失败。

### 7.3 PASS/FAIL 分支

- **PASS**：允许提交 AOne Bug。
- **FAIL**：该 Bug 从草稿中移除，不允许提报；返回缺陷定位阶段重新排查。

### 7.4 与 hfz-test-workflow 的映射

```
你现在必须执行：CP4 Bug 复验对抗审计（触发时机=Bug 草稿生成后、AOne 提报前；动作=调用 qa-adversarial-agent 对每条 Bug 执行重新造数 + 页面复验；bash=无；PASS=允许提交 AOne；FAIL=移除该 Bug，返回缺陷定位）
```

## 8. 与 qa-adversarial-agent 的调用协议

### 8.1 调用方式

每个检查点以**隔离子任务**身份调用 `qa-adversarial-agent`，保持信息不对称：

- 只传递 `caseContext`：包含 `caseId`、`caseTitle`、`expectedResult`、`pageUrl`、`screenshotPath`、`claimedResults`、`dbHints`、`executionTimestamp`、`retryCount`、`previousFailures`。
- 不传递执行者的推理过程、API 调用记录、内部提取的 ID 值。
- `dbHints` 只给表名和字段名，不给具体 ID。

### 8.2 caseContext 示例

```json
{
  "caseId": "TC-001",
  "caseTitle": "审核完成触发抽检任务创建",
  "expectedResult": "主任务 status 变为 5，抽检任务被创建",
  "pageUrl": "https://pre-aifashion-xiaoer.../taskId=88001&taskType=audit",
  "screenshotPath": "/path/to/screenshot_tc001.png",
  "claimedResults": {
    "taskId": "88001",
    "status": "已完成",
    "statusCode": 5,
    "batchId": "BT_7543"
  },
  "dbHints": {
    "table": "g_afd_personal_task",
    "idField": "task_id"
  },
  "executionTimestamp": "2026-08-04T14:30:00+08:00",
  "retryCount": 0,
  "previousFailures": [],
  "checkpoint": "CP3"
}
```

### 8.3 返回报告格式

`qa-adversarial-agent` 返回 JSON 报告，编排器解析 `verdict`、`evidenceVerdict`、`failureDetail`：

```json
{
  "checkpoint": "CP3",
  "verdict": "PASS | FAIL | VERIFIER_ERROR",
  "caseId": "TC-001",
  "confidence": "HIGH | MEDIUM | LOW",
  "auditFindings": {
    "directContradiction": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "temporalConsistency": {"status": "CLEAR | SUSPICIOUS | VIOLATION", "detail": "..."},
    "dataChainIntegrity": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "existenceVerification": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "stateReasonability": {"status": "CLEAR | SUSPICIOUS | VIOLATION", "detail": "..."}
  },
  "evidenceAudit": {
    "E1_screenshotFreshness": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "E2_screenshotRelevance": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "E3_dbTimestamp": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "E4_batchIdTraceability": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "E5_evidenceSourceLegitimacy": {"status": "CLEAR | VIOLATION", "detail": "..."},
    "E6_evidenceCompleteness": {"status": "CLEAR | VIOLATION", "detail": "..."}
  },
  "evidenceVerdict": "VALID | INVALID",
  "suspiciousObservations": [],
  "failureDetail": null
}
```

`failureDetail` 非空时结构：

```json
{
  "primaryViolation": "最严重的不一致描述",
  "secondaryViolations": ["其他问题"],
  "retrySuggestion": "给执行者的修正建议"
}
```

## 9. 在 hfz-test-workflow 中的阶段映射

### 9.1 F88 十步流程映射

| 检查点 | hfz-test-workflow 步骤 | 时机 | 审计范围 |
|--------|------------------------|------|----------|
| CP1 | S3 之后、S5 之前 | 造数完成后、执行前 | 造数产物存在性 + 初始态 + 黄金数据集 |
| CP2 | S5 执行中 | 关键操作后、下一步前 | 阶段性声称快速审计 |
| CP3 | S6 之后、S8 之前 | 采证前、上报前 | 完整六维 + 四链证据 |
| CP4 | S9 之后、AOne 提报前 | Bug 草稿生成后 | 重新造数 + 页面复验 |

### 9.2 原创保护八阶段流程映射

| 检查点 | 原创保护阶段 | 时机 | 审计范围 |
|--------|--------------|------|----------|
| CP1 | P3 之后、P4 之前 | 造数完成后、执行前 | applyId/settleOrderId 存在性 + 初始态 |
| CP2 | P4 执行中 | 关键操作后、下一步前 | 阶段性声称快速审计 |
| CP3 | P5/P6 之后、P7 之前 | 采证前、上报前 | 完整六维 + 四链证据 |
| CP4 | P7 之后、AOne 提报前 | Bug 草稿生成后 | 重新造数 + 页面复验 |

## 10. 执行循环伪代码

```
# CP1
造数完成 → 启动 qa-adversarial-agent（checkpoint=CP1）
IF CP1 FAIL:
    退回造数自愈
    RETURN

# CP2 + CP3 每条用例
FOR each case IN cases:
    retryCount = 0
    WHILE retryCount <= 2:
        执行用例

        # CP2：关键操作后拦截
        FOR each milestone IN case.milestones:
            执行者声称阶段性结果
            启动 qa-adversarial-agent（checkpoint=CP2）
            IF CP2 FAIL:
                当场拦截，停止继续
                retryCount += 1
                BREAK 到 WHILE 开头

        # CP3：采证前完整审计
        构造 caseContext
        启动 qa-adversarial-agent（checkpoint=CP3）
        IF CP3 PASS:
            att-tf 采证（status=PASS）
            BREAK
        ELSE:
            retryCount += 1
            IF retryCount > 2:
                标记 BLOCKED，记入 blocked_cases.json
                不采集证据，不上报

# CP4
FOR each bug IN bug_drafts:
    重新造数 + 页面复验
    启动 qa-adversarial-agent（checkpoint=CP4）
    IF CP4 FAIL:
        从草稿中移除该 Bug
        返回缺陷定位
    ELSE:
        允许提交 AOne

# 台账
每个检查点结果写入 checkpoint_log.json
```

## 11. 台账与度量

### 11.1 checkpoint_log.json 字段

```json
{
  "caseId": "TC-001",
  "checkpoint": "CP3",
  "timestamp": "2026-08-04T14:35:00+08:00",
  "verdict": "PASS",
  "confidence": "HIGH",
  "primaryViolation": null,
  "retryCount": 0,
  "auditorSessionId": "..."
}
```

### 11.2 关键指标

| 指标 | 说明 |
|------|------|
| CP1 拦截率 | 造数阶段被拦截的任务占比 |
| CP2 当场拦截率 | 执行中被当场拦截的用例占比 |
| CP3 误报/漏报数 | 审计结果与人工复核不一致的数量 |
| CP4 Bug 移除率 | 因复验失败被移除的 Bug 占比 |
| BLOCKED 强制重测完成率 | 标记 BLOCKED 后是否全部完成重测 |

## 12. 安全与边界

1. **只读原则**：`qa-adversarial-agent` 只查询、不修改任何数据。
2. **env='staging'**：所有 DB 查询必须带 `env='staging'` 过滤（`f88_*` 表除外）。
3. **禁止传递 ID 值**：`dbHints` 只给表名和字段名，ID 由对抗 agent 自己从页面提取。
4. **CP2 不豁免 CP3**：即使 CP2 通过，采证前仍必须跑完整 CP3。
5. **CP3 不豁免 CP4**：Bug 草稿必须独立过 CP4，即使对应用例已通过 CP3。
6. **VERIFIER_ERROR 处理**：若对抗 agent 自身工具异常，输出 `verdict=VERIFIER_ERROR`，不算用例 FAIL，请求人工介入。

## 13. 关联文档

- `qa-adversarial-agent/SKILL.md`：对抗 agent 的完整行为准则、五维审计法、证据链审计、输出协议。
- `hfz-test-workflow/SKILL.md`：双域编排器入口、步骤与子 skill 映射。
- `hfz-test-workflow/references/orchestration-flow.md`：F88 十步流程与原创保护八阶段流程的详细步骤。
- `yc-protection-qa-workbench/regression-suite-index.md`：回归用例集索引，CP3 审计的用例来源之一。
