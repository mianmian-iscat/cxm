# 报告输出模板

检查完成后按此模板生成 Markdown 报告。

---

## 模板开始

# F88 链路配置检查报告

> 链路: {LINK_ID} {LINK_NAME} | 环境: {ENV} | 状态: {LIFE_CYCLE} | 检查时间: {CHECK_TIME}

---

### 基本信息

| 字段 | 值 |
|------|-----|
| 链路 ID | {LINK_ID} |
| 名称 | {LINK_NAME} |
| 环境 | {ENV} |
| 生命周期 | {LIFE_CYCLE} |
| 阶段数 | {STAGE_COUNT} |
| 策略数 | {STRATEGY_COUNT} |
| 提交人 | {SUBMITTER} |
| 最后修改 | {GMT_MODIFIED} |

### 阶段编排

{STAGE_SEQUENCE}
（示例：刷标签 → 首图生图 → 首图审核 → 套图生图 → 套图审核 → 上传）

---

### 检查结果汇总

| 类别 | 检查项数 | 通过 | 告警 | 严重 |
|------|---------|------|------|------|
| A. 阶段编排 | 6 | {A_OK} | {A_WARN} | {A_ERR} |
| B. 模板匹配 | 5 | {B_OK} | {B_WARN} | {B_ERR} |
| C. 生图节点 | 4 | {C_OK} | {C_WARN} | {C_ERR} |
| D. 审核节点 | 8 | {D_OK} | {D_WARN} | {D_ERR} |
| E. 参数流转 | 5 | {E_OK} | {E_WARN} | {E_ERR} |
| F. 环境运维 | 5 | {F_OK} | {F_WARN} | {F_ERR} |
| G. 多套上传 | 4 | {G_OK} | {G_WARN} | {G_ERR} |
| H. LLM文本节点 | 5 | {H_OK} | {H_WARN} | {H_ERR} |
| I. 模型可用性 | 4 | {I_OK} | {I_WARN} | {I_ERR} |
| J. 容量与限流 | 4 | {J_OK} | {J_WARN} | {J_ERR} |
| K. 阶段流转与容错 | 3 | {K_OK} | {K_WARN} | {K_ERR} |
| L. 逆向操作与生命周期 | 5 | {L_OK} | {L_WARN} | {L_ERR} |
| M. 执行模式 | 3 | {M_OK} | {M_WARN} | {M_ERR} |
| **合计** | **61** | **{TOTAL_OK}** | **{TOTAL_WARN}** | **{TOTAL_ERR}** |

---

### A. 阶段编排检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| A1. 阶段数量 | {STATUS} | {FINDING} |
| A2. UID 唯一性 | {STATUS} | {FINDING} |
| A3. 阶段顺序 | {STATUS} | {FINDING} |
| A4. 阶段类型覆盖 | {STATUS} | {FINDING} |
| A5. 单阶段审查 | {STATUS} | {FINDING} |
| A6. 生命周期状态 | {STATUS} | {FINDING} |

### B. 模板匹配检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| B1. matchScene | {STATUS} | {FINDING} |
| B2. targetMatchCount | {STATUS} | {FINDING} |
| B3. mustMatchFields | {STATUS} | {FINDING} |
| B4. templateMaxUseCount | {STATUS} | {FINDING} |
| B5. templatePkgCondition | {STATUS} | {FINDING} |

### C. 生图节点检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| C1. modelType | {STATUS} | {FINDING} |
| C2. imageSize/outputRatio | {STATUS} | {FINDING} |
| C3. outputModel | {STATUS} | {FINDING} |
| C4. 输入字段命名 | {STATUS} | {FINDING} |

### D. 审核节点检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| D1. approveType | {STATUS} | {FINDING} |
| D2. passedImg 输出 | {STATUS} | {FINDING} |
| D3. imgUrlReviewList | {STATUS} | {FINDING} |
| D4. not_pass_reason 命名 | {STATUS} | {FINDING} |
| D5. imgUrlReview 字段存在性 | {STATUS} | {FINDING} |
| D6. 图片来源映射有效性 | {STATUS} | {FINDING} |
| D7. 首节点 approve 图片必填 | {STATUS} | {FINDING} |
| D8. approve 数据源与 execMode 一致性 | {STATUS} | {FINDING} |

### E. 参数流转检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| E1. 跨阶段引用完整性 | {STATUS} | {FINDING} |
| E2. 输出编号风格 | {STATUS} | {FINDING} |
| E3. 命名变体 | {STATUS} | {FINDING} |
| E4. 通用参数覆盖率 | {STATUS} | {FINDING} |
| E5. 种子图字段命名 | {STATUS} | {FINDING} |

