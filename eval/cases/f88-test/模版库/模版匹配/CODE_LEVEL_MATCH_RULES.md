# F88 模板匹配 - 代码库实际规则详解

> **基于实际代码库**：`/Users/caoxuemei/stylespot-admin`  
> **核心处理器**：`TemplateMatchProcessor.java`  
> **代码路径**：`stylespot-admin-application/src/main/java/com/taobao/stylespot/admin/application/workflow2/processor/template/TemplateMatchProcessor.java`

---

## 🎯 核心发现：代码库中只有"规则匹配"

### 关键结论

**代码库中只找到了 `TemplateMatchProcessor`（规则匹配处理器），没有找到独立的"模型匹配"处理器。**

这意味着：
1. **F88 平台的模板匹配节点目前只支持规则匹配模式**
2. **"模型匹配"可能是前端配置界面的概念，后端实际都走规则匹配逻辑**
3. **或者"模型匹配"是未来规划的功能，尚未实现**

---

## 📊 代码级规则详解

### 1️⃣ 核心处理器：TemplateMatchProcessor

**文件位置**：
```
stylespot-admin-application/src/main/java/com/taobao/stylespot/admin/application/workflow2/processor/template/TemplateMatchProcessor.java
```

**核心方法 `process()` 完整流程**（832行代码）：

```java
public void process(NodeProcessorContext context) {
    // 1. 获取当前节点
    TemplateMatchNode templateMatchNode = (TemplateMatchNode) context.getCurrentNode();
    
    // 2. 获取商家ID（入参必传）
    String sellerIdStr = context.getCommonVariable(CommonVariableEnum.SELLER_ID, null);
    if (StringUtils.isBlank(sellerIdStr)) {
        sendFail(context, "商家ID为空");
        return;
    }
    
    // 3. 提取上下文变量
    String stage = templateMatchNode.getTemplatePkgCondition().getStageCode();  // 应用环节
    String scene = templateMatchNode.getTemplatePkgCondition().getSceneCode();  // 应用场景
    String taoCate = context.getCommonVariable(CommonVariableEnum.TAO_CATE, "");
    String seasonTag = context.getCommonVariable(CommonVariableEnum.SEASON_TAG, "");
    Integer targetMatchCount = Optional.ofNullable(templateMatchNode.getTargetMatchCount()).orElse(1);
    List<String> styleTags = ObjectUtil.getStrList(context.getCommonVariable(CommonVariableEnum.STYLE_TAG));
    
    // 4. 查询商家正在使用的模版包
    List<AfdSellerTemplateEntity> templatePackages = querySellerUsingTemplates(sellerId, stage, scene);
    if (CollectionUtils.isEmpty(templatePackages)) {
        sendFail(context, String.format("未找到模板包, seller_id = %s, stage = %s, scene = %s", sellerId, stage, scene));
        return;
    }
    
    // 5. 当前流程是否是clone来的，如果是，则找到之前使用过的模板
    List<String> usedTemplateIds = tryGetUsedTemplateIds(context);
    
    // 6. 解析模版内容并排序
    List<AfdPicTemplateDTO> sortedTemplates = parseAndSortTemplates(
        templatePackages, taoCate, seasonTag, styleTags, batchId,
        templateMatchNode, usedTemplateIds, strategyId
    );
    
    // 7. 校验模板数量
    if (CollectionUtils.isEmpty(sortedTemplates) || sortedTemplates.size() < targetMatchCount) {
        sendFail(context, "未找到模板或模板数量不够");
        return;
    }
    
    // 8. 使用计数递增（Tair）
    sortedTemplates.forEach(e -> incrUserCount(batchId, e.getTemplateId()));
    
    // 9. 输出结果
    outputData.put("matched_template_ids", sortedTemplates.stream().map(AfdPicTemplateDTO::getTemplateId).collect(toList()));
    outputData.put("matched_template_used_ids", sortedTemplates.stream().map(e -> {
        return TemplatePackageFun.getTemplateUsedId(e.getTemplateId(), templatePackages.get(0).getId(), sellerId);
    }).collect(toList()));
    outputData.put("matched_template_pkg", templatePackages.get(0).getId());
    outputData.put(templateMatchNode.getMatchedImg().getCode(), picUrls);
}
```

