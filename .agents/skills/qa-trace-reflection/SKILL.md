---
name: qa-trace-reflection
description: QA 执行轨迹自动复盘与 skill 进化提案生成器。每日定时采集 att-tf 采证记录、gap-guardian 审计台账、edit-history 编辑追踪，从失败和成功两个维度分析执行轨迹，评估 skill 编辑影响，产出结构化改进提案。对标 SkillOpt 的 Reflection + Validation Gate 机制。触发词：每日复盘、轨迹分析、执行复盘、trace reflection、编辑影响评估、daily reflection、skill 进化分析。
version: 1.0.0
---

# qa-trace-reflection — 每日执行轨迹自动复盘

**定位**：qa-gap-guardian 的"被动模式"。gap-guardian 是用户主动触发的实时复盘（单会话粒度），本 skill 是每日定时的批量复盘（跨会话聚合）。两者共享 `pending-review/` 输出目录和编辑影响追踪协议。

**对标 SkillOpt**：
- Reflection（反思）：从成功/失败轨迹中提取可复用的过程性知识
- Validation Gate（验证门控）：评估已有 skill 编辑的实际效果
- Slow Update（慢速整合）：跨天累积数据，发现趋势性模式

## 数据源

| 数据源 | 路径 | 采集内容 |
|--------|------|----------|
| att-tf 采证记录 | `~/.att-tf/cases/{date}.jsonl` | 用例执行结果（PASS/FAIL/SKIP/BLOCKED）、错误信息、执行日志 |
| gap-guardian 审计台账 | `~/.qoderwork/gap-guardian/ledger/{date}.jsonl` | gap 判定、分类（G1-G9）、证据、修复动作 |
| gap-guardian 修复记录 | `~/.qoderwork/gap-guardian/ledger/fixes.jsonl` | T1/T2 修复动作、备份路径 |
| 编辑影响追踪 | `~/.qoderwork/gap-guardian/edit-history/edit-history.jsonl` | before/after snippet、影响评估（assessed: true/false） |
| 已知失败方案 | `~/.qoderwork/skills/qa-self-healing/references/rejected-approaches.jsonl` | 负反馈记录、times_tried 变化 |

## 工作流（五步）

### Step 1：采集当日执行轨迹

```bash
# 1a. att-tf 采证记录
# 真实存储格式：~/.att-tf/cases/{session-uuid}/cases.json（JSON 数组）
# status 为数字：1=PASS 2=FAIL 3=SKIP；会话归属日期按 cases.json 的 mtime 判定
# 支持 REFLECT_DATE=YYYY-MM-DD 环境变量补跑历史日期
python3 -c "
import os, json
from datetime import datetime

target = os.environ.get('REFLECT_DATE') or datetime.now().strftime('%Y-%m-%d')
base = os.path.expanduser('~/.att-tf/cases')
STATUS_MAP = {0: 'PENDING', 1: 'PASS', 2: 'FAIL', 3: 'SKIP'}

all_cases = []
session_ids = set()
for d in sorted(os.listdir(base)):
    cj = os.path.join(base, d, 'cases.json')
    if not os.path.isfile(cj):
        continue
    mdate = datetime.fromtimestamp(os.path.getmtime(cj)).strftime('%Y-%m-%d')
    if mdate != target:
        continue
    try:
        with open(cj) as f:
            cases = json.load(f)
    except (json.JSONDecodeError, OSError):
        continue
    for c in cases:
        c['_session'] = d
        c['_status_str'] = STATUS_MAP.get(c.get('status'), 'UNKNOWN')
    all_cases.extend(cases)
    session_ids.add(d)

print(f'目标日期: {target} | 会话数: {len(session_ids)} | 用例总数: {len(all_cases)}')
stats = {}
for c in all_cases:
    stats[c['_status_str']] = stats.get(c['_status_str'], 0) + 1
for s, n in sorted(stats.items()):
    print(f'  {s}: {n}')
# 输出 FAIL/SKIP 用例摘要
for c in all_cases:
    if c['_status_str'] in ('FAIL', 'SKIP'):
        print(f\"  [{c['_status_str']}] {c.get('caseTitle','')} | {str(c.get('errorMessage',''))[:100]}\")
if not all_cases:
    print('当日无采证记录（无测试会话或 cases.json 未更新）')
"

# 1b. gap-guardian 审计台账
cat ~/.qoderwork/gap-guardian/ledger/$(date +%Y-%m-%d).jsonl 2>/dev/null | wc -l
# 有内容时解析 gap 分类分布

# 1c. 编辑影响追踪（未评估的编辑）
cat ~/.qoderwork/gap-guardian/edit-history/edit-history.jsonl 2>/dev/null | python3 -c "
import sys, json
entries = [json.loads(l) for l in sys.stdin if l.strip()]
unassessed = [e for e in entries if not e.get('impact',{}).get('assessed')]
print(f'总编辑记录: {len(entries)}, 未评估: {len(unassessed)}')
for e in unassessed:
    print(f\"  [{e.get('skill','')}] {e.get('gap_id','')} | {e.get('location','')} | {e.get('edit_type','')} | lines={e.get('lines_changed',0)}\")
"
```

