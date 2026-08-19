---
name: att-start
description: 测试会话开场声明(必须声明,但只登记身份/采证,不接管你的测试流程)。本次是测试会话就先调本 skill 声明身份,并在执行前锁定用例上传规范:有原始测试用例时后续 att-report 必须沿用 caseTitle/description/priority/groupPath,执行结果只进 status/errorMessage/execLog。别因路由到其它测试技能或用户自有流程 skill 就跳过声明;声明后回到用户 prompt 选该走的流程 skill。触发:用户说测一下/测试/帮我测/验证/验收/跑用例/写用例/QA/复现 bug/排查 bug/调接口断言……等测试场景,或 SessionStart 建议你调 /att-start 时。流程:你判定是测试会话 → 先一句话确认「是要上报的测试需求吧?」→ 从当前明确上下文提取唯一 aoneId,没有或多个再问 → 跑 `att start <aoneId> --agent-id <你的agent名>`。纯聊天/纯设计/纯写代码(不做执行验证)则忽略。
---

<!-- att-tf-skill-version: 1.5.0 -->

# att-tf 测试会话声明

> 命令名 `att`(`att-tf` 为兼容别名)。

SessionStart hook 只静态注入一行建议,**判断权在你**。

att-start 只声明身份、不接管执行、不替代任何测试流程的路由(test-case-generator/test-case-executor 等原子技能、用户自定义的流程/编排 skill 都一样)——哪怕要走它们,也**先**声明。但证据链归 att-tf:声明后截图与证据由 `att report` 自动从 transcript 重建并落 OSS,**别再按其它 skill 手动 curl 上传截图到别的端点**(重复无效)。

## ① 判断:是不是测试会话

要写用例/跑命令/调接口/点页面/做断言来验证需求 → 继续 ②。纯设计/闲聊/只写代码 → 忽略本 skill,不打扰用户。

## ② 先确认性质,再解析 aoneId

判定是测试后,**先一句话确认这是要上报的测试需求**,别对模糊/边缘会话直接硬问 aoneId。若当前用户消息 / 最近明确上下文 / Aone 链接里已经给出**唯一**需求 ID,直接使用并在回复里回显;没有或出现多个候选,把「确认性质」与「要 aoneId」合成一个自然问句:

> 「在测 XX 需求吧?需求 ID(aoneId)多少?」

用户确认是 → aoneId 是硬门:

- **aoneId 必须来自当前明确上下文或用户回答,绝不臆测**。上下文里有唯一明示 ID 就直接用,不要重复问;没有 / 多个 / 不确定才问。绝不从 git 分支名/目录名/commit、历史会话、identity 缓存沿用(每次测的是不同需求)。这是唯一硬门。
- **aoneId 只问一次**:用户**明确**表示没有 / 无需上报测试证据 → 不再追问、不跑 att-start、按原 prompt 继续,并一句话告知本次无 testflow 证据上报。
- **唯一明示的判定要保守**:只认用户明确说的「aoneId / 需求 ID / Aone 需求链接」里的唯一值;不要把 testflow caseId、bugId、订单号、工号、traceId、分支里的日期/需求号片段当 aoneId。若上下文同时出现多个可能的 ID,先问用户选哪个。
- **绝不拿占位值跑流程**。用户说「继续/跑一遍/试一下」≠ 让你用 `999999`/`000000`/`123456` 之类占位值或系统用户名(`whoami`/`admin`)把流程跑通——没拿到真实 aoneId 就先问。att-tf 对占位值会 LOUD 警告;看到 = 你在用假身份,立刻停下问用户。

工号/名字可选:

- **工号 `empNo` / 名字 `user_name` 可选,优先 agent 自己找真实值**:显式值 → env `ATT_EMP_NO`/`ATT_USER_NAME` → 安装期/历史缓存(`~/.att-tf/identity.json`)→ BUC(A1) 登录态(`a1 auth whoami`)自动识别。`att install` 会 best-effort 做一次 BUC/A1 身份缓存,只保存工号/姓名、不保存 token。找不到留空,不阻断上报。**绝不用系统用户名/占位值顶替**——宁可留空。
- **agent 名 `agentId`** 你自己知道(如 `claude-code`),自己填,或走 env `ATT_AGENT_ID`。

