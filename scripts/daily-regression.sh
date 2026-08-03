#!/bin/bash
# daily-regression.sh — 每日自动化回归编排脚本
#
# 用法：
#   bash scripts/daily-regression.sh                    # 跑全部（小二端 + F88）
#   bash scripts/daily-regression.sh --op               # 仅原创保护小二端
#   bash scripts/daily-regression.sh --f88              # 仅 F88
#   bash scripts/daily-regression.sh --merchant         # 仅商家端
#   bash scripts/daily-regression.sh --skip-login-check # 跳过登录态检测
#
# 环境变量：
#   DINGTALK_WEBHOOK    钉钉机器人 webhook（告警 + 报告通知）
#   WEB_AUTO_CDP_URL    小二端/F88 CDP 地址（默认 http://127.0.0.1:9222）
#   MERCHANT_CDP_URL    商家端 CDP 地址（默认 http://127.0.0.1:9223）
#   REGRESSION_REPORT_OSS  OSS 上传路径（可选，如 oss://bucket/reports/）
#
# 输出：
#   artifacts/op-YYYYMMDD.json       原创保护小二端结果
#   artifacts/f88-YYYYMMDD.json      F88 结果
#   artifacts/merchant-YYYYMMDD.json 商家端结果
#   artifacts/*-report.html          HTML 报告

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

TODAY=$(date '+%Y%m%d')
NOW=$(date '+%Y-%m-%d %H:%M:%S')
TIMESTAMP=$(date '+%H:%M:%S')

CDP_URL="${WEB_AUTO_CDP_URL:-http://127.0.0.1:9222}"
MERCHANT_CDP="${MERCHANT_CDP_URL:-http://127.0.0.1:9223}"
ALERT_WEBHOOK="${DINGTALK_WEBHOOK:-}"

# 解析参数
RUN_OP=true
RUN_F88=true
RUN_MERCHANT=false
SKIP_LOGIN_CHECK=false

for arg in "$@"; do
  case "$arg" in
    --op) RUN_F88=false; RUN_MERCHANT=false ;;
    --f88) RUN_OP=false; RUN_MERCHANT=false ;;
    --merchant) RUN_OP=false; RUN_F88=false; RUN_MERCHANT=true ;;
    --skip-login-check) SKIP_LOGIN_CHECK=true ;;
  esac
done

# ── 工具函数 ──
log() { echo "[$(date '+%H:%M:%S')] $*"; }

send_dingtalk() {
  local title="$1"
  local content="$2"
  if [ -n "$ALERT_WEBHOOK" ]; then
    curl -s -X POST "$ALERT_WEBHOOK" \
      -H 'Content-Type: application/json' \
      -d "{\"msgtype\":\"markdown\",\"markdown\":{\"title\":\"$title\",\"text\":\"$content\"}}" &>/dev/null
  fi
}

extract_summary() {
  local json_file="$1"
  if [ -f "$json_file" ]; then
    python3 -c "
import sys, json
try:
    d = json.load(open('$json_file'))
    s = d.get('summary', d)
    total = s.get('total', 0)
    passed = s.get('pass', s.get('passed', 0))
    failed = s.get('fail', s.get('failed', 0))
    skipped = s.get('skip', s.get('skipped', 0))
    print(f'{passed}/{total} 通过, {failed} 失败, {skipped} 跳过')
except:
    print('解析失败')
" 2>/dev/null
  else
    echo "文件不存在"
  fi
}

# ════════════════════════════════════════════
# 开始执行
# ════════════════════════════════════════════

log "========================================="
log " 每日自动化回归 - $NOW"
log "========================================="
log ""

REPORT_LINES="## 每日回归报告 $TODAY\n\n"
TOTAL_PASS=0
TOTAL_FAIL=0
HAS_ERROR=false

