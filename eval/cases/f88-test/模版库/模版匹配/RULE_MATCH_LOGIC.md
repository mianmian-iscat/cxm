# F88 模板匹配 - 规则匹配逻辑详解

> **基于实际代码库**：`/Users/caoxuemei/stylespot-admin`  
> **核心处理器**：`TemplateMatchProcessor.java`（832行）  
> **代码路径**：`stylespot-admin-application/src/main/java/com/taobao/stylespot/admin/application/workflow2/processor/template/TemplateMatchProcessor.java`

---

## 🎯 规则匹配完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│  1. 提取上下文变量                                            │
│     - seller_id (入参必传)                                   │
│     - stage (应用环节: 搭配/视觉/套图)                        │
│     - scene (应用场景: 主图素材/种草素材)                     │
│     - taoCate (类目标签)                                     │
│     - seasonTag (季节标签)                                   │
│     - styleTags (风格标签列表)                               │
│     - targetMatchCount (目标匹配数量, 默认1)                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 校验 seller_id                                          │
│     - 如果为空 → 发送失败消息："商家ID为空"                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 查询商家正在使用的模板包                                  │
│     - 条件: seller_id + stage + scene + status=IN_USE       │
│     - 如果为空 → 发送失败消息："未找到模板包"                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 克隆去重检查                                              │
│     - 检查当前流程是否从其他流程 clone 而来                   │
│     - 如果是，获取之前使用过的模板 ID 列表                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 解析模板内容                                              │
│     - 遍历所有模板包                                         │
│     - 反序列化 templateContent (JSON)                        │
│     - 仅取 auditStatus=APPROVE 的模板                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  6. 判断是否需要跳过过滤                                      │
│     - mustMatchFields 不包含 "match_cate" → 跳过类目过滤    │
│     - mustMatchFields 不包含 "match_season" → 跳过季节过滤  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  7. 类目过滤                                                  │
│     - 根据 taoCate 过滤模板                                  │
│     - 匹配逻辑: tagId 精确匹配 / parentTagId 相同           │
│     - 如果过滤后数量不足 → 提前返回                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  8. 季节过滤                                                  │
│     - 根据 seasonTag 过滤模板                                │
│     - 匹配逻辑: SEASON_FILTER_MAPPING 映射                  │
│     - 如果过滤后数量不足 → 提前返回                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  9. Tair 疲劳度检查                                           │
│     - 检查每个模板的使用次数 (Tair 计数器)                   │
│     - 过滤掉使用次数 >= maxUseCount 的模板                  │
│     - 如果全部超限 → 清除所有计数，重新使用全部模板          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  10. 排序                                                     │
│      - 按 matchTypes 列表顺序决定优先级                      │
│      - 优先级: 类目 > 季节 > 风格 > CTR                     │
│      - 每个维度内部有得分计算逻辑                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  11. 克隆去重                                                 │
│      - 移除之前使用过的模板                                   │
│      - 如果移除后数量不足 → 保留已用模板                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  12. 截断                                                     │
│      - 取 top targetMatchCount 个模板                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  13. 使用计数递增                                             │
│      - Tair 计数器 +1 (TTL=24小时)                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  14. 输出结果                                                 │
│      - matched_template_ids: 匹配的模板 ID 列表              │
│      - matched_template_used_ids: sellerId_pkgId_templateId  │
│      - matched_template_pkg: 模板包 ID                       │
│      - matchedImg: 匹配的模板图片 URL 列表                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 核心方法详解

