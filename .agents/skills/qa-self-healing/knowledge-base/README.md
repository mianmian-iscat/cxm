# 知识三层分类统一索引

> 按课程《阿里妈妈 Agentic AI 基建与实战》的业务/系统/职责三层模型重组知识。
> 各 skill 的 references/ 中的知识文件逐步迁移到本目录，原位置保留软链接或路由指引。

## business/ — 业务规则知识

| 文件 | 用途 | 来源 skill |
|------|------|-----------|
| f88-workflow-rules.md | F88 工作流规则（阶段流转/审核逻辑/状态机） | f88-failure-analysis, F88测试知识库 |
| yc-protection-rules.md | 原创保护规则（状态机/结算逻辑/首发标窗口） | 原创保护规则校验, 原创保护知识库 |
| business-glossary.md | 业务术语表（跨域统一用语） | 新建 |

## system/ — 系统架构知识

| 文件 | 用途 | 来源 skill |
|------|------|-----------|
| db-schema-index.md | 统一表结构索引（跨 skill 的 DB 表速查） | f88-data-query, f88-failure-analysis, yc-db-verification |
| api-catalog.md | API 目录（MCP/DMS/HSF 接口汇总） | f88-failure-analysis, 原创保护执行助手 |
| infra-topology.md | 基础设施拓扑（预发/线上/DB 实例/CDN） | F88测试知识库 |

## responsibility/ — 职责/流程知识

| 文件 | 用途 | 来源 skill |
|------|------|-----------|
| skill-routing-map.md | Skill 路由决策树（遇到什么场景调哪个 skill） | hfz-test-workflow, 原创保护测试编排 |
| escalation-matrix.md | 问题升级矩阵（什么问题找谁/什么路径） | qa-self-healing |
| decision-playbook.md | 常见决策手册（造数路径选择/降级策略/红线判断） | qa-self-healing |

## 迁移计划

1. 先建索引文件（本文件），明确每个知识文件的归属层
2. 各 skill 的 references/ 中已有文件暂不移动，在索引中标注"来源 skill"
3. 新建的跨域知识文件直接放在本目录对应层
4. 逐步将各 skill 的通用知识抽取到本目录，原位置改为路由指引

## 使用方式

遇到未知问题需要查知识时，按以下顺序检索：
1. 先查本索引，确定问题属于哪一层
2. 到对应层查找具体知识文件
3. 未命中 → 查对应 skill 的 references/
4. 仍未命中 → 自行推理分析（记录到 learned-solutions.jsonl）