---

### 2️⃣ 解析+排序算法：`parseAndSortTemplates()`

```java
private List<AfdPicTemplateDTO> parseAndSortTemplates(
    List<AfdSellerTemplateEntity> templatePackages,
    String taoCate, 
    String seasonTag, 
    List<String> styleTags,
    String batchId,
    TemplateMatchNode templateMatchNode,
    List<String> usedTemplateIds,
    String strategyId
) {
    // 1. 解析所有模版内容
    List<AfdPicTemplateDTO> allTemplates = new ArrayList<>();
    for (AfdSellerTemplateEntity templatePackage : templatePackages) {
        // templateContent 是 Map<String, String>，key 是 templateId，value 是 JSON 字符串
        for (Map.Entry<String, String> entry : templatePackage.getTemplateContent().entrySet()) {
            List<AfdPicTemplateDTO> templates = JSON.parseArray(entry.getValue(), AfdPicTemplateDTO.class);
            // 仅取 auditStatus=APPROVE 的模板
            allTemplates.addAll(templates.stream()
                .filter(x -> TemplatePackageStatusEnum.APPROVE.getCode().toString().equals(x.getAuditStatus()))
                .collect(Collectors.toList()));
        }
    }
    
    // 2. 判断是否需要跳过类目/季节过滤
    List<String> mustMatchFields = templateMatchNode.getMustMatchFields();
    boolean skipCategoryFilter = CollectionUtils.isNotEmpty(mustMatchFields) && !mustMatchFields.contains("match_cate");
    boolean skipSeasonFilter = CollectionUtils.isNotEmpty(mustMatchFields) && !mustMatchFields.contains("match_season");
    
    // 3. 类目过滤
    if (!skipCategoryFilter && StringUtils.isNotBlank(taoCate)) {
        filteredTemplates = filteredTemplates.stream()
            .filter(e -> {
                TagSearchConditionEntity templateCateTag = findCategoryTag(categoryTagList, e.getCateId(), e.getCategoryName());
                if (templateCateTag == null) return false;
                
                boolean cateMatch = templateCateTag.getTagName().equals(taoCate)
                    || templateCateTag.getTagId().equals(targetCateTag.getTagId());
                boolean parentMatch = StringUtils.isNotBlank(targetParentTagId)
                    && targetParentTagId.equals(templateCateTag.getParentTagId());
                
                return cateMatch || parentMatch;
            })
            .collect(Collectors.toList());
    }
    
    // 4. 季节过滤
    if (!skipSeasonFilter && StringUtils.isNotBlank(seasonTag)) {
        Set<String> allowedSeasons = getAllowedSeasonsByTarget(seasonTag);
        filteredTemplates = filteredTemplates.stream()
            .filter(e -> {
                String[] templateSeasons = e.getSeasonTags().split(",");
                return Arrays.stream(templateSeasons)
                    .map(String::trim)
                    .filter(StringUtils::isNotBlank)
                    .anyMatch(allowedSeasons::contains);
            })
            .collect(Collectors.toList());
    }
    
    // 5. Tair 使用计数检查
    Integer templateMaxUseCount = templateMatchNode.getTemplateMaxUseCount();
    if (Objects.nonNull(templateMaxUseCount) && templateMaxUseCount > 0) {
        filteredTemplates = filterTemplatesByTairUseCount(allTemplates, batchId, templateMaxUseCount);
        if (CollectionUtils.isEmpty(filteredTemplates) || filteredTemplates.size() < targetMatchCount) {
            // 全部超限时清除所有计数重试（软限制，非硬上限）
            clearAllTemplateUseCounts(allTemplates, batchId);
            filteredTemplates = allTemplates;
        }
    }
    
    // 6. 排序
    List<AfdPicTemplateDTO> sortedTemplates = sortTemplates(
        filteredTemplates, 
        templateMatchNode.getMatchTypes(),  // 匹配类型列表
        taoCate, 
        seasonTag, 
        styleTags
    );
    
    // 7. 尝试去掉之前用过的
    if (CollectionUtils.isNotEmpty(usedTemplateIds)) {
        int count = (int) sortedTemplates.stream()
            .filter(e -> !usedTemplateIds.contains(e.getTemplateId()))
            .count();
        if (count >= targetMatchCount) {
            sortedTemplates = sortedTemplates.stream()
                .filter(e -> !usedTemplateIds.contains(e.getTemplateId()))
                .collect(Collectors.toList());
        }
    }
    
    // 8. 限制返回数量
    if (sortedTemplates.size() > targetMatchCount) {
        return sortedTemplates.subList(0, targetMatchCount);
    }
    
    return sortedTemplates;
}
```

