<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护用例生成/references/original-protection-code.md -->
<!-- synced-at: 2026-07-11T03:52:35.001268 -->
<!-- skill: 原创保护用例生成 -->

# 原创保护平台代码层技术参考（前后端）

> 本文档面向 QA 测试，沉淀三个核心仓库的代码级知识，便于精准设计测试用例和定位风险。
>
> **仓库索引**
> - 商家前端：`industry-source-code/original-protection`（ID 3721961）
> - 小二前端：`bzb-westeros/taotian-apparel-original-protection-xiaoer`（ID 3824672，**icestark 子应用**）
> - 后端：`industry-serverless-apps/taobao-yc-serverless`（多模块 DDD，预生成 wiki 在 `domain-knowledge-base/qoder-knowledge-engine/industry-serverless-apps/taobao-yc-serverless/repowiki/zh/content/`）
>
> 访问方式：`a1 repo file view --repo {path} {file}` / `a1 repo search "{kw}" --repo {path}`（不可 git clone）

---

## 一、商家前端 `industry-source-code/original-protection`

### 1.1 技术栈

ice.js 3 + React 18 + TypeScript + Ant Design 5 + ProComponents；MTOP（@ali/lib-mtop）+ axios 双通道；hash router；ice plugin-store + plugin-request；SCSS Modules；OSS 直传 + axios `/api/file/upload`；PDF.js 动态加载（本地→CDN 回退）。主色 `#3D5EFF`。

### 1.2 目录结构（关键路径）

```
src/
├── app.ts                      # 401 → Havana 登录跳转；userType admin/user
├── pages/
│   ├── layout.tsx              # ProLayout + ConfigProvider，首页隐藏菜单
│   ├── index.tsx               # 总入口，sellerSigned 切换签约/未签约
│   ├── patentList/             # 专利列表
│   ├── originalProtectionList/ # 淘内首发列表
│   └── $.tsx                   # 404
├── components/
│   ├── PatentApply/            # 申请抽屉（1500+ 行，最复杂）
│   ├── PatentDetail/           # 详情页 + StatusTimeline
│   ├── BindProductModal/       # 商品绑定（多选 + 滚动加载 pageSize=16）
│   ├── InspectionDetail/       # 巡检 + 维权发起
│   ├── RightsProtectionRecord/ # 维权记录
│   ├── ContractPage/           # 未签约引导
│   ├── ContractDrawer/         # 签约协议 iframe
│   ├── StatisticsCards/        # 4 张统计卡（<5 警告）
│   ├── TabSwitcher/            # patent / original
│   ├── ProtectionSteps/
│   ├── Whitelist/              # 旗下店铺白名单
│   ├── AddProductModal/ ItemModal/ # 商品链接 onBlur 反填
└── services/                   # 所有 API 调用集中
    ├── api.ts                  # MTOP 统一封装、错误归一
    ├── patentApply.ts / patentList.ts / originalProtection.ts
    ├── inspection.ts / rightsProtection.ts / whitelist.ts
    ├── contract.ts / enum.ts(Promise 缓存) / statistics.ts
    ├── upload.ts / parseItemInfoByUrl.ts
    ├── contentCheck.ts          # ⚠ 当前 stub，恒返回 true
    └── tortStatus.ts
```

### 1.3 路由表

| 路径 | 组件 | 说明 |
|---|---|---|
| `/` | pages/index.tsx | 签约状态 + Tab 驱动业务 |
| `/?rightId=xxx` | 同上 | 直达专利详情，进入后 replaceState 清除参数 |
| `/?applyId=xxx` | 同上 | 直达申请记录 |
| `*` | pages/$.tsx | 404 |

> 实际路由极简，详情/编辑/查看均为 Drawer/Modal。

### 1.4 MTOP API 列表（商家前端）

| API | 功能 | 文件 |
|---|---|---|
| `taobao.industry.yc.right.apply` | 提交申请/草稿（saveOrApply） | patentApply.ts |
| `taobao.industry.yc.right.category.list` | 类目下拉 | patentApply.ts |
| `taobao.industry.yc.right.list` | 专利列表分页 | patentList.ts |
| `taobao.industry.yc.right.detail` | 专利详情 | patentList.ts |
| `taobao.industry.yc.right.cancel` | 取消申请 | patentList.ts |
| `taobao.industry.yc.right.terminate` | 终止申请 | patentList.ts |
| `taobao.industry.yc.right.bind.item` | 商品绑定 | patentList.ts |
| `taobao.industry.yc.right.item.list` | 待绑定商品分页 | patentList.ts |
| `taobao.industry.yc.right.original.protect.apply` | 申请原创保护 | patentList.ts |
| `taobao.industry.yc.inneryc.page` | 淘内首发列表 | originalProtection.ts |
| `taobao.industry.yc.tort.page` | 巡检/线索分页 | inspection.ts |
| `taobao.industry.yc.tort.add` | 手动添加侵权线索 | inspection.ts |
| `taobao.industry.yc.right.protect.submit` | 发起维权（多选 tortRecordIds[]） | inspection.ts |
| `taobao.industry.yc.right.protect.page` | 维权记录分页 | rightsProtection.ts |
| `taobao.industry.yc.whitelist.page/save/delete` | 店铺白名单 CRUD | whitelist.ts |
| `taobao.industry.yc.seller.sign` | 签约（返回 jumpTo） | contract.ts |
| `taobao.industry.yc.common.allenum` | 全量枚举（Promise 缓存） | enum.ts |
| `taobao.industry.yc.common.statistics` | 4 卡统计 | statistics.ts |
| `taobao.industry.yc.common.oss.getsignature`（ecode=1） | OSS 签名 | upload.ts |

