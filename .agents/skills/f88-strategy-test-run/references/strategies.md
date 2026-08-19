# 策略速查与执行模式

## 常用造数策略（审核专用）

| 策略 ID | 名称 | 执行模式 | 审核节点 |
|---------|------|---------|---------|
| **10833** | mmtest审核--块式 | BATCH | 模板审核(138) → 首图审核(168) → 套图审核(139) → 视频审核(144) |
| **10834** | mmtest审核--流式 | STREAM | 模板审核(138) → 首图审核(168) → 套图审核(139) → 视频审核(144) |

## 其他常用策略

| strategyId | 名称 | 节点组合 | 模式 |
|-----------|------|---------|------|
| 10817 | mmtest首图&套图审核--流式 | 168(首图,q4) → 139(套图,q2) | STREAM |
| 10816 | mmtest视频&模板审核--流式 | 144(视频,q3) → 138(模板,q5) | STREAM |
| 10814 | mmtest首图&模板审核--块式 | 168(首图,q4) → 138(模板,q5) | BATCH |
| 10812 | mmtest视频&套图审核--块式 | 144(视频,q3) → 139(套图,q2) | BATCH |

## 执行模式差异

| 模式 | 策略示例 | 首个节点状态 | 审核任务生成时机 |
|------|---------|-------------|----------------|
| STREAM（流式） | 10834, 10817, 10816 | 立即 HANDLING | 即时（记录到达即创建，~10秒） |
| BATCH（块式） | 10833, 10814, 10812 | 先 TO_SUBMIT → 批提交后 HANDLING | 批提交后创建（30-60秒，等 ScheduleX 攒批） |

**批提交由 ScheduleX 定时器 `ApproveTaskGenProgressJob` 周期扫描驱动**；formal 与 test 都靠它，
formal 需等定时周期、审核任务出来要数分钟级，**不是不产出**——等待时不要误判"卡死/产不出"。

## runMode 选择

`runMode` 有 `test` 与 `formal`，**需要验证什么场景就造什么场景的数据，不一律固定**：
- 验过滤规则（自过滤等 formal 语义）→ `formal`
- 验链路（test 语义：抽检人可=审核人、走通全链路）→ `test`

## xlsx → inputDatas 映射规则

| xlsx 列名 | 对应 inputParam code | 说明 |
|-----------|---------------------|------|
| seller_id | seller_id | 商家ID |
| seed_image_url | seed_image_url | 种子图URL |
| main_img_url | main_img_url | 主图URL |
| fabric_tryon_url | fabric_tryon_url | 面料试穿图URL |
| fabric_url | fabric_url | 面料图URL |
| item_id | item_id | 商品ID（部分策略需要） |
| tao_cate | tao_cate | 淘系类目 |

**不同策略的 inputParams 不同**，脚本会自动从 `/api/workflow2/strategy/get` 获取并按 code 过滤。
固定输入文件：`/Users/caoxuemei/qoder/f88素材生产/审核专用模板.xlsx`（5 行数据，列名全匹配）。

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| inputDatas 字段不匹配 | xlsx 列名与策略 inputParams code 不一致 | 先查 strategy-info 获取 inputParams |
| 返回 success:false | 策略不存在或未发布 | 确认策略 ID 和状态 |
| 批次创建成功但无审核任务 | workflow 管线未跑完 | 查 workflow_record_log 状态，STREAM 即时、BATCH 需等批提交 |
| 请求没落到 f88 租户 | 未带 `X-AFD-Emp-Identity: f88` header | 脚本已固化该 header；手写请求必须加 |
| UI 灰色无图 | inputDatas 图片 URL 无效（404/不可达） | 输入数据问题，非试运行限制；换有效图片 URL |

## 常用 nodeId / questionType

| nodeId | 审核节点 | questionType |
|--------|---------|-------------|
| 168 | 首图审核 | 4 |
| 139 | 套图审核 | 2 |
| 144 | 视频审核 | 3 |
| 138 | 模板审核 | 5 |
