---
name: f88-seeding-material
description: F88 种草素材域问题排查技能。覆盖种草图文/视频素材从选品调度（P1/P2/P3 定时器）、素材生产链路、图文上传节点（image_text_upload）到纵横平台发布与回流落库的全链路。与 f88-mainimg-material（主图素材域）同级并列。触发词：种草排查、种草素材排查、图文上传失败、种草没发布、contentId 为空、image_text_upload、LESS_PHOTO_MIN、PIC_RADIO_NOT_VALID、素材数量已达上限、产业带种草、种草优先级、种草 PENDING。
version: 2.3.0
---

# F88 种草素材问题排查

> **定位**：种草素材域专属排查技能，轻量方法论 + 知识库索引。详细领域知识按模块组织在知识库 `.md` 中。
> **域边界**：种草素材与主图素材是同级的两个独立域。本技能覆盖种草图文/视频的全链路；去选图缺图、主图类型（1:1/3:4/SKC/商详图）问题属于**主图素材域**（`f88-mainimg-material`），不在本技能范围内。

## 触发条件

用户消息含以下任一关键词时激活：种草排查 / 种草素材 / 图文上传 / image_text_upload / contentId 为空 / LESS_PHOTO_MIN / 产业带种草 / 种草优先级 / 种草 PENDING / 纵横发布 / 回流表。

## 域判别（群→归属）

问题来自钉钉群时，先判断是否属于本域——群里有**澜蓝** → 种草素材群 → 本技能范围；群里有**宗育** → 主图素材群 → 不在本域，建议用 `f88-mainimg-material`；**用户指定归属优先于成员判别**。已核实群清单见 [references/groups.md](references/groups.md)。

## 现象→知识索引