### 1.5 内部 axios `/api/*`

| 路径 | 方法 | 功能 |
|---|---|---|
| `/api/seller/apply/submitToRegular` | POST | 转普通申请 |
| `/api/file/upload` | POST | 文件上传（响应结构兼容多种） |
| `api/common/parseItemInfoByUrl` | GET | 商品链接解析（⚠ 无前导 `/`，依赖 base path） |
| `/api/tort/statistic` | GET | 侵权统计 |

### 1.6 MTOP 环境识别与错误归一

- 预发：`hostname.includes('pre')` 或 URL `?usePreMtop=true`；prefix=h5api，subDomain=wapa|m
- `FAIL_SYS_SESSION_EXPIRED` → 跳 `https://login.taobao.com/havanaone/login/login.htm`
- `BIZ_ERROR::msg` 双冒号格式解析；兼容 JSON onError

### 1.7 商家端状态机与枚举

#### IRightStatus（专利权利状态，9 态）
| 值 | 含义 | UI Tab |
|---|---|---|
| SAVING | 草稿 | 草稿箱 |
| APPLYING | 申请中 | 申请中 |
| REJECT | 驳回 | 驳回 |
| APPLY_TERMINATED | 申请终止 | 已终止 |
| YC_PROTECTING | 保护中 | 保护中 |
| YC_PROTECT_EXPIRED | 保护到期 | 已到期 |
| YC_PROTECT_INVALID | 保护失效 | 已失效（详情映射 expired） |
| IN_TRANSFER | 转让中 | 转让中 |
| TRANSFERRED | 已转让 | 已转让 |

#### PatentDetail 五段流程态（mapStatusToComponentStatus）
quickAudit / initialReview / preAudit / certification / certificate / expired
子状态：QUICK_AUDITING / AUDITED / REJECT / PRE_PRE_AUDITING / PRE_AUDITING / SUPPLEMENT / CERT_DOING / AUTHED / CERT_FILE_SYNCED / APPLY_END

#### 申请类型 applyType
QUICK / PRE / **REGUALR**（⚠ 拼写错误，需与后端确认实际枚举字符串）

#### 平台枚举不一致（QA 红线）
- 巡检：`PDD/DY/JD/XHS/TB/TM`
- 白名单：`PDD/DOUYIN/JD/XIAOHONGSHU/TAOBAO/TMALL/XIANYU/1688`

### 1.8 表单关键字段（PatentApply）

```
designers[]: name / idNumber / nationality / idCardFront / idCardBack
contactName / contactPhone
productName / category(默认 服装) / productPurpose
designPoints: { type, views[] }
productImages: { stereo, main, back, left, right, top, bottom }
extraMaterials[] / expectedListDate / originalDescription
applyType / saveOrApply / id(更新回填)
```

校验：身份证 `/^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$/`；手机号 `/^1[3-9]\d{9}$/`；权益不足正则 `/权益|次数不足|权利.*不足|可用.*不足|可用权益数不足|没有可用的充值订单/`。

### 1.9 商家端代码风险点（QA 重点）

