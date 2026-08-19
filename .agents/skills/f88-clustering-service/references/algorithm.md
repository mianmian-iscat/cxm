# 聚类算法与签名库

## 算法流程

1. **文本预处理**：clean_error_msg() 去除 URL/时间戳/ID/UUID → jieba 分词 → 停用词过滤
2. **TF-IDF 向量化**：max_features=500，中文语料
3. **顶层聚类**：KMeans(n_clusters=5)，silhouette_score 评估
4. **标签生成**：make_label() 从 TF-IDF 特征词 + 正则模式匹配生成可读标签
5. **子聚类**：对样本数 >= sub_min_size(10) 的顶层簇，自动搜索最优 k（2-5）做二级聚类

## make_label() 正则模式库

| 模式类别 | 正则表达式 | 标签 | 对应问题 |
|---------|-----------|------|---------|
| API 错误 | `Error\s*404\|was not found` | Gemini API 404 | API 路径错误 |
| 上游故障 | `upstream request failed` | 上游服务不可达 | 上游服务异常 |
| 算法空结果 | `算法返回结果为空` | 算法返回空 | 算法层异常 |
| Quota 耗尽 | `RESOURCE_EXHAUSTED\|429` | RESOURCE_EXHAUSTED 429 | 配额超限 |
| 模型内部错误 | `Internal error encountered\|500` | 模型内部错误 500 | 模型服务异常 |
| 流截断 | `unexpected end of stream` | 流截断 | 网络/模型输出截断 |
| URL 不可访问 | `Cannot fetch content` | URL 不可访问 | 素材 URL 失效 |
| 模型下线 | `model was deprecated\|model not found\|Claude` | 模型已下线 | 策略配置引用废弃模型 |
| CDN 过期 | `AccessDenied\|403\|SignatureDoesNotMatch\|URL expired` | CDN URL 签名过期 | 签名 URL 超期 |
| TPP 超时 | `TPP\|callback timeout\|排队超时\|queue timeout` | TPP 排队超时 | 生图服务回调丢失 |
| JSON 解析 | `JSON parse\|Unexpected character\|Unexpected token` | JSON 解析失败 | LLM 输出含非法字符 |
| 任务丢失 | `task not found\|downstream missing` | 下游任务丢失 | 上游部分失败 |
| 跨域隔离 | `SharedArrayBuffer\|Cross-Origin Isolated\|COOP\|COEP` | SharedArrayBuffer/COOP 缺失 | 预发环境缺少跨域隔离头（BT_6149） |
| 追踪断裂 | `subJobId\|sub_job_id\|trace lost` | subJobId 未传递 | 素材操作链路追踪断裂（BT_5976） |
| 跨表不一致 | `stale URL\|旧 URL\|review_job.info 未更新\|replaceImage.*旧` | replaceImage 跨表不一致 | 素材更新未回写审核快照（BT_6148） |
| 模式差异 | `BATCH.*STREAM\|execMode\|mode mismatch` | BATCH/STREAM 模式差异 | 执行模式行为不一致 |
| 审核分配校验 | `构建子任务失败\|期望分配数量\|与实际分配数量` | 审核任务分配校验不一致 | 整除/取余校验差 1（BT_7495） |
| 审核回调缺失 | `doCompleteMainTaskIfAllPersonalDone\|审核完成不流转` | 审核回调三条件缺失 | 三条件缺一不流转（BT_7485） |
| LLM JSON 解析 | `FASTJSON\|error, offset` | LLM JSON 解析异常 | 模型输出格式漂移（BT_7417） |
| 淘积木转存失败 | `转存失败\|图片下载失败, responseCode=403\|taojimu.oss` | 淘积木OSS转存失败 | 品牌故事图临时签名 URL 未走转存永久 CDN（2026-08-12 线上 317 条） |

## 治理签名打标（v1.2）

来源《生产链路稳定性提升方案》的 7 类高频错误签名，命中即返回「治理-N」标签：