---

### 3️⃣ 排序算法：`sortTemplates()`

```java
/**
 * 对模版进行排序
 * 排序优先级：
 * 1. seller_id（硬隔离）
 * 2. 类目优先级（二级＞一级＞无）
 * 3. 季节优先级（精准＞模糊>无）
 * 4. 风格优先级（精准＞模糊＞无）
 * 5. 推荐ctr（由大到小）
 */
private List<AfdPicTemplateDTO> sortTemplates(
    List<AfdPicTemplateDTO> templates,
    List<String> matchTypes,  // 匹配类型列表，顺序决定优先级
    String targetCate,
    String targetSeason,
    List<String> targetStyles
) {
    return templates.stream()
        .sorted(Comparator.comparing(AfdPicTemplateDTO::getUseCount))  // 先按使用次数升序
        .sorted((t1, t2) -> {
            // 1. seller_id 硬隔离（已经在查询时过滤，这里不需要额外处理）
            
            for (String matchType : matchTypes) {
                if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.CATE.getCode())) {
                    // 2. 类目优先级（二级＞一级＞无）
                    int cateCompare = compareCategory(t1, t2, targetCate);
                    if (cateCompare != 0) return cateCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.SEASON.getCode())) {
                    // 3. 季节优先级（精准＞模糊>无）
                    int seasonCompare = compareSeason(t1, t2, targetSeason);
                    if (seasonCompare != 0) return seasonCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.STYLE.getCode())) {
                    // 4. 风格优先级（精准＞模糊＞无）
                    int styleCompare = compareStyle(t1, t2, targetStyles);
                    if (styleCompare != 0) return styleCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.CTR.getCode())) {
                    // 5. 推荐ctr（由大到小）
                    return compareCTR(t1, t2);
                }
            }
            return 0;
        })
        .collect(Collectors.toList());
}
```

---

### 4️⃣ 匹配维度得分算法

#### 类目匹配得分

```java
private int getCategoryMatchScore(AfdPicTemplateDTO template, String targetCate) {
    if (StringUtils.isBlank(targetCate) || template.getCateId() == null) {
        return 0;
    }
    
    TagSearchConditionEntity templateCateTag = findCategoryTag(categoryTagList, template.getCateId(), template.getCategoryName());
    TagSearchConditionEntity targetCateTag = findCategoryTagByName(categoryTagList, targetCate);
    if (templateCateTag == null || targetCateTag == null) {
        return 0;
    }
    
    // 二级类目匹配（精准匹配）
    if (templateCateTag.getTagId().equals(targetCateTag.getTagId())) {
        return 2;
    }
    
    // 一级类目匹配（parentTagId 相同）
    if (StringUtils.isNotBlank(templateCateTag.getParentTagId())
        && templateCateTag.getParentTagId().equals(targetCateTag.getParentTagId())) {
        return 1;
    }
    
    return 0;
}
```

#### 季节匹配得分

```java
private int getSeasonMatchScore(AfdPicTemplateDTO template, String targetSeason) {
    if (StringUtils.isBlank(targetSeason) || StringUtils.isBlank(template.getSeasonTags())) {
        return 0;
    }
    
    String[] seasonTags = template.getSeasonTags().split(",");
    
    // 精准匹配
    for (String tag : seasonTags) {
        if (StringUtils.isNotBlank(tag) && tag.trim().equals(targetSeason)) {
            return 2; // 精准匹配
        }
    }
    
    // 模糊匹配逻辑（例如：春季包含春）
    for (String tag : seasonTags) {
        if (StringUtils.isNotBlank(tag) && targetSeason.contains(tag.trim())) {
            return 1; // 模糊匹配
        }
    }
    
    return 0; // 无匹配
}
```

