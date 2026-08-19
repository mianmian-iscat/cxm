---
name: f88-mainimg-material
description: F88 主图素材域问题排查路由器（与种草素材域 f88-seeding-material 同级并列）。输入商品ID(item_id)、批次号(BT_xxxx)、节点类型、错误现象、买手平台数据流或商详拼接问题，路由到知识库对应业务模块的 .md 文档进行排查。触发词：主图素材、素材排查、商品排查、排查素材、item排查、BT_排查、批次排查、生图失败、审核卡住、产出异常、素材缺失、去选图异常、模板匹配失败、视频生成失败、买手平台、种子图、数据源没进来、推回买手、素材没回流、展示不对、link 20188、主图素材供给、商详拼接、商详长图、长图生成失败、尺码图、面料图、品牌故事、itemDetailReady、星链、node_id=9、白名单、款提交失败、图片转存失败、图片下载失败、403、详情图403、平台商品ID、供给品ID、ID映射、商品详情图。
version: 2.3.0
---

# F88主图素材（排查路由层）

> 本 skill 是**排查路由器**：定位问题属于哪个业务模块，然后读取知识库对应 .md 文档执行排查。
> 详细知识（PRD 定义/字段表/失败链路/案例/SQL）全部在知识库 .md 文档中，按业务模块组织。

## 知识库路径

```
/Users/caoxuemei/quderwork/f88素材生产/素材排查知识库/
├── 00-总览与通用/
│   ├── 链路流转总览.md        ← 全域链路地图/主图/商详/种草流转
│   ├── 排查决策树.md          ← 现象→根因决策树（D-01~D-09）
│   ├── 全链路排查方法论.md    ← 路径A/B/C/D（商品→批次→节点→输出物）
│   ├── SQL模板.md             ← T1-T17 查询模板
│   ├── 环境与工具.md          ← 数据库/表索引/MCP/已知陷阱15条
│   └── 来源文档索引.md        ← PRD/技术文档/群聊来源链接
├── 01-主图素材供给/
│   ├── 买手平台数据流.md      ← 上游/中游/下游三点验证 + 72h状态机
│   └── 排查案例.md            ← E1-E10 实战案例
└── 02-商详拼接/
    ├── PRD内容详情.md         ← 三接口/点位映射/素材规格/长图组成
    ├── 失败链路.md            ← 架构 + F0-F4 全失败点 + 取证方法论
    └── 验证流程.md            ← detailSlices 四步验证
```

## 排查入口路由

| 用户输入 | 读取文档 |
|----------|----------|
| item_id / BT_xxxx / 节点名 / 通用现象 | `00-总览与通用/全链路排查方法论.md` + `排查决策树.md` |
| 买手平台数据没进来 / 推回展示不对 / 种子图 / 回流 | `01-主图素材供给/买手平台数据流.md` |
| 款提交失败 / 图片转存403 / 详情图下载失败 | `排查决策树.md` D-08「款提交失败/图片转存403」分支 |
| 需要主图域完整表清单/字段说明/SQL模板/负责人 | `quderwork/f88素材生产/主图素材数据链路速查表.md` | 独立速查表，含 16 张表 + 72h 状态机 + MetaQ + 商详拼接 |
| 需要全域表总览/跨域关联 | `quderwork/f88素材生产/F88全链路表速查手册.md` | 总览文档，全域链路地图 + 文档索引 |
| 商详长图失败 / 拼接失败 / 尺码/面料/品牌故事 / itemDetailReady | `02-商详拼接/失败链路.md` + `验证流程.md` |
| 需要查 SQL | `00-总览与通用/SQL模板.md` |
| 环境/表结构/陷阱 | `00-总览与通用/环境与工具.md` |

## 前置步骤：平台商品ID → 供给品ID 映射（必做）

> **关键陷阱**：用户提供的"平台商品ID"是 `shop_tao_item_id`，但 F88 生产记录（`g_afd_material_prod_record`）中 `item_id` 存的是**供给品ID**（`supply_tao_item_id`）。两者不同，直接查会查不到数据。

**当用户提供平台商品ID时，第一步必须先查 ID 映射：**

```sql
-- scenario 库（dbId=975919）
SELECT shop_tao_item_id, supply_tao_item_id, supply_shop_user_id
FROM fs_shop_item_supply_relation
WHERE shop_tao_item_id = '{平台商品ID}' AND is_deleted = 0
LIMIT 1;
```

拿到 `supply_tao_item_id` 后，再用它查 `g_afd_material_prod_record`（stylespot 库 dbId=5335708）。

> 详见 `quderwork/f88素材生产/主图素材数据链路速查表.md` §2.6。

## 核心约束（每次排查必须遵守）

```
【强制】涉及数据库连接（dbId/实例）、ScheduleX、Switch、HSF、平台入口等操作时，必须先读取 quderwork/f88素材生产/常用地址手册.md 获取地址，禁止自行推理或搜索。地址全部写死在手册中，不靠推理。
数据库：stylespot 生产库（dbId=5335708）— 连接详情见 F88测试知识库/references/shared/db-connections.md
env 过滤：所有查询必须带 env='staging'
workflow_record_log：必须带 id > 4000000 否则超时
查批次用 batch_id 字段，NOT relation_id
status 失败值是 'FAIL'，不是 'FAILED'
【强制】平台商品ID ≠ 供给品ID，先查 fs_shop_item_supply_relation 映射再查 F88 表
```

## 排查流程

1. **ID 映射**（如用户提供平台商品ID）：查 `fs_shop_item_supply_relation` 获取供给品ID
2. 识别用户输入属于哪个路由（见上表）
3. 读取对应知识库 .md 文档
4. 按文档中的步骤执行 SQL 查询 / 验证 / 判读
5. 输出排查结论（格式见 `00-总览与通用/环境与工具.md` §7）

## 关联 Skill 路由

| 场景 | 路由到 |
|------|--------|
| 实时查批次进度/重试节点 | `strategy-platform` |
| 深度 SQL 归因（11 个工作流） | `f88-failure-analysis` |
| 生产事故应急（TPP回调/审核回调链） | `stylespot-prod-troubleshoot` |
| 审核节点替换验证 | `f88-approve-verify-sql` |
| 链路配置正确性检查 | `f88-link-config-check` |
| 自动化巡检(9维度) | `f88-pipeline-monitor` |
| 失败数据聚类分析 | `f88-clustering-service` |
| 视频输出物 ffprobe 校验 | `f88-ffmpeg` |
| 审核测试数据构造 | `审核数据构造` |
| 种草素材链路排查 | `f88-seeding-material` |
