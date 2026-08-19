# 机器人/cron 任务审计细则（v1.1 扩展）

机器人/cron 任务运行在独立会话，通常不加载 att-start/qa-self-healing，没有 gap 台账——**以 transcript 事后复盘为唯一主证据**，辅以 cron 配置与产物落盘检查。

## 采集路径（全程只读）

1. **枚举任务**：`qw_query qoderwork.tasks`（params: limit/status/时间窗），筛出 cron 与机器人来源的任务（看 chatType/sourceChatId/name）。
2. **拉执行记录**：对目标任务 `qoder_get_task_detail`（分页，limit≤10），从消息与工具调用中找问题点：
   - 工具调用 result 报错、同一命令反复重试
   - 异常终止（无完成标志/无产物）
   - 卡在权限/AskUser 等待无人响应
   - 降级痕迹（"改为手动""跳过""忽略错误"）
3. **对照 cron 配置**：`qoder_cron list` 取每个 job 的 payload.message / schedule / missedRunPolicy：
   - payload 引用的 skill 是否已变更版本（对照 `~/.qoderwork/skills/{name}/SKILL.md` frontmatter）
   - payload 描述的流程是否与当前 skill 内容一致（如引用的路径/编号/群目标）
   - missedRunPolicy 是否与任务性质匹配（资金/对账类应 run_latest 或 prompt，纯报表类可 skip）
   - **模型配置漂移**：`scheduled_tasks.model`（agents.db）或 payload 指定的模型是否已被后端移除。典型症状：机器人/任务一开口即 `BAD_REQUEST 100404 Specified custom model have been removed`（如 qwen3.8-max-preview 下线案例）。核查三处落点：`app_settings.modelLevel`（应用默认）、`sub_chats.model_level`（单会话）、`scheduled_tasks.model`（定时任务）；有效值为 qwork-auto / qwork-advanced / qwork-ultimate 等平台在册档位，preview 类实验模型随时可能下线，cron 不应硬编码
4. **产物落盘检查**：预期产物（日报/summary/inbox JSON/报告文件）是否真实存在、时间戳是否符合调度周期——缺失 = 静默失败候选。

## G9 子类定义

| 子类 | 定义 | 典型信号 | 判定证据 |
|------|------|----------|----------|
| G9a | cron payload 与 skill 版本失同步 | skill 已升级（frontmatter 版本↑）但 payload 仍按旧流程描述 | payload 文本 vs skill frontmatter/正文 diff |
| G9b | 机器人推送目标错误 | 发向默认群/错误群（对照 MEMORY 红线：韩非子测试群禁发、目民001 推送须用户指定群） | transcript 推送目标 vs 用户指定/红线 |
| G9c | 定时任务静默失败 | 任务 failed/超时无告警无产物，下一周期照常 | 任务状态 + 产物缺失 + 无告警记录 |
| G9d | missedRunPolicy 配置不当 | 资金对账类配 skip、低价值轮询配 run_all | cron 配置 vs 任务性质 |
| G9e | 无人值守遇错即弃 | bot/cron 任务遇错不自愈不留痕直接放弃（G1 的无人值守版） | transcript 错误后无修复尝试即终止 |

## 修复路由

- G9a → 检测 T1 自动（T1-7 新鲜度检查），payload 内容更新走 **T2 合并协议**（先 qw_query 取当前 payload 最新版合并，勿整段覆盖，更新后必须 qw_query 复核 prompt 字段）
- G9b → P0，T2 草案（推送目标固化到 payload + 红线提示注入）
- G9c → T2 草案（补失败告警：任务收尾自检产物，缺失则 IM 通知）
- G9d → T2 草案（仅建议，改配置需用户确认）
- G9e → 视根因归并 G1/G2 修复路径，另建议 payload 注入 qa-self-healing 触发词
- 模型配置漂移（100404）→ 归 G9c/G9a 并案处理；修复默认 **T2 草案**（建议将 `scheduled_tasks.model` 改为 qwork-auto 或置空继承应用默认，改 agents.db 需用户确认）；用户已明确批准标准档位时按 T1 执行并复核任务下一次运行
