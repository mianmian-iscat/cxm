<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护缺陷排查/references/Aone缺陷上报.md -->
<!-- synced-at: 2026-07-11T03:52:35.003088 -->
<!-- skill: 原创保护缺陷排查 -->

# 原创保护-Aone缺陷上报指南

## Aone 项目信息

- **项目名**：淘天服饰原创保护
- **项目 ID**：（首次使用时通过 `a1 project list --keyword 原创保护` 查询并填入此处）
- **缺陷模板**：参考 F88（type=515）和大淘宝缺陷模版（type=2099106）选择，原创保护项目首次提单时确认实际 type
- **必填字段**：依据项目模板，常见有：
  - cfs 141538：关联需求（必填，需求 ID 来自 a1）
  - cfs 47：发现阶段（自测/集成测试/UAT/灰度/线上）
  - verifier：验证人花名

## CLI 命令模板

### 查需求
```bash
a1 project workitem get <需求ID> -f json
# 注意：需求/Bug 正文（描述）在顶层 description 字段，不在 fields 数组（已沉淀 MEMORY）
```

### 创建缺陷
```bash
a1 project workitem create \
  --project <项目ID> \
  --type <type-id> \
  --title "<标题>" \
  --description-file ./bug-detail.md \
  --cfs 141538=<需求ID> \
  --cfs 47=<发现阶段值> \
  --verifier <花名> \
  --severity <P0|P1|P2|P3> \
  --priority <high|medium|low>
```

### 关联需求（不可用 --relation parent）
- 已沉淀 MEMORY：F88 项目 2120437 中 --relation parent 不可用，改用 cfs 141538
- 原创保护项目首次提单时验证 --relation parent 是否可用，否则用 cfs

---

## 缺陷模板（粘贴到 description-file）

```markdown
## 现象
{一句话描述异常}

## 复现步骤
1. {环境} 登录商家身份 {test_account}
2. {操作} 进入 /patent/apply，选择"快审"模式
3. {操作} 上传 1 张图片（少于 3 张）
4. {操作} 点击提交

## 预期 vs 实际
- 预期：前端阻塞提示"至少上传 3 张图片"
- 实际：提交成功，进入 pending 状态

## 影响
- 影响范围：所有快审申请商家
- 影响业务：违规申请进入审核队列，浪费小二审核工时
- 严重程度：P1（数据不规范但可被小二驳回）

## 关键证据
- traceId: <鹰眼traceId>
- DB 数据：yc_right_apply.id=12345，应不存在
- API 请求/响应：见附件 request.json / response.json
- 截图：bug-screenshot.png

## 复现率
- 必现 / 偶现（X/10）

## 测试环境
- 预发环境：pre-fsyc.alibaba-inc.com
- 千牛白名单：TTYCBH
- 测试账号：isv项目测试专用

## 根因（如已定位）
{推断的根因，引用代码位置}
- 代码位置：industry-source-code/original-protection/src/pages/PatentApply/index.tsx:line 142
- 缺失：fastReview 模式的图片数量校验
```

---

## 严重程度判断

| 级别 | 判定 | 示例 |
|------|------|------|
| P0 | 阻塞主流程 / 资损风险 | 结算金额错算、维权下架失败、千牛白名单失效 |
| P1 | 关键功能数据不准 / 状态机异常 | 首发标到期未摘、补贴档位错算 |
| P2 | 体验问题 / 边界场景 | Tooltip 错位、文案不一致 |
| P3 | 优化建议 / 易用性 | 列宽不合理、提示文案不够友好 |

---

## 验证人选择

- **业务测试问题**：选业务对接的产品/开发花名
- **底层接口问题**：选服务端开发花名
- **前端组件问题**：选前端开发花名
- 通过 `a1 project member list` 查项目成员

---

## 提单后跟进

1. **每日跟进**：列表过滤 status=待处理 + verifier=自己 → 催办
2. **复现验证**：开发 fix 后切到 dev/test 环境复现验证
3. **回归测试**：合入预发后跑回归用例集
4. **关闭单据**：验证通过后 `a1 project workitem update <id> --status closed`

---

## 批量操作

```bash
# 列出当前迭代所有缺陷
a1 project workitem list \
  --project <PID> \
  --type <BUG_TYPE> \
  --filter "iteration=<迭代ID>" \
  -f json

# 按严重程度过滤
| jq '.workitems[] | select(.severity=="P0")'

# 检查 P0 是否有遗留
| jq '.workitems[] | select(.severity=="P0" and .status!="closed")'
```

---

## 集成至质量月报

参考 F88 经验：AOne 质量报告 KindEditor 内容设 `iframe.body.innerHTML`，标题 id=dailyReportName，开发=参与者-测试-产品（去重仅名字），用例评审人=测试人员，bug 空间=缺陷页链接。保存按钮可能不可见先 scrollIntoView；成功标志 URL 由 #finalReport/new 变为 #finalReport/detail/{id}。导航离开会重置表单。
