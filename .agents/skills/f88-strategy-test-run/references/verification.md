# 造数结果验证（DB 三层结构 + UI）

> 脚本触发试运行后，用本文档的 SQL 走 dms-alibaba（组 stylespot）验证；UI 验证走浏览器。

## UI 验证（必须先做）

1. 导航到 `https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center`
2. 切换到「审核任务」tab，搜索批次号（如 `BT_7544`）
3. **预期**：列表出现一条记录，状态"待开始: 0/N"

**主任务 vs 子任务**：
- **主任务**（job_type=4）：批提交后即创建，在个人任务中心可见
- **子任务/审核条目**：需等 ScheduleX 定时器分配后才填充。分配未执行时点进详情显示 "No data"——不是任务不存在

## 1. 批次状态（g_workflow_batch）

```sql
SELECT batch_id, status, relation_id, gmt_create, gmt_modified
FROM g_workflow_batch WHERE batch_id = 'BT_XXXX';
```

## 2. workflow 记录（workflow_record_log）

```sql
SELECT id, batch_id, node_type, status, gmt_create, gmt_modified,
       LEFT(extra_info, 200) as extra
FROM workflow_record_log WHERE batch_id = 'BT_XXXX';
```

- STREAM：记录立即出现，status=HANDLING
- BATCH：先 status=TO_SUBMIT，批提交后变 HANDLING

## 3. 审核任务（g_afd_review_job，三层结构）

```sql
-- 主任务 (job_type=0)
SELECT id, name, job_status, batch_id FROM g_afd_review_job
WHERE batch_id='BT_XXXX' AND job_type=0 AND deleted=0;

-- 子任务组 (job_type=4)
SELECT id, name, job_status, parent_job_id FROM g_afd_review_job
WHERE parent_job_id={主任务id} AND job_type=4 AND deleted=0;

-- 审核条目 (job_type=1)，每行 xlsx 数据对应一条
SELECT id, job_status, LEFT(info, 300) FROM g_afd_review_job
WHERE parent_job_id={主任务id} AND job_type=1 AND deleted=0;
```

**任务命名规则**：`{策略名}-{批次号}-{节点名}-{日期}`（流式带日期后缀，块式不带）

## 4. 审核条目 info 字段验证

```json
{
  "coverImageAuditContent": {
    "imgUrlList": [{"afdMid": "AFD_RT...", "url": "https://..."}],
    "taoCate": "tao_cate-1"
  },
  "createMode": "STREAM",     // 或 "BATCH"
  "questionType": 4,          // 4=首图, 2=套图, 3=视频, 5=模板
  "parentTaskId": 1507025
}
```

**关键验证点**（方式二手动创建）：确认 `dataFileUrl` 字段非 null，UI 能正常显示图片。
