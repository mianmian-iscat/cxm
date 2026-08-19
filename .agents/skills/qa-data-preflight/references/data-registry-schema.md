# Data Registry Schema

Data Registry 是 qa-data-preflight 的核心配置，定义"什么数据怎么造、怎么验、依赖什么"。

## 目录结构

```
references/
├── data-registry-schema.md    ← 本文件（schema 定义）
├── f88-registries.md          ← F88/i-FASHION 业务域的注册条目
├── yc-registries.md           ← 原创保护业务域的注册条目（待建）
└── ...                        ← 其他业务域按需添加
```

## Registry 条目 Schema

每个数据类型在 Registry 中注册为一个条目，YAML 格式：

```yaml
# Data Registry Entry Schema
data_type: string              # 数据类型唯一标识（如 template_package）
display_name: string           # 可读名称（如 "模板包"）
domain: string                 # 业务域（f88 / yc / common）

# 造数能力
create_skill: string           # 调用的造数 skill 名称（如 f88-template-package-create）
create_method: enum            # 造数方式：skill / api / browser / sql
params_template:               # 传给造数 skill 的参数模板
  param_name: value            # 支持占位符 {gap.deficit.xxx}

# 验证能力
verify_query: string           # 验证数据就绪的 SQL 查询
verify_method: enum            # 验证方式：sql / api / page
min_threshold:                 # 最低阈值（可以是数量或多样性）
  field: min_value             # 如 cateId: 5

# 依赖关系
depends_on: list[string]       # 前置依赖的数据类型列表
cooldown_ms: integer           # 造数后等待生效的时间（毫秒）

# 重试策略
max_retries: integer           # 最大重试次数（默认 3）
backoff_ms: list[integer]      # 退避间隔（默认 [30000, 60000, 120000]）

# 元数据
description: string            # 数据类型描述
affected_cases_hint: string    # 数据不足时影响的用例类型提示
last_verified: datetime        # 上次验证时间（运行时更新）
```

## 条目示例

### 模板包（F88）

```yaml
data_type: template_package
display_name: 模板包
domain: f88

create_skill: f88-template-package-create
create_method: skill
params_template:
  applyRange: "{gap.requirement.applyRange}"
  applyScene: "{gap.requirement.applyScene}"
  cateId: "auto_diverse"       # skill 内部自动选择多样化 cateId
  styleTags: "auto_diverse"    # skill 内部自动选择多样化 styleTags
  count: "{gap.deficit.cateId}"  # 需要创建的数量 = 缺口数

verify_query: |
  SELECT
    COUNT(DISTINCT cate_id) as cate_cnt,
    COUNT(DISTINCT style_tags) as tag_cnt
  FROM template_package
  WHERE env='staging'
    AND status IN (3, 4)
    AND apply_range = '{gap.requirement.applyRange}'
    AND apply_scene = '{gap.requirement.applyScene}'
verify_method: sql
min_threshold:
  cate_cnt: "{gap.requirement.cateId.min_distinct}"
  tag_cnt: "{gap.requirement.styleTags.min_distinct}"

depends_on: []
cooldown_ms: 5000

max_retries: 3
backoff_ms: [30000, 60000, 120000]

description: F88 模板包数据，需保证 cateId 和 styleTags 的多样性
affected_cases_hint: 模板匹配相关用例（风格排序/CTR排序/Clone去重/排序组合）
```

### 策略配置（F88）

```yaml
data_type: strategy_config
display_name: 策略配置
domain: f88

create_skill: f88-link-config-check
create_method: skill
params_template:
  nodeType: "{gap.requirement.nodeType}"
  action: "verify_and_fix"

verify_query: |
  SELECT COUNT(DISTINCT id) as cnt
  FROM g_strategy
  WHERE env='staging'
    AND status = 1
    AND workflow_def LIKE '%{gap.requirement.nodeType}%'
verify_method: sql
min_threshold:
  cnt: "{gap.requirement.count.min}"

depends_on: [template_package]
cooldown_ms: 3000

description: F88 策略配置，需保证特定 nodeType 的策略存在
```

### 批次数据（F88）

```yaml
data_type: batch_data
display_name: 批次数据
domain: f88

create_skill: strategy-platform
create_method: skill
params_template:
  action: "trigger_batch"
  linkId: "{gap.requirement.linkId}"

verify_query: |
  SELECT COUNT(*) as cnt
  FROM g_workflow_batch
  WHERE env='staging'
    AND relation_id = '{gap.requirement.linkId}'
    AND status IN ('SUCCESS', 'FAIL', 'HANDLING')
verify_method: sql
min_threshold:
  cnt: 1

depends_on: [strategy_config]
cooldown_ms: 60000             # 批次执行需要较长时间

description: F88 策略批次数据，通过触发链路生产
```

## 占位符语法

`params_template` 和 `min_threshold` 中支持以下占位符：

| 占位符 | 含义 | 示例值 |
|--------|------|--------|
| `{gap.requirement.xxx}` | 用例声明的数据需求 | `{min_distinct: 5}` |
| `{gap.deficit.xxx}` | 当前值与需求的差值 | `4` |
| `{gap.current.xxx}` | 当前环境数据现状 | `1` |
| `{gap.registry.xxx}` | Registry 中配置的参数 | `COLLOCATION` |

## 扩展新数据类型

添加新的数据类型只需：

1. 在对应业务域的 registries 文件中新增一个条目
2. 填写所有必填字段（data_type / create_skill / verify_query / min_threshold）
3. 确保 `create_skill` 对应的 skill 已安装
4. 确保 `verify_query` 的 SQL 已验证可执行

不需要修改 qa-data-preflight 的逻辑——Registry 是纯配置驱动的。
