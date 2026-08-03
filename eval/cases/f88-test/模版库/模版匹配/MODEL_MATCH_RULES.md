# F88 模板匹配 - 模型匹配规则详解

> **文档目的**：详细说明模型匹配模式的具体规则、算法逻辑和实现机制

---

## 📊 模板匹配的两种模式

F88平台的模板匹配节点支持**两种匹配模式**：

| 模式 | 处理器 | 匹配方式 | 适用场景 |
|------|--------|---------|---------|
| **规则匹配** | `TemplateMatchProcessor` | 基于规则过滤+排序 | 需要精确控制匹配逻辑 |
| **模型匹配** | `TemplateMatchProcessor` + AI模型 | 基于AI算法匹配 | 需要智能化匹配 |

---

## 🎯 规则匹配模式（TemplateMatchProcessor）

### 核心算法流程

```java
// 文件：application/workflow2/processor/template/TemplateMatchProcessor.java

process() 完整流程：
1. 提取上下文：sellerId, stage(applyRange), scene(applyScene), taoCate, seasonTag, styleTags, targetMatchCount(默认1)
2. 查询活跃包：status=4(IN_USE) + sellerId + stage + scene
3. 克隆去重：tryGetUsedTemplateIds() → 检查 CLONE_FROM_INSTANCE_ID → 提取已匹配模板 ID（biz_record_id 去重）
4. 解析+排序（parseAndSortTemplates）：
   a. 解析：遍历所有包 → 反序列化 templateContent → 仅取 auditStatus=6(APPROVE) 的模板
   b. 类目过滤：
      - mustMatchFields 不含 match_cate 时才过滤
      - 匹配逻辑：tagId 精确匹配(score=2) / 同 parentTagId(score=1)
      - 存活模板太少 → 提前返回
   c. 季节过滤：
      - SEASON_FILTER_MAPPING 决定允许的季节组合（如"春"允许"春""夏""秋"）
      - 模糊匹配：targetSeason.contains(tag.trim()) → 不对称！"春季".contains("春")=true，反之 false
   d. Tair 使用计数：
      - key: template_use_count:{batchId}:{templateId}，TTL=24h
      - 超 maxCount 的模板被过滤
      - **全部超限时清除所有计数重试**（软限制，非硬上限）
   e. 排序（matchTypes 列表顺序决定优先级）：
      - cate: 类目匹配分(2精确/1同父/0无) + 使用次数升序
      - season: 季节分(2精确/1模糊/0无)
      - style: 风格分(2完全匹配/1有交集/0无)
      - ctr: recApplyItemCtrOnline14d 降序
   f. 克隆去重：移除已用模板 → 不够 targetMatchCount 则保留
   g. 截断：取 top targetMatchCount
5. 使用计数递增：incrUserCount()
6. 输出：matched_template_ids, matched_template_used_ids(sellerId_pkgId_templateId), matched_template_pkg, matchedImg
```

### 匹配维度优先级

| 维度 | 优先级 | 匹配逻辑 | 得分规则 |
|------|--------|---------|---------|
| **类目 (CATE)** | 最高 | tagId 精确匹配 / 同 parentTagId | 精确=2, 同父=1, 无=0 |
| **季节 (SEASON)** | 次高 | SEASON_FILTER_MAPPING | 精确=2, 模糊=1, 无=0 |
| **风格 (STYLE)** | 次低 | 完全匹配 / 有交集 | 完全=2, 交集=1, 无=0 |
| **CTR** | 最低 | recApplyItemCtrOnline14d | 降序排列 |

### 疲劳度控制

```
Tair 计数：
- key: template_use_count:{batchId}:{templateId}
- TTL: 24小时
- 限制: 每模板每批次最多 5 次
- 分布式锁：保证计数原子性
- 风险：锁超时可能导致计数偏差
```

### 去重逻辑

```java
// 幂等检查 + 业务记录ID去重
checkDataProcessed() + BIZ_RECORD_ID

// 克隆去重
tryGetUsedTemplateIds() → 检查 CLONE_FROM_INSTANCE_ID
```

---

## 🤖 模型匹配模式

### 核心概念

```
模型匹配 = 规则匹配基础流程 + AI模型优化

关键差异：
1. 必须选择AI模型（如 wan2.7-image）
2. 没有"排序维度"和"硬匹配字段"配置
3. 由AI算法自动决定匹配逻辑
4. seller_id 用于查询店铺基因，优化匹配结果
```

### 匹配流程（推测）

```
1. 提取上下文：sellerId, stage, scene, taoCate, ...
2. 查询店铺基因（基于 seller_id）
   - 店铺风格偏好
   - 历史匹配记录
   - 商家活跃模板包
3. 调用AI模型进行匹配
   - 输入：店铺基因 + 模板特征
   - 输出：匹配度评分 + 排序
4. 返回匹配结果（matched_template_ids, matchedImg）
```

### seller_id 的作用

