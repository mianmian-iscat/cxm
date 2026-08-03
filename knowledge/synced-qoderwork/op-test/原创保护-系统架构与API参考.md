<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护用例生成/references/原创保护-系统架构与API参考.md -->
<!-- synced-at: 2026-07-11T03:52:35.001567 -->
<!-- skill: 原创保护用例生成 -->

# 原创保护平台 - 系统架构与API参考

## 技术栈
- **商家前端**: ICE.js 3.x + Ant Design 5 + TypeScript, Hash路由, MTOP协议
- **小二前端**: ICE3 + icestark微前端子应用 + antd v5 + @ali/tao-design
- **后端**: Java/Spring Boot (Serverless) + MyBatis + HSF + MetaQ + Diamond + ScheduleX
- **DB**: scenario@33.9.212.198:3011 (实际DB名=prod)

## 仓库
| 仓库 | 地址 |
|------|------|
| 商家前端 | industry-source-code/original-protection |
| 小二前端 | bzb-westeros/taotian-apparel-original-protection-xiaoer |
| 后端 | industry-serverless-apps/taobao-yc-serverless |

## 环境
| 环境 | 商家端 | 小二端 |
|------|--------|--------|
| 生产 | ttfsycbh.taobao.com | pre-xiaoer.alibaba-inc.com/.../taotian-apparel-original-protection-xiaoer/list |
| 预发 | pre-fsyc.taobao.com | 同上(预发hostname含pre自动切环境) |
| MTOP生产 | h5api.m.taobao.com | — |
| MTOP预发 | h5api.wapa.taobao.com | — |
| 测试账号 | isv项目测试专用(常用), 测试账号八载02(备用) | — |

## 后端DDD分层
```
start → service → application → domain → infrastructure
                                      ↑ client (对外DTO)
                                      ↑ common (工具/常量)
```

---

## 商家端 MTOP API (21个)

| API Key | 功能 | 服务文件 |
|---------|------|---------|
| taobao.industry.yc.right.apply | 提交/更新专利申请(草稿save/正式apply) | patentApply.ts |
| taobao.industry.yc.right.category.list | 获取商品类目列表 | patentApply.ts |
| taobao.industry.yc.right.page | 专利列表分页查询 | patentList.ts |
| taobao.industry.yc.inneryc.getyclink | 获取平台原创保护申请链接 | patentList.ts |
| taobao.industry.yc.right.apply.get | 获取申请详情 | patentList.ts |
| taobao.industry.yc.right.apply.terminate | 终止申请 | patentList.ts |
| taobao.industry.yc.right.apply.cancel | 取消申请 | patentList.ts |
| taobao.industry.yc.right.item.page | 可绑定商品列表 | patentList.ts |
| taobao.industry.yc.right.binditem | 绑定商品到专利 | patentList.ts |
| taobao.industry.yc.inneryc.page | 平台原创保护记录列表 | originalProtection.ts |
| taobao.industry.yc.right.protect.page | 维权记录列表 | rightsProtection.ts |
| taobao.industry.yc.seller.sign | 签约服务合同 | contract.ts |
| taobao.industry.yc.common.statistics | 仪表盘统计数据 | statistics.ts |
| taobao.industry.yc.tort.page | 侵权巡检记录列表 | inspection.ts |
| taobao.industry.yc.tort.add | 手动添加侵权记录 | inspection.ts |
| taobao.industry.yc.right.protect.submit | 提交维权请求(批量) | inspection.ts |
| taobao.industry.yc.tort.whitelist.page | 白名单店铺列表 | whitelist.ts |
| taobao.industry.yc.tort.whitelist.save | 添加/编辑白名单店铺 | whitelist.ts |
| taobao.industry.yc.tort.whitelist.delete | 删除白名单店铺 | whitelist.ts |
| taobao.industry.yc.common.allenum | 获取所有枚举值(缓存) | enum.ts |
| taobao.industry.yc.common.oss.getsignature | OSS上传签名 | upload.ts |

## 商家端 REST API (4个)

| Endpoint | Method | 功能 |
|----------|--------|------|
| /api/seller/apply/submitToRegular | POST | 快审转普通申请 |
| /api/file/upload | POST | 文件上传 |
| /api/tort/statistic | GET | 侵权状态统计 |
| /api/common/parseItemInfoByUrl | GET | URL解析商品信息 |

## 小二端 MTOP API (10个)

