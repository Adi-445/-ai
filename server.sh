#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

UVICORN_BIN="$(command -v uvicorn || true)"
if [ -z "$UVICORN_BIN" ]; then
  echo "uvicorn is not installed. Run go.sh first to install dependencies." >&2
  exit 1
fi

echo "[run] Launching backend on 0.0.0.0:8000 using system Python..."
exec "$UVICORN_BIN" backend.main:app --host 0.0.0.0 --port 8000