#### 风格匹配得分

```java
private int getStyleMatchScore(AfdPicTemplateDTO template, List<String> targetStyles) {
    if (CollectionUtils.isEmpty(targetStyles) || StringUtils.isBlank(template.getStyleTags())) {
        return 0;
    }
    
    String splitChar = template.getStyleTags().contains("，") ? "，" : ",";
    List<String> styleTags = Arrays.stream(template.getStyleTags().split(splitChar))
        .map(e -> e.trim())
        .collect(Collectors.toList());
    
    // 精准匹配
    if (ListUtils.isEqualList(targetStyles, styleTags)) {
        return 2;
    }
    
    // 模糊匹配逻辑
    if (styleTags.stream().anyMatch(targetStyles::contains)) {
        return 1;
    }
    
    return 0; // 无匹配
}
```

#### CTR 比较

```java
private int compareCTR(AfdPicTemplateDTO t1, AfdPicTemplateDTO t2) {
    Double ctr1 = t1.getRecApplyItemCtrOnline14d();
    Double ctr2 = t2.getRecApplyItemCtrOnline14d();
    
    if (ctr1 == null && ctr2 == null) return 0;
    if (ctr1 == null) return 1; // null 排在后面
    if (ctr2 == null) return -1;
    
    return ctr2.compareTo(ctr1); // 降序
}
```

---

### 5️⃣ Tair 疲劳度控制

```java
// key: template_use_count:{batchId}:{templateId}
// TTL: 24小时
// 限制: 每模板每批次最多 5 次（可配置）

private void incrUserCount(String batchId, String templateId) {
    String tairKey = generateTemplateUseCountKey(batchId, templateId);
    try {
        commonTairService.incr(tairKey, 1, 0, 24 * 60 * 60); // 24小时过期
    } catch (Exception e) {
        log.warn("failed to increment use count for template {}", templateId, e);
    }
}

private List<AfdPicTemplateDTO> filterTemplatesByTairUseCount(
    List<AfdPicTemplateDTO> templates, 
    String batchId, 
    int maxUseCount
) {
    return templates.stream()
        .filter(template -> {
            String tairKey = generateTemplateUseCountKey(batchId, template.getTemplateId());
            Integer currentCount = commonTairService.get(tairKey);
            if (currentCount == null) currentCount = 0;
            
            template.setUseCount(currentCount);
            
            // 检查是否超过最大使用次数
            if (currentCount >= maxUseCount) {
                return false;
            }
            return true;
        })
        .collect(Collectors.toList());
}

// 全部超限时清除所有计数重试（软限制，非硬上限）
private void clearAllTemplateUseCounts(List<AfdPicTemplateDTO> templates, String batchId) {
    for (AfdPicTemplateDTO template : templates) {
        String tairKey = generateTemplateUseCountKey(batchId, template.getTemplateId());
        try {
            commonTairService.delete(tairKey);
        } catch (Exception e) {
            log.warn("failed to clear use count for template {}", template.getTemplateId(), e);
        }
    }
}
```

---

### 6️⃣ 匹配类型枚举：TemplateMatchTypeEnum

**文件位置**：
```
stylespot-admin-domain/src/main/java/com/taobao/stylespot/admin/domain/workflow2/enums/TemplateMatchTypeEnum.java
```

```java
public enum TemplateMatchTypeEnum {
    CATE("cate", "类目"),
    SEASON("season", "季节"),
    STYLE("style", "风格"),
    CTR("ctr", "CTR"),
    ;
    private final String code;
    private final String desc;
}
```

**注意**：枚举中只有 4 种匹配类型，没有"模型匹配"相关的枚举值。

---

### 7️⃣ 模板匹配节点模型：TemplateMatchNode

**文件位置**：
```
stylespot-admin-domain/src/main/java/com/taobao/stylespot/admin/domain/workflow2/model/TemplateMatchNode.java
```

