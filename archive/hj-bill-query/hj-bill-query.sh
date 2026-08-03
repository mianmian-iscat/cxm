#!/bin/bash
# 汇金平台账单查询 - 一键执行脚本
# 用法：./hj-bill-query.sh <订单号> <业务类型 1> [业务类型 2] ...

set -e

ORDER_ID="$1"
shift
BIZ_TYPES=("$@")

if [ -z "$ORDER_ID" ] || [ ${#BIZ_TYPES[@]} -eq 0 ]; then
    echo "用法：./hj-bill-query.sh <订单号> <业务类型 1> [业务类型 2] ..."
    echo "示例：./hj-bill-query.sh 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS"
    exit 1
fi

echo "🔍 开始查询订单：$ORDER_ID"
echo "📋 目标业务类型：${BIZ_TYPES[*]}"
echo ""

# 使用 browser 工具打开页面并获取快照
# 这里需要调用 OpenClaw 的 browser 工具
# 由于这是 shell 脚本，我们通过 sessions_spawn 创建一个子任务来执行

cd ~/.openclaw/workspace/skills/web-automation

# 创建 input.json 用于 web-automation
cat > /tmp/hj-query-input.json << EOF
{
  "id": "hj-bill-query-$ORDER_ID",
  "name": "汇金账单查询：$ORDER_ID",
  "context": {
    "urlPattern": "pre-hjratingconsole.alibaba-inc.com",
    "baseUrl": "https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm",
    "orderId": "$ORDER_ID",
    "targetBizTypes": [$(printf '"%s",' "${BIZ_TYPES[@]}" | sed 's/,$//')]
  },
  "steps": [
    {
      "type": "navigate",
      "url": "https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm",
      "description": "打开汇金账单查询页面"
    },
    {
      "type": "wait",
      "ms": 2000,
      "description": "等待页面加载"
    },
    {
      "type": "fill",
      "field": "outBizId",
      "value": "$ORDER_ID",
      "description": "填写外部订单号"
    },
    {
      "type": "click",
      "text": "一键排查",
      "description": "点击查询按钮"
    },
    {
      "type": "wait",
      "ms": 5000,
      "description": "等待查询结果"
    },
    {
      "type": "screenshot",
      "label": "query-result",
      "description": "截取查询结果"
    }
  ],
  "capture": {
    "enabled": true,
    "filter": "/hjratingconsole/"
  }
}
EOF

echo "📝 已创建 input.json，现在执行查询..."
echo ""

# 执行 Python 脚本
python3 impl.py /tmp/hj-query-input.json

echo ""
echo "✅ 查询完成！结果已保存到 artifacts/ 目录"
