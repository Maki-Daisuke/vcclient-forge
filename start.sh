#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting VCClient v2.0.78-beta (pure-ONNX)..."

if [ -f "$SCRIPT_DIR/runtime/bin/python" ]; then
    "$SCRIPT_DIR/runtime/bin/python" backend/main.py server --launch_client True
elif [ -f "$SCRIPT_DIR/backend/.venv/bin/python" ]; then
    "$SCRIPT_DIR/backend/.venv/bin/python" backend/main.py server --launch_client True
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    "$SCRIPT_DIR/.venv/bin/python" backend/main.py server --launch_client True
else
    uv run --project backend python backend/main.py server --launch_client True
fi