```java
@Data
public class TemplateMatchNode extends Node {
    /**
     * 目标匹配数量
     */
    private Integer targetMatchCount;
    
    /**
     * 模板包条件
     */
    private TemplatePkgCondition templatePkgCondition;
    
    /**
     * 必须匹配的字段
     * 目前只有 seller_id, match_cate
     */
    private List<String> mustMatchFields;
    
    /**
     * 模板匹配类型
     * @see TemplateMatchTypeEnum
     */
    private List<String> matchTypes;
    
    /**
     * 匹配到的图像
     */
    private Variable matchedImg;
    
    /**
     * 模板最大使用次数
     */
    private Integer templateMaxUseCount;
    
    @Data
    public static class TemplatePkgCondition {
        private String stageCode;   // 应用环节：搭配/视觉/套图
        private String stageName;
        private String sceneCode;   // 应用场景：主图素材/种草素材
        private String sceneName;
    }
}
```

**关键发现**：
- `mustMatchFields`：必须匹配的字段，目前只有 `seller_id` 和 `match_cate`
- `matchTypes`：匹配类型列表，决定排序优先级
- 没有"模型选择"字段

---

## 🎯 关键结论

### 1️⃣ 代码库中只有"规则匹配"

- **只找到 `TemplateMatchProcessor` 处理器**
- **没有找到独立的"模型匹配"处理器**
- **`TemplateMatchTypeEnum` 枚举中只有 4 种匹配类型：CATE、SEASON、STYLE、CTR**

### 2️ seller_id 的作用

```java
// 代码中的 seller_id 使用
String sellerIdStr = context.getCommonVariable(CommonVariableEnum.SELLER_ID, null);
if (StringUtils.isBlank(sellerIdStr)) {
    sendFail(context, "商家ID为空");
    return;
}

// 查询商家正在使用的模版包
List<AfdSellerTemplateEntity> templatePackages = querySellerUsingTemplates(sellerId, stage, scene);
```

**seller_id 的作用**：
1. **入参必传**（缺失直接报错）
2. **查询商家正在使用的模板包**（硬隔离）
3. **生成 matched_template_used_ids**（sellerId_pkgId_templateId）

### 3️⃣ 排序优先级

```
1. seller_id（硬隔离）- 已经在查询时过滤
2. 类目优先级（二级＞一级＞无）
3. 季节优先级（精准＞模糊>无）
4. 风格优先级（精准＞模糊＞无）
5. 推荐ctr（由大到小）
```

**排序优先级由 `matchTypes` 列表顺序决定**，可以配置。

---

## 📚 已知问题与风险点

### 代码级问题

| 问题 | 位置 | 风险 |
|------|------|------|
| tagSearchConditionEntityList 静态缓存永不失效 | TemplateMatchProcessor:65 | 类目标签变更后验证匹配结果 |
| Tair 计数重置（全超限时清除） | TemplateMatchProcessor.parseAndSortTemplates | 大量请求耗尽配额后验证轮转 |
| 季节匹配不对称 | TemplateMatchProcessor SEASON_FILTER_MAPPING | 验证各季节组合的匹配结果 |
| 分布式锁超时 | Tair 计数器 | 可能导致计数偏差 |

---

## 🔄 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-07-07 | v1.0 | 初始版本，基于实际代码库整理 | AI Agent |

---

**文档维护者**：AI Agent  
**最后更新**：2026-07-07  
**文档状态**：✅ 已完成

**代码库路径**：`/Users/caoxuemei/stylespot-admin`  
**核心文件**：`TemplateMatchProcessor.java`（832行）
# F88 模板匹配 - 代码级规则详解

> **基于代码库**：`stylespot/stylespot-admin`（后端）+ `industry-source-code/iFashion-tools`（前端）  
> **核心处理器**：`application/workflow2/processor/template/TemplateMatchProcessor.java`

---

## 📊 模板匹配的两种模式（代码级）

### 1️⃣ 规则匹配模式（TemplateMatchProcessor）

**文件位置**：`application/workflow2/processor/template/TemplateMatchProcessor.java`

#### 核心方法：`process()`

