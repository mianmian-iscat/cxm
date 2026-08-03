# 断言能力速查 · 一期三件套

> 版本：v1.0 · 作者：web-automation 断言增强计划
> 适用：eval/cases/*.json 用例层 + 场景化测试 Skill
> 关联：schema/tools/{dbAssert,assertAPI,assertUI}.schema.json

本框架的断言分两层：

- **Python 内核层**（[core/assertion_framework.py](../core/assertion_framework.py)）：四层领域断言（状态机/结算/契约/合规） + 三层执行断言（Pre/Realtime/Post），给 harness 用。
- **JSON 用例层**（[core/step_executor.py](../core/step_executor.py)）：暴露给 `eval/cases/*.json` 的 step.type 集合，给用例编写者用。

本文档只覆盖 **JSON 用例层**，且聚焦一期三件套新增的 `dbAssert / assertAPI / assertUI`。

## 速查表

| type | 用途 | 必填 | 通道 | schema |
|---|---|---|---|---|
| `dbAssert` | SQL 只读查询 + 行/字段比对 | group, db, sql | dms-alibaba CLI 桥 | [dbAssert.schema.json](../schema/tools/dbAssert.schema.json) |
| `assertAPI` | 对已捕获 API 响应做精确断言 | type | capture_manager.last_api_entry / get_api_entry | [assertAPI.schema.json](../schema/tools/assertAPI.schema.json) |
| `assertUI` | DOM 元素 visible/disabled/text/count/attribute/css | selector | CDP evaluate 注入 JS | [assertUI.schema.json](../schema/tools/assertUI.schema.json) |
| `assert`（原有） | page/api 文本 contains | target, contains | — | [assert.schema.json](../schema/tools/assert.schema.json) |
| `assertStore`（原有） | 已存值 equals/gte/lt/expression | key | variable_store | [assertStore.schema.json](../schema/tools/assertStore.schema.json) |

---

## 1. dbAssert — DB 断言

**通道**：`scripts/dms-alibaba-bridge.js` → `dms-alibaba sql query <group> --db <db> --sql <sql>`

**安全约束**：
- SQL 首关键字必须是 `SELECT` / `WITH` / `EXPLAIN`
- 禁用 `DROP / TRUNCATE / ALTER / GRANT / INSERT / UPDATE / DELETE / CREATE / EXEC` 等
- 剥离字符串字面量与注释后再检查（避免误判 `WHERE status='delete'`）
- 超时默认 30s，最大 120s

### 最小用法

```json
{
  "type": "dbAssert",
  "group": "quality_f88",
  "db": "dev-wulanchabu",
  "sql": "SELECT id, job_type FROM g_afd_review_job WHERE id = 12345",
  "rowCount": 1,
  "jsonPath": "$.job_type",
  "equals": 0
}
```

### 参数替换（防注入请配合 SQL 只读检查）

```json
{
  "type": "dbAssert",
  "group": "quality_f88",
  "db": "dev-wulanchabu",
  "sql": "SELECT id, task_name FROM g_afd_review_job WHERE id IN (:a, :b)",
  "params": {"a": 12345, "b": "BT_6789"},
  "rowCount": 2
}
```

替换规则：
- `number` → `12345`
- `string` → `'O''Brien'`（单引号自动转义）
- `boolean` → `1` / `0`
- `null` → `NULL`

### 全字段对照

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| group | ✅ | string | DMS 数据库组名（如 `quality_f88`） |
| db | ✅ | string | 组内具体库名（如 `dev-wulanchabu`） |
| sql | ✅ | string | 只读 SQL，长度 ≤ 4000 |
| params | ❌ | object | `:name` 占位符替换字典 |
| expect | ❌ | array | 期望行数组（按顺序逐行逐字段比对） |
| rowCount | ❌ | integer | 期望返回行数 |
| jsonPath | ❌ | string | 对第一行做点号路径提取（`$.taskName`） |
| equals | ❌ | any | jsonPath 提取后等于 |
| contains | ❌ | string | jsonPath 提取后字符串包含 |
| timeoutMs | ❌ | integer | CLI 超时，默认 30000，1000~120000 |

### 返回

```json
{
  "dbGroup": "quality_f88",
  "db": "dev-wulanchabu",
  "sql": "SELECT ...",
  "rows": [{"id": 12345, "job_type": 0}],
  "rowCount": 1,
  "matched": true,
  "failures": [],
  "durationMs": 820
}
```

---

## 2. assertAPI — API 精确断言

**通道**：`capture_manager.last_api_entry` 或 `get_api_entry(urlPattern)` / `get_all_api_entries(urlPattern)`

**前置**：前面必须有一个 `waitForAPI`（或页面加载时自然产生的 API 请求已被 capture_manager 抓包）。

### 最小用法

```json
{
  "type": "assertAPI",
  "status": 200,
  "jsonPath": "$.success",
  "equals": true
}
```

### 多维断言（累积失败，全过才 pass）

```json
{
  "type": "assertAPI",
  "urlPattern": "/api/workflow2/link/run",
  "status": 200,
  "jsonPath": "$.data.batchId",
  "valueType": "string",
  "matches": "^BT_\\d+$",
  "maxDurationMs": 5000
}
```

### 批量断言（captureAll）

```json
{
  "type": "assertAPI",
  "urlPattern": "/api/afd/review/task/main/list",
  "captureAll": true,
  "status": 200
}
```

`captureAll=true` 时，同一 urlPattern 的所有已抓 entry 都检查一遍 status，`matchedCount` 返回数量。

### 全字段对照

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| urlPattern | ❌ | string | URL 关键词过滤；空则取 last_api_entry |
| status | ❌ | integer | 期望 HTTP 状态码 |
| jsonPath | ❌ | string | 点号路径提取（`$.data.success`） |
| equals | ❌ | any | jsonPath 提取后等于（支持 string/number/bool/null） |
| contains | ❌ | string | 响应体字符串化后包含 |
| matches | ❌ | string | 正则字符串，匹配响应体字符串化结果 |
| valueType | ❌ | string | 类型断言（string/number/boolean/array/object/null） |
| maxDurationMs | ❌ | integer | 响应耗时上限 |
| captureAll | ❌ | boolean | 默认 false；true 时取全部匹配 entry |
| expectAll | ❌ | array | captureAll=true 时对每个 entry 做子断言 |

### 返回

```json
{
  "url": "https://x/api/workflow2/link/run",
  "status": 200,
  "jsonPathValue": "BT_12345",
  "durationMs": 482,
  "pass": true,
  "failures": [],
  "matchedCount": 1
}
```

---

## 3. assertUI — UI 属性断言

**通道**：CDP evaluate 注入 JS（`document.querySelectorAll` + 属性/CSS/文本检查）

**元素等待**：`timeoutMs` 默认 5000ms，0.2s 轮询直到 selector 匹配到元素或超时。

### 最小用法

```json
{
  "type": "assertUI",
  "selector": "button.ant-btn-primary",
  "visible": true
}
```

### 多维断言

```json
{
  "type": "assertUI",
  "selector": ".ant-modal-confirm-btns button.ant-btn-primary",
  "visible": true,
  "enabled": true,
  "text": "确认",
  "attribute": {"name": "type", "equals": "button"},
  "cssProperty": {"name": "backgroundColor", "equals": "rgb(24, 144, 255)"}
}
```

### 计数 + 范围

```json
{
  "type": "assertUI",
  "selector": "tr.ant-table-row",
  "count": 10
}
// 或
{
  "type": "assertUI",
  "selector": "tr.ant-table-row",
  "minCount": 1,
  "maxCount": 50
}
```

### 全字段对照

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| selector | ✅ | string | CSS 选择器，长度 ≤ 1000 |
| visible | ❌ | boolean | true=至少一个匹配元素可见 |
| hidden | ❌ | boolean | true=所有匹配元素都不可见 |
| disabled | ❌ | boolean | true=第一个元素 disabled/aria-disabled=true |
| enabled | ❌ | boolean | true=第一个元素可交互 |
| text | ❌ | string | 第一个元素 textContent 完全等于 |
| textContains | ❌ | string | textContent 包含 |
| textMatches | ❌ | string | 正则字符串匹配 textContent |
| count | ❌ | integer | 匹配元素个数断言 |
| minCount | ❌ | integer | 个数下限 |
| maxCount | ❌ | integer | 个数上限 |
| attribute | ❌ | object | `{name, equals\|contains\|exists}` |
| cssProperty | ❌ | object | `{name, equals}` |
| timeoutMs | ❌ | integer | 等待超时，默认 5000，0~30000 |

### 返回

```json
{
  "selector": "button.ant-btn-primary",
  "checked": {"visible": true, "text": "试运行"},
  "pass": true,
  "failures": [],
  "matchCount": 1,
  "firstElementText": "试运行",
  "domSnippet": "<button class=\"ant-btn ant-btn-primary\" type=\"button\">试运行</button>"
}
```

---

## 断言组合模式

用例经常把三种断言组合在同一步骤链里：

```
navigate → waitForAPI → assertUI（按钮可见）
  → click → waitForAPI → assertAPI（接口返回 success + 耗时）
  → dbAssert（DB 已落库）→ screenshot（证据）
```

示例：[TC-AUDIT-DB-001-审核主任务DB断言.json](../eval/cases/f88-test/审核管理/TC-AUDIT-DB-001-审核主任务DB断言.json) 与 [TC-TRIAL-API-001-试运行API断言.json](../eval/cases/f88-test/上游素材生产链路/主图链路/TC-TRIAL-API-001-试运行API断言.json)。

## 易踩的坑

1. **dbAssert 必须先调 waitForAPI**：bridge 是同步 spawn，如果 SQL 里用了 `:id` 占位符想从前面步骤取，得先用 `evaluate + storeAs` 存，然后手动把 store 值传到 params。变量引用机制目前不在 dbAssert 内做。
2. **assertAPI 的 urlPattern 是「包含」匹配**：`urlPattern: "list"` 会同时命中 `main/list` 和 `sub/list`，写 pattern 要够具体。
3. **assertUI 的 selector 转义**：选择器中的单引号会被 JS 侧自动 `\'` 转义，不需要自己处理；双引号同理。
4. **jsonPath 的 `$` 前缀可选**：`$.data.success` 与 `data.success` 等价。
5. **captureAll=true 时每个 entry 都会跑一遍全部断言**：如果只想验证"至少一个成功"，不要用 captureAll，改用 assertStore 配 evaluate 自定义逻辑。

## 单测覆盖

| 文件 | 覆盖 |
|---|---|
| [tests/test_assertion_framework.py](../tests/test_assertion_framework.py) | `check_sql_readonly` / `resolve_json_path` / `assert_value` |
| [tests/test_capture_manager.py](../tests/test_capture_manager.py) | `get_all_api_entries` |
| [tests/test_dms_alibaba_bridge.test.js](../tests/test_dms_alibaba_bridge.test.js) | bridge 的 parseArgs / applyParams / parseOutput |
| [tests/test_step_executor_new_handlers.py](../tests/test_step_executor_new_handlers.py) | 三个新 handler 的全部分支 |

## 不做的事（二期）

- `assertNetwork`（断言网络请求次数 / 请求体）
- JS 箭头函数 → Python 转换升级（`?.` / `??` / `Array.isArray`）
- 软断言聚合（assert 失败不立即停）
- VRT baseline 持久化跨用例 diff
- 响应 schema 验证（OpenAPI schema）
