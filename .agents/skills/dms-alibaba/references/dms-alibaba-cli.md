# DMS Alibaba CLI 使用指南

## 概述

让 Cursor、Qoder、Qoder Work、悟空、CC 等本地 AI 客户端，以及 VSCode 系 IDE / DataGrip，直接使用阿里云 DMS 的数据库元数据、SQL 执行和工单能力。
它会把集团DMS的数据字典、SQL文件、执行结果和工单状态同步到本地文件系统。AI Agent可以直接读取本地上下文完成数据库分析，IDE插件也可以基于同一份数据提供可视化界面，不需要用户反复登录DMS控制台或手动调用API。


## 快速使用

3 步上手 dms-alibaba。完整的安装、配置、目录结构、更新与卸载手册见 [安装/更新说明](../docs/installation.md)。

### 1. 安装和更新

**前置条件：** Node.js 16+ · Python 3.8+

**安装与升级为同一命令**：已安装过再执行一次下方命令，会覆盖更新 CLI、Skill、IDE 插件包等（本地 `db-groups/`、配置里已有项一般保留；详见 [安装/更新说明](../docs/installation.md)）。

**方案一**：根据本机 git 凭证二选一（不知道选哪个？跑 `ssh -T git@gitlab.alibaba-inc.com`；静默失败等排查见 [安装有问题？](../docs/installation.md#安装有问题)）。

```bash
# HTTPS
npx -y git+https://gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc

# SSH
npx -y 'git+ssh://git@gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master' --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc
```

**方案二**：克隆本仓库到本地，用 Cursor / Qoder 打开项目目录，让 Agent 参考 [docs/installation.md](../docs/installation.md) 协助执行 `node bin/install.js`（参数与方案一相同）。适合 `npx` 拉取不稳或需要在源码侧排查时。

安装过程会自动拉起浏览器登录 DMS 拿 AK 写入 shell rc，无需额外配置。换路径、跳过登录、卸载等 → [安装/更新说明](../docs/installation.md)。

### 2. 快速实践

`quickstart` 一条命令把"搜库 → 同名建组 → 全量入库 → 数据字典同步"都做了。根据需求选一条执行即可：

```bash
# 批量配置：交互式选择推荐库
dms-alibaba quickstart
# --auto 直接配置所有推荐库
dms-alibaba quickstart --auto

# 指定 schema：单次 quickstart

# 默认 quick：每个 env 选一个代表库做"全量表结构同步"，其他同 env 的库只同步表列表
dms-alibaba quickstart <schema_name>

# all：组内所有库都做"全量表结构同步"（库多时耗时较多，不建议，一般表结构都一致，没必要全部同步）
dms-alibaba quickstart <schema_name> --sync all

# 自定义数据库组名（不传时默认用 schema_name 当组名）
dms-alibaba quickstart <schema_name> --group <group_name>

# 逻辑库：把组标记为 logic=true，后续 search/sync/sql/order 都按逻辑库走
dms-alibaba quickstart <logic_schema_name> --logic
```

参考提示quickstart中的提示执行一条SQL就能验证整条链路是通的：
```
dms-alibaba sql run <group> --db <db_name> --sql "SELECT ..."
```

## CLI 调用方式

全局安装后，`dms-alibaba` 命令可在任意目录下直接使用：

```bash
dms-alibaba <command> [args]
```

项目下的 `.dms-alibaba` 是指向 `$DMS_ALIBABA_HOME`（默认 `~/dms-alibaba/`）的软链接，IDE 插件通过该链接调用 CLI。也可以直接通过 Python 模块调用：

```bash
cd .dms-alibaba  # 或 cd "$DMS_ALIBABA_HOME"
python -m dms_alibaba.cli <command> [args]
```

`dms_alibaba/paths.py` 使用 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 定位根目录（即 `dms_alibaba` 的父目录），所有路径解析（db-groups、config.json 等）都基于该根目录。

## 命令速查

### 授权配置

```bash
# 检查并配置 DMS Access Key 到 shell rc
# 优先级：当前 env > ~/.dms/credentials.json > 浏览器 OAuth 授权
dms-alibaba auth

# 强制重新走一次浏览器授权（即使 env / 凭证文件已有）
dms-alibaba auth --force

# 指向其它 DMS 环境
dms-alibaba auth --dms-host https://dms.alibaba-inc.com
```

> 安装时如果 OAuth 步骤被跳过 / 失败，事后用这条命令补一次即可。

### 一键快速启动（quickstart）

示例命令见上文「快速使用 → 快速实践」。下面给出 **`--workers`** 等与进阶调试相关的用法：

```bash
dms-alibaba quickstart <schema_name> --workers 10
```

行为说明：
- **`--workers`**：调整表结构同步并发数（默认读 `config.sync.table_detail_workers`，缺省 5）
- **`--auto`**：仅在不传 `schema_name` 时有效；省略则为交互多选；指定 `schema_name` 时 `--auto` 无效。
- 推荐模式下不支持 `--group`（每个 schema 用自身 `schemaName` 做组名）。
- 严格按 `schemaName` 等值匹配（哪怕后端搜索改成模糊，本地也只收同名库）
- 默认数据库组名 = schema 名；可用 `--group` 自定义（同名/跨 schema 收敛到同一组时有用）
- 本地库名按 `env-region` 生成，冲突自动加序号
- quick 模式：每个 env 选一个代表库 → 表列表 + 所有表的字段/索引详情；其余库只同步表列表
- all 模式：所有库都拉表列表 + 字段/索引详情
- 后续如想给 quick 跳过的库也补全表结构，单独执行
  `dms-alibaba sync <group> --db <db_name> --all-tables` 即可
- 若同名组已存在会拒绝执行，用 `--group <name>` 自定义个新名字再来一次即可
- `--logic`：逻辑库（DMS 的 logic schema）专用；写到 `group.json` 的 `logic: true`
  字段，后续所有底层 API（searchDatabase / listTables / getTableDetail /
  executeScript / createDataCorrectOrder）都会带 `logic=true`，不要和物理库混在
  同一个组里

### 数据库组管理

```bash
# 创建数据库组
dms-alibaba group create <name> --description "描述"
# 创建逻辑库组（写入 group.json 的 logic:true，后续所有接口都按逻辑库调用）
dms-alibaba group create <name> --logic --description "..."

# 删除数据库组
dms-alibaba group remove <name>

# 添加数据库到组
dms-alibaba group add-db <group> <db_name> \
  --host <host> --port <port> --schema <schema> \
  --env production --region cn-hangzhou

# 从组移除数据库
dms-alibaba group remove-db <group> <db_name>

# 列出所有组
dms-alibaba group list

# 查看组详情
dms-alibaba group info <name>

# 搜索 DMS 数据库（严格匹配库名）
dms-alibaba group search-db <schema_name>
# 指定分页参数
dms-alibaba group search-db <schema_name> --page 2 --page-size 20
# JSON 格式输出（供插件调用，包含分页信息）
dms-alibaba group search-db <schema_name> --json
```

### 多环境数据库初始化建议

用户项目中通常只会放开发环境的相关配置。初始化数据库组时，建议：

**除了用户配置的数据库，还需要拿数据库名去搜索是否有其他环境的同名数据库**（生产、预发等），有的话一并本地配置到数据库组。

```bash
# 搜索指定库名在各环境的实例
dms-alibaba group search-db dms_rm
```

这样可以找到同一库名在不同环境（开发/预发/生产）的实例，统一本地配置到数据库组中。

### 本地配置后的数据字典同步

数据库本地配置完成后，需要对各个库做数据字典同步以拉取表清单和表结构。由于数据库数量可能很多，**不建议一次性全量同步，应选择几个关键库优先同步**，例如日常环境、预发环境、生产环境各选一个库：

```bash
# 只同步指定库的表清单
dms-alibaba sync <group> --db <daily_db>
dms-alibaba sync <group> --db <staging_db>
dms-alibaba sync <group> --db <prod_db>

# 如果需要同步指定库的所有表结构（较慢，按需执行）
dms-alibaba sync <group> --db <db_name> --all-tables
```

### 数据字典同步

```bash
# 同步组内所有库的表清单
dms-alibaba sync <group>

# 同步指定库
dms-alibaba sync <group> --db <db_name>

# 同步所有表的详细结构（较慢）
dms-alibaba sync <group> --all-tables

# 同步所有表的详细结构（并行拉取，默认并发=5，可配置）
dms-alibaba sync <group> --all-tables --workers 10

# 同步指定表结构
dms-alibaba sync <group> --db <db_name> --table <table_name>
```

> `--all-tables` 现在支持并发拉取表结构。并发数优先取命令行 `--workers`，未传时读
> `config.sync.table_detail_workers`（默认 5）。

#### 查看本地结构前的检查建议

在依赖本地 JSON 查看库表结构前，先看 **`database.json`**、`tables/{table}.json`（以及 **`_index.json`**）里的 **`synced_at`**，判断数据字典是否够新；文件不存在（未同步）或 **`synced_at` 过久**时，应先执行同步再读文件：

```bash
# 同步指定库的表清单
dms-alibaba sync <group> --db <db_name>
# 同步指定表的结构
dms-alibaba sync <group> --db <db_name> --table <table_name>
```

### SQL 管理与执行

```bash
# 创建 SQL 文件夹
dms-alibaba sql create <group> <sql_name> \
  --description "描述" --db db1,db2 --tags tag1,tag2
# 标记为写操作
dms-alibaba sql create <group> <sql_name> --write

# 执行 SQL 文件（对配置的所有目标库）
dms-alibaba sql exec <group>/<sql_name>

# 执行指定行范围
dms-alibaba sql exec <group>/<sql_name> --lines 5-15

# 执行时覆盖目标库
dms-alibaba sql exec <group>/<sql_name> --db db1,db2

# 快捷执行一条 SQL（写入组内 sql/quick_<db>/quick_<db>.sql 末尾再执行；若 sql/quick_<db>/ 不存在则自动创建配置与占位文件；结果归档到该目录 _results/）
dms-alibaba sql run <group> --db <db_name> --sql "SELECT ..."
# --db 支持逗号分隔多库（db1,db2），每个库各自对应 quick_db1、quick_db2 目录
```

每次 **`sql exec`** / **`sql run`** 会在对应 SQL 目录下的 **`_results/`** 落盘（路径相对于 `db-groups/<group>/sql/<sql_name>/`，快捷模式为 `sql/quick_<db>/` 等）：

- **Markdown**：`_results/{YYYY-MM-DD}.md` — 追加式日志
- **JSON**：`_results/{YYYY-MM-DD}/{HHMMSS}_{db}.json` — 单次执行详情

### 配置管理（API 后端 / 同步并发）

API 后端的 `region → env → URL` 映射由 **官方维护**，跟随版本一起发布；
用户只能在已发布的列表里切换 region/env，不能自定义 URL。

```bash
# 查看当前配置（含当前启用的 API backend 与全量表结构并发）
dms-alibaba config show

# 交互式切换后端（↑/↓ 选择，Enter 确认）
dms-alibaba config set-api

# 设置全量表结构同步默认并发（sync --all-tables / quickstart）
dms-alibaba config set-sync --table-detail-workers 8
```

> 应急场景下可通过环境变量临时绕过：`DMS_ALIBABA_API_BASE_URL=http://...` 直接指定完整 URL。

### 环境与执行方式

不同类型的 SQL 在不同环境下应使用不同的执行方式：

- **查询类 SQL（SELECT 等）**：所有环境均可直接通过 `sql exec` 或 `sql run` 执行，结果即时返回。
- **变更类 SQL（INSERT/UPDATE/DELETE/DDL 等）**：
  - **日常环境（dev/daily）**：可以直接通过 `sql exec` 或 `sql run` 执行。
  - **预发环境（staging/pre）和生产环境（production）**：必须通过 `order submit` 提交工单，经 DMS 审批后执行，不要直接执行。

创建 SQL 时建议根据环境区分目标库，避免误操作。

### 工单管理

下文 **`$ORDER_REL`** 表示工单 JSON 路径（相对 **`db-groups`**，形如 `<group>/orders/{change|perm|nddl}/<name>.json`，子目录须与 **`order_type`** 一致）。**标准流程**：**`order init`** 生成草稿 → **编辑 JSON**（标题、SQL / 权限 / 描述等）→ **`order submit`** → 按类型走审批与后续 CLI。

表草稿临时文件在 **`orders/nddl/tmp/`**（由 **`nddl save-table`** 成功后清理登记）。存量目录不齐时执行 **`dms-alibaba migrate orders-layout`**。

#### 新建工单草稿：`order init`（不调 API）

| 目的 | 说明 |
|------|------|
| **必填** | **`--order-type`**：`change` \| `perm` \| `nddl`；**`--db-path`**：相对 `db-groups` |
| **仅组名** `mygrp` | `change` / `perm`：不在模板里预填目标库，须在 JSON 里写 **`target_databases`**；`nddl`：在组内自动选一个 **dev / development** 库写入 **`dev_db_name`**（stderr 会提示；无开发库则失败） |
| **组 + 库目录** `mygrp/db-dir` | `change` / `perm`：预填 **`target_databases`**；`nddl`：预填 **`dev_db_name`**（须为开发库） |
| **`--file-name`** | 可选，只要文件名；写入对应 **`orders/<kind>/`** |
| **`--format json`** | stdout 一行 **`path`** + **`fill`**（提交前建议补齐项） |

```bash
dms-alibaba order init --order-type change --db-path mygrp/prod-db
dms-alibaba order init --order-type perm --db-path mygrp --format json
dms-alibaba order init --order-type nddl --db-path mygrp/dev-db
```

---

#### 实践：数据变更工单（`change`）

| 阶段 | 目的 | 命令 |
|------|------|------|
| A | 生成草稿 | `dms-alibaba order init --order-type change --db-path <group>/<库> …` |
| A | 编辑工单：**标题**、**`sql`**、**`target_databases`**（须为组内已注册库） | 编辑器 / 插件 |
| B | 提交到 DMS | `dms-alibaba order submit "$ORDER_REL"` |
| B | 刷新状态 | `dms-alibaba order status "$ORDER_REL"` |
| C | 待审批：提交审批流 | `dms-alibaba order submit-approval "$ORDER_REL"` |
| C | 查看审批与链接 | `dms-alibaba order view-approval "$ORDER_REL"`（必要时 **`--runtime-ins-id`**） |
| D | 审批通过后执行变更 | `dms-alibaba order execute "$ORDER_REL"` |

**预发 / 生产**上的写操作须走工单，勿直接 **`sql exec`** / **`sql run`**。

---

#### 实践：权限工单（`perm`）

| 阶段 | 目的 | 命令 |
|------|------|------|
| A | 生成草稿 | `dms-alibaba order init --order-type perm --db-path <group>/<库> …` |
| A | 编辑工单：**标题**、**`comment`**、**`target_databases`**、**`perm_types`**（如 `QUERY` / `CHANGE` / …）、可选 **`days`**、**`resource_type`** | 编辑器 / 插件 |
| B | 提交 | `dms-alibaba order submit "$ORDER_REL"` |
| B | 刷新状态 | `dms-alibaba order status "$ORDER_REL"` |
| C | 查看审批 | `dms-alibaba order view-approval "$ORDER_REL"` |

审批通过后权限按策略生效，**无需** **`order execute`**。

---

#### 实践：结构设计工单（`nddl`）

| 阶段 | 目的 | 命令 |
|------|------|------|
| A | 生成草稿 | `dms-alibaba order init --order-type nddl --db-path <group>` 或 `…/<dev-db>` |
| A | 编辑：**标题**、**描述**、**备注**等（勿手写远端回填字段） | 编辑器 / 插件 |
| B | 创建远端项目 | `dms-alibaba order submit "$ORDER_REL"` |
| B | 刷新 **`order_id` / `project_id` / `node_role`** 等 | `dms-alibaba order status "$ORDER_REL"` |
| C · DESIGN | 表草稿与开发库发布 | `nddl create-draft` **`nddl column-data-types`** → 编辑 tmp 中的draft文件 → **`nddl save-table`** → **`nddl build-sql`** → **`nddl publish`** → **`nddl query-publish-groups`** |
| D | 节点流转（先门禁） | **`nddl check-next-node`** → **`nddl next-node`**（可重复直至 **`node_role=PUBLISH`**） |
| E · PUBLISH | 生产定时发布（推荐合一命令） | **`nddl publish-prod-bundle`**：`--db-path <group>/<prod-db目录名>`、`--plan-time`、`--precheck`（预检） |
| E | 核对任务与审批 | **`nddl query-publish-groups`**、**`order view-approval`** |
| （可选） | 退回设计继续改表（仅当生产库未执行任何发布时可以退回） | **`nddl return-design`** |

分步说明、生产 **`publish-prod-bundle`** 示例与门禁细节见仓库 **`.dev-note/perf-api/nddl-agent-playbook.md`** 及 **`.dev-note/perf-api/order_cli.sh`**。

---

## CLI 命令一览

| 命令 | 说明 |
|------|------|
| `migrate orders-layout [--db-groups DIR]` | 补齐各组 `orders/{change,nddl,perm}` 与 `nddl/tmp`，并按 `order_type` 移动仍躺在 `orders/*.json` 的文件 |
| `quickstart [--auto] [<schema>]` | 搜库 + 建组 + 入库 + 同步；不传 `<schema>` 时默认交互多选推荐，`--auto` 则对推荐列表全部批量 |
| `group create <name>` | 创建数据库组 |
| `group remove <name>` | 删除数据库组 |
| `group add-db <group> <db> --host --port --schema` | 添加数据库 |
| `group remove-db <group> <db>` | 移除数据库 |
| `group list` | 列出所有组 |
| `group info <name>` | 查看组详情 |
| `group search-db <schema> [--page N] [--page-size N]` | 搜索 DMS 数据库（严格匹配库名） |
| `sync <group> [--db <db>] [--all-tables] [--workers N]` | 数据字典同步（`--all-tables` 支持并发） |
| `config show` | 查看当前配置（API 后端、并发、AK 环境变量名） |
| `config set-api` | 交互式选择并切换当前 API 后端 |
| `config set-sync --table-detail-workers N` | 设置全量表结构同步默认并发 |
| `auth [--dms-host URL] [--force]` | 配置 DMS Access Key（env > 凭证文件 > 浏览器授权） |
| `sql create <group> <name> [--db <dbs>]` | 创建 SQL 文件夹 |
| `sql exec <group/name> [--lines 5-15] [--db <dbs>]` | 执行 SQL |
| `sql run <group> --db <db> --sql "SELECT ..."` | 快捷执行 SQL（按库使用 `sql/quick_<db>/`，不存在则创建；SQL 追加留底，结果在 `_results/`） |
| `order submit <path>` | 提交工单（`change` / `perm` / `nddl`） |
| `order status <path>` | 更新工单状态 |
| `order submit-approval <path>` | 待审批状态下提交审批流 |
| `order view-approval <path> [--runtime-ins-id N]` | 查看审批实例状态并获取审批链接 |
| `order execute <path>` | 审批通过后提交执行 |
| `order init` | 创建工单草稿 JSON（不调 API）；参数见上文 **`order init`** 小节 |
| `nddl list-tables <path>` | [nddl] 刷新表草稿清单 |
| `nddl list-dev-tables <path> [--pattern %foo%] [--format json]` | [nddl] 列出开发库表名（加载已有表草稿前检索） |
| `nddl column-data-types <path> [--format json]` | [nddl] 列出草稿列可选 `dataType` |
| `nddl create-draft <path> --table-name NAME [--force]` | [nddl] 同步清单后创建/复用本地草稿并登记（IDE 主路径） |
| `nddl obtain-table <path> (--meta-relation-id N \| --table-name NAME) [-o file]` | [nddl] 拉单表 editTable JSON |
| `nddl save-table <path> --table-file file.json` | [nddl] 预检+保存表草稿（成功后删临时文件并清 `draft_file`） |
| `nddl draft-register <path> --draft-file <rel> [--meta-relation-id N] [--table-name NAME] [--replace]` | [nddl] 登记本地草稿相对路径 |
| `nddl draft-delete <path> (--draft-file rel \| --meta-relation-id N \| --table-name NAME)` | [nddl] 删除草稿文件并清除工单登记 |
| `nddl build-sql <path>` | [nddl] 预览草稿应用到开发库的 SQL（**若有未保存本地草稿则拒绝**） |
| `nddl publish <path>` | [nddl] 将草稿真执行到开发库 |
| `nddl list-prod-databases <path> [--format json]` | [nddl] 枚举所属组内生产库 |
| `nddl load-bound-resources <path> --db-id N [--format json]` | [nddl] 基准库同组绑定生产库 |
| `nddl publish-prod-bundle <path> --db-path <group>/<prod-db> --plan-time "…" [--precheck] [--comment …]` | [nddl] 生产定时发布合一（绑定库 + 预检或下发） |
| `nddl publish-prod <path> --plan-time "…" --db-id N [--db-id N …]` | [nddl] 定时发布到指定生产库（可多 `--db-id`） |
| `nddl query-publish-groups <path> [--format json]` | [nddl] 列出发布任务组 |
| `nddl check-next-node <path> [--format json]` | [nddl] 检查是否满足进入下一节点的门禁 |
| `nddl next-node <path>` | [nddl] 进入下一流转节点 |
| `nddl return-design <path>` | [nddl] 从发布等阶段退回结构设计（DESIGN） |

## 目录结构

CLI 和数据统一存储在 `$DMS_ALIBABA_HOME`（默认 `~/dms-alibaba/`），项目下的 `.dms-alibaba` 是指向该目录的软链接。

```
$DMS_ALIBABA_HOME/   # 默认 ~/dms-alibaba/
├── bin/dms-alibaba            # CLI 包装脚本（全局命令）
├── config.json              # 全局配置（API 密钥环境变量名）
├── requirements.txt         # Python 依赖
├── skills/                  # AI Agent Skill 文档
├── dms_alibaba/               # CLI 源码
│   ├── __init__.py
│   ├── cli.py               # 命令入口
│   ├── client.py            # DMS API 客户端
│   ├── paths.py             # 路径工具
│   └── commands/
│       ├── group.py          # 数据库组管理
│       ├── sync.py           # 数据字典同步
│       ├── sql.py            # SQL 管理与执行
│       └── order.py          # 工单管理
└── db-groups/
    └── {group}/
        ├── group.json
        ├── databases/{db}/
        │   ├── database.json          # 数据库连接信息 + synced_at 同步时间
        │   ├── _index.json            # 表清单 + synced_at + table_comments
        │   └── tables/
        │       └── {table}.json       # 表结构详情 + comment + synced_at
        ├── sql/{sql_name}/
        │   ├── config.json
        │   ├── {sql_name}.sql
        │   └── _results/
        │       ├── {YYYY-MM-DD}.md       # Markdown 追加式日志
        │       └── {YYYY-MM-DD}/         # JSON 归档
        │           └── {HHMMSS}_{db}.json
        └── orders/
            ├── change/{order}.json
            ├── nddl/{order}.json
            │   └── tmp/
            └── perm/{order}.json
```

## 初始化注意事项

如果当前项目是 Git 仓库，初始化时会自动将 `.dms-alibaba` 加入 `.gitignore`，避免污染版本控制。


## 💬 问题反馈/疑问咨询
安装、使用或接入过程中遇到问题，可以加入钉钉群咨询，或直接钉钉联系相关同学：
- 群名称：集团DMS MCP答疑群
- 群号：`110720047302`
- 联系人：立生、舜尧、为知