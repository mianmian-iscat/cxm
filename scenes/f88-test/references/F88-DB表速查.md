# F88 素材生产平台 - DB表速查

> 来源：知识库 + CDP抓包 + HSF接口逆推 | 数据库：F88业务库
>
> ⚠️ 部分字段名来自接口返回 / 前端代码逆推，可能与实际DDL略有差异

---

## 1. material（素材主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 素材ID |
| seller_id | BIGINT | 商家ID |
| item_id | BIGINT | 商品ID |
| material_type | VARCHAR | 素材类型：主图/详情页/白底图/场景图/标题/描述 |
| url | VARCHAR | 当前生效图片URL（确认编辑后由localAdjustUrl写入） |
| origin_url | VARCHAR | 原始图片URL（不随编辑变化） |
| local_adjust_url | VARCHAR | 编辑后临时URL（确认前存此处） |
| local_adjust_status | INT | 编辑状态：0=已确认, 其他=编辑中 |
| audit_status | VARCHAR | 审核状态：PENDING/APPROVED/REJECTED/WITHDRAWN |
| audit_type | INT | 审核类型：qt=1单图, qt=2套图, qt=4封面图 |
| reject_reason | TEXT | 驳回原因 |
| reject_type | VARCHAR | 驳回类型：QUALITY/CONTENT/SIZE/FORMAT/OTHER |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |
| gmt_modified | DATETIME | 最后修改时间 |

**关键约束**：
- `url` 在编辑确认后由 `local_adjust_url` 覆写
- `origin_url` 始终保持不变（前端 CopyURL 逻辑：`originUrl || url`）
- `local_adjust_status = 0` 表示已确认，toolbar 可见

---

## 2. audit_record（审核记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 记录ID |
| material_id | BIGINT FK | 关联素材 |
| auditor_id | VARCHAR | 审核员工号 |
| audit_action | VARCHAR | 操作：approve/reject/batch_approve/batch_reject |
| audit_result | VARCHAR | 结果：APPROVED/REJECTED |
| reject_reason | TEXT | 驳回原因（驳回时必填） |
| reject_type | VARCHAR | 驳回类型 |
| comment | TEXT | 审核备注 |
| create_time | DATETIME | 审核时间 |

---

## 3. audit_standard（审核标准表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 标准ID |
| standard_name | VARCHAR | 标准名称 |
| audit_type | VARCHAR | 适用审核类型（图片/视频/文本） |
| threshold | JSON | 判定阈值配置 |
| scope | VARCHAR | 生效范围 |
| status | INT | 状态：1=启用, 0=禁用 |
| creator | VARCHAR | 创建人 |
| usage_count | INT | 使用次数 |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

---

## 4. audit_node（审核节点表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 节点ID |
| node_name | VARCHAR | 节点名称 |
| node_type | VARCHAR | 初审/复审/终审 |
| standard_id | BIGINT FK | 关联审核标准 |
| assignee_group | VARCHAR | 审核组/负责人 |
| timeout_hours | INT | 超时时间（小时） |
| efficiency_estimate | FLOAT | 人效预估 |
| difficulty_estimate | VARCHAR | 难度预估 |
| assign_method | VARCHAR | 分配方式 |
| sort_order | INT | 排序（初审=1, 复审=2, 终审=3） |
| create_time | DATETIME | 创建时间 |

---

## 5. audit_task（审核任务表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 任务ID |
| task_name | VARCHAR | 任务名称 |
| task_type | VARCHAR | 审核任务/抽检任务/埋雷任务 |
| link_id | BIGINT FK | 关联链路 |
| batch_id | VARCHAR | 批次号 |
| status | VARCHAR | 状态：待分配/待审核/审核中/已完成/失败 |
| assignee | VARCHAR | 分配人 |
| material_count | INT | 素材数量 |
| pass_count | INT | 通过数 |
| reject_count | INT | 驳回数 |
| create_time | DATETIME | 创建时间 |
| finish_time | DATETIME | 完成时间 |

---

## 6. strategy（策略表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 策略ID |
| strategy_name | VARCHAR | 策略名称 |
| stage | VARCHAR | 策略阶段：实验/灰度/正式 |
| link_step | VARCHAR | 环节（视觉/设计/视频） |
| node_config | JSON | 节点编排配置 |
| storage_config | JSON | 落库配置 |
| description | TEXT | 策略说明 |
| creator | VARCHAR | 创建人 |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