| 治理标签 | 签名特征 | 基线次数 | 治理状态 |
|---------|---------|------|------|
| 治理-1: ideaLAB额度耗尽 | F88_4/F88_5 + 额度已消耗完 | 18870 | 已完成 |
| 治理-2: 模型不可用 | was not found or your project does not have access | 4272 | 已完成 |
| 治理-3: 模型资源限流 | RESOURCE_EXHAUSTED | 2829 | 已完成 |
| 治理-4: 平台限流 | PL-002 / video generation任务已达到200 | 2653+1004 | 已完成 |
| 治理-5: 模板URL失效 | URL_ERROR-ERROR_NOT_FOUND | 2410 | 规划中 |
| 算法返回结果为空 | 沿用既有模式 | 1279 | 已完成 |

使用方式：报告中「治理-N」标签的簇样本数即该类错误的现存规模，与基线对比判断治理是否收敛。

> 注意：修改的是 references/app.py 源文件，已部署的服务实例需重新上传并重启。

## 三孤岛 gapType 打标（v2.1）

> 同步 f88-failure-analysis v0.6.2 三孤岛分类模型（对标《AI 应用评测方法与实践》）。
> 聚类报告与 failure-analysis Stage 3 归因报告使用相同 gapType 口径，保证两边统计可互相对标。

每个顶层簇打标一个 gapType，报告输出「三孤岛分布 (gapType)」段落：

| gapType | 鸿沟 | 含义 | 签名映射 |
|---------|------|------|---------|
| `data` | 理解鸿沟 | 数据源问题 | 治理-5 模板URL失效、淘积木OSS转存失败、URL 过期/403/资源缺失类 |
| `prompt` | 具象鸿沟 | 指令/配置问题 | 治理-2 模型不可用、模型下线、策略配置错误、模板匹配逻辑类 |
| `engineering` | 泛化鸿沟 | 工程健壮性问题 | 治理-1/3/4 额度与限流、BT_6149/5976/6148/7495/7485/7417、BATCH/STREAM 差异、超时/解析失败类 |

打标规则（实现于统一脚本 `GAP_TYPE_MAP` + `infer_gap_type()`）：

1. 簇标签命中签名映射表 → 直接取映射值
2. 未命中 → 按关键词规则推断（data/prompt/engineering 各自关键词计分，取最高）
3. 均无命中 → 兜底 `engineering`
4. 统计时只计顶层簇（子簇不重复计数），占比最高的鸿沟写入优化建议

## execMode 交叉分析维度

除 errorMsg 文本聚类外，按 execMode（BATCH/STREAM）做交叉分析：

```python
def cross_analyze_exec_mode(rows):
    """对聚类结果按 execMode 做交叉分析"""
    mode_counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        cluster = row['cluster_label']
        mode = row.get('exec_mode', 'UNKNOWN')
        mode_counts[cluster][mode] += 1
    for label, modes in mode_counts.items():
        batch_n = modes.get('BATCH', 0)
        stream_n = modes.get('STREAM', 0)
        if batch_n > 0 and stream_n > 0:
            ratio = batch_n / (batch_n + stream_n)
            if ratio > 0.8 or ratio < 0.2:
                print(f"[WARN] {label}: BATCH={batch_n} STREAM={stream_n} — 模式分布严重偏斜")
```

**分析要点**：
- 某类错误只出现在 BATCH → 可能是 review_job.info 快照问题（BT_6148）
- 某类错误只出现在 STREAM → 可能是实时读取 g_afd_material 的竞态问题
- 两种模式都有但比例偏斜 → 可能是模式相关的配置差异

## g_afd_material 辅助数据源

聚类分析时可选关联 `g_afd_material` 表，补充素材操作维度信息：

```sql
SELECT
  wrl.batch_id, wrl.node_type,
  JSON_EXTRACT(wrl.extra_info, '$.errorMsg') AS error_msg,
  m.operation_type, m.material_type,
  CASE WHEN m.sub_job_id IS NOT NULL AND m.sub_job_id != '' THEN 'HAS_SUBJOBID' ELSE 'NO_SUBJOBID' END AS subjobid_status,
  m.gmt_modified AS material_last_modified
FROM workflow_record_log wrl
LEFT JOIN g_afd_material m ON wrl.workflow_instance_id = m.workflow_instance_id
WHERE wrl.batch_id = '{batch_id}' AND wrl.status = 'FAIL' AND wrl.id > 4000000;
```

**用途**：
- 对"跨表不一致"类错误，补充 material 的操作类型和修改时间
- 对"追踪断裂"类错误，统计 subJobId 传递率
- 为聚类报告增加"素材操作维度"的分析图表
