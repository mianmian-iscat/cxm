# DMS MCP ↔ dms-alibaba CLI 参数映射表

> 本表在 `f88-data-query` 已有映射表基础上，按原创保护 `yc-db-verification` 场景做最小化沉淀。调用 DMS 前必查，避免把 MCP 的 `database_id` 当成 CLI 的 `--db`、把多行 SQL 直接塞进 CLI。

## 核心差异

| 维度 | DMS MCP (`mcp__dms-mcp-server::executeScript`) | dms-alibaba CLI |
|------|------------------------------------------------|-----------------|
| **数据库指定** | `database_id`（逻辑库 ID） | `--db`（数据库组名） |
| **原创保护 scenario** | `database_id: 975919` | `--db scenario`，实例 `rm-8vb6631b89ix0qkwl` |
| **F88/i-FASHION stylespot** | `database_id: 30417`（逻辑库）或 `6369910`（物理 dev） | `--db stylespot`，实例 `rm-lgay0v5lor8396yka` |
| **SQL 传递** | `script` 参数，多行 SQL 直接传 | `--sql` 参数，**单行**、无尾分号 |
| **结果格式** | JSON，`columnNames` + `rows` 数组 | JSON，`rows` 数组（或 `data.rows`） |
| **大批量** | 无分页参数，大结果会被截断 | `sql run` 子命令落盘到 `_results/` 目录 |
| **超时** | MCP 默认 60s | CLI 默认 30s，大查询可加 `--timeout` |

## 常用库连接速查

### scenario 库（原创保护 + F88 素材生产表）

```bash
# 快速查询（≤200 行，直接输出）
~/dms-alibaba/bin/dms-alibaba sql query scenario --db rm-8vb6631b89ix0qkwl --sql "SELECT ..."

# 大批量（>200 行，结果落盘）
~/dms-alibaba/bin/dms-alibaba sql run scenario --db rm-8vb6631b89ix0qkwl --sql "SELECT ..."
```

### stylespot 库（F88/i-FASHION 审核/工作流/批次）

```bash
# 快速查询
~/dms-alibaba/bin/dms-alibaba sql query stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."

# 大批量
~/dms-alibaba/bin/dms-alibaba sql run stylespot --db rm-lgay0v5lor8396yka --sql "SELECT ..."
```

## 高频错误

| 错误 | 原因 | 修正 |
|------|------|------|
| MCP 返回找不到库 / 无权限 | 用 `database_id=5335708`（stylespot 物理库） | stylespot 应使用逻辑库 `30417` |
| CLI 报错 `group not found` | `--db` 填了实例名 | 应使用数据库组名 `stylespot` / `scenario` |
| CLI 报错 SQL 解析失败 | `--sql` 传了多行或尾分号 | 压成单行，去掉尾分号 |
| 大结果返回被截断 | 用 MCP 直接跑 `SELECT *` | 改用 CLI `sql run` 落盘，或对 MCP 加 `LIMIT` |

## 结果文件读取

CLI `sql run` 结果默认写入：

```
~/dms-alibaba/db-groups/{group}/sql/quick_{instance}/_results/{日期}/{时间}_{instance}.json
```

读取时优先取 `rows`：

```python
rows = d.get('rows') or d.get('data', {}).get('rows') or []
```

## 与 `f88-data-query` 的分工

- **原创保护 DB 验证**：优先使用本 skill 的 `mcp__dms-mcp-server__executeScript` 模板（见 [query-templates.md](query-templates.md)）。
- **F88/i-FASHION 查询**：优先使用 `f88-data-query` 的 dms-alibaba CLI 模板，其内部已引用本映射表。
- **MCP 不可用降级**：按 AGENTS.md 三级降级协议，先 L2 切到 dms-alibaba CLI，参数必须对照本表转换。
