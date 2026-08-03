#!/bin/bash
# devix-run.sh — Devix 云端执行入口
#
# 由 Devix cron job 或手动调用，在云端沙箱中执行回归测试。
#
# 用法:
#   bash scripts/devix-run.sh <input.json>
#   bash scripts/devix-run.sh <input.json> <output.json>
#
# 环境变量（由 Devix 平台注入）:
#   DEVIX_CDP_WS_URL    — 云端浏览器 WebSocket CDP 端点（wss://...）
#   DEVIX_COOKIES_JSON   — 登录态 Cookie JSON 字符串
#   WEB_AUTO_SKIP_SSO_WARMUP — 是否跳过 SSO 预热（默认 true）
#
# 示例:
#   export DEVIX_CDP_WS_URL="wss://xxx.agentrun-data.cn-hangzhou.aliyuncs.com/..."
#   export DEVIX_COOKIES_JSON='[{"name":"SSO_LANG_V2","value":"...","domain":".alibaba-inc.com"}]'
#   bash scripts/devix-run.sh scenes/f88-test/cases/tc01-merchant-login-redirect.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# ── 运行时环境变量 ──
export WEB_AUTO_RUNTIME="${WEB_AUTO_RUNTIME:-agentbay}"
export WEB_AUTO_CDP_WS_URL="${DEVIX_CDP_WS_URL:-${WEB_AUTO_CDP_WS_URL:-}}"
export WEB_AUTO_COOKIES_JSON="${DEVIX_COOKIES_JSON:-${WEB_AUTO_COOKIES_JSON:-}}"
export WEB_AUTO_SKIP_SSO_WARMUP="${WEB_AUTO_SKIP_SSO_WARMUP:-true}"

# ── 前置检查 ──
if [ -z "$WEB_AUTO_CDP_WS_URL" ]; then
  echo "[devix-run] 错误: 未设置 DEVIX_CDP_WS_URL 或 WEB_AUTO_CDP_WS_URL" >&2
  echo "[devix-run] 请提供云端浏览器 WebSocket CDP 端点" >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/devix-run.sh <input.json> [output.json]" >&2
  exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="${2:-}"

echo "[devix-run] 运行环境: $WEB_AUTO_RUNTIME"
echo "[devix-run] WebSocket: ${WEB_AUTO_CDP_WS_URL:0:60}..."
echo "[devix-run] SSO 预热: $WEB_AUTO_SKIP_SSO_WARMUP"
echo "[devix-run] 输入文件: $INPUT_FILE"

# ── 安装依赖（首次运行时）──
if [ ! -d "node_modules/puppeteer-core" ]; then
  echo "[devix-run] 安装 Node 依赖..."
  npm install --production 2>/dev/null || true
fi

# ── 执行测试 ──
echo "[devix-run] 开始执行..."
START_TIME=$(date +%s)

# 优先使用 python3（macOS / 多数 Linux 默认），回退 python
PYTHON_CMD="${PYTHON_CMD:-$(command -v python3 || command -v python || echo python)}"

if [ -n "$OUTPUT_FILE" ]; then
  $PYTHON_CMD impl.py "$INPUT_FILE" "$OUTPUT_FILE"
  EXIT_CODE=$?
else
  $PYTHON_CMD impl.py "$INPUT_FILE"
  EXIT_CODE=$?
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "[devix-run] 执行完成，耗时: ${ELAPSED}s，退出码: $EXIT_CODE"

if [ $EXIT_CODE -eq 0 ]; then
  echo "[devix-run] 测试通过"
elif [ $EXIT_CODE -eq 2 ]; then
  echo "[devix-run] 已保存 checkpoint（段式执行）"
else
  echo "[devix-run] 测试失败或出错"
fi

exit $EXIT_CODE
