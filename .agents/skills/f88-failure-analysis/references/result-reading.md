# 结果文件读取与 Stage 3 归因报告

## 结果文件读取

dms-alibaba 查询结果保存在 `~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{日期}/{时间}_rm-lgay0v5lor8396yka.json`。

当终端输出被截断时（尤其是 extra_info、workflow_def 等大 JSON 字段），用 Python 读取完整结果文件：

```python
import json, os
result_path = os.path.expanduser("~/dms-alibaba/db-groups/stylespot/sql/quick_rm-lgay0v5lor8396yka/_results/{日期}/{文件名}.json")
with open(result_path) as f:
    data = json.load(f)
for row in data.get("rows", []):
    print(row)
```

## Stage 3 归因报告增强：BLOCKED 子分类消费

当本技能作为 5-Stage Test Resilience Pipeline 的 Stage 3 运行时，上游 Stage 0-1（qa-data-preflight）和 Stage 2（qa-self-healing）会提供 BLOCKED 子分类标签。

> **post_verify 三层验证归因提示**：Stage 2 造数步骤支持三层 post_verify（`type: db` → DataSetupVerifier / `type: ui` → UIVerifier / `type: code` → CodeVerifier），失败归因时可查看 `_post_verify.type` 字段判断是哪层验证失败。

### BLOCKED 子分类定义

| 子分类 | 含义 | 来源 Stage | 本技能归因动作 |
|--------|------|-----------|--------------|
| `BLOCKED_DATA` | 前置数据不满足 | Stage 0-1 | 查 Data Registry 造数记录，判断造数失败根因 |
| `BLOCKED_ENV` | 环境不可用 | Stage 2 | 关联环境状态日志，判断是宕机/网络/部署问题 |
| `BLOCKED_DEP` | 外部依赖缺失 | Stage 2 | 核查算法模型/第三方 API 可用性，关联模型下线检测（WF3 Step 5） |
| `BLOCKED_LOGIC` | 业务逻辑限制 | Stage 2 | 记录具体逻辑约束，标记为需人工介入 |

### 报告格式

```
测试报告摘要:
  总用例: 204
  PASS: 120 | FAIL: 15 | SKIP: 10
  BLOCKED: 59
    ├─ BLOCKED_DATA: 50 (84.7%)
    │   ├─ 造数恢复: 45 (Stage 1 自动补齐)
    │   └─ 仍阻塞: 5 (造数 skill 无法覆盖)
    ├─ BLOCKED_ENV: 3 (5.1%)
    ├─ BLOCKED_DEP: 4 (6.8%)
    └─ BLOCKED_LOGIC: 2 (3.4%)

  实际覆盖率: 135/204 = 66.2%
  潜在覆盖率(造数恢复后): 180/204 = 88.2%
  造数恢复率: 45/50 = 90.0%
```

### 三孤岛分布统计（评测体系增强）

> 对标《AI 应用评测方法与实践》三孤岛理论，将 FAIL/BLOCKED 用例按失败来源归类为三个鸿沟。

```
三孤岛分布:
  总失败/阻塞: 74 (FAIL: 15 + BLOCKED: 59)
    ├─ 理解鸿沟 (data):        32 (43.2%) — 数据源问题
    │   ├─ URL 过期/403:        18
    │   ├─ 商品数据缺失:         8
    │   └─ 离线数据未同步:       6
    ├─ 具象鸿沟 (prompt):      22 (29.7%) — 指令/配置问题
    │   ├─ 模型下线/废弃:       10
    │   ├─ 策略配置错误:         7
    │   └─ 模板匹配逻辑错误:     5
    └─ 泛化鸿沟 (engineering): 20 (27.0%) — 工程健壮性问题
        ├─ 超时/限流:           8
        ├─ 格式解析失败:         6
        └─ 并发/一致性问题:      6

  优化建议:
    data 占比最高(43.2%) → 建议加强数据源治理，增加输入 URL 有效性预检
    prompt 次之(29.7%)   → 建议增加策略配置校验，模型下线自动检测告警
    engineering(27.0%)   → 建议增加重试策略和 SharedArrayBuffer 兼容降级
```

**三孤岛统计规则**：
1. 汇总所有 WF 输出的 `gapType` 字段值
2. 按 `data` / `prompt` / `engineering` 分组计数
3. 计算各类型占比，占比最高的鸿沟类型写入优化建议
4. 与历史数据对比趋势（如有）：如果某类鸿沟占比连续上升，标记为"需重点关注"

### 与 Pipeline 其他 Stage 的协作

- **Stage 0-1** 提供 DataGap 列表和造数结果，本技能在 BLOCKED_DATA 中引用造数 skill 的调用参数和失败响应
- **Stage 2** 提供七步诊断结果，本技能在 BLOCKED_DEP/BLOCKED_LOGIC 中引用诊断结论
- **Stage 4** 消费本技能归因报告中的失败条目，对可自愈的 BLOCKED_DATA/BLOCKED_DEP 执行七步诊断→修复→重触发验证
- **本技能（Stage 3）** 将以上信息整合为最终归因报告
