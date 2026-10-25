#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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
