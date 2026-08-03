<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/缺陷分析分发/references/defect-analysis-templates.md -->
<!-- synced-at: 2026-07-11T03:52:35.008895 -->
<!-- skill: 缺陷分析分发 -->

# 缺陷分析模板

## AOne 缺陷查询命令

### 基础查询
```bash
# 查询项目所有缺陷
a1 workitem list --project {projectId} --type defect --size 50 --page 1

# 查询未闭环缺陷
a1 workitem list --project {projectId} --type defect --status "新建,处理中,重新打开,已修复" --size 50

# 查询指定优先级
a1 workitem list --project {projectId} --type defect --priority "P0,P1" --size 50
```

### F88 项目特殊处理
```bash
# F88项目ID: 2120437
# 使用大淘宝缺陷模版(type 515)创建缺陷
a1 workitem create --project 2120437 --type 515 --title "缺陷标题" \
  --field 141538="关联需求ID" \
  --field 47="测试阶段"
```

## 缺陷状态说明

| 状态 | 含义 | 是否闭环 |
|------|------|---------|
| 新建 | 刚创建，未指派 | 否 |
| 处理中 | 已指派，开发处理中 | 否 |
| 已修复 | 开发修复，待验证 | 否 |
| 已验证 | 测试验证通过 | 是 |
| 已关闭 | 确认关闭 | 是 |
| 重新打开 | 验证不通过，重新打开 | 否 |
| 已拒绝 | 非缺陷或重复 | 视情况 |

## 钉钉消息模板

### 个人缺陷通知（Markdown格式）
```markdown
### 【缺陷提醒】{项目名} - {日期}

**{姓名}**，以下是你当前负责的未闭环缺陷：

| ID | 标题 | 优先级 | 状态 | 滞留天数 |
|----|------|--------|------|---------|
| {id} | {title} | {priority} | {status} | {days}天 |

请及时处理，详情查看 [缺陷列表]({url})
```

### 团队缺陷周报（ActionCard格式）
```json
{
  "title": "【缺陷周报】{项目名} {日期范围}",
  "text": "## 缺陷周报 - {项目名}\n\n**{日期范围}**\n\n### 概览\n- 总缺陷: **{total}**\n- 未闭环: **{unclosed}**\n- 闭环率: **{rate}%**\n\n### 本周变化\n- 新增: **{new}** | 关闭: **{closed}**\n\n### P0/P1 超期未处理\n{overdue_list}",
  "btns": [
    {"title": "查看详情", "actionURL": "{detail_url}"},
    {"title": "我的缺陷", "actionURL": "{my_url}"}
  ]
}
```

## 数据分析SQL模板

### 按状态统计
```
缺陷总数: {total}
├── 已闭环: {closed} ({closed_rate}%)
│   ├── 已验证: {verified}
│   └── 已关闭: {closed_status}
└── 未闭环: {unclosed} ({unclosed_rate}%)
    ├── 新建: {new}
    ├── 处理中: {processing}
    ├── 已修复待验证: {fixed}
    └── 重新打开: {reopened}
```

### 按团队统计
```
| 团队/负责人 | 总数 | 未闭环 | P0 | P1 | 超期 |
|------------|------|--------|----|----|------|
| {team1}    | {n}  | {n}    | {n}| {n}| {n}  |
| {team2}    | {n}  | {n}    | {n}| {n}| {n}  |
```
