#!/bin/bash
# check-login-status.sh — 检查各端登录态是否有效
#
# 用法：
#   bash scripts/check-login-status.sh              # 检查全部
#   bash scripts/check-login-status.sh operator      # 仅检查小二端
#   bash scripts/check-login-status.sh merchant      # 仅检查商家端
#
# 退出码：
#   0 = 全部正常
#   1 = 至少一端登录态失效

set -euo pipefail

CDP_URL="${WEB_AUTO_CDP_URL:-http://127.0.0.1:9222}"
CHECK_TARGET="${1:-all}"
ALERT_WEBHOOK="${DINGTALK_WEBHOOK:-}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAIL_COUNT=0

# ── 通过 CDP 在浏览器中检查页面登录态 ──
check_login_via_cdp() {
  local name="$1"
  local url="$2"
  local fail_pattern="$3"  # URL 包含此模式说明被重定向到登录页

  # 获取 Chrome 当前 tab 列表
  local tabs
  tabs=$(curl -s "$CDP_URL/json/list" 2>/dev/null) || {
    echo -e "${RED}✗ $name: 无法连接 CDP ($CDP_URL)${NC}"
    return 1
  }

  # 通过 CDP DevTools Protocol 打开新 tab 并导航到目标页面
  local ws_url
  ws_url=$(echo "$tabs" | python3 -c "import sys,json;tabs=json.load(sys.stdin);print(tabs[0]['webSocketDebuggerUrl'] if tabs else '')" 2>/dev/null)

  if [ -z "$ws_url" ]; then
    echo -e "${YELLOW}⚠ $name: 无法获取 WebSocket URL，尝试直接 curl 检测${NC}"
    # 降级：直接用 curl 检测 HTTP 重定向
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-redirs 0 "$url" 2>/dev/null || echo "000")
    if [ "$http_code" = "302" ] || [ "$http_code" = "301" ]; then
      local redirect_url
      redirect_url=$(curl -sI "$url" 2>/dev/null | grep -i "^location:" | head -1 || echo "")
      if echo "$redirect_url" | grep -qi "$fail_pattern"; then
        echo -e "${RED}✗ $name: 被重定向到登录页 (HTTP $http_code)${NC}"
        return 1
      fi
    fi
    echo -e "${GREEN}✓ $name: 登录态正常 (HTTP $http_code)${NC}"
    return 0
  fi

  # 用 node + puppeteer-core 做真实页面检测（更可靠）
  local result
  result=$(node -e "
    const puppeteer = require(require('path').join('$PWD', 'node_modules', 'puppeteer-core'));
    (async () => {
      try {
        const browser = await puppeteer.connect({ browserURL: '$CDP_URL' });
        const page = await browser.newPage();
        await page.setExtraHTTPHeaders({ 'Accept-Language': 'zh-CN,zh;q=0.9' });

        const response = await page.goto('$url', { waitUntil: 'domcontentloaded', timeout: 15000 });
        const finalUrl = page.url();

        await page.close();
        await browser.disconnect();

        if (finalUrl.includes('$fail_pattern')) {
          console.log('REDIRECTED');
          process.exit(1);
        } else {
          console.log('OK:' + finalUrl);
          process.exit(0);
        }
      } catch (e) {
        console.log('ERROR:' + e.message);
        process.exit(1);
      }
    })();
  " 2>/dev/null) || true

  if [[ "$result" == *"REDIRECTED"* ]]; then
    echo -e "${RED}✗ $name: 登录态已失效（被重定向到登录页）${NC}"
    return 1
  elif [[ "$result" == *"OK:"* ]]; then
    echo -e "${GREEN}✓ $name: 登录态正常${NC}"
    return 0
  else
    echo -e "${YELLOW}⚠ $name: 检测异常 ($result)${NC}"
    return 1
  fi
}

# ── 发送钉钉告警 ──
send_alert() {
  local msg="$1"
  if [ -n "$ALERT_WEBHOOK" ]; then
    curl -s -X POST "$ALERT_WEBHOOK" \
      -H 'Content-Type: application/json' \
      -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$msg\"}}" &>/dev/null
  fi
}

echo "========================================="
echo " 登录态检测 $(date '+%Y-%m-%d %H:%M:%S')"
echo " CDP: $CDP_URL"
echo "========================================="
echo ""

# ── 检查 CDP 服务可用性 ──
if ! curl -s "$CDP_URL/json/version" &>/dev/null; then
  echo -e "${RED}✗ Chrome CDP 服务不可用 ($CDP_URL)${NC}"
  echo "  请检查：systemctl status chrome-cdp"
  send_alert "[回归告警] Chrome CDP 服务不可用，回归中止"
  exit 1
fi
echo -e "${GREEN}✓ Chrome CDP 服务正常${NC}"
echo ""

# ── 小二端登录态 ──
if [ "$CHECK_TARGET" = "all" ] || [ "$CHECK_TARGET" = "operator" ]; then
  echo "── 小二端（BUC SSO）──"
  if ! check_login_via_cdp \
    "小二端-策略平台" \
    "https://pre-aifashion-xiaoer.alibaba-inc.com/strategy/config" \
    "login.alibaba-inc.com\|login.aliyun.com"; then
    FAIL_COUNT=$((FAIL_COUNT + 1))
    send_alert "[回归告警] 小二端 BUC 登录态已失效，请通过 VNC 重新登录"
  fi
  echo ""
fi

# ── 商家端登录态（需独立 CDP 实例，端口 9223）──
if [ "$CHECK_TARGET" = "all" ] || [ "$CHECK_TARGET" = "merchant" ]; then
  MERCHANT_CDP="${MERCHANT_CDP_URL:-http://127.0.0.1:9223}"
  echo "── 商家端（淘宝 SSO）──"

  if curl -s "$MERCHANT_CDP/json/version" &>/dev/null; then
    CDP_URL_BAK="$CDP_URL"
    CDP_URL="$MERCHANT_CDP"
    if ! check_login_via_cdp \
      "商家端-原创保护" \
      "https://pre-fsyc.taobao.com/original/home" \
      "login.taobao.com\|login.aliyun.com"; then
      FAIL_COUNT=$((FAIL_COUNT + 1))
      send_alert "[回归告警] 商家端淘宝登录态已失效，请通过 VNC 重新登录"
    fi
    CDP_URL="$CDP_URL_BAK"
  else
    echo -e "${YELLOW}⚠ 商家端 CDP ($MERCHANT_CDP) 不可用，跳过${NC}"
  fi
  echo ""
fi

# ── 汇总 ──
echo "========================================="
if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED} 检测结果：$FAIL_COUNT 端登录态失效${NC}"
  echo " 请通过 VNC 连接到虚机桌面手动重新登录"
  echo " x11vnc -display :99 -forever -noauth &"
  exit 1
else
  echo -e "${GREEN} 检测结果：全部登录态正常${NC}"
  exit 0
fi
