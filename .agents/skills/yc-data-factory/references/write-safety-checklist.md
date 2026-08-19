# 原创保护 HSF 写操作安全清单

> 本清单适用于所有通过 HSF Tool 服务修改 `yc_right_apply` / `yc_right` / `yc_right_settle_order` 及相关子表的操作。
> 任何一步未通过，都必须停止写操作并改为 IM 私聊用户说明风险。

---

## 一、强制前置校验

### 1.1 环境校验脚本

使用本 Skill 提供的统一脚本完成 env 校验，禁止手写 SQL 后凭记忆判断。

```bash
# 基础用法
python3 ~/.qoderwork/skills/yc-data-factory/scripts/env_check.py --apply-id 200001005

# 脚本化调用示例（$? 为 0 才继续）
APPLY_ID=200001005 python3 ~/.qoderwork/skills/yc-data-factory/scripts/env_check.py --json
if [ $? -ne 0 ]; then
  echo "环境校验未通过，中止 HSF 写操作"
  exit 1
fi
```

脚本行为：

| 场景 | 退出码 | 输出 | 后续动作 |
|------|--------|------|----------|
| `env='staging'` | 0 | `校验通过，允许执行写操作` | 可继续执行 HSF 调用 |
| `env='prod'` / `'production'` | 2 | `检测到生产数据，禁止执行任何 HSF 写操作` | 立即中止，IM 私聊用户 |
| 记录不存在 | 2 | `未找到记录` | 中止，核对 applyId |
| env 为空 / 其他值 | 2 | `不是预期的 staging` | 中止，人工确认 |
| 查询失败 / CLI 不存在 | 1 | 错误原因 | 走 MCP 三级降级 L2/L3 |

### 1.2 每次写操作前重新校验

- 同一个 applyId 在一次会话内被操作 N 次，每次写操作前都要重新执行 `env_check.py`
- 禁止复用上一环节 / 上一用例 / 上一秒的校验结果
- env 可能被他人、其他流程或 Job 修改，唯一可信的是当次查询结果

---

## 二、调用前必须确认的信息

执行 HSF Tool 写操作前，向用户或日志中明确展示：

| 信息项 | 示例 |
|--------|------|
| 目标申请编号 | `applyId = 200001005` |
| 目标环境 | `env = staging`（由 env_check.py 输出） |
| 服务接口全名 | `com.taobao.industry.yc.serverless.service.hsf.tool.RightApplyToolHsfService:1.0.0` |
| 方法名 + 签名 | `updateStatus~java.lang.Long;java.lang.String` |
| 实际参数 | `[200001005, "YC_PROTECTING"]` |
| 操作目的 | 将保护状态推进到 YC_PROTECTING，用于验证退款链路 |
| 预期影响 | 修改 yc_right_apply.status 及关联状态机 |

---

## 三、执行中约束

### 3.1 仅允许 staging 写操作

- 生产环境（`env='production'`）数据只允许 SELECT 查询
- 严禁通过 HSF Tool、DMS 变更工单、直接 DB 连接或其他任何方式写入/更新/删除生产数据

### 3.2 SQL 过滤铁律

所有 DB 查询必须加 `env='staging'` 过滤：

```sql
-- 有 env 列的表
SELECT * FROM yc_right_apply WHERE id = 200001005 AND env = 'staging';
SELECT * FROM yc_right WHERE id = {rightId} AND env = 'staging';
SELECT * FROM yc_right_settle_order WHERE right_apply_id = 200001005 AND env = 'staging';

-- 无 env 列的表，必须通过已核实的 staging applyId / rightId 间接过滤
SELECT * FROM yc_right_apply_op_record WHERE right_apply_id = 200001005;
SELECT * FROM yc_tort_record WHERE right_id = {rightId};
```

### 3.3 参数类型核对

- `java.util.List<java.lang.Long>` 类型参数使用双括号：`[[id1, id2]]`
- `java.util.Date` 使用格式 `yyyy-MM-dd HH:mm:ss` 或 `yyyy-MM-dd`
- 字符串参数用英文双引号包裹

---

## 四、执行后验证

每次 HSF 写操作后必须做 DB 验证：

| 服务 | 推荐验证 SQL | 关键字段 |
|------|-------------|---------|
| RightApplyToolHsfService | `SELECT id, status, gmt_modified FROM yc_right_apply WHERE id = {applyId} AND env = 'staging'` | status 是否到达目标 |
| RightToolHsfService | `SELECT id, status, protect_expire_time FROM yc_right WHERE id = {rightId} AND env = 'staging'` | protect_expire_time / status |
| RightSettleToolHsfService | `SELECT id, settle_status, init_allowance_start_time FROM yc_right_settle_order WHERE right_apply_id = {applyId} AND env = 'staging'` | settle_status / 补贴时间 |
| ServiceTradeToolService | `SELECT id, settle_status, serv_finish_refund_status FROM yc_right_settle_order WHERE right_apply_id = {applyId} AND env = 'staging'` | 退款子状态 |
| TortToolService | `SELECT id, status FROM yc_tort_record WHERE right_id = {rightId}` | 侵权记录状态 |

---

## 五、失败与降级处理

### 5.1 env_check.py 失败时的降级路径

按 MCP 三级降级协议执行：

| 失败原因 | Level | 动作 |
|----------|-------|------|
| dms-alibaba 临时超时 / 网络抖动 | L1 | 等待 3 秒后重试一次 |
| dms-alibaba CLI 不可用 | L2 | 使用 DMS MCP `executeScript` 手动执行 `SELECT id, env FROM yc_right_apply WHERE id = {applyId}` |
| 无替代路径 | L3 | 记录 `BLOCKED_MCP: env_check 不可用`，IM 私聊用户 |

### 5.2 HSF 调用失败处理

- 服务异常 / 超时：先确认目标记录 env 仍为 staging，再重试一次
- 非法状态跳转：检查当前状态是否允许目标状态，必要时通过 DB 验证当前状态
- 参数错误：核对方法签名与参数类型，参考 SKILL.md 中的已验证签名

---

## 六、清单速查表

```
□ 已确认 applyId 为纯数字
□ 已执行 env_check.py 且退出码为 0
□ 已向用户展示服务名 / 方法名 / 参数 / 目的
□ 已确认操作目的与测试计划一致
□ HSF 调用命令已复核参数类型
□ 执行后立即做了 DB 验证
□ 验证结果与预期一致
□ 如不一致，已停止并记录现象
```