## ③ 声明

**Codex 受限沙箱**（仅工具支持时）：首次直接用 `sandbox_permissions="require_escalated"` + `prefix_rule=["att", "start"]`，理由为允许管理 `~/.att-tf`；不先普通执行失败再重试。无沙箱/已有权限/不支持该参数则普通执行；拒绝授权就停止，不扩大为整个 `att`。

```
# 工号/名字走 env 或缓存(CLI 自动回填):
att start <aoneId> --agent-id <你的agent名>

# 已确定真实工号/名字:显式给值并刷新缓存:
att start <aoneId> --emp-no <工号> --user-name <名字> --agent-id <你的agent名>
```

start 成功后立即调用一次本地 checkpoint（无需用户操作，失败不改变测试流程）：

```
att checkpoint --stage preparing
```

后续每次进入明确用例/阶段时由你自动更新，例如
`att checkpoint --stage executing --case-id <id> --case-title <标题>`；等待用户/外部系统时加
`--attention waiting_user|waiting_external`，恢复后写 `--attention none`。只报显式已知值，未知就不猜，
禁止按工具数/token/耗时推百分比。

测试执行期间由 Agent 自动维护 checkpoint，用户不需要手工操作：

- 进入或切换 Case 前：`att checkpoint --stage executing --case-id <id> --case-title <标题>`；只有显式知道总数时才加 `--progress-current N --progress-total M`。
- 等待用户输入：`att checkpoint --attention waiting_user`；等待环境/权限/外部系统：`--attention waiting_external`；恢复执行：`--attention none`。
- 开始收集截图、日志、接口回执等关键证据：`att checkpoint --stage collecting_evidence`。
- 执行结束、根据预期与实际结果裁决 Case：`att checkpoint --stage judging`。
- 进入 att-report 收尾：`att checkpoint --stage reporting --clear-case`。

这些 checkpoint 只声明你明确掌握的语义，不替代真实测试，也不允许从 transcript、工具数、token、耗时或收尾 cases.json 反推当前 Case/阶段。

声明后,用户**接下来的第一条测试 prompt 就是测试需求本体**;收尾上报时证据从会话起点机械重建、首 prompt 必被纳入,所以现在声明即可,**不必复述需求**。

start 只写身份;证据(execLog/截图/耗时)在收尾 `att report` 时重建、不依赖 start 时机——忘了开场声明,事后补 `att start` 再走 `/att-report` 也能正确出报告。

**声明完别由 att-start 直接开测**:重新回到用户的原始 prompt,据此选择该走的测试流程 skill(用户自有的测试流程/编排 skill、test-case-generator、test-case-executor 等),att-start 到此交回控制权。

## ④ 开测前锁定上传规范

声明后、真正执行前先定这条约束,后续 att-report 必须照此写 cases:

- **有原始用例定义**(测试用例文档/脑图/testflow case/用户给出的 case 表)时,先识别并保留原 `caseTitle` / `description` / `priority` / `groupPath`;执行结束上传时优先沿用这些字段,不要把 `description` 改成执行日志、实际结果摘要、环境说明或个人总结。若原定义缺描述,补充时优先写 JSON 对象 `{"preconditions":[],"steps":[],"expectedResults":[]}`。
- **执行结果只放结果字段**:`status` 写通过/失败/跳过,失败原因写 `errorMessage`;命令、接口响应、traceId、planId、DB 回查值、截图和耗时由 att-tf 从 transcript 机械重建到 execLog/证据里,不要塞进用例定义字段。
- **若本次新增探索用例**,标题/描述可以新写,但要按测试设计写「前置/步骤/预期」,不要冒充原用例;收尾时仍由 att-report 负责上报。

测完收尾走 **att-report**。