**输出**：当日执行概况（用例数/状态分布/gap 数/未评估编辑数），决定是否继续深度分析。

### Step 2：失败轨迹 Reflection（对标 SkillOpt failure minibatch）

对 FAIL/BLOCKED 用例和当日 gap 做聚合分析：

1. **提取失败模式**：从 att-tf 的 FAIL/BLOCKED 用例中提取 errorType（造数失败/验证走不通/环境故障/逻辑限制）和 rootCause
2. **按 errorType 聚合**：至少 2 条同类失败才产出提案（避免轶事式修补——SkillOpt 原文："单条轨迹往往只产出轶事式修补，而 minibatch 能暴露可复用的过程性错误"）
3. **对照 rejected-approaches**：检查失败路径是否已在负反馈库中。如果同一 attempted 路径 times_tried 持续增加但没有 alternative 被采纳 → 说明替代方案没有被执行者使用，需要在 skill 中强化路由
4. **产出 skill patch 提案**：格式为 `{target_skill, action: add|delete|replace, location, proposed_text, rationale, evidence: [gap_ids]}`

### Step 2b：回归防护快照分析（对标 MerchantBench Bench 回归检查点）

> 自愈规则每次变更后都会生成回归快照（由 `healing-regression-check.py` 产出）。本步骤对快照目录做趋势分析，防止"错误复利"——同一规则反复导致回归说明规则本身有缺陷，需要修正而非反复放行。

```bash
# 2b-1. 扫描回归快照目录，统计 verdict 趋势和回归频率
# 数据源：~/.qoderwork/qa-self-healing/regression-snapshots/
# 快照格式：regression-{timestamp}.json，含 verdict/pool_size/regressions[]/block_count/review_count
python3 -c "
import os, json, glob
from collections import defaultdict
from datetime import datetime

snap_dir = os.path.expanduser('~/.qoderwork/qa-self-healing/regression-snapshots')
if not os.path.isdir(snap_dir):
    print('快照目录不存在，跳过回归防护分析')
    exit(0)

files = sorted(glob.glob(os.path.join(snap_dir, '*.json')))
print(f'快照总数: {len(files)}')

# 统计各 verdict 分布 + 按 rule_type 聚合 BLOCK 次数
verdict_counts = defaultdict(int)
block_by_rule_type = defaultdict(int)
total_regressions = 0

for f in files:
    try:
        with open(f) as fh:
            snap = json.load(fh)
    except (json.JSONDecodeError, OSError):
        continue
    verdict = snap.get('verdict', 'UNKNOWN')
    verdict_counts[verdict] += 1
    rule_type = snap.get('rule_type', 'unknown')
    if verdict == 'BLOCK':
        block_by_rule_type[rule_type] += 1
    total_regressions += len(snap.get('regressions', []))

print(f'\\nVerdict 分布: {dict(verdict_counts)}')
print(f'总回归条目: {total_regressions}')

# 告警：有 BLOCK 记录的类型
if block_by_rule_type:
    print(f'\\n⚠ 回归防护告警: 以下 rule_type 曾触发 BLOCK')
    for rt, cnt in sorted(block_by_rule_type.items(), key=lambda x: -x[1]):
        print(f'  [{rt}] BLOCK {cnt} 次')
    print('建议: 这些规则类型可能存在设计缺陷，应转 T2 人工审查而非反复回滚重试')
else:
    print('\\n回归防护正常: 无 BLOCK 记录')

# 最近快照摘要
if files:
    latest = files[-1]
    try:
        with open(latest) as fh:
            snap = json.load(fh)
        print(f'\\n最近快照: {snap.get(\"timestamp\")} | verdict={snap.get(\"verdict\")} | pool={snap.get(\"pool_size\")} 条')
    except (json.JSONDecodeError, OSError):
        pass
"
```

**输出与联动**：

| 发现 | 动作 |
|------|------|
| 某 rule_type 多次 BLOCK | 产出 T2 草案到 `pending-review/`，建议修正规则逻辑而非继续回滚重试 |
| verdict=PASS_REVIEW 累积 ≥3 次 | 提醒用户在下次周审时集中审议 |
| 快照目录为空或无快照 | 说明 `healing-regression-check.py` 未被调用，检查 qa-self-healing Step 6b 和 gap-guardian T1 规则 7 是否生效 |

### Step 3：成功轨迹 Reflection（对标 SkillOpt success minibatch）

对 PASS 用例分析自愈路径的成功模式：

1. **提取成功路径**：从 att-tf 的 PASS 用例的 execLog 中，找到走过自愈（规则零/一/二/三）后成功的案例
2. **高频成功路径（>= 3 次）**：提案沉淀为 qa-self-healing 新规则或示例
3. **低频成功路径（1-2 次）**：追加到 capability-registry.md（正向能力清单）
4. **特别关注**：Step 0（Rejected-Edit Buffer）命中并成功换路的案例 → 验证负反馈库的有效性

