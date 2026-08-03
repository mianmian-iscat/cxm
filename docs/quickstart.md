# web-automation 快速开始

## 🎯 5 分钟上手

### 第一步：确认环境

```bash
# 检查 Chrome CDP 是否正常
curl http://127.0.0.1:9222/json/version
```

返回 JSON 即表示环境就绪。

---

### 第二步：创建测试用例

创建 `test.json`：

```json
{
  "id": "my-first-test",
  "name": "我的第一个测试",
  "context": {
    "urlPattern": "example.com"
  },
  "steps": [
    {
      "type": "navigate",
      "url": "https://example.com",
      "waitUntil": "networkidle",
      "description": "打开首页"
    },
    {
      "type": "click",
      "text": "搜索",
      "screenshot": true,
      "description": "点击搜索按钮"
    },
    {
      "type": "assert",
      "target": "page",
      "contains": "搜索结果",
      "description": "验证有搜索结果"
    }
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

---

### 第三步：执行测试

```bash
cd /root/.openclaw/workspace/skills/web-automation
python impl.py test.json
```

---

### 第四步：查看结果

**控制台输出（summary 模式）：**
```
✅ 测试用例通过

📊 执行摘要
- 用例：my-first-test
- 时长：3.2s
- 步骤：3/3 通过

📸 截图：1 张
   见：artifacts/my-first-test-20260427103000/screenshots/

📡 抓包：5 个请求
   见：artifacts/my-first-test-20260427103000/capture.json
```

**产物目录：**
```
artifacts/my-first-test-20260427103000/
├── manifest.json       # 产物清单
├── input.json          # 输入
├── output.json         # 输出（精简版）
├── capture.json        # 抓包数据
└── screenshots/
    └── step1-click.png
```

---

## 📚 Step 类型速查

| 类型 | 说明 | 示例 |
|------|------|------|
| `navigate` | 跳转到 URL | `{"type": "navigate", "url": "https://..."}` |
| `click` | 点击元素 | `{"type": "click", "text": "搜索"}` |
| `fill` | 填写表单 | `{"type": "fill", "selector": "#q", "value": "关键词"}` |
| `wait` | 等待 | `{"type": "wait", "ms": 2000}` |
| `waitForAPI` | 等待接口 | `{"type": "waitForAPI", "urlPattern": "/api/search"}` |
| `screenshot` | 截图 | `{"type": "screenshot", "label": "step1"}` |
| `assert` | 断言 | `{"type": "assert", "target": "page", "contains": "成功"}` |

---

## 🔧 常用配置

### 开启抓包
```json
"capture": {
  "enabled": true,
  "filter": "/api/"  // 只抓含 /api/ 的请求
}
```

### 开启断点续跑（长流程用例）
```json
"checkpoint": {
  "enabled": true,
  "segmentSize": 8  // 每 8 步保存一次
}
```

### 截图策略
```json
"screenshot": {
  "onEachStep": false,  // 不要每步都截图
  "onError": true       // 出错时截图
}
```

---

## ⚠️ 常见问题

### Q: 找不到元素？
**A:** 优先使用 `text` 而非 `selector`，text 更稳定：
```json
// ✅ 推荐
{"type": "click", "text": "搜索"}

// ❌ 不推荐（容易变）
{"type": "click", "selector": "#search-btn.btn-primary"}
```

### Q: 页面还没加载完就执行下一步？
**A:** 增加 `waitAfterLoad` 或使用 `waitForAPI`：
```json
"context": {
  "waitAfterLoad": 3000  // 页面加载后等 3 秒
}
```

### Q: 如何调试失败的用例？
**A:** 关闭优化配置，查看完整日志：
```json
"contextOptimization": {
  "verboseMode": "full"
}
```

### Q: 如何查看完整 output.json？
**A:** 读取 artifacts 中的文件：
```bash
cat artifacts/my-first-test-*/output.json | jq .
```

---

## 📖 下一步

- [上下文优化指南](context-optimization.md) — 节省 80-90% tokens
- [优化效果对比](optimization-comparison.md) — 详细数据对比
- [input.schema.json](../schema/input.schema.json) — 完整字段定义

---

## 💡 最佳实践

1. **默认开启优化配置** — 节省上下文，单会话能执行更多用例
2. **优先使用 text 定位** — 比 selector 更稳定
3. **关键步骤才截图** — 不要每步都截图
4. **使用 waitForAPI** — 比固定等待更可靠
5. **长流程开启 checkpoint** — 避免失败后从头开始
