---
name: att-report
description: 测试收尾上报(强制)。测完把每条用例的裁决语义(caseTitle/description/status 1通过2失败3跳过/priority/groupPath/errorMessage)定边界写成 cases 草稿；有原始测试用例时 caseTitle/description/priority/groupPath 必须优先沿用原定义,不能把 description 改写成执行总结；经 att-tf 复核后直报 testflow;execLog/截图/耗时由 CLI 从 transcript 机械重建自动附。触发:Stop hook 提示"发现未上报 session"、用户说"测完上报/同步 testflow/上报用例"等收尾场景、或你判断本次测试已跑完(命令跑完、断言出结果)时。即便用了 test-case-generator/test-case-executor 等其它测试技能,收尾仍必须走 att-report。
---

<!-- att-tf-skill-version: 1.9.0 -->

# att-tf 用例裁决上报

> 命令名 `att`(`att-tf` 为兼容别名)。

**TL;DR(测完别等 Stop,立刻按 5 步)**:

1. 身份:核对 / 补 `att start <aoneId> --emp-no <工号> --agent-id <agent名>`(aoneId 只取当前明确上下文或用户回答;工号自动识别,绝不臆测 / 占位)。
2. `att index` → 首行回显 `# session: <sid>`。**0 事件 = 多半选错会话**;大会话 stdout 自动精简成候选边界(非全部事件),全量在回显的 `index.txt`(**最新事件在末尾**)——逐事件读该文件或 `--full`,别因没在 stdout 看到最新 seq 就反复重跑测试。
3. 在索引上定边界,cases 草稿写到 `~/.att-tf/cases/<sid>/cases.json`(JSON 数组)。若已有测试用例文档/脑图/testflow case,先沿用原 `caseTitle/description/priority/groupPath`,只补 `status/errorMessage/seq`。若前一轮调用本 skill 后被 compaction 打断且没写出 cases,先试 `att report --resume <sid>` 从 transcript 恢复草稿。
4. 自动记录 `att checkpoint --stage reporting --clear-case`，再跑 `att report --dry-run`(不带 sid 自动定位;复核边界 / status,不发网络)。
5. `att report`(无误真发 testflow；成功后客户端自动写 Case 最终裁决、报告回执与 Run completed，不因失败用例把 Run 标 execution_failed)。

---

## Codex 受限沙箱（仅工具支持时）

- 首次直接提权：`att index` 用 `prefix_rule=["att", "index"]`；dry-run/正式 report 共用 `prefix_rule=["att", "report"]`；均传 `sandbox_permissions="require_escalated"`，理由为允许管理 `~/.att-tf`。
- 不先普通执行失败再重试，不得使用 `prefix_rule=["att"]`。无沙箱/已有权限/不支持参数则普通执行；拒绝授权就停止，不删锁、不绕过审批。
- cases 写工作区后用 `--cases` / `--cases-stdin`，不扩大编辑权限。

---

## 机制(一句话)

att-tf 不是零接管拦截器,**靠你声明测试会话**:只装 Stop + SessionStart 两个 hook,execLog / 截图 / 耗时在 `att report` 时**从 transcript 机械重建**——你无法伪造、也不用管。你唯一要做的:把「测了什么、过没过」这层只有你懂的语义定边界写成 cases。

实时过程同样只认 Agent 显式 checkpoint：准备/进入或切换 Case/等待/采证/裁决阶段由 att-start 注入的规范要求你自动调用；本 skill 接手后先写 `att checkpoint --stage reporting --clear-case`。用户不手工操作，CLI 也绝不从 transcript 或最终 cases.json 猜当前阶段/Case/百分比。

### inline / delegated 两种报告模式