### Step 3b：过程审计抽样（对标 SkillOpt SkillCoach）

> "通过最终检查的轨迹并不自动是可复用的技能使用范例——一条轨迹可以在选中干扰技能、跳过既定 SOP、靠不可复用的试错拿到答案的同时通过检查。"

对当日 PASS 用例**抽样 20%** 做过程审计（对标 `qa-adversarial-agent` 的"过程审计"章节）。过程审计不影响用例的 PASS/FAIL 判定，但会标记 `process_warning`。

**抽样方法**：按 caseId 哈希取模 5 == 0 选取（确定性抽样，同一条用例不会有时抽有时不抽）。

```bash
# 3b-1. 提取当日 PASS 用例 + 哈希抽样 20%（适配 att-tf 真实存储格式）
# 数据源：~/.att-tf/cases/{session-uuid}/cases.json（status 数字 1=PASS）
# execLog：从同目录 evidence*.json 的 execOssUrl 下载 gz → 解 gz → 拍平 context.calls 为有序文本
# 支持 REFLECT_DATE=YYYY-MM-DD 环境变量补跑历史日期
python3 -c "
import os, json, hashlib, gzip, urllib.request
from datetime import datetime

target = os.environ.get('REFLECT_DATE') or datetime.now().strftime('%Y-%m-%d')
base = os.path.expanduser('~/.att-tf/cases')

# 1) 遍历目标日期的会话目录，收集 PASS 用例（status==1）
pass_cases = []
for d in sorted(os.listdir(base)):
    cj = os.path.join(base, d, 'cases.json')
    if not os.path.isfile(cj):
        continue
    mdate = datetime.fromtimestamp(os.path.getmtime(cj)).strftime('%Y-%m-%d')
    if mdate != target:
        continue
    try:
        with open(cj) as f:
            cases = json.load(f)
    except (json.JSONDecodeError, OSError):
        continue
    for c in cases:
        if c.get('status') == 1:
            c['_session'] = d
            pass_cases.append(c)

# 2) 确定性抽样：caseTitle 哈希取模 5 == 0
sampled = []
for c in pass_cases:
    cid = c.get('caseTitle') or ''
    h = int(hashlib.md5(cid.encode()).hexdigest(), 16)
    if h % 5 == 0:
        sampled.append(c)

print(f'目标日期: {target} | PASS 用例: {len(pass_cases)}, 抽样: {len(sampled)}')

# 3) execLog 获取：caseTitle -> execOssUrl（扫会话内所有 evidence*.json）
def load_execlog_map(session_dir):
    m = {}
    try:
        fns = os.listdir(session_dir)
    except OSError:
        return m
    for fn in fns:
        if fn.startswith('evidence') and fn.endswith('.json'):
            try:
                with open(os.path.join(session_dir, fn)) as f:
                    ev = json.load(f)
                for ec in ev.get('cases', []):
                    if ec.get('execOssUrl'):
                        m[ec.get('caseTitle', '')] = ec['execOssUrl']
            except (json.JSONDecodeError, OSError):
                pass
    return m

# 4) execLog 拍平：结构化 calls JSON → 按 seq 排序的文本（供模式匹配）
def flatten_execlog(data):
    lines = []
    calls = data.get('context', {}).get('calls', [])
    calls = sorted(calls, key=lambda x: x.get('seq', 0))
    for call in calls:
        name = call.get('name', '')
        inp = call.get('input') or {}
        inp_text = inp.get('preview', '') if isinstance(inp, dict) else str(inp)
        result = call.get('result') or {}
        res_text = result.get('preview', '') if isinstance(result, dict) else ''
        lines.append(f'[{name}] {inp_text} => {res_text}')
    return '\n'.join(lines)

url_cache = {}
for c in sampled:
    sid = c['_session']
    if sid not in url_cache:
        url_cache[sid] = load_execlog_map(os.path.join(base, sid))
    url = url_cache[sid].get(c.get('caseTitle', ''), '')
    log_text, source = '', 'unavailable'
    if url:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
                log_text = flatten_execlog(json.loads(gzip.decompress(resp.read())))
            source = 'oss'
        except Exception:
            source = 'download_failed'
    c['_execLog'] = log_text
    c['_execLog_source'] = source
    print(f'  [SAMPLED] {c.get(\"caseTitle\",\"?\")[:60]} | session={sid[:8]} | execLog={source} len={len(log_text)}')

# 5) 输出抽样结果供后续四维检查消费
if sampled:
    print('---SAMPLED_JSON_START---')
    for c in sampled:
        print(json.dumps({
            'caseId': c.get('caseTitle', ''),
            'groupPath': c.get('groupPath', ''),
            'execLog': c.get('_execLog', '')[:8000],
            'execLog_source': c.get('_execLog_source', ''),
            'errorMessage': c.get('errorMessage', ''),
            'status': 'PASS'
        }, ensure_ascii=False))
    print('---SAMPLED_JSON_END---')
else:
    print('无 PASS 用例可抽样')
"
```