1. **applyType 拼写不一致 REGUALR**：保存草稿/提交/详情回显需逐路径核验字符串一致性。
2. **接口字段单复数差异**：`patentApply` 类型用 `designElement/designView`，请求体却写 `designElements/designViews`；详情字段 `otherFile` 与 `otherFiles` 单复数兼容读取，需测 5 种组合（单只/双有/双空/缺失）。
3. **isTrue 兼容**：仅识别 `'true' | true`；后端返回 `1/'1'/'TRUE'/'Y'/''` 会判错。
4. **publishItemAvailable + publishItemGray 双字段组合**：available=true & gray=true（保留可发但置灰提示）/ available=false & gray=false（直接禁用）需各自验证。
5. **submitProtectExpireTime 维权置灰**：测临界值（恰等当前/早 1s/晚 1s）和时区差。
6. **服务次数 <5 警告**：阈值 5；测 0/1/4/5/6 边界，验证充值入口仅 <5 出现。
7. **BindProductModal 滚动加载**：距底 120px、pageSize=16；商品总数 16/17/32/33 验证不重复请求与去重。
8. **专利权利状态 9 态 × Tab 过滤**：每态需逐一打桩；YC_PROTECT_INVALID 在列表 Tab 是否独立。
9. **三阶段补充材料**：预审前/预审/出证共享相同字段结构；测 1 段触发 / 多段连续 / 补完后再次驳回。
10. **签约状态切换**：signContract 成功直接改 `window.yc_info.sellerSigned=true`，未重新拉接口；测后端实际签约失败但 MTOP 返回 success 的误判场景。
11. **草稿 → 申请**：补充材料 omitSaveOrApplyOnSubmit 不传字段；验证后端是否要求该字段。
12. **submitToRegular 走 axios 不走 MTOP**：会话过期不跳登录；同样问题影响 `/api/file/upload` `/api/tort/statistic`。
13. **取消 vs 终止 vs 草稿删除**：cancelApply / terminateApply 语义易混，权利状态对它们的可见性需逐态校验。
14. **MTOP/axios 双错误体系**：BIZ_ERROR::msg vs axios HTTP 错误展示差异。
15. **contentCheck stub**：所有违禁词/敏感图测试用例前端不会拦截，必须由后端兜底验证。
16. **parseItemInfoByUrl 路径无前导 `/`**：相对路径，部署到子路径环境（pre/线上）可能错。
17. **enum 全量缓存**：Promise 缓存，首次失败后续都失败需刷新；测首次 500/401/缓存陈旧。
18. **平台枚举两套不一致**：交叉过滤场景（白名单店铺与巡检线索关联）易错。
19. **维权 mapStatus 中文/英文关键字匹配脆弱**：文案改一字（"已成功"→"成功完成"）即破坏映射。
20. **OSS 签名 ecode=1**：需登录态；匿名/未签约用户上传应触发跳登录。
21. **PDF.js 本地+CDN**：本地资源 404 / CDN 网络断 / 大 PDF 需测。
22. **uploadFile 响应兼容多结构**：后端改返回结构需回归。
23. **批量绑定部分成功**：Promise.all 收集成功/失败 warning；测部分失败的失败列表是否可重试。
24. **history.replaceState 清除 URL 参数**：刷新页不复现详情；分享链接是否需复现要确认产品需求。
25. **`patentApplySuccess` 自定义事件**：连续多次提交、提交后立即关页、提交后切 Tab 是否触发刷新。
26. **window.yc_info 全局**：注入晚于 React 渲染会闪屏；A 标签页登出但 B 标签页 sellerSigned 仍为 true。
27. **menuConfig 模板菜单残留**：偶然访问会暴露工作台/表单等模板菜单。
28. **登录跳转 redirectURL 编码**：URL 含 `&#=` 是否被二次编码、回跳是否复现原页。

---

## 二、小二前端 `bzb-westeros/taotian-apparel-original-protection-xiaoer`

### 2.1 技术栈（关键差异）

- **icestark 子应用**（type:`child`）+ ice.js 3 + React 18，**不可独立访问**，由主应用挂载
- 子应用基础路径硬编码为 `taotian-apparel-original-protection-xiaoer`
- UI **混用三套**：`antd@5.27` + `@ali/tao-design`（FilterArea/QuickAuditDrawer）+ `@alifd/next`（Upload.Uploader）
- 网关请求：`@ali/bzb-request`，封装在 `src/services/request.ts`
- 监控：`@ali/aes-tracker` 系列
- OSS 直传（前端拿签名后 PUT/POST）

### 2.2 目录结构（关键）

```
src/
├── app.ts                          # icestark mount/unmount 钩子（仅 console）
├── layouts/BasicLayout/            # antd ConfigProvider zh_CN
├── pages/list/                     # ★唯一页面
├── components/
│   ├── FilterArea                  # 顶部筛选（21 状态硬编码）
│   ├── Table                       # 列表 + FirstLaunchCell
│   ├── PatentApply                 # 申请抽屉（新建/补充材料/查看）
│   ├── PatentDetail                # 状态详情抽屉 + StatusTimeline
│   ├── QuickAuditDrawer            # ★小二独有：发起快审
│   ├── WhitelistDrawer             # 白名单（只读）
│   ├── InspectionDetail / RightsProtectionRecord / DetailedMaterialsLinks
│   ├── OSSUpload / PdfThumbnail
├── services/
│   ├── request.ts / patent.ts / upload.ts
└── declarations/patent.ts
```

### 2.3 路由表

| 路径 | 组件 | 备注 |
|---|---|---|
| `taotian-apparel-original-protection-xiaoer` | BasicLayout | 子应用根 |
| `taotian-apparel-original-protection-xiaoer/list` | pages/list/index.tsx | **唯一业务路由** |

> 没有独立详情路由，所有详情/编辑/查看均为 Drawer，由列表页 selectedRecord 传 applyId/rightId。

### 2.4 MTOP API 列表（小二端）