### 1️⃣ `process()` - 主流程方法

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
    String batchId = context.getWorkflowBatchEntity().getBatchId();
    Long sellerId = Long.valueOf(sellerIdStr);
    String stage = templateMatchNode.getTemplatePkgCondition().getStageCode();  // 应用环节
    String scene = templateMatchNode.getTemplatePkgCondition().getSceneCode();  // 应用场景
    String taoCate = context.getCommonVariable(CommonVariableEnum.TAO_CATE, "");
    String seasonTag = context.getCommonVariable(CommonVariableEnum.SEASON_TAG, "");
    Integer targetMatchCount = Optional.ofNullable(templateMatchNode.getTargetMatchCount()).orElse(1);
    List<String> styleTags = ObjectUtil.getStrList(context.getCommonVariable(CommonVariableEnum.STYLE_TAG));
    
    // 4. 添加输入数据（用于日志和调试）
    Map<String, Object> inputData = new HashMap<>();
    inputData.put("stage", stage);
    inputData.put("scene", scene);
    inputData.put("seller_id", sellerId);
    inputData.put("tao_cate", taoCate);
    inputData.put("season_tag", seasonTag);
    inputData.put("style_tag", styleTags);
    workflowRecordDomainService.addInputData(context.getWorkflowRecordLogEntity().getId(), inputData);
    
    // 5. 查询商家正在使用的模版包
    List<AfdSellerTemplateEntity> templatePackages = querySellerUsingTemplates(sellerId, stage, scene);
    if (CollectionUtils.isEmpty(templatePackages)) {
        sendFail(context, String.format("未找到模板包, seller_id = %s, stage = %s, scene = %s", sellerId, stage, scene));
        return;
    }
    
    // 6. 克隆去重检查
    List<String> usedTemplateIds = tryGetUsedTemplateIds(context);
    
    // 7. 解析模版内容并排序
    List<AfdPicTemplateDTO> sortedTemplates = parseAndSortTemplates(
        templatePackages, 
        taoCate, 
        seasonTag, 
        styleTags, 
        batchId,
        templateMatchNode, 
        usedTemplateIds,
        Optional.ofNullable(context.getWorkflowInstanceEntity()).map(WorkflowInstanceEntity::getStrategyId).orElse(null)
    );
    
    // 8. 校验模板数量
    if (CollectionUtils.isEmpty(sortedTemplates) || sortedTemplates.size() < targetMatchCount) {
        String msg = CollectionUtils.isEmpty(sortedTemplates) ? "未找到模板" : "模板数量不够";
        sendFail(context, String.format(
            msg + ", seller_id = %s, tao_cate = %s, season_tag = %s, style_tag = %s, targetMatchCount = %s, result = %s",
            sellerId, taoCate, seasonTag, JSON.toJSONString(styleTags), targetMatchCount, JSON.toJSONString(sortedTemplates)
        ));
        return;
    }
    
    // 9. 使用计数递增（Tair）
    sortedTemplates.forEach(e -> incrUserCount(batchId, e.getTemplateId()));
    
    // 10. 输出结果
    Map<String, Object> outputData = new HashMap<>();
    List<String> picUrls = sortedTemplates.stream().map(e ->
        StringUtils.isBlank(e.getSrcTfs()) ? e.getPicUrl() : FileConstants.PICT_URL_PREFIX + e.getSrcTfs()
    ).collect(Collectors.toList());
    
    outputData.put(templateMatchNode.getMatchedImg().getCode(), picUrls);
    outputData.put("matched_template_ids", sortedTemplates.stream()
        .map(AfdPicTemplateDTO::getTemplateId).collect(Collectors.toList()));
    outputData.put("matched_template_used_ids", sortedTemplates.stream().map(e -> {
        return TemplatePackageFun.getTemplateUsedId(e.getTemplateId(), templatePackages.get(0).getId(), sellerId);
    }).collect(Collectors.toList()));
    outputData.put("matched_template_pkg", templatePackages.get(0).getId());
    
    // 11. 发送成功消息
    WorkflowRecordFinishMessage finishMessage = new WorkflowRecordFinishMessage();
    finishMessage.setWorkflowRecordId(context.getWorkflowRecordLogEntity().getId());
    finishMessage.setWorkflowInstanceId(context.getWorkflowRecordLogEntity().getWorkflowInstanceId());
    finishMessage.setNodeUId(context.getWorkflowRecordLogEntity().getNodeId());
    finishMessage.setNodeType(context.getWorkflowRecordLogEntity().getNodeType());
    finishMessage.setBatchId(context.getWorkflowRecordLogEntity().getBatchId());
    finishMessage.setStatus(WorkflowStatusEnum.SUCCESS.getCode());
    finishMessage.setOutputData(outputData);
    workflowMessageSender.sendWorkflowRecordFinishMsg(finishMessage);
}
```

---

### 2️⃣ `parseAndSortTemplates()` - 解析+排序核心算法

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
        if (templatePackage.getTemplateContent() == null) {
            continue;
        }
        
        // templateContent 是 Map<String, String>，key 是 templateId，value 是 JSON 字符串
        for (Map.Entry<String, String> entry : templatePackage.getTemplateContent().entrySet()) {
            try {
                List<AfdPicTemplateDTO> templates = JSON.parseArray(entry.getValue(), AfdPicTemplateDTO.class);
                if (CollectionUtils.isNotEmpty(templates)) {
                    templates.forEach(e -> e.setSellerId(templatePackage.getSellerId()));
                    // 仅取 auditStatus=APPROVE 的模板
                    allTemplates.addAll(templates.stream()
                        .filter(x -> TemplatePackageStatusEnum.APPROVE.getCode().toString().equals(x.getAuditStatus()))
                        .collect(Collectors.toList()));
                }
            } catch (Exception e) {
                log.warn("parse template failed, templateId={}", entry.getKey(), e);
            }
        }
    }
    
    if (CollectionUtils.isEmpty(allTemplates)) {
        return Collections.emptyList();
    }
    
    // 2. 判断是否需要跳过过滤
    List<String> mustMatchFields = templateMatchNode.getMustMatchFields();
    boolean skipCategoryFilter = CollectionUtils.isNotEmpty(mustMatchFields) && !mustMatchFields.contains("match_cate");
    boolean skipSeasonFilter = CollectionUtils.isNotEmpty(mustMatchFields) && !mustMatchFields.contains("match_season");
    
    List<AfdPicTemplateDTO> filteredTemplates = allTemplates;
    Integer targetMatchCount = Optional.ofNullable(templateMatchNode.getTargetMatchCount()).orElse(1);
    
    // 3. 类目过滤
    if (!skipCategoryFilter && StringUtils.isNotBlank(taoCate)) {
        List<TagSearchConditionEntity> categoryTagList = getCategoryTagList();
        TagSearchConditionEntity targetCateTag = findCategoryTagByName(categoryTagList, taoCate);
        final String targetParentTagId = targetCateTag != null ? targetCateTag.getParentTagId() : null;
        
        filteredTemplates = filteredTemplates.stream()
            .filter(e -> {
                TagSearchConditionEntity templateCateTag = findCategoryTag(categoryTagList, e.getCateId(), e.getCategoryName());
                if (templateCateTag == null) return false;
                
                if (targetCateTag == null) return true;
                
                boolean cateMatch = templateCateTag.getTagName().equals(taoCate)
                    || templateCateTag.getTagId().equals(targetCateTag.getTagId());
                boolean parentMatch = StringUtils.isNotBlank(targetParentTagId)
                    && targetParentTagId.equals(templateCateTag.getParentTagId());
                
                return cateMatch || parentMatch;
            })
            .collect(Collectors.toList());
        
        if (CollectionUtils.isEmpty(filteredTemplates) || filteredTemplates.size() < targetMatchCount) {
            return filteredTemplates;
        }
    }
    
    // 4. 季节过滤
    if (!skipSeasonFilter && StringUtils.isNotBlank(seasonTag)) {
        Set<String> allowedSeasons = getAllowedSeasonsByTarget(seasonTag);
        if (CollectionUtils.isNotEmpty(allowedSeasons)) {
            filteredTemplates = filteredTemplates.stream()
                .filter(e -> {
                    if (StringUtils.isBlank(e.getSeasonTags())) return false;
                    String[] templateSeasons = e.getSeasonTags().split(",");
                    return Arrays.stream(templateSeasons)
                        .map(String::trim)
                        .filter(StringUtils::isNotBlank)
                        .anyMatch(allowedSeasons::contains);
                })
                .collect(Collectors.toList());
            
            if (CollectionUtils.isEmpty(filteredTemplates) || filteredTemplates.size() < targetMatchCount) {
                return filteredTemplates;
            }
        }
    }
    
    // 5. Tair 疲劳度检查
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
    
    // 7. 克隆去重
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
    
    // 8. 截断
    if (sortedTemplates.size() > targetMatchCount) {
        return sortedTemplates.subList(0, targetMatchCount);
    }
    
    return sortedTemplates;
}
```