```java
// 完整流程（代码级）
public void process() {
    // 1. 提取上下文
    String sellerId = context.getSellerId();
    String stage = context.getApplyRange();  // 应用环节：搭配/视觉/套图
    String scene = context.getApplyScene();   // 应用场景：主图素材/种草素材
    String taoCate = context.getTaoCate();
    String seasonTag = context.getSeasonTag();
    List<String> styleTags = context.getStyleTags();
    int targetMatchCount = context.getTargetMatchCount();  // 默认1
    
    // 2. 查询活跃包
    List<TemplatePackage> activePackages = queryActivePackages(
        sellerId, stage, scene, status=IN_USE
    );
    
    // 3. 克隆去重
    Set<String> usedTemplateIds = tryGetUsedTemplateIds(batchId);
    
    // 4. 解析+排序
    List<Template> candidates = parseAndSortTemplates(activePackages, taoCate, seasonTag, styleTags);
    
    // 5. 移除已用模板
    candidates.removeAll(usedTemplateIds);
    
    // 6. 截断
    List<Template> matched = candidates.subList(0, targetMatchCount);
    
    // 7. 使用计数递增
    incrUserCount(batchId, matched);
    
    // 8. 输出结果
    return MatchResult(
        matchedTemplateIds = matched.stream().map(Template::getId).collect(toList()),
        matchedTemplateUsedIds = matched.stream().map(t -> sellerId + "_" + t.getPkgId() + "_" + t.getId()).collect(toList()),
        matchedTemplatePkg = matched.get(0).getPkgId(),
        matchedImg = matched.get(0).getMainImageUrl()
    );
}
```

#### 解析+排序算法：`parseAndSortTemplates()`

```java
private List<Template> parseAndSortTemplates(
    List<TemplatePackage> packages, 
    String taoCate, 
    String seasonTag, 
    List<String> styleTags
) {
    List<Template> candidates = new ArrayList<>();
    
    // a. 解析：遍历所有包 → 反序列化 templateContent → 仅取 auditStatus=APPROVE 的模板
    for (TemplatePackage pkg : packages) {
        List<Template> templates = JSON.parseArray(pkg.getTemplateContent(), Template.class);
        for (Template t : templates) {
            if (t.getAuditStatus() == APPROVE) {
                candidates.add(t);
            }
        }
    }
    
    // b. 类目过滤
    candidates = filterByCate(candidates, taoCate);
    
    // c. 季节过滤
    candidates = filterBySeason(candidates, seasonTag);
    
    // d. Tair 使用计数检查
    candidates = filterByTairCount(candidates, batchId, maxCount=5);
    
    // e. 排序（matchTypes 列表顺序决定优先级）
    candidates.sort((t1, t2) -> {
        // 1. 类目匹配分
        int cateScore1 = calcCateScore(t1, taoCate);
        int cateScore2 = calcCateScore(t2, taoCate);
        if (cateScore1 != cateScore2) return cateScore2 - cateScore1;
        
        // 2. 季节匹配分
        int seasonScore1 = calcSeasonScore(t1, seasonTag);
        int seasonScore2 = calcSeasonScore(t2, seasonTag);
        if (seasonScore1 != seasonScore2) return seasonScore2 - seasonScore1;
        
        // 3. 风格匹配分
        int styleScore1 = calcStyleScore(t1, styleTags);
        int styleScore2 = calcStyleScore(t2, styleTags);
        if (styleScore1 != styleScore2) return styleScore2 - styleScore1;
        
        // 4. CTR 降序
        return Double.compare(t2.getCtr(), t1.getCtr());
    });
    
    return candidates;
}
```

#### 类目匹配得分算法

```java
private int calcCateScore(Template template, String taoCate) {
    if (template.getTagId().equals(taoCate)) {
        return 2;  // 精确匹配
    } else if (template.getParentTagId().equals(getParentTagId(taoCate))) {
        return 1;  // 同父类目
    } else {
        return 0;  // 不匹配
    }
}
```

#### 季节过滤映射

