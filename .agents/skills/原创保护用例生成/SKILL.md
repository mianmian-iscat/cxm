---
name: 原创保护用例生成
description: 淘天服饰原创保护平台测试用例生成器。输入 PRD / 需求文档 / 技术方案 / 口头变更点，输出 XMind 结构化用例大纲 + pytest 可执行脚本。覆盖入驻、快审 QUICK、初审 PRE、普通 REGULAR、商品绑定、首发标、保护期、维权、结算/退款/确收全链路。触发词：原创保护用例、yc用例、生成原创保护测试用例、原创保护测试大纲、XMind用例、原创保护pytest。
version: 1.0.0
---

# 原创保护用例生成

输入 PRD / 需求文档 / 技术方案 / 口头变更点，生成覆盖原创保护全生命周期的测试用例。

## 输入处理

支持以下输入形式：
- 钉钉文档 / 语雀 / 本地 Markdown 路径
- PRD 文字片段或图片
- 口头变更点（用户逐条描述）
- AOne 需求链接（提取需求正文）

读取输入后，先提取以下信息：
1. 需求范围：涉及哪些业务域（入驻 / QUICK / PRE / REGULAR / 商品绑定 / 首发标 / 保护期 / 维权 / 结算）
2. 变更类型：新增字段、状态机调整、接口改动、规则变更、UI 改动、定时任务、结算逻辑
3. 关联方：是否影响 HSF Tool 造数、ScheduleX 任务、MTOP 接口、DB 状态机
4. 测试限制：预发/生产隔离、是否需要 TTYCBH 千牛标、是否需要 PRE 充值

## 输出物

1. **XMind 结构化用例大纲**（Markdown 表格形式，可直接导入 XMind）
2. **pytest 可执行脚本**：`test_yc_*.py`，可直接被 pytest 执行
3. **数据构造清单**：每条用例需要的 applyId、rightId、sellerId、前置状态
4. **验证 SQL 清单**：基于 `yc-db-verification` 的查询模板编号

## 业务域覆盖矩阵

生成用例时，按需求范围选择业务域组合：

| 业务域 | 关键状态/节点 | 典型验证点 |
|--------|--------------|-----------|
| 入驻 | TTYCBH 千牛标、SellerEnterToolService.enter | 未打标拦截、打标后入驻、幂等入驻 |
| 快审 QUICK | QUICK_AUDITING → QUICK_AUDITED | 提交不扣减、状态机、OCR/图片校验 |
| 初审 PRE | PRE_AUDITING → PRE_AUDITED | 服务次数扣减、充值、驳回/通过 |
| 普通 REGULAR | 转普通 to_regular_status | 旧结算单 CANCEL、新单 PROCESSING |
| 商品绑定 | bindItem、SYNC_CERT_FILE | 绑定/解绑、类目快照、首发编辑权限 |
| 首发标 | first_publish、9 类白名单 | 编辑权限、补贴触发、类目校验 |
| 保护期 | protect_expire_time、YC_PROTECT_INVALID | 20 天禁发、到期失效、线索提交限制 |
| 维权 | yc_tort_record、autoProtectForManual | 侵权记录生成、下架率计算、保护成功 |
| 结算/退款/确收 | settle_status、serv_finish_refund_status、serv_finish_income_status | 4 个 ScheduleX Job、70% 下架率分流 |

## 用例结构模板

每条用例统一采用 **四段式结构**：

```
操作 → 即时验证 → 等待 → 阶段验证
```

| 阶段 | 说明 | 常用断言 |
|------|------|---------|
| 操作 | API 调用 / HSF Tool / UI 操作 / 定时任务触发 | HTTP 200 / HSF 返回 success / 页面元素可见 |
| 即时验证 | 操作完成后立即检查可见状态 | 申请状态、结算单状态、操作流水 |
| 等待 | 异步链路等待：MetaQ 消费 / ScheduleX 执行 / 定时 Job | 记录等待原因和最长等待时间 |
| 阶段验证 | 异步完成后检查最终一致性 | DB 状态、资金流向、下游消息、UI 展示 |

## XMind 用例大纲模板

```markdown
# 原创保护 - <需求名称>

## 1. 入驻
### 1.1 正常流程
- YC-001 已打标 TTYCBH 商家入驻成功
- YC-002 未打标商家收到拦截提示
### 1.2 异常流程
- YC-003 重复入驻幂等处理

## 2. 快审 QUICK
### 2.1 提交
- YC-010 快审提交不扣减服务次数
- YC-011 图片不符合规范被驳回
### 2.2 审核
- YC-020 快审通过状态变为 QUICK_AUDITED
- YC-021 快审驳回后申诉入口打开

## 3. 初审 PRE
...

## 9. 结算/退款/确收
### 9.1 补贴
- YC-090 9 类商家 SYNC_CERT_FILE 后触发补贴
- YC-091 非 9 类商家不触发补贴
### 9.2 到期结算
- YC-100 保护到期 + 下架率 < 70% 走退款
- YC-101 保护到期 + 下架率 ≥ 70% 走确收
```

