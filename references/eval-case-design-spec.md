# Eval 用例设计规范

> 本规范来源于 qoderwork 用例设计体系，适配 web-automation 的 `eval/cases/` JSON 格式。
> 所有新增 eval 用例必须遵循本规范。

---

## 1. 用例 8 类分类

每个 eval 场景（如 f88、xiaoer）下的用例应覆盖以下 8 类：

| # | 类别 | 命名前缀 | 说明 |
|---|------|---------|------|
| 1 | 正常流程 | `normal_` | 核心 happy-path，端到端完整链路 |
| 2 | 异常流程 | `error_` | 错误/失败路径，验证错误处理 |
| 3 | 边界条件 | `boundary_` | 空数据/超时/分页极值/特殊字符 |
| 4 | 状态机覆盖 | `state_` | 状态枚举转换矩阵 |
| 5 | 接口契约验证 | `contract_` | API 响应字段结构断言 |
| 6 | 自愈验证 | `heal_` | 故意触发自愈引擎，验证修复闭环 |
| 7 | 风险点覆盖 | `risk_` | 来自代码分析/踩坑记录的高风险场景 |
| 8 | 冒烟回归 | `smoke_` | 页面可访问 + 基础交互验证 |

---

## 2. 用例 JSON 标准结构

每个 eval case JSON 必须包含以下字段：

```json
{
  "id": "category-scene-description",
  "name": "分类：场景描述",
  "description": "一句话说明验证目标",
  "businessType": "f88_material | product_management | ...",
  "scene": "f88-test | xiaoer | qianniu | ...",
  "priority": "P0 | P1 | P2",
  "category": "normal_flow | error_flow | boundary | state_machine | api_contract | self_healing_validation | risk_coverage | smoke",
  "context": { "urlPattern": "...", "url": "...", "waitAfterLoad": 3000 },
  "steps": [ ... ],
  "capture": { "enabled": true, "filter": "...", "captureBody": true },
  "screenshot": { "onError": true },
  "_expected": { "status": "pass | fail | error" },
  "_testDesign": {
    "preconditions": "前置条件描述",
    "riskPoints": ["风险点1", "风险点2"],
    "relatedDocs": ["references/xxx.md"],
    "boundaryType": "empty_data | timeout | pagination | ...",
    "expectedHealBehavior": "（自愈用例专用）预期自愈行为",
    "verifyFields": ["output.steps[N].healAttempt.action == 'knowledge_fix'"]
  }
}
```

### 2.1 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 全局唯一标识，格式 `{category}-{scene}-{slug}` |
| `name` | ✅ | 中文标题，格式 `分类：简短描述` |
| `description` | ✅ | 一句话说明验证目标 |
| `businessType` | ✅ | 业务类型（与 metrics 对齐） |
| `scene` | ✅ | 归属场景（与 thresholds.yaml 分组对齐） |
| `priority` | ✅ | P0=阻断/P1=重要/P2=辅助 |
| `category` | ✅ | 8 类分类之一 |
| `context` | ✅ | 执行环境配置 |
| `steps` | ✅ | 步骤数组 |
| `_expected` | ✅ | 预期最终状态 |
| `_testDesign` | ✅ | 用例设计元数据 |
| `capture` | 推荐 | 网络抓包配置 |
| `screenshot` | 推荐 | 截图策略 |

### 2.2 `_testDesign` 字段详解

| 子字段 | 说明 |
|--------|------|
| `preconditions` | 数据准备、环境要求、账号状态 |
| `riskPoints` | 该用例覆盖的风险点列表 |
| `relatedDocs` | 关联的参考文档路径 |
| `boundaryType` | 边界条件类型（仅 boundary 类用例） |
| `expectedHealBehavior` | 预期自愈行为描述（仅 heal_ 类用例） |
| `verifyFields` | 需要在 output 中校验的字段表达式 |
| `contractFields` | API 契约必须存在的字段（仅 contract_ 类用例） |

---

## 3. 测试方法论

### 3.1 等价类划分
- 有效等价类：合理输入，系统应正常处理
- 无效等价类：不合理输入，系统应给出错误提示
- 每个等价类至少选取一个代表值

### 3.2 边界值分析
- 数值型：最小值、最小值+1、最大值-1、最大值、超出范围值
- 字符串：空串、单字符、最大长度、超长、特殊字符
- 列表：空列表、单元素、满容量、超容量
- 时间：超时阈值-1ms、超时阈值、超时阈值+1ms