| API | 功能 |
|---|---|
| `bzb.api.sceneplatform.tbyc.right.page` | 分页查询权利/申请列表 |
| `bzb.api.sceneplatform.tbyc.right.apply.get` | 申请详情 |
| `bzb.api.sceneplatform.tbyc.right.protect.page` | 维权记录分页 |
| `bzb.api.sceneplatform.tbyc.right.tort.page` | 巡检列表 |
| `bzb.api.sceneplatform.tbyc.right.tort.statistics` | 侵权统计（statusCount + takeDownRate） |
| `bzb.api.sceneplatform.tbyc.right.firstpublish.set` | 设置是否首发 |
| `bzb.api.sceneplatform.tbyc.right.whitelist.page` | 白名单**只读**分页 |
| `bzb.api.sceneplatform.tbyc.seller.get` | sellerId → shopName |
| `bzb.api.sceneplatform.tbyc.right.apply.submit` | **小二独有：提交快审** |
| `bzb.api.sceneplatform.tbyc.common.allenum` | 全量枚举 |
| `bzb.api.sceneplatform.tbyc.common.getosssignature` | OSS 签名 |

> ⚠ 网关返回三层包裹：`res.data.data.content`（列表）；同时检查 `res.success` 与 `wrapper.fail`，但两者并非全文统一。

### 2.5 状态机（v5 最细粒度，21 态硬编码 FilterArea）

| Code | 文案 | 阶段 |
|---|---|---|
| SAVING | 草稿中 | - |
| QUICK_AUDITING / QUICK_REJECT / QUICK_AUDITED | 快审中/拒绝/通过 | 快审 |
| PRE_PRE_AUDITING / PRE_PRE_AUDITED / PRE_PRE_AUDIT_REJECT / PRE_PRE_AUDIT_SUPPLEMENT | 初审 4 态 | 初审 |
| PRE_AUDITING / PRE_AUDITED / PRE_AUDIT_REJECT / PRE_AUDIT_SUPPLEMENT | 预审 4 态 | 预审 |
| CERT_DOING | 专利权利已受理 | 认证 |
| CERT_AUTHED / CERT_REJECT / CERT_SUPPLEMENT | 认证已授权/驳回/补正 | 认证 |
| CERT_FILE_SYNCED | 已同步证书 | 证书 |
| APPLY_END | 申请终止（认证阶段） | 认证 |
| YC_PROTECT_INVALID | 专利保护已过期 | 失效 |
| APPLY_TERMINATED | 申请终止 | 终态 |
| IN_TRANSFER / TRANSFERRED | 专利转回申请中/已转回 | 转回 |

### 2.6 状态映射规则

- `mapStatusToComponentStatus` 映射 6 流程态：quickAudit / initialReview / preAudit / certification / certificate / expired
- `rightStatus === 'YC_PROTECT_INVALID'` 强制覆盖为 expired，但保留原 subStatus
- `regularApply === true` 跳过"专利预审备案"节点（5 步变 4 步）
- 普通申请入口：`toRegularStatus === 'TO_DO'` 才显示"提交普通申请"按钮
- 筛选项二分组：`PATENT_APPLY_STATUS_CODES` 排除 `SAVING/YC_PROTECT_INVALID/APPLY_TERMINATED/IN_TRANSFER/TRANSFERRED` 5 个进 `status`（粗），其余进 `applyStatus`（细）

### 2.7 小二端独有功能

1. **发起快审（QuickAuditDrawer）**：sellerId 失焦反查店铺名 + 主视图图片 + 预计上架日期；接口 `bzb.api.sceneplatform.tbyc.right.apply.submit`
2. **运营搜索维度更全**：商家ID 输入框（商家端无）
3. **是否首发可编辑**：FirstLaunchCell 下拉 + Modal.confirm + setRightFirstPublish；`firstPublishAvailable=false` 禁用
4. **白名单只读**：仅展示分页，**无新增/删除入口**
5. **审核人脱敏**：maskName（保留首字）+ maskPhone（前3后4），但 StatusTimeline 默认不脱敏，权限边界需关注
6. **缺失结算单管理**：搜索 `settlement|结算单` 无匹配

### 2.8 小二端代码风险点