- **inline 模式**：执行测试的父 Agent 在原会话内按现有流程运行 checkpoint、index 与 report。这是所有平台的默认路径。
- **delegated 模式**：只有宿主具备可靠侧边任务/子 Agent 能力时，父测试 Agent 才可把平台无关来源句柄
  `source_sid + source_run_id + source_aone_id` 交给 worker。worker 必须显式使用原来源，先运行
  `att checkpoint --sid <source_sid> --run-id <source_run_id> --aone-id <source_aone_id> --stage reporting --clear-case`，
  最终运行
  `att report <source_sid> --run-id <source_run_id> --aone-id <source_aone_id>`；禁止自动定位 worker 自己的 sid，
  也不得假设 worker 自己拥有或共享父会话 transcript。CLI 会用 `source_sid` 读取既有绑定的 transcript_path，
  并把 run_id/aoneId 仅作为 expected identity guard；任一不匹配立即拒绝，不发现、不切换绑定、不写状态、不发网络。
- **跨平台边界**：Qoder、QoderWork、Codex、Claude Code 共用上述句柄契约；平台 adapter 只负责是否能发起委托。
  不具备侧边任务/子 Agent 能力或委托失败时，回退 inline 模式。委托失败不猜
  `execution_failed/cancelled`，原 Run 留待重试并由 Hub 后续显示 idle/stale。

**别等 Stop 提示**:Stop 的软提示只是兜底(绝不 block,你忙别的时可能滑过)。判断测试已跑完(命令跑完 / 断言出结果)的当下就上报——测试与上报常在同一会话闭环,而 Stop 在会话结束才触发,对单会话闭环无效。**唯一例外(flush 优先)**:若 `att index` / `att report` 打出 `[⚠ transcript 可能未 flush]`,说明本 turn 测试事件尚未落盘,此时**别立刻定版**,把上报挪到**下一个 turn(新 prompt)**再做(见 ③ flush 项与 ④ 复核区)。

## 第一性原则(红线)

- **必须真执行**:跑命令 / 调接口 / 点页面 / 断言;描述 ≠ 执行。
- **status 反映真实验证**(判据=「执行了没」):`1` 真执行 + 断言全过;`2` 真执行但断言不过 / 报错(500 / 返回不符 / 抛异常);`3` 根本没执行(环境 / 前置 / 依赖缺失 / 主动跳过)。易混:环境起不来没跑成 → 3;跑了结果不对 → 2。只有证据支持才填 1,注水会被 execLog 对账判假阳。
- **用例定义不得被执行总结污染**:有原始测试用例(文档/脑图/testflow case/用户给出的 case 表)时,`caseTitle` 必须**逐字沿用原文**(连标点措辞都别改——它是同一需求跨轮对账的身份键,改一个字第二轮就和第一轮对不上、看板里同一条用例裂成两条);`description`/`priority`/`groupPath` 也是用例定义,必须优先原样沿用或等价保留;不要为了说明本次怎么跑,把 `description` 改成执行日志、实际结果摘要、个人总结、环境说明。执行过程和证据由 att-tf 从 transcript 重建;结果差异只放 `status` 和 `errorMessage`(失败时):**发现真缺陷 = `status` 必为 2,绝不判 1 通过却把缺陷写进 `errorMessage`(自相矛盾的假阳通过)**。
- **绝不伪造证据**:截图只来自真实图像(浏览器 / GUI / 截图工具的图像文件 / 内联图)。纯 CLI / 接口测试本就无图、以 execLog 为主证据,**截图为空 ≠ 缺陷**;**绝不**打印「格式化文字框」冒充截图(= 造假)。
- **身份必须真实**:见 ② 身份门(aoneId 来自当前明确上下文或用户回答、绝不臆测、绝不占位)。

## ① 判是不是测试

跑命令 / 调接口 / 点页面 / 断言才算;纯设计 / 闲聊 / 写代码不算。

- 不是 → `att mark-handled <sid>` 标记已处理(免 Stop 反复 nudge),干净结束,不上报。
- 是 → 继续 ②,**立即**走流程(别等会话结束 / Stop 提示;**也别反问用户「要不要上报」,直接做**——只在缺 aoneId 等硬性信息时才问,见 ②;自查可 `att pending`)。

## ② 身份门(report 前必须真实)

开场理想已由 att-start 声明;忘了**现在补 `att start` 即可**——证据是 report 时从 transcript 重建、不依赖 start 时机,事后补也能正确出报告(仅损失 `--since` 便利,见③)。