**四维检查**（详见 `qa-adversarial-agent/SKILL.md` 过程审计章节）：

1. **Skill Selection**：是否先查知识库再推理？造数路径是否正确？是否命中 rejected-approaches 仍尝试？
2. **Skill Following**：七步诊断是否按序？CP 门禁是否全过？群消息白名单是否遵守？
3. **Skill Composition**：多 skill 协作时数据传递是否正确？DB 路由是否按前缀规则？
4. **Grounded Reflection**：结论是否有 DB/API 证据？提测前是否验证了部署状态？

```bash
# 3b-1b. 四维过程审计（对 3b-1 抽样出的每条用例做 execLog 模式匹配）
# 输入：3b-1 输出的 SAMPLED_JSON 块（从 stdin 读取）
# 输出：每条用例的四维审计结果 JSON
python3 -c "
import sys, json, re

# ---- 信号词定义 ----
# Skill Selection 信号
KB_QUERY_PATTERNS = [r'知识库', r'kbase', r'F88测试知识库', r'knowledge.?base', r'知识库搜索', r'查知识库']
REJECTED_BUF_PATTERNS = [r'rejected.?approaches', r'负反馈库', r'已知失败方案']
NEGATION_PREFIXES = [r'未查询', r'未读取', r'未检查', r'跳过', r'未访问', r'未查看', r'没有查询', r'没有读取', r'未.*rejected', r'跳过.*rejected']
DATA_CREATE_ORDER = {
    'strategy_test_run': [r'策略试运行', r'strategy.?test.?run', r'f88-strategy-test-run'],
    'manual_api': [r'手动创建API', r'manual.?create', r'f88-review-task-create'],
    'db_direct': [r'DB直操', r'DB直接', r'INSERT INTO', r'UPDATE.*SET'],
}

# Skill Following 信号
STEP_MARKERS = [r'Step 0', r'Step 1', r'Step 2', r'Step 3', r'Step 4', r'Step 5', r'Step 6']
CP_MARKERS = [r'CP0', r'CP1', r'CP2', r'CP3', r'CP4']
GROUP_MSG_VIOLATION = [r'发送.*群消息', r'推送到群', r'群聊发送', r'send.*group']

# Skill Composition 信号
DB_PREFIX_RULES = {
    'f88_': 'scenario',
    'g_afd_': 'stylespot',
    'g_workflow_': 'stylespot',
}

# Grounded Reflection 信号
EVIDENCE_PATTERNS = [r'SELECT\b', r'查询结果', r'API.*response', r'接口返回', r'数据库.*显示', r'页面.*截图', r'screenshotPath']
DEPLOY_CHECK = [r'部署.*确认', r'代码.*部署', r'发布.*状态', r'环境.*就绪', r'版本.*确认']

def check_dimension(execLog, patterns):
    return any(re.search(p, execLog, re.IGNORECASE) for p in patterns)

def find_positions(execLog, patterns):
    positions = []
    for p in patterns:
        m = re.search(p, execLog, re.IGNORECASE)
        if m:
            positions.append(m.start())
    return positions

def audit_case(case):
    log = case.get('execLog', '')
    cid = case.get('caseId', '?')
    warnings = []

    # --- Dimension 1: Skill Selection ---
    kb_positions = find_positions(log, KB_QUERY_PATTERNS)
    # 检查 rejected-approaches 是否被查询（排除否定语境，如：未查询 rejected-approaches）
    raw_rejected_match = check_dimension(log, REJECTED_BUF_PATTERNS)
    negation_context = False
    if raw_rejected_match:
        for neg_pat in NEGATION_PREFIXES:
            if re.search(rf'{neg_pat}\s*.{{0,10}}(?:rejected.?approaches|负反馈库|已知失败方案)', log, re.IGNORECASE):
                negation_context = True
                break
    rejected_queried = raw_rejected_match and not negation_context
    # 检查知识库查询是否出现在推理/结论之前（简化：知识库查询在前半段）
    if log and not kb_positions:
        warnings.append({'dimension': 'skill_selection', 'violation_type': 'skip_knowledge_base',
                         'detail': '未查询知识库即开始推理'})
    elif log and kb_positions:
        avg_kb_pos = sum(kb_positions) / len(kb_positions)
        if avg_kb_pos > len(log) * 0.6:
            warnings.append({'dimension': 'skill_selection', 'violation_type': 'late_knowledge_base',
                             'detail': f'知识库查询偏晚（位置 {int(avg_kb_pos)}/{len(log)}）'})
    # 检查造数路径是否跳级
    data_positions = {}
    for name, pats in DATA_CREATE_ORDER.items():
        pos = find_positions(log, pats)
        if pos:
            data_positions[name] = min(pos)
    if 'db_direct' in data_positions and 'strategy_test_run' not in data_positions:
        warnings.append({'dimension': 'skill_selection', 'violation_type': 'skip_data_create_path',
                         'detail': '直接使用 DB 直操，跳过策略试运行'})
    if not rejected_queried and check_dimension(log, [r'造数失败', r'数据.*失败', r'SKIP', r'BLOCKED']):
        warnings.append({'dimension': 'skill_selection', 'violation_type': 'skip_rejected_buffer',
                         'detail': '造数失败后未查询 rejected-approaches'})

    # --- Dimension 2: Skill Following ---
    # 检查自愈七步是否按序（简化：检查出现的 Step 标记是否递增）
    found_steps = []
    for i, marker in enumerate(STEP_MARKERS):
        pos = find_positions(log, [marker])
        if pos:
            found_steps.append((i, min(pos)))
    if found_steps:
        for j in range(1, len(found_steps)):
            if found_steps[j][1] < found_steps[j-1][1]:
                warnings.append({'dimension': 'skill_following', 'violation_type': 'step_order_violation',
                                 'detail': f'Step {found_steps[j][0]} 出现在 Step {found_steps[j-1][0]} 之前'})
                break
    # 检查群消息违规
    if check_dimension(log, GROUP_MSG_VIOLATION):
        warnings.append({'dimension': 'skill_following', 'violation_type': 'group_message_violation',
                         'detail': '检测到向群发送消息（违反白名单规则）'})

    # --- Dimension 3: Skill Composition ---
    # 检查 DB 路由前缀是否正确
    for prefix, expected_db in DB_PREFIX_RULES.items():
        pattern = rf'{re.escape(prefix)}\w+'
        matches = re.findall(pattern, log)
        if matches:
            # 检查是否在正确的 DB 上下文中使用
            wrong_ctx = [m for m in matches if expected_db not in log[max(0, log.index(m)-100):log.index(m)+len(m)+100].lower()]
            # 简化：只报告有跨 DB 混用嫌疑的情况
            # （实际执行时需要更精确的 SQL 上下文解析）

    # --- Dimension 4: Grounded Reflection ---
    has_evidence = check_dimension(log, EVIDENCE_PATTERNS)
    has_conclusion = check_dimension(log, [r'PASS', r'验证通过', r'符合预期', r'结果正确'])
    if has_conclusion and not has_evidence:
        warnings.append({'dimension': 'grounded_reflection', 'violation_type': 'no_evidence',
                         'detail': '结论无 DB/API 证据支撑'})
    # 提测场景检查部署确认
    is_deploy_test = check_dimension(log, [r'提测', r'部署.*验证', r'发布.*测试'])
    if is_deploy_test and not check_dimension(log, DEPLOY_CHECK):
        warnings.append({'dimension': 'grounded_reflection', 'violation_type': 'skip_deploy_check',
                         'detail': '提测场景未验证代码部署状态'})

    # 输出结果
    status = 'CLEAR' if not warnings else 'WARNING'
    return {
        'caseId': cid,
        'sampled': True,
        'status': status,
        'warnings': warnings,
        'dimensions': {
            'skill_selection': 'WARNING' if any(w['dimension'] == 'skill_selection' for w in warnings) else 'CLEAR',
            'skill_following': 'WARNING' if any(w['dimension'] == 'skill_following' for w in warnings) else 'CLEAR',
            'skill_composition': 'WARNING' if any(w['dimension'] == 'skill_composition' for w in warnings) else 'CLEAR',
            'grounded_reflection': 'WARNING' if any(w['dimension'] == 'grounded_reflection' for w in warnings) else 'CLEAR',
        }
    }

# 从 stdin 读取 SAMPLED_JSON 块
lines = sys.stdin.readlines()
in_block = False
results = []
unauditable = []
for line in lines:
    stripped = line.strip()
    if stripped == '---SAMPLED_JSON_START---':
        in_block = True
        continue
    if stripped == '---SAMPLED_JSON_END---':
        in_block = False
        break
    if in_block and stripped:
        try:
            case = json.loads(stripped)
            if case.get('execLog_source', 'oss') != 'oss':
                unauditable.append({'caseId': case.get('caseId', '?'), 'reason': case.get('execLog_source', 'unknown')})
            results.append(audit_case(case))
        except json.JSONDecodeError:
            pass

# 汇总输出
clear_count = sum(1 for r in results if r['status'] == 'CLEAR')
warn_count = sum(1 for r in results if r['status'] == 'WARNING')
total_warnings = sum(len(r['warnings']) for r in results)

print(f'过程审计完成: {len(results)} 条 (CLEAR: {clear_count}, WARNING: {warn_count}, 总 warning: {total_warnings})')
if unauditable:
    print(f'注意: {len(unauditable)} 条 execLog 不可审计（未计入告警判定，空日志不触发 warning）')
    for u in unauditable:
        print(f'  [UNAUDITABLE] {u[\"caseId\"][:60]} | reason={u[\"reason\"]}')
for r in results:
    if r['warnings']:
        for w in r['warnings']:
            print(f'  [{r[\"caseId\"]}] {w[\"dimension\"]}: {w[\"violation_type\"]} - {w[\"detail\"]}')

# 输出 JSON 供 Step 5 报告消费
print('---PROCESS_AUDIT_RESULT_START---')
print(json.dumps(results, ensure_ascii=False))
print('---PROCESS_AUDIT_RESULT_END---')
"
```

