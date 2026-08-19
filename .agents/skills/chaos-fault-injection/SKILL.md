---
name: chaos-fault-injection
description: 混沌工程与故障注入测试技能。提供系统化的故障注入方法论和实操模式，覆盖 UI/API/服务/数据四层故障模拟，验证系统韧性和容错能力。与 automation-blocker-resolver（UI 层注入）、qa-adversarial-agent（结果验证）协同工作。触发词：混沌工程、故障注入、韧性测试、容错验证、降级演练、断网模拟、超时注入、重试风暴、熔断测试、Chaos Engineering、Fault Injection。
version: 1.0.0
---

# 混沌工程与故障注入测试

通过系统化的故障注入验证系统在异常条件下的韧性。核心思想：主动制造可控故障，观察系统行为，验证容错机制是否按设计工作。

## 安全红线

1. **环境隔离**：故障注入仅限 staging 环境，生产环境只读巡检
2. **爆炸半径**：单次实验只影响一个功能路径，不扩散到无关模块
3. **回滚预案**：每个实验必须有明确的恢复步骤，注入前确认可回滚
4. **超时自动恢复**：所有注入必须设置自动过期时间（默认 5 分钟），防止遗忘清理
5. **状态记录**：注入开始/结束/影响范围全程记录，写入实验报告

## 混沌循环（五步法）

```
1. 定义稳态 → 2. 建立假设 → 3. 设计实验 → 4. 执行注入 → 5. 分析结论
     ↑                                                          |
     └──────────────── 沉淀经验 ←────────────────────────────────┘
```

### Step 1: 定义稳态

明确系统正常状态的可量化指标，作为故障注入后的对比基线。

| 维度 | 稳态指标示例 |
|------|------------|
| 功能 | 核心流程成功率 = 100% |
| 性能 | P99 响应时间 < 2s |
| 数据 | 数据一致性校验通过 |
| 用户体验 | 页面加载完成、无白屏、有降级提示 |

### Step 2: 建立假设

格式："当 [故障X] 发生时，系统应该 [预期行为Y]，因为 [容错机制Z] 会生效。"

示例：
- "当 HSF 下游服务超时 10s 时，系统应该展示降级数据，因为本地缓存兜底机制会生效"
- "当网络断开 30s 后恢复，系统应该自动重试失败请求，因为前端有指数退避重试逻辑"
- "当 DB 连接池耗尽时，新请求应该排队而非报错，因为连接池有等待队列配置"

### Step 3: 设计实验

每个实验必须包含：

```json
{
  "experimentId": "CHAOS-001",
  "hypothesis": "当 API 返回 500 时，前端展示友好错误提示",
  "faultLayer": "API",
  "faultType": "server_error",
  "target": "**/api/material/generate**",
  "injectionMethod": "page.route() 拦截返回 500",
  "duration": "60s",
  "steadyStateMetric": "页面展示错误提示 + 不白屏 + 控制台无未捕获异常",
  "rollbackMethod": "page.unroute() 清除拦截",
  "expectedBehavior": "展示'服务暂时不可用'提示，30s 后自动重试",
  "actualBehavior": null,
  "verdict": null
}
```

## 四层故障注入模式

### Layer 1: UI 层（浏览器 DevTools / Playwright）

最安全的注入层，只影响前端，不动后端服务。

| 故障类型 | 注入方式 | 验证目标 |
|---------|---------|---------|
| 网络超时 | `page.route(url, r => setTimeout(() => r.continue(), 30000))` | 加载态展示、超时提示 |
| API 500 | `page.route(url, r => r.fulfill({status: 500, body: errorJson}))` | 错误提示、降级 UI |
| 断网 | `page.route('**/api/**', r => r.abort('failed'))` | 离线提示、缓存兜底 |
| 慢网络 | CDP `Network.emulateNetworkConditions` | 加载态、骨架屏、进度条 |
| 资源加载失败 | `page.route('**/*.png', r => r.abort())` | 默认图、占位符 |
| JS 异常 | `page.evaluate(() => throw new Error('chaos'))` | 错误边界、降级渲染 |
| Cookie 失效 | `context.clearCookies()` | 重新登录、会话恢复 |