| API Key | 功能 |
|---------|------|
| bzb.api.sceneplatform.tbyc.right.page | 专利列表分页(9个筛选字段) |
| bzb.api.sceneplatform.tbyc.common.allenum | 枚举配置 |
| bzb.api.sceneplatform.tbyc.right.apply.get | 申请详情 |
| bzb.api.sceneplatform.tbyc.right.protect.page | 维权记录 |
| bzb.api.sceneplatform.tbyc.right.tort.statistics | 侵权统计(含下架率) |
| bzb.api.sceneplatform.tbyc.right.firstpublish.set | 设置是否首发 |
| bzb.api.sceneplatform.tbyc.right.whitelist.page | 白名单店铺 |
| bzb.api.sceneplatform.tbyc.right.tort.page | 侵权巡检记录 |
| bzb.api.sceneplatform.tbyc.seller.get | 商家信息(sellerId→shopName) |
| bzb.api.sceneplatform.tbyc.right.apply.submit | 小二发起快审 |

## 后端 REST Controller (7个)

| Endpoint | Method | 功能 |
|----------|--------|------|
| /api/tort/statusCount | GET | 侵权状态计数 |
| /api/file/upload | POST | 文件上传(MediaFacade) |
| /api/metaq/sendDocumentRenderDelayMsg | GET | 文档延迟渲染消息 |
| /api/common/parseItemInfoByUrl | GET | URL解析商品 |
| /api/inspect/whitelist/addForSeller | GET | 商家加入白名单 |
| /api/seller/apply/submitToRegular | POST | 快审转普通 |
| / , /index.html | GET | 主页(Velocity) |

---

## 数据库表 (12个)

| 表名 | Entity | 说明 |
|------|--------|------|
| yc_right | Right | 专利权主表(id, sellerId, status, applyTime, protectExpiredTime) |
| yc_right_apply | RightApply | 申请记录(id, rightId, status, applyType, applyTime) |
| yc_right_settle_order | RightSettleOrder | 结算单(id, settleStatus, totalAmount, servFinishRefundStatus) |
| yc_right_apply_op_record | ApplyOpRecord | 操作审计日志(operateType, operator) |
| yc_right_protect_record | RightProtectRecord | 维权记录(protectWay, status, startTime, finishTime) |
| tort_record | TortRecord | 侵权记录(rightId, status, rightTortRecordId) |
| inspect_whitelist | InspectWhitelist | 巡检白名单(id, sellerId, shopName) |
| seller_enter_info | SellerEnterInfo | 商家入驻(sellerId, status) |
| seller_contract_info | SellerContractInfo | 商家合同信息 |
| seller_wechat_group | SellerWechatJoinWayInfo | 商家微信群加入方式 |
| service_trade_record | ServiceTradeRecord | 服务交易记录 |
| refund_apply_order | RefundApplyOrder | 退款申请单 |

---

## 状态机

### 申请状态 RightApplyStatusEnum → RightStatusEnum

```
SAVING(草稿) ─┬─ QUICK_APPLY → QUICK_AUDITING(快审中) → QUICK_AUDITED
              │                                              │
              └─ SUBMIT_APPLY → PRE_PRE_AUDITING(初审中) ←───┘(补充后)
                                    │
                    ┌─── PRE_PRE_PASS ───┐
                    │                    │
              PRE_PRE_AUDITED    PRE_PRE_AUDIT_SUPPLEMENT(补正)
                    │                    │
              CERT_SUBMIT          补正后重新提交
                    │
              CERT_AUTHED(认证授权)
                    │
              CERT_FILE_SYNC(证书同步)
                    │
              CERT_FILE_SYNCED → Right: YC_PROTECT_VALID(保护中)
                    │
              (到期) → YC_PROTECT_INVALID(保护失效)

驳回路径:
  PRE_PRE_AUDITING → PRE_PRE_REJECT → Right: REJECT
  PRE_PRE_AUDIT_SUPPLEMENT → PRE_PRE_AUDIT_REJECT → REJECT
  任意状态 → END_APPLY → APPLY_TERMINATED(已终止)
  CERT_AUTHED → CERT_REJECT → (驳回)
```

### 结算状态 SettleStatusEnum
TO_DO → PROCESSING → FINISH

### 侵权状态 RightTortStatusEnum
TO_PROTECT(待维权) → PROTECTING(维权中)

### 维权状态 RightProtectStatusEnum
RUNNING(维权中) → SUCCESS(维权成功)

### 商家入驻 SellerEnterStatusEnum
ENTERED(已入驻)

---

## HSF/RPC 服务

### MTOP服务(商家端)
- RightMtopHsfService: 专利CRUD/内容校验/状态查询
- TortMtopHsfService: 侵权操作/统计/维权提交
- ItemMtopHsfService: 商品列表分页
- YcSellerMtopHsfService: 签约入驻
- YcCommonMtopHsfService: 统计/枚举
- InnerYcMtopHsfService: 平台原创链接

### 小二服务
- XiaoerRightHsfService: 专利管理(列表/详情/侵权/维权) @WebCobwebHSF 60s超时
- XiaoerSellerHsfService: 商家信息
- XiaoerYcCommonHsfService: 枚举值

### TOP开放平台(给YC机构)
- TopRightHsfService: 初审操作(通过/驳回/补正)/侵权提交/维权

