#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$(uname -s)" = "Darwin" ]; then
    xattr -rd com.apple.quarantine "$SCRIPT_DIR" >/dev/null 2>&1 || true
fi

echo "Starting VCClient Forge Desktop..."

if [ -d "$SCRIPT_DIR/vcclient-forge.app" ]; then
    open "$SCRIPT_DIR/vcclient-forge.app"
elif [ -x "$SCRIPT_DIR/vcclient-forge" ]; then
    exec "$SCRIPT_DIR/vcclient-forge" "$@"
elif [ -f "$SCRIPT_DIR/vcclient-forge" ]; then
    chmod +x "$SCRIPT_DIR/vcclient-forge"
    exec "$SCRIPT_DIR/vcclient-forge" "$@"
else
    echo "Desktop binary not found, falling back to browser launcher..."
    exec "$SCRIPT_DIR/start.sh" "$@"
fi