1. **专利申请 handleFinish 整体被注释**：当前小二端点提交无任何反应，需确认产品是否下线"小二代提交"，仅保留快审+查看+补充材料。
2. **状态映射兜底默认 initialReview**：未匹配任何 case 时归类为初审中——后端新增枚举（v5 子状态）必须前后端联调。
3. **regularApply 双轨**：步骤 4 vs 5，`isThirdStep/isFourthStep` 双轨；测 `regularApply true/false × 各 currentStatus` 笛卡尔积。
4. **是否首发过期判断**：`firstPublishEditEndTime` 仅前端展示，编辑权限完全靠后端 `firstPublishAvailable`；跨日临界场景前后端时间一致性需验证。
5. **筛选状态二分硬编码**：`PATENT_APPLY_STATUS_CODES` 集合是前端硬编码；后端字典调整会传错参数。
6. **响应解包链路三层**：`res.data.data.content`，任一层 null/undefined/fail=true 处理不一致会导致空白或异常 toast。
7. **MTOP 通用错误降级**：apiRequest 把 `SYS_ERR/API_GATEWAY_TIMEOUT` 一律转"网络异常"，业务错误码被吞掉；测试错误文案要让后端返回业务码。
8. **isTrue 与 coerceOptionalBoolean 双标准**：前者只识 'true'/true，后者支持 Y/N，标准不统一。
9. **身份证正则不验校验位**：合法格式但实际错误的身份证号能输入。
10. **OSS 直传 policy base64 解析 acl**：policy 结构变化静默丢失 acl；测大文件、断网重传、签名过期。
11. **环境判定 `hostname.includes('localhost'|'pre')`**：预发域名要确认含 "pre"；不含会误打 prod。
12. **tao-design Input allowClear 不触发 onValuesChange**：FilterArea 手写 onClear；漏写会导致清空后旧值仍参与查询。
13. **PatentDetail 转回 Modal 写死 mocky URL**：仅校验 xls 类型（产品文案可能要求 PDF），上传成功逻辑未对接真实接口。
14. **PDF 缩略图 CDN 回退**：线上 CSP 拦截 cdnjs 会显示占位。
15. **InspectionDetail 内置默认 PLAT/SOURCE 枚举**：getAllEnum 失败兜底硬编码（不含京东以外），后端新增平台会丢失。
16. **遗留 console.log**：FilterArea `[FilterArea] submit/reset` 未清理。
17. **PatentDetail 三按钮无业务**：onTerminateApply / onAbandonPatent / onDelegateManage 被 void，按钮"没反应"需判断是否符合预期。

---

## 三、后端 `industry-serverless-apps/taobao-yc-serverless`

### 3.1 模块结构（DDD 多模块 Maven）

| 模块 | 职责 |
|---|---|
| `taobao-yc-serverless-start` | 启动模块 + Pandora Boot + `application-{testing,staging,production}.properties` + ali_env_sign |
| `taobao-yc-serverless-service` | 服务暴露：REST Controller + HSF 实现 + TOP 网关适配 |
| `taobao-yc-serverless-application` | 应用编排：ApplicationServiceImpl + MetaQ 监听器 + ScheduleX 任务 + Converter |
| `taobao-yc-serverless-domain` | 领域：聚合根（Right/TortRecord/ServiceTradeRecord）+ 领域服务 + 状态枚举 + Facade 接口 |
| `taobao-yc-serverless-infrastructure` | 基础设施：MyBatis Mapper.xml + Repository + TDDL + Tair + Lock + Metaq + OSS |
| `taobao-yc-serverless-client` | 对外契约：DTO + 请求对象 + HSF 接口 |
| `taobao-yc-serverless-common` | 常量（RightConstant/RightSettleConstant）+ 工具 + 异常 |

### 3.2 技术栈

Pandora Boot；HSF + TOP + MTOP；MetaQ（含 delay level / RECONSUME_LATER）；SchedulerX2；Diamond；Tair（缓存+分布式锁，`${spring.tair.namespace}`）；OSS/STS；TDDL + MyBatis；TBSession + Cobweb + UIC；EagleEye；`TransactionService.executeAfterCommit`（事务后回调）。环境通过 `ali_env_sign`（SMALLFLOW=production）+ Spring Profile 控制。

### 3.3 接口清单

#### 3.3.1 REST（service 模块）
| 路径 | 方法 | 功能 | 调用端 |
|---|---|---|---|
| `/api/common/parseItemInfoByUrl` | GET | 商品链接解析 | 商家前端 |
| `/api/tort/statusCount` | GET | 侵权状态统计 | 商家前端首页 |
| `/api/tort/statistic` | GET | 侵权统计分析 | 商家+小二 |
| `/api/inspect/whitelist/addForSeller` | POST | 商家自助加白名单（千牛 TTYCBH） | 仅特定主账号 |
| `/api/inspect/whitelist/updateForSeller` | POST | 更新自身白名单 | 千牛 |
| `/api/file/upload` | POST | OSS/STS 上传 | 商家前端 |

#### 3.3.2 MTOP（商家/千牛）
contentCheck / categoryList / rightApply / pageRight / getRightApply / terminateApply / cancelApply / bindItem

#### 3.3.3 TOP 接口（外部服务机构回调，TopRightHsfService）
| API | 功能 |
|---|---|
| syncAuditOperation | 同步审核操作（初审/预审/认证 通过/拒绝/补正/已授权） |
| saveTortRecord | 批量同步侵权记录入库 |
| syncRightProjectProcess | 维权过程进度同步 |
| syncRightProjectResult | 维权结果回写（含是否下架） |

#### 3.3.4 工具 HSF（小二/内部）
RightToolHsfService / SellerEnterToolService / ServiceTradeToolService / TortToolService

> 商家入驻状态必须为 `ENTERED`；`MyValidator` 统一校验；`BizException` 由 `ExceptionAdvice` 转标准错误码。

