# 上下文优化速查表 🚀

## 📌 一句话推荐

**默认开启优化配置，单会话可执行 10 倍更多用例！**

---

## ⚡ 复制即用

```json
{
  "contextOptimization": {
    "screenshotExternal": true,
    "maxResponseSizeKb": 50,
    "outputCompact": true,
    "verboseMode": "summary"
  }
}
```

---

## 📊 配置项速查

| 配置 | 默认 | 推荐值 | 作用 | 节省 |
|------|------|--------|------|------|
| `screenshotExternal` | true | true | 截图只存路径，不嵌入 Base64 | 60-80% |
| `maxResponseSizeKb` | 50 | 50 | 响应体超过 50KB 截断 | 50-70% |
| `outputCompact` | true | true | 精简 output.json | 30-50% |
| `verboseMode` | summary | summary | 对话输出摘要 | 40-60% |

---

## 🎯 场景配置

### 日常执行（推荐）
```json
{"contextOptimization": {
  "screenshotExternal": true,
  "maxResponseSizeKb": 50,
  "outputCompact": true,
  "verboseMode": "summary"
}}
```

### 调试模式
```json
{"contextOptimization": {
  "screenshotExternal": false,
  "maxResponseSizeKb": 0,
  "outputCompact": false,
  "verboseMode": "full"
}}
```

### 批量执行
```json
{"contextOptimization": {
  "screenshotExternal": true,
  "maxResponseSizeKb": 10,
  "outputCompact": true,
  "verboseMode": "minimal"
}}
```

### 长流程 + 断点
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

## 📈 效果对比

### 单用例（9 步骤，4 截图，15 API）

| 配置 | tokens |
|------|--------|
| ❌ 无优化 | ~42,000 |
| ✅ 优化后 | ~4,500 |
| 💪 优化 + minimal | ~1,500 |

### 单会话可执行用例数

| 配置 | 用例数 |
|------|--------|
| ❌ 无优化 | 2-3 个 |
| ✅ 优化后 | 20-25 个 |
| 💪 优化 + minimal | 50+ 个 |

---

## 🔍 字段说明

### `screenshotExternal: true`
- ✅ output 中只保留路径：`"path": "artifacts/xxx/step0.png"`
- ❌ 不嵌入 Base64：`"data": "iVBORw0KGgoAAA..."`
- 📁 完整截图仍在 `artifacts/xxx/screenshots/`

### `maxResponseSizeKb: 50`
- ✅ 超过 50 KB 自动截断
- 🏷️ 添加标记：`responseBodyTruncated: true`
- 📊 记录原始大小：`responseBodySizeKb: 245.3`
- 📁 完整数据仍在 `artifacts/xxx/capture.json`

### `outputCompact: true`
- ✅ 成功步骤只保留核心字段
- ✅ 抓包只保留前 20 条完整记录
- 📝 添加优化标记：`_contextOptimization`

### `verboseMode`
| 值 | 输出内容 | 适用场景 |
|----|---------|---------|
| `full` | 完整日志 + 截图 + 抓包 | 调试 |
| `summary` | 摘要 + 产物路径 | 日常 ✅ |
| `minimal` | 只输出结论（✅/❌） | 批量 |

---

## ⚠️ 何时关闭优化

- 🔧 调试单个复杂用例
- 📄 需要完整 API 响应体做断言
- 🖼️ 需要 Base64 截图嵌入报告
- 🔄 一次性执行，不关心上下文

---

## 📁 完整数据位置

优化后，完整数据仍在：

```
artifacts/{run_id}/
├── output.json      ← 完整版（未精简前）
├── capture.json     ← 完整抓包
└── screenshots/     ← 所有截图
```

**读取完整 output：**
```bash
cat artifacts/{run_id}/output.json | jq .
```

---

## 💡 最佳实践

1. ✅ **默认开启优化** — 节省 80-90% tokens
2. 📸 **关键步骤才截图** — 不要每步都截图
3. 🎯 **优先 text 定位** — 比 selector 稳定
4. ⏱️ **使用 waitForAPI** — 比固定等待可靠
5. 🔄 **长流程开 checkpoint** — 避免从头开始

---

## 📖 详细文档

- [context-optimization.md](context-optimization.md) — 完整指南
- [optimization-comparison.md](optimization-comparison.md) — 效果对比
- [quickstart.md](quickstart.md) — 快速开始

---

**总结：** 复制顶部配置，粘贴到你的 input.json，立省 80-90% 上下文！🎉