## pytest 脚本模板

```python
import pytest
from datetime import datetime, timedelta

class TestYcXXX:
    """<需求名称> - <业务域>"""

    @pytest.fixture(scope="class")
    def seller_id(self):
        return 2213249110271

    def test_yc_xxx_正常路径(self, seller_id):
        # 1. 操作
        apply_id = create_quick_apply(seller_id)
        hsf_update_status(apply_id, "QUICK_AUDITED")

        # 2. 即时验证
        assert get_apply_status(apply_id) == "QUICK_AUDITED"
        assert op_record_exists(apply_id, "QUICK_AUDIT_AGREE")

        # 3. 等待（异步：绑定商品 + SYNC_CERT_FILE）
        bind_item(apply_id, item_id=12345)
        wait_for_sync_cert_file(apply_id, timeout=120)

        # 4. 阶段验证
        assert get_right_status(apply_id) == "YC_PROTECTING"
        assert get_settle_status(apply_id) == "PROCESSING"
```

## 安全与数据约束

- 所有 DB 验证 SQL 必须带 `env = 'staging'` 过滤
- HSF Tool 写操作前必须执行 `SELECT id, env FROM yc_right_apply WHERE id = {applyId}` 预检
- 生产数据（env='production'）只读，禁止写操作
- 默认测试 seller_id 见 `yc-protection-qa-workbench/test-accounts.md`

## 自检清单（生成后必须逐项确认）

生成用例后，对每条用例执行以下自检：

- [ ] **waiting**：是否明确标注等待原因、等待对象、最长等待时间？异步链路禁止省略等待阶段。
- [ ] **bloodline**：用例的数据血缘是否清晰？applyId / rightId / settleId 如何构造、如何传递、如何清理？
- [ ] **triple-check**：关键状态变更是否有三层验证？即时验证 + DB 验证 + 操作流水验证。
- [ ] **immediate verification**：操作后是否立即断言可见结果？禁止只写操作不写断言。
- [ ] **domain coverage**：需求涉及的每个业务域是否至少有一条正例和一条反例？
- [ ] **state machine**：状态跳转是否符合状态机定义？非法跳转是否作为异常用例覆盖？
- [ ] **settlement branch**：结算相关需求是否同时覆盖退款路径和确收路径？
- [ ] **env isolation**：脚本中是否硬编码了生产 applyId / sellerId？是否使用 staging 数据？

## att-tf case.json 字段映射

生成 pytest 脚本时，同时输出对应 `cases.json` 结构供 `att-report` 上报：

```json
{
  "caseTitle": "YC-001 已打标 TTYCBH 商家入驻成功",
  "description": "验证已打标千牛标的测试商家可正常完成原创保护入驻",
  "status": 1,
  "priority": "P1",
  "groupPath": "原创保护/入驻/正常流程",
  "errorMessage": "",
  "execLog": "applyId=200001234, sellerId=2213249110271, 入驻耗时 2.3s"
}
```

字段映射说明：

| cases.json 字段 | 来源 | 说明 |
|----------------|------|------|
| caseTitle | XMind 用例编号 + 标题 | 必须保留原用例标题，不可改写为执行总结 |
| description | 用例前置条件 + 预期结果 | 沿用生成时的描述 |
| status | 执行结果 | 1=通过，2=失败，3=跳过 |
| priority | P0/P1/P2/P3 | 核心状态机 P0，结算分支 P0，异常边界 P1 |
| groupPath | XMind 路径 | 用 `业务域/模块/场景` 三级结构 |
| errorMessage | 失败原因 | 失败时填写，通过时为空 |
| execLog | 执行关键信息 | applyId、rightId、耗时、关键断言结果 |

## 工作流

```
1. 读取输入文档 / 变更点
2. 提取需求范围与变更类型
3. 按业务域覆盖矩阵生成 XMind 大纲
4. 为每条用例填充四段式结构
5. 生成 pytest 脚本 + cases.json 草稿
6. 执行自检清单
7. 输出：XMind 大纲 + pytest 脚本 + 数据构造清单 + 验证 SQL 清单
```

## 参考与下游 Skill

- 数据构造：`yc-data-factory`、`yc-quick-audit-data-create`
- DB 验证：`yc-db-verification`
- 结算分析：`yc-settlement-analyser`
- 执行与对抗验证：`原创保护执行助手`、`原创保护规则校验`、`qa-adversarial-agent`
- 报告：`qa-test-report`、`att-report`
- 详细用例示例见 [references/case-templates.md](references/case-templates.md)
