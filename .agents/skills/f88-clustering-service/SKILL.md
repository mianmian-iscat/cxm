---
name: f88-clustering-service
description: F88 失败数据统一聚类分析路由器。基于 TF-IDF + KMeans 对多源失败记录（DMS 数据库、att-tf 用例执行、QA 自愈、UI 自动化、审计检查点）做自动聚类分析，生成 MD/JSON/HTML 报告并可选推送钉钉。当用户说"失败聚类""聚类分析""聚类报告""失败模式分析""clustering service""分析失败模式"时触发。
version: 2.0.2
---

# F88 失败聚类分析（路由层 v2）

> v2.0: 合并 analyze_failure_patterns.py + f88-clustering-service/app.py 为统一脚本。
> Flask/APScheduler 长驻服务已废弃，改为按需 CLI + QoderWork cron 调度。

## 统一脚本

```
~/.qoderwork/scripts/analyze_failure_patterns.py
```

### 数据源 (7)

| # | 数据源 | 路径/来源 | 说明 |
|---|--------|-----------|------|
| 1 | rejected-approaches | qa-self-healing/references/rejected-approaches.jsonl | QA 自愈被证伪方案 |
| 2 | fails-7d | workspace/f88-patrol/fails_7d.json | 预发 7 天生产失败 |
| 3 | error-pattern-map | web-automation/references/error-pattern-map.json | UI 自动化错误模式 |
| 4 | checkpoint-log | workspace/*/checkpoint_log.json | 对抗审计检查点 |
| 5 | session-strategies | workspace/*/session-strategies.jsonl | 跨 session 策略 |
| 6 | att-tf cases | ~/.att-tf/cases/*/cases.json | 测试用例执行失败 (status=2) |
| 7 | DMS (可选) | dms-alibaba CLI → workflow_record_log | 策略平台实时失败 |

### 用法

```bash
# 基础: 仅本地数据
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py

# + HTML 可视化报告
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py --html

# + DMS 实时数据
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py --dms --dms-hours 8

# + 钉钉推送 (需 DINGTALK_WEBHOOK 环境变量)
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py --html --dingtalk

# 全量模式
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py --dms --html --dingtalk

# 排除 att-tf 数据
python3 ~/.qoderwork/scripts/analyze_failure_patterns.py --no-att-tf
```

### 输出

| 文件 | 说明 |
|------|------|
| qa-analysis/failure_patterns_{timestamp}.md | Markdown 聚类报告 |
| qa-analysis/suggested_routing_rules.json | 路由规则建议 (可导入 qa-self-healing) |
| qa-analysis/f88-clustering-{timestamp}.html | HTML 可视化报告 (--html) |
| 钉钉群 | Markdown 摘要 (--dingtalk) |

### 依赖 (全部可选)

| 库 | 作用 | 缺失时降级 |
|----|------|-----------|
| jieba | 中文分词 | 手写 2-gram |
| sklearn | TF-IDF + KMeans + silhouette | 内置零依赖实现 |
| requests | 钉钉推送 | 跳过推送 |
| yaml | 配置文件 | 内置默认值 |

## 知识库路径

```
f88-clustering-service/references/
├── app.py              # [已废弃] 原 Flask 服务源码 (保留作历史参考)
├── config.yaml         # [已废弃] 原服务配置 (参数已迁入统一脚本)
├── requirements.txt    # [已废弃] 原服务依赖
├── deployment.md       # 部署运维手册 (历史参考)
└── algorithm.md        # 聚类算法 + 签名库文档 (仍有效)
```

## 需求路由

| 用户输入 | 动作 |
|----------|------|
| 跑一次聚类 / 失败聚类分析 | 执行 `analyze_failure_patterns.py --html` |
| 含 DMS 实时数据的聚类 | 执行 `analyze_failure_patterns.py --dms --html` |
| 部署/启动聚类服务 | 告知用户 v2 已改为 CLI + cron，无需长驻服务 |
| 聚类算法/签名库说明 | 读取 `algorithm.md` |
| 治理-N 打标/收敛分析 | 读取 `algorithm.md` → 治理签名打标 |
| execMode 交叉分析 | 读取 `algorithm.md` → execMode 交叉分析维度 |
| 修改聚类参数 | 编辑 `analyze_failure_patterns.py` 的 DEFAULT_* 常量或 CLI 参数 |
| 配置定时调度 | 使用 QoderWork cron 定时执行脚本 |

## 签名库

签名匹配逻辑已迁入统一脚本的 `SIGNATURES` 和 `REVIEW_SIGNATURES` 字典。
完整签名列表见 `algorithm.md`。

覆盖:
- 治理-1~5 (ideaLAB额度/模型不可用/资源限流/平台限流/URL失效)
- v1.1 (SharedArrayBuffer/subJobId/replaceImage跨表/BATCH-STREAM差异)
- v1.3 (审核分配校验/审核回调/LLM JSON解析)
- v1.4 (淘积木OSS转存403/商详图转存失败，同步 error-signatures.md 2026-08-12)
- 审核类关键词签名 (16 条)

## 核心约束

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
查询安全规则（env 过滤铁律/写操作红线/ScheduleX 只读）：见 F88测试知识库/references/shared/query-safety-rules.md
env 红线：DMS 只查 staging 数据
workflow_record_log：必须带 id > 4000000 否则超时（近期批次建议 id > 6400000 进一步缩小扫描范围，与 f88-failure-analysis / f88-approve-verify-sql 口径一致）
只读不写：只做 SELECT 查询
数据不入库：失败记录仅在内存中处理
```

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 实时巡检 + 告警 + 自愈 | `f88-pipeline-monitor` |
| 单次手动失败分析 | `f88-failure-analysis` |
| 实时查批次进度/重试节点 | `strategy-platform` |
| QA 自愈路由表更新 | `qa-self-healing` |
| att-tf 测试度量基线 | `att-tf-metrics-baseline` |
