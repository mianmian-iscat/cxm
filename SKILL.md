---
name: web-automation
version: 3.0.0
description: 通用 Web 浏览器自动化操作基座 skill，专注于测试页面的 UI 执行。通过 CDP 连接本地已登录浏览器，提供页面操作、截图、表单填写、网络抓包、iframe、文件上传、弹窗处理等通用能力。触发词：浏览器操作、网页自动化、CDP、截图、表单填写、文件上传、iframe、抓包、网络监听 | 千牛、素材管理、搭配、图文搭配、搭配素材、编辑搭配、创建搭配 | 品质联盟商品、平台商品管理、商品列表查询、商品状态、SKU详情、SKU上下架、提报价调价、日销价调价、试销完成、商品下架。注意：TPP分桶配置、安全码加白等数据构造操作已迁移至 browser-data-setup 技能。
enabled_at: 1782389924935
---

# Web Automation（通用浏览器操作基座）

通过 CDP（Chrome DevTools Protocol）连接本地已登录浏览器，提供通用的 Web 页面自动化能力。

> **目录导航**：见 [INDEX.md](INDEX.md)（根目录只保留 `SKILL.md` + `impl.py` + `package.json`）

---

## 🧠 会话启动：L0 铁律加载

> 每次会话开始时，**必须**先读取 `memory/L0/` 下的铁律文件。这些是不可违反的行为规则。

| 铁律 | 文件 | 核心内容 |
|------|------|--------|
| 数据安全 | `memory/L0/01-data-safety.md` | 禁止删除历史存量数据 |
| 多 Skill 验证 | `memory/L0/02-multi-skill-verification.md` | UI+DB+日志三层验证 |
| 不上报 att-tf | `memory/L0/03-no-att-report.md` | 除非用户明确要求 |
| 租户隔离 | `memory/L0/04-tenant-isolation.md` | F88/AFD 租户头确认 |

完整记忆入口: [memory/MEMORY.md](memory/MEMORY.md)

---

## 📸 测试报告输出规范（必须遵守）

**每次执行完测试用例后，必须以图文混排方式输出测试报告。**

### 报告格式要求

1. **每个测试用例**：用 `## TCxx ✅/❌ 用例名称` 作为标题
2. **每个关键步骤**：用加粗文字描述操作，紧跟截图
3. **截图引用**：使用 `![描述](绝对路径)` 嵌入到 Markdown 中
4. **末尾汇总表**：用表格列出所有用例的执行结果
5. **发送方式**：通过 CLI 以图文混排方式发送给用户

### 发送命令模板

```bash
openclaw message send --channel dingtalk --target <你的工号> -m "
## 🧪 测试报告标题

### TC01 ✅ 用例名称
**Step 1 - 操作描述**
![截图说明](/absolute/path/to/screenshot.png)
...

| 用例 | 操作 | 结果 |
| --- | --- | --- |
| TC01 | 操作 | ✅ PASS |
"
```

### 注意事项
- 截图路径必须是**绝对路径**
- 图文混排用 `![](path)` 嵌入，**不要**用 `--media` 单独发文件
- 每个用例至少包含：搜索/操作截图 + 验证结果截图
- 报名/提交类用例还需包含：弹窗截图 + 填写截图 + 验证截图

---

## 🐛 缺陷处理规范（必须遵守）

**执行测试用例发现缺陷时，必须立即通过 `aone-coop.create_workitem` 提交 Bug，无需等待用户提示。**

### 判断标准

| 情况 | 处理 |
|------|------|
| 前端参数正确传入，后端返回不符合条件的数据 | ✅ 提 Bug |
| API 返回错误码或服务异常 | ✅ 提 Bug |
| 页面功能未按需求预期工作 | ✅ 提 Bug |
| 业务规则限制（如红线价保护、折扣限制）导致失败 | ❌ 不提 Bug，在报告中注明 |
| 测试数据问题导致失败 | ❌ 不提 Bug，在报告中注明 |

### 提 Bug 命令模板

```bash
mcporter call aone-coop.create_workitem --args '{
  "projectId": <从需求链接中取 project/XXXXX>,
  "stamp": "Bug",
  "subject": "【模块名】简短描述",
  "assignedTo": "<你的工号>",
  "priorityId": 95,
  "cfList": {
    "47": "2-测试执行期间",
    "141538": "<关联需求的工作项ID>"
  },
  "description": "|md|\n## 问题描述\n...\n## 复现步骤\n...\n## 实际结果\n...\n## 期望结果\n...\n## 接口信息\n..."
}'
```

**必填自定义字段说明（cfList）：**

