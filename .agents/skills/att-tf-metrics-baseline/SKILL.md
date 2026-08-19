---
name: att-tf-metrics-baseline
description: 从 ~/.att-tf/cases/ 历史测试数据中提取度量基线报告。按会话、业务域、优先级统计 PASS/FAIL/SKIP 分布，分类 FAIL 根因，生成 Markdown 基线报告，用于迭代间质量改进对比基准。当用户说"度量基线"、"测试基线报告"、"att-tf 历史数据统计"、"质量度量"、"PASS/FAIL 统计"、"失败根因分析"、"baseline"、"metrics baseline"时触发。
version: 1.0.0
---

# att-tf 度量基线采集

> 一句话：扫描 `~/.att-tf/cases/` 全部会话数据，按会话/业务域/优先级/根因四维度聚合统计，生成 Markdown 基线报告，作为迭代间质量对比的基准锚点。

## 触发条件

以下任一场景触发本技能：

- 用户说"度量基线"、"基线报告"、"baseline"、"metrics baseline"
- 用户说"测试数据统计"、"历史测试数据"、"PASS/FAIL 统计"
- 用户说"失败根因分析"、"FAIL 分类"、"质量度量"
- 用户说"att-tf 数据汇总"、"cases 统计"
- 用户要求对比不同迭代的测试质量变化

## 数据源

### 目录结构

```
~/.att-tf/cases/
  ├── {session-id-1}/
  │   ├── cases.json       # 核心数据：用例执行结果
  │   ├── index.txt        # 会话索引（可选）
  │   └── acked.*.json     # att-tf 回执（可选）
  ├── {session-id-2}/
  │   ├── cases.json
  │   └── ...
  └── ...
```

### cases.json 字段定义

每条用例为一个 JSON 对象，关键字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `caseTitle` | string | 用例标题，格式通常为 `TC_{MODULE}_{SEQ} {描述}` |
| `description` | object | 用例描述，含 preconditions / steps / expectedResults |
| `status` | int | 执行结果：**1=PASS, 2=FAIL, 3=SKIP** |
| `priority` | string | 优先级：`P0` / `P1` / `P2` / `P3` |
| `groupPath` | string | 业务域路径，格式 `一级域/二级域`，如 `LLM视频理解/P0核心功能` |
| `errorMessage` | string | FAIL 时的错误信息，是根因分类的核心依据 |
| `seq_from` / `seq_to` | int | 用例序号范围（元数据，统计时忽略） |

### 数据过滤规则

- 跳过没有 `cases.json` 的会话目录
- 跳过 `cases.json` 为空数组或解析失败的会话
- 仅处理 `status` 为 1/2/3 的用例，其他值归入"OTHER"

## 工作流

### Step 1: 扫描与解析

```bash
# 扫描全部会话目录，逐个解析 cases.json
CASES_DIR="$HOME/.att-tf/cases"

python3 << 'PYEOF'
import json, os, sys
from pathlib import Path
from collections import defaultdict

cases_dir = Path.home() / ".att-tf" / "cases"
if not cases_dir.exists():
    print("ERROR: ~/.att-tf/cases/ 不存在", file=sys.stderr)
    sys.exit(1)

all_cases = []
session_meta = []

for session_dir in sorted(cases_dir.iterdir()):
    if not session_dir.is_dir():
        continue
    cases_file = session_dir / "cases.json"
    if not cases_file.exists():
        continue
    try:
        cases = json.loads(cases_file.read_text())
        if not cases:
            continue
    except (json.JSONDecodeError, Exception):
        continue

    session_id = session_dir.name
    session_meta.append({
        "session_id": session_id,
        "case_count": len(cases)
    })
    for c in cases:
        c["_session"] = session_id
        all_cases.append(c)

print(f"已解析: {len(session_meta)} 个会话, {len(all_cases)} 条用例")
PYEOF
```

### Step 2: 多维统计

对全部用例按以下四个维度聚合：

#### 维度 A：会话维度

按 session 聚合，每个会话统计 PASS / FAIL / SKIP 数量与通过率。

```
通过率 = PASS / (PASS + FAIL + SKIP) × 100%
```

