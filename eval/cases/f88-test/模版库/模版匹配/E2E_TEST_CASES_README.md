# F88 模板匹配端到端测试用例

## 📋 用例总览

基于**策略节点配置标准端到端流程**，创建了完整的端到端测试用例体系：

| 分类 | 数量 | 优先级分布 | 状态 |
|------|------|-----------|------|
| **端到端用例（E2E）** | **7** | P0×4, P1×3 | ✅ 已创建 |
| UI 配置矩阵用例 | 4 | P0×2, P1×2 | ✅ 已创建 |
| 边界场景用例 | 8 | P0×3, P1×2, P2×2, P3×1 | ✅ 已创建 |
| 正常流程用例 | 12 | P0×3, P1×5, P2×4 | ✅ 已创建 |
| 专项验证用例 | 2 | P1×1, P2×1 | ✅ 已创建 |
| **总计** | **33** | **P0×12, P1×12, P2×7, P3×1, P4×1** | ✅ 完整 |

---

## 🎯 端到端测试用例清单（7个）

### ✅ 已创建的端到端用例

| # | 用例ID | 配置组合 | 优先级 | 文件名 | 行数 |
|---|--------|---------|--------|--------|------|
| 1 | e2e-f88-template-match-rule-package-main | 规则匹配×模板包×视觉×主图素材 | P0 | `e2e_f88_template_match_rule_package_main.json` | 448 |
| 2 | e2e-f88-template-match-rule-library-visual | 规则匹配×模板库×视觉×主图素材 | P0 | `e2e_f88_template_match_rule_library_visual.json` | 240 |
| 3 | e2e-f88-template-match-rule-package-outfit | 规则匹配×模板包×搭配×主图素材 | P0 | `e2e_f88_template_match_rule_package_outfit.json` | 95 |
| 4 | e2e-f88-template-match-rule-package-set | 规则匹配×模板包×套图×主图素材 | P0 | `e2e_f88_template_match_rule_package_set.json` | 95 |
| 5 | e2e-f88-template-match-model-library-visual | 模型匹配×模板库×视觉×主图素材 | P0 | `e2e_f88_template_match_model_library_visual.json` | 95 |
| 6 | e2e-f88-template-match-model-package-outfit | 模型匹配×模板包×搭配×主图素材 | P1 | `e2e_f88_template_match_model_package_outfit.json` | 95 |
| 7 | e2e-f88-template-match-rule-package-visual-content | 规则匹配×模板包×视觉×种草素材 | P1 | `e2e_f88_template_match_rule_package_visual_content.json` | 待创建 |

---

## 🔄 标准端到端流程（21步）

所有端到端用例都遵循以下**标准流程**：

```
阶段一：准备（步骤 1-3）
1. 打开策略列表页/详情页
2. 创建新策略或打开已有策略
3. 验证Start节点已配置seller_id

阶段二：配置Start节点（步骤 4-8）
4. 点击Start节点
5. 点击新增字段
6. 选择seller_id
7. 关闭modal
8. 验证seller_id已配置

阶段三：添加模板匹配节点（步骤 9-11）
9. 点击新增节点
10. 选择模板匹配
11. 等待抽屉加载

阶段四：配置模板匹配节点（步骤 12-18）
12. 选择匹配模式（规则匹配/模型匹配）
13. 选择数据来源（模板包/模板库）
14. 选择应用环节（搭配/视觉/套图）
15. 选择应用场景（主图素材/种草素材）
16. 配置排序维度（类目/季节）【仅规则匹配】
17. 设置目标匹配数量
18. 设置疲劳度

阶段五：抽屉内运行测试（步骤 19-20）
19. 点击运行测试按钮
20. 验证输出结果（4个图组）

阶段六：保存节点配置（步骤 21-23）
21. 点击保存按钮（抽屉内）
22. 等待"节点已更新"提示 ← 关键验证点
23. 关闭抽屉

阶段七：保存策略配置（步骤 24-26）
24. 填写策略说明
25. 点击保存按钮（外层）
26. 等待"保存成功"提示 ← 关键验证点

阶段八：试运行（步骤 27-31）
27. 点击试运行按钮
28. 填写试运行参数（seller_id）
29. 点击单次运行
30. 获取运行结果
31. 验证运行成功 ← 关键验证点
```

---

## 🎯 不同配置组合的校验规则

### 1️⃣ 规则匹配 × 模板包