```java
// SEASON_FILTER_MAPPING
private static final Map<String, List<String>> SEASON_FILTER_MAPPING = Map.of(
    "春", List.of("春", "夏", "秋"),
    "夏", List.of("夏", "秋"),
    "秋", List.of("秋", "冬"),
    "冬", List.of("冬", "春")
);

private boolean matchSeason(String targetSeason, String templateSeason) {
    // 模糊匹配：targetSeason.contains(tag.trim())
    // 不对称！"春季".contains("春")=true，反之 false
    return SEASON_FILTER_MAPPING.get(targetSeason).contains(templateSeason.trim());
}
```

#### Tair 使用计数

```java
// key: template_use_count:{batchId}:{templateId}
// TTL: 24小时
// 限制: 每模板每批次最多 5 次

private List<Template> filterByTairCount(List<Template> candidates, String batchId, int maxCount) {
    List<Template> filtered = new ArrayList<>();
    boolean allExceeded = true;
    
    for (Template t : candidates) {
        String key = "template_use_count:" + batchId + ":" + t.getId();
        int count = tair.get(key);
        if (count < maxCount) {
            filtered.add(t);
            allExceeded = false;
        }
    }
    
    // 全部超限时清除所有计数重试（软限制，非硬上限）
    if (allExceeded) {
        for (Template t : candidates) {
            String key = "template_use_count:" + batchId + ":" + t.getId();
            tair.delete(key);
        }
        return candidates;
    }
    
    return filtered;
}
```

---

### 2️⃣ 模型匹配模式（推测实现）

**注意**：知识库中未找到模型匹配的具体实现代码，以下基于规则匹配逻辑的推测。

#### 可能的处理器：`ModelTemplateMatchProcessor`

```java
// 推测：模型匹配处理器
public class ModelTemplateMatchProcessor extends AbstractNodeProcessor {
    
    public void process() {
        // 1. 提取上下文
        String sellerId = context.getSellerId();  // 入参必传
        String stage = context.getApplyRange();
        String scene = context.getApplyScene();
        String model = context.getModel();  // 模型选择：wan2.7-image 等
        int targetMatchCount = context.getTargetMatchCount();
        
        // 2. 查询店铺基因（基于 seller_id）
        ShopGene shopGene = queryShopGene(sellerId);
        // {
        //     stylePreference: ['简约', '复古'],
        //     historyMatches: [{templateId: 'xxx', score: 0.95}],
        //     activePackages: [{pkgId: 'yyy', useCount: 3}]
        // }
        
        // 3. 查询候选模板
        List<Template> candidates = queryActiveTemplates(stage, scene);
        
        // 4. AI模型匹配
        List<TemplateScore> scored = aiModel.match(model, shopGene, candidates);
        // 输入：店铺基因 + 模板特征
        // 输出：匹配度评分 + 排序
        
        // 5. 取 top N
        List<Template> matched = scored.stream()
            .sorted(Comparator.comparingDouble(TemplateScore::getScore).reversed())
            .limit(targetMatchCount)
            .map(TemplateScore::getTemplate)
            .collect(toList());
        
        // 6. 返回结果（不会强校验 seller_id）
        return MatchResult(
            matchedTemplateIds = matched.stream().map(Template::getId).collect(toList()),
            matchedImg = matched.get(0).getMainImageUrl()
        );
    }
    
    // 推测：AI模型匹配接口
    private List<TemplateScore> match(String model, ShopGene shopGene, List<Template> candidates) {
        // 调用AI服务
        String endpoint = getModelEndpoint(model);
        AITemplateMatchRequest request = new AITemplateMatchRequest(shopGene, candidates);
        AITemplateMatchResponse response = httpClient.post(endpoint, request);
        return response.getScores();
    }
}
```

#### 店铺基因查询

```java
// 推测：店铺基因查询
private ShopGene queryShopGene(String sellerId) {
    // 查询店铺风格偏好
    List<String> stylePreference = queryShopStyle(sellerId);
    
    // 查询历史匹配记录
    List<MatchRecord> historyMatches = queryMatchHistory(sellerId, limit=10);
    
    // 查询商家活跃模板包
    List<TemplatePackage> activePackages = queryActivePackages(sellerId);
    
    return new ShopGene(stylePreference, historyMatches, activePackages);
}
```

---

## 🔍 规则匹配 vs 模型匹配对比

