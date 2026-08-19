---
name: f88-strategy-test-run
description: 通过F88策略平台试运行API构造审核任务测试数据，是`审核数据构造`skill的方式一（首选）。输入文件固定用`审核专用模板.xlsx`，产出真实BT_批次、走完整workflow管线、UI图片正常显示（前提inputDatas图片URL有效；历史"灰色无图"是图片URL无效的输入问题，非试运行限制）。方式二手动创建API仅用于formal语义（自过滤等）验证。Use when constructing F88 review task test data via strategy test run (primary method), or verifying workflow pipeline end-to-end (template_match → gen_img → review).
version: 1.2.0
---

# F88 策略试运行造数

通过 F88 策略平台「试运行」API 触发策略执行，自动创建审核任务测试数据，产出真实 BT_ 批次、走完整 workflow 管线。是 `审核数据构造` skill 的方式一（首选）；方式二手动创建 API 仅用于需要 formal 语义（自过滤/ratio=0 等过滤规则生效）的单点验证。

## 脚本优先（v1.2.0）

**高频操作一律先跑脚本**，脚本固化了租户 header、inputParams 列过滤、批次轮询等踩坑经验；脚本失败才回退到浏览器 fetch 兜底（见 references/api-details.md）。

```bash
SCRIPT=~/.qoderwork/skills/f88-strategy-test-run/scripts/f88_review_data.py

# 试运行造数（默认读审核专用模板.xlsx，自动查 inputParams 过滤列，返回 batchId 并轮询）
python3 $SCRIPT trial-run --strategy 10834 --mode test

# 查批次状态 / 轮询到终态
python3 $SCRIPT batch-status --batch BT_7544 --watch

# 查策略 inputParams 与节点编排
python3 $SCRIPT strategy-info --id 10834

# 方式二：手动创建审核任务（仅 formal 语义验证，自动上传模板取 OSS URL）
python3 $SCRIPT create-task --node 168 --upload-xlsx /Users/caoxuemei/qoder/f88素材生产/审核专用模板.xlsx
```

前置：已登录的 Chrome 以 CDP 调试端口运行（端口自动探测 9223-9230，详见 web-automation skill 的端口自动探测逻辑，禁止写死 9222）+ web-automation 已 `npm install`（详见脚本头部说明）。脚本不可用时按 [references/api-details.md](references/api-details.md) 浏览器兜底。

## 适用场景

- 日常测试造数、链路级（E2E）验证（产出真实 BT_ 批次）
- 验证 workflow 管线完整流转（template_match → gen_img/gen_video → 审核）
- 测试 BATCH vs STREAM 执行模式差异
- 验证下游节点（抽检、分配）的流转逻辑

## 关键决策速查

| 决策点 | 结论 |
|--------|------|
| 策略选哪个 | 流式 10834 / 块式 10833（四节点全链路），详见 [references/strategies.md](references/strategies.md) |
| runMode 选哪个 | 验链路→`test`；验过滤规则（自过滤等）→`formal`，需要验什么场景就造什么场景 |
| 等多久 | STREAM 即时~10秒；BATCH 30-60秒（ScheduleX 攒批），formal 数分钟级——**不是不产出，别误判卡死** |
| 租户 header | 所有请求必须带 `X-AFD-Emp-Identity: f88`（脚本已固化） |
| 审核人 | 必须填目民（emp 526043）——红线 |

## 验证造数结果

脚本返回 batchId 后，按 [references/verification.md](references/verification.md) 做 UI 验证（个人任务中心搜批次号）+ DB 三层结构验证（g_workflow_batch → workflow_record_log → g_afd_review_job，走 dms-alibaba stylespot 组）。

## 知识引用

| 需要什么 | 读哪个文件 |
|---------|-----------|
| API 细节 + 浏览器兜底 | [references/api-details.md](references/api-details.md) |
| 策略速查 + 执行模式 + 常见错误 | [references/strategies.md](references/strategies.md) |
| 造数结果验证 SQL/UI | [references/verification.md](references/verification.md) |
