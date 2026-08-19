# 已知问题模式与风险感知

> 从 SKILL.md 提取的已知问题速查表和风险提醒。遇到相关症状时按需读取。

## 已知问题模式速查

| 问题编号 | 根因 | 关键特征 | 影响 | 处置 |
|---------|------|---------|------|------|
| BT_6148 | replaceImage 只更新 g_afd_material.url，未回写 g_afd_review_job.info | BATCH 模式 approve 拿老 URL，STREAM 正常 | 下游拿到过期 URL | 修复回写逻辑或切换 STREAM |
| BT_5976 | 5 类素材操作中约 4 类未传 subJobId | g_afd_material.sub_job_id 为空 | 链路追踪断裂 | 修复参数传递 |
| BT_6149 | 预发 Nginx 未配置 COOP/COEP 响应头 | Console 报 SharedArrayBuffer / ffmpeg-wasm 加载失败 | 客户端视频编辑器不可用 | 配置 Nginx 响应头 |
| BATCH 卡死 | 预发 SchedulerX 未运行 | BATCH 模式批次卡在 COLLOCATION/approve/HANDLING 无限期 | 批次无法推进 | 改用 STREAM 模式 |
| BT_7495 | 审核任务分配算法整除/取余校验不一致 | 审核环节记录全部 INIT（runningCount=0）、前台无审核任务、errorMsg 含"期望分配数量与实际分配数量不一致"、手动 triggerApprove 也失败 | 整批审核任务无法创建 | 已修复（2026-08-05）；遇此先确认修复是否已部署，临时可调整参与人配置使总量整除 |
| BT_7485 | 审核回调三条件缺失（子任务+抽检完成/runMode 开关/MQ 发送） | 审核已完成但批次不流转；主任务 status=4 为抽检中属预期等待 | 批次卡在审核环节 | 按三条件逐项排查，抽检未完成属预期，勿误判为故障 |
| 单模型集中失败 | 模型服务端不可用（账号欠费/配额），非链路 bug | 单一模型失败占比 >80% 且 >100 条，重试后仍同样失败（如 gemini-3.1-flash-image-preview 案例） | 该模型任务全量失败 | 停止盲目重试，转外部依赖告警（idealab），切换模型 |

## replaceImage 风险感知

当用户提到"替换图片""replaceImage""换素材"等操作时，需主动提醒：

1. **BATCH 模式风险**：replaceImage 只更新 g_afd_material.url，不会回写 g_afd_review_job.info 快照。如果批次是 BATCH 模式，approve 节点仍会使用旧 URL。
2. **验证方法**：操作后执行跨表一致性检查（工作流 6 Step 2-3），确认 snapshot URL 与 material URL 一致。
3. **缓解措施**：对需要 replaceImage 的场景，建议使用 STREAM 模式策略。

## 版本动态

### v3.2.2（Aone 85010050，提测中，来源 features/15-strategy-platform-v3.2.2.md）

分支 feature/20260812_30719664_v3.2_sp_1，应用 stylespot-admin。发布后运维口径需注意：

1. **链路/策略新增挂起状态**：`LifeCycleEnum.SUSPEND`（"suspend"）。g_link.life_cycle 出现 suspend 属合法值，不要误判为异常配置；挂起链路不应再产生新批次，若挂起链路仍有 PROCESSING 批次需提醒用户确认。
2. **节点类型按租户过滤**：`TENANT_NODE_TYPE_CONFIG` switch 控制 `getNodeTypeEnums()` 返回，不同租户可见节点类型不同；排查"节点类型缺失"类问题先确认租户配置。
3. **策略环节枚举收敛**：`getForStrategyPlatform()` 仅返回 COLLOCATION/VIEW/SET/VIDEO 4 类，历史 10 类枚举中其余类型在策略平台隐藏（仍存在 DB 中，属预期）。
4. **生产看板新增超时统计**：`MaterialSupplyStat.prodTimeOutCount` / `auditTimeOutCount`，巡检健康度时可直接消费。
5. **列表筛选增强**：策略/链路列表支持按 id、提交人（submitterId/submitterName）筛选。