| 字段 ID | 字段名 | 示例值 | 说明 |
|---------|--------|--------|------|
| `"47"` | 发现阶段 | `"2-测试执行期间"` | Bug 在哪个阶段发现 |
| `"141538"` | 关联需求 | `"81287816"` | 关联的需求工作项 ID |

**发现阶段常见选项：**
- `"1-需求评审期间"`
- `"2-测试执行期间"`（测试阶段发现，**默认用这个**）
- `"3-生产环境"`
- `"4-线上监控"`

### 优先级参考

| 优先级 | 值 | 适用场景 |
|--------|-----|----------|
| 紧急 | 94 | 核心功能完全不可用 |
| 高 | 95 | 数据过滤/筛选逻辑错误 |
| 中 | 96 | 非核心功能异常 |
| 低 | 97 | UI 显示问题 |

### 提交后必须在报告中包含

- Bug 工作项 ID
- Bug 链接（格式：`https://project.aone.alibaba-inc.com/v2/project/<projectId>/bug/<bugId>`）

### 重新执行时必须更新 Bug 状态

**重新执行测试用例时，若之前有提交过 Bug，必须根据最新执行结果更新 Bug 状态：**

| 执行结果 | Bug 操作 |
|---------|----------|
| 问题依然复现 | 保持原状态，在报告中注明 Bug 仍存在 |
| 问题已修复（用例通过）| 使用 `aone-coop.change_workitem_status` 将 Bug 状态改为「已修复」或「已验证」 |
| 问题行为变化（新现象）| 在 Bug 下用 `aone-coop.add_comment` 追加新的复现信息 |

**更新状态命令：**
```bash
# 修改状态（已修复）
mcporter call aone-coop.change_workitem_status --args '{"workitemId": <bugId>, "statusText": "已修复"}'

# 追加评论（新信息）
mcporter call aone-coop.add_comment --args '{"workitemId": "<bugId>", "content": "重新执行结果：..."}'
```

> ⚠️ **已知限制**：`change_workitem_status` 传入 `"Invalid"` 时会因「发现阶段」等必填字段为空而失败。这种情况需通过**浏览器点击**：
> 1. 打开 Bug 页面：`https://project.aone.alibaba-inc.com/v2/project/<projectId>/bug/<bugId>`
> 2. 点击状态按鈕（`workitemStatus` class）打开下拉
> 3. 点击 `Invalid`（`.aone-menu-item`）即可直接切换，无需填写必填字段

---

## 工具选择规则（必读）

本 skill 的所有任务 **必须使用 puppeteer（CDP 9222）**，禁止使用 OpenClaw 内置 `browser` 工具。

| 维度 | 内置 `browser` 工具 | puppeteer（CDP 9222）|
|------|--------------------|-----------------------|
| 本质 | OpenClaw 托管无头浏览器（Playwright） | 接入用户本地已登录 Chrome |
| 登录态 | ❌ 无（每次新 session） | ✅ 保留用户已有 cookie |
| 内网页面 | ❌ 无法访问（无 SSO/BUC cookie） | ✅ 可直接访问 |
| CDP 抓包 | ❌ 不支持 Network 域完整抓包 | ✅ 完整 CDP Network 域 |
| React 填值 | ❌ 仅支持 Playwright act，不稳定 | ✅ native setter + dispatchEvent |
| 适用场景 | 公网页面快速截图/查询（非本 skill） | **本 skill 全部场景** |

**判断口诀：**
- 需要登录态（内网/淘系页面）→ **只用 puppeteer**
- 需要抓包 → **只用 puppeteer**
- 需要 React 填值 → **只用 puppeteer**
- 仅浏览公网页面且无需登录 → 可用内置 `browser`（但不在本 skill 范围内）

> ⚠️ 不要尝试用内置 `browser` 连接内网页面后「再补 cookie」——这条路不通。

---

## 能力边界

**支持：**
- Chrome 135+，本地已登录浏览器（CDP 端口 9222）
- HTTP / HTTPS 请求抓包（XHR、fetch）
- React / Vue / 原生 DOM 表单操作
- iframe、文件上传、弹窗处理

