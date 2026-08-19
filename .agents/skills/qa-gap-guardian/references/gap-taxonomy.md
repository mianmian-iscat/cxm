# Gap 分类法（GAP-01 ~ GAP-09）

每条 gap 判定必须归入以下一类，并给出证据锚点。分类决定修复路由（见 repair-playbook.md）。

| 编号 | 类别 | 定义 | 典型信号 | 判定证据要求 | 默认修复路由 |
|------|------|------|----------|--------------|--------------|
| G1 | 漏自愈 | 有已知修复手段但没执行，直接降级/SKIP/问用户 | 违反 qa-self-healing 规则零/2b；「XX 缺模块→直接换工具」「浏览器受阻→指挥用户手动」 | transcript 中出现降级但无修复尝试痕迹；对照规则零/2b/2c 条款 | 检查点协议注入相关 skill（T1）+ 规则引用强化（T2） |
| G2 | 漏 API 替代路径 | 能力清单里有现成 API/skill 路径但未使用，走了 UI 死磕或放弃 | 用户红线「浏览器自动化受阻必须优先找 API 替代」的违反 | capability-registry 有对应条目 + transcript 未调用 | 能力清单引用注入执行 skill（T1） |
| G3 | 违规降级 | 违反明确红线的降级（未造数用存量、API 代 UI 提交、抽检分错人仍继续、降级到指挥用户手动） | 红线条款被绕过 | 对照 USER.md 红线/qa-self-healing 规则零b/零c 原文 | T2（多为流程缺陷，需人审） |
| G4 | 次优路径 | 能完成但绕远：重复造轮子、漏用现成 skill、串行跑了可并行的 | 同一会话内重新发明了已有 skill 的能力 | 能力清单匹配 + 实际路径对比（耗时/步骤数） | playbook 优化建议（T2） |
| G5 | 重复踩坑 | memory/已知问题里有记录但没避开（如 EBADF 反复重试、插件改了没 rsync） | MEMORY.md 有对应条目但执行未规避 | memory 条目引用 + transcript 重犯证据 | memory/skill 提示强化（T1 注检查点 / T2 改流程） |
| G6 | 检查点漏记 | 发生 SKIP/BLOCKED/降级但没写 gap 台账条目（协议本身未被执行） | ledger 条目数 < transcript 中卡点数 | transcript 卡点计数 vs ledger 条数 | 检查点协议再注入/强化（T1） |
| G7 | 判定失误 | 结论与证据不符：假 PASS、BLOCKED 分类错误、缺证据的结论 | 与 qa-adversarial-agent FAIL 记录重合 | 对抗验证结果 + 证据链缺口 | 通常不修框架，记录执行者问题；若反复出现同类则 T2 |
| G8 | 框架空白 | 真没有可用手段（新场景、无 skill/API/配方） | 能力清单穷举后确实无匹配 | 能力清单穷举记录 | T2：新增 skill/API 封装/路由条目的立项草案 |
| G9 | 机器人/cron 专属 | 定时任务/机器人特有问题：G9a payload 与 skill 版本失同步 / G9b 推送目标错误 / G9c 静默失败无告警 / G9d missedRunPolicy 配置不当 / G9e 无人值守遇错即弃 | cron 任务 failed 无产物、payload 引用旧流程、发向默认群 | qoder_cron 配置 + 任务 transcript + 产物落盘检查（细则见 bot-cron-audit.md） | G9a 检测 T1/payload 更新 T2；G9b P0 T2；G9c/G9d T2 草案 |

## 判定原则

1. **先查能力清单再下结论**：G1/G2 的「明明可以」必须引用 capability-registry 的具体条目或真实存在的 skill 文件，不得凭印象。
2. **区分「试了失败」与「没试」**：前者不是 gap（或仅 G4），后者才是 G1/G2。
3. **G3 优先级最高**：违规降级直接标 P0，其余按影响面定 P1/P2。
4. **观察区**：证据不足的疑似项写入报告「观察区」，不计入 gap 统计、不进修复。