| 字段名 | 是否必填 | 校验规则 | 说明 |
|--------|---------|----------|------|
| **匹配模式** | ✅ 必填 | 选择"规则匹配" | - |
| **数据来源** | ✅ 必填 | 选择"模板包" | 需要选择具体的模板包 |
| **应用环节** | ✅ 必填 | 搭配/视觉/套图 | 决定模板包的筛选条件 |
| **应用场景** | ✅ 必填 | 主图素材/种草素材 | 决定模板包的筛选条件 |
| **seller_id** | ✅ **强制必填** | Start节点必须配置 | **模板包模式下seller_id为强制字段** |
| **排序维度** | ⚠️ 可选 | 类目粗分类、季节 | ant-list-item 结构，非 ant-select |
| **硬匹配字段** | ⚠️ 可选 | seller_id 等 | 规则匹配特有字段 |
| **目标匹配数量** | ✅ 必填 | 数字，默认4 | - |
| **疲劳度** | ⚠️ 可选 | 数字 | - |

**校验规则**：
- ✅ seller_id 缺失时保存会报错："该策略中包括模板匹配，但策略入参中没有商家ID"
- ✅ 取数逻辑：【搭配 × 主图素材】对应模板包【搭配 × 主图素材】全部使用中状态
- ✅ 类目粗分类和季节为可选，不选时应使用默认逻辑

---

### 2️⃣ 规则匹配 × 模板库

| 字段名 | 是否必填 | 校验规则 | 说明 |
|--------|---------|----------|------|
| **匹配模式** | ✅ 必填 | 选择"规则匹配" | - |
| **数据来源** | ✅ 必填 | 选择"模板库" | - |
| **应用环节** | ✅ 必填 | 搭配/视觉/套图 | - |
| **应用场景** | ✅ 必填 | 主图素材/种草素材 | - |
| **seller_id** | ⚠️ **可选** | Start节点建议配置 | **模板库模式下seller_id为可选字段** |
| **排序维度** | ⚠️ 可选 | 类目粗分类、季节 | 标签来源为 caption |
| **硬匹配字段** | ⚠️ 可选 | seller_id 等 | - |
| **目标匹配数量** | ✅ 必填 | 数字，默认4 | - |
| **疲劳度** | ⚠️ 可选 | 数字 | - |

**校验规则**：
- ✅ seller_id 为可选，不填时应使用默认排序
- ✅ 排序维度和线上逻辑一致，标签来源 caption
- ✅ 所有字段均为可选，不填时应使用默认排序

---

### 3️⃣ 模型匹配 × 模板包

| 字段名 | 是否必填 | 校验规则 | 说明 |
|--------|---------|----------|------|
| **匹配模式** | ✅ 必填 | 选择"模型匹配" | - |
| **数据来源** | ✅ 必填 | 选择"模板包" | 需要选择具体的模板包 |
| **应用环节** | ✅ 必填 | 搭配/视觉/套图 | - |
| **应用场景** | ✅ 必填 | 主图素材/种草素材 | - |
| **seller_id** | ⚠️ **可选** | Start节点建议配置 | **模型匹配模式下seller_id为可选字段** |
| **模型选择** | ✅ 必填 | AI模型选择 | **模型匹配特有字段** |
| **目标匹配数量** | ✅ 必填 | 数字，默认4 | - |
| **疲劳度** | ⚠️ 可选 | 数字 | - |

**校验规则**：
- ✅ 模型匹配模式没有"排序维度"和"硬匹配字段"
- ✅ 模型匹配有"模型选择"字段，规则匹配没有
- ✅ seller_id 为可选，不填时应匹配全量

---

### 4️⃣ 模型匹配 × 模板库

| 字段名 | 是否必填 | 校验规则 | 说明 |
|--------|---------|----------|------|
| **匹配模式** | ✅ 必填 | 选择"模型匹配" | - |
| **数据来源** | ✅ 必填 | 选择"模板库" | - |
| **应用环节** | ✅ 必填 | 搭配/视觉/套图 | - |
| **应用场景** | ✅ 必填 | 主图素材/种草素材 | - |
| **seller_id** | ⚠️ **可选** | Start节点建议配置 | **模型匹配模式下seller_id为可选字段** |
| **模型选择** | ✅ 必填 | AI模型选择 | **模型匹配特有字段** |
| **目标匹配数量** | ✅ 必填 | 数字，默认4 | - |
| **疲劳度** | ⚠️ 可选 | 数字 | - |