**不支持：**
- Firefox / Safari
- Headless 模式（需要已有登录态的本地浏览器）
- WebSocket 完整抓包（只支持帧级别监听，见 [network-capture.md](references/network-capture.md#9-兼容性边界)）
- Service Worker 缓存命中的请求（见 [boundary_cases.md](references/boundary_cases.md)）
- 跨机器远程浏览器（使用 MCP browser-automation 服务器）

---

## 安装 & 环境配置

本 skill 支持三种运行环境，启动时自动检测，无需手动切换：

| 环境 | 标识 (`WEB_AUTO_RUNTIME`) | CDP 端口 | puppeteer 来源 | 适用场景 |
|------|--------------------------|----------|---------------|----------|
| CloudCLI | `cloudcli` | 动态（从 `DevToolsActivePort` 读取） | `~/.aone-cloud-cli/plugins/browser/` | CloudCLI Web UI 浏览器 |
| OpenClaw 沙箱 | `sandbox` | 固定 9222 | `/usr/lib/node_modules/...` 内置 | OpenClaw 沙箱环境 |
| 本地 | `local` | 默认 9222（可覆盖） | `node_modules/puppeteer-core` | 个人电脑开发调试 |

**自动检测逻辑：**
1. 如果 `~/.aone-cloud-cli/browser-data/DevToolsActivePort` 存在 → `cloudcli`
2. 如果 OpenClaw 内置 puppeteer 路径存在 → `sandbox`
3. 否则 → `local`

**强制指定环境：**
```bash
export WEB_AUTO_RUNTIME=cloudcli   # 或 sandbox / local
```

---

### 环境一：CloudCLI（Cloud CLI Web UI 浏览器）

CloudCLI 自动管理 headless Chrome 实例，使用**随机 CDP 端口**（每次重启可能变化）。

| 依赖 | 状态 | 说明 |
|------|------|------|
| Node.js ≥22 | ✅ 内置 | CloudCLI 环境自带 |
| Python ≥3.8 | ✅ 内置 | CloudCLI 环境自带 |
| puppeteer-core | ✅ 内置 | `~/.aone-cloud-cli/plugins/browser/node_modules/puppeteer-core` |
| Chrome（CDP 动态端口）| ✅ 自动启动 | 端口写入 `~/.aone-cloud-cli/browser-data/DevToolsActivePort` |

**特点：**
- CDP 端口**每次启动不同**，skill 会自动从 `DevToolsActivePort` 文件读取
- 浏览器为 `headless=new` 模式，不可见但支持完整 CDP 协议
- 无需任何配置，即插即用

---

### 环境二：OpenClaw 沙箱（默认，零配置）

OpenClaw 沙箱已内置所有依赖，直接使用无需任何配置：

| 依赖 | 状态 | 说明 |
|------|------|------|
| Node.js ≥22 | ✅ 内置 | v22.21.0 |
| Python ≥3.8 | ✅ 内置 | 3.10.12 |
| puppeteer-core | ✅ 内置 | `/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core` |
| Chrome（CDP 9222）| ✅ 自动启动 | OpenClaw 沙箱管理，带 `--remote-debugging-port=9222` |
| ffmpeg | ✅ 内置 | 视频录制可选功能 |
| ImageMagick | ✅ 内置 | 截图验证可选功能 |
| openai Python 包 | ❌ 缺失 | 仅 `scripts/nl2input.py`（自然语言转 input）需要，直接传 input JSON 不受影响 |

**特点：**
- 固定 CDP 端口 9222，无需动态探测
- 所有核心依赖预装，开箱即用

**修复缺失的 openai 包：**
```bash
pip install openai
```

---

### 环境三：个人电脑（本地运行）

需要手动完成以下四步：

#### 第一步：以 CDP 模式启动 Chrome

puppeteer 通过 `connect()` 接入**已运行的** Chrome，不会自己启动浏览器。需要手动用以下命令启动：

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/chrome-debug"

# Windows（PowerShell）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" \
  --remote-debugging-port=9222 \
  --user-data-dir="$env:LOCALAPPDATA\chrome-debug"

# Linux
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

> ⚠️ **保留登录态**：`--user-data-dir` 建议指向你平时使用的 Chrome profile 目录，否则会进入全新 profile，内网登录态会丢失，需要重新登录。
>
> 验证 Chrome 是否正常开启 CDP：
> ```bash
> curl http://127.0.0.1:9222/json/version
> ```
> 返回 JSON 即表示成功。

#### 第二步：安装 puppeteer-core

```bash
cd ~/.openclaw/workspace/skills/web-automation
npm install
# 安装完成后 _node_bridge.js 会优先使用本地 node_modules/puppeteer-core
```

#### 第三步：安装 Python 依赖

```bash
pip install openai   # scripts/nl2input.py 调 LLM 所需（直接传 input JSON 可跳过）
```

#### 第四步：配置 LLM 环境变量（scripts/nl2input.py 需要）

```bash
# 使用任意 OpenAI 兼容接口
export WEB_AUTO_LLM_BASE_URL="https://api.openai.com/v1"
export WEB_AUTO_LLM_API_KEY="sk-xxx"
export WEB_AUTO_LLM_MODEL="gpt-4o"

# 或写入 ~/.bashrc / ~/.zshrc 持久化
```

#### 可选：覆盖 CDP 地址（Chrome 端口不是 9222 时）

```bash
export WEB_AUTO_CDP_URL="http://127.0.0.1:9223"  # 按实际端口修改
```

#### 网络前提（访问阿里内网页面）

`xiaoer.alibaba-inc.com`、`tppnext.alibaba-inc.com` 等均为阿里内网域名，个人电脑需连接 **VPN 或内网**方可访问。

---

### 依赖对比速查

| 依赖 | CloudCLI | 沙箱环境 | 个人电脑 |
|------|----------|----------|----------|
| Node.js ≥22 | ✅ 内置 | ✅ 内置 | 自行安装 |
| Python ≥3.8 | ✅ 内置 | ✅ 内置 | 自行安装 |
| puppeteer-core | ✅ CloudCLI 插件路径 | ✅ OpenClaw 内置路径 | `npm install` |
| Chrome CDP | ✅ 动态端口 | ✅ 固定 9222 | 手动加参数启动 |
| openai 包 | ❌ 需 pip install | ❌ 需 pip install | ❌ 需 pip install |
| LLM API Key | 阿里内网免配 | 阿里内网免配 | 需配环境变量 |
| 内网域名访问 | ✅ 直接可访问 | ✅ 直接可访问 | 需要 VPN |

### 环境变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_AUTO_RUNTIME` | 自动检测 | 强制指定运行环境：`cloudcli` / `sandbox` / `local` |
| `WEB_AUTO_CDP_URL` | 按环境 | 强制覆盖 CDP 地址（优先级最高） |
| `WEB_AUTO_PUPPETEER_PATH` | `auto` | 强制指定 puppeteer-core 路径 |
| `WEB_AUTO_ARTIFACTS_DIR` | `{skill_dir}/artifacts` | 产物输出目录 |

---

## 页面知识库（knowledge/）

`knowledge/` 目录内置了已探索过的页面结构，**避免重复探索，直接组装 input JSON**。

```
knowledge/
├── index.json                        ← 全局路由索引（10 个平台页面统一登记）
├── f88/f88-material-audit.json       ← F88 审核管理
├── f88/f88-material-production.json  ← F88 策略生产
├── afd/afd-knowledge-framework.json  ← AFD 风格店铺协作
├── aifashion/aifashion-style-selection.json
├── hjratingconsole/hjratingconsole-bill-query.json
├── xiaoer/xiaoer-original-protection.json  ← 原创保护
├── xiaoer/xiaoer-product-mgmt.json
└── xiaoer/xiaoer-adplacement.json
```

场景化 skill 的 knowledge 文件存放在各自目录下，通过 index.json 的 `file` 字段跨目录引用。

### 使用约定

**每次收到自动化请求（无论是自然语言还是直接给 input JSON），必须先进行 knowledge 查找，这一步对用户透明。**

```
1. 从请求中识别目标页面（URL / 页面名称 / 平台名）
2. 读 knowledge/index.json，匹配 env.pre/prod host + route
   ├─ 命中 → 读对应 .json，直接组装 input，无需探索
   └─ 未命中 → 实时探索页面，探索完后将结果写入新 knowledge，下次同页面不再探索
3. 生成 input JSON 并执行
```

用户不需要说「先探索页面」或「更新知识」——这些是我的内部流程。

### 知识文件结构速查

| 字段 | 说明 |
|------|------|
| `fields` | 页面可操作字段（输入框、下拉、checkbox）及定位方式 |
| `actions` | 按钮/操作（重置、搜索、展开等）|
| `apis` | 关键接口（name、urlKeyword、请求/响应字段映射）|
| `assertHints` | 推荐的断言条件 |
| `knownIssues` | 已知坑（selector 冲突、框架特殊性等）|
| `prerequisites` | 前置条件（如需签署协议）|
| `notes` | 重要注意事项 |

### knowledge 更新规则

| 场景 | 操作 |
|------|------|
| 新页面（index 未命中） | 探索完后写入新 `.json` + 更新 `index.json` |
| 发现已有 knowledge 有误 | 进行修正，更新 `lastUpdated` + 记入 `knownIssues` |
| 页面更新导致字段变化 | 更新 `fields`，标注变更日期 |

这些更新均在我内部完成，用户不需感知。

---

## 产物目录规范

每次执行必须通过 `impl.py` 走正规流程，产物自动写入 `artifacts/`。

**目录命名格式：**
```
artifacts/{scene}-{case-slug}-{YYYYMMDD-HHMMSS}/
├── manifest.json        ← 必须
├── input.json
├── output.json
├── capture.json         ← capture.enabled=true 时
├── knowledge_update.json ← knowledge 有变更时
└── screenshots/
    └── {step_index:02d}-{label}.jpg   # 1458×784 JPEG medium
```

**scene slug 对照：**
`xiaoer` / `tpp` / `qianniu` / `aifashion` / `safety-code` / `smoke`

直接写 node 脚本的执行（未经过 impl.py）需将截图和结果手动存入对应目录。

---

## 冒烟测试要求

**更新以下内容后必跟Due:**

| 更新内容 | 必跟冒烟组 |
|---------|----------|
| `core/`、`impl.py`、`knowledge/index.json` | 全部（base + 各场景）|
| `web-automation/knowledge/xiaoer-*.json` | base + xiaoer |
| `tpp-test/knowledge/` 或 `scripts/` | tpp |
| `qianniu-test/knowledge/` 或 `references/` | qianniu |
| `safety-code-whitelist/knowledge/` | safety-code |
| `web-automation/knowledge/aifashion-*.json` | aifashion |

冒烟 case 定义在 `eval/cases/`，门笛配置在 `eval/thresholds.yaml`。

**用例设计规范**：新增 eval 用例必须遵循 [references/eval-case-design-spec.md](references/eval-case-design-spec.md)，包含：
- 8 类分类（正常流程 / 异常 / 边界 / 状态机 / 接口契约 / 自愈验证 / 风险点 / 冒烟）
- 标准 JSON 结构（含 `priority` / `category` / `_testDesign` 元数据）
- 测试方法论（等价类 / 边界值 / 状态迁移 / 错误猜测 / 自愈场景）
- thresholds.yaml 注册规范

---

## 自更新机制

### knowledge_updater（自动，每次执行后触发）

`core/knowledge_updater.py` 在 FINALIZE 阶段自动运行，把执行结果反哺回对应 knowledge 文件：

| 触发条件 | 动作 |
|---------|------|
| 执行全部通过 | 更新 `_meta.lastVerified` + `verifiedByRun` |
| 步骤失败（可识别错误） | 追加到 `knownIssues[]`（去重） |
| selector 找不到元素 | 追加到 `_meta.staleFields[]` |
| 任何变更 | 追加一行到 `history/CHANGELOG.md` |

`_meta.initStatus` 从 `draft`（新建）→ `verified`（首次通过）自动升级。

### init-scene（手动，新页面初始化）

```bash
node scripts/init-scene.js \
  --name my-page-test \
  --url "https://example.alibaba-inc.com/some/route" \
  --skill-desc "某某页面测试"
```

自动生成：`SKILL.md` + `knowledge/{scene}.json`（draft）+ `references/overview.md`，并更新全局 index.json。

---

## 场景 Skill 导航

| 场景 | 子目录 | 说明 |
|------|--------|------|
| 千牛商家工作台 | `scenes/qianniu-test` | 素材管理、搭配创建/编辑 |
| 品质联盟商品管理 | `scenes/product-management-test` | 商品列表、调价、状态变更 |

> **已迁移至 `browser-data-setup` 技能**：TPP 分桶配置、时间穿越、安全码加白。这些操作页面稳定，脚本化后作为 CLI 工具使用。

---

## 输入 / 输出契约

| 文件 | 说明 |
|------|------|
| [schema/input.schema.json](schema/input.schema.json) | 测试用例输入结构（调用方必须满足） |
| [schema/output.schema.json](schema/output.schema.json) | 执行结果输出结构（下游稳定消费，不能随意改） |

**输入最小示例：**
```json
{
  "id": "example-001",
  "name": "示例：点击搜索按钮并验证结果",
  "context": { "urlPattern": "xiaoer.alibaba-inc.com" },
  "steps": [
    { "type": "click", "text": "搜索", "screenshot": true, "description": "点击搜索" },
    { "type": "wait", "ms": 2000 },
    { "type": "assert", "target": "page", "contains": "共", "description": "验证有结果" }
  ],
  "capture": { "enabled": true, "filter": "/cobweb/api/" }
}
```

---

## 🚀 上下文优化（重要）

执行多个测试用例时，上下文消耗是主要瓶颈。**推荐默认开启优化配置**：

```json
{
  "contextOptimization": {
    "screenshotExternal": true,    // 截图只保存路径，不嵌入 Base64
    "maxResponseSizeKb": 50,       // 响应体超过 50KB 截断
    "outputCompact": true,         // 精简 output.json
    "verboseMode": "summary"       // 对话输出摘要模式
  }
}
```

**优化效果：**
| 指标 | 无优化 | 优化后 | 节省 |
|------|--------|--------|------|
| output.json 大小 | ~185 KB | ~18 KB | 90% |
| tokens 消耗 | ~42,000 | ~4,500 | 89% |
| 单会话可执行用例 | 2-3 个 | 20-25 个 | 8-10 倍 |

**详细文档：** [docs/context-optimization.md](docs/context-optimization.md)

### 配置项速查

| 配置 | 默认 | 说明 |
|------|------|------|
| `screenshotExternal` | true | 截图仅保存文件路径，output 中不嵌入 Base64 |
| `maxResponseSizeKb` | 50 | 单个 API 响应体最大保留大小（KB），0=不限制 |
| `outputCompact` | true | 精简 output：成功步骤只保留核心字段，抓包只保留前 20 条 |
| `verboseMode` | summary | 对话输出模式：full\|summary\|minimal |

### 何时关闭优化

- 调试单个复杂用例（需要完整日志）
- API 响应体很大但需要全量断言
- 需要 Base64 截图嵌入报告

---

---

## 执行流程

```
读取 input（符合 input.schema.json）
  ↓
连接浏览器（127.0.0.1:9222）
  ↓
开启 CDP Network 监听（如 capture.enabled=true）
  ↓
逐步执行 steps[]
  ├─ click / fill / wait / waitForAPI / screenshot / assert / navigate
  ├─ 每步记录耗时和状态
  └─ 出错时截图 + 记录 error
  ↓
生成 output（符合 output.schema.json）
  ↓
browser.disconnect()
```

---

## 连接模板

```javascript
// puppeteer-core 由 _node_bridge.js 自动探测，直接调用脚本时无需手动 require
// 若在 skill 外部单独使用，请先 cd web-automation && npm install
const puppeteer = require('puppeteer-core'); // 或用 resolvePuppeteer() 自动探测
const fs = require('fs');

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const browser = await puppeteer.connect({ browserURL: CDP_URL, defaultViewport: null });
const pages = await browser.pages();

let page = pages.find(p => p.url().includes('目标域名'));
if (!page) {
  page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
}

const client = await page.target().createCDPSession();
const { windowId } = await client.send('Browser.getWindowForTarget');
await client.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'maximized' } });
await new Promise(r => setTimeout(r, 300));
const { bounds } = await client.send('Browser.getWindowBounds', { windowId });
await page.setViewport({ width: bounds.width, height: bounds.height, deviceScaleFactor: 1 });

// ... 执行 steps ...

browser.disconnect(); // 不要用 browser.close()
```

---

## References 导航

| 文档 | 内容 |
|------|------|
| [boundary_cases.md](references/boundary_cases.md) | ⚠️ 出现问题先查这里：遮挡/detach/抓包失败等边界场景处理口径 |
| [login-guard.md](references/login-guard.md) | ?? 登录态检测与处理：淘宝账号密码自动登录 / BUC 人工登录说明 |
| [network-capture.md](references/network-capture.md) | CDP Network 抓包：监听、拦截、Mock、HAR 导出、兼容性边界 |
| [react-form.md](references/react-form.md) | React 受控组件填值（native setter + dispatchEvent） |
| [screenshot.md](references/screenshot.md) | CDP 截图规范、水印清除 |
| [iframe-ops.md](references/iframe-ops.md) | iframe 定位、跨 frame 操作、detach 处理 |
| [file-upload.md](references/file-upload.md) | 文件上传（waitForFileChooser、非标准上传组件） |
| [popup-handling.md](references/popup-handling.md) | 引导弹窗、通知面板、遮挡清除 |
| [adaptive-locator.md](references/adaptive-locator.md) | UI 频繁变动时的语义定位策略 |
| [cdp-apis.md](references/cdp-apis.md) | 常用 CDP API 速查 |
| [eval-case-design-spec.md](references/eval-case-design-spec.md) | eval 用例设计规范（8类分类 + JSON结构 + 测试方法论） |
| [error-pattern-map.json](references/error-pattern-map.json) | 错误模式→解决方案映射表（15条规则） |

---

## 自愈强制规则（Self-Healing Mandatory Rules）

> **铁律：执行过程中遇到已有解决方案的问题时，禁止询问用户，必须自动查阅并应用。**

### 触发条件

当执行步骤出现以下任一情况时，必须进入自愈流程：
- 元素未找到 / selector 失效
- 点击无效 / 下拉菜单未展开
- Modal/Drawer 未出现
- 等待超时
- API 调用失败
- 页面未加载完成
- waitForTimeout 报错
- 登录态失效

### 自愈流程（强制执行，不得跳过）

```
步骤失败
  ↓
① 查场景参考文档（scenes/{scene}/references/*.md）
  ↓ 找到解决方案 → 直接应用 → 重试
  ↓ 未找到
② 查通用参考文档（references/*.md）
  ↓ 找到解决方案 → 直接应用 → 重试
  ↓ 未找到
③ 查知识库（knowledge/*.json + knowledge/index.json）
  ↓ 找到相关 knownIssues → 直接应用 → 重试
  ↓ 未找到
④ 查 Qoder 记忆（SearchMemory）
  ↓ 找到经验 → 直接应用 → 重试
  ↓ 未找到
⑤ 自主探索修复（调整 selector / 重新定位 / 等待策略）
  ↓ 修复成功 → 重试 + 将解法写入 references
  ↓ 失败
⑥ 仅在以上全部失败后，才允许询问用户
```

### 错误模式 → 解决方案映射表

| 错误模式 | 必查文档 | 标准解法 |
|----------|----------|----------|
| `.ant-select` 点击无反应 | 场景 references/前端组件测试要点.md | `page.mouse.click` 箭头址标 + 300ms 等待 |
| Modal 确认按钮找不到 | 场景 references/前端组件测试要点.md | 多文案正则 `/确定\|确认\|OK\|提交/` |
| `waitForTimeout is not a function` | references/boundary_cases.md | `new Promise(r => setTimeout(r, ms))` |
| 登录态失效 / BUC 跳转 | references/login-guard.md | CDP 9222 复用已登录浏览器 |
| dropdown 挂在 body 找不到 | references/popup-handling.md | `document.querySelectorAll('.ant-dropdown-menu-item')` |
| Drawer 未出现 | references/react-form.md | `waitForSelector('.ant-drawer-content', {visible:true})` |
| 文件上传失败 | references/file-upload.md | `waitForFileChooser` + `accept()` |
| iframe 内元素 | references/iframe-ops.md | `page.frames()` 查找目标 frame |
| 截图水印/弹窗遮挡 | references/popup-handling.md | 先关闭引导层再截图 |
| MTOP 请求数据未返回 | 场景 references/前端组件测试要点.md | `page.waitForResponse(url => url.includes('mtop'))` |
| 表格 loading 未完成 | references/boundary_cases.md | `waitForFunction(() => !document.querySelector('.ant-spin'))` |
| React 受控组件填值无效 | references/react-form.md | native setter + `dispatchEvent(new Event('input'))` |

### 自愈重试规则

- 引擎层（impl.py）已内置自动闭环：查知识库 → 执行 fix_code → 重试步骤 → 成功则继续
- 当 `step.healAttempt.retrySuccess == true` 时，该步骤已自动恢复，**禁止**再次询问用户或报错
- 当 `step.healAttempt.retrySuccess == false` 时，Agent 应根据 `healAttempt.source` 文档自行尝试替代方案
- 最多重试 **2次**（含首次失败共 3 次尝试）
- 每次重试前必须应用不同的修复策略（禁止盲目重试相同代码）
- 重试成功后，将有效解法写入场景 `references/` 或 `knownIssues`
- 记录自愈过程到 output 中：`step.healAttempt: {action, message, source, fix_code, retrySuccess}`

### 禁止行为

- ❌ 遇到已有解决方案的问题时询问用户
- ❌ 未查阅参考文档就询问用户
- ❌ 第一次失败就放弃并说“找不到元素”
- ❌ 盲目重试相同代码超过3次
- ❌ 跳过自愈流程直接报错

---

## 断点续跑（Checkpoint Resume）

### 何时开启

长流程用例（steps > 10 或含大量截图）建议在 input.json 中加入：

```json
"checkpoint": {
  "enabled": true,
  "segmentSize": 8,
  "outputSizeLimitKb": 200
}
```

### 执行器行为

- 每执行完 `segmentSize` 步，或累积输出超过 `outputSizeLimitKb`，自动写 `checkpoints/seg-{N}.json`
- 返回 `status="checkpoint_saved"` + `checkpoint.runId`，进程退出码为 **2**
- 全部完成返回 `status="pass"`，退出码为 **0**；出错为 **1**

### Agent 调用规则（必须遵守）

收到 `status="checkpoint_saved"` 时：

1. **不要** 在当前 session 继续生成后续 steps
2. 用 `sessions_spawn` 开一个新的轻量子 Agent（`lightContext: true`）
3. 子 Agent 任务：读 `checkpoint.stateFile`（state.json） → 续跑
4. 续跑命令：`python impl.py input.json --resume <checkpoint.runId>`
5. 子 Agent 再次收到 `checkpoint_saved` 时递归重复，直到 `pass` 或 `error`

```python
# 子 Agent 续跑示例
result = asyncio.run(run_test(input_data, resume_run_id="xiaoer-xxx-20260424-133000"))
```

### state.json 结构速查

```json
{
  "runId": "xiaoer-adjust-price-20260424-133000",
  "totalSteps": 25,
  "lastCompletedStep": 15,
  "lastPageUrl": "https://pre-xiaoer...",
  "capturedApis": {
    "adjustPrice.checkTriggerApprove": { "responseBody": {...} }
  },
  "segments": [
    { "segIndex": 0, "stepRange": [0, 7], "status": "pass" },
    { "segIndex": 1, "stepRange": [8, 15], "status": "pass" }
  ],
  "status": "running"
}
```

---

## 硬约束（速查）

> 完整约束见 [prompts/system.txt](prompts/system.txt)

- React input **必须** 用 native setter，**禁止** `page.type()`
- 截图 **必须** 用 `Page.captureScreenshot`，**禁止** `page.screenshot()`
- 抓包 **必须** 用 CDP Network 域，**禁止** `page.on('response')`
- 操作完成 **必须** `browser.disconnect()`，**禁止** `browser.close()`
- `getResponseBody` **必须** 在 `Network.loadingFinished` 之后调用

---

## 依赖

| 项目 | 值 |
|------|---|
| puppeteer-core | 按运行环境自动探测（CloudCLI / Sandbox / 本地），也可通过 `WEB_AUTO_PUPPETEER_PATH` 指定 |
| Node.js | >=22.0.0 |
| Chrome CDP 端口 | CloudCLI 动态端口 / Sandbox 固定 9222 / 本地可通过 `WEB_AUTO_CDP_URL` 覆盖 |

### 安装（移植到新机器时）

```bash
cd skills/web-automation
npm install          # 安装 puppeteer-core
```

### 可选环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_AUTO_RUNTIME` | 自动检测 | 强制指定运行环境：`cloudcli` / `sandbox` / `local` |
| `WEB_AUTO_CDP_URL` | 按环境 | Chrome CDP 地址，强制覆盖自动检测 |
| `WEB_AUTO_ARTIFACTS_DIR` | `{skill_dir}/artifacts` | 产物输出目录 |
| `WEB_AUTO_PUPPETEER_PATH` | `auto` | puppeteer-core 路径，`auto` 时按环境自动探测 |

---

## 📌 汇金平台账单查询示例

### 场景描述

打开汇金 Rating Console 预发环境的账单查询页面，通过外部订单号查询特定业务类型的账单结果。

### 支持的业务类型

- `TB_FUSHI_CD_LIVE_YJ_STD_PROCESS` - 直播服饰抽佣（正常）
- `TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS` - 直播服饰抽佣（退款）
- 其他业务类型可通过页面查询结果查看

### 使用方法

#### 方法一：使用 browser 工具直接操作

```javascript
// 1. 打开页面
browser(action="open", targetUrl="https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm")

// 2. 获取 snapshot 找到输入框 ref
browser(action="snapshot", refs="aria")

// 3. 填写订单号
browser(action="act", kind="fill", fields=[{"ref": "e21", "value": "5115769992032011830"}])

// 4. 点击查询
browser(action="act", kind="click", ref="e38")

// 5. 等待并获取结果
browser(action="act", kind="wait", timeMs=5000)
browser(action="snapshot", refs="aria", depth=5)
```

#### 方法二：使用 Python 脚本提取结果

```bash
# 先用 browser 工具获取 snapshot，然后：
python3 archive/hj-bill-query/hj-bill-query-simple.py 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS
```

#### 方法三：使用 input.json 执行完整流程

```json
{
  "id": "hj-bill-query-001",
  "name": "汇金账单查询",
  "context": {
    "urlPattern": "pre-hjratingconsole.alibaba-inc.com",
    "baseUrl": "https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm",
    "orderId": "5115769992032011830",
    "targetBizTypes": ["TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS", "TB_FUSHI_CD_LIVE_YJ_STD_PROCESS"]
  },
  "steps": [
    {"type": "navigate", "url": "https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm"},
    {"type": "wait", "ms": 2000},
    {"type": "fill", "field": "outBizId", "value": "5115769992032011830"},
    {"type": "click", "text": "一键排查"},
    {"type": "wait", "ms": 5000},
    {"type": "screenshot", "label": "result"}
  ]
}
```

### 查询结果结构

查询结果分为三部分：

1. **消息查询结果** - 包含消息 ID、业务时间、状态、错误码等
2. **详单查询结果** - 包含交易额、金额、科目、业务时间等
3. **账单查询结果** - 包含账单 ID、交易额、金额、未销金额、支付宝账号等

### Knowledge 文件

页面结构已保存在 `knowledge/hjratingconsole-bill-query.json`

### 注意事项

- 需要阿里内网访问权限（BUC 登录）
- 预发环境 URL：`https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm`
- 查询结果可能包含多个表格，需要按业务类型筛选
