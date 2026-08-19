# 输出格式与交互样例

## 输出格式模板

```markdown
## 日志分析结果

### 查询概况
- **排查场景**: {场景名称}
- **输入参数**: {batch_id / item_id / seller_id}
- **数据源**: DMS(stylespot) + {SLS/ffprobe/环境检查}
- **查询时间**: {timestamp}

### 数据快照
| 指标 | 值 |
|---|---|
| 总记录数 | {count} |
| 成功数 | {success_count} |
| 失败数 | {fail_count} |
| 处理中 | {handling_count} |
| 成功率 | {success_rate}% |

### 错误分布（如有失败）
| 错误类型 | 数量 | 占比 |
|---|---|---|
| {error_type_1} | {cnt} | {pct}% |
| {error_type_2} | {cnt} | {pct}% |

### 根因分析
{基于数据证据的根因推理过程}

### 证据链
{关键 SQL 查询结果摘录，作为结论的支撑证据}

### 建议
{针对根因的处理建议，如：重试、配置修改、数据修复等}
```

---

## 交互样例

### 样例 1：批次失败排查

**用户**：BT_6200 跑挂了，帮我看看什么原因

**执行过程**：

1. 识别场景：批次失败分析 → 路由到 T1 模板
2. 执行 T1-1 查全貌：
```bash
dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql \
  "SELECT node_type, status, COUNT(*) AS cnt FROM workflow_record_log WHERE batch_id = 'BT_6200' AND id > 4000000 AND env = 'staging' GROUP BY node_type, status ORDER BY node_type, status"
```
3. 发现 gen_img 节点有 35 条 FAIL → 执行 T1-2 错误分类
4. 发现 28 条是 429 Quota → 执行 T1-3 检查 TPP 任务状态
5. 综合结论：模型调用超配额导致批量失败，建议降低并发或等待配额恢复

### 样例 2：审核卡住排查

**用户**：商品 726384910285 审核一直卡着没动

**执行过程**：

1. 识别场景：审核节点排查 → 路由到 T2 + T3 模板
2. 先查商品关联批次（T3-1）→ 找到 BT_6180
3. 查审核任务层级（T2-1）→ 发现主任务 job_status=0（待处理）
4. 查审核回调状态（T2-3）→ 发现 approve 节点 status=HANDLING
5. 查快照一致性（T2-2）→ 发现 mismatch_cnt > 0（replaceImage 副作用）
6. 综合结论：审核任务创建后素材被 replaceImage 替换，但 info 快照未更新，导致审核回调丢失

### 样例 3：超出职责范围

**用户**：帮我生成一份审核节点的测试用例

**回复**：我的职责定位是 F88 全链路日志分析与问题排查。生成测试用例请使用 `hfz-test-workflow` 编排器，它会按八步流程帮你完成从需求分析到用例生成的全流程。
