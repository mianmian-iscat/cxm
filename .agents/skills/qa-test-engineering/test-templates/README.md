# 测试脚本模板库

> Agent 生成测试脚本时从模板库选取，而非从零编写。确保脚本质量一致性。

## 目录结构

### api-assertion/ — API 断言模板
- `status-code-response-body.md` — 标准 API 断言（状态码 + 响应体字段校验 + DB 交叉验证）
- `async-callback.md` — 异步回调类 API 断言（提交 → 轮询 → 超时处理）

### browser-automation/ — 浏览器操作模板
- `navigate-fill-submit.md` — 标准导航→填写→提交→截图流程
- `spa-state-preservation.md` — SPA 状态保持（resize 后重新导航、CDP 设备模拟）
- `modal-interaction.md` — Modal/弹窗交互（刷新关闭、CDP 直接触发）

### data-setup/ — 造数模板
- `strategy-test-run.md` — 策略试运行造数（固定模板 + BT 批次产出）
- `manual-api-create.md` — 手动 API 创建（formal 语义验证）
- `browser-automation-create.md` — 浏览器自动化造数（模板包等无 API 场景）

### verification/ — 验证模板
- `four-chain-evidence.md` — 四链证据采集（UI 操作 + UI 截图 + API 验证 + DB 核对）
- `db-cross-validation.md` — DB 交叉验证（多表 JOIN + 字段对比）
- `post-verify-three-layer.md` — 后置验证三层（结构 + 语义 + 消费端可用性）

## 使用方式

Agent 生成测试脚本时：
1. 识别场景属于哪个模板类别
2. 读取对应模板文件获取标准结构
3. 基于模板填充具体参数（URL/字段/断言条件）
4. 不从零编写，确保关键步骤不遗漏
