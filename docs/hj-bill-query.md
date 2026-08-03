# 汇金平台账单查询功能集成指南

本文档说明如何将汇金平台（hjratingconsole）账单查询功能内化到 web-automation skill 中。

## 📁 已添加的文件

### 1. Knowledge 文件
**路径**: `knowledge/hjratingconsole-bill-query.json`

描述汇金账单查询页面的结构，包括：
- 页面字段（输入框、下拉选择器、按钮）
- 操作定义（一键排查、重置）
- API 信息
- 断言提示
- 已知问题

### 2. 查询脚本

#### JavaScript 版本
**路径**: `archive/hj-bill-query/hj-bill-query.js`

使用 puppeteer-core 直接连接 CDP 浏览器，执行完整的查询流程并提取结果。

**用法**:
```bash
node archive/hj-bill-query/hj-bill-query.js <订单号> <业务类型 1> [业务类型 2] ...
```

**示例**:
```bash
node archive/hj-bill-query/hj-bill-query.js 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS
```

#### Python 简化版本
**路径**: `archive/hj-bill-query/hj-bill-query-simple.py`

从 browser snapshot 输出中提取指定业务类型的结果。需要先通过 browser 工具获取页面快照。

**用法**:
```bash
python3 archive/hj-bill-query/hj-bill-query-simple.py <订单号> <业务类型 1> [业务类型 2] ...
```

#### Shell 封装脚本
**路径**: `archive/hj-bill-query/hj-bill-query.sh`

一键执行的 shell 脚本，自动创建 input.json 并调用 impl.py 执行。

**用法**:
```bash
./archive/hj-bill-query/hj-bill-query.sh <订单号> <业务类型 1> [业务类型 2] ...
```

### 3. 文档更新

#### SKILL.md
在通用 Web 自动化 skill 文档中添加了汇金查询示例章节，包括：
- 场景描述
- 支持的业务类型
- 三种使用方法
- 查询结果结构说明
- 注意事项

#### knowledge/index.json
添加了汇金账单查询页面的全局索引条目，便于快速查找。

## 🎯 支持的业务类型

| 业务类型 | 说明 |
|---------|------|
| `TB_FUSHI_CD_LIVE_YJ_STD_PROCESS` | 直播服饰抽佣（正常） |
| `TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS` | 直播服饰抽佣（退款） |
| 其他 | 可通过页面查询，自动识别 |

## 📊 查询结果结构

查询结果分为三个表格：

### 1. 消息查询结果
- ID
- 用户 ID
- 业务时间
- 创建时间
- 修改时间
- 业务唯一号
- 外部订单号
- 业务类型 (bizType)
- 状态
- 环境
- 处理次数
- 错误码

### 2. 详单查询结果
- ID
- 用户
- 交易额
- 金额
- 业务时间
- 消息时间
- 科目
- 状态
- 创建时间
- 消息 ID

### 3. 账单查询结果
- ID
- 用户
- 交易额
- 金额
- 未销金额
- 业务时间
- 创建时间
- 修改时间
- 销账时间
- 科目
- 状态
- 错误码
- 商家支付宝 ID
- 平台支付宝 ID

## 🔧 使用方式

### 方式一：直接使用 browser 工具（推荐用于调试）

```javascript
// 1. 打开页面
browser(action="open", targetUrl="https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm")

// 2. 获取 snapshot
browser(action="snapshot", refs="aria")

// 3. 填写订单号（根据 snapshot 找到的 ref）
browser(action="act", kind="fill", fields=[{"ref": "e21", "value": "订单号"}])

// 4. 点击查询
browser(action="act", kind="click", ref="e38")

// 5. 等待并获取结果
browser(action="act", kind="wait", timeMs=5000)
browser(action="snapshot", refs="aria", depth=5)
```

### 方式二：使用 JavaScript 脚本（推荐用于自动化）

```bash
cd ~/.openclaw/workspace/skills/web-automation
node archive/hj-bill-query/hj-bill-query.js 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS
```

### 方式三：使用 Python 脚本处理 snapshot（推荐用于快速提取）

```bash
# 1. 通过 browser 工具获取 snapshot
# 2. 将 snapshot 输出粘贴到脚本
python3 hj-bill-query-simple.py 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS
```

### 方式四：使用 input.json（推荐用于测试用例）

创建 input.json 文件，定义完整的测试步骤，然后通过 `python3 impl.py input.json` 执行。

## ⚠️ 注意事项

1. **内网访问**: 需要阿里内网权限和 BUC 登录态
2. **环境选择**: 
   - 预发：`https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm`
   - 日常：`https://hjratingconsole-admin-daily.taobao.net/hjratingconsole/faq/billQuery.htm`
   - 线上：`https://hjratingconsole.admin.taobao.org/hjratingconsole/faq/billQuery.htm`
3. **CDP 连接**: 确保 Chrome 浏览器在 CDP 模式下运行（端口 9222）
4. **结果去重**: 脚本会自动去重相同 ID 的记录

## 🧪 测试验证

使用以下命令验证功能是否正常：

```bash
# 测试 JavaScript 脚本
cd ~/.openclaw/workspace/skills/web-automation
node archive/hj-bill-query/hj-bill-query.js 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS

# 检查结果是否保存到 artifacts 目录
ls -la artifacts/hj-bill-query-*
```

## 📝 维护说明

- **页面结构变更**: 更新 `knowledge/hjratingconsole-bill-query.json`
- **新增业务类型**: 无需修改代码，脚本支持任意业务类型查询
- **环境变更**: 修改脚本中的 `BASE_URL` 常量
- **提取逻辑优化**: 更新 `archive/hj-bill-query/` 下脚本中的解析逻辑

## 🔗 相关文件

- Knowledge: `knowledge/hjratingconsole-bill-query.json`
- 索引：`knowledge/index.json`
- JS 脚本：`archive/hj-bill-query/hj-bill-query.js`
- Python 脚本：`archive/hj-bill-query/hj-bill-query-simple.py`
- Shell 脚本：`archive/hj-bill-query/hj-bill-query.sh`
- 文档：`SKILL.md`（汇金查询示例章节）
