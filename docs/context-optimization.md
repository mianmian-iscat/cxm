# 上下文消耗优化指南

## 🎯 问题背景

web-automation 执行测试用例时，以下内容会快速消耗会话上下文：

| 消耗源 | 量级 | 说明 |
|--------|------|------|
| 截图（Base64） | 2-8 KB/张 → 2000-8000 tokens | 全分辨率 PNG 编码后极大 |
| API 响应体 | 1-50 KB/个 → 1000-10000+ tokens | 完整 JSON 响应体 |
| 步骤详细日志 | 200-500 tokens/步 | 每步的执行细节 |
| 页面探索输出 | 3-15 KB/次 | 新页面首次探索的 DOM 分析 |

**典型场景：** 执行 5 个带截图 + 抓包的用例 → 累积 150K+ tokens → 上下文超限

---

## ✅ 优化方案

### 配置位置

在 `input.json` 中添加 `contextOptimization` 配置：

```json
{
  "id": "my-test-case",
  "name": "我的测试用例",
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 50,
    "outputCompact": true,
    "verboseMode": "summary"
  },
  ...
}
```

---

### 配置项详解

#### 1️⃣ `screenshotExternal`（默认：true）

**作用：** 截图仅保存为文件，output 中只保留路径引用

| 模式 | output 内容 | 上下文消耗 |
|------|------------|-----------|
| `false` | 嵌入 Base64 数据 | 🔴 极高（每张 2000-8000 tokens） |
| `true` | 只保留文件路径 | 🟢 极低（每条 ~50 tokens） |

**示例：**
```json
// 优化前（嵌入 Base64）
"screenshots": [
  { "stepIndex": 0, "data": "iVBORw0KGgoAAAANSUhEUgAA..." }
]

// 优化后（路径引用）
"screenshots": [
  { "stepIndex": 0, "label": "step0-click", "path": "artifacts/xxx/screenshots/step0-click.png" }
]
```

**节省：60-80% 截图消耗**

---

#### 2️⃣ `maxResponseSizeKb`（默认：50）

**作用：** 限制单个 API 响应体保留大小

| 配置 | 行为 |
|------|------|
| `0` | 不限制（保留完整响应体） |
| `50` | 超过 50 KB 截断，保留前 50 KB |
| `10` | 超过 10 KB 截断，保留前 10 KB |

**截断标记：**
```json
{
  "url": "https://example.com/api/data",
  "responseBody": "{...前 50 KB 内容...}",
  "responseBodyTruncated": true,
  "responseBodySizeKb": 245.3
}
```

**完整数据位置：** `artifacts/{run_id}/capture.json`

**节省：50-70% 抓包消耗**

---

#### 3️⃣ `outputCompact`（默认：true）

**作用：** 精简 output.json 内容

**精简策略：**
1. **成功步骤**：只保留核心字段（index, type, status, duration, description）
2. **抓包数据**：只保留前 20 条完整记录，其余只保留摘要
3. **添加提示**：`_contextOptimization` 字段说明完整数据位置

**示例：**
```json
// 优化前（详细步骤）
{
  "index": 0,
  "type": "click",
  "status": "pass",
  "duration": 234,
  "selector": "#search-btn",
  "elementInfo": { "tagName": "BUTTON", "text": "搜索" },
  "logs": ["找到元素", "点击成功", "页面开始加载"]
}

// 优化后（精简步骤）
{
  "index": 0,
  "type": "click",
  "status": "pass",
  "duration": 234,
  "description": "点击搜索按钮"
}
```

**节省：30-50% output 消耗**

---

#### 4️⃣ `verboseMode`（默认：summary）

**作用：** 控制对话输出模式

| 模式 | 输出内容 | 适用场景 |
|------|---------|---------|
| `full` | 完整执行日志 + 截图 + 抓包详情 | 调试单个用例 |
| `summary` | 执行摘要 + 关键结论 + 产物路径 | 日常执行（推荐） |
| `minimal` | 只输出最终结论（✅/❌） | 批量执行 |

**输出示例：**

`summary` 模式：
```
✅ 测试用例通过
- 执行时长：12.3s
- 步骤：8/8 通过
- 截图：3 张（见 artifacts/xxx/screenshots/）
- 抓包：15 个请求（见 artifacts/xxx/capture.json）
```