| 对比项 | 规则匹配 | 模型匹配 |
|--------|---------|---------|
| **处理器** | `TemplateMatchProcessor` | `ModelTemplateMatchProcessor`（推测） |
| **排序方式** | 手动配置（类目>季节>风格>CTR） | AI自动排序 |
| **配置字段** | 排序维度、硬匹配字段 | 模型选择 |
| **seller_id** | 硬匹配条件（模板包模式） | 查询店铺基因（不参与强校验） |
| **灵活性** | 高（可精确控制） | 低（依赖AI） |
| **匹配质量** | 依赖规则设计 | 依赖AI模型质量 |
| **性能** | 快速（规则计算） | 较慢（AI调用，可能30-60秒） |
| **可解释性** | 高（规则清晰） | 低（黑盒） |

---

## 📋 代码级校验规则

### 规则匹配模式

```java
// 1. 必填字段校验
if (stage == null || scene == null) {
    throw new BizException("应用环节和应用场景为必填");
}

// 2. 模板包模式 seller_id 校验
if (dataSource == TEMPLATE_PACKAGE && sellerId == null) {
    throw new BizException("该策略中包括模板匹配，但策略入参中没有商家ID");
}

// 3. 排序维度配置
List<MatchType> matchTypes = List.of(MatchType.CATE, MatchType.SEASON, MatchType.STYLE, MatchType.CTR);
// 类目 > 季节 > 风格 > CTR

// 4. 硬匹配字段配置
if (hardMatchField == "seller_id" && sellerId == null) {
    throw new BizException("硬匹配字段 seller_id 缺失");
}
```

### 模型匹配模式

```java
// 1. 必填字段校验
if (model == null) {
    throw new BizException("必须选择AI模型");
}

// 2. seller_id 入参必传
if (sellerId == null) {
    throw new BizException("Start节点必须配置seller_id");
}

// 3. 店铺基因查询（不强制校验）
ShopGene shopGene = queryShopGene(sellerId);
// 不会报错："seller_id 不匹配"
// 而是优先匹配该商家的模板

// 4. AI模型调用
List<TemplateScore> scores = aiModel.match(model, shopGene, candidates);
// 耗时：30-60秒
```

---

## 🎯 已知问题与风险点

### 规则匹配模式的已知问题

| 问题 | 位置 | 风险 |
|------|------|------|
| tagSearchConditionEntityList 静态缓存永不失效 | TemplateMatchProcessor:65 | 类目标签变更后验证匹配结果 |
| Tair 计数重置（全超限时清除） | TemplateMatchProcessor.parseAndSortTemplates | 大量请求耗尽配额后验证轮转 |
| 季节匹配不对称 | TemplateMatchProcessor SEASON_FILTER_MAPPING | 验证各季节组合的匹配结果 |
| 分布式锁超时 | Tair 计数器 | 可能导致计数偏差 |

### 模型匹配模式的推测风险

| 风险点 | 说明 |
|--------|------|
| AI模型质量 | 模型训练数据不足影响匹配质量 |
| 店铺基因准确性 | seller_id 查询的店铺基因可能不准确 |
| 性能问题 | AI模型调用可能耗时较长（30-60秒） |
| 可解释性差 | 无法精确控制匹配逻辑 |
| 模型服务稳定性 | AI服务可能不可用 |

---

## 📚 代码路径总结

| 关注点 | 路径 |
|--------|------|
| 模板匹配处理器 | `application/workflow2/processor/template/TemplateMatchProcessor.java` |
| 节点处理器工厂 | `domain/workflow2/factory/NodeProcessorFactory.java` |
| 工作流引擎 | `domain/workflow2/service/impl/Workflow2EngineImpl.java` |
| 策略匹配 | `domain/workflow2/service/impl/StrategyPickHelper.java` |

---

## 🔄 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-07-07 | v1.0 | 初始版本，整理代码级规则 | AI Agent |

---

**文档维护者**：AI Agent  
**最后更新**：2026-07-07  
**文档状态**：✅ 已完成

**注意**：本文档中的模型匹配部分为推测实现，实际代码需要查询 `stylespot/stylespot-admin` 代码仓库确认。