#### 维度 B：业务域维度

从 `groupPath` 提取一级域名（`/` 前部分），按域聚合。

```python
domain = groupPath.split('/')[0] if '/' in groupPath else groupPath
```

每个域输出：总用例数、PASS 数、FAIL 数、SKIP 数、通过率。

#### 维度 C：优先级维度

按 P0/P1/P2/P3 分层统计，关注高优先级用例的通过率是否达标。

#### 维度 D：FAIL 根因分类

仅对 status=2 的用例，从 `errorMessage` 提取关键词进行根因归类。分类规则见下方「FAIL 根因分类规则」。

### Step 3: 基线报告生成

生成 Markdown 文件，保存至工作目录：

```
输出路径: {workspace}/outputs/metrics-baseline-{YYYY-MM-DD}.md
```

报告包含以下章节（Markdown 模板见下方「报告模板」）：

1. **总览摘要** — 总会话数、总用例数、整体 PASS/FAIL/SKIP 数与占比、整体通过率
2. **会话明细表** — 每会话一行：会话 ID（截断前8位）、用例数、PASS/FAIL/SKIP、通过率
3. **业务域统计表** — 每域一行：域名、用例数、PASS/FAIL/SKIP、通过率、FAIL 占比
4. **优先级统计表** — 每优先级一行：用例数、PASS/FAIL/SKIP、通过率
5. **FAIL 根因分类表** — 每类根因：FAIL 数、占比、典型 errorMessage 摘录
6. **Top-N 高频失败模式** — 按 FAIL 频次降序，取前 10 条具体 errorMessage

### Step 4: 对比模式（可选）

当用户提供了上一期基线文件路径时，生成 delta 对比报告：

```
输入: --compare {上一期基线 .md 文件路径}
```

对比内容：
- 整体通过率变化（↑/↓/→）
- 新增 FAIL 模式（本期有、上期无）
- 改善域（通过率上升）与退化域（通过率下降）
- 优先级维度变化

如用户未提供对比文件，仅生成单期基线报告。

## FAIL 根因分类规则

从 `errorMessage` 中按以下关键词规则分类。匹配优先级从上到下，命中即停。

| 根因类别 | 匹配关键词（正则/子串，不区分大小写） | 说明 |
|----------|--------------------------------------|------|
| **环境问题** | `timeout`、`connection`、`502`、`503`、`500`、`网络`、`偶发`、`环境`、`pre-prod`、`预发`、`refused`、`ECONNRESET` | 环境不稳定或网络问题导致的非代码失败 |
| **脚本/配置问题** | `ImportError`、`ModuleNotFoundError`、`fixture`、`conftest`、`SyntaxError`、`NameError`、`assert`、`断言失败` | 测试脚本本身的问题 |
| **真实 Bug** | `Bug`、`bug`、`不符合预期`、`不一致`、`缺失`、`不存在`、`未实现`、`功能异常`、`逻辑错误`、`未校验`、`未拦截` | 被测系统确实存在的缺陷 |
| **数据问题** | `数据`、`为空`、`null`、`empty`、`mock`、`测试数据`、`数据不一致` | 测试数据准备不足或数据不一致 |
| **权限/校验问题** | `权限`、`permission`、`auth`、`校验`、`未通过`、`拦截`、`forbidden` | 权限控制或参数校验相关 |
| **其他** | 以上均未命中 | 无法归类的失败 |

**注意**：分类为近似启发式，报告末尾需注明"根因分类基于 errorMessage 关键词匹配，仅供参考，人工复核后使用"。

## 报告模板

以下为生成的 Markdown 报告结构：

