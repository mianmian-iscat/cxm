# Gap 检查点协议 v1.0（执行内嵌轨道）

执行类 skill 在以下时刻**必须**追加一条 gap 台账条目到 `~/.qoderwork/gap-guardian/ledger/{YYYY-MM-DD}.jsonl`：

## 触发时刻

1. 即将标 SKIP / BLOCKED 之前（缺失分析完成后）
2. 发生降级/换路时（含 UI→API、换工具、换观测源）
3. 同一工具/路径第 2 次重试前
4. 决定询问用户「怎么办」之前（红线外确认除外）

## 执行步骤（当场 3 步，30 秒内完成）

1. **查能力清单**：读 `~/.qoderwork/skills/qa-gap-guardian/references/capability-registry.md`，找有没有现成解（API 捷径/造数路由/已知陷阱解）。
2. **有匹配 → 先试清单路径**；试了仍失败或无匹配 → 继续原决策。
3. **追加台账条目**（无论最终走哪条路都要记）：

```bash
mkdir -p ~/.qoderwork/gap-guardian/ledger && cat >> ~/.qoderwork/gap-guardian/ledger/$(date +%F).jsonl <<'EOF'
{"ts":"ISO8601","chat_id":"会话ID","case_id":"用例ID或null","stage":"执行阶段","problem":"问题一句话","chosen_path":"实际选的路径","alternatives_considered":["考虑过的替代"],"capabilities_checked":["查过的能力清单条目"],"outcome":"resolved|degraded|blocked|pending","reason":"为什么这么选"}
EOF
```

> 实操提示：字段值含特殊字符时，用 Write 工具把 JSON 行追加进文件更稳，避免 heredoc 引号问题。

## 强制项

- `alternatives_considered` 为空 = 没想过替代方案，审计时直接按 G1/G2 候选处理
- `capabilities_checked` 为空 = 没查能力清单，按 G6 处理
- 台账条目是 att-tf 证据链之外的补充决策记录，不影响 att-report 上报

## 即时止损（可选）

卡点当场可唤起 qa-gap-guardian（说「查能力清单」），它只返回匹配的建议路径，不接管执行——换不换路由执行者自己决定，但换了/不换都要记入台账。
