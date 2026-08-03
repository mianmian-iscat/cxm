<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护用例生成/references/yc-platform-quickref.md -->
<!-- synced-at: 2026-07-11T03:52:35.001152 -->
<!-- skill: 原创保护用例生成 -->

# YC 原创保护平台速查（从 MEMORY 迁移）

> 本文件包含原 MEMORY.md 中 YC 域专属的速查知识。详细的架构/代码/API 文档见同目录下的其他 references 文件。

## 补贴规则

- 补贴以 `init_allowance_start_time` 为准，NOT NULL 则 `init_allowance_amount` 必有
- 资格校验取绑定商品一致时的主营类目，须在 9 类白名单（含 1625 童装）
- 主营变更不影响历史
- 触发须：主营白名单 + first_publish=Y + to_regular_status≠DONE

## 转普通流程

- 仅 PRE_PRE_REJECT / PRE_AUDIT_REJECT / CERT_REJECT 触发
- 流程：驳回 → SUGGEST_TO_REGULAR → SUBMIT_TO_REGULAR → 重新预审 → 证书流程

## 首发编辑权限

- 仅运营端可编辑
- 确认后 first_publish 赋值
- init_allowance_start_time = T+3天
- 测试金额=6 / 生产=30200
- 脏数据排除：200000026 / 200000028
- 可用验证数据：200000752 / 747 / 755

## yc_service_trade_record

- 无 DEDUCT 类型
- trade_type = BUY / REFUND / INCOME

## 快审扣减

- 走 yc_right_settle_order（TO_DO→DONE 约 50min）
- 扣减节点 = 初审提交 SUBMIT_APPLY
- 驳回不返还
- 真实通过/驳回须钉钉 @卢彩xq
- remainRightCount 由服务市场侧计算，用结算单验证

## 知识库

- workspaceId = nb9XJ9YdaYkZLzyA
- 交接文档 nodeId = 20eMKjyp810mMdK4H4PKm76jJxAZB1Gv
