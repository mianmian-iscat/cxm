<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护结算分析/references/fund-flow-model.md -->
<!-- synced-at: 2026-07-14T01:00:04.601894 -->
<!-- skill: 原创保护结算分析 -->

# 资金流向模型

## 角色定义

| 角色 | 说明 | 典型实体 |
|------|------|----------|
| 商家 | 缴费方，也是退款接收方 | seller_id=2213249110271（测试） |
| 平台 | 结算引擎运营方 | 原创保护平台 / 淘宝 |
| 供应商 | 确收接收方（维权服务方） | 维权服务商 |
| 支付通道 | 资金流转通道 | 支付宝 / 网商银行 |

## 资金流向总图

```mermaid
flowchart LR
    subgraph 商家侧
        A[商家账户]
    end
    subgraph 平台侧
        B[原创保护平台]
        C[结算引擎]
        D[补贴账户]
    end
    subgraph 供应商侧
        E[供应商账户]
    end
    subgraph 支付通道
        F[支付宝/网商银行]
    end

    A -->|"① 缴纳服务费<br/>500元(生产) / 10分(测试)"| B
    B -->|② 创建结算单| C
    
    C -->|"③a 退款路径<br/>下架率<70%<br/>退商家33元(非首发)/133元(首发)"| A
    C -->|"③b 确收路径<br/>下架率≥70%<br/>付供应商335元"| E
    
    D -->|"④ 首发补贴<br/>9类商家<br/>33元/133元"| A
    
    F -.->|资金通道| C

    style A fill:#e3f2fd,stroke:#1565c0
    style C fill:#fff9c4,stroke:#f9a825
    style E fill:#c8e6c9,stroke:#2e7d32
    style D fill:#fff9c4,stroke:#f9a825
```

## 退款路径详细流向

```mermaid
sequenceDiagram
    participant Job as SchedulerX
    participant Engine as 结算引擎
    participant DB as scenario DB
    participant Pay as 支付通道

    Job->>Engine: Task 399576024 扫描过期right
    Engine->>DB: yc_right.status = YC_PROTECT_INVALID
    Engine->>DB: 计算下架率
    Engine->>DB: serv_finish_refund_status = TO_DO

    Note over Job: 等待 Task 719211870 (04:00)
    Job->>Engine: Task 719211870 第1次触发
    Engine->>DB: serv_finish_refund_status = PROCESSING
    Engine->>Pay: 发起退款请求
    
    Note over Pay: 支付回调
    Pay->>Engine: 退款成功回调
    Note over Job: 需再次触发
    Job->>Engine: Task 719211870 第2次触发
    Engine->>DB: serv_finish_refund_status = FINISH
    Engine->>DB: settle_status = FINISH
```

## 确收路径详细流向

```mermaid
sequenceDiagram
    participant Job as SchedulerX
    participant Engine as 结算引擎
    participant DB as scenario DB
    participant Pay as 支付通道

    Job->>Engine: Task 399576024 扫描过期right
    Engine->>DB: yc_right.status = YC_PROTECT_INVALID
    Engine->>DB: 计算下架率 ≥ 70%
    Engine->>DB: serv_finish_income_status = TO_DO

    Note over Job: 等待 Task 721504806 (06:00)
    Job->>Engine: Task 721504806 第1次触发
    Engine->>DB: serv_finish_income_status = PROCESSING
    Engine->>Pay: 发起确收请求(335元→供应商)
    
    Pay->>Engine: 确收成功回调
    Job->>Engine: Task 721504806 第2次触发
    Engine->>DB: serv_finish_income_status = FINISH
    Engine->>DB: settle_status = FINISH
```

## 补贴路径详细流向

```mermaid
sequenceDiagram
    participant Seller as 商家
    participant Platform as 平台
    participant ODPS as ODPS快照
    participant DB as scenario DB
    participant Job as SchedulerX

    Seller->>Platform: 提交申请
    Platform->>Platform: SYNC_CERT_FILE(确认商品一致性)
    Platform->>ODPS: 查询商家主营类目快照
    ODPS-->>Platform: 主营类目ID
    Platform->>Platform: 判定是否∈9类白名单
    
    alt 9类商家
        Platform->>DB: init_allowance_start_time = 当前时间
        Platform->>DB: init_allowance_amount = 补贴金额
        Note over Job: Task 715618497 (01:00)
        Job->>DB: 发放补贴到商家账户
    else 非9类商家
        Platform->>DB: init_allowance_start_time = NULL
        Note over Job: 不触发补贴
    end
```

## 下架率计算

```
下架率 = SUCCESS(已下架)数 / 全部侵权记录数(含PROTECTING) × 100%
```

| 下架率 | 分流路径 | 资金方向 |
|--------|----------|----------|
| < 70% | 退款 | 平台 → 商家 |
| ≥ 70% | 确收 | 平台 → 供应商 |
| = 0%（无侵权记录） | 退款 | 平台 → 商家 |

### SQL 计算方式

```sql
SELECT 
    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) AS taken_down,
    COUNT(*) AS total,
    ROUND(COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) * 100.0 / COUNT(*), 2) AS rate_pct
FROM yc_tort_record
WHERE right_id = {rightId} AND env = 'staging';
```
