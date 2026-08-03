# QA 自动化流水线模式

从 F88 素材生产测试实践中沉淀的自动化测试工程模式，适用于 pytest + 接口/UI 混合测试场景。

## 测试策略优先级：接口优先，UI 兜底

| 优先级 | 方式 | 适用场景 | 自愈规则 |
|--------|------|----------|----------|
| 1（首选） | 接口验证 | MTOP/HTTP API 功能校验、数据一致性、状态流转、权限控制 | H1-H5 |
| 2（兜底） | UI 验证 | 视觉渲染、复杂前端交互流、前端状态联动、无 API 的纯前端功能 | H1-H9 |

**判定规则**：
- 能用接口断言的（返回码/响应体/DB 状态），**一律走接口**，不启动浏览器
- 仅以下场景走 Playwright UI：页面渲染正确性、前端交互时序（拖拽/动画）、纯前端状态（localStorage 联动）、无后端 API 的纯 UI 功能
- 同一模块混合两种类型时，拆分为 `Test{Module}_API` 和 `Test{Module}_UI`
- UI 用例 docstring 末尾标注 `[UI]`，接收 `page` fixture

**conftest 部署策略**：
- 纯接口项目 → `conftest_self_heal.py`（H1-H5）
- 纯 UI 项目 → `conftest_ui_self_heal.py`（H1-H9）
- 混合项目 → `conftest_ui_self_heal.py`（全量规则，接口用例无 `page` fixture 自动跳过 UI 自愈）

## 自愈规则 H1-H9

通过 pytest `pytest_runtest_makereport` hookwrapper 实时拦截失败，匹配规则后当场重试。

### H1-H5：通用规则（接口 + UI）

| ID | 名称 | 匹配模式 | 等待 | 最大重试 | 说明 |
|----|------|---------|------|---------|------|
| H1 | 429限流 | `429`, `Too Many Requests`, `限流`, `rate.?limit` | 5s | 2 | 限流后等待重试 |
| H2 | 超时 | `timeout`, `Timeout`, `超时`, `Read timed out` | 3s | 1 | 网络或服务端慢 |
| H3 | 数据未就绪 | `数据未就绪`, `not ready`, `pending`, `处理中` | 10s | 2 | 异步数据延迟 |
| H4 | 环境抖动 | `ECONNRESET`, `Network is unreachable`, `502`, `503` | 3s | 2 | 瞬时网络问题 |
| H5 | 脚本问题 | `ImportError`, `ModuleNotFoundError`, `fixture not found`, `SyntaxError` | 0 | 0 | 不重试，标记 SCRIPT_FIX |

### H6-H9：UI 专属规则（需 `page` fixture）

| ID | 名称 | 匹配模式 | UI 恢复动作 | 最大重试 |
|----|------|---------|------------|---------|
| H6 | 元素漂移 | `element not found`, `locator`, `not visible`, `strict mode violation` | `page.reload()` + `scrollIntoView` | 2 |
| H7 | 焦点抢占 | `intercepts pointer events`, `element is not clickable`, `overlapping element` | 移除遮挡层 + `SELF_HEAL_FORCE=1` 环境变量 | 1 |
| H8 | 弹窗遮挡 | `dialog`, `modal`, `overlay`, `beforeunload` | `dialog.accept()` + 移除 DOM 弹窗 | 1 |
| H9 | 页面未稳定 | `animating`, `still loading`, `networkidle` | `wait_for_load_state("networkidle")` + 等待 CSS 动画结束 | 1 |

### 技术实现要点

```python
# hookwrapper 模式：拦截 call 阶段失败
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    # 匹配规则 → 等待 → UI恢复 → item.runtest() 重试
    # 用 TestReport.from_item_and_call() 构造重试报告
    # outcome.force_result(retry_report) 替换原始结果
```

**关键陷阱**：
- **不用 `runtestprotocol()`**：它会跑 setup/teardown，第二次调用时 `caplog_records_key` 已被删除导致 KeyError
- **用 `item.runtest()`**：只跑测试函数本身，不触发 setup/teardown
- **构造 CallInfo**：`CallInfo(result=None, excinfo=excinfo, start=start, stop=stop, duration=duration, when="call", _ispytest=True)`
- **构造 TestReport**：`TestReport.from_item_and_call(item, retry_call_info)`，不要用 `from_item_and_test_outcome`（不存在）
- **重试后清理**：`os.environ.pop("SELF_HEAL_FORCE", None)` 防止污染后续用例
- **H6 选择器提取**：从 Playwright 错误信息中解析 selector（`locator('#xxx')` 格式），仅对 CSS selector 做 scrollIntoView，xpath= / text= 格式跳过

## 失败分类体系（先修再报）

### 核心准则

**是否有可自行处理的解决方案** —— 不依赖工程配合、不依赖外部系统变更、不需要他人协助，自己就能修 + 重新验证。