# ── 1. 登录态预检 ──
if [ "$SKIP_LOGIN_CHECK" = false ]; then
  log "── Step 1: 登录态预检 ──"
  if ! bash "$SCRIPT_DIR/check-login-status.sh" ${RUN_MERCHANT:+merchant} ${RUN_OP:+operator} >/dev/null 2>&1; then
    log "ERROR: 登录态检测失败，回归中止"
    send_dingtalk "回归中止" "## 每日回归 $TODAY\n\n**登录态检测失败**，回归已中止。\n\n请通过 VNC 检查虚机登录状态。"
    exit 1
  fi
  log "登录态正常，继续执行"
  log ""
fi

# ── 2. 小二端回归（原创保护 + F88）──
if [ "$RUN_OP" = true ]; then
  log "── Step 2a: 原创保护小二端回归 ──"
  OP_RESULT_FILE="artifacts/op-${TODAY}.json"

  OP_START=$(date +%s)
  if node scripts/run-op-regression.js --out "$OP_RESULT_FILE" 2>&1; then
    OP_END=$(date +%s)
    OP_DURATION=$((OP_END - OP_START))
    OP_SUMMARY=$(extract_summary "$OP_RESULT_FILE")
    log "原创保护完成: $OP_SUMMARY (${OP_DURATION}s)"
    REPORT_LINES+="### 原创保护小二端\n- 结果: $OP_SUMMARY\n- 耗时: ${OP_DURATION}s\n- 详情: \`$OP_RESULT_FILE\`\n\n"
  else
    OP_END=$(date +%s)
    OP_DURATION=$((OP_END - OP_START))
    log "ERROR: 原创保护回归执行异常"
    REPORT_LINES+="### 原创保护小二端\n- **执行异常** (${OP_DURATION}s)\n\n"
    HAS_ERROR=true
  fi
  log ""
fi

if [ "$RUN_F88" = true ]; then
  log "── Step 2b: F88 回归 ──"
  F88_RESULT_FILE="artifacts/f88-${TODAY}.json"

  F88_START=$(date +%s)
  if node scripts/run-f88-regression.js --sequential --out "$F88_RESULT_FILE" 2>&1; then
    F88_END=$(date +%s)
    F88_DURATION=$((F88_END - F88_START))
    F88_SUMMARY=$(extract_summary "$F88_RESULT_FILE")
    log "F88 完成: $F88_SUMMARY (${F88_DURATION}s)"
    REPORT_LINES+="### F88 审核\n- 结果: $F88_SUMMARY\n- 耗时: ${F88_DURATION}s\n- 详情: \`$F88_RESULT_FILE\`\n\n"
  else
    F88_END=$(date +%s)
    F88_DURATION=$((F88_END - F88_START))
    log "ERROR: F88 回归执行异常"
    REPORT_LINES+="### F88 审核\n- **执行异常** (${F88_DURATION}s)\n\n"
    HAS_ERROR=true
  fi
  log ""
fi

# ── 3. 商家端回归 ──
if [ "$RUN_MERCHANT" = true ]; then
  log "── Step 3: 商家端回归 ──"
  MERCHANT_RESULT_FILE="artifacts/merchant-${TODAY}.json"

  if curl -s "$MERCHANT_CDP/json/version" &>/dev/null; then
    MERCHANT_START=$(date +%s)
    if WEB_AUTO_CDP_URL="$MERCHANT_CDP" node scripts/run-op-regression.js \
        --out "$MERCHANT_RESULT_FILE" signup tort settlement apply_list 2>&1; then
      MERCHANT_END=$(date +%s)
      MERCHANT_DURATION=$((MERCHANT_END - MERCHANT_START))
      MERCHANT_SUMMARY=$(extract_summary "$MERCHANT_RESULT_FILE")
      log "商家端完成: $MERCHANT_SUMMARY (${MERCHANT_DURATION}s)"
      REPORT_LINES+="### 商家端\n- 结果: $MERCHANT_SUMMARY\n- 耗时: ${MERCHANT_DURATION}s\n- 详情: \`$MERCHANT_RESULT_FILE\`\n\n"
    else
      MERCHANT_END=$(date +%s)
      MERCHANT_DURATION=$((MERCHANT_END - MERCHANT_START))
      log "ERROR: 商家端回归执行异常"
      REPORT_LINES+="### 商家端\n- **执行异常** (${MERCHANT_DURATION}s)\n\n"
      HAS_ERROR=true
    fi
  else
    log "WARNING: 商家端 CDP ($MERCHANT_CDP) 不可用，跳过"
    REPORT_LINES+="### 商家端\n- ⚠ CDP 不可用，已跳过\n\n"
  fi
  log ""