**违规累积处理**：
- 单次违规 → 标记 `process_warning`，记入当日复盘报告
- 同类违规累积 >= 3 次（跨天累计）→ 产出 skill patch 提案（强化该规则措辞或增加硬拦截），写入 `pending-review/`
- 过程审计结果追加到复盘报告的"执行质量"段落

```bash
# 3b-2. 跨天违规累积统计（检查是否有维度累积 >= 3 次需产出 skill patch）
# 从历史复盘报告中提取 process_warning 记录，按维度+类型聚合
grep -h "process_warning" ~/.qoderwork/gap-guardian/pending-review/trace-*.md 2>/dev/null | \
python3 -c "
import sys, json, re
from collections import Counter

warnings = []
for line in sys.stdin:
    line = line.strip()
    if line.startswith('{'):
        try:
            warnings.append(json.loads(line))
        except:
            pass

# 按 (dimension, violation_type) 聚合
counter = Counter()
for w in warnings:
    dim = w.get('dimension', 'unknown')
    vtype = w.get('violation_type', 'unknown')
    counter[(dim, vtype)] += 1

# 输出需要产出 skill patch 的项（累积 >= 3）
patches_needed = {k: v for k, v in counter.items() if v >= 3}
if patches_needed:
    print(f'需要产出 skill patch 的违规累积: {len(patches_needed)} 项')
    for (dim, vtype), count in patches_needed.items():
        print(f'  [{dim}] {vtype}: {count}次 -> 写入 pending-review/process-patch-{dim}.md')
else:
    print('无违规累积 >= 3 次的维度')

# 输出当日过程审计 JSON（供 Step 5 合并到复盘报告）
print('---PROCESS_AUDIT_JSON_START---')
print(json.dumps({'warnings_today': len(warnings), 'patches_needed': len(patches_needed)}, ensure_ascii=False))
print('---PROCESS_AUDIT_JSON_END---')
"
```

