# F88 模板匹配测试用例清单

## 📊 用例概览

**用例目录**: `eval/cases/f88-test/模版库/模版匹配/`  
**用例总数**: 24 个  
**创建时间**: 2026-07-07  
**覆盖场景**: UI 端到端配置、边界场景、正常流程、全配置矩阵

---

## 🎯 核心用例分类

### 1. UI 端到端全流程用例（4个）

| 用例 ID | 名称 | 优先级 | 覆盖场景 |
|---------|------|--------|----------|
| `ui_f88_create_template_strategy.json` | UI：F88 新建模板匹配策略（全流程） | P0 | 从策略列表新建策略，配置 Start 节点入参 seller_id，添加模板匹配节点，保存并验证持久化 |
| `ui_f88_template_match_node_config.json` | UI：F88 模板匹配节点完整配置 | P0 | 完整配置模板匹配节点的所有必填字段（匹配模式、数据来源、应用环节、应用场景、排序维度） |
| `ui_f88_node_input_inspection.json` | UI：F88 节点入参探查工具 | P0 | 配置前探查节点的所有入参字段、必填要求、数据来源配置要求 |
| `ui_f88_template_match_all_configs.json` | UI：F88 模板匹配节点全配置矩阵 | P1 | 覆盖所有配置组合（匹配模式×数据来源×应用环节×应用场景） |

### 2. 边界场景用例（6个）

| 用例 ID | 名称 | 优先级 | 验证点 |
|---------|------|--------|--------|
| `boundary_f88_template_match_seller_required.json` | 边界场景：模板匹配节点 seller_id 为强制字段 | P0 | Start 节点必须配置 seller_id，否则保存失败 |
| `boundary_f88_template_match_start_no_seller.json` | 边界场景：Start节点未配置seller_id时保存 | P0 | 验证 API 返回"策略入参中没有商家ID"错误 |
| `boundary_f88_template_match_no_data_source.json` | 边界场景：入参未配置数据来源时保存 | P0 | 验证 API 返回"入参数据来源配置异常"错误 |
| `boundary_f88_rule_package_seller_empty.json` | 边界场景：规则匹配×模板包，seller_id 为空 | P1 | 验证 seller_id 为空时的错误处理 |
| `boundary_f88_model_package_seller_empty.json` | 边界场景：模型匹配×模板包，seller_id 为空 | P1 | 验证模型匹配模式下的 seller_id 校验 |
| `boundary_f88_model_library_no_data.json` | 边界场景：模型匹配×模板库，无数据 | P2 | 验证模板库无数据时的处理逻辑 |
| `boundary_f88_visual_library_no_washed.json` | 边界场景：视觉×模板库，未洗图 | P2 | 验证未洗图数据的处理 |
| `boundary_f88_url_seq_cycle.json` | 边界场景：URL序号循环问题 | P3 | 验证节点序号不会循环重复 |

### 3. 正常流程用例（12个）

| 用例 ID | 名称 | 优先级 | 配置组合 |
|---------|------|--------|----------|
| `normal_f88_template_match_rule_package.json` | 正常流程：规则匹配 × 模板包 | P0 | 规则匹配 + 模板包 + 搭配 + 主图素材 |
| `normal_f88_template_match_rule_library.json` | 正常流程：规则匹配 × 模板库 | P0 | 规则匹配 + 模板库 + 视觉 + 主图素材 |
| `normal_f88_template_match_model_package.json` | 正常流程：模型匹配 × 模板包 | P1 | 模型匹配 + 模板包 + 搭配 + 主图素材 |
| `normal_f88_template_match_model_library.json` | 正常流程：模型匹配 × 模板库 | P1 | 模型匹配 + 模板库 + 视觉 + 主图素材 |
| `normal_f88_template_match_visual_library.json` | 正常流程：视觉 × 模板库 | P1 | 规则匹配 + 模板库 + 视觉 + 种草素材 |
| `normal_f88_template_match_model_mode.json` | 正常流程：模型匹配模式完整配置 | P0 | 模型匹配全字段配置（含模型选择） |
| `normal_f88_match_app_scene_main.json` | 正常流程：应用场景 - 主图素材 | P1 | 主图素材场景专项验证 |
| `normal_f88_match_app_scene_content.json` | 正常流程：应用场景 - 种草素材 | P1 | 种草素材场景专项验证 |
| `normal_f88_match_app_link_outfit.json` | 正常流程：应用环节 - 搭配 | P2 | 搭配环节专项验证 |
| `normal_f88_match_target_count.json` | 正常流程：目标匹配数量配置 | P2 | 验证目标匹配数量字段 |
| `normal_f88_template_match_priority.json` | 正常流程：优先级配置 | P2 | 验证节点优先级 |
| `normal_f88_template_match_output_structure.json` | 正常流程：输出结构验证 | P1 | 验证匹配到的图组输出结构 |
| `normal_f88_template_match_reuse_upstream.json` | 正常流程：复用上游节点输出 | P2 | 验证入参复用上游节点输出 |

### 4. 专项验证用例（2个）

