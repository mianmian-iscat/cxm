<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/features/05-LLM生文.md -->
<!-- synced-at: 2026-07-11T03:52:35.007081 -->
<!-- skill: F88测试知识库 -->

---
id: features/05-LLM生文
title: F88 LLM 生文（字符数校验+重试+降级）
tags: [LLM, 生文, 字符校验, 降级]
owner: 目民
version: 1.0.0
created: 2026-06-29
updated: 2026-06-29
source_sessions: []
promotion_count: 0
---

# F88 LLM 生文（字符数校验+重试+降级）

## LLM 文本处理器（`LLMTextProcessor`）

| NodeType | 处理器 | 处理类型 | 核心逻辑 |
|----------|--------|----------|----------|
| `llm_text` | `LLMTextProcessor` | AI 生成 | LLM 文本生成，NanoBanana 任务，支持 JSON 字段提取。回调类型 `ALGO_NANO_BANANA` |

- **支持重试**：✅
- **支持重产**：—

## 生成类处理器通用模式（`GenAbstractProcessor`）

```
1. parseInput() → 提取 modelType / systemPrompt / inputImages
2. buildGenJob() → 创建 AfdJobEntity（type=LLM_GEN）
3. checkDataProcessed() → 幂等检查（防重复提交）
4. TaskService.submitTasks() → 提交到任务队列
5. @TaskCallback(taskType + taskStatus + sceneCode) → 异步回调
6. 回调内：更新 job 状态 → 创建素材 → 发送 WorkflowRecordFinishMessage
```

**QA 风险点**：
- 回调丢失会导致 record 卡在 HANDLING（已知问题：AfdJob `job_status` 回调不可靠，88% 的 job 卡在 INIT 未更新）
- `checkDataProcessed()` 幂等检查可能误判导致跳过合法任务

## LLM/AI 集成

### 模型配置

通过 Diamond 动态配置（`GeminiModelConfig`）：模型列表、IdeaLab AK/URL、流式 URL、每模型 QPS、按租户 AK 映射。

### API 调用链路

```
Processor → NanoBananaTaskBuilder.buildTask() → TaskService.submitTasks()
  → NanoBananaTaskHandler → GeminiApiFacade.callGemini() / callGeminiStream()
  → IdeaLab 代理 → Vertex API (Gemini) / OpenAI 兼容接口 (Qwen)
```

### 模型路由

| 模型 | API 路径 | 视频支持 | 备注 |
|------|----------|----------|------|
| Gemini 系列 | NanoBanana(Vertex API)，fileData 格式 | gemini-3-flash-preview、gemini-3.5-flash 支持 | 走 IdeaLab 代理 |
| Qwen 系列 | OpenAI 兼容接口，video_url 类型 | 支持 | `QwenLLMFacadeImpl` |
| Claude 系列 | — | **不支持视频输入** | — |

### 任务场景（TaskSceneEnum）

| 场景 | 说明 |
|------|------|
| `STRATEGY_PLATFORM` | 策略平台通用 |
| `LLM_TEXT` / `LLM_TEXT_TRY_RUN` | LLM 文本生成 / 试运行 |
| `GEN_IMG` / `GEN_IMG_TRY_RUN` | 图片生成 / 试运行 |
| `GEN_IMG_MAP` / `GEN_IMG_MAP_TRY_RUN` | MAP 图片生成 / 试运行 |
| `GEN_VIDEO` | 视频生成 |

## 其他文本/标注类处理器

| NodeType | 处理器 | 处理类型 | 核心逻辑 |
|----------|--------|----------|----------|
| `caption` | `CaptionProcessor` | 文本生成 | Caption 文案生成 |
| `design_agent_prompt` | `DesignAgentPromptProcessor` | 自研推理 | 改款 prompt 推理（自研模型） |
| `season_tag` | `SeasonTag2Processor` | 标签 | 季节标打标 |
| `industry_tag` | `IndustryTagProcessor` | 标签 | 产业标打标 |
| `sub_category` | `SubCategoryProcessor` | 分类 | 副类目分类 |
| `suggest_price` | `SuggestPriceProcessor` | 定价 | 建议定价 |
| `match_score` | `MatchingScoreProcessor` | 评分 | 匹配度打分 |
| `style_allocation` | `StyleAllocationProcessor` | 分配 | 款式分配 |

**辅助方法**：`isLlm()` (llm_text/design_agent_prompt)、`isGenImg()` (gen_img/map_gen_img/fabric_tryon)、`haveTemplateInput()` (gen_img/map_gen_img/fabric_tryon)

## 失败排查速查

| 错误特征 | 类别 | 处置 |
|----------|------|------|
| `429` / `RESOURCE_EXHAUSTED` | Quota 耗尽 | 手动重试（`workflow_fail_retry`） |
| `500` / `Internal error` | 模型内部错误 | 少量可接受，大量需上报 |
| `Error 404` / `was not found` | API 路径错误 | 检查 modelType 到 API 路径映射 |
| `upstream request failed` | 上游服务不可达 | 检查服务可用性 |
| `算法返回结果为空` | 算法层返回空 | 检查输入数据 |
| `unexpected end of stream` | 流截断 | 重试 |
| `CutEdgeExceedRange` | 数据质量问题 | 人工排查 |
| `Cannot fetch content` | URL 不可访问 | 检查图片/视频 URL 有效性 |

## LLM 生文相关代码路径

| 关注点 | 路径 |
|--------|------|
| Gemini API 集成 | `infrastructure/facade/nano/GeminiApiFacadeIdeaLabImpl.java` |
| Qwen LLM 集成 | `infrastructure/facade/llm/QwenLLMFacadeImpl.java` |
| 节点处理器工厂 | `domain/workflow2/factory/NodeProcessorFactory.java` |