**过程审计写入复盘报告的格式**（Step 5 合并时使用）：

```markdown
## 执行质量（过程审计）
- 抽样: {sampled_count}/{pass_count} 条 PASS 用例（20% 确定性抽样）
- 四维概况: Skill Selection:{ss_warnings} | Skill Following:{sf_warnings} | Skill Composition:{sc_warnings} | Grounded Reflection:{gr_warnings}

| caseId | 维度 | 状态 | 说明 |
|--------|------|------|------|
| {caseId} | {dimension} | WARNING | {detail} |

### 违规累积（跨天）
| 维度 | 违规类型 | 累计次数 | 处理 |
|------|----------|----------|------|
| {dimension} | {violation_type} | {count} | process_warning / skill patch 提案 |
```

### Step 4：编辑影响评估（Edit Impact Assessment）

对 edit-history.jsonl 中 `assessed: false` 的条目做影响评估。评估方法见 `~/.qoderwork/skills/qa-gap-guardian/references/edit-impact-tracker.md`。

**评估流程**：

1. 读取未评估编辑的 `ts`（编辑时间）和 `skill`（目标 skill）
2. 在编辑时间之后，查找目标 skill 被使用的执行记录（从 att-tf cases 中找 skill 相关用例）
3. 对比编辑前后的表现：
   - 编辑目标 gap 不再出现 → `outcome: resolved`
   - 编辑目标 gap 频率下降但未消除 → `outcome: partial`
   - 编辑后同 skill 出现新 gap（不同区域）→ `outcome: regression`
   - 编辑后无明显变化 → `outcome: stable`
4. 更新 edit-history.jsonl 中对应条目的 `impact` 字段
5. `regression` 结果 → 自动追加到 rejected-approaches.jsonl（该修复方案本身成为负反馈）

**无法评估的情况**：编辑后目标 skill 未被使用过 → `outcome: null, evidence: "编辑后无执行记录，暂无法评估"`，保持 `assessed: false`，下次 cron 再评。

### Step 5：归并排序 + 输出

