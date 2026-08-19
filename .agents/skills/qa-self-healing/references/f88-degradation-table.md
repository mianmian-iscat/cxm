# F88 高频失败形态结构化降级表

> 定位：qa-self-healing 规则二（三层降级）与规则一（七步诊断）的**场景化路由**。
> 遇到下表失败形态时，先按"识别特征"对号入座，按"降级动作"顺序执行，超过"最大重试"立即切换下一动作；全部耗尽才按"终态"标注 BLOCKED 子类型。
> 仍须遵守规则零：任何降级前先查根因、尝试修复；降级报告必须写根因。

## 一、造数类失败

| # | 失败形态 | 识别特征 | 降级动作（按序执行） | 单项最大重试 | 终态 | 禁止行为 |
|---|---------|---------|--------------------|------------|------|---------|
| D1 | 试运行 API 返回失败 | `strategy/run` 返回 success:false | ① 核对 inputDatas 列名与 inputParams code（`strategy-info` 查）→ 修正重发 ② 确认策略已发布/未下线 ③ 换同类型策略（10834↔10833） | 3 | BLOCKED_LOGIC | 不查 inputParams 盲目重发 |
| D2 | 批次创建成功但无审核任务 | batch 有记录，review_job 0 条 | ① STREAM 等 10s / BATCH 等攒批周期 30-60s（formal 数分钟）② 查 workflow_record_log 首节点状态（TO_SUBMIT=等批提交，HANDLING=正常）③ 查 ScheduleX `ApproveTaskGenProgressJob` 是否在跑 | 轮询 3 轮 | BLOCKED_ENV | 等待期内误判"卡死"并重复触发新批次 |
| D3 | 审核任务 UI 灰色无图 | 任务存在但图片不显示 | ① 查 review_job.info 快照中 imgUrl 是否 404/不可达（curl -I 验证）② 输入图片 URL 无效 → 换有效 URL 重新造数 ③ dataFileUrl 为 null（方式二路径）→ 改用方式一策略试运行 | 2 | BLOCKED_DATA | 把输入数据问题当成平台 bug 提报 |
| D4 | 手动创建审核任务失败 | `task/main/create` 报错 | ① 检查 dataFileUrl 是否为有效 OSS URL（先 /api/file/upload）② 核对 nodeId 与 standardIds 匹配 ③ 确认审核人填目民 526043 ④ 降级走方式一策略试运行 | 3 | BLOCKED_LOGIC | 审核人填其他工号 |
| D5 | 模板包数据单一/缺失 | 用例需要的 cateId/styleTags 无模板包 | ① `f88-template-package-create` 造多 cateId 模板包 ② 换已有模板包覆盖的类目改用例 ③ qa-data-preflight 预检补造 | 3 | BLOCKED_DATA | 用单一模板包硬跑所有类目用例 |

## 二、环境/工具类失败

| # | 失败形态 | 识别特征 | 降级动作（按序执行） | 单项最大重试 | 终态 | 禁止行为 |
|---|---------|---------|--------------------|------------|------|---------|
| E1 | Chrome 调试端口不通 | 脚本报 fetch failed / 9223 无监听 | ① 扫描 9223-9225 找已有调试 Chrome ② 按 skill 文档启动调试 Chrome（已登录 profile）③ 降级浏览器扩展通道（builtin_browser）④ 纯 API 用例改 curl+cookie | 2 | BLOCKED_ENV | 无端口时反复重跑 CDP 脚本 |
| E2 | 登录态失效 | check_login 落到 BUC/登录页 | ① 提示用户在调试 Chrome 手动登录（一次性）② 换已登录的浏览器通道 ③ 无交互能力时标 BLOCKED_ENV 并记录断点 | 1 | BLOCKED_ENV | 伪造登录态或绕过 SSO |
| E3 | DMS 查询 20s 超时 | sql query 超时退出 | ① 检查是否漏 `id > 4000000`（workflow_record_log 必加）② 加 `env='staging'` 缩小范围 ③ JOIN 拆两步单表查 ④ 窄时间窗/窄 batch 分段 | 3 | BLOCKED_ENV | 裸查 workflow_record_log 全表 |
| E4 | DMS 结果超 200 行 | 提示结果已截断/落盘 | ① 改聚合 COUNT/GROUP BY ② 改 `sql run` 读结果文件 ③ 分页（ROW_NUMBER 确定性分页） | — | — | 直接相信截断后的部分结果 |
| E5 | EBADF / fd 泄漏 | spawn EBADF | 见 SKILL.md 已知不可自愈错误速查表：告知用户重启 QoderWork；当轮可试子任务通道（子代理进程独立） | 1 | BLOCKED_ENV | 同 session 循环重试 Bash |
| E6 | MCP 工具权限不足 | 403/无权限报错 | ① 按规则 2b 确认是否可申请 ② F88 场景降级 dms-alibaba CLI（f88-failure-analysis 本就禁用 MCP 走 CLI）③ 记录受限工具名 | 1 | BLOCKED_DEP | 静默换工具不记根因 |

