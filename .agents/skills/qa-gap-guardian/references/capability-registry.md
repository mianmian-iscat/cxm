# 能力清单（capability registry）

gap 判定（G1/G2/G4）的客观依据。判「明明可以解决」必须引用本清单条目或真实存在的 skill 文件。
维护规则：新发现能力/陷阱 → T1 自动追加条目（qa-gap-guardian Stage 5）；条目带日期，过时条目降权不删除。

## A. 已知 API 捷径（绕过 UI 的服务端直解）

| 能力 | 入口 | 说明 | 收录日期 |
|------|------|------|----------|
| F88 身份切换根治 | `POST /api/tenant/cacheEmployeeIdentity` body `{"tenantId":"f88"}` + header `X-AFD-Emp-Identity:f88` | 服务端 cachedIdentity 落库，返回 data:true；有数秒传播延迟勿立即复查。禁止靠 UI 下拉切换（自动化不稳）。验证用 `POST /api/tenant/queryEmployeeIdentityList` | 2026-08-04 |
| F88 审核任务造数 | `审核数据构造` skill 方式一（策略试运行+审核专用模板.xlsx） | 产出真实 BT_ 批次；方式二（手动创建 API）仅 formal 语义验证 | 2026-08-04 |

## B. 工具链陷阱与已知解

| 陷阱 | 已知解 | 收录日期 |
|------|--------|----------|
| Shell EBADF / fd 泄漏 | 同一对话内无法自愈，必须开新对话；主 shell 全坏时试子任务路径。dms-alibaba workaround：`env -i HOME=$HOME PATH=... /bin/zsh -c 'dms-alibaba ...'`；heredoc 含单引号先 Write 落脚本再执行 | 2026-08 |
| plugins-custom 改完不生效 | 必须 rsync 到 `~/.qoderwork/plugins/cache/local/{插件名}/{版本}/` 并 grep 验证；已知缓存：qa-testing-workbench 2.1.0、yc-protection-qa-workbench 1.0.0/1.1.0。用户级 skill 无需同步 | 2026-08 |
| MCP 浏览器 tab 截不到 | MCP tab 不在 AppleScript 可见实例里，system-screenshot/osascript 无效；一律用 builtin_browser 自带 screenshot/navigate | 2026-08 |
| dms-alibaba 大窗口 GROUP BY 20s 超时 | 先按 PK 探针定 id↔日期映射，再分段窄窗口扫；超时就对半拆 | 2026-08 |
| stylespot 库查询 | database_id=5335708；env 列区分 staging/prod；g_workflow_batch 先取 batch_id 再 IN(...) 分 chunk ≤40；g_afd_review_job 只走 id/parent_job_id 窄窗口 | 2026-08 |
| 模板匹配 mustMatchFields 语义 | V1 空=默认启用硬过滤；V2 勾选才硬过滤、空=仅排序。语义相反，跨版本核对必查 | 2026-08 |
| 大会话 transcript 读取 token 溢出 | `qoder_get_task_detail` 返回可达 100k+ 字符，直接读入上下文会超限；先落盘原始 JSON，再用 Python 脚本压缩成 compact 视图（工具调用链+关键错误+时间戳）后审计 | 2026-08-05 |
| QoderWork Models 为 UI-only 隐藏功能 | 不能通过 agent 工具修改模型配置，禁止发明 `qoderwork.settings.models` 等查询键；模型配置只能改 agents.db 三处落点（见 E 区 custom model removed 条目）或引导用户走 UI | 2026-08-05 |

## C. 造数路由（引用 qa-self-healing 规则 3b，防重复发明）

审核任务→`审核数据构造`；模板包→`f88-template-package-create`；YC 快审/初审→`yc-quick-audit-data-create`；YC 状态/时间→`yc-data-factory`；策略批次→`strategy-platform`。完整表在 qa-self-healing 规则 3b。

## D. 自动化降级序（卡点换路时对照）

Computer Use（系统级原生事件）> 浏览器自动化 > 视觉 AI 自动化 > API 直调（红线内）。同一工具最多重试 3 次。React 受控组件不响应 JS 注入 → 立即换 Computer Use 或找 API 替代。

## E. 历史成功配方

| 场景 | 成功路径 | 收录日期 |
|------|----------|----------|
| 空输入静默卡死批次诊断 | 查输入必填字段是否为空（空字符串 API 不校验但 workflow 不推进）→ 补全输入重触发（BT_7350→BT_7352 案例） | 2026-07-29 |
| att-start 测试会话声明 | 必须通过 `Skill skill=att-start args="aoneId=..."` 调用；curl POST localhost:8765 为占位符，不可用 | 2026-08-05 |
| QoderWork 能力边界速查 | 排查 QoderWork 应用自身行为前先加载 `qoderwork-guidance`；Models 为 UI-only 隐藏功能，禁止发明 `qoderwork.settings.models` 等键 | 2026-08-05 |
| custom model removed 根因定位 | 模型配置落点：`app_settings.modelLevel`（应用默认）、`sub_chats.model_level`（单会话）、`scheduled_tasks.model`（定时任务）；出现 `100404 Specified custom model have been removed` 时优先查这三处 | 2026-08-05 |
| 技能发现入口 | 遇到生疏领域先调用 `find-skills` 或 `qw_query qoderwork.settings.skills` 检索已有 skill，避免手动重发明 | 2026-08-05 |

<!-- 追加区：T1 修复自动追加条目于此行之前 -->
