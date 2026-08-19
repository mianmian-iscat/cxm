# 修复 Playbook（分级自主策略）

修复分两级：**T1 确定性修复**自动执行（机械性、可逆、有白名单），**T2 设计类修复**落 pending-review 等人审。分级判定有疑问时就低不就高（转 T2）。

## T1 白名单（可自动落盘，改前必备份到 ~/.qoderwork/gap-guardian/patches/）

| 编号 | 修复类型 | 动作 | 回归验证方式 |
|------|----------|------|--------------|
| T1-1 | 插件缓存未同步 | 检测 plugins-custom 源与 cache 版本不一致 → rsync 到 `~/.qoderwork/plugins/cache/local/{插件名}/{版本}/` | grep 缓存文件确认关键段落存在 |
| T1-2 | 检查点协议缺失 | 向执行类 skill 注入 checkpoint-protocol.md 的标准段落（只增不改原有逻辑） | grep 注入段落 + frontmatter 可解析 |
| T1-3 | 能力清单/路由表条目补充 | 向 capability-registry.md 或 qa-self-healing 路由表追加已验证的条目（带日期） | grep 条目存在 |
| T1-4 | 告警规则编号注册 | f88-pipeline-monitor 新规则前查 references/alert-rules.md 最大编号防撞号，注册编号并同步 SKILL.md 内联步骤 | grep 两处编号一致 |
| T1-5 | 触发词补漏 | skill 描述触发词缺失导致该触发没触发（有证据）→ 追加触发词 | frontmatter 可解析 |
| T1-6 | 修复登记 | 每次 T1/T2 动作写 ledger/fixes.jsonl | 文件可被 jq 解析 |
| T1-7 | cron payload 新鲜度检查 | 对每个 cron job：payload 引用的 skill 版本 vs 已装 frontmatter 版本比对，不一致产出差异清单（**仅检测，payload 内容更新归 T2**） | 差异清单含 jobId/skill/版本对 |

**T1 执行铁律**：

1. 备份先行：`cp <目标文件> ~/.qoderwork/gap-guardian/patches/{文件名}.{GAP编号}.bak`
2. plugins-custom 改动必须 rsync 全部已知缓存版本（qa-testing-workbench 2.1.0、yc-protection-qa-workbench 1.0.0/1.1.0），grep 验证
3. 用户级 skill（~/.qoderwork/skills/）改完即生效，无需 rsync
4. 中文插件 skill（如 审核数据构造）直接 Edit 源文件再 rsync，不走 skill_manage
5. Edit 报「文件已被修改」→ 重读再改（并发修改通常来自同款巡检 cron）
6. 验证失败 → 立即用备份回滚，该修复转 T2
7. **回归防护**：T1 修复写入后，必须执行 `python3 ~/.qoderwork/scripts/healing-regression-check.py --rule-type patch --rule-file <patch目标> --backup-file <patches/备份>`。BLOCK → 自动回滚转 T2；PASS(with review) → 写入 pending-review 但修复仍生效。快照保存在 `~/.qoderwork/qa-self-healing/regression-snapshots/`。

## T2 范围（写草案到 pending-review/，禁止自动落盘）

- 工作流语义变更（新增/修改 Stage、改判定逻辑、改门禁）
- 新增规则或红线条款
- 跨多个 skill 的联动改动
- 新 skill 立项（G8 框架空白）
- 告警阈值调整（需生产观测数据支撑，参考 R024 校准流程）
- cron payload 内容更新（G9a 修复）：必须走合并协议——先 qw_query 取当前 payload 最新版再合并，勿整段覆盖（可能有并发写入者），更新后必须 qw_query 复核 prompt 字段确认落盘
- 任何涉及用户红线条款附近的改动

**T2 草案格式**（pending-review/GAP-YYYYMMDD-NNN.md）：

```markdown
# GAP-YYYYMMDD-NNN 修复草案
- gap 分类：G1-G9
- 证据锚点：{transcript 片段/台账条目 id}
- 目标文件：{路径}
- 改动 diff：{before/after}
- 影响面：{哪些流程受影响}
- 回归建议：{落盘后应跑什么验证}
- 状态：pending_review | approved | rejected
```

## 修复优先级

| 级别 | 条件 | 时限 |
|------|------|------|
| P0 | G3 违规降级 / G9b 机器人推错群 / 影响测试结果真实性的 gap | 当次审计内完成 T1 部分，T2 草案当天产出 |
| P1 | G1/G2/G6/G9a/G9c/G9e | 当次审计完成 T1，T2 草案 3 天内 |
| P2 | G4/G5/G8/G9d | 记入报告，随日审/周审处理 |

## 回滚规程

1. 从 fixes.jsonl 找到 gap_id 对应的备份路径
2. `cp <备份> <原路径>`（plugins-custom 记得重新 rsync）
3. fixes.jsonl 追加一条 `{"action":"rollback","gap_id":"..."}`
4. 该 gap 修复转 T2 重新走草案
