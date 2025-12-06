#!/usr/bin/env bash
set -euo pipefail

# Always operate from the repo root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON=${PYTHON:-python3}
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

# Prefer CPU-only PyTorch wheels to avoid pulling NVIDIA CUDA packages automatically
export PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cpu}

echo "[setup] Ensuring Python ($PYTHON) is available..."
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python not found at $PYTHON" >&2
  exit 1
fi

echo "[setup] Creating virtual environment at $VENV_DIR..."
if [ ! -x "$VENV_PY" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "[setup] Upgrading pip inside virtualenv..."
"$VENV_PY" -m pip install --upgrade pip

echo "[setup] Installing Python dependencies into virtualenv..."
INSTALL_CMD=("$VENV_PY" -m pip install --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt)
if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then
  INSTALL_CMD+=(--extra-index-url "$PIP_EXTRA_INDEX_URL")
fi
if ! "${INSTALL_CMD[@]}"; then
  echo "[setup] Retrying dependency install without extra indexes..."
  "$VENV_PY" -m pip install --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt
fi

echo "[setup] Making agent scripts executable..."
chmod +x "$SCRIPT_DIR/agent/search.sh" "$SCRIPT_DIR/agent/install.sh"
if [ ! -x "$SCRIPT_DIR/agent/search.sh" ] || [ ! -x "$SCRIPT_DIR/agent/install.sh" ]; then
  echo "Agent scripts missing or not executable" >&2
  exit 1
fi

"$SCRIPT_DIR/agent/install.sh"

"$VENV_PY" - <<'PY'
from backend import db, models, rag
print('Initializing database and embeddings...')
db.init_db(models)
rag.build_embeddings()
print('Ready!')
PY

echo "[run] Starting server on 0.0.0.0:8000..."
UVICORN_BIN="$VENV_DIR/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
  echo "uvicorn not found in virtualenv" >&2
  exit 1
fi
exec "$UVICORN_BIN" backend.main:app --host 0.0.0.0 --port 8000