### F. 环境运维检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| F1. test 链路清理 | {STATUS} | {FINDING} |
| F2. mass_prod 活跃度 | {STATUS} | {FINDING} |
| F3. 策略一致性 | {STATUS} | {FINDING} |
| F4. 修改人追溯 | {STATUS} | {FINDING} |
| F5. COOP/COEP 响应头检查 | {STATUS} | {FINDING} |

### G. 多套上传出参拆分检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| G1. 审核出参拆分 | {STATUS} | {FINDING} |
| G2. 上传策略映射 | {STATUS} | {FINDING} |
| G3. inputParams 对齐 | {STATUS} | {FINDING} |
| G4. 其他上传链路排查 | {STATUS} | {FINDING} |

### H. LLM 文本节点检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| H1. outputText.type=JSON 时 outputFields 非空 | {STATUS} | {FINDING} |
| H2. JSON 输出时 prompt 含格式约束 | {STATUS} | {FINDING} |
| H3. prompt 禁止原始换行声明 | {STATUS} | {FINDING} |
| H4. modelType 有效性 | {STATUS} | {FINDING} |
| H5. userPrompt 变量引用有效性 | {STATUS} | {FINDING} |

### I. 模型可用性检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| I1. modelType 非已停用模型 | {STATUS} | {FINDING} |
| I2. 单模型依赖风险 | {STATUS} | {FINDING} |
| I3. 模型与任务类型匹配 | {STATUS} | {FINDING} |
| I4. 活跃策略模型白名单校验 | {STATUS} | {FINDING} |

### J. 容量与限流检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| J1. gen_video 并发配置 | {STATUS} | {FINDING} |
| J2. 模板包体积预估 | {STATUS} | {FINDING} |
| J3. 前置数据准备完整性 | {STATUS} | {FINDING} |
| J4. 批次优先级与模型队列负载匹配 | {STATUS} | {FINDING} |

### K. 阶段流转与容错检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| K1. 节点间流转依赖完整性 | {STATUS} | {FINDING} |
| K2. 单张失败容错配置 | {STATUS} | {FINDING} |
| K3. 重试后下游触发机制 | {STATUS} | {FINDING} |

### L. 逆向操作与生命周期联动检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| L1. 参数双向引用完整性 | {STATUS} | {FINDING} |
| L2. 批次撤回/取消联动配置 | {STATUS} | {FINDING} |
| L3. 审核驳回后重生路径完整性 | {STATUS} | {FINDING} |
| L4. 多阶段部分失败回滚策略 | {STATUS} | {FINDING} |
| L5. 跨策略参数流转一致性 | {STATUS} | {FINDING} |

### M. 执行模式检查

| 检查项 | 状态 | 发现 |
|--------|------|------|
| M1. execMode 字段存在性 | {STATUS} | {FINDING} |
| M2. BATCH 模式 SchedulerX 依赖告警 | {STATUS} | {FINDING} |
| M3. BATCH/STREAM 数据源一致性 | {STATUS} | {FINDING} |

---

### 问题明细

对于每项非"通过"的检查，列出具体发现和修复建议：

#### {CHECK_ID}. {CHECK_TITLE}

- **状态**: {STATUS_ICON} {STATUS_TEXT}
- **发现**: {DETAILED_FINDING}
- **修复建议**: {RECOMMENDATION}
- **关联策略**: {AFFECTED_STRATEGIES}

---

### 修复优先级建议

| 优先级 | 检查项 | 原因 |
|--------|--------|------|
| P0 立即修复 | {ITEM} | {REASON} |
| P1 尽快处理 | {ITEM} | {REASON} |
| P2 建议优化 | {ITEM} | {REASON} |

---

> 检查报告 · 只读分析（仅 SELECT 查询）· 数据来源：stylespot.g_link + g_strategy · 生成时间：{CHECK_TIME}

## 模板结束

---

## 状态标记规范

- ✅ 通过：配置正确，无需修改
- ⚠️ 告警：存在风险或不一致，建议优化
- ❌ 严重：配置缺陷可能导致功能异常，需立即修复
- ℹ️ 信息：参考信息，无需操作

## 使用指南

1. 复制模板，将 `{PLACEHOLDER}` 替换为实际检查数据
2. 非"通过"状态的检查项展开到"问题明细"
3. 所有严重和告警项汇总到"修复优先级建议"
4. 输出为 .md 文件，命名格式：`link-check-{LINK_ID}-{DATE}.md`
