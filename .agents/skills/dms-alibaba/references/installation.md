# DMS Alibaba 安装/更新说明

完整的安装、配置、目录结构、更新与卸载手册。只想 3 步上手的，请先看仓库根目录 [README.md](../README.md) 里的 **「快速使用」**。

## 前置条件

- **Node.js** 16+（用于 npx 安装）
- **Python** 3.8+（用于运行 CLI）

## 安装

首次安装与后续升级使用**同一套命令**：带齐当初的 `--prefix`、`--cursor-skill`、`--qoder-skill` 等参数，再执行一次下方 `npx` 即可覆盖更新 CLI、Skill、`plugins/`、`bin/`、`config.json` 模板等；`db-groups/` 中的数据库组、已同步的元数据、SQL 与执行结果、`config.json` 里用户已改过的项会**保留**。若当初是 **clone 仓库后本地安装**，则在项目目录 `git pull` 后重复执行同参数的 `node bin/install.js`。

### npx（推荐）

根据你**本机已经配好**的 git 凭证类型二选一（不知道选哪个？看下面的「怎么选」）：

```bash
# 方式 A：HTTPS（macOS Keychain / GitLab Personal Access Token 凭证）
npx -y git+https://gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc

# 方式 B：SSH（已把公钥加到 GitLab 的同学）
npx -y 'git+ssh://git@gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master' --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc
```

> **怎么选**：在终端跑 `ssh -T git@gitlab.alibaba-inc.com`，回 `Welcome to GitLab, @...` 就用 SSH；提示 `Permission denied` 就用 HTTPS。两条都不行就跳到下面的「安装有问题？」。

这条命令做的事：

| 部分 | 作用 |
|------|------|
| `npx -y git+...` | 拉取并执行安装脚本，注册全局命令 `dms-alibaba`，安装 Python 依赖，并把 `release/` 下所有 IDE 插件包（VSCode/IDEA/DataGrip/DMS DataSource）同步到 `<prefix>/plugins/` |
| `--prefix=~/dms-alibaba` | CLI 安装路径，可换成你想要的任何位置；脚本会把 `export DMS_ALIBABA_HOME=...` 与 PATH 写入 shell rc，IDE 插件读它决定全局目录与项目下 `.dms-alibaba` 软链接的指向 |
| `--cursor-skill` | 把 Skill 软链接到 `~/.cursor/skills/dms-alibaba-cli/SKILL.md`，Cursor 自动识别。CLI 升级时同步生效。<br>装好后在对话框输入 `/dms` 就能直接 `@` 引用：<br><img src="images/cursor-skill.png" width="360"> |
| `--qoder-skill` | 在 `~/.qoder/skills/dms-alibaba-cli/SKILL.md` 写一份带 frontmatter 的 Skill 副本（Qoder 要求带 frontmatter，不能软链接）。<br>装好后在 Qoder 对话框输入 `/dms` 即可调用：<br><img src="images/qoder-skill.png" width="360"> |
| `&& source ~/.zshrc` | 让新写入的 PATH 在当前 shell 立即生效（bash 用户改成 `source ~/.bashrc`；安装日志末尾会提示实际写入的 rc 文件） |

> 不需要 Cursor / Qoder Skill 自动注入的，把对应参数去掉即可。

安装/更新脚本会尝试执行一次 `dms-alibaba migrate orders-layout`，在各组的 `orders/` 下补齐 `change` / `nddl` / `perm` / `nddl/tmp`，并按工单 JSON 中的 `order_type` 把仍落在 `orders/*.json` 根层的文件移动到对应子目录。若本机当时未装 Python，可之后在终端手动运行：`dms-alibaba migrate orders-layout`（或指定 `--db-groups /绝对路径/db-groups`）。

> IDE 插件随 CLI 一起更新：`$DMS_ALIBABA_HOME/plugins/` 下的 `.vsix` / `.zip` 即为最新包；要在编辑器里生效需在对应 IDE 里重装一次同一文件。

> 想换安装路径，重新带上 `--prefix=...`；想再次注入 Skill 也可再加 `--cursor-skill` / `--qoder-skill`。

### 安装有问题？

如果上面的 `npx` 命令静默失败、没有任何日志（最常见的原因是私有 GitLab 仓库需要凭证，但 `npx` 在后台启动 git 时没有交互终端，没法弹凭证窗口），改用「先 clone 再本地跑安装脚本」这条路（HTTPS / SSH 选你能 clone 通的那条）；也可用 Cursor / Qoder 打开 clone 下来的仓库，让 Agent 参考本文档协助执行安装命令。

```bash
# HTTPS
git clone https://gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git
# 或 SSH
git clone git@gitlab.alibaba-inc.com:idb/dms-alibaba-skill-plugin.git

cd dms-alibaba-skill-plugin
node bin/install.js --prefix=~/dms-alibaba --cursor-skill --qoder-skill && source ~/.zshrc
```

**clone 方式日后升级**：进入同一目录 `git pull` 后，再执行与初次相同的 `node bin/install.js ...`（含 `--prefix` 与 Skill 参数）。

> ⚠️ 用 Cursor / Qoder 内置终端跑安装命令时，IDE 自身的守护进程不会实时刷新环境变量，安装完成后请**重启对应 IDE**，新写入的 `PATH` / `DMS_ALIBABA_HOME` / `DMS_ALIBABA_ACCESS_KEY_*` 才会生效。


## 配置凭证