---

### 3️⃣ `sortTemplates()` - 排序算法

```java
/**
 * 对模版进行排序
 * 排序优先级：
 * 1. seller_id（硬隔离）- 已经在查询时过滤
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
            // 按 matchTypes 列表顺序决定优先级
            for (String matchType : matchTypes) {
                if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.CATE.getCode())) {
                    // 类目优先级（二级＞一级＞无）
                    int cateCompare = compareCategory(t1, t2, targetCate);
                    if (cateCompare != 0) return cateCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.SEASON.getCode())) {
                    // 季节优先级（精准＞模糊>无）
                    int seasonCompare = compareSeason(t1, t2, targetSeason);
                    if (seasonCompare != 0) return seasonCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.STYLE.getCode())) {
                    // 风格优先级（精准＞模糊＞无）
                    int styleCompare = compareStyle(t1, t2, targetStyles);
                    if (styleCompare != 0) return styleCompare;
                } else if (matchType.equalsIgnoreCase(TemplateMatchTypeEnum.CTR.getCode())) {
                    // 推荐ctr（由大到小）
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
    
    List<TagSearchConditionEntity> categoryTagList = getCategoryTagList();
    if (CollectionUtils.isEmpty(categoryTagList)) {
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

## 🎯 匹配维度详解

### 1️⃣ 类目匹配（CATE）

**匹配逻辑**：
- **精准匹配（2分）**：模板的 tagId 与目标类目的 tagId 相同
- **一级匹配（1分）**：模板的 parentTagId 与目标类目的 parentTagId 相同
- **无匹配（0分）**：其他情况

**示例**：
```
目标类目：连衣裙（tagId=123, parentTagId=10）
模板A：连衣裙（tagId=123）→ 精准匹配（2分）
模板B：半身裙（tagId=124, parentTagId=10）→ 一级匹配（1分）
模板C：T恤（tagId=200, parentTagId=20）→ 无匹配（0分）
```

---

### 2️⃣ 季节匹配（SEASON）

**匹配逻辑**：
- **精准匹配（2分）**：模板的季节标签与目标季节完全相同
- **模糊匹配（1分）**：目标季节包含模板的季节标签（例如："春季"包含"春"）
- **无匹配（0分）**：其他情况

**季节映射**（SEASON_FILTER_MAPPING）：
```java
Map<String, Set<String>> seasonMapping = Map.of(
    "春", Set.of("春", "夏", "秋"),
    "夏", Set.of("春", "夏"),
    "秋", Set.of("春", "秋", "冬"),
    "冬", Set.of("秋", "冬")
);
```

**示例**：
```
目标季节：春
模板A：春 → 精准匹配（2分）
模板B：春季 → 模糊匹配（1分，"春"包含"春"）
模板C：夏 → 无匹配（0分）
```

---

### 3️⃣ 风格匹配（STYLE）

**匹配逻辑**：
- **精准匹配（2分）**：模板的风格标签列表与目标风格列表完全相同
- **模糊匹配（1分）**：模板的风格标签与目标风格有交集
- **无匹配（0分）**：其他情况

**示例**：
```
目标风格：["简约", "复古"]
模板A：["简约", "复古"] → 精准匹配（2分）
模板B：["简约", "休闲"] → 模糊匹配（1分，有交集"简约"）
模板C：["休闲", "运动"] → 无匹配（0分）
```

---

### 4️⃣ CTR 比较

**匹配逻辑**：
- 按 `recApplyItemCtrOnline14d`（近14天推荐CTR）降序排列
- null 值排在最后

**示例**：
```
模板A：CTR=0.15
模板B：CTR=0.12
模板C：CTR=null
排序结果：A > B > C
```

---

## 🔄 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-07-07 | v1.0 | 初始版本，基于实际代码库整理规则匹配逻辑 | AI Agent |

---

**文档维护者**：AI Agent  
**最后更新**：2026-07-07  
**文档状态**：✅ 已完成

**代码库路径**：`/Users/caoxuemei/stylespot-admin`  
**核心文件**：`TemplateMatchProcessor.java`（832行）
