---
name: pytest-to-bug-draft-pipeline
description: "pytest 执行 → att-tf cases.json 转换 → Bug 草稿自动生成的闭环流水线。当用户需要执行已有 pytest 脚本并自动串联自愈重试、att-tf 证据采集和缺陷初判提报时使用。触发词：跑用例并提 bug、执行并生成缺陷、闭环验证、pytest to bug、执行转 bug 草稿、跑完自动提报、串联执行和缺陷。"
version: 1.0.0
---

# Pytest → Bug 草稿闭环流水线

> 一句话：把 pytest 执行结果自动转换为 att-tf cases.json，再经规则引擎初判生成 Bug 草稿，实现"执行→分类→提报"零人工闭环。

## 触发条件

- 用户说"跑一下用例"、"执行 pytest 并提 bug"、"闭环验证"
- 用户已有一批 pytest 脚本（遵循本 Skill 约定的 docstring/marker 规范），需要串联执行和缺陷提报
- 用户说"串联执行和缺陷"、"pytest to bug"、"跑完自动提报"
- 其他 Skill（如 PRD用例生成）产出 pytest 脚本后，需要后续闭环

## 前置依赖：pytest 脚本规范

流水线要求 pytest 脚本遵循以下约定，否则转换阶段会丢失关键信息。

### docstring 约定

```python
class Test首图生图_API:
    """Module: 首图生图"""  # ← class docstring = groupPath 来源

    def test_tc_firstimage_001_normal(self):
        """TC_firstimage_001: 正常生图请求返回成功"""  # ← function docstring 第一行
        ...
```

| 位置 | 格式 | 转换目标 |
|------|------|----------|
| class docstring | `Module: {groupPath}` | cases.json 的 `groupPath` 字段 |
| function docstring 第一行 | `TC_{ID}: {caseTitle}` | cases.json 的 `caseTitle` 字段 |
| function 命名 | `test_tc_{module}_{seq}_{scenario}` | docstring 缺失时的回退解析 |

### marker 约定

```python
@pytest.mark.p0   # → priority: P0（冒烟/核心链路）
@pytest.mark.p1   # → priority: P1（重要功能）
@pytest.mark.p2   # → priority: P2（一般功能，默认值）
@pytest.mark.p3   # → priority: P3（低优先级/探索性）
```

未标注 marker 时默认 P2。

### 测试策略：四链证据标准（红线）

执行过程 + 测试报告必须同时涵盖四条证据链：①页面 UI 实际操作（预发环境真实执行）②每步关键操作 UI 截图留证 ③API 接口返回数据断言 ④DB 实际落库字段核对。缺一即不合格，禁止编造未执行的验证步骤。

```python
class Test某模块_API:
    """Module: 某模块/接口验证"""
    # 用 requests/HTTP 做接口断言

class Test某模块_UI:
    """Module: 某模块/UI验证"""
    # 接收 page fixture 做 Playwright 页面级验证
    # docstring 末尾标 [UI]
```

判定规则：能用接口断言的一律走接口；只有页面渲染、前端交互时序、纯前端状态三类场景才走 UI。

### status 映射

| pytest 结果 | cases.json status |
|-------------|-------------------|
| passed | 1 |
| failed | 2 |
| skipped | 3 |

## 流水线步骤

### Step 0: 部署 conftest（自愈引擎）

根据用例类型选择对应的 conftest 文件：

```bash
# 纯接口测试（所有用例都不含 [UI] 标记、无 page fixture）
cp {prd_skill_dir}/scripts/conftest_self_heal.py {pytest_dir}/conftest.py

# 含 UI 测试（有用例标注 [UI] 或 test class 名含 _UI 或含 page fixture）
cp {prd_skill_dir}/scripts/conftest_ui_self_heal.py {pytest_dir}/conftest.py
```

**选择逻辑**：扫描 pytest 脚本中是否有 `page` fixture 参数或 `[UI]` 标记。有则用 UI 版，否则用通用版。两者不冲突——UI 版在无 `page` fixture 时静默跳过浏览器级自愈。

**脚本来源**：`PRD用例生成/scripts/conftest_self_heal.py`（306行，通用 H1-H5）和 `PRD用例生成/scripts/conftest_ui_self_heal.py`（454行，H1-H9 + Playwright 级自愈 + UISelfHealHelper）。

### Step 1: 执行 pytest

```bash
cd {pytest_dir}
python3 -m pytest --json-report --json-report-file=results.json -v --tb=short
```

**必须参数**：
- `--json-report` — 启用 pytest-json-report 插件
- `--json-report-file=results.json` — 输出 JSON 结果文件

**自愈行为**：conftest 会在每条用例失败时实时判断是否可自愈（H1-H9 规则），满足条件则当场恢复+重试，无需跑完再二次分析。自愈通过的用例最终状态为 passed，并携带 `self_heal_rule` 和 `retry_healed: True` 标记。