## 三、链路/算法类失败（被测系统侧，判断是产品 bug 还是环境问题）

| # | 失败形态 | 识别特征 | 降级动作（按序执行） | 单项最大重试 | 终态/判定 | 禁止行为 |
|---|---------|---------|--------------------|------------|----------|---------|
| L1 | gen_img/gen_video 模型失败 | errorMsg 含 429/RESOURCE_EXHAUSTED | ① 判定 quota 耗尽 → 等待或换模型时段重跑 ② 单条重试该批次节点（strategy-platform 重试能力）③ 仍失败 → 真实问题，走 bug 草稿 | 节点重试 1 轮 | BUG（quota 类标 BLOCKED_DEP） | 把 quota 耗尽当脚本问题修 |
| L2 | 模型已下线 | errorMsg 含 model was deprecated/not found | ① 查 g_strategy.workflow_def 确认策略引用的模型 ② 模型下线但策略未更新 → 提 BUG（配置治理问题）③ 换用在线模型的策略重造 | 1 | BUG | 基于代码分支推断预发部署状态（必须查 DB；DB 不够时须到预发实操验证，禁止反问用户"要不要我去预发验证"） |
| L3 | CDN/OSS URL 失效 | AccessDenied / URL expired | ① 区分"URL 本身无效"vs"签名过期"：重查 DB 拿新 URL 再验 ② 仍无效 → 素材生产侧问题，提 BUG | 2 | BUG | 用过期签名 URL 下结论 |
| L4 | 记录卡 HANDLING 不动 | status=HANDLING 超阈值 | ① 查 g_admin_task：task_status=10 且 gmt_modified=gmt_create → TPP 从未回调（提 BUG）② approve HANDLING → 先查 review_job 抽检子任务（job_type=3/5, status=1）是否待处理，是则正常等待 ③ 查 SLS `sendWorkflowRecordFinishMsg` 消费日志 | — | 按证据定 BUG/等待 | 看到 HANDLING 就判"卡死" |
| L5 | 快照与实时 URL 不一致 | review_job.info ≠ g_afd_material.url | ① 确认 execMode：STREAM 下不影响 approve（非 bug）② BATCH 下 approve 读旧 URL → 提 BUG（参考 BT_6148）③ 用 T-15 模板批量扫 mismatch 面 | — | BUG/非 BUG 按 execMode | 不看 execMode 一律提 BUG |
| L6 | SharedArrayBuffer/COOP 报错 | errorMsg 含 SharedArrayBuffer/COOP | ① `curl -sI` 检查预发响应头 cross-origin-opener-policy/embedder-policy ② 头缺失 → 环境配置问题，提 BUG/找开发 ③ 头存在仍报错 → 收集浏览器环境证据 | 1 | BUG/BLOCKED_ENV | 无证据猜测环境正常 |

## 使用规则

1. **先对号再动手**：按识别特征匹配形态编号（D/E/L + 序号），在诊断报告中引用编号（如"按 D2 降级路径执行"）。
2. **重试预算独立计算**：每项动作的重试上限独立，但同一失败形态累计降级动作不超过表列项数；全部耗尽才标 BLOCKED。
3. **终态映射**：BLOCKED 子类型按 qa-self-healing 规则一 Step 7 的四分类标注（DATA/ENV/DEP/LOGIC），供 qa-data-preflight 与失败分析消费。
4. **表外形态**：未收录的失败形态走规则一七步诊断，事后把新形态补进本表（知识沉淀）。
