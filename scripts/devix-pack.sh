#!/bin/bash
# devix-pack.sh — 打包 web-automation 为 Devix 上传的 .zip
#
# 用法: bash scripts/devix-pack.sh
# 输出: web-automation-devix.zip（当前目录）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

OUTPUT="web-automation-devix.zip"

# 清理旧包
rm -f "$OUTPUT"

echo "[devix-pack] 打包 $PROJECT_DIR → $OUTPUT"
echo "[devix-pack] 排除: node_modules, .git, artifacts, __pycache__, .qoder, .agents, archive, .cache, deploy, deploy secrets"

zip -r "$OUTPUT" . \
  -x "node_modules/*" \
  -x ".git/*" \
  -x "artifacts/*" \
  -x ".pytest_cache/*" \
  -x "**/__pycache__/*" \
  -x ".qoder/*" \
  -x ".agents/*" \
  -x "archive/*" \
  -x "*.pyc" \
  -x ".DS_Store" \
  -x ".gitignore" \
  -x ".qoderwork/*" \
  -x ".cache/*" \
  -x "deploy/*" \
  -x "*.pem" \
  -x "*.key" \
  -x "*.env" \
  -x "config.local.yaml"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "[devix-pack] 打包完成: $OUTPUT ($SIZE)"
echo "[devix-pack] 上传到: https://devix.alibaba-inc.com/devix/skill?tab=mine&sub=created"
