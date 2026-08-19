---
name: 原创保护千牛标打标
version: 1.1.0
description: 为淘天服饰原创保护测试商家自动打上千牛标 TTYCBH，解决 SellerEnterDomainServiceImpl.enter() 准入拦截，使测试账号可正常入驻并进入申请流程。v1.1.0 增加 Phase 0 自检清单与已知问题速查。
---

> 测试商家 seller_id 统一维护入口：[yc-protection-qa-workbench/test-accounts.md](../yc-protection-qa-workbench/test-accounts.md)

# 原创保护千牛标打标

解决商家入驻时被提示「抱歉，该服务现面向具备高原创能力要求的商家开放」的拦截问题。该提示由 `SellerEnterDomainServiceImpl.enter()` 调用千牛标读服务 `qnTagReadFacade.hasUserDataTag(sellerId, "TTYCBH")` 触发，未打标则抛 `BizException` 拦截。

## 触发条件

- 商家端入驻提示：「抱歉，该服务现面向具备高原创能力要求的商家开放，如有需求您可联系店铺小二申请加入」
- 执行 `yc-data-factory` 的 `SellerEnterToolService.enterSeller(sellerId)` 返回失败/无权限
- `原创保护测试编排` 进入「千牛标打标 → 入驻」阶段
- 用户明确说：打千牛标、TTYCBH 打标、原创保护入驻拦截

## Phase 0 自检清单

进入打标流程前必须先完成以下检查；任一项未通过即停止执行，改为 IM 私聊用户说明原因。

| # | 检查项 | 通过标准 | 失败处理 |
|---|--------|---------|---------|
| P0-1 | 环境确认 | `env` 为 `staging` / `pre`，不含 `prod` / `production` | 立即中止并告警 |
| P0-2 | seller_id 白名单 | 所有待打标 ID 均出现在 [test-accounts.md](../yc-protection-qa-workbench/test-accounts.md) | 非白名单 ID 必须经用户书面确认属于测试账号 |
| P0-3 | 缺省跳过条件 | 该 seller_id 已存在 `TTYCBH` 标且 `SellerEnterToolService.enterSeller` 已成功 | 跳过打标，直接进入下一步申请构造 |
| P0-4 | 权益数预检 | 入驻后预计需要新建申请时，测试账号有可用权益或已准备小二端绕过方案 | 权益为 0 时提前告知，避免入驻后卡在 `BIZ_ERROR::可用权益数不足` |
| P0-5 | 千牛标后台可访问 | 能正常打开 `https://qn.alibaba-inc.com/qndev-data-app/management#/` | 不可用时改走 API-first 路径或等待用户恢复登录态 |

## 安全红线（不可跳过）

⚠️ **仅限预发/测试环境使用**。生产卖家严禁打标。

1. **白名单校验**：默认仅允许 [test-accounts.md](../yc-protection-qa-workbench/test-accounts.md) 中登记的测试 seller_id，当前默认：`2213249110271`。
2. **环境隔离**：预发与生产走同一套千牛标校验逻辑，操作前必须确认当前为预发环境。
3. **二次确认**：实际打标前向用户展示待打标 seller_id 列表，等待用户确认。
4. **禁止 DML**：本 Skill 不直接修改 scenario DB；如后续对接 API，必须通过 HSF/千牛平台官方接口完成。
5. **可审计**：操作完成后记录 seller_id、操作人、时间、结果到操作流水或会话日志。

## 输入

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| seller_ids | `List<Long>` | 否 | 待打标卖家 ID 列表；未提供时使用默认白名单 `[2213249110271]` |
| env | `String` | 是 | 必须为 `staging` / `pre`；出现 `prod` / `production` 立即中止并告警 |

## 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| tag_applied | `boolean` | 是否完成 TTYCBH 打标 |
| applied_seller_ids | `List<Long>` | 成功打标的 seller_id 列表 |
| failed_seller_ids | `List<Long>` | 失败的 seller_id 列表及原因 |
| next_step | `String` | 固定为：调用 `SellerEnterToolService.enterSeller(sellerId)` 触发入驻 |

## 执行路径

### 路径 A：API-first（优先）

> ⚠️ 写标接口未在 `yc-data-factory` 中沉淀，需业务方确认后启用。

**已知读标链路**（已验证）：
- 代码位置：`taobao-yc-serverless-domain/.../SellerEnterDomainServiceImpl.java:65-67`
- 读标 Facade：`QnTagReadFacadeImpl`
- HSF 服务：`QnResourceTagService`
- 方法：`hasResourceTag(userId, qnTagCode, projectName)`
- 千牛标 Code：`TTYCBH`

