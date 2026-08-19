# 种草素材错误码/错误信息速查

> 来源：workflow_record_log.extra_info.errorMsg、回流表 ext_info.publishFailReason、交付群实战记录。
> 原则：先区分「数据问题（非缺陷）/ 配置问题 / 真实 Bug」，真实 Bug 须重新造数复验后才可确认。

## 图文上传节点（image_text_upload）失败

| 错误信息 | 含义 | 排查方向 | 定性 |
|----------|------|----------|------|
| `[LESS_PHOTO_MIN] 至少需要上传3张图片哦` | imageList 图片数 <3 | 查上游 approve passedImg 数量；确认入参图片数组长度 | 校验正确，数据问题（BT_7072 实例） |
| `[PIC_RADIO_NOT_VALID] 图片尺寸必须3:4或者1:1 且不可混搭` | 生成图尺寸不符或 3:4/1:1 混搭 | 查 gen_img 产出尺寸；同一批不可混用两种比例 | 上游生图数据问题，非节点缺陷（BT_7030/6997/6996） |
| `图文上传发布失败，contentId 为空` | 纵横发布未返回 contentId | **第一步**查 image_list 是否为逗号分隔字符串（必须 JSON 数组）；排除后才是纵横侧真实失败 | 多为入参格式问题（BT_7073 实例） |
| `素材数量已达上限` | 商家/达人内容池坑位已满 | 查回流表该 seller/userId 历史 status=6 条数；与产品确认坑位上限 | 业务限制，非链路 bug（2026-07-27 生产实例，考鱼定位） |
| `变量解析失败` / `sellerId 为空` | 商家模式 sellerId 变量未解析 | 查链路配置 sellerId 变量引用是否指向有效上游变量（如 inputParams.seller_id） | 配置问题 |
| `商家不存在` / `卖家不存在` | sellerId 对应商家无效 | 核对 sellerId 数值 | 数据问题 |
| `商品不属于该卖家` | itemId 与 sellerId 不匹配 | 核对商品归属 | 数据问题 |
| 权限相关提示 | sellerId 商家无内容发布权限 | 找纵横侧确认商家发布权限 | 外部依赖 |
| `标题超长`（title >20 字符） | 标题超限 | 查 llm_text 产出 title 长度；配置侧应有限制 | 数据/配置 |
| `文案超长`（text >1000 字符） | 文案超限 | 同上 | 数据/配置 |
| `图片列表为空` | imageList 变量解析为空 | 查上游 approve/gen_img 是否有产出 | 上游问题 |
| 上游原始错误（ContentFacade 返回） | 纵横接口异常/限流 | 同商品 1s 内重复发布有 Tair 限流锁；看 errorMsg 中上游原文，找考鱼/纵横侧 | 外部依赖 |
| `批次终止` | 批次 TERMINATED 后节点 start | 查批次为何被终止 | 预期防护 |

## 审核节点（approve）失败

| 错误信息 | 含义 | 排查方向 | 定性 |
|----------|------|----------|------|
| `CommonRspCode(rspType=1, rspCode=99999, toastMsg=图片素材错误)` | ApproveProcessor 收集图片素材失败（兜底错误） | **首要排查**：策略 approveType 与审核节点 qt 类型是否一致；节点类型是否被修改但链路配置未同步。常见根因：①approveType=1（单图审核已下线）与 qt=2 套图节点不匹配 ②审核节点从套图改为首图后链路 approveType 未更新 ③imgUrlReview 字段配置缺失 | 配置问题（非代码缺陷） |
| `g_afd_review_job 无主任务` | 审核任务创建失败（事务回滚） | 通常是 rspCode=99999 的伴随现象；查 ApproveProcessor 异常堆栈 | 配置问题 |

> **2026-08 种草批次案例**：策略选了套图审核节点配到链路，后审核节点从套图改为首图，链路运行时仍走套图逻辑，175 条集中报 `rspCode=99999 图片素材错误`。根因是节点类型变更后链路配置未同步。

## 发布成功但下游不可见

| 现象 | 排查方向 |
|------|----------|
| 节点 SUCCESS，回流表 status=6，商家端看不到 | 确认登录的是 sellerId 对应商家账号；myseller.taobao.com 素材管理中心「推荐」Tab；内容平台分发有延迟 |
| 节点 SUCCESS，回流表 status=6，纵横查不到 | 用 ext_info.contentId 在 content.alibaba-inc.com 查；达人内容池与商家内容池不同 |
| 节点 SUCCESS，回流表**无记录** | 发布回流（MySQL→ODPS 定时同步）未触发/延迟；注意节点 output_json={} 是现状，contentId 本来就不落 workflow_record_log |
| 回流表 status=7 | 看 ext_info.publishFailReason，对照上表 |

## 调度层（商品未进入种草生产）

| 现象 | 可能原因 | 定性 |
|------|----------|------|
| 非女装商品无种草任务 | 女装过滤（一级类目=16），三入口直接跳过且**不落 PENDING** | 预期行为（2026-07 需求 84528309） |
| F0 商品素材数≥6 不再生产 | P2 坑位已满（口径 feeds_publish_scene='item_self_content'） | 预期 |
| 商品已生产过不再出现 | 疲劳度去重 | 预期 |
| 周末/节假日 P3 无新任务 | P3 定时器仅工作日 | 预期 |
| 预发达人定时器不触发 | 已知预发环境现象 | 非功能问题，勿做基线 |
| 队列高峰期排队 | 队列上限 2000，每小时补 (2000-n)/6 | 预期 |
| ODPS 分区缺失导致取数空 | ads_tb_fashion_f88_itm_agg 最新分区未产出 | 上游数据延迟，查分区 |

## 配置/脚本侧高频坑（排查工具自身防坑）

| 坑 | 说明 |
|----|------|
| 商家枚举写成 MERCHANT_IMAGE_TEXT | 实际是 `SEEDING_IMAGE_TEXT_SELLER` |
| workflowDef 节点字段写成 nodes | 实际是 `innerNodes` |
| seed_image_url / image_list 传逗号字符串 | 必须 JSON 数组，否则发布失败 |
| dms-alibaba 缺 `--db 5335708` | CLI 返回用法报错文本，会被误判为"无数据" |
| requests 裸调预发 API | httpOnly SSO cookie 取不到，返回登录页 HTML；走浏览器 fetch / CachedSession |
| 旧数据无 uploadType 字段 | 兜底 SEEDING_IMAGE_TEXT（达人），加载/重试不报错属正常 |

## 真实案例索引

| 日期 | 案例 | 根因 | 来源 |
|------|------|------|------|
| 2026-07-23 | BT_7072 图文上传失败 | 只传 1 张图，LESS_PHOTO_MIN 拦截 | 测试造数 |
| 2026-07-23 | BT_7073 图文上传失败 | image_list 逗号字符串，contentId 为空 | 测试造数 |
| 2026-07-23 | BT_7030/6997/6996 失败 | 生成图尺寸不符 PIC_RADIO_NOT_VALID | E2E |
| 2026-07-27 | 生产图文上传失败 | 素材数量已达上限 | AFD种草合作群（俨冰/考鱼） |
| 2026-07-24 | 达人 1027873092 预发定时器未触发 | 预发环境现象，非功能问题 | 测试报告 |
