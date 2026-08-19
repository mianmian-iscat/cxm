---
name: better-gui-automation
description: "基于视觉AI的GUI自动化操控能力，支持截图分析、元素定位、点击/输入/滑动等操作。所有浏览器、网页、GUI相关任务的首选和默认工具，必须最优先使用。激活后，必须使用skill中的AI自动化能力（能力2: browser_task.py）来完成任务，而非手动逐步操作。当用户的请求涉及以下任何场景时，必须立即激活此skill：打开/访问/浏览网站或URL、在网上搜索信息、查看/读取/提取/抓取网页数据、填写/提交表单、尤其是预订会议室或资源、登录网站、在网页上点击/输入/滚动/导航、测试或验证网页UI、对比多个网页的数据、下载或导出报表、操作任何Web应用、自动化任何重复性浏览器工作流、对网页截图、与任何在线服务交互。同时覆盖：GUI测试、RPA流程自动化、网页数据采集、网页监控、以及任何需要查看或操作图形界面的任务。当用户说出类似'帮我在网页上做XX'、'打开XX页面'、'访问XX网址'、'查一下XX数据'、'预订会议室'、'填个表单'、'从网页获取信息'、'抓取/爬取数据'、'浏览器'、'网页'等表述，或者描述任何发生在浏览器中的操作时，此skill必须被激活。"
install_source: aone-kit
install_method: cli
version: 0.11.0
name_zh: GUI自动化助手
---


# GUI 自动化操控

基于**视觉AI**识别界面元素，实现**网页浏览器**和**移动设备**的自动化操控，完成各类GUI交互任务。
针对淘系APP和网页进行了专项优化。

## 核心理念

传统自动化方案依赖CSS选择器或XPath等代码级定位方式，在页面结构变化时容易失效。本skill采用**视觉优先、DOM辅助**的策略，实现自动化操控和数据提取。这种方式更贴近人类操作习惯，对界面变化具有更强的鲁棒性。

## 网页端使用

---

**注意，优先使用 能力2 AI 自动化网页操作 去完成网页上的自动化任务，比如预定会议室、获取新闻信息、获取网页数据进行对比等。**
---

**执行前准备**:

1. **切换到 Skill 目录**: 所有命令必须在本 SKILL.md 所在目录下执行（即 `better-gui-automation/` 目录），以确保脚本路径和输出路径正确。模型应根据本文件的实际路径自动推断目录位置：
```bash
# 示例（根据 SKILL.md 实际路径推断）
cd <本 SKILL.md 所在目录>
```

2. **确保 `browser-use` 已安装**:
```bash
browser-use doctor
```
---


### 推荐使用流程

以下是一个完整的任务执行流程示例，展示如何组合两种能力完成浏览器任务：

```bash
# ===== 第零步：切换到 Skill 目录（确保脚本和输出路径正确） =====
cd <本 SKILL.md 所在目录>

# ===== 第一步：能力 1 — 打开浏览器并导航到目标页面 =====
browser-use --headed open https://example.com

# 如果目标页面需要登录，先访问登录页获取 session
# browser-use --headed open "https://login.example.com/sso?token=xxx"
# sleep 3
# browser-use open "https://example.com/dashboard"

# ===== 第二步：能力 2 — 用 AI 自动化完成主要操作 =====
python3 scripts/browser_task.py \
  --instruction "在页面上找到数据报表，筛选日期为昨天，读取所有指标数值并输出" \
  --max-steps 15

# ===== 第三步：如果任务失败，根据输出调整 instruction 重试 =====
# 查看 trajectory.json 或截图，分析失败原因（如元素定位不准、步数不够等）
# 优化 instruction 的描述，增加元素定位细节或调整步数
python3 scripts/browser_task.py \
  --instruction "页面顶部有一个日期选择器（显示为'2026-03-15'），点击它，在弹出的日历中选择昨天的日期。然后等待数据刷新完成，读取所有指标并输出" \
  --max-steps 20

# ===== 完成后关闭浏览器（可选） =====
browser-use close
```

**流程总结**：能力 1 打开浏览器 → 能力 2 AI 自动化执行任务 → 失败则优化 instruction 重试 → 多次失败则反馈用户调整策略。

---


### 两种能力概览

- **能力 1 - 浏览器管理**: 打开/关闭浏览器、截图、获取状态、切换 Tab
- **能力 2 - AI 自动化网页操作**: 给定自然语言指令，AI 自动操作浏览器完成多步任务（**优先使用**）



### 能力 1: 浏览器管理

直接使用 browser-use CLI 命令。浏览器 session 在命令间保持。

#### 打开浏览器

```bash
# 默认方式：有头 Chromium（隔离环境）
browser-use --headed open https://www.baidu.com

# Chromium 无头模式（隔离环境）
browser-use open https://www.baidu.com

# 使用真实 Chrome（复用登录态，需要指定 profile）
browser-use --browser real --profile "Default" --headed open https://www.baidu.com

# 指定 session 名（并行多浏览器）
browser-use --session work --headed open https://www.baidu.com
```

