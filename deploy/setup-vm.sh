#!/bin/bash
# setup-vm.sh — 虚机环境一键初始化
#
# 用法：
#   sudo bash deploy/setup-vm.sh              # 全新虚机
#   sudo bash deploy/setup-vm.sh --skip-chrome # 跳过 Chrome 安装（已装时）
#
# 前置条件：
#   - CentOS 7+ / Ubuntu 20.04+ / Debian 11+
#   - root 或 sudo 权限
#   - 能访问内网 yum/apt 源

set -euo pipefail

SKIP_CHROME=false
[[ "${1:-}" == "--skip-chrome" ]] && SKIP_CHROME=true

AUTOMATION_USER="automation"
PROJECT_DIR="/data/web-automation"
CHROME_PROFILE_DIR="/data/chrome-profile"

echo "========================================="
echo " web-automation 虚机环境初始化"
echo "========================================="

# ── 1. 创建专用用户 ──
echo "[1/7] 创建用户 $AUTOMATION_USER ..."
if ! id "$AUTOMATION_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$AUTOMATION_USER"
  echo "  用户已创建"
else
  echo "  用户已存在，跳过"
fi

# ── 2. 系统依赖 ──
echo "[2/7] 安装系统依赖 ..."
if command -v apt-get &>/dev/null; then
  apt-get update -qq
  apt-get install -y -qq \
    xvfb \
    curl wget unzip \
    fonts-wqy-microhei fonts-wqy-zenhei \
    libgbm1 libnss3 libatk-bridge2.0-0 \
    libgtk-3-0 libxss1 libasound2 \
    python3 python3-pip \
    jq cron
elif command -v yum &>/dev/null; then
  yum install -y -q \
    xorg-x11-server-Xvfb \
    curl wget unzip \
    wqy-microhei-fonts wqy-zenhei-fonts \
    libgbm nss atk at-spi2-atk gtk3 \
    python3 python3-pip \
    jq cronie
else
  echo "ERROR: 不支持的包管理器" >&2
  exit 1
fi

# ── 3. Chrome 安装 ──
if [ "$SKIP_CHROME" = false ]; then
  echo "[3/7] 安装 Google Chrome Stable ..."
  if [ ! -f /usr/bin/google-chrome-stable ]; then
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.deb -O /tmp/chrome.deb 2>/dev/null || \
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm -O /tmp/chrome.rpm 2>/dev/null

    if [ -f /tmp/chrome.deb ]; then
      apt-get install -y -qq /tmp/chrome.deb && rm /tmp/chrome.deb
    elif [ -f /tmp/chrome.rpm ]; then
      yum install -y -q /tmp/chrome.rpm && rm /tmp/chrome.rpm
    else
      echo "ERROR: Chrome 下载失败，请手动安装" >&2
      exit 1
    fi
    echo "  Chrome $(google-chrome-stable --version 2>/dev/null || echo 'unknown') 已安装"
  else
    echo "  Chrome 已存在，跳过"
  fi
else
  echo "[3/7] 跳过 Chrome 安装"
fi

# ── 4. Node.js 22 ──
echo "[4/7] 安装 Node.js 22 ..."
if ! command -v node &>/dev/null || [[ "$(node -v)" != v22* ]]; then
  curl -fsSL https://rpm.nodesource.com/setup_22.x 2>/dev/null | bash - 2>/dev/null || \
  curl -fsSL https://deb.nodesource.com/setup_22.x 2>/dev/null | bash - 2>/dev/null
  if command -v apt-get &>/dev/null; then
    apt-get install -y -qq nodejs
  elif command -v yum &>/dev/null; then
    yum install -y -q nodejs
  fi
  echo "  Node.js $(node -v) 已安装"
else
  echo "  Node.js $(node -v) 已存在，跳过"
fi

# ── 5. 项目部署 ──
echo "[5/7] 部署项目到 $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"
mkdir -p "$CHROME_PROFILE_DIR"
mkdir -p "$PROJECT_DIR/artifacts"

# 如果项目已在当前目录，拷贝过去
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$SCRIPT_DIR" != "$PROJECT_DIR" ]; then
  rsync -a --exclude='node_modules' --exclude='.git' "$SCRIPT_DIR/" "$PROJECT_DIR/" 2>/dev/null || \
  cp -r "$SCRIPT_DIR"/* "$PROJECT_DIR/" 2>/dev/null || true
fi

chown -R "$AUTOMATION_USER":"$AUTOMATION_USER" "$PROJECT_DIR" "$CHROME_PROFILE_DIR"

cd "$PROJECT_DIR"
su - "$AUTOMATION_USER" -c "cd $PROJECT_DIR && npm ci --production 2>/dev/null || npm install --production"

# ── 6. Systemd 服务 ──
echo "[6/7] 安装 systemd 服务 ..."
cp "$PROJECT_DIR/deploy/xvfb.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/chrome-cdp.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable xvfb chrome-cdp
systemctl start xvfb
sleep 2
systemctl start chrome-cdp
sleep 3

# 验证 CDP
if curl -s http://127.0.0.1:9222/json/version | grep -q "Browser"; then
  echo "  Chrome CDP 服务正常运行 ✓"
else
  echo "  WARNING: Chrome CDP 未就绪，请检查 journalctl -u chrome-cdp"
fi

# ── 7. Cron 定时任务 ──
echo "[7/7] 配置每日回归 cron ..."
CRON_JOB="0 9 * * * cd $PROJECT_DIR && bash scripts/daily-regression.sh >> /var/log/daily-regression.log 2>&1"
(su - "$AUTOMATION_USER" -c "crontab -l 2>/dev/null | grep -v daily-regression; echo '$CRON_JOB'") | \
  su - "$AUTOMATION_USER" -c "crontab -"

echo ""
echo "========================================="
echo " 初始化完成！"
echo "========================================="
echo ""
echo "后续步骤："
echo "  1. 通过 VNC 连接到虚机桌面（DISPLAY=:99）"
echo "     x11vnc -display :99 -forever -noauth &"
echo "     然后用 VNC 客户端连接 <虚机IP>:5900"
echo ""
echo "  2. 在 VNC 中打开 Chrome 手动登录一次："
echo "     - 小二端：https://login.alibaba-inc.com（BUC SSO）"
echo "     - 商家端：https://login.taobao.com（淘宝账号）"
echo ""
echo "  3. 验证登录态："
echo "     su - $AUTOMATION_USER -c 'bash $PROJECT_DIR/scripts/check-login-status.sh'"
echo ""
echo "  4. 手动试跑一次回归："
echo "     su - $AUTOMATION_USER -c 'cd $PROJECT_DIR && bash scripts/daily-regression.sh'"
echo ""
echo "  之后每天 9:00 自动执行回归，报告输出到 $PROJECT_DIR/artifacts/"
