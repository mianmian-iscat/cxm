# DMS Alibaba - 数据管理DMS Skill & Plugin
让 Cursor、Qoder、Qoder Work、悟空、CC 等本地 AI 客户端，以及 VSCode 系 IDE / DataGrip，直接使用阿里云 DMS 的数据库元数据、SQL 执行和工单能力。
它会把集团DMS的数据字典、SQL文件、执行结果和工单状态同步到本地文件系统。AI Agent可以直接读取本地上下文完成数据库分析，IDE插件也可以基于同一份数据提供可视化界面，不需要用户反复登录DMS控制台或手动调用API。

## ✨ 它能帮你做什么？
- 让AI读取真实DMS表结构、字段、索引和注释，减少凭空猜表、猜字段
- 让AI基于数据库上下文生成、解释和优化SQL
- 在本地执行SQL，结果自动归档，方便回看和审计AI做过什么
- 生产 / 预发变更通过 DMS 工单提交审批，避免高危环境直接执行
- 在VSCode / Cursor / Qoder 中用侧边栏可视化管理数据库组、SQL和工单，人机无缝交互
- 在DataGrip / IDEA 中像普通数据源一样浏览DMS库表

## 🧩 支持的客户端
| 客户端 | 接入方式 | 主要能力 |
|------|----------|----------|
| Cursor / Qoder / CC | AI Skill | 对话中让AI读取DMS元数据、生成SQL、调用CLI执行与归档 |
| QoderWork / 悟空 | 技能广场 | 直接选择DMS数据管理 技能 |
| VSCode / Cursor / Qoder | VSIX插件 | 可视化浏览元数据、执行SQL、回看历史结果、提交并跟踪工单 |
| DataGrip / IDEA | JetBrains 插件 | DMS数据源、库表浏览、Query Console |

## 🗂️ 工作方式

**与常规方式的对比：**

- 常规方式（MCP / CLI）——每次查询都要走完整链路：

```text
调 API 查库列表 → 调 API 查表列表 → 调 API 获取表结构 → 拼 SQL → 调 API 执行 → 拿结果
```

每一步都是一次网络请求，AI Agent 做一次分析可能要调十几次 API，慢且不稳定。

- 本地化 CLI ——数据字典、**SQL 执行记录**（`_results/` 下的 Markdown / JSON）、**工单 JSON** 等都在本地；

Agent 直接读文件即可分析库表与工单进度。以 SQL 为例：`sql/` 里的脚本与归档结果一目了然 → 生成或改写 SQL → CLI 执行 → 新结果继续落盘，无需反复拉接口。

```text
读本地 JSON / _results → 知道有哪些库、表结构、字段、索引与历次执行结果
  → 生成 SQL → 执行 → 输出写入 _results/（按日期归档）
```

## 🚀 快速使用

3 步上手 dms-alibaba。完整的安装、配置、目录结构、更新与卸载手册见 [安装/更新说明](docs/installation.md)。

### 1. 安装和更新

**前置条件：** Node.js 16+ · Python 3.8+

**安装与升级为同一命令**：已安装过再执行一次下方命令，会覆盖更新 CLI、Skill、IDE 插件包等（本地 `db-groups/`、配置里已有项一般保留；详见 [安装/更新说明](docs/installation.md)）。

**方案一（推荐）**：根据本机 git 凭证二选一（不知道选哪个？跑 `ssh -T git@gitlab.alibaba-inc.com`；静默失败等排查见 [安装有问题？](docs/installation.md#安装有问题)）。

```bash
# HTTPS
npx -y git+https://gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc

# SSH
npx -y 'git+ssh://git@gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master' --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc
```

**方案二**：克隆本仓库到本地，用 Cursor / Qoder 打开项目目录，让 Agent 参考 [docs/installation.md](docs/installation.md) 协助执行 `node bin/install.js`（参数与方案一相同）。适合 `npx` 拉取不稳或需要在源码侧排查时。

安装过程会自动拉起浏览器登录 DMS 拿 AK 写入 shell rc，无需额外配置。换路径、跳过登录、卸载等 → [安装/更新说明](docs/installation.md)。

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

![quickstart 后试跑 SQL](docs/images/quickstart-sql.png)

### 3. AI 接入


| 场景 | 安装方式 | 怎么唤起 | 开发实践 |
|------|----------|----------|----------|
| **Cursor / Qoder** | 安装时带上 `--cursor-skill` / `--qoder-skill` | 对话中输入 `/dms-alibaba-cli` | **[Cursor / Qoder AI Coding 实践](docs/best-practices/Cursor%20Qoder%20AI%20Coding%20实践.md)** |
| **Qoder Work / 悟空** | 在技能广场找到 `DMS数据管理-集团`并选择使用 | 直接使用技能 | **[Qoder Work 协同实践](docs/best-practices/Qoder%20Work%20协同实践.md)** |

> ⚠️ **AI 调用 CLI 前请先关闭 IDE 的命令沙箱**：Cursor / Qoder 默认开启的沙箱会隔离 shell 环境，让 `dms-alibaba` 读不到 `PATH` / `DMS_ALIBABA_HOME` / `DMS_ALIBABA_ACCESS_KEY_*`，表现为"command not found"或登录态失效。
> - **Cursor**：Settings → Features → Agent / Terminal，把执行模式从 Sandbox 切到 Auto-Run，或将 `dms-alibaba` 加入允许命令列表
> - **Qoder**：对话工具栏里关闭"沙箱执行"，或在自动执行白名单中加上 `dms-alibaba`

### 4. IDE 可视化

不想走 AI 链路、或者想观测 AI 都做了什么事情、还是想在 IDE 里直接用图形化界面浏览表结构 / 跑 SQL / 提工单？装上 `$DMS_ALIBABA_HOME/plugins/` 下对应 IDE 的插件即可——CLI 落到本地的元数据会被插件直接读上。

| 场景 | 安装方式 | 能做什么 | 开发实践 |
|------|----------|----------|----------|
| **VSCode / Cursor / Qoder** | `Cmd+Shift+P` → **从 VSIX 安装**，选 `$DMS_ALIBABA_HOME/plugins/dms-alibaba.vsix` | 侧边栏新增 DMS 面板：可视化创建/管理数据库组与库、跑 SQL、回看历史结果、提交并跟踪工单 | **[Cursor / Qoder 数据库开发实践](docs/best-practices/Cursor%20Qoder%20数据库开发实践.md)** |
| **DataGrip / IDEA** | 设置 → 插件 → **从磁盘安装**，选 `$DMS_ALIBABA_HOME/plugins/dms-datasource.zip` | 自动新增一个 **DMS** 数据源，像普通数据源一样浏览所有库表 / 双击看数据 / 在 Query Console 写 SQL | **[DataGrip 接入实践](docs/best-practices/DataGrip%20接入实践.md)** |

> 插件随 CLI 一起发版，CLI 升级后直接重装一次同名 vsix / zip 就是新版。


## 📝 深入了解

| 文档 | 说明 |
|------|------|
| [docs/installation.md](docs/installation.md) | 完整安装/更新说明：参数详解、目录结构、卸载、凭证、排查 |
| [skills/dms-alibaba-cli.md](skills/dms-alibaba-cli.md) | CLI 完整命令参考（同 `dms-alibaba --help`） |

## 💬 问题反馈/疑问咨询
安装、使用或接入过程中遇到问题，可以加入钉钉群咨询，或直接钉钉联系相关同学：
- 群名称：集团DMS MCP答疑群
- 群号：`110720047302`
- 联系人：立生、舜尧、为知