### Step 2: 转换 cases.json

```bash
python3 {prd_skill_dir}/scripts/pytest_to_cases.py results.json cases.json
```

**脚本来源**：`PRD用例生成/scripts/pytest_to_cases.py`（131行）

**转换逻辑**：
1. 读取 pytest-json-report 的 JSON 输出
2. 遍历每条 test，从 docstring/nodeid 解析 caseTitle、groupPath、priority
3. 按 status 映射（passed→1, failed→2, skipped→3）写入 cases.json

### Step 3: att-tf 测试会话声明

调用 `/att-start` 声明测试会话，登记 aoneId（需求 ID）并开启采证。

> **注意**：att-start 只登记身份和采证配置，不接管测试流程。声明后回到本管线继续执行后续步骤。

### Step 4: 规则初判（失败分类）

```bash
python3 {bug_drafter_dir}/scripts/bug_drafter.py --analyze cases.json analysis.json
```

**脚本来源**：`f88-bug-drafter/scripts/bug_drafter.py`（530行）

**输出**：`analysis.json` 包含每条失败用例的分类结果和重试计划。

**分类体系**（三层优先级）：

| 优先级 | 分类 | 含义 | 后续动作 |
|--------|------|------|----------|
| 1（最高） | SELF_HEAL | 匹配 H1-H9 自愈规则 | 生成重试命令，跑 `--merge` 合并 |
| 2 | BUG | 匹配 R1-R6 缺陷规则 | 进入 Step 5 生成 Bug 草稿 |
| 2 | SCRIPT_FIX | 脚本/配置问题 | 修复后重跑，不提 Bug |
| 2 | SKIP | 环境依赖/前置条件不满足 | 标记跳过 |
| 3（最低） | UNKNOWN | 不匹配任何规则 | 需人工判定 |

**SELF_HEAL 后续处理**：
```bash
# 用 analysis.json 中的重试命令重跑失败用例
cd {pytest_dir} && python3 -m pytest --json-report --json-report-file=retry_results.json -v -k "{retry_selector}"

# 合并重试结果
python3 {bug_drafter_dir}/scripts/bug_drafter.py --merge cases.json retry_results.json cases_merged.json
```

### Step 5: 生成 Bug 草稿

```bash
python3 {bug_drafter_dir}/scripts/bug_drafter.py cases.json bug_drafts.json --analysis analysis.json
```

**过滤逻辑**：仅对 BUG 类失败用例生成草稿，自动排除 SELF_HEAL / SCRIPT_FIX / SKIP 类。

**草稿内容**（每条 Bug）：
- `caseTitle` — 用例标题
- `groupPath` — 模块路径
- `priority` — 优先级（P0-P3）
- `description` — Markdown 格式的复现步骤 + 预期结果 + 实际结果
- `errorMessage` — 原始错误信息
- `moduleOwner` — 模块负责人（从 MODULE_OWNERS 映射表查询）

## 失败分类规则速查

### SELF_HEAL 自愈规则（H1-H9）

| ID | 名称 | 错误模式 | 动作 |
|----|------|----------|------|
| H1 | 限流 429 | `429`, `Too Many Requests`, `rate limit` | 等 5s 重试 ×3 |
| H2 | 超时 | `timeout`, `TimeoutError`, `timed out` | 等 3s 重试 ×2 |
| H3 | 数据未就绪 | `data not ready`, `not yet available`, `processing` | 等 5s 重试 ×3 |
| H4 | 环境抖动 | `ConnectionError`, `ConnectionReset`, `ECONNREFUSED` | 等 3s 重试 ×2 |
| H5 | 脚本/配置问题 | `ImportError`, `ModuleNotFoundError`, `fixture not found` | 等 1s 重试 ×1 |
| H6 | 元素漂移（UI） | `strict mode violation`, `not visible`, `element has been detached` | 等 2s + reload/scrollIntoView ×2 |
| H7 | 焦点抢占（UI） | `intercepts pointer`, `other element would receive` | 等 1s + 移除遮挡层 ×2 |
| H8 | 弹窗遮挡（UI） | `modal`, `dialog`, `alert`, `beforeunload` | 等 1s + dismiss dialog ×2 |
| H9 | 页面未稳定（UI） | `animating`, `still loading`, `networkidle` | 等 3s + wait stable ×2 |

### BUG 缺陷规则（R1-R6）

| ID | 名称 | 错误模式 |
|----|------|----------|
| R1 | 校验缺失 | `AssertionError`, `assert`, `expected`, `实际` |
| R2 | 接口异常 | `HTTPError`, `status_code`, `response`, `500`, `502`, `503` |
| R3 | 数据不一致 | `数据不一致`, `数量不符`, `字段缺失`, `状态异常` |
| R4 | 环境问题 | `环境问题`, `配置错误`, `权限不足` |
| R5 | 已知问题 | `已知问题`, `已有 bug`, `duplicate` |
| R6 | UI 缺陷 | `文案不一致`, `按钮不存在`, `样式异常`, `布局错乱` |