```javascript
// 模型匹配模式
async function modelMatch(sellerId, stage, scene) {
  // 1. 查询店铺基因
  const shopGene = await queryShopGene(sellerId);
  // {
  //   stylePreference: ['简约', '复古'],
  //   historyMatches: [{templateId: 'xxx', score: 0.95}],
  //   activePackages: [{pkgId: 'yyy', useCount: 3}]
  // }

  // 2. 查询候选模板
  const candidates = await queryActiveTemplates(stage, scene);

  // 3. AI模型匹配
  const matched = await aiModel.match(shopGene, candidates);
  // {
  //   templateIds: ['t1', 't2', 't3'],
  //   scores: [0.92, 0.88, 0.85]
  // }

  // 4. 返回结果（不会强校验 seller_id）
  return matched;
}
```

### 与规则匹配的对比

| 对比项 | 规则匹配 | 模型匹配 |
|--------|---------|---------|
| **排序方式** | 手动配置（类目>季节>风格>CTR） | AI自动排序 |
| **配置字段** | 排序维度、硬匹配字段 | 模型选择 |
| **seller_id** | 硬匹配条件（模板包模式） | 查询店铺基因（不参与强校验） |
| **灵活性** | 高（可精确控制） | 低（依赖AI） |
| **匹配质量** | 依赖规则设计 | 依赖AI模型质量 |
| **适用场景** | 需要精确控制 | 需要智能化 |

---

## 🔍 模型匹配的具体规则（基于PRD和知识库）

### 1️⃣ 入参要求

```
必填字段：
- seller_id（入参必传，用于查询店铺基因）
- 应用环节（搭配/视觉/套图）
- 应用场景（主图素材/种草素材）
- 模型选择（AI模型）
- 目标匹配数量

可选字段：
- 疲劳度
```

### 2️⃣ 匹配逻辑

```
Step 1: 查询候选模板
- 基于应用环节和应用场景筛选
- 查询活跃状态的模板包/模板库

Step 2: 查询店铺基因
- 基于 seller_id 查询
- 包含店铺风格偏好、历史匹配记录等

Step 3: AI模型匹配
- 输入：店铺基因 + 候选模板特征
- 输出：匹配度评分 + 排序

Step 4: 返回结果
- matched_template_ids
- matchedImg
- matched_template_used_ids
```

### 3️⃣ 校验规则

```
UI配置校验：
- ✅ 必须选择AI模型
- ✅ 必须选择数据来源（模板包/模板库）
- ✅ 必须选择应用环节
- ✅ 必须选择应用场景
- ✅ Start节点必须配置seller_id

运行时校验：
- ✅ 必须有seller_id入参
- ❌ 不会强校验seller_id与模板的匹配关系
- ✅ 但会影响匹配质量（店铺基因）
```

---

## 📚 已知问题与风险点

### 规则匹配模式的已知问题

| 问题 | 位置 | 风险 |
|------|------|------|
| tagSearchConditionEntityList 静态缓存永不失效 | TemplateMatchProcessor:65 | 类目标签变更后验证匹配结果 |
| Tair 计数重置（全超限时清除） | TemplateMatchProcessor.parseAndSortTemplates | 大量请求耗尽配额后验证轮转 |
| 季节匹配不对称 | TemplateMatchProcessor SEASON_FILTER_MAPPING | 验证各季节组合的匹配结果 |

### 模型匹配模式的推测风险

| 风险点 | 说明 |
|--------|------|
| AI模型质量 | 模型训练数据不足影响匹配质量 |
| 店铺基因准确性 | seller_id 查询的店铺基因可能不准确 |
| 性能问题 | AI模型调用可能耗时较长（30-60秒） |
| 可解释性差 | 无法精确控制匹配逻辑 |

---

## 🎓 自动化测试注意事项

### 规则匹配用例

```javascript
// 验证排序维度配置
assert.contains('排序维度');
assert.contains('类目');
assert.contains('季节');

// 验证硬匹配字段配置
assert.contains('硬匹配字段');
assert.contains('seller_id');

// 验证疲劳度控制
// 每模板每批次最多5次
```

### 模型匹配用例

```javascript
// 验证模型选择字段
assert.contains('模型选择');
assert.contains('wan2.7-image');

// 验证不存在的字段
assert.not.contains('排序维度');
assert.not.contains('硬匹配字段');

// 验证seller_id入参必传
assert.contains('节点已更新');
// 试运行时需要传入seller_id
await trialRun({ seller_id: 'test_seller_123' });
```

---

## 📖 参考文档

- **F88主图素材供给产品方案 v3.0 20260623**
- **F88 模板匹配（并行去重+通用/店铺模板包）** - `knowledge/synced-qoderwork/f88-test/04-模板匹配.md`
- **F88 平台代码架构与技术实现** - `knowledge/synced-qoderwork/f88-test/code-architecture.md`
- **TemplateMatchProcessor 代码实现** - `application/workflow2/processor/template/TemplateMatchProcessor.java`

---

## 🔄 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-07-07 | v1.0 | 初始版本，整理模型匹配规则 | AI Agent |

---

**文档维护者**：AI Agent  
**最后更新**：2026-07-07  
**文档状态**：✅ 已完成

**注意**：知识库中关于"模型匹配"模式的详细描述较少，主要描述的是"规则匹配"模式（TemplateMatchProcessor）。模型匹配的具体实现可能需要进一步查询代码或咨询开发人员。
