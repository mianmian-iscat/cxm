# 上下文优化效果对比

## 测试用例：日销价调价流程（9 个步骤）

| 项目 | 数值 |
|------|------|
| 步骤数 | 9 |
| 截图数 | 4 张 |
| API 抓包 | 15 个请求 |
| 执行时长 | ~12 秒 |

---

## 📊 消耗对比

### 无优化配置

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

**output.json 大小：** ~185 KB  
**预估 tokens：** ~42,000 tokens

**详细构成：**
| 项目 | 大小 | tokens |
|------|------|--------|
| steps[]（详细日志） | 12 KB | ~3,000 |
| screenshots[]（Base64） | 95 KB | ~28,000 |
| capture[].responseBody | 68 KB | ~10,000 |
| 其他（metadata 等） | 10 KB | ~1,000 |

---

### 优化配置（推荐）

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

**output.json 大小：** ~18 KB  
**预估 tokens：** ~4,500 tokens

**详细构成：**
| 项目 | 大小 | tokens |
|------|------|--------|
| steps[]（精简后） | 2 KB | ~500 |
| screenshots[]（路径） | 0.5 KB | ~150 |
| capture[]（前 20 条 + 截断） | 14 KB | ~3,500 |
| 其他（metadata 等） | 1.5 KB | ~350 |

---

## 🎯 优化效果

| 指标 | 无优化 | 优化后 | 节省 |
|------|--------|--------|------|
| output.json 大小 | 185 KB | 18 KB | **90%** |
| 预估 tokens | 42,000 | 4,500 | **89%** |
| 可执行用例数（单会话） | ~2-3 个 | ~20-25 个 | **8-10 倍** |

---

## 📁 产物对比

### 无优化
```
output.json (185 KB) ← 包含所有详细数据
artifacts/xxx/
├── input.json
├── output.json (185 KB)
├── capture.json (68 KB)
└── screenshots/ (95 KB)
```

### 优化后
```
output.json (18 KB) ← 精简版，适合对话传递
artifacts/xxx/
├── input.json
├── output.json (185 KB) ← 完整版仍保存在此
├── capture.json (68 KB)
└── screenshots/ (95 KB)
```

**关键：** 优化只影响返回给对话的 output，artifacts 中仍保留完整数据供后续分析！

---

## 💡 对话输出对比

### 无优化（verboseMode: full）
```
执行开始...
[Step 0] navigate → https://xiaoer.alibaba-inc.com/product/list
  - 等待 networkidle...
  - 截图：step0-navigate.png (Base64: iVBORw0KGgoAAA...)
[Step 1] click → 搜索
  - selector: #search-btn
  - element: <button id="search-btn">搜索</button>
  - 截图：step1-click.png (Base64: ...)
[Step 2] waitForAPI → /cobweb/api/product/search
  - 等待中...
  - 响应：{"code":200,"data":{"items":[...500 行...]}}
...
（继续输出 9 个步骤的详细信息）
...
执行完成，总耗时 12.3s
完整 output: {...185 KB JSON...}
```

**对话消耗：** ~45,000 tokens

---

### 优化后（verboseMode: summary）
```
✅ 测试用例通过

📊 执行摘要
- 用例：optimized-example-001
- 时长：12.3s
- 步骤：9/9 通过

📸 截图：4 张
   见：artifacts/optimized-example-001-20260427103000/screenshots/

📡 抓包：15 个请求
   见：artifacts/optimized-example-001-20260427103000/capture.json

📝 完整产物：artifacts/optimized-example-001-20260427103000/
```

**对话消耗：** ~800 tokens

---

## 🚀 批量执行场景

### 场景：执行 20 个用例

| 配置 | 总 tokens | 是否超限 |
|------|-----------|----------|
| 无优化 | 20 × 42,000 = 840,000 | ❌ 严重超限 |
| 优化后 | 20 × 4,500 = 90,000 | ✅ 可接受 |
| 优化 + minimal | 20 × 1,500 = 30,000 | ✅ 极佳 |

---

## ⚠️ 何时不使用优化

以下场景建议使用无优化配置：

1. **调试单个复杂用例**：需要完整日志定位问题
2. **API 响应体很大但需要全量断言**：`maxResponseSizeKb` 可能截断关键数据
3. **需要 Base64 截图嵌入报告**：某些报告工具需要内嵌图片
4. **单次执行，不关心上下文**：一次性任务，后续不再继续

---

## ✅ 推荐配置速查

### 日常执行
```json
"contextOptimization": {
  "screenshotExternal": true,
  "maxResponseSizeKb": 50,
  "outputCompact": true,
  "verboseMode": "summary"
}
```

### 调试模式
```json
"contextOptimization": {
  "screenshotExternal": false,
  "maxResponseSizeKb": 0,
  "outputCompact": false,
  "verboseMode": "full"
}
```

### 批量执行
```json
"contextOptimization": {
  "screenshotExternal": true,
  "maxResponseSizeKb": 10,
  "outputCompact": true,
  "verboseMode": "minimal"
}
```

---

**结论：** 默认开启优化配置，仅在调试时临时关闭，可在不影响功能的前提下节省 80-90% 上下文。