1. **合并提案**：将 Step 2（失败驱动）和 Step 3（成功驱动）的提案合并
2. **排序**：失败纠正优先（对标 SkillOpt failure-priority merge），然后按 evidence 数量降序
3. **去重去矛盾**：同一 location 的多条提案合并为一条；互相矛盾的提案（add vs delete 同一规则）标记为需人工判断
4. **输出到 pending-review/**：写入 `~/.qoderwork/gap-guardian/pending-review/trace-{date}.md`，格式：

```markdown
# 每日轨迹复盘 - {date}

## 执行概况
- 用例总数: X (PASS: X, FAIL: X, BLOCKED: X, SKIP: X)
- 新增 gap: X
- 编辑影响评估: X 条（resolved: X, partial: X, regression: X, stable: X, 无法评估: X）

## 执行质量（过程审计）
- 抽样: {sampled}/{pass} 条 PASS 用例（20% 确定性抽样）
- 四维概况: Skill Selection:{ss} | Skill Following:{sf} | Skill Composition:{sc} | Grounded Reflection:{gr}

| caseId | 维度 | 状态 | 说明 |
|--------|------|------|------|
| {caseId} | {dimension} | WARNING | {detail} |

### 违规累积（跨天）
| 维度 | 违规类型 | 累计次数 | 处理 |
|------|----------|----------|------|
| {dimension} | {violation_type} | {count} | process_warning / skill patch 提案 |

## 失败驱动提案（按优先级）
### 提案 1: {target_skill} - {action}
- **位置**: {location}
- **提案内容**: {proposed_text}
- **证据**: {gap_ids}
- **理由**: {rationale}

## 成功驱动提案
### 提案 N: ...

## 编辑影响详情
| gap_id | skill | location | outcome | evidence |
|--------|-------|----------|---------|----------|

## 负反馈库更新
- 新增: X 条
- times_tried 递增: X 条
```

5. **IM 私聊通知用户**：通过 IM 私聊发送摘要（不发群消息），包含提案数量和关键发现

## 群消息与 IM 路由（红线）

**严格遵守 AGENTS.md 群消息白名单**：
- 本 skill 不向任何钉钉群发送消息
- 复盘结果通过 IM 私聊通知用户
- 通知内容纯 ASCII 文本，不用 emoji 或特殊符号

**IM 通知模板**：
```
每日轨迹复盘完成 ({date})
用例: {total}条 (PASS:{pass} FAIL:{fail} BLOCKED:{blocked} SKIP:{skip})
Gap: {gap_count}条
编辑评估: {edit_count}条 (resolved:{r} partial:{p} regression:{rg} stable:{s})
提案: {proposal_count}条 (失败驱动:{fd} 成功驱动:{sd})
详情: ~/.qoderwork/gap-guardian/pending-review/trace-{date}.md
```

## 与 qa-gap-guardian 的分工

| 维度 | qa-gap-guardian | qa-trace-reflection |
|------|-----------------|---------------------|
| 触发方式 | 用户主动触发 | 每日 cron 自动运行 |
| 分析粒度 | 单会话/单任务 | 跨会话批量聚合 |
| 输入 | 单会话 transcript + gap 台账 | att-tf cases + gap 台账 + edit-history |
| 输出 | 审计报告 + 即时修复（T1/T2） | 改进提案（全部进 pending-review，不自动修复） |
| 编辑执行 | T1 自动执行，T2 等审批 | 不执行任何编辑，只产出提案 |

## cron 配置

```yaml
schedule:
  kind: cron
  expr: "0 20 * * 1-5"  # 工作日晚 8 点
  tz: Asia/Shanghai
missedRunPolicy: skip
```

payload.message 须包含：
1. 群消息白名单规则（仅允许"收到提测消息"和"测试完成"结果摘要）
2. 禁止向群发送中间状态消息
3. 复盘结果仅 IM 私聊用户
4. 通用排查原则（先查知识库再推理）

## 红线

- 不自动执行任何 skill 修改（全部进 pending-review 等用户审批）
- 不向群发送任何消息（仅 IM 私聊）
- 不重新触发已完成的测试任务
- 编辑影响评估只读分析，不修改 att-tf 或 gap-guardian 的原始数据（只写 edit-history 的 impact 字段）

## Step 6: Skill 健康度报告（改进五·新增）

> 借鉴《从聊天到驾驭》"方法也会过期"——定期审查 references/ 文件的引用频率和有效性。

每周执行一次（可复用本 cron 任务的定时调度），扫描 qa-testing-workbench 插件下所有 references/ 文件：

### 6.1 引用频率审计
- 扫描 `~/.qoderwork/plugins-custom/qa-testing-workbench/skills/*/references/` 下所有文件
- 检查每个文件在最近 30 天内是否被任何执行会话（exec-log / cron 运行日志）引用
- 30 天未被引用 → 标记为 `stale`

### 6.2 rejected-approaches 过期扫描
- 读取 `qa-self-healing/references/rejected-approaches.jsonl`
- 检查每条记录的 `valid_until` 字段
- 过期记录（当前日期 > valid_until）标注 `[EXPIRED]`
- 统计过期占比，超过 50% 时建议清理

### 6.3 输出格式
生成 `outputs/skill-health-report-{date}.md`，包含：
- 活跃文件数 / stale 文件数 / 过期 rejected-approaches 数
- stale 文件清单（路径 + 最后引用时间）
- 建议退役的文件清单
- 与上期报告的对比（如有）

报告同步到 `references/skill-retirement-log.md`（qa-testing-workbench 插件）供人工审核。

## Step 7：失败知识自进化（learned-solutions 提取）

> 3.2 失败知识自进化闭环的落地。从成功解决的 case 中提取 pattern → solution 对，写入 learned-solutions.jsonl。

### 7.1 从成功轨迹提取 learned solutions

在 Step 3（成功轨迹 Reflection）中，对高频成功路径（>= 3 次）额外执行：

```bash
# 提取成功模式并写入 learned-solutions.jsonl
python3 -c "
import json, sys
from datetime import datetime