**待业务方确认的写标方案**：
- 可能接口：`com.taobao.multi.client.service.QnResourceTagService:1.0.0`
- 可能方法：`createQnTag` / `addResourceTag` / `batchAddResourceTag` 等（待确认）
- 参数示例：`userId={sellerId}, qnTagCode="TTYCBH", projectName="taobao-yc-serverless"`

**确认后调用模板**（mw CLI）：

```bash
mw hsf service invoke "com.taobao.multi.client.service.QnResourceTagService:1.0.0" \
  --method "<method>~java.lang.Long;java.lang.String" \
  --args '[2213249110271, "TTYCBH"]' \
  --app taobao-yc-serverless --unit pre
```

若业务方确认接口可用，本路径自动执行并输出结果；否则进入路径 B。

### 路径 B：半自动后台上传（Fallback）

当 API 未确认/不可用时，生成标准化 TXT 上传模板，引导用户通过千牛标管理后台完成打标。

**步骤**：
1. 读取 seller_ids，校验格式并过滤非白名单 ID。
2. 生成 TXT 文件：`{timestamp}_ttycbh_sellers.txt`。
3. 引导用户打开千牛标管理后台：`https://qn.alibaba-inc.com/qndev-data-app/management#/`。
4. 进入「名单管理」→「名单操作 = 打标」→「上传TXT」。
5. 上传生成的 TXT 文件。

**TXT 格式规范**：
- 纯文本 `.txt` 文件
- 每行一个纯数字 sellerId
- 无空格、无逗号、无中文备注、无科学计数法

正确示例：
```text
2213249110271
2219635657158
```

常见错误：
- 文件格式非 TXT 或编码异常 → 使用官方模板
- Excel 导出导致科学计数法 → 单元格设为「文本」后再复制
- 行尾空格/逗号 → 删除后重新上传
- 行内混入中文备注 → 只保留纯数字

## 打标成功验证

1. 商家重新进入「淘天服饰原创保护」商家端。
2. 不再弹出「高原创能力要求」BizException 提示。
3. 页面正常展示：专利认证数量、疑似侵权商家数量、4 步引导、申请列表。
4. DB 侧可核：`SELECT * FROM seller_enter_info WHERE seller_id = {sellerId};` 出现入驻记录。

## 下一步：触发入驻

打标成功后，调用 `yc-data-factory` 的 `SellerEnterToolService`：

```bash
mw hsf service invoke \
  "com.taobao.industry.yc.serverless.service.hsf.tool.SellerEnterToolService:1.0.0" \
  --method "enter~java.lang.Long" \
  --args '[2213249110271]' \
  --app taobao-yc-serverless --unit pre
```

入驻成功后，继续后续流程：
- 构造申请：`yc-quick-audit-data-create`
- 状态/时间操作：`yc-data-factory`
- DB 验证：`yc-db-verification`

## 脚本模板

本地半自动模板：`references/apply_ttycbh_tag.py`

功能：
- 从文件或环境变量读取 seller_id 列表
- 校验格式并过滤白名单
- 生成千牛标后台可上传的 TXT 文件
- 打印 API/HSF 调用示例与后台操作步骤
- **不发起任何真实网络/HSF/DB 调用**

用法：
```bash
# 默认使用白名单
python3 references/apply_ttycbh_tag.py

# 从文件读取
python3 references/apply_ttycbh_tag.py --input sellers.txt

# 从环境变量读取
SELLER_IDS="2213249110271,2219635657158" python3 references/apply_ttycbh_tag.py
```

## 关联 Skill

- `yc-data-factory`：入驻 HSF Tool `SellerEnterToolService.enterSeller`
- `yc-quick-audit-data-create`：入驻后构造 QUICK/PRE 申请
- `yc-db-verification`：验证 `seller_enter_info` 入驻记录
- `yc-defect-diagnosis/references/已知问题与踩坑.md` §8.1：千牛标已知问题

## 验证清单

- [ ] 输入 env 为 staging / pre，未出现 prod / production
- [ ] 待打标 seller_id 已确认属于测试白名单
- [ ] 用户已二次确认打标列表
- [ ] API 路径：接口与方法已获业务方确认（如走 API）
- [ ] Fallback 路径：TXT 文件格式符合后台要求
- [ ] 打标成功后商家端不再提示「高原创能力要求」
- [ ] 已调用 `SellerEnterToolService.enterSeller` 完成入驻

## 已知问题速查

打标前/打标失败时优先核对 [references/known-issues.md](references/known-issues.md)，覆盖：

1. **准入拦截「高原创能力要求」**：根因是 `SellerEnterDomainServiceImpl.enter()` 读 `TTYCBH` 未命中。 
2. **TXT 上传格式错误**：科学计数法、行尾空格/逗号、中文备注均会导致失败。 
3. **二级校验**：打标成功仅代表准入通过；若入驻后「可用权益数 = 0」，新建申请会报 `BIZ_ERROR::可用权益数不足`。
