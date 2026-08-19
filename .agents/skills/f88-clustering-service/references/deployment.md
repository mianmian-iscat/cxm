# 部署与运维手册

## 前置条件

- Python 3.10+ 运行时
- `dms-alibaba` CLI 已安装并完成 OAuth 授权（`dms-alibaba auth login`）
- DMS 数据库组 `stylespot`，数据库 `rm-lgay0v5lor8396yka`（db_id=5335708）
- 钉钉机器人 webhook（可选，用于推送通知）

## 部署步骤

### 第 1 步：上传服务文件

```
f88-clustering-service/
├── app.py              # 主服务（Flask + APScheduler + 聚类逻辑，~670行）
├── config.yaml         # 运行配置（DMS/聚类/调度/钉钉）
├── requirements.txt    # Python 依赖
└── reports/            # HTML 报告输出目录（自动创建）
```

### 第 2 步：安装依赖

```bash
pip install -r requirements.txt
```

依赖列表：flask>=3.0, apscheduler>=3.10, requests>=2.31, scikit-learn>=1.4, jieba>=0.42, pyyaml>=6.0, numpy>=1.26

### 第 3 步：配置环境变量

```bash
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
export DINGTALK_SECRET="SECxxxxx"   # 可选：加签密钥
```

config.yaml 支持 `${ENV_VAR}` 占位符自动展开。

### 第 4 步：验证 DMS CLI 连通性

```bash
dms-alibaba sql run stylespot --db 5335708 \
  --sql "SELECT COUNT(*) AS cnt FROM workflow_record_log WHERE id > 4000000 AND env = 'staging' AND status = 'FAIL' LIMIT 1"
```

### 第 5 步：启动服务

```bash
python app.py                    # 前台（调试）
nohup python app.py > service.log 2>&1 &  # 后台（生产）
```

### 第 6 步：验证部署

```bash
curl http://localhost:5100/health     # 健康检查
curl -X POST http://localhost:5100/run  # 手动触发
ls -la reports/                        # 查看报告
```

## 配置参数说明

```yaml
dms:
  group: stylespot          # dms-alibaba 数据库组名
  db_id: "5335708"          # 数据库 ID
  env: staging              # 红线：只能为 staging
  query_hours: 8            # 每次查询回溯小时数
  max_rows: 2000            # 单次最大采样行数
  id_floor: 4000000         # workflow_record_log id 下限（近期批次可调高至 6400000 缩小扫描范围）

clustering:
  top_k: 5                  # 顶层聚类数
  sub_min_size: 10          # 子聚类触发最小样本量
  tfidf_max_features: 500   # TF-IDF 最大特征维度
  sub_k_range: [2, 5]       # 子聚类 k 搜索范围

schedule:
  hours: [9, 14, 19]        # 每日执行时间
  timezone: Asia/Shanghai

output:
  dir: ./reports            # HTML 报告存储目录
  keep_days: 30             # 报告保留天数

dingtalk:
  webhook: "${DINGTALK_WEBHOOK}"
  secret: "${DINGTALK_SECRET}"
  enabled: true

server:
  port: 5100
  host: 0.0.0.0
```

## API 端点

### GET /health
返回服务状态、scheduler 状态、上次运行结果。

### POST /run
手动触发聚类分析（后台线程，立即返回）。

### GET /config
返回当前配置快照（钉钉 webhook 已脱敏）。

## 数据红线

- **仅查预发数据**：所有 SQL 强制带 `env = 'staging'`
- **只读不写**：只做 SELECT 查询
- **id 下限保护**：查询带 `id > 4000000` 防止全表扫描超时
- **数据不入库**：失败记录仅在内存中处理

## 运维手册

### 日志关键标记

| 标记 | 含义 |
|---|---|
| `[JOB] 开始执行聚类任务` | 定时/手动触发 |
| `[DMS] 获取 N 条失败记录` | 数据拉取完成 |
| `[JOB] 顶层聚类 k=N 完成` | 聚类完成 |
| `[JOB] 报告已生成: reports/xxx.html` | HTML 写入成功 |
| `[DingTalk] 推送成功` | 钉钉通知发送成功 |
| `[JOB] 数据不足（N 条 < 5），跳过聚类` | 正常跳过 |
| `[ERROR]` | 异常，需排查 |

### 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `/health` 无响应 | 服务未启动或端口冲突 | 检查 service.log |
| `dms-alibaba: command not found` | CLI 未安装 | `npm i -g @ali/dms-alibaba` |
| 查询超时 | 未加 id 下限 | 检查 config.yaml 的 `id_floor` |
| 钉钉 403 | webhook 或 secret 错误 | 检查环境变量 |
| 聚类结果全为 1 簇 | 数据量太少或同质化 | 增加 `query_hours` |

### 报告清理

```bash
find reports/ -name "*.html" -mtime +30 -delete
```

## 版本更新日志

### v1.4.0（2026-08-10）
SKILL.md 重构为路由层，部署/算法知识拆分至 references/deployment.md 与 algorithm.md；make_label() 签名库保持与 error-signatures.md v1.1.0 对齐（含 BT_7495/BT_7485/BT_7417）。

### v1.3.0（2026-08-05）
make_label() 签名库与 error-signatures.md v1.1.0 对齐——新增审核平台类（BT_7495/BT_7485）和 LLM JSON 解析类（BT_7417）共 3 类确定性签名。

### v1.2.0（2026-08-04）
新增《生产链路稳定性提升方案》7 类高频错误签名的「治理-N」确定性打标。

### v1.1.0
新增 4 类错误模式正则标签（SharedArrayBuffer/COOP/COEP、subJobId、replaceImage 跨表不一致、BATCH/STREAM 模式差异），新增 execMode 交叉分析维度。