### 工具服务(测试用)
- RightToolHsfService: updateExtraInfo, initProtectExpiredTime
- RightApplyToolHsfService: updateExtraInfo, updateStatus, updateProtectExpiredTime, updateApplyTime
- RightSettleToolHsfService: initSettleOrder, updateSettleStatus, querySettleOrders, getSettleOrderByApplyId, updateInitAllowanceStartTimeWithApplyId
- ServiceTradeToolService: triggerRefund
- SellerEnterToolService: enterSeller
- TortToolService: batchUpdateStatus

---

## ScheduleX 定时任务 (6个)

| 任务类 | 功能 |
|--------|------|
| RightProtectExpiredJob | 扫描到期专利，标记失效 |
| RightInvalidJob | 标记专利权无效 |
| RigthApplyToRegularTimeOutJob `[typo: Rigth→Right]` | 快审超时→转普通(TO_REGULAR_TIMEOUT_DAYS) |
| ServFinishIncomeJob | 服务到期确收(结算单PROCESSING) |
| ServFinishRefundJob | 服务到期退款(结算单PROCESSING) |
| InitAllowanceRefundJob | 初始化补贴退款(结算单TO_DO) |

---

## MetaQ 消息监听 (19个)

| 监听器 | 触发事件 | 处理逻辑 |
|--------|---------|---------|
| RightMessageListener | Right状态变更 | 同步状态/更新商品/处理终态 |
| RightApplyMessageListener | Apply状态变更 | 证书同步/更新商品 |
| RightApplyForSettleMessageListener | Apply→结算 | 初始化/更新结算单 |
| RightApplyForWhitelistMessageListener | Apply→白名单 | 申请事件更新白名单 |
| RightApplyForRightMessageListener | Apply→Right同步 | 申请状态同步到父Right记录 |
| RightForSettleMessageListener | Right→结算 | 到期→结算/Right状态变更 |
| TortMessageListener | 侵权记录事件 | 处理侵权状态变更 |
| TortMessageForRightListener | 侵权→Right同步 | 侵权状态同步到Right |
| ProtectMessageForSelfListener | 维权记录事件 | 处理维权状态 |
| ProtectMessageForRightListener | 维权→Right同步 | 维权状态同步到Right |
| ItemMessageListener | 商品事件 | 更新商品-证书关系 |
| ContractMessageListener | 合同事件 | 合同签署/文档渲染 |
| WhitelistMessageListener | 白名单事件 | 白名单变更处理 |
| ServiceRefundMessageListener | 退款事件 | 退款结果处理 |
| WechatGroupCreateMessageListener | 微信群创建 | 创建企微群加入方式 |
| SellerEnterMsgForSelfListener | 商家入驻事件 | 入驻处理 |
| SellerEnterMsfFroWhitelistListener `[typo: MsfFro→MsgFor]` | 入驻→白名单 | 入驻自动加白名单 |
| SellerEnterMsgForWhitelistListener | 入驻白名单同步 | 同步到白名单 |
| YcTradeMsgForSettleListener | 交易→结算 | 交易事件入结算 |
| ServiceMarketMsgListener | 服务市场通知 | 市场订单事件 |

---

## 外部集成 (15个Facade)

| Facade | 对接系统 | 功能 |
|--------|---------|------|
| YcServiceAgencyFacade | YC代理机构 | 申请提交/审核/证书同步/维权 |
| ContractFacade | 合同中心 | 合同渲染/签署 |
| DocumentFacade | 文档渲染中心 | PDF生成/证书渲染 |
| InnerYcFacade | 内部原创平台 | 签约状态查询 |
| ServiceMarketFacade | 淘宝服务市场 | 退款/确收/订单管理 |
| UicFacade | 用户中心 | 商家身份验证 |
| ItemFacade | 商品中心(IC) | 商品详情查询 |
| ShopFacade | 店铺服务 | 店铺信息查询 |
| CsiFacade | 绿网/内容安全 | 内容审核(已移除) |
| OssFacade | OSS对象存储 | 文件上传/STS凭证 |
| MediaFacade | 媒体服务 | 媒体文件上传 |
| WechatFacade | 企业微信 | 群加入二维码 |
| DingtalkFacade | 钉钉 | 运营通知消息 |
| QnTagReadFacade | 千牛标签 | 读取TTYCBH白名单标签 |
| MetaqFacade | MetaQ消息队列 | 异步消息发送 |

## Diamond 动态配置

| DataId | 用途 |
|--------|------|
| yc.common.config | 平台通用配置 |
| yc.service.agency.config | YC机构端点/认证 |
| yc.seller.whitelist | 商家白名单 |
| inner.yc.config | 内部原创平台 |
| service.market.config | 服务市场 |
| dingtalk.robot.config | 钉钉机器人 |
| RightSwitch (AppSwitch) | 运行时开关: TO_REGULAR_TIMEOUT_DAYS等 |