### 3.3 状态迁移测试
- 绘制状态迁移图
- 覆盖所有合法状态转换路径
- 验证非法状态转换被拒绝
- 关注并发状态冲突

### 3.4 错误猜测法
- 网络中断/超时/重复提交
- 并发操作同一资源
- 大数据量下的性能退化
- 权限越级访问
- DOM 结构变更导致选择器失效

### 3.5 自愈场景设计
- 故意使用过时/错误的 selector
- 模拟 DOM 结构与知识库不一致
- 验证 `healAttempt.retrySuccess` 字段
- 确认自愈不会无限循环

---

## 4. 优先级定义

| 优先级 | 定义 | 示例 |
|--------|------|------|
| P0 | 阻断性/核心链路，必须通过 | 完整审核流程、自愈闭环验证 |
| P1 | 重要功能，影响主要使用 | API 契约验证、边界条件 |
| P2 | 辅助功能，有替代方案 | UI 展示异常、非核心状态 |

---

## 5. F88 业务测试五阶段优先顺序

> 此顺序同时适用于 **用例设计** 和 **用例执行**，不可打乱。
> 完整定义见 `harness/regression_matrix.yaml` 的 `f88-material.phases`。

| 阶段 | 名称 | 业务模块 | 用例目录 | 通过率门槛 | 失败动作 |
|------|------|----------|----------|------------|----------|
| P1 | 节点先行 | 策略管理 + 链路管理 | `eval/cases/f88-test/策略管理/策略列表/**` + `策略详情/**` + `链路管理/链路列表/**` + `链路详情/**` | 100% | abort |
| P2 | 审核验证 | 审核管理 + 生产看板 | `eval/cases/f88-test/审核管理/审核标准管理/**` + `审核节点管理/**` + `任务大厅/**` + `个人任务中心/**` + `任务详情/**` + `审核操作/**` + `生产看板/**` | ≥95% | abort |
| P3 | 模板库 | 模版库 | `eval/cases/f88-test/模版库/模版包管理/**` + `淘内资源池/**` + `优质模板库/**` + `模版匹配/**` | ≥95% | abort |
| P4 | 商家管理 | 商家管理 | `eval/cases/f88-test/商家管理/商家信息配置/**` + `竞品关联/**` | ≥90% | warn |
| P5 | 链路串联 | 全链路E2E | `eval/cases/f88-test/全链路E2E/**` | ≥90% | abort |

**依赖关系**：
- P2、P3 依赖 P1（可并行）
- P4 依赖 P2
- P5 依赖 P1~P4 全部通过

**设计规则**：
- 写用例时先写单模块原子用例，最后写链路串联用例
- 用例的 `priority` 字段必须与所属阶段匹配
- 反模式：不直接写链路串联用例而跳过单模块用例

---

## 6. thresholds.yaml 注册规范

新增用例后必须注册到 `eval/thresholds.yaml` 的对应场景分组：

```yaml
smoke_cases:
  {scene}:
    - cases/{filename}.json   # 简短注释说明
```

注册规则：
- `smoke_` 前缀用例：注册到对应 scene 分组
- `normal_` / `contract_` / `boundary_` 用例：注册到对应 scene 分组
- `heal_` / `error_` 用例：注册到 `self-healing` 分组
- 更新 `core/` 或 `impl.py` 后：必须跑 `base` + `self-healing` 分组

---

## 7. 用例覆盖完整性检查清单

新增场景时，按以下清单逐项检查：

- [ ] 主流程（Happy Path）完整覆盖
- [ ] 所有关键分支有对应异常用例
- [ ] 接口必要字段有契约断言
- [ ] 空数据/超时边界已覆盖
- [ ] 自愈路径（error-pattern-map 中涉及的模式）已验证
- [ ] **F88 场景：用例按五阶段顺序设计（P1节点→P2审核→P3模板库→P4商家→P5链路）**
- [ ] **F88 场景：链路串联用例必须在单模块用例之后编写**
- [ ] 用例已注册到 thresholds.yaml
- [ ] `_testDesign` 元数据完整

---

## 8. 与 examples/ 的关系

| 目录 | 定位 | 运行方式 |
|------|------|---------|
| `eval/cases/` | 上线门槛 + 回归验证 | `score_eval.py` 自动评分 |
| `examples/f88-audit/` | 详细业务测试脚本 | 手动或 `run-f88-regression.js` |

`eval/cases/` 是 `examples/` 的精选子集，确保关键链路在每次变更后自动验证。