**CDP 慢网络模拟（精确控制）：**
```javascript
// 通过 CDP 模拟 3G 网络
await page.context().route('**/*', async route => {
  await route.continue();
});
const client = await page.context().newCDPSession(page);
await client.send('Network.emulateNetworkConditions', {
  offline: false,
  latency: 200,      // ms
  downloadThroughput: 780 * 1024,  // 780 KB/s
  uploadThroughput: 330 * 1024,    // 330 KB/s
});
```

**代码参考：** `automation-blocker-resolver` Layer 3 Mock/Network Interception 章节有完整的 Playwright/Cypress/Selenium 代码模式。

### Layer 2: API 层（请求/响应篡改）

在 API 网关或代理层注入异常。

| 故障类型 | 注入方式 | 验证目标 |
|---------|---------|---------|
| 响应延迟 | 代理层 addHeader `X-Delay: 5000` | 超时处理、重试逻辑 |
| 响应篡改 | 代理修改 response body 字段为 null/空 | 空值防御、默认值兜底 |
| 状态码异常 | 返回 429/502/503/504 | 重试策略、退避算法 |
| 认证失效 | 清除/篡改 token | 重新认证、会话恢复 |
| 响应截断 | 返回不完整的 JSON | 解析容错、部分渲染 |
| 重复提交 | 同一请求发送两次 | 幂等性、去重逻辑 |

**`injectFailureOnNthCall()` 模式：**
```javascript
let callCount = 0;
async function injectFailureOnNthCall(url, failAtCall, failureType = '500') {
  await page.route(url, async route => {
    callCount++;
    if (callCount === failAtCall) {
      if (failureType === '500') {
        await route.fulfill({ status: 500, body: '{"error":"injected"}' });
      } else if (failureType === 'timeout') {
        await new Promise(r => setTimeout(r, 30000));
        await route.continue();
      } else if (failureType === 'disconnect') {
        await route.abort('failed');
      }
    } else {
      await route.continue();
    }
  });
}
// 用法：第 3 次调用返回 500，验证重试是否成功
await injectFailureOnNthCall('**/api/generate**', 3, '500');
```

### Layer 3: 服务层（HSF/Dubbo 模拟）

适用于微服务间调用的故障模拟。需要后端配合或使用 Mock 平台。

| 故障类型 | 注入方式 | 验证目标 |
|---------|---------|---------|
| 服务超时 | HSF Mock 平台配置延迟 | 超时降级、缓存兜底 |
| 服务不可用 | 关闭某个 provider 实例 | 服务发现切换、failover |
| 返回异常 | Mock 平台配置异常响应 | 异常处理、错误传播 |
| 线程池满 | 配置 provider 线程池大小为 1 | 排队等待、拒绝策略 |
| 序列化失败 | 返回不兼容的数据格式 | 反序列化容错 |

**F88 场景常用 HSF 故障点：**
- stylespot 素材生成服务超时 → 验证前端轮询+降级
- 模板匹配服务返回空 → 验证默认模板兜底
- 审核服务不可用 → 验证任务队列堆积+恢复

### Layer 4: 数据层（DB/缓存异常）

最危险的注入层，必须谨慎操作。

| 故障类型 | 注入方式 | 验证目标 |
|---------|---------|---------|
| 慢查询 | 添加无索引的 WHERE 条件 | 查询超时处理、缓存命中 |
| 连接池耗尽 | 并发占满连接 | 排队等待、降级读取 |
| 数据不一致 | 主从延迟模拟 | 读写分离容错 |
| 缓存失效 | 清除 Redis 指定 key | 缓存穿透保护、DB 回源 |
| 数据为空 | 查询不存在的 ID | 空结果处理、404 页面 |

