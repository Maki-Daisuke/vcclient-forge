#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Detecting platform 检测操作系统..."

case "$OSTYPE" in
  solaris*) echo "SOLARIS" ;;
  darwin*)
      echo "MacOS"
      echo "Using Xattr to remove Downloaded flag to avoid Gatekeeper refuse..."
      echo "使用Xattr以移除下载的文件表示防止Gatekeeper截拦..."
      if xattr -rd com.apple.quarantine "$SCRIPT_DIR" >/dev/null; then
      echo "Processing complet!"
      echo "处理完成!"
        else
        echo "Processing complet!"
      echo "处理完成!"
        fi
    ;; 
  linux*)   echo "Linux" ;;
  bsd*)     echo "BSD" ;;
  msys*)    echo "Windows" ;;
  *)        echo "unknown: $OSTYPE" ;;
esac

echo "Starting VCClient Forge..."

URL="http://127.0.0.1:18888/"

open_browser() {
    sleep 2
    if command -v xdg-open > /dev/null 2>&1; then
        xdg-open "$URL" > /dev/null 2>&1 &
    elif command -v open > /dev/null 2>&1; then
        open "$URL" > /dev/null 2>&1 &
    fi
}

open_browser &

exec "$SCRIPT_DIR/main" "$@"