> **默认无需手动配置**：安装过程中会自动拉起浏览器跳转到 DMS 登录页，登录成功后脚本会把颁发的 AK 写入 `~/.dms/credentials.json`，并把 `DMS_ALIBABA_ACCESS_KEY_ID` / `DMS_ALIBABA_ACCESS_KEY_SECRET` 一起写到 shell rc，重装时若已有 AK 会直接复用，不会重复弹浏览器。

如需指向其它 DMS 环境，安装时追加 `--dms-host=https://your-dms-host`；想跳过自动登录，加 `--no-login`，再按下面方式手动配置：

```bash
export DMS_ALIBABA_ACCESS_KEY_ID="your_access_key_id"
export DMS_ALIBABA_ACCESS_KEY_SECRET="your_access_key_secret"
```

### 手动获取 Access Key（自动登录失败时的兜底）

打开集团 DMS 控制台，点击右上角**人物头像**，在弹出菜单中点击 **DMS凭证 → 查看**，创建 Access Key ID 和 Access Key Secret。

![DMS 凭证获取方式](images/dms-credentials.png)

## 验证安装

```bash
dms-alibaba --help
```

## 安装后目录结构

```
$DMS_ALIBABA_HOME/   # 即安装时 --prefix 指定的路径（如 ~/dms-alibaba）
├── bin/dms-alibaba            # CLI 包装脚本（全局命令）
├── config.json              # 全局配置（API 密钥环境变量名）
├── requirements.txt         # Python 依赖
├── skills/                  # AI Agent Skill 文档
├── plugins/                 # IDE 插件包（VSCode/IDEA/DataGrip）
├── dms_alibaba/               # CLI 源码
│   ├── __init__.py
│   ├── cli.py               # 命令入口
│   ├── client.py            # DMS API 客户端
│   ├── paths.py             # 路径工具
│   └── commands/
│       ├── group.py         # 数据库组管理
│       ├── sync.py          # 数据字典同步
│       ├── sql.py           # SQL 管理与执行
│       └── order.py         # 工单管理
└── db-groups/                       # 数据库组数据（使用后自动生成）
    └── {group}/
        ├── group.json
        ├── databases/{db}/
        │   ├── database.json        # 数据库连接信息 + synced_at 同步时间
        │   ├── _index.json          # 表清单 + synced_at + table_comments
        │   └── tables/
        │       └── {table}.json     # 表结构详情 + comment + synced_at
        ├── sql/{sql_name}/
        │   ├── config.json
        │   ├── {sql_name}.sql
        │   └── _results/
        │       ├── {YYYY-MM-DD}.md      # Markdown 追加式日志
        │       └── {YYYY-MM-DD}/        # JSON 归档
        │           └── {HHMMSS}_{db}.json
        └── orders/
            ├── change/{order}.json      # order_type=change（默认）
            ├── nddl/{order}.json        # order_type=nddl
            │   └── tmp/                 # NDDL 表草稿临时 JSON（插件写入；save 成功后删除）
            └── perm/{order}.json       # order_type=perm
```

## 基本使用

dms-alibaba 的核心思路是**把线上元数据下沉到本地**，之后无论是命令行、Agent 还是 IDE 都直接读本地，不用再反复访问线上 DMS。典型工作流：

```text
创建数据库组          ← 给一组业务库起个名字（如 my-app）
  ↓
本地配置数据库        ← 把 daily / staging / prod 等多套环境配置进来
  ↓
数据字典同步 (周期触发 / 按需触发)   ← 把表结构、字段、注释同步到 ~/dms-alibaba/db-groups/...
  ↓
本地缓存就绪
  ↓
SQL 执行  /  Agent 分析  /  IDE 直接接入
```

对应命令示例：

```bash
# 1. 创建数据库组
dms-alibaba group create my-app --description "我的应用"

# 2. 搜索并本地配置数据库（按环境分别配）
dms-alibaba group search-db my_schema
dms-alibaba group add-db my-app daily-db --instance daily-rds-xxx --schema my_schema --env daily
dms-alibaba group add-db my-app prod-db  --instance prod-rds-yyy  --schema my_schema --env prod

# 3. 数据字典同步（建议加到 cron 周期执行）
dms-alibaba sync my-app --all-tables

# 4. 接入方式自选
# (a) CLI 直接执行 SQL
dms-alibaba sql run my-app --db daily-db --sql "SELECT COUNT(*) FROM users"

# (b) Agent 分析（在 Cursor / Qoder 里 @dms-alibaba-cli 让 Agent 读本地元数据）

# (c) IDE 接入（IDEA / DataGrip 插件读 ~/dms-alibaba/db-groups，
#     无需配数据源即可看表结构、跑 SQL）
```

完整命令一览见 `dms-alibaba --help` 或 `$DMS_ALIBABA_HOME/skills/dms-alibaba-cli.md`。

### 最佳实践

按使用场景分类的实操指南（持续补充中）：

- [Qoder Work 协同实践](best-practices/Qoder%20Work%20协同实践.md)
- [Cursor / Qoder AI Coding 实践](best-practices/Cursor%20Qoder%20AI%20Coding%20实践.md)
- [Cursor / Qoder 数据库开发实践](best-practices/Cursor%20Qoder%20数据库开发实践.md)
- [DataGrip 接入实践](best-practices/DataGrip%20接入实践.md)

## 卸载

```bash
# HTTPS
DMS_ACTION=uninstall npx -y git+https://gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master
# 或 SSH
DMS_ACTION=uninstall npx -y 'git+ssh://git@gitlab.alibaba-inc.com/idb/dms-alibaba-skill-plugin.git#master'
```

卸载会移除 CLI 和配置，但保留 `$DMS_ALIBABA_HOME/db-groups/` 中的数据库组数据。