### 3.4 MetaQ 监听器清单

> 所有发送通过 `MetaqFacade` + `executeAfterCommit`（事务提交后投递）。

| 监听器 | Topic | Tag | 触发逻辑 |
|---|---|---|---|
| RightMessageListener | TOPIC_TBYC_RIGHT | audit-pass | 审核通过缓存证书；状态变更清证书缓存 |
| RightApplyMessageListener | TOPIC_TBYC_RIGHT_APPLY | submit/update/terminate/cancel/cert-synced | 提交→对接服务机构落申请；更新→回写；证书同步→缓存+渲染承诺书；终止/撤销→通知服务机构 |
| TortMessageListener | TOPIC_TBYC_TORT | new / 维权 | new：批量校验外部 ID 后生成维权记录 |
| WhitelistMessageListener | 白名单主题 | add/update | 同步抽检/巡检 |
| SellerEnterMsgForSelfListener | 商家入驻 | enter | 入驻成功初始化资源 |
| WechatGroupCreateMessageListener | 微信群创建 | create | 申请阶段创建补正沟通群 |
| ContractMessageListener | 合同 | sign/lifecycle | 合同/电子文档生命周期回写 |
| ItemMessageListener | 商品变更 | item-update | 商品下架/更新触发权利联动 |
| ServiceRefundMessageListener | 服务退款 | apply/result | apply→构造 ServiceRefundReq 调 startRefund；result→根据状态判断 finishRefund |

### 3.5 ScheduleX 定时任务

| 任务类 | 频率 | 功能 |
|---|---|---|
| RightProtectExpiredJob | 每天 | 扫描保护到期权利 → invalid + MetaQ 通知 |
| ServFinishIncomeJob | 周期 | 服务完结确收：扫描结算单待处理项调服务市场确收 |
| ServFinishRefundJob | 周期 | 服务完结退款：扫描结算单待处理项发起退款 |
| InitAllowanceRefundJob | 周期 | 首发补贴退款扫描 |
| ProtectExpired2RefundJob | **当前已注释禁用** | 保护到期转退款，需关注是否恢复 |

> 所有 Job 为"逐笔扫描+串行处理"。

### 3.6 领域实体 + 状态枚举

#### 三大聚合根
| 聚合根 | 关键字段 |
|---|---|
| Right | id / rightType / status / sellerId / ownerType / category / serviceAgencyCode / authFileUrl / certFileUrl / rightNo / itemId / itemName / protectStartTime / protectExpireTime / submitProtectExpireTime / extraInfo（侵权统计/平台销量）/ firstPublish / env / test |
| TortRecord | rightId / 侵权平台 / 发现时间 / 巡检次数 / 商品 / 数据源 / 状态 / outerTortId（外部）；关联 RightProtectRecord（维权方式/起止/状态） |
| ServiceTradeRecord | sellerId / tradeType / tradeId / parentTradeId / subOrderId / refundId / incomeId / status / amount(分) / tradeDetail / tradeExtraInfo / bizScene / rightId / rightApplyId / test |

#### 状态枚举（与小二端 21 态 v5 对齐）

- **RightStatusEnum（8 态）**：草稿中/申请中/已驳回/已终止/保护中/保护已失效/转让中/已回转
- **RightApplyStatusEnum（15 态）**：跨初审/预审/认证三阶段；`ApplyOperateTypeEnum` 严格约束前置/目标
- **TradeStatusEnum**：进行中/成功/失败
- **RefundApplyStatusEnum**：审批中/审批通过/退款中/已退款/审批拒绝
- **TradeBizSceneEnum**：充值/商家退款/首发补贴退款/服务完结确收/服务完结退款
- **SettleStatusEnum**：待处理/处理中/已完成/取消/不需要
- **RightProtectStatusEnum** + **RightTortStatusEnum**：维权中/成功/失败；侵权 待维权/维权中/已下架/未下架
- **PlatformEnum**：淘宝/天猫/抖音/小红书/拼多多/京东
- **RightTypeEnum**：外观专利/商标/著作权

### 3.7 外部依赖（Facade）

| Facade | 职责 |
|---|---|
| YcServiceAgencyFacade | 对接服务机构（专利代理）：提交申请/补正/终止/撤销/同步审核 |
| ServiceMarketFacade | 阿里服务市场：退款申请、确收插入、UnSubApply 退款实体 |
| DocumentFacade | 法务文档渲染：承诺书、合同 |
| MetaqFacade | 消息门面（topic+tag+key+body+delay level） |
| UicFacade | 用户中心：主账号、入驻状态 |
| ItemFacade / ItemHsfService | 商品中心：解析 URL、商品下架/变更 |
| TairService / LockService | Tair 缓存与分布式锁 |
| TBSession / TaoLoginUtil | 商家身份/主账号解析 |

### 3.8 Diamond 配置项

