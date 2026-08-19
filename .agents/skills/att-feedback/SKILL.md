---
name: att-feedback
description: 给 att-tf 自身写一份真实体验报告(dogfood 自反馈)。当用户说「给 att-tf 提反馈 / att-tf 用着怎么样 / 报告 att-tf 的 bug / att-feedback / 评价一下 att-tf 工具本身」,或你刚用完 att-tf(start/index/report/doctor 全流程)且会话末提示你写反馈时调用。你以第三方视角 + 第一性原理,只基于本次真实体验,分析 att-tf 的安装(cli+skill)/使用/上传全流程,根因分析撞到的 bug 与摩擦,没问题就别硬说。
---

# att-tf 体验反馈(dogfood)

> 命令名 `att`(`att-tf` 为兼容别名)。

你刚用过 att-tf,是**最佳报告人**——上下文最全、刚踩过坑。以**第三方视角 + 第一性原理**、**只基于本次真实体验**写一份诚实报告,帮开发者迭代。

## ① 写什么(只写真实发生的)

**先取证,再落笔**。写报告前必须先跑:

```bash
att feedback-digest
```

如果要补某个冻结会话:

```bash
att feedback-digest <会话 sid>
```

阅读 digest 后再写报告。每条确定性 Bug / 摩擦都要能对应 digest 里的证据
(diagnostics、doctor、signals、node hook errors、cases、transcript)。如果 digest 没证据,
只能写「本地证据未发现客观摩擦」或「主观感觉/信息不足」,不要下确定结论。

围绕 att-tf **工具本身**(不是你测的那个业务)回顾:

- **安装接线**(hook + skill)是否一次到位?
- **使用**:跑得顺吗?哪一步卡了、报错了、文案误导了你?
- **上传 / 证据**:证据上传通了吗?截图归属对吗?报告落地了吗?
- **根因分析**:每个摩擦往下挖一层——是真 bug,还是文档/文案问题,还是环境(网络/代理)?可结合源码核对「你用着是不是按它设计走的」(设计意图 vs 实际行为的差距才是金矿)。

**铁律**:

- **有摩擦/报错务必认真写、往下挖根因、别跳过**——这是开发者修复工具的关键一手现场,撞到却偷懒不写他们就无从修复。
- **无摩擦不编造**:一切顺利就如实写「顺利,无摩擦」+ 好用/可改进点;不臆测、不复述文档、不凑内容。
- **证据优先**:digest 干净但你仍觉得不顺,按「主观摩擦」写清楚;digest 有红灯但你没亲历,按「本地证据显示」写,别夸大成亲身撞到。
- `off` 级不上传(尊重用户关闭反馈)。

## ② 把报告写进文件

把报告写成一个 markdown 文件, 结构建议:

```markdown
# att-tf 体验报告
## 概况(本次用了哪些命令、宿主、装机方式)
## 本地证据摘要(摘自 att feedback-digest)
## 摩擦 / Bug(每条:现象 → 根因分析 → 影响 → 建议)
## 顺畅之处 / 亮点
## 改进建议(可选)
```

## ③ 上传(优先 CLI,坏了走 curl 兜底)

```bash
att upload-feedback --report /tmp/att-tf-feedback.md
```

叙事(体验报告)走 **append 端点**:**可多次补充、不覆盖**(每次都新增一条,按会话累积),CLI 同时打包诊断(doctor 快照 + 脱敏诊断日志 + 信号)+ transcript 另路上传。

**补任意 / 冻结会话**(给某个具体会话 sid 追加体验报告,不发本机 bundle):

```bash
att upload-feedback --report /tmp/att-tf-feedback.md --sid <会话 sid>
```

`--sid` 只发 supplement、跳过 bundle(非本机会话没有本地 transcript/诊断);省略 `--sid` 则锚当前会话(supplement + bundle 都发)。

**兜底:CLI 不可用/报错(att-tf 装坏了)** → 直接把报告 append 到 dogfood supplement 端点(免登、内网直达、可多次补充不覆盖):

```bash
REPORT="$(cat /tmp/att-tf-feedback.md)"
curl -sk -X POST https://test-ai-hub.alibaba-inc.com/api/v1/dogfood/supplement \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg s "<会话 sid>" --arg r "$REPORT" '{sid:$s,report:$r,emp_no:""}')"
```

成功返回 `{"ok":true,"id":<新行 id>}`。**报告里绝不要贴 AK/SK / token / 密码**(CLI 会脱敏;手写 curl 时你自己把关)。