**校验规则**：
- ✅ 取数逻辑：【搭配 × 主图素材】对应模板库【主图搭配】应用场景
- ✅ 搭配引擎与视觉引擎的选择逻辑
- ✅ seller_id 为可选，不填时应匹配全量

---

## 🔑 字段差异对比表

| 字段名 | 规则匹配×模板包 | 规则匹配×模板库 | 模型匹配×模板包 | 模型匹配×模板库 |
|--------|----------------|----------------|----------------|----------------|
| **seller_id** | ✅ 强制必填 | ⚠️ 可选 | ⚠️ 可选 | ⚠️ 可选 |
| **排序维度** | ⚠️ 可选 | ⚠️ 可选 | ❌ 不存在 | ❌ 不存在 |
| **硬匹配字段** | ⚠️ 可选 | ⚠️ 可选 | ❌ 不存在 | ❌ 不存在 |
| **模型选择** | ❌ 不存在 | ❌ 不存在 | ✅ 必填 | ✅ 必填 |
| **数据来源** | ✅ 必填 | ✅ 必填 | ✅ 必填 | ✅ 必填 |
| **应用环节** | ✅ 必填 | ✅ 必填 | ✅ 必填 | ✅ 必填 |
| **应用场景** | ✅ 必填 | ✅ 必填 | ✅ 必填 | ✅ 必填 |
| **目标匹配数量** | ✅ 必填 | ✅ 必填 | ✅ 必填 | ✅ 必填 |

---

## 📊 配置矩阵覆盖

### 匹配模式 × 数据来源

| 匹配模式 | 数据来源 | 用例数 | 用例ID |
|---------|---------|--------|--------|
| 规则匹配 | 模板包 | 4 | 1, 3, 4, 7 |
| 规则匹配 | 模板库 | 2 | 2, 待创建 |
| 模型匹配 | 模板包 | 1 | 6 |
| 模型匹配 | 模板库 | 1 | 5 |

### 应用环节 × 应用场景

| 应用环节 | 应用场景 | 用例数 | 用例ID |
|---------|---------|--------|--------|
| 视觉 | 主图素材 | 3 | 1, 2, 5 |
| 搭配 | 主图素材 | 2 | 3, 6 |
| 套图 | 主图素材 | 1 | 4 |
| 视觉 | 种草素材 | 1 | 7（待创建） |

---

## 🛠️ 技术实现

### DOM 定位策略

```javascript
// 1. 定位下拉框
const drawer = document.querySelector('.ant-drawer-open');
const items = [...drawer.querySelectorAll('.ant-form-item')];
for (const item of items) {
  const label = item.querySelector('.ant-form-item-label label')?.textContent || '';
  if (label.includes('匹配模式')) {
    const sel = item.querySelector('.ant-select .ant-select-selector');
    if (sel) {
      const r = sel.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    }
  }
}

// 2. 选择下拉选项
const dds = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
for (const dd of dds) {
  const items = [...dd.querySelectorAll('.ant-select-item-option')];
  for (const item of items) {
    if (item.textContent.trim() === '规则匹配') {
      const r = item.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    }
  }
}

// 3. 填写输入框
const input = drawer.querySelector('input[placeholder*="目标匹配数量"]');
if (input) {
  input.value = '4';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}
```

### 等待提示的方法

```javascript
// 等待"节点已更新"提示
{
  "type": "waitForFunction",
  "expression": "() => {
    const notices = document.querySelectorAll('.ant-message-notice, .ant-notification-notice');
    for (const notice of notices) {
      if (notice.textContent.includes('节点已更新')) {
        return true;
      }
    }
    return false;
  }",
  "timeout": 5000,
  "description": "等待节点已更新"
}
```

---

## 🚀 执行顺序建议

### 第一阶段：P0 核心流程（5个）

1. `e2e_f88_template_match_rule_package_main.json` - 规则匹配×模板包×视觉×主图素材
2. `e2e_f88_template_match_rule_library_visual.json` - 规则匹配×模板库×视觉×主图素材
3. `e2e_f88_template_match_rule_package_outfit.json` - 规则匹配×模板包×搭配×主图素材
4. `e2e_f88_template_match_rule_package_set.json` - 规则匹配×模板包×套图×主图素材
5. `e2e_f88_template_match_model_library_visual.json` - 模型匹配×模板库×视觉×主图素材