| 配置类 | 用途 | 关键属性 |
|---|---|---|
| HsfConfig | HSF 客户端 | 服务版本/超时 |
| UicConfig | UIC | appKey/env |
| OssConfig | OSS | bucket/AK/endpoint |
| FuwuConfiguration | 服务市场 | **ownsign（daily/pre/product 三档不同）**、appKey、secret |
| YcCommonConfig | 业务参数 | 保护期参数（+1年-30天、+180天）、商品发布链接模板、首发判定阈值 |
| RightConstant | 权利常量 | 侵权统计 key、特征 key |
| RightSettleConstant | 结算金额 | **基础服务费 500/SKU、首发补贴 302、非首发 202、官费 165**、测试金额开关 |
| application-{env}.properties | Spring Profile | MetaQ consumerGroup / Tair namespace / SchedulerX2 groupId |

### 3.9 后端代码风险点（30 条）

#### 事务边界
1. **executeAfterCommit 后消息发送失败无补偿**：commit 后 MetaQ 发送失败（broker 抖动），DB 已提交但监听器永不驱动后续动作（对接服务机构、渲染承诺书）；目前未见显式补偿 Job。
2. **保存权利+保存申请未在显式 @Transactional**：草稿首次同时新建 Right + RightApply；Right 成功 RightApply 失败留下脏权利。
3. **finishRefund 状态变更 + 服务计数重建 + 发消息**：计数重建抛异常时状态已落库；并发同卖家多笔退款计数可能重复减扣或漏减。

#### 并发
4. **finishRefund 锁粒度仅退款ID+卖家ID，但服务计数读写未在锁内**：A 完成读 status=SUCCESS 计数；B 同时完成抢先更新；A 计数基于过期数据写入。
5. **提交申请未见显式 LockService**：极速双击可能产生两条 RightApply（不同 id 同 sellerId 同 productName）；建议加幂等键唯一索引。
6. **白名单 addForSeller 与商家入驻状态变更并发**：入驻状态被撤销但白名单写入成功 → 非入驻商家在白名单。
7. **TortDomainServiceImpl 批量新增侵权幂等仅"外部ID存在则跳过"未加锁**：并发投递两个请求同时通过校验 → 插入两条相同 outerTortId 记录；需依赖 (rightId, outerTortId) 唯一索引兜底。

#### 异步消息可靠性
8. **MetaQ 消费失败 RECONSUME_LATER 无限重试**：RightApplyMessageListener 消费"证书已同步"时服务机构 RPC 不可用 → 反复重试触发证书缓存重复写 Tair；超过最大次数进死信，证书永不缓存；需查 DLQ 处理策略。
9. **延迟级别跨环境不一致**：daily/pre/product 三套 FuwuConfiguration 不同；预发延迟 1s 而生产 10s，定时类业务行为不一致。
10. **消息发送失败兜底缺失**：MetaqFacade.send 异常被吞或仅日志，无补偿落库。

#### 重复消费
11. **ServiceRefundMessageListener 退款消息无 dedupe 表**：at-least-once 投递特性下同 refundId apply 消息消费两次，第二次进入 startRefund 写入第二条退款记录；需 refundId 唯一索引兜底。
12. **TortMessageListener new tag 重复消费**：跳过策略未在事务+锁内，重复消费时第二次校验仍判不存在（前次未提交）；需 (rightId, outerTortId) 唯一索引。
13. **Job + 消息重复触发同一动作**：ServFinishRefundJob 扫描与退款结果消息可能交错，Job 在结果消息前再次扫描同一未完成单 → 重复发起退款。

#### 状态机异常迁移
14. **RightApplyStatusEnum 15 态非法迁移**：TOP `syncAuditOperation` 接口外部机构若误传"认证已授权 → 初审补正"等非法迁移；需 ApplyOperateTypeEnum 校验前置状态；穷举 15×15 矩阵；尤其补正回退（初审补正 → 初审中等）勿误回到错误阶段。
15. **updateApply 仅允许补正状态时更新，绕过校验直接走 saveTemporary 可能更新已提交申请**：构造 status=初审中 调用 saveTemporary 验证拒绝。
16. **终止/撤销允许集合**：商家在 `已授权 / 证书已同步` 后请求终止，服务机构可能已花费成本；需逐状态测 terminate/cancel 允许集合。
17. **RightStatusEnum 终态被误恢复**：管理员强制变更（RightToolHsfService）跳过状态机；运营工具操作入口隐蔽。
18. **保护期 min(认证申请+1年-30天, 一致性通过+180天) 边界**：跨年时区、闰年 2/29、UTC vs 本地时间；首发标记修正会触发 submitProtectExpireTime 重算。
19. **firstPublish 与补贴金额联动**：补贴 302（首发）vs 202（非首发），setFirstPublish 在保护期开始后改写可能产生补贴金额不匹配的结算单；变更顺序敏感。
20. **侵权状态与维权状态 1-1 映射断裂**：syncRightProjectResult 只同步维权状态而漏更新侵权状态 → 下架率统计偏差；双表更新需同事务。