## 管线数据流图

```
pytest 脚本 (.py)
    │
    ├── [Step 0] 部署 conftest.py（自愈引擎）
    │
    ├── [Step 1] pytest 执行
    │       └─ 自愈重试（H1-H9 实时判定）
    │       └─ 输出: results.json
    │
    ├── [Step 2] pytest_to_cases.py 转换
    │       └─ 解析 docstring/marker → caseTitle/groupPath/priority
    │       └─ 输出: cases.json（att-tf 格式）
    │
    ├── [Step 3] att-tf 声明（/att-start）
    │       └─ 登记 aoneId + 开启采证
    │
    ├── [Step 4] bug_drafter.py --analyze
    │       └─ 三层分类: SELF_HEAL > BUG/SCRIPT_FIX/SKIP > UNKNOWN
    │       └─ SELF_HEAL → 生成重试命令 → 重跑 → --merge 合并
    │       └─ 输出: analysis.json
    │
    └── [Step 5] bug_drafter.py 生成草稿
            └─ 仅 BUG 类 → Markdown 复现步骤 + 预期/实际结果
            └─ 输出: bug_drafts.json
```

## 常见坑点（Lessons Learned）

### 坑点 1：docstring 丢失

**现象**：pytest 执行后 cases.json 中 caseTitle 全部变成 nodeid 解析的函数名，原始用例标题丢失。

**根因**：conftest.py 覆盖了 pytest 默认的 report 生成，导致 docstring 未被传递到 pytest-json-report 的 user_properties。

**解法**：确保 conftest.py 中包含 `pytest_collection_modifyitems` hook，将 docstring 注入 `item.user_properties`：
```python
def pytest_collection_modifyitems(items):
    for item in items:
        doc = item.obj.__doc__ or ""
        item.user_properties.append(("docstring", doc))
```

### 坑点 2：JSON 结构假设错误

**现象**：pytest_to_cases.py 报错 `KeyError: 'tests'` 或转换结果为空。

**根因**：pytest-json-report 的 JSON 顶层结构为 `{"tests": [...]}` 而非 `{"reports": [...]}`，早期版本脚本误用了错误字段名。

**解法**：使用当前版本的 pytest_to_cases.py（已修正），它读取 `data["tests"]` 字段。

### 坑点 3：conftest 命名冲突

**现象**：部署 conftest.py 后 pytest 报错 `conftest.py not found` 或自愈逻辑不生效。

**根因**：文件未正确重命名为 `conftest.py`（小写），或放置目录不在 pytest 搜索路径中。

**解法**：文件必须命名为 `conftest.py`（不能是 `conftest_self_heal.py`），且放置在 pytest 执行目录的根级别。

### 坑点 4：UI 版 conftest 对纯接口测试产生干扰

**现象**：纯接口测试用例出现 `page fixture not found` 错误。

**根因**：错误地选择了 UI 版 conftest，而接口测试没有安装 pytest-playwright。

**解法**：严格按 Step 0 的选择逻辑判断——只有含 `page` fixture 或 `[UI]` 标记的用例才使用 UI 版。UI 版的 `_ui_heal_before_retry` 在无 `page` fixture 时会静默跳过（`item.funcargs.get("page")` 返回 None），但前提是 pytest-playwright 已安装。

## 验证步骤

完成管线搭建后，按以下步骤验证全链路：

1. **准备最小用例集**：编写 2-3 条 pytest 用例（1 条 pass、1 条 fail + 匹配 R1、1 条 fail + 匹配 H2）
2. **执行 Step 0-1**：部署 conftest + 跑 pytest，确认 results.json 生成且自愈用例标记了 `retry_healed`
3. **执行 Step 2**：运行 pytest_to_cases.py，检查 cases.json 中 caseTitle/groupPath/priority 是否正确解析
4. **执行 Step 4**：运行 `--analyze`，确认分类结果（pass 的不出现、H2 匹配 SELF_HEAL、R1 匹配 BUG）
5. **执行 Step 5**：生成 bug_drafts.json，确认仅 BUG 类用例出现且 description 格式正确

## 脚本来源索引

| 脚本 | 路径 | 行数 |
|------|------|------|
| conftest_self_heal.py | `PRD用例生成/scripts/` | 306 |
| conftest_ui_self_heal.py | `PRD用例生成/scripts/` | 454 |
| pytest_to_cases.py | `PRD用例生成/scripts/` | 131 |
| bug_drafter.py | `f88-bug-drafter/scripts/` | 530 |

所有脚本均位于 `~/.qoderwork/plugins-custom/qa-testing-workbench/skills/` 下对应 Skill 的 `scripts/` 目录中。