---

## 7. strategy_link（链路表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 链路ID（如20180） |
| link_name | VARCHAR | 链路名称 |
| lifecycle | VARCHAR | 生命周期：实验/灰度/正式 |
| description | TEXT | 描述 |
| strategy_consistency | VARCHAR | 策略一致性 |
| start_params | JSON | 起点入参配置（seller_id, seed_image_url, tao_cate, item_id） |
| steps | JSON | 环节列表 |
| creator | VARCHAR | 提交人 |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

---

## 8. g_workflow_instance（工作流实例表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 实例ID |
| link_id | BIGINT FK | 关联链路 |
| task_name | VARCHAR | 任务名称 |
| run_type | VARCHAR | 运行类型：正式/测试 |
| status | VARCHAR | 运行状态 |
| common_variable | JSON | 全局变量（含 passedImg） |
| create_time | DATETIME | 创建时间 |
| finish_time | DATETIME | 完成时间 |

---

## 9. workflow_record_log（工作流节点执行记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 记录ID |
| instance_id | BIGINT FK | 关联实例 |
| node_name | VARCHAR | 节点名称 |
| node_type | VARCHAR | 节点类型（20种之一） |
| input_data | JSON | 节点输入数据 |
| output_json | JSON | 节点输出数据 |
| status | VARCHAR | 执行状态 |
| duration_ms | BIGINT | 执行耗时(ms) |
| error_msg | TEXT | 错误信息 |
| create_time | DATETIME | 开始时间 |
| finish_time | DATETIME | 结束时间 |

**下游流转验证方法**：
```sql
-- 查询审核节点的输出（passedImg）
SELECT output_json FROM workflow_record_log 
WHERE instance_id = ? AND node_name = '人工审核';

-- 验证下游节点收到正确input_data
SELECT input_data FROM workflow_record_log
WHERE instance_id = ? AND node_name = '算法过滤';
```

---

## 10. spot_check_record（抽检记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 记录ID |
| material_id | BIGINT FK | 被抽检素材 |
| original_result | VARCHAR | 原始审核结果 |
| check_result | VARCHAR | 抽检结果 |
| is_consistent | BOOLEAN | 是否一致 |
| inconsistency_reason | TEXT | 不一致原因 |
| checker_id | VARCHAR | 抽检人 |
| create_time | DATETIME | 抽检时间 |

---

## 11. landmine_record（埋雷记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 记录ID |
| material_id | BIGINT FK | 埋雷素材 |
| landmine_type | VARCHAR | 标准埋雷/违规埋雷/边界埋雷 |
| expected_result | VARCHAR | 预期结果（通过/驳回） |
| actual_result | VARCHAR | 审核员实际判定 |
| is_correct | BOOLEAN | 是否判定正确 |
| auditor_id | VARCHAR | 审核员 |
| create_time | DATETIME | 记录时间 |

---

## 表关系图

```
material ──1:N── audit_record
material ──1:N── spot_check_record
material ──1:N── landmine_record
audit_task ──N:1── strategy_link
strategy_link ──1:N── g_workflow_instance
g_workflow_instance ──1:N── workflow_record_log
audit_node ──N:1── audit_standard
```

---

## 常用查询

```sql
-- 查询待审核素材
SELECT * FROM material WHERE audit_status = 'PENDING' AND seller_id = ?;

-- 查询审核通过率
SELECT 
  COUNT(CASE WHEN audit_result='APPROVED' THEN 1 END) * 100.0 / COUNT(*) AS pass_rate
FROM audit_record WHERE auditor_id = ? AND create_time > ?;

-- 查询编辑确认状态
SELECT id, url, origin_url, local_adjust_url, local_adjust_status 
FROM material WHERE id = ?;

-- 查询链路运行状态
SELECT wrl.node_name, wrl.status, wrl.output_json 
FROM workflow_record_log wrl
JOIN g_workflow_instance gwi ON wrl.instance_id = gwi.id
WHERE gwi.link_id = ? ORDER BY wrl.create_time;

-- 验证下游流转数据
SELECT output_json->'$.passedImg' AS passed_img 
FROM workflow_record_log 
WHERE instance_id = ? AND node_name = '人工审核';
```