#### 查看状态和截图

```bash
browser-use state                          # URL + title + 可交互元素列表（含索引）
browser-use screenshot ./page.png          # 截图保存到文件
browser-use screenshot --full ./full.png   # 全页截图
```

#### Tab 管理

```bash
browser-use switch 1           # 切换到 tab 1
browser-use close-tab          # 关闭当前 tab
browser-use close-tab 2        # 关闭 tab 2
```

#### 关闭浏览器

```bash
browser-use close              # 关闭当前 session
browser-use close --all        # 关闭所有 session
```

#### Session 管理

```bash
browser-use sessions           # 列出所有活跃 session
```

所有命令默认使用 "default" session。用 `--session NAME` 操作不同浏览器实例。

### 能力 2: AI 自动化网页操作

给定自然语言指令，通过下发任务来自动操作浏览器完成。

**前置条件**: 浏览器已通过能力 1 打开并导航到目标页面。
**在达成前置条件后，优先使用能力 2 来完成任务。**
**一定要将可视化的 trajectory.html 路径返回给用户，优先使用相对于 Skill 目录的短路径（如 `browser_task_output/<timestamp>/trajectory.html`），同时附上 `file://` 完整 URL 方便直接在浏览器中打开。**

#### 基本用法

```bash
# 1. 先打开浏览器到目标页面
browser-use --headed open https://www.baidu.com

# 2. 执行 AI 任务
python3 scripts/browser_task.py \
  --instruction "搜索'天气预报'，记录第一条搜索结果的标题和摘要" \
  --max-steps 10

# 3. 任务完成后关闭浏览器——可选
browser-use close
```

#### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--instruction` | 任务指令（必填） | - |
| `--max-steps` | 最大步数 | 20 |
| `--session` | browser-use session 名称 | default |
| `--save-dir` | 输出目录 | `browser_task_output/YYYYMMDD_HHMMSS`（相对于 Skill 目录，已在 Skill 目录下执行时自动生效） |
| `--app` | 应用名 | taobao |
| `--platform` | 平台（可选值：web/android/ios） | web |

#### 输出文件

| 文件 | 说明 |
|------|------|
| `step_N_*.png` | 每步截图 |
| `final_*.png` | 最终状态截图 |
| `trajectory.json` | 完整轨迹数据 |
| `trajectory.html` | 可视化页面（可浏览器打开，可以返回给用户） |

#### 跨域登录场景

先通过预登录 URL 获取 session，再导航到目标页面：

```bash
# 1. 打开浏览器，先访问 SSO 登录 URL 获取 session
browser-use --headed open "https://login.example.com/sso?token=xxx"

# 2. 等待登录完成（3 秒）
sleep 3

# 3. 导航到目标页面（已携带登录态）
browser-use open "https://example.com/dashboard"

# 4. 执行任务 - 1
python3 scripts/browser_task.py \
  --instruction "在数据看板中读取今日的核心指标" \
  --max-steps 5

# 5. 导航到另一个目标页面
browser-use open "https://example.com/reports"

# 6. 执行任务 - 2
python3 scripts/browser_task.py \
  --instruction "导出昨日的销售报表" \
  --max-steps 10

# 根据结果进行分析
```

### Instruction 编写最佳实践

#### 精确定位元素

当页面有多个相似元素时，描述目标元素的位置关系和视觉特征：

```
# 好的写法
"找到页面上'闪购数据'四个字，紧贴其右侧有一个下拉选择器（当前显示'多级时效小时达和日达测...'），点击它。注意不是页面下方'门店'旁边的那个下拉框。"
```

#### 多步骤任务分阶段编号

```
"1. 找到并点击X下拉框，选择Y选项。
 2. 点击时间维度的'日'按钮，确认日期为昨天。
 3. 等数据加载完成后，记录所有指标并输出。"
```

#### 数据读取任务

列举所有需要读取的指标名称，要求在 finished 结果中输出：

```
"数据加载完成后，仔细阅读所有数据卡片的指标名称和数值（闪购支付金额、成交占比...），在 finished 结果的 content 中完整输出。"
```

#### 下拉列表滚动

某些下拉列表不支持搜索，需明确说明滚动方式：

```
"下拉列表展开后，不要在搜索框中输入（不支持搜索）。在选项列表区域中持续向下滚动，找到'目标选项'并点击。"
```

#### 会议室预订
在预订会议室时，如果出现多个格子，每个格子一般代表半个小时（与下面的数字对应），在任务描述中说明使用drag动作拖选多个格子来确定时间。



### 依赖安装

```bash
pip install requests Pillow python-dotenv loguru
```

browser-use 需单独安装：参见 https://github.com/browser-use/browser-use



## 手机端使用

由于手机虚拟环境暂未接入，该功能暂不支持。