# 从 att-tf PASS 用例的 execLog 中提取成功模式
# 关注：自愈成功的路径、造数成功的路径、验证成功的路径
patterns = []
# ... (解析 execLog 中的成功路径)

# 写入 learned-solutions.jsonl
with open('/Users/caoxuemei/.qoderwork/skills/qa-self-healing/references/learned-solutions.jsonl', 'a') as f:
    for p in patterns:
        entry = {
            'pattern': p['pattern'],
            'solution': p['solution'],
            'source': p['source'],
            'confidence': p['confidence'],
            'times_used': 0,
            'created': datetime.now().strftime('%Y-%m-%d')
        }
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
"
```

### 7.2 查询 learned-solutions

自愈过程中（qa-self-healing 规则一步骤 0），在查 rejected-approaches 之后，额外查 learned-solutions：

```bash
# 查询 learned-solutions（按 times_used 降序）
cat ~/.qoderwork/skills/qa-self-healing/references/learned-solutions.jsonl | python3 -c "
import sys, json
entries = [json.loads(l) for l in sys.stdin if l.strip()]
entries.sort(key=lambda e: e.get('times_used', 0), reverse=True)
for e in entries[:20]:
    print(f\"[{e.get('confidence',0):.0%}] {e.get('pattern','')} -> {e.get('solution','')} | 来源: {e.get('source','')} | 使用: {e.get('times_used',0)}次\")
"
```

命中后：
- 将 `solution` 作为候选修复路径，优先级高于自行推理
- 递增 `times_used` 计数
- 如果实际执行成功，更新 `confidence`（贝叶斯更新：confidence = (confidence * times_used + 1) / (times_used + 1)）

### 7.3 与 rejected-approaches 的关系

| 维度 | rejected-approaches.jsonl | learned-solutions.jsonl |
|------|--------------------------|------------------------|
| 知识类型 | 负反馈（什么不该做） | 正反馈（什么该做） |
| 查询时机 | Step 0（七步诊断入口） | Step 0 之后（候选路径排序） |
| 写入时机 | 自愈失败时 | 自愈成功时 |
| 衰减机制 | valid_until 过期 + superseded_by | confidence 贝叶斯更新 |

## Step 8：周度深度分析（慢飞轮）

> 4.2 慢飞轮周度沉淀的落地。每日复盘是"快飞轮"（实时反馈），周度分析是"慢飞轮"（系统性问题发现）。

### 触发方式

每周日 21:00 通过 cron 触发（与每日复盘 cron 共用调度，通过日期判断执行周度分析）。

### 分析内容

1. **聚合一周执行数据**：
   - PASS/FAIL/BLOCKED 分布趋势（日粒度折线）
   - 自愈成功率趋势（是否在改善）
   - gap 类型分布（G1-G9 占比变化）
   - learned-solutions 命中率（新增多少、使用了多少）

2. **识别系统性问题**：
   - 某类用例持续 FAIL（连续 3 天以上）→ 可能是用例设计问题而非执行问题
   - 某个 skill 的 gap 频率持续上升 → 可能需要重构而非修补
   - rejected-approaches 中某条路径 times_tried 持续增加 → 说明 Agent 反复尝试已知死路

3. **自动更新知识库**：
   - 将本周新增的 learned-solutions 汇总
   - 清理过期 rejected-approaches
   - 更新 capability-registry.md

4. **产出周度质量报告**：
   - 写入 `outputs/weekly-quality-report-{week}.md`
   - 通过 IM 私聊通知用户（不发群）
   - 包含：本周概况、系统性问题、改进建议、下周关注点

### cron 配置

```yaml
schedule:
  kind: cron
  expr: "0 21 * * 0"  # 每周日晚 9 点
  tz: Asia/Shanghai
missedRunPolicy: skip
```

### 与每日复盘的关系

| 维度 | 每日复盘（Step 1-7） | 周度分析（Step 8） |
|------|---------------------|-------------------|
| 频率 | 工作日每天 | 每周日 |
| 粒度 | 单日用例/gap 级 | 周度趋势/系统性 |
| 产出 | skill patch 提案 | 质量报告 + 知识库更新 |
| 关注点 | 即时修复 | 趋势发现 + 预防 |
