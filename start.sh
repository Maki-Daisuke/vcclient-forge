#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting VCClient v2.0.78-beta (pure-ONNX)..."

exec "$SCRIPT_DIR/main" server --launch_client True "$@"