`minimal` 模式：
```
✅ TC001 通过
```

---

## 📊 优化效果对比

### 场景：执行 10 个中等复杂度用例（每用例 3 截图 + 5 API）

| 配置 | 预估消耗 | 优化后消耗 | 节省 |
|------|---------|-----------|------|
| 无优化 | ~250K tokens | - | - |
| 仅截图外部化 | - | ~100K tokens | 60% |
| + 响应体限制 | - | ~50K tokens | 80% |
| + output 精简 | - | ~35K tokens | 86% |
| + verbose=minimal | - | ~25K tokens | 90% |

---

## 🛠️ 最佳实践

### 1. 日常执行推荐配置

```json
{
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 50,
    "outputCompact": true,
    "verboseMode": "summary"
  },
  "capture": {
    "enabled": true,
    "filter": "/core/api/",  // 只抓核心接口
    "captureBody": true
  },
  "screenshot": {
    "onEachStep": false,  // 不要每步都截图
    "onError": true
  }
}
```

### 2. 调试单个用例（需要详细信息）

```json
{
  "contextOptimization": {
    "screenshotExternal": false,
    "maxResponseSizeKb": 0,
    "outputCompact": false,
    "verboseMode": "full"
  }
}
```

### 3. 批量执行（极致精简）

```json
{
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 10,
    "outputCompact": true,
    "verboseMode": "minimal"
  },
  "screenshot": {
    "onEachStep": false,
    "onError": false  // 失败也不截图，极致精简
  }
}
```

### 4. 长流程用例（配合断点续跑）

```json
{
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 50,
    "outputCompact": true,
    "verboseMode": "summary"
  },
  "checkpoint": {
    "enabled": true,
    "segmentSize": 8,
    "outputSizeLimitKb": 200
  }
}
```

---

## 📁 完整数据访问

优化后，完整数据仍保存在 artifacts 目录：

```
artifacts/{run_id}/
├── input.json           # 原始输入
├── output.json          # 完整输出（未精简前）
├── capture.json         # 完整抓包数据
├── capture.har          # HAR 格式（如开启）
└── screenshots/
    ├── step0-click.png
    ├── step2-assert.png
    └── ...
```

**读取完整数据：**
```bash
# 查看完整 output
cat artifacts/{run_id}/output.json

# 查看完整抓包
cat artifacts/{run_id}/capture.json

# 查看截图
ls artifacts/{run_id}/screenshots/
```

---

## ⚠️ 注意事项

1. **精简模式不影响产物文件**：`outputCompact=true` 只精简返回给对话的 output，artifacts 中的文件仍是完整版

2. **响应体截断可能影响断言**：如果断言依赖大响应体的后半部分，需调大 `maxResponseSizeKb` 或关闭限制

3. **断点续跑与优化配置**：checkpoint 保存的是完整状态，续跑时自动继承优化配置

4. **knowledge 更新不受影响**：页面知识库更新基于实际执行结果，与优化配置无关

---

## 🔧 快速开始

复制以下模板到你的 input.json：

```json
{
  "id": "quick-start",
  "name": "快速开始示例",
  "context": {
    "urlPattern": "example.alibaba-inc.com"
  },
  "steps": [
    { "type": "navigate", "url": "https://example.alibaba-inc.com" },
    { "type": "click", "text": "搜索", "screenshot": true }
  ],
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 50,
    "outputCompact": true,
    "verboseMode": "summary"
  },
  "capture": {
    "enabled": true,
    "filter": "/api/"
  }
}
```

执行：
```bash
python impl.py quick-start.json
```

---

## 📈 监控建议

定期检查 artifacts 目录大小，清理过期产物：

```bash
# 查看 artifacts 总大小
du -sh artifacts/

# 清理 7 天前的产物
python -c "from core.artifact_manager import ArtifactManager; ArtifactManager.cleanup_old_runs(retention_days=7)"
```

---

**总结：** 合理配置优化选项，可在不影响调试能力的前提下，**节省 80-90% 上下文消耗**，让单个会话能执行更多测试用例。