#### 其他
21. **白名单千牛 TTYCBH 权限控制硬编码主账号 ID**：测试账号必须在 daily/pre 列表内；预发用生产账号会被拒绝。
22. **测试环境隔离 test=true 标记泄漏**：DMS 直接改表或 API 跨环境调用产生 test=true 但 env=production 脏数据；跨环境隔离需 ali_env_sign + test 双校验。
23. **OSS/STS 文件 URL 失效**：身份证、产品图、证书 URL 存 DB；STS 临时凭证过期后不可访问；需确认存的是永久 URL 还是签名 URL。
24. **跨平台 outerTortId 命名空间冲突**：不同平台 outerTortId 数值可能相同；幂等键不带 platformEnum 误跳过；TortRecord 唯一索引须含 platform。
25. **TOP 接口鉴权与防重放**：syncAuditOperation 等需校验签名 + timestamp + nonce；模拟过期 timestamp / 重复 nonce。
26. **分布式锁释放异常**：finally 释放锁，JVM crash 依赖 Tair TTL；TTL 短锁早释放产生并发，长则故障恢复慢。
27. **定时任务串行性能瓶颈**：4 个 Job 逐笔扫描；结算单堆积时单次 Job 跑超时；超时是否触发重跑导致重复处理。
28. **HSF 工具接口缺乏审计**：小二强制变更状态/手动补录侵权记录无操作日志；运营误操作回滚困难。
29. **Right.extraInfo JSON 字段被多方读写**：侵权统计、平台销量、维权统计共用；并发更新无 CAS 会丢字段；需检查 update 是全量覆盖还是 JSON_SET。
30. **Diamond 动态配置变更不立即生效**：YcCommonConfig 保护期参数变更后已运行 Job 仍用旧值；不同机器拉取时间差致部分订单按新值、部分按旧值。

---

## 四、QA 测试快速索引

### 4.1 Top 5 优先排查
1. 风险 #7/#12（后端）：MetaQ 重复消费 + 外部 ID 唯一索引兜底（侵权/维权幂等）
2. 风险 #4（后端）：finishRefund 服务计数重建并发安全
3. 风险 #18（后端）：保护期计算闰年/时区/双取最小值边界
4. 风险 #20（后端）：侵权 ↔ 维权状态双表更新断裂导致下架率统计偏差
5. 风险 #13（后端）：Job + 消息重复触发同一退款动作

### 4.2 商家端 P0 用例
- 专利申请提交：applyType（QUICK/PRE/REGUALR）× saveOrApply（save/apply）× 快审/初审
- 三阶段补充材料（PRE_PRE/PRE/CERT）
- 商品绑定批量部分成功
- 维权批量提交
- 签约失败回退

### 4.3 小二端 P0 用例
- 21 种 applyStatus × regularApply（true/false）详情抽屉时间轴
- 筛选项 status/applyStatus 二分组参数装配正确性
- 快审表单（必填校验、sellerId 反查、OSS 上传失败回显）
- 是否首发可编辑/不可编辑边界（firstPublishAvailable + firstPublishEditEndTime）
- 网关包装异常（fail=true / success=false / 三层解包某层 null）

### 4.4 后端 P0 用例
- 保护到期日 min 双值边界（构造 2024/02/29、跨年、跨时区）
- MetaQ 重复投递（手动重投同 refundId / outerTortId）
- finishRefund 并发同卖家多笔退款（计数最终一致性）
- TOP syncAuditOperation 非法状态迁移（穷举 15×15 矩阵中关键反例）
- 跨平台同 outerTortId 投递

### 4.5 测试环境核对
- 预发：商家 `pre-fsyc.taobao.com`，小二 `pre-xiaoer.alibaba-inc.com/bzb/noone/taotian-apparel-original-protection-xiaoer/list`
- 生产：商家 `ttfsycbh`
- 千牛白名单：TTYCBH（测试账号必须在硬编码白名单中）
- 测试账号：isv 项目测试专用（主）/ 测试账号八载02（备）
- DB（生产只读）：`scenario @ 33.9.212.198:3011`，--db prod；表 `yc_right` / `yc_right_apply` / `yc_right_settle_order` / `yc_service_trade_record`

---

## 附录：a1 CLI 速查

```bash
# 查看仓库信息
a1 repo view --repo industry-source-code/original-protection
a1 repo view --repo bzb-westeros/taotian-apparel-original-protection-xiaoer
a1 repo view --repo industry-serverless-apps/taobao-yc-serverless

# 列目录
a1 repo file list --repo {repo} [path]

# 查文件
a1 repo file view --repo {repo} {path}

# 搜索代码
a1 repo search "{keyword}" --repo {repo}
a1 repo search "{keyword}" --repo {repo} --lang Java

# 后端预生成 wiki（在另一仓库下）
a1 repo file view --repo domain-knowledge-base/qoder-knowledge-engine \
  industry-serverless-apps/taobao-yc-serverless/repowiki/zh/content/项目概述/项目概述.md
```