- **`aoneId`(需求 ID,唯一硬门)**:优先从当前用户消息 / 最近明确上下文 / Aone 需求链接里提取唯一明示 ID,能唯一确定就直接补 `att start`;没有 / 多个 / 不确定才问用户。只认用户明确说的「aoneId / 需求 ID / Aone 需求链接」里的唯一值;不要把 testflow caseId、bugId、订单号、工号、traceId、分支里的日期/需求号片段当 aoneId。绝不从 git 分支名/目录名/commit、历史会话、identity 缓存沿用(每次测的是不同需求)。**aoneId 只问一次**:用户**明确**表示没有 / 无需上报测试证据 → 不再追问、不跑 att-start、按原 prompt 继续,并一句话告知本次无 testflow 证据上报。
- **工号 `empId` / 名字**:可选,优先 agent 自找(显式值/env `ATT_EMP_NO`/安装期或历史缓存/BUC(A1) 登录态自动识别),找不到留空;`att install` 会 best-effort 做一次身份缓存,只保存工号/姓名、不保存 token。绝不用 whoami/系统用户名/占位值顶替。
- **agent 名 `agentId`**:你自己填原始执行 agent 名(或 env `ATT_AGENT_ID`);上传 payload 会由 CLI 自动转成 `<agentId>-att-report`,用于标识 att-report 直报链路。
- **🚫 占位红线**:用户说「继续/跑一遍」≠ 让你用假值把流程跑通——没真实身份先问。att-tf 对占位 aoneId/工号在 start 与 report 各 LOUD 警告一次:看到 = 你在用假身份,立刻停下问用户(server 也会以「can't find the issue by id」拒)。

```
att start <aoneId> --emp-no <工号> --agent-id <你的agent名>   # 例 --agent-id claude-code
```

工号 / 名字可走缓存(att-start 已确认时),**aoneId 只能来自当前明确上下文或用户回答,永不走缓存**。

## ③ 定边界 + 写 cases

`att index`(不带 sid 自动取当前会话、首行回显 `# session: <sid>`,后续 report / mark-handled 都用它;显式指定才 `att index <sid>`)。在 preview 索引上定每条用例的 `seq_from..seq_to`(闭区间),pass / fail 由你的本会话上下文裁决(你最准)。

- **🚫 seq 铁律(最易犯的致命错)**:`seq_from`/`seq_to` = `att index` 索引里每个事件行首的 `[seq]` **事件序号**(transcript 归一化事件流里第几个事件),**不是用例第几条、不是 TC-001 编号里的 1、不是 results 数组下标**。严禁 `seq_from=seq_to=用例序号`(如 TC-003 填 3)这种填法——那会把所有用例的证据窗口塌缩、重叠到 transcript 头部,自动扫描会把同一批内联图串给所有用例,看板里这些用例图一模一样(report 907 事故根因)。每条用例的 seq 区间必须照着 index 里真实事件序号定。
  - **并行 / 多 Agent 同会话**:各用例的 tool_use / tool_result 在时间线上天然交叉(如 33 C4·use / 34 C5·use / 35 C4·result / 36 C5·result),不存在互不重叠的连续区间。att-tf **默认零配置**按 `tool_use_id` 把切片内孤儿 result(其 tool_use 落窗外)的 tool_use + 入参自动补回证据(标 backReferenced),你照常定连续区间即可;若想让每条用例证据**互不重叠**,可选 `seq_exclude`(整数数组)列出落本案窗口内但属别 Agent 的 seq 剔除(如 `seq_from:33, seq_to:35, seq_exclude:[34]` → 证据 {33,35})。

- **0 事件 / 疑似选错会话**:多宿主下选错会话或空会话——先核对回显的 `# session: <sid>` 是否本会话,必要时显式 `att index <正确sid>`,别拿空证据上报。
- **大会话自动精简**:超窗时 stdout 只出候选边界概览(att-tf **主动精简、非宿主截断**),**不是全部事件**;全量始终写到 `~/.att-tf/cases/<sid>/index.txt`(首行回显路径)、**最新事件在文件末尾**——逐事件定边界请 Read 该文件或 `att index --full`。别因 stdout 没看到最新 seq 就以为没采到、反复重跑测试(最大时间浪费源)。
- **transcript 按 turn flush(硬信号优先)**:宿主按 turn 缓冲落盘,同一 turn 内既测又 `index`/`report`,本 turn 刚产生的事件可能还没刷进 JSONL、索引/上报看不到。不是 bug,但**会定版到不完整证据**(上下文只到前导段 + 多用例被迫共享满窗口致时长虚高)。**判据不靠你肉眼数事件,靠工具硬信号**:`att index` / `att report` 检测到「最新事件距今过久」会打 `[⚠ transcript 可能未 flush]` / `ⓘ transcript 可能未 flush`。**见到该提示 = 本 turn 测试事件尚未落盘,必须在下一个 turn(新 prompt)重跑 `att index` + `att report` 再定版,别无视、别照旧上报**(事后补报旧会话才可忽略)。把上报当测试之后的独立一步。
- **`--since`(大会话减负)**:`att index --since <ISO时刻>` 只索引该时刻后的事件,并标 `# >>> run 起始边界`。**仅当开场就 start 过**时用(传那次 start 时刻);②里事后补的 start 时刻晚于全部事件,用了会把整场过滤光——那就直接 `att index` 看全量。
- **红线(第一条 prompt 契约)**:证据下界 = **会话起点**,不是 start 时刻;用户第一条 prompt 是需求本体,必须纳入(会话级背景或首条用例 `seq_from` 起点)。`# >>> run 起始边界` 是标注非过滤,别漏边界前的首 prompt。

**cases 落盘**:必须 `~/.att-tf/cases/<sid>/cases.json`(不是 `<sid>.json`,否则判「无 done marker」拒收);格式为 JSON 数组 `[{...}]` 或 JSONL(每行一对象),别的格式不收。

**受限宿主(写不进 home,如 IDE 沙箱)**:cases 写到工作区任意可写路径,再 `att report --cases <该路径>`;或不落盘直接 `cat cases.json | att report --cases-stdin`(绕 done-marker,须完整成品)。

**compaction 恢复**:若 inline skill 刚启动就被上下文压缩打断,`cases.json` 可能还没写出,但宿主 transcript 里通常已有 `Skill(att-report,args=...)` 入参。此时跑 `att report --resume <sid>`:
- 若恢复出的 cases 已含 `seq_from/seq_to`,CLI 会写回 `cases.json` 并继续上报。
- 若缺 seq,CLI 只写 `~/.att-tf/cases/<sid>/cases.resume.json` 和 `report_state.json`,不会猜边界、不会上传半成品。你需要 `att index <sid>` 定边界,把草稿补齐为 `cases.json`,再跑 `att report --resume <sid>`。

**用例定义来源优先级**:

1. 已有测试用例文档/脑图/testflow case/用户给出的 case 表 → `caseTitle`/`description`/`priority`/`groupPath` 从原定义取,不要自行改写语义。
2. 原定义只有标题没有完整描述 → 可补齐 `description`,推荐写成 JSON 对象 `{"preconditions":[],"steps":[],"expectedResults":[]}`;只写测试设计本身,不要写本次实际返回、planId、traceId、DB 结果等执行摘要。
3. 本次临时探索出来的新 case → 可以新写标题/描述,`description` 优先用同一 JSON 对象格式;必须标明它是新增/补充用例,不要冒充原用例。

**执行结果放哪里**:

- 通过/失败/跳过放 `status`。
- 失败原因放 `errorMessage`。
- 真实命令、接口响应、截图、耗时由 att-tf 自动从 transcript 附到 execLog/证据里。
- planId、traceId、DB 回查值等只作为证据留在 execLog;除非原测试用例描述本来要求这些变量,否则不要塞进 `description`。

每条用例对象:

```json
{"seq_from":12,"seq_to":28,"caseTitle":"下单-优惠券抵扣正确","description":{"preconditions":["满100减20券"],"steps":["加购100元","下单","选券"],"expectedResults":["实付80"]},"status":1,"priority":"P1","groupPath":"交易/下单/优惠","errorMessage":""}
```

status=2 失败可带 errorMessage + 可选 issues 关联 Aone bug:

```json
{"seq_from":30,"seq_to":45,"caseTitle":"库存0仍下单(超卖)","status":2,"priority":"P0","groupPath":"交易/下单/库存","errorMessage":"实际:库存0仍下单成功,未拦截","issues":[{"name":"库存超卖","bugId":"12345","bugUrl":"https://aone.alibaba-inc.com/.../bug/12345","description":"未校验实时库存"}]}
```

并行 / 多 Agent 同会话,想让证据互不重叠时用 `seq_exclude` 剔除窗口内属别 Agent 的 seq(34 是另一 Agent 的事件):

```json
{"seq_from":33,"seq_to":35,"seq_exclude":[34],"caseTitle":"商品详情-规格切换","description":{"steps":["切换规格"],"expectedResults":["价格随规格更新"]},"status":1,"priority":"P2","groupPath":"商品/详情/规格","errorMessage":""}
```

字段:

- `seq_from` / `seq_to` 区间(看 index 的 `[seq]` 事件序号,见上「seq 铁律」)。**多条用例共享同一 seq 区间是带强约束的**:仅当这些用例**本就无独立截图**(纯接口 / CLI 批量验)时才可共享;**只要用例有截图,必须各自填精确、互不重叠的 seq**——否则 att-tf 自动扫描会把同一批内联图串给多条用例,看板里这些用例图会一模一样(report 907 事故)。
- 可选 `seq_exclude`(整数列表):并行 / 多 Agent 同会话时,剔除落本案窗口内但属别 Agent 的 seq(见上「seq 铁律」并行项,如 `seq_from:33,seq_to:35,seq_exclude:[34]`);不填则默认按 `tool_use_id` 自动配对兜底,无需关心交叉。
- **skipped 用例复用窗口约束**:多条 `status=3` 用例只有在**同一阻塞原因**时才可复用同一个 `seq_from..seq_to` 和同一个 `errorMessage`;若不是同一阻塞原因,必须拆分 seq 边界或写出差异化 `errorMessage` 后再真发。dry-run 出现「N 条 skipped 用例复用同一证据窗口 seq X..Y 且 errorMessage=...」提示时,先按这条复核。
- 必填 `caseTitle` / `description`(用例定义里的前置 / 步骤 / 预期,优先沿用原文;无原文时优先 JSON 对象 `preconditions`/`steps`/`expectedResults`,CLI 上报前会压成紧凑 JSON 字符串) / `status` / `priority`(P0~P3) / `groupPath`(`/` 分层);`errorMessage` 仅 status=2 填。不要把 `description` 写成「本次执行:xxx;实际:xxx」的总结。
- **不要写** `execLog` / `screenshots` / `duration`——CLI 从真实 run 机械附(手填会被覆盖)。
- **条件必填** `screenshotPaths`(绝对路径数组,如 `$PWD/shots/tc003.png`):
  - GUI / 浏览器 / 移动端云真机 / 任何外部截图工具(Playwright `page.screenshot(path=)`、playwright-cli、adb、scrcpy 等)产出的截图 = 落在磁盘、transcript 里**只有路径没有图像** → **必须**在对应用例显式填,否则该用例要么没图、要么被自动扫描串入别的用例的内联图(与自动采集合并去重)。
  - 纯接口 / CLI 测试本就无图 → 留空正常(截图为空 ≠ 缺陷)。
  - 浏览器 / GUI **内联进 transcript** 的图(att-tf 能直接抓到)无需手填——但**多用例共用同一段内联图时仍要靠精确 seq 区分**(见上 seq 铁律),否则串图。
- 可选 `issues`(仅 status=2):关联你已提的 Aone bug,`bugId` 是纯数字(无 `BUG-` 前缀);没提就不写。与 errorMessage 互补(errorMessage 说为什么挂、issues 指向 bug)。**失败用例(status=2)必须提 bug**:用 `att submit-bug` 提的 bug 会**自动回填**进对应用例的 `issues`,**无需手抄**到 `cases.json`;dry-run 复核时 att-tf 会**强提醒**未关联 bug 的失败用例(只提醒、不阻断正常上报、不改 exit code)。提 bug 时若用户未明确指定指派人 → 默认提给自己(本会话工号),见 aone-bug-submit skill 指派人规则。
  - **dry-run 四态提示要区分**:① 已关联 bug(issues 有值)=正常;② **未关联 bug**(从没提过)→提醒去 `att submit-bug` 提单;③ **状态未知(pending)**——已提交但远端结果未确认→去 Aone 核对是否已建、**勿重试**;④ **明确拒绝(rejected)**——已尝试且服务端确认未创建→按显示的原因修正,获得用户明确授权后才能再提交。③ 的重复风险高于④；两种记录并存时先按③查重。

> **截图别手动 curl**:上传由 `att report` 接管(transcript 重建 + 落 OSS),别按其它 skill 手动传到别的端点(重复无效)。**移动端云真机 / 点点助手**:截图在外部 OSS,agent 只拿到文字报告 + 链接(`…/report_24121.html`),att-tf 已自动把链接当 URL 型截图采进 `screenshots`(看板内网可点)——你别手动下载、别打印文字框冒充;断言以文字 / 接口返回为准,把「观察到 XXX」写进 `description`。

## ④ 复核 + 真发

```
att report --dry-run    # 自动定位 sid;逐条精简复核(seq/status/证据量/execLog 预览,对账边界与证据)+ 裁决前置,不 POST
att report              # 无误真发(唯一碰网络处);显式历史会话才 att report <sid>
att report --resume <sid>   # compaction 后 cases.json 缺失时,从 transcript 恢复 /att-report 入参草稿
att report --dry-run --full   # 需逐字节看完整 payload 原文时(默认精简已够复核;原文含 execLog 全文+内联图,受限 stdout 宿主慎用)
att report <sid> --force   # 仅确需无条件重传时;必须显式 SID,会失效同身份旧 bug_links
```

- **重传边界**:正常修改 case 语义后 CLI 会靠 revision 自动重传，不要习惯性加 `--force`。确需 force 时先复核 `issues`：旧 `bug_links` 自动关联会被失效，cases 里手写的 `issues` 保留。
- **串图自检(真发前必查)**:dry-run 复核时若看到「GUI 用例却 `截图×0`(明明截过)」或「多条用例 screenshots 完全相同」或 att-tf 打出 `[⚠ 串图] …` 警告 → 说明 seq 当用例号填了 / 漏填 `screenshotPaths`,**先修正再真发**(att-tf 新版会对自动扫描产出的相同图 LOUD 警告)。

## 收尾

成功即完成,服务端做三态诚实度研判汇入看板。缺凭证(AK/SK) / 身份会进 pending,补齐重跑 `att report` 幂等安全。

收尾后留意 `att report` 真发成功的输出:**若它提示你写体验反馈,务必接着调 `/att-feedback`**——你刚完整用过 att-tf、上下文最全,是最佳报告人:顺利就如实写顺利+亮点,有摩擦往下挖根因,**别跳过**(开发者靠它迭代)。是否提示由 att-tf 按反馈级别决定(off/logs 级不提示,你无需自己判级别——看输出即可)。

- **报错读法**:真发回「查询Issue失败 / can't find the issue by id」——「Issue」就是你传的 `aoneId`,多半 aoneId 不存在 / 无权限 / 用了占位值;别改别的、别 mock,核对真实 `aoneId` 再重跑(att-tf 也会附同义提示)。
- **截图上传失败兜底**(受限网络 hub 不可达):用例照常上报成功,失败截图字节本地留存;网络恢复跑 `att upload-evidence <sid>`(sid 见 index 首行)补传,或 config.local 配 AK/SK 直连 OSS。