| 用例 ID | 名称 | 优先级 | 验证点 |
|---------|------|--------|--------|
| `normal_f88_template_match_output_structure.json` | 正常流程：输出结构验证 | P1 | 验证模板匹配节点的输出数据结构 |
| `normal_f88_template_match_reuse_upstream.json` | 正常流程：复用上游节点输出 | P2 | 验证入参可以复用上游节点的输出变量 |

---

## 🔧 关键配置字段

### 模板匹配节点必填字段（规则匹配模式）

| 字段名 | 类型 | 选项 | 默认值 |
|--------|------|------|--------|
| 匹配模式 | select | 规则匹配、模型匹配 | 规则匹配 |
| 数据来源 | select | 模板包、模板库 | - |
| 应用环节 | select | 搭配、视觉、套图 | - |
| 应用场景 | select | 主图素材、种草素材 | - |
| 排序维度 | list | 类目、季节 | - |
| 硬匹配字段 | select | 动态选项 | - |
| 目标匹配数量 | input | 数字 | 4 |

### 模板匹配节点必填字段（模型匹配模式）

| 字段名 | 类型 | 选项 | 默认值 |
|--------|------|------|--------|
| 匹配模式 | select | 规则匹配、模型匹配 | 模型匹配 |
| 数据来源 | select | 模板包、模板库 | - |
| 应用环节 | select | 搭配、视觉、套图 | - |
| 应用场景 | select | 主图素材、种草素材 | - |
| 模型选择 | select | 动态模型列表 | - |

### Start 节点入参（强制要求）

| 字段名 | 必填 | 说明 |
|--------|------|------|
| seller_id | ✅ | 商家 ID，模板匹配策略保存时 API 校验必须 |

---

## ⚠️ 常见错误与风险点

### 1. Start 节点未配置 seller_id
**错误提示**: "该策略中包括模板匹配，但策略入参中没有商家ID"  
**解决方案**: 配置 Start 节点 → 新增字段 → 选择 seller_id

### 2. 入参未配置数据来源
**错误提示**: "节点模板匹配的入参 styleImageUrl 数据来源配置异常:未知数据来源: null"  
**解决方案**: 编辑模板匹配节点 → 配置入参区域的数据来源

### 3. 多抽屉问题
**问题**: 页面可能有多个 `.ant-drawer` 实例  
**解决方案**: 使用 `.ant-drawer-open` 选择当前打开的抽屉

### 4. 节点类型选择
**问题**: 新增节点弹窗使用 `ant-card-hoverable` 卡片  
**解决方案**: 使用 `.ant-card-meta-title` 精确匹配标题文本

### 5. getBoundingClientRect() 序列化
**问题**: Puppeteer evaluate 中直接返回 `el.getBoundingClientRect()` 得到空对象 `{}`  
**解决方案**: 显式提取属性 `{ x: br.x, y: br.y, width: br.width, height: br.height }`

---

## 📋 用例执行顺序建议

### P0 级用例（优先执行）
1. `ui_f88_node_input_inspection.json` - 先探查入参要求
2. `ui_f88_create_template_strategy.json` - 完整创建流程
3. `ui_f88_template_match_node_config.json` - 节点完整配置
4. `boundary_f88_template_match_start_no_seller.json` - 边界场景验证
5. `boundary_f88_template_match_no_data_source.json` - 边界场景验证
6. `normal_f88_template_match_rule_package.json` - 规则匹配基础配置
7. `normal_f88_template_match_model_mode.json` - 模型匹配完整配置

### P1 级用例（回归执行）
8. `ui_f88_template_match_all_configs.json` - 全配置矩阵
9. `normal_f88_template_match_rule_library.json` - 模板库配置
10. `normal_f88_template_match_model_package.json` - 模型匹配×模板包
11. `normal_f88_match_app_scene_main.json` - 主图素材场景
12. `normal_f88_match_app_scene_content.json` - 种草素材场景

### P2 级用例（可选执行）
13. 其他专项验证用例

---

## 🎓 使用说明

### 配置前必做
```bash
# 1. 运行入参探查工具
运行: ui_f88_node_input_inspection.json
输出: 节点入参探查报告（字段总数、必填字段、下拉选项等）

# 2. 根据报告配置节点
运行: ui_f88_template_match_node_config.json
依据: 探查报告中的必填字段列表

# 3. 保存策略并验证
运行: 保存按钮
结果: ✅ 成功（因为入参已正确配置）
```

### 关键 DOM 交互模式
- 使用 `.ant-drawer-open` 选择当前打开的抽屉
- 使用 `.ant-card-meta-title` 精确匹配节点类型标题
- 使用 `Math.round()` 显式提取 `getBoundingClientRect()` 属性
- 使用 `mouse.click` 坐标点击下拉框选项

---

## 📚 相关文档

- **脚本文件**: `scripts/create-template-strategy.js`
- **知识库**: `knowledge/f88/f88-material-production.json`
- **场景 Skill**: `scenes/f88-test/`
- **PRD 文档**: 钉钉文档 `MNdoBb60VLYDGNPytBE4qmgwJlemrZQ3`

---

**最后更新**: 2026-07-07  
**维护者**: Web 自动化测试团队
