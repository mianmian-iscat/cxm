<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/日志排查诊断/references/sls-diagnosis-methodology.md -->
<!-- synced-at: 2026-07-11T03:52:35.008653 -->
<!-- skill: 日志排查诊断 -->

# SLS 日志诊断方法论

## 查询语法速查

### 基础搜索
```
level:ERROR                           # 按日志级别
level:ERROR AND keyword               # 组合搜索
message:"OutOfMemoryError"            # 精确搜索
message:OutOfMemory*                  # 通配符搜索
traceId:"abc123def456"                # TraceId追踪
```

### 分析语法（管道后使用SQL）
```
# 错误类型分布
level:ERROR | SELECT errorMessage, COUNT(*) as cnt GROUP BY errorMessage ORDER BY cnt DESC LIMIT 20

# 错误时间分布（5分钟粒度）
level:ERROR | SELECT date_format(__time__ - __time__ % 300, '%H:%i') as t, COUNT(*) as cnt GROUP BY t ORDER BY t

# 按服务分组统计
level:ERROR | SELECT serviceName, COUNT(*) as cnt GROUP BY serviceName ORDER BY cnt DESC

# 最近N条错误
level:ERROR | SELECT * ORDER BY __time__ DESC LIMIT 50

# 统计某个接口的错误率
api:"/api/v1/resource" | SELECT 
  COUNT(CASE WHEN level='ERROR' THEN 1 END) * 100.0 / COUNT(*) as error_rate,
  COUNT(*) as total
```

### 常用时间函数
```
# 按小时统计
date_trunc('hour', __time__)

# 按5分钟统计
date_format(__time__ - __time__ % 300, '%H:%i')

# 时间范围过滤（在SQL中）
__time__ >= unix_timestamp() - 3600  # 最近1小时
```

## 排查决策树

```
问题报告
├── 有traceId？
│   ├── 是 → 按traceId查完整调用链 → 定位第一个出错节点
│   └── 否 → 按关键词+时间搜索错误日志
│
├── 找到错误日志？
│   ├── 是 → 分析错误堆栈
│   │   ├── NPE → 检查空值来源（上游参数/DB查询/缓存）
│   │   ├── Timeout → 检查下游服务响应时间 + 网络状况
│   │   ├── BizException → 检查业务规则触发条件
│   │   ├── DBException → 检查SQL + 连接池 + 锁等待
│   │   └── 其他 → 检查异常类型特有处理逻辑
│   │
│   └── 否 → 扩大搜索范围
│       ├── 检查其他Logstore
│       ├── 检查是否有日志采集延迟
│       └── 确认问题是否发生在客户端
│
└── 定位到根因？
    ├── 是 → 输出诊断报告
    └── 否 → 扩展分析
        ├── 对比同时段正常请求
        ├── 检查近期发布变更
        └── 检查系统资源指标
```

## 诊断报告模板

```markdown
## 问题诊断报告

### 问题概述
{一句话描述}

### 影响评估
- 影响范围：{功能/用户/时间段}
- 严重程度：P{0-3}
- 持续时长：{时长}

### 根因分析

**直接原因**：
{导致错误的具体代码位置和操作}

**根本原因**：
{为什么会出现这个问题}

**关键证据**：
```
{关键日志片段}
```

### 时间线
| 时间 | 事件 |
|------|------|
| HH:MM | 问题开始 |
| HH:MM | 问题被发现 |
| HH:MM | 根因定位 |

### 修复建议
- **短期止血**：{临时解决方案}
- **长期修复**：{根本解决方案}

### 预防措施
1. {措施1}
2. {措施2}
```