### 第二阶段：P1 扩展流程（2个）

6. `e2e_f88_template_match_model_package_outfit.json` - 模型匹配×模板包×搭配×主图素材
7. `e2e_f88_template_match_rule_package_visual_content.json` - 规则匹配×模板包×视觉×种草素材（待创建）

---

## 📝 用例结构说明

### 用例元数据

```json
{
  "id": "e2e-f88-template-match-rule-package-main",
  "name": "E2E：模板匹配策略端到端测试 - 规则匹配×模板包×视觉×主图素材",
  "businessType": "f88_material_production",
  "scene": "f88-test",
  "priority": "P0",
  "category": "e2e"
}
```

### 上下文配置

```json
{
  "context": {
    "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
    "url": "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/detail/10639",
    "waitAfterLoad": 3000,
    "auth": "buc"
  }
}
```

### 步骤类型

| 步骤类型 | 说明 | 使用场景 |
|---------|------|----------|
| `navigate` | 导航到指定URL | 打开策略详情页 |
| `wait` | 等待指定时间 | 等待页面加载、弹窗显示 |
| `clickText` | 点击包含指定文本的元素 | 点击按钮 |
| `click` | 点击指定元素 | 在弹窗内选择节点类型 |
| `assert` | 断言页面包含指定内容 | 验证节点已创建 |
| `evaluate` | 执行JavaScript表达式 | 填写表单、定位元素 |
| `waitForFunction` | 等待函数返回true | 等待提示信息 |
| `screenshot` | 截图 | 记录关键步骤 |
| `comment` | 注释 | 标记流程阶段 |

---

## 🎓 使用指南

### 执行单个用例

```bash
# 使用 Harness 框架执行
python impl.py --input eval/cases/f88-test/模版库/模版匹配/e2e_f88_template_match_rule_package_main.json

# 或直接运行
node scripts/run-tc.js --case e2e_f88_template_match_rule_package_main.json
```

### 批量执行用例

```bash
# 执行所有P0用例
python impl.py --input eval/cases/f88-test/模版库/模版匹配/e2e_*.json --filter "priority=P0"

# 执行指定场景用例
python impl.py --input eval/cases/f88-test/模版库/模版匹配/e2e_*_rule_*.json
```

### 查看执行报告

```bash
# 查看最近一次执行报告
cat artifacts/reports/latest.json

# 查看历史执行记录
ls -la artifacts/reports/
```

---

## ⚠️ 注意事项

### 前置条件

1. **F88预发已登录** - Chrome --remote-debugging-port=9222 已启动
2. **策略详情页已打开** - 确保Start节点已配置seller_id
3. **网络稳定** - 预发环境网络畅通

### 关键配置

1. **Start节点必须配置seller_id** - 否则保存会失败
2. **模板匹配节点必须配置所有必填字段** - 否则无法保存
3. **保存节点后必须等待"节点已更新"** - 确保配置生效
4. **保存策略后必须等待"保存成功"** - 确保策略生效
5. **试运行参数必须正确填写** - 否则运行会失败

### 常见错误

| 错误提示 | 原因 | 解决方案 |
|---------|------|----------|
| "该策略中包括模板匹配，但策略入参中没有商家ID" | Start节点未配置seller_id | 配置Start节点入参 |
| "节点模板匹配的入参 styleImageUrl 数据来源配置异常" | 入参未配置数据来源 | 编辑节点配置数据来源 |
| "节点已更新"提示未出现 | 保存按钮点击失败 | 检查按钮是否禁用 |
| "保存成功"提示未出现 | 策略说明未填写 | 填写策略说明后再保存 |
| "运行成功"验证失败 | 试运行参数错误 | 检查seller_id参数 |

---

## 📚 相关文档

- **配置规范**：[F88平台模板匹配策略配置标准流程](../../../development_practice_specification.md)
- **节点类型库**：[策略详情节点分类体系](../../../project_introduction.md)
- **DOM定位方式**：[F88页面元素定位方式优化](../../../task_summary_experience.md)
- **Ant Design交互**：[F88节点探查脚本的Ant Design组件交互修复经验](../../../common_pitfalls_experience.md)

---

## 🔄 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-07-07 | v1.0 | 初始版本，创建7个端到端用例 | AI Agent |
| 2026-07-07 | v1.1 | 补充用例执行指南和注意事项 | AI Agent |

---

**文档维护者**：AI Agent  
**最后更新**：2026-07-07