| 现象 | 知识库文件 | 补充 |
|------|-----------|------|
| 图文上传节点 FAIL / 报错 | → [03-种草素材/排查案例.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/排查案例.md) §错误信息速查 | 同时查 [references/error-codes.md](references/error-codes.md) |
| 节点 SUCCESS 但下游看不到 | → [03-种草素材/排查案例.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/排查案例.md) §已知陷阱 T2（output_json 为空） | 查回流表 status + ext_info |
| 商品没进种草生产 / 没任务 | → [03-种草素材/种草图文数据流.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/种草图文数据流.md) §2.1 调度规则 + §2.2 疲劳度 | 按 R3 逐层排除；完整表清单/SQL 见 [种草图文数据链路速查表.md](file:///Users/caoxuemei/quderwork/f88素材生产/种草图文数据链路速查表.md) |
| 种草视频上传问题 | → [03-种草素材/排查案例.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/排查案例.md) §代码入口速查 | 视频产物校验用 `f88-ffmpeg` |
| 需要表结构/枚举/SQL | → [03-种草素材/种草图文数据流.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/种草图文数据流.md) §5 速查表 + [references/sql-queries.md](references/sql-queries.md) | 种草域完整表清单/字段/SQL 见 [种草图文数据链路速查表.md](file:///Users/caoxuemei/quderwork/f88素材生产/种草图文数据链路速查表.md) |
| 需要了解全链路/上下游数据流 | → [03-种草素材/种草图文数据流.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/种草图文数据流.md) | 含 Mermaid 流程图 + SQL 判读；全域表总览见 [F88全链路表速查手册.md](file:///Users/caoxuemei/quderwork/f88素材生产/F88全链路表速查手册.md) |
| 需要查 PRD 产品定义（优先级/构图标/发布规格/效率看板/问题标记） | → [03-种草素材/PRD内容详情.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/PRD内容详情.md) | 9 章节：全链路概览/优先级/构图标/模版匹配/LLM生文/发布规格/问题标记/任务类型/效率看板 |
| 产业带种草专属细节（数据源/模版召回/爆款取数/定时器差异） | → [03-种草素材/产业带链路.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/03-种草素材/产业带链路.md) | link 20250/20259；含爆款取数 SQL 结构 + 交付表字段 |
| 需要种草域完整表清单/字段说明/SQL模板/负责人 | → [种草图文数据链路速查表.md](file:///Users/caoxuemei/quderwork/f88素材生产/种草图文数据链路速查表.md) | 独立速查表，含 13 张表 + P1/P2/P3 定时器 + 代码入口 + 已知陷阱 |
| 需要全域表总览/跨域关联 | → [F88全链路表速查手册.md](file:///Users/caoxuemei/quderwork/f88素材生产/F88全链路表速查手册.md) | 总览文档，全域链路地图 + 文档索引 |
| 需要查 PRD / 产品方案原文 | → 见下方「PRD 文档索引」 | 钉钉文档，需登录 |

## PRD 文档索引

> 完整索引见 [来源文档索引.md](file:///Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/00-总览与通用/来源文档索引.md)，以下列出种草素材域核心 PRD。

| 文档 | 链接 | 覆盖内容 |
|------|------|----------|
| F88 种草素材全链路产品需求 | [钉钉文档](https://alidocs.dingtalk.com/i/nodes/a9E05BDRVQRkezKGCy2K4BbeJ63zgkYA) | 全链路总需求（选品→生产→上传→发布） |
| F88 种草素材生产优先级调整 | [钉钉文档](https://alidocs.dingtalk.com/i/nodes/7NkDwLng8Za7QYkeHNBxZ3rNJKMEvZBY) | P1/P2/P3 优先级规则、定时器、疲劳度 |
| 产业带种草产品需求 | [钉钉文档](https://alidocs.dingtalk.com/i/nodes/MNDoBb60VLYDGNPytBmXge05JlemrZQ3) | 产业带 TOP5% 链路（link 20250）、图文上传节点 |
| 产业带素材产品方案 | [钉钉文档](https://alidocs.dingtalk.com/i/nodes/14lgGw3P8vxjwogPCppLQkg1V5daZ90D) | 产业带整体方案 |
| 产业带爆款取数口径 | [钉钉文档](https://alidocs.dingtalk.com/i/nodes/93NwLYZXWyxXroNzCZON0a2g8kyEqBQm) | TOP5% 爆品筛选规则与 SQL |

**Aone 需求 ID**：84575256（商家图文上传）/ 83324341（种草视频上传）/ 84332107 / 84528309 / 84053976

## 通用排查障方法

### 信息收集清单

1. 排查入口标识：batch_id（BT_xxxx）/ item_id / contentId / sellerId / userId
2. 问题现象描述
3. 时间范围 + 环境（预发 / 生产）
4. 来源群（如有）

### 六表查询顺序

`workflow_record_log`（节点执行）→ `g_afd_recommend_material_pool_record`（回流）→ `g_workflow_batch`（批次）→ `g_afd_material_prod_record`（商品→批次）→ `ai_process_record`（serverless 生产）→ ODPS 离线表

### SQL 铁律

- **【强制】** 涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 `quderwork/f88素材生产/常用地址手册.md` 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
- stylespot 库 DMS database_id=5335708
- 所有查询带 `env='staging'`，生产只读
- workflow_record_log 必须带 `id > 4000000` 或 batch_id 窄窗口（2026-08 max_id≈933 万，裸查超时）
- dms-alibaba CLI 受 DMS API 200 行限制，聚合查询不受限
- ODPS 分页必须 `ROW_NUMBER() OVER(ORDER BY col)`；collect 上限 10,000 行

### R3 调度层逐层排除（顺序重要）

1. 女装过滤：一级类目≠16 → 跳过不落 PENDING（预期）
2. 入池条件：F0 层级？is_online？爆款潜爆标记？产业带 TOP5%？风险单剔除？
3. 坑位已满：素材数≥6 不进 P2
4. 疲劳度：全局口径，任意链路生产过即跳过
5. 定时器：P3 周末/节假日不跑属预期
6. 队列容量：2000 上限 + 每小时补 (2000-n)/6

### 结论分类

- **数据问题**（入参/图片尺寸/坑位满）→ 非缺陷
- **配置问题**（链路 stage 缺失/策略枚举错）→ 改配置
- **真实 Bug** → 重新造数复验后才可确认，走 AOne（项目 2120437）

## 同级协作技能

- **主图素材域**（同级兄弟）`f88-mainimg-material` — 去选图/SKC/商详图/主图类型问题
- 深度 SQL 归因 `f88-failure-analysis`
- 链路配置检查 `f88-link-config-check`
- 视频校验 `f88-ffmpeg`
- 生产应急 `stylespot-prod-troubleshoot`
