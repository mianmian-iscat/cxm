# 编辑影响追踪协议（Edit Impact Tracker）

**理念**：不限制编辑次数，但追踪每次编辑的完整上下文和后续影响。用数据驱动学习，而非用预算限制自由。

**对标 SkillOpt**：Bounded Edits（学习率）→ 我们不做硬截断，而是记录每次"参数更新"，事后看哪些更新有效、哪些引入了回归。这更接近真实的 SGD——学习率不是"不准更新"，而是"更新后看 loss 变化"。

## 数据文件

`~/.qoderwork/gap-guardian/edit-history/edit-history.jsonl`

每条记录格式：

```json
{
  "ts": "2026-08-12T20:00:00+08:00",
  "gap_id": "GAP-20260812-003",
  "skill": "qa-self-healing",
  "file": "SKILL.md",
  "edit_type": "add|delete|replace",
  "location": "规则一 Step 4 分层执行",
  "before_snippet": "被替换的原文（前3行+后3行）",
  "after_snippet": "替换后的文本（前3行+后3行）",
  "lines_changed": 5,
  "reason": "Step 4 缺少重试上限约束，导致同一工具死循环",
  "confidence": 0.8,
  "backup_path": "patches/qa-self-healing-SKILL.md.bak-20260812",
  "impact": {
    "assessed": false,
    "assessed_at": null,
    "outcome": null,
    "evidence": null
  }
}
```

## 写入时机

**T1 修复执行后立即写入**（Stage 3 完成后）：
- gap-guardian 每次执行 T1 修复，无论改了多少处，每处都追加一条记录
- `impact` 字段初始为 `assessed: false`

**T2 修复经用户批准后补写**：
- pending-review 中的草案被批准后，由批准者补写一条记录
- `confidence` 设为 0.5（T2 不确定性更高）

## 影响评估（由 qa-trace-reflection 执行）

每日 cron 运行时，对未评估的编辑做影响评估：

### 评估方法

1. **找到编辑后的执行记录**：编辑时间戳之后，目标 skill 被使用的会话（从 att-tf cases.json 或 gap-guardian ledger 中找）
2. **对比编辑前后的表现**：
   - 编辑目标 gap 是否再出现？→ `outcome: resolved`
   - 编辑目标 gap 出现频率下降但未消除？→ `outcome: partial`
   - 编辑后出现了新的 gap（同一 skill 的不同区域）？→ `outcome: regression`
   - 编辑后该 skill 无新 gap 也无明显改善？→ `outcome: stable`
3. **记录证据**：`evidence` 字段记录具体的 gap_id 或会话记录

### 评估输出

```json
{
  "assessed": true,
  "assessed_at": "2026-08-13T20:00:00+08:00",
  "outcome": "resolved|partial|regression|stable",
  "evidence": "编辑后 3 次使用 qa-self-healing，Step 4 相关 gap 未再出现"
}
```

## 学习闭环

影响评估数据供两个消费者使用：

1. **qa-trace-reflection 周报**：统计本周各 outcome 分布，识别"哪类编辑最有效"
   - resolved 率高 → 该类 T1 修复策略可靠，可扩大自动执行范围
   - regression 率高 → 该类修复需要更谨慎，可能需要升级为 T2

2. **Slow/Meta Update（P2）**：跨周对比，发现"编辑的编辑"模式
   - 如果某个 skill 连续 3 周都有 regression → 该 skill 可能需要结构性重构而非打补丁
   - 如果某类 gap 反复被修复又反复出现 → 根因未解决，需要 T2 设计类修复

## 与 fixes.jsonl 的关系

| 文件 | 记录什么 | 谁写 | 谁读 |
|------|---------|------|------|
| `ledger/fixes.jsonl` | 修复动作（gap_id → 动作 → 结果） | gap-guardian Stage 3 | gap-guardian 自身审计 |
| `edit-history/edit-history.jsonl` | 编辑内容+影响（before/after + impact） | gap-guardian Stage 3 + trace-reflection | trace-reflection + Slow/Meta |

fixes.jsonl 是"做了什么"，edit-history 是"改了什么+效果如何"。前者是审计日志，后者是学习数据。