fi

# ── 4. 生成 HTML 报告 ──
log "── Step 4: 生成 HTML 报告 ──"
for result_file in artifacts/op-${TODAY}.json artifacts/f88-${TODAY}.json artifacts/merchant-${TODAY}.json; do
  if [ -f "$result_file" ]; then
    report_html="${result_file%.json}-report.html"
    if node scripts/generate-regression-report.js "$result_file" --out "$report_html" 2>/dev/null; then
      log "报告已生成: $report_html"
    else
      log "WARNING: 报告生成失败 $result_file"
    fi
  fi
done
log ""

# ── 5. 产物归档（可选 OSS 上传）──
if [ -n "${REGRESSION_REPORT_OSS:-}" ]; then
  log "── Step 5: 归档到 OSS ──"
  for f in artifacts/*-${TODAY}*.json artifacts/*-${TODAY}*-report.html; do
    if [ -f "$f" ]; then
      ossutil cp "$f" "${REGRESSION_REPORT_OSS}$(basename "$f")" 2>/dev/null && \
        log "已上传: $(basename "$f")" || \
        log "WARNING: OSS 上传失败 $(basename "$f")"
    fi
  done
  log ""
fi

# ── 6. 产物清理（保留最近 30 天）──
log "── Step 6: 清理过期产物 ──"
find artifacts/ -name "*.json" -mtime +30 -delete 2>/dev/null
find artifacts/ -name "*-report.html" -mtime +30 -delete 2>/dev/null
log "已清理 30 天前的报告"
log ""

# ── 7. 汇总通知 ──
log "========================================="
log " 回归完成"
log "========================================="

REPORT_LINES+="---\n_执行时间: $NOW_"

if [ "$HAS_ERROR" = true ]; then
  REPORT_TITLE="⚠ 回归异常 $TODAY"
else
  REPORT_TITLE="✓ 回归完成 $TODAY"
fi

# 打印报告
echo ""
echo -e "$REPORT_LINES"

# 钉钉通知
send_dingtalk "$REPORT_TITLE" "$REPORT_LINES"

# 退出码
if [ "$HAS_ERROR" = true ]; then
  exit 1
fi
exit 0
#!/bin/bash
# daily-regression.sh — 每日回归构建脚本
#
# 流程:
#   1. 检查/启动 Chrome CDP
#   2. 注入登录态 (复用 tdbank 登录态注入)
#   3. 按 regression_manifest.json 执行回归套件
#   4. 生成 HTML 报告
#   5. 推送钉钉群通知 (可选)
#
# 用法:
#   ./scripts/daily-regression.sh                    # 默认执行 f88-smoke 套件
#   ./scripts/daily-regression.sh --suite f88-core   # 指定套件
#   ./scripts/daily-regression.sh --suite f88-full-weekly
#   ./scripts/daily-regression.sh --all               # 按 manifest 自动选择今天的套件
#
# 定时任务 (macOS crontab -e):
#   0 8 * * 1-5  cd /path/to/web-automation && ./scripts/daily-regression.sh --suite f88-smoke
#   0 2 * * *    cd /path/to/web-automation && ./scripts/daily-regression.sh --suite f88-regression-core
#   0 2 * * 0    cd /path/to/web-automation && ./scripts/daily-regression.sh --suite f88-full-weekly

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
ARTIFACTS_DIR="$WORKSPACE/artifacts"
MANIFEST="$WORKSPACE/regression_manifest.json"
CDP_URL="${WEB_AUTO_CDP_URL:-http://127.0.0.1:9222}"
CHROME_APP="/Applications/Google Chrome.app"
SUITE="f88-smoke"
ALL_SUITES=false
DRY_RUN=false
LOG_FILE="$ARTIFACTS_DIR/daily-regression-$(date +%Y%m%d-%H%M%S).log"

# ── 参数解析 ──
while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) SUITE="$2"; shift 2 ;;
    --all) ALL_SUITES=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --cdp-url) CDP_URL="$2"; shift 2 ;;
    --log) LOG_FILE="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

mkdir -p "$ARTIFACTS_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# ── 日志 ──
log() {
  local ts=$(date '+%H:%M:%S')
  local icon="${2:-ℹ️}"
  echo "$icon [$ts] $1" | tee -a "$LOG_FILE"
}

log_ok()  { log "$1" "✅"; }
log_warn(){ log "$1" "⚠️"; }
log_err() { log "$1" "❌"; }

# ── 检查/启动 Chrome CDP ──
check_chrome_cdp() {
  log "检查 Chrome CDP: $CDP_URL"

  # 尝试连接
  if curl -sf "${CDP_URL}/json/version" > /dev/null 2>&1; then
    log_ok "Chrome CDP 已连接"
    return 0
  fi

  log "Chrome CDP 未连接，尝试启动..."

  # macOS 启动 Chrome
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if [[ -d "$CHROME_APP" ]]; then
      open -a "$CHROME_APP" --args \
        --remote-debugging-port=9222 \
        --no-first-run \
        --no-default-browser-check \
        --user-data-dir="$HOME/.chrome-cdp-profile" \
        2>/dev/null &

      # 等待 CDP 就绪
      local max_wait=30
      local waited=0
      while ! curl -sf "${CDP_URL}/json/version" > /dev/null 2>&1; do
        sleep 1
        waited=$((waited + 1))
        if [[ $waited -ge $max_wait ]]; then
          log_err "Chrome CDP 启动超时 (${max_wait}s)"
          return 1
        fi
      done
      log_ok "Chrome CDP 已启动 (等待 ${waited}s)"
      return 0
    else
      log_err "未找到 Chrome: $CHROME_APP"
      return 1
    fi
  else
    # Linux
    if command -v google-chrome &> /dev/null; then
      google-chrome --remote-debugging-port=9222 --no-first-run --headless &
      sleep 5
      if curl -sf "${CDP_URL}/json/version" > /dev/null 2>&1; then
        log_ok "Chrome CDP 已启动 (headless)"
        return 0
      fi
    fi
    log_err "无法启动 Chrome CDP"
    return 1
  fi
}

# ── 注入登录态 ──
inject_login() {
  log "检查登录态..."

  # 尝试通过 CDP 检查是否已登录
  local check_result
  check_result=$(node -e "
    const puppeteer = require('puppeteer-core');
    (async () => {
      try {
        const browser = await puppeteer.connect({ browserURL: '$CDP_URL', defaultViewport: null });
        const page = await browser.newPage();
        await page.goto('https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center', {
          waitUntil: 'networkidle2', timeout: 15000
        });
        await new Promise(r => setTimeout(r, 3000));
        const text = await page.evaluate(() => document.body.innerText);
        const loggedIn = text.includes('审核任务') || text.includes('个人任务');
        console.log(loggedIn ? 'LOGGED_IN' : 'NOT_LOGGED_IN');
        await page.close();
      } catch (e) {
        console.log('CHECK_ERROR');
      }
    })();
  " 2>/dev/null)

  if [[ "$check_result" == *"LOGGED_IN"* ]]; then
    log_ok "登录态有效"
    return 0
  fi

  log_warn "登录态可能失效，请手动登录后继续"
  log "提示: 在 Chrome CDP 浏览器中访问预发环境并完成登录"

  # 等待用户手动登录 (最多 120s)
  local max_wait=120
  local waited=0
  while [[ $waited -lt $max_wait ]]; do
    sleep 10
    waited=$((waited + 10))
    check_result=$(node -e "
      const puppeteer = require('puppeteer-core');
      (async () => {
        try {
          const browser = await puppeteer.connect({ browserURL: '$CDP_URL', defaultViewport: null });
          const page = await browser.newPage();
          await page.goto('https://pre-aifashion-xiaoer.alibaba-inc.com/review/personal-task-center', {
            waitUntil: 'networkidle2', timeout: 15000
          });
          await new Promise(r => setTimeout(r, 2000));
          const text = await page.evaluate(() => document.body.innerText);
          console.log((text.includes('审核任务') || text.includes('个人任务')) ? 'LOGGED_IN' : 'NOT_LOGGED_IN');
          await page.close();
        } catch(e) { console.log('CHECK_ERROR'); }
      })();
    " 2>/dev/null)

    if [[ "$check_result" == *"LOGGED_IN"* ]]; then
      log_ok "登录完成"
      return 0
    fi
    log "等待登录... (${waited}/${max_wait}s)"
  done

  log_err "登录超时"
  return 1
}

# ── 根据 manifest 选择套件 ──
get_today_suites() {
  local day_of_week=$(date +%u)  # 1=Mon, 7=Sun
  local hour=$(date +%H)

  if [[ "$ALL_SUITES" == "true" ]]; then
    # 根据星期和时间自动选择
    # 周日凌晨: full-weekly
    if [[ "$day_of_week" == "7" ]]; then
      echo "f88-full-weekly"
    else
      # 工作日: smoke + core
      echo "f88-smoke f88-regression-core"
    fi
  else
    echo "$SUITE"
  fi
}

# ── 执行回归套件 ──
run_suite() {
  local suite_name="$1"
  local results_file="$ARTIFACTS_DIR/regression-${suite_name}-$(date +%Y%m%d).json"

  log "━━━ 执行套件: $suite_name ━━━"

  # 从 manifest 读取套件配置
  if [[ -f "$MANIFEST" ]]; then
    local suite_info
    suite_info=$(node -e "
      const fs = require('fs');
      const m = JSON.parse(fs.readFileSync('$MANIFEST', 'utf8'));
      const s = m.suites['$suite_name'];
      if (!s) { console.log('NOT_FOUND'); process.exit(0); }
      console.log(JSON.stringify(s));
    " 2>/dev/null)

    if [[ "$suite_info" == "NOT_FOUND" ]]; then
      log_warn "manifest 中未找到套件: $suite_name"
    fi
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY-RUN] 将执行套件: $suite_name"
    return 0
  fi

  # 执行回归
  log "执行 run-f88-regression.js ..."
  WEB_AUTO_CDP_URL="$CDP_URL" node "$WORKSPACE/scripts/run-f88-regression.js" 2>&1 | tee -a "$LOG_FILE"

  local exit_code=${PIPESTATUS[0]}

  if [[ -f "$ARTIFACTS_DIR/regression-results.json" ]]; then
    cp "$ARTIFACTS_DIR/regression-results.json" "$results_file"
    log_ok "回归结果: $results_file"
  fi

  if [[ $exit_code -ne 0 ]]; then
    log_warn "回归执行有失败 (exit=$exit_code)"
  else
    log_ok "回归执行完成"
  fi

  return $exit_code
}

# ── 生成报告 ──
generate_report() {
  local results_file="$ARTIFACTS_DIR/regression-results.json"
  local report_file="$ARTIFACTS_DIR/daily-report-$(date +%Y%m%d).html"

  if [[ ! -f "$results_file" ]]; then
    log_warn "无回归结果文件，跳过报告生成"
    return 0
  fi

  log "生成 HTML 报告..."

  # 使用 generate-regression-report.js (如果结果格式兼容)
  if [[ -f "$WORKSPACE/scripts/generate-regression-report.js" ]]; then
    node "$WORKSPACE/scripts/generate-regression-report.js" "$results_file" --out "$report_file" 2>&1 | tee -a "$LOG_FILE"
    if [[ -f "$report_file" ]]; then
      log_ok "报告: $report_file"
    fi
  fi
}

# ── 钉钉通知 ──
send_dingtalk_notification() {
  local results_file="$ARTIFACTS_DIR/regression-results.json"

  if [[ ! -f "$results_file" ]]; then
    return 0
  fi

  # 读取结果摘要
  local summary
  summary=$(node -e "
    const fs = require('fs');
    const d = JSON.parse(fs.readFileSync('$results_file', 'utf8'));
    const s = d.summary || {};
    console.log(JSON.stringify({
      tc: s.tc || 0,
      pass: s.pass || 0,
      fail: s.fail || 0,
      skip: s.skip || 0,
      logPass: s.logPass || 0,
      logFail: s.logFail || 0
    }));
  " 2>/dev/null)

  if [[ -z "$summary" ]]; then
    return 0
  fi

  local tc=$(echo "$summary" | node -e "process.stdin.resume();let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.tc)})")
  local pass=$(echo "$summary" | node -e "process.stdin.resume();let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.pass)})")
  local fail=$(echo "$summary" | node -e "process.stdin.resume();let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.fail)})")

  log "回归结果摘要: TC=$tc PASS=$pass FAIL=$fail"

  # 如果有钉钉 webhook 配置，发送通知
  if [[ -n "${DINGTALK_WEBHOOK:-}" ]]; then
    local color="#22c55e"
    if [[ "$fail" -gt 0 ]]; then color="#ef4444"; fi

    local msg
    msg=$(cat <<EOF
{
  "msgtype": "markdown",
  "markdown": {
    "title": "F88 每日回归 $(date +%Y-%m-%d)",
    "text": "## F88 每日回归报告\n\n**日期**: $(date +%Y-%m-%d)\n\n**套件**: ${SUITE}\n\n- 用例总数: ${tc}\n- ✅ 通过: ${pass}\n- ❌ 失败: ${fail}\n\n**通过率**: $(( pass * 100 / (tc > 0 ? tc : 1) ))%"
  }
}
EOF
    )

    curl -sf -H 'Content-Type: application/json' -d "$msg" "$DINGTALK_WEBHOOK" > /dev/null 2>&1
    log_ok "钉钉通知已发送"
  else
    log "未配置 DINGTALK_WEBHOOK，跳过钉钉通知"
  fi
}

# ── 主流程 ──
main() {
  log "═══════════════════════════════════"
  log "F88 每日回归构建 — $(date '+%Y-%m-%d %H:%M:%S')"
  log "═══════════════════════════════════"
  log "套件: $(get_today_suites)"
  log "CDP: $CDP_URL"
  log "日志: $LOG_FILE"

  cd "$WORKSPACE"

  # 1. 检查 Chrome
  check_chrome_cdp || {
    log_err "Chrome CDP 检查失败"
    exit 1
  }

  # 2. 检查登录态
  inject_login || {
    log_err "登录态检查失败"
    exit 1
  }

  # 3. 执行套件
  local suites
  suites=$(get_today_suites)
  local total_exit=0

  for suite in $suites; do
    run_suite "$suite" || total_exit=1
  done

  # 4. 生成报告
  generate_report

  # 5. 钉钉通知
  send_dingtalk_notification

  log "═══════════════════════════════════"
  if [[ $total_exit -eq 0 ]]; then
    log_ok "每日回归构建完成"
  else
    log_warn "每日回归构建完成 (有失败项)"
  fi
  log "═══════════════════════════════════"

  exit $total_exit
}

main "$@"
