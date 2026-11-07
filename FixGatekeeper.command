#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "Using Xattr to remove Downloaded flag to avoid Gatekeeper refuse..."
echo "使用Xattr以移除下载的文件表示防止Gatekeeper截拦..."
if xattr -rd com.apple.quarantine "$SCRIPT_DIR" >/dev/null; then
echo "Processing complet!"
echo "处理完成!"
else
echo "Processing complet!"
echo "处理完成!"
fi
