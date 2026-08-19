# F88 / i-FASHION + 原创保护 双域回归用例集统一索引

> 本索引用于集中管理两个 QA 域的回归用例，统一用例元数据、att-tf cases.json 字段映射、执行口径与统计口径，确保用例可追溯、可统计、可复用。
>
> 配套文档：
> - [双域统一知识索引](file:///Users/caoxuemei/.qoderwork/workspace/msylhfhn4qp8csq8/f88_yc_knowledge_index.md)
> - [双域 Skill 体系与测试架构](file:///Users/caoxuemei/.qoderwork/workspace/msylhfhn4qp8csq8/f88_yc_skill_architecture.md)

---

## 一、用例元数据标准

### 1.1 字段定义与 cases.json 映射

| 字段 | 说明 | cases.json 字段 | 必填 | 取值规范 |
|------|------|-----------------|------|----------|
| caseId | 全局唯一用例编号 | `caseTitle` 前缀或 `groupPath` 推导 | 是 | `{域}-{模块}-{序号}`，如 F88-IMG-001、YC-SETTLE-012 |
| title | 用例标题 | `caseTitle` | 是 | 动宾结构，避免高层描述 |
| domain | 业务域 | 从 `groupPath` 第一级提取 | 是 | `F88` / `i-FASHION` / `YC` / `通用` |
| module | 功能模块 | `groupPath` 第二级 | 是 | 见下文模块清单 |
| priority | 优先级 | `priority` | 是 | `P0` / `P1` / `P2` |
| caseType | 用例类型 | 从 `groupPath` 或标题推断 | 是 | `UI` / `API` / `DB` / `混合` |
| dataTag | 数据依赖标签 | `description` 或自定义 tag | 否 | 见 1.2 数据标签 |
| sourceReq | 来源需求/PRD | `description` 中标注 | 是 | aoneId 或 PRD 章节 |
| status | 执行状态 | `status` | 是 | `1=通过` / `2=失败` / `3=跳过` |
| errorMessage | 失败信息 | `errorMessage` | 否 | 失败时必填 |
| execLog | 执行日志/截图 | `execLog` | 否 | 截图用相对路径 `screenshots/{caseId}-{desc}.png` |
| runId | 执行批次 | cases.json 外层字段或文件名 | 否 | att-tf 会话 ID |

### 1.2 数据标签（dataTag）

| 标签 | 含义 | 触发 Skill |
|------|------|-----------|
| `BT_BATCH` | 需要构造 F88 BT_ 批次 | `f88-strategy-test-run` |
| `REVIEW_TASK` | 需要 F88 审核任务 | `审核数据构造` |
| `TEMPLATE_PKG` | 需要 F88 模板包 | `f88-template-package-create` |
| `YC_APPLY` | 需要原创保护申请单 | `yc-data-factory` / `原创保护执行助手` |
| `YC_QUICK` | 需要快审数据 | `yc-quick-audit-data-create` |
| `YC_PRE` | 需要初审 PRE 数据 | `yc-quick-audit-data-create` |
| `YC_TAG` | 需要千牛标 TTYCBH | `原创保护千牛标打标` |
| `MANUAL_DATA` | 需人工准备数据 | 标记 SKIP 时说明 |

### 1.3 groupPath 规范

`groupPath` 统一为四级结构：

```
{域}/{模块}/{子模块}/{执行类型}
```

示例：
- `F88/主图素材/模板匹配/API`
- `F88/主图素材/审核节点/UI`
- `YC/结算退款/退款路径/DB`
- `YC/入驻申请/千牛标/混合`

---

## 二、F88 / i-FASHION 回归用例集

### 2.1 模块清单

| 模块代码 | 模块名称 | 说明 | 主要造数方式 |
|----------|----------|------|--------------|
| IMG | 主图素材 | 模板匹配、生图、审核、替换 | `f88-strategy-test-run` |
| SEED | 种草素材 | 图文上传、纵横发布、回流 | `f88-strategy-test-run` |
| VID | 视频生产 | gen_video、视频审核、格式校验 | `f88-ffmpeg.standalone-20260630` |
| TMPL | 模板包 | 模板包创建、租户绑定 | `f88-template-package-create` |
| APPROVE | 审核节点 | BATCH/STREAM、replaceImage、任务层级 | `f88-strategy-test-run` |
| LINK | 链路配置 | 阶段编排、参数流转、模型可用性 | 配置平台 + DB 验证 |
| BATCH | 批次运维 | 失败重试、节点进度、LLM 资源 | `strategy-platform` |
| MONITOR | 监控巡检 | 链路健康、告警规则 | `f88-pipeline-monitor` |

### 2.2 用例索引模板

| caseId | title | module | priority | caseType | dataTag | sourceReq |
|--------|-------|--------|----------|----------|---------|-----------|
| F88-IMG-001 | 主图模板匹配成功后生成正确尺寸素材 | IMG | P0 | API | BT_BATCH | PRD-XXX §3.2 |
| F88-IMG-002 | 替换后 BATCH 模式下游节点拿到新 URL | IMG | P0 | DB | BT_BATCH | PRD-XXX §4.1 |
| F88-SEED-001 | 种草图文上传成功后 contentId 非空 | SEED | P0 | UI | BT_BATCH | PRD-XXX §5.1 |
| F88-VID-001 | gen_video 输出物分辨率符合策略配置 | VID | P1 | API | BT_BATCH | PRD-XXX §6.3 |
| F88-APPROVE-001 | approve 节点三级审核任务全部完成 | APPROVE | P0 | DB | REVIEW_TASK | PRD-XXX §7.2 |
| F88-LINK-001 | 新链路阶段编排与系分一致 | LINK | P1 | 混合 | - | PRD-XXX §8.1 |
| F88-BATCH-001 | 失败批次重试后阶段正常流转 | BATCH | P1 | API | BT_BATCH | PRD-XXX §9.4 |

---

## 三、原创保护回归用例集

### 3.1 模块清单

| 模块代码 | 模块名称 | 说明 | 主要造数方式 |
|----------|----------|------|--------------|
| ENTER | 商家入驻 | 千牛标、准入拦截、服务标签 | `原创保护千牛标打标` |
| APPLY | 申请单 | 申请创建、资料提交、状态机 | `yc-data-factory` / `原创保护执行助手` |
| QUICK | 快审 | 快审申请、扣减、结果回调 | `yc-quick-audit-data-create` |
| PRE | 初审 | 初审申请、充值、审核结果 | `yc-quick-audit-data-create` |
| GOODS | 商品绑定 | 绑定/解绑、首发标、保护期 | `yc-data-factory` / `原创保护执行助手` |
| SETTLE | 结算退款 | settle_order、资金流向、退款路径 | `yc-data-factory` |
| RULE | 规则校验 | 9 类白名单、补贴、首发编辑权限 | `原创保护规则校验` |
| RIGHT | 权益保护 | 保护期、维权、下架率分流 | `yc-data-factory` |

### 3.2 用例索引模板

| caseId | title | module | priority | caseType | dataTag | sourceReq |
|--------|-------|--------|----------|----------|---------|-----------|
| YC-ENTER-001 | 打 TTYCBH 后商家可正常入驻 | ENTER | P0 | 混合 | YC_TAG | PRD-YYY §2.1 |
| YC-APPLY-001 | 免费申请成功后 yc_right_apply.free=1 | APPLY | P0 | DB | YC_APPLY | PRD-YYY §3.1 |
| YC-QUICK-001 | 快审通过后服务次数正确扣减 | QUICK | P0 | DB | YC_QUICK | PRD-YYY §4.2 |
| YC-PRE-001 | PRE 初审充值后可用次数增加 | PRE | P1 | API | YC_PRE | PRD-YYY §4.3 |
| YC-GOODS-001 | 商品绑定成功后状态为 PROTECTING | GOODS | P0 | DB | YC_APPLY | PRD-YYY §5.1 |
| YC-SETTLE-001 | 服务完结后生成正确 settle_order | SETTLE | P0 | DB | YC_APPLY | PRD-YYY §6.1 |
| YC-RULE-001 | 首发编辑权限窗口期内可编辑 | RULE | P1 | API | YC_APPLY | PRD-YYY §7.2 |
| YC-RIGHT-001 | 保护期内下架率分流正确 | RIGHT | P1 | DB | YC_APPLY | PRD-YYY §8.3 |

---

## 四、att-tf 上报约定

### 4.1 cases.json 单条结构

```json
{
  "caseTitle": "F88-IMG-001 主图模板匹配成功后生成正确尺寸素材",
  "description": "来源：PRD-XXX §3.2；操作：策略试运行构造BT_批次→等待生图完成→查询g_afd_material；期望：URL非空且尺寸符合模板配置。",
  "status": 1,
  "priority": "P0",
  "groupPath": "F88/主图素材/模板匹配/API",
  "errorMessage": "",
  "execLog": "screenshots/F88-IMG-001-material-url.png"
}
```

### 4.2 状态语义

| status | 含义 | 使用条件 |
|--------|------|----------|
| 1 | 通过 | 证据完整且验证成功 |
| 2 | 失败 | 验证不通过，已排除自愈可能 |
| 3 | 跳过 | 数据/环境/账号不可用，已确认无替代路径 |

### 4.3 必填自检

上报前检查：
1. `caseTitle` 包含 `caseId`，便于索引反查。
2. `description` 包含来源需求章节和数据构造方式。
3. `groupPath` 符合四级规范。
4. 失败用例 `errorMessage` 不为空，且不含截图路径等无关信息。
5. UI 用例 `execLog` 包含截图相对路径，且文件已落盘确认。

---

## 五、统计口径

### 5.1 基础指标

| 指标 | 计算公式 | 说明 |
|------|----------|------|
| 用例总数 | `count(caseId)` | 按 domain/module/priority 分组 |
| 通过率 | `sum(status=1) / 总数` | 不含 SKIP |
| 失败率 | `sum(status=2) / 总数` | 不含 SKIP |
| 跳过率 | `sum(status=3) / 总数` | 单独统计 |
| P0 覆盖率 | `P0 已执行数 / P0 总数` | 回归必须 = 100% |
| 数据就绪率 | `无需 MANUAL_DATA 用例数 / 总数` | 衡量自动化造数覆盖 |

### 5.2 报表模板

```markdown
## 回归执行摘要（{日期} / {runId}）

- 用例总数：{N}
- 通过：{P} / 失败：{F} / 跳过：{S}
- 通过率：{P%} / 失败率：{F%} / 跳过率：{S%}
- P0 未覆盖：{list}
- 失败聚焦模块：{top3 modules}
```

---

## 六、维护约定

1. **新增用例**：必须补充到本索引对应模块表格，并分配全局唯一 `caseId`。
2. **用例废弃**：保留条目，状态列标注 `DEPRECATED`，说明替代 caseId。
3. **需求变更**：`sourceReq` 变更时同步更新 `description` 和用例标题。
4. **模块拆分**：新增模块需同步更新模块清单、groupPath 规范和本索引表格。
5. **cases.json 导出**：执行完成后由 `att-report` 统一上报，禁止手动修改 status。
6. **双域一致性**：跨域依赖用例（如 F88 素材用于原创保护商品绑定）在两侧索引中各保留一行，并通过 `sourceReq` 关联。

---

## 七、相关 Skill 与入口

| 用途 | Skill |
|------|-------|
| F88 全流程回归 | `hfz-test-workflow` |
| 原创保护全流程回归 | `原创保护测试编排` |
| 用例完整性评估 | `test-case-completeness-assessment` |
| 数据就绪预检 | `qa-data-preflight` |
| 对抗验证接入 | `qa-adversarial-agent` |
| 失败分析与 Bug 草稿 | `aone-bug-submit` / `pytest-to-bug-draft-pipeline` |
| 测试报告生成 | `qa-test-report` |