```markdown
# att-tf 度量基线报告

> 生成时间: {YYYY-MM-DD HH:mm}
> 数据范围: {N_sessions} 个会话
> 用例总数: {M} 条

## 1. 总览摘要

| 指标 | 数值 |
|------|------|
| 总会话数 | {sessions} |
| 总用例数 | {total} |
| PASS | {pass_count} ({pass_pct}%) |
| FAIL | {fail_count} ({fail_pct}%) |
| SKIP | {skip_count} ({skip_pct}%) |
| **整体通过率** | **{pass_rate}%** |

## 2. 会话明细

| 会话 | 用例数 | PASS | FAIL | SKIP | 通过率 |
|------|--------|------|------|------|--------|
| {session_id[:8]}... | {count} | {pass} | {fail} | {skip} | {rate}% |

## 3. 业务域统计

| 业务域 | 用例数 | PASS | FAIL | SKIP | 通过率 | FAIL 占比 |
|--------|--------|------|------|------|--------|-----------|
| {domain} | {count} | {pass} | {fail} | {skip} | {rate}% | {fail_pct}% |

## 4. 优先级统计

| 优先级 | 用例数 | PASS | FAIL | SKIP | 通过率 |
|--------|--------|------|------|------|--------|
| P0 | {count} | {pass} | {fail} | {skip} | {rate}% |
| P1 | ... | ... | ... | ... | ... |
| P2 | ... | ... | ... | ... | ... |
| P3 | ... | ... | ... | ... | ... |

## 5. FAIL 根因分类

| 根因类别 | FAIL 数 | 占比 | 典型 errorMessage |
|----------|---------|------|-------------------|
| 环境问题 | {n} | {pct}% | "{excerpt}" |
| 脚本/配置问题 | {n} | {pct}% | "{excerpt}" |
| 真实 Bug | {n} | {pct}% | "{excerpt}" |
| 数据问题 | {n} | {pct}% | "{excerpt}" |
| 权限/校验问题 | {n} | {pct}% | "{excerpt}" |
| 其他 | {n} | {pct}% | "{excerpt}" |

> 根因分类基于 errorMessage 关键词匹配，仅供参考，建议人工复核后使用。

## 6. Top-10 高频失败模式

| # | errorMessage (截断前80字符) | 出现次数 |
|---|---------------------------|----------|
| 1 | {msg} | {count} |

## 7. 对比 delta（仅对比模式）

| 维度 | 上期 | 本期 | 变化 |
|------|------|------|------|
| 整体通过率 | {old}% | {new}% | {delta} |
| P0 通过率 | ... | ... | ... |

### 新增 FAIL 模式
- {new_fail_pattern}

### 退化域（通过率下降）
- {domain}: {old}% → {new}%

### 改善域（通过率上升）
- {domain}: {old}% → {new}%

---

*本报告由 att-tf-metrics-baseline 技能自动生成。*
```

## 执行方式

本技能全部逻辑使用 **Bash + 内联 Python3** 实现，不依赖外部包，不需要独立脚本文件。

Agent 执行时按以下约束自行编写 Python 脚本：

1. **数据源**: `~/.att-tf/cases/*/cases.json`
2. **status 映射**: `{1: "PASS", 2: "FAIL", 3: "SKIP"}`
3. **domain 提取**: `groupPath.split('/')[0]`，缺失时归入"未分类"
4. **FAIL 根因分类**: 按上述规则表匹配 errorMessage，不区分大小写
5. **输出格式**: Markdown，严格遵循上述报告模板
6. **保存路径**: `{workspace}/outputs/metrics-baseline-{YYYY-MM-DD}.md`
7. **Python 依赖**: 仅标准库（json, os, re, collections, datetime），零外部依赖

## 注意事项与坑点

1. **session 目录名是 UUID 或 hash**：不含时间信息。报告中的"数据范围"如无时间戳则仅展示会话数量。

2. **cases.json 可能为空数组**：`[]` 是合法的 JSON，需跳过而非报错。

3. **groupPath 可能为空或缺失**：归入"未分类"域。

4. **errorMessage 可能是多行文本**：截取前 80 字符作为"典型摘录"，报告表格中避免过宽。

5. **同一 errorMessage 可能跨多条用例重复出现**：Top-N 统计需先去重计数（相同 errorMessage 合并）。

6. **对比模式依赖上期报告格式一致**：如果用户提供的上期文件不是本技能生成的，需提示格式不匹配并建议重新生成上期基线。

7. **Python 内联脚本不依赖第三方包**：仅使用标准库（json, os, re, collections, datetime），确保零依赖可运行。

8. **errorMessage 中文/英文混合**：关键词匹配需同时覆盖中英文，使用 `re.IGNORECASE`。