### 五类分类

| 分类 | 含义 | 判断依据 | 后续动作 |
|------|------|---------|---------|
| SELF_HEAL | 可自愈 | 有自足方案（重试/等待/调参/刷新数据），不依赖他人 | 重试（最多 2 轮） |
| SCRIPT_FIX | 脚本问题 | 测试脚本本身有错（import/fixture/语法），自己能改 | 修复脚本后重跑 |
| BUG | 真实缺陷 | 需要后端修代码 / 前端改逻辑 / 他人配合才能解决 | 上报后提 Bug |
| SKIP | 环境/已知问题 | 已确认非 Bug 或超出测试范围 | 跳过 |
| UNKNOWN | 无法判定 | 信息不足以判断 | 人工判断 |

### 关键区分（同样的表象，不同的分类）

- **超时** → 加大 timeout 参数能解决 = SELF_HEAL；后端服务慢需工程优化 = BUG
- **数据异常** → 重新造数据能解决 = SELF_HEAL；数据被其他系统锁定无法重置 = BUG
- **429 限流** → 等待后重试能通过 = SELF_HEAL；持续性限流需后端调整配额 = BUG

## Bug 草稿分类 R1-R6

自愈循环结束后，仅对分类为 BUG 且最终仍 FAIL 的用例生成草稿：

| 规则 | 名称 | 匹配条件 | 置信度 |
|------|------|---------|--------|
| R1 | 校验缺失 | `断言失败`, `assert`, `校验`, `不匹配`, `expected` | 高 |
| R2 | 接口异常 | `500`, `Internal Server Error`, `服务异常`, `exception` | 高 |
| R3 | 数据不一致 | `数据不一致`, `data mismatch`, `状态不对`, `字段缺失` | 中 |
| R4 | 环境问题 | `环境`, `配置`, `网络`, `connection`, `timeout` | 低 |
| R5 | 已知问题 | 匹配 `patterns/known-issues.md` 中的已知模式 | 跳过 |
| R6 | 无法判定 | 以上均未匹配 | 低 |

## 全流程编排（10 阶段闭环）

```
PRD读取 → 用例设计 → 脚本生成 → 自愈执行 → 失败分析 → 自愈重试
                                                              ↓
报告更新 ← 结果合并 ← 脚本修复 ←──────────────────── 三层分类
    ↓
证据上报 → Bug草稿 → 缺陷提报
```

**各阶段调用的组件 Skill**：
- Stage 0-2：`PRD用例生成`（读 PRD → 设计用例 → 生成 pytest）
- Stage 3：`PRD用例生成` 的 conftest 部署 + pytest 执行
- Stage 4-6：`f88-bug-drafter`（分析 → 重试 → 合并）
- Stage 8：`att-report`（证据上报）
- Stage 9-10：`f88-bug-drafter` + `aone-bug-submit`（草稿 → 提报）

### 5-Stage Test Resilience Pipeline（底层韧性管线）

在上述 10 阶段闭环之下，harness-runner 运行时会插入一条 5 阶段韧性管线，由三个专项 Skill 实现：

| Stage | 名称 | 管辖 Skill | 职责 |
|-------|------|-----------|------|
| 0 | 数据就绪检查 | qa-data-preflight | 扫描用例数据需求，对比环境现状，输出 DataGap |
| 1 | 造数自愈 | qa-data-preflight | 调用造数 Skill 填补缺口，填不了标记 BLOCKED_DATA |
| 2 | 测试执行 | qa-self-healing | 七步诊断 + 三层降级 + conftest 自愈 |
| 3 | 归因报告 | f88-failure-analysis | SQL 深度归因 + BLOCKED 子分类 |
| 4 | 自愈流程验证 | qa-self-healing | 故意制造故障 → 七步诊断 → 修复 → 重触发验证 |

**Pipeline 验证结论（2026-07-29 全链路验证）**：

BT_7340（有 preflight）vs BT_7350（跳过 preflight，空输入）对比证明：**预防性造数（Stage 0→1）远优于事后自愈**。BT_7340 在 Stage 0 检测到数据缺口后由 Stage 1 自动补齐模板包，1 秒到达审核节点、0 失败；BT_7350 因空输入卡死 PROCESSING、0 条 workflow 记录，需七步诊断 + 修复批次才能恢复。

**关键教训**：空字符串输入比非法值更危险——API 返回 success 但数据流静默中断，无报错、无日志、无 workflow 记录。

## 执行红线

1. **接口优先**：能用 API/DB 断言的一律走接口
2. **先修再报**：可自愈的先重试，修复不了的才上报
3. **不自动提 Bug**：草稿必须用户确认才提交
4. **数据安全**：不在线上环境执行写操作
5. **HSF 调用需确认**：任何 HSF 接口调用前必须先找用户确认