**安全约束：** 数据层注入优先使用 SELECT 查询验证，禁止在 staging 以外执行任何 DML。

## 韧性模式验证清单

每个容错机制都需要对应的故障注入来验证：

| 韧性模式 | 验证方法 | 通过标准 |
|---------|---------|---------|
| 重试 | 注入第 N 次失败，观察是否重试成功 | 重试次数符合配置，最终成功 |
| 指数退避 | 注入连续失败，测量重试间隔 | 间隔递增（1s→2s→4s） |
| 熔断 | 注入连续失败超过阈值 | 熔断器打开，快速失败而非等待 |
| 降级 | 注入下游不可用 | 展示降级内容而非白屏/报错 |
| 限流 | 并发请求超过限额 | 超限额请求被拒绝或有排队提示 |
| 幂等 | 同一请求重复发送 | 不产生重复数据 |
| 超时 | 注入响应延迟 | 超时后优雅处理，不无限等待 |
| 回滚 | 操作中途失败 | 数据恢复到操作前状态 |
| 缓存兜底 | 清除缓存 + 注入 DB 异常 | 展示缓存数据或友好提示 |

## 与现有技能协同

### 注入执行 → `automation-blocker-resolver`

UI 层的网络拦截代码模式（Playwright page.route / Cypress cy.intercept / Selenium interceptor）参考 `automation-blocker-resolver` Layer 3 章节。本技能提供方法论和实验设计，该技能提供具体代码实现。

### 结果验证 → `qa-adversarial-agent`

故障注入后的结果验证使用 `qa-adversarial-agent` 的五维审计：
- CP1（注入后）：确认故障确实生效（API 确实返回了 500）
- CP2（执行中）：观察系统行为是否符合假设
- CP3（取证前）：四链证据收集（UI 截图 + API 日志 + DB 状态 + 控制台输出）
- CP4（结论前）：独立验证系统确实触发了容错机制

### 用例生成 → `fliggy-tc-generator` / `qa-test-case-gen`

混沌实验的用例可以融入常规测试用例集，在 fliggy-tc-generator 的"异常测试"类别下补充故障注入场景。

## 实验报告模板

```markdown
## 混沌实验报告

- 实验 ID：CHAOS-XXX
- 日期：YYYY-MM-DD
- 环境：staging
- 假设：当 [故障] 发生时，系统应该 [行为]

### 注入详情
- 故障层：UI / API / 服务 / 数据
- 故障类型：[具体类型]
- 注入方法：[代码/配置]
- 持续时间：[X 秒]

### 观察结果
- 稳态指标变化：[对比数据]
- 系统行为：[实际表现]
- 用户可见影响：[有/无]

### 结论
- 假设验证：通过 / 不通过
- 韧性评分：[1-5]
- 发现的问题：[列表]
- 改进建议：[列表]
```

## 决策树

```
需要测试系统韧性吗？
├── 否 → 常规测试流程
└── 是
    ├── 测试哪一层？
    │   ├── UI 层（前端容错）→ Layer 1: Playwright page.route / CDP
    │   ├── API 层（接口容错）→ Layer 2: 代理拦截 / injectFailureOnNthCall
    │   ├── 服务层（微服务容错）→ Layer 3: HSF Mock 平台
    │   └── 数据层（存储容错）→ Layer 4: 慢查询 / 缓存清除
    ├── 验证哪个韧性模式？
    │   ├── 重试/退避 → injectFailureOnNthCall + 观察重试间隔
    │   ├── 降级 → 关闭下游 + 检查降级 UI
    │   ├── 熔断 → 连续失败 + 检查熔断器状态
    │   └── 幂等 → 重复请求 + 检查数据唯一性
    └── 如何验证结果？
        └── qa-adversarial-agent 四链证据 + 五维审计
```
