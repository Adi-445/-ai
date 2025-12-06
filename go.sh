#!/usr/bin/env bash
set -euo pipefail

# Always operate from the repo root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON=${PYTHON:-python3}

# Prefer CPU-only PyTorch wheels to avoid pulling NVIDIA CUDA packages automatically
export PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cpu}

echo "[setup] Ensuring pip is available..."
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python not found at $PYTHON" >&2
  exit 1
fi
"$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON" -m pip install --upgrade pip >/dev/null 2>&1 || true

# Install pipx if missing so we can bootstrap uv reliably
if ! command -v pipx >/dev/null 2>&1; then
  "$PYTHON" -m pip install --user pipx
  export PATH="$HOME/.local/bin:$PATH"
fi
pipx ensurepath >/dev/null 2>&1 || true
hash -r

# Ensure uv is present (preferred installer)
if ! command -v uv >/dev/null 2>&1; then
  if ! pipx install uv >/dev/null 2>&1; then
    "$PYTHON" -m pip install --user uv
    export PATH="$HOME/.local/bin:$PATH"
  fi
  hash -r
fi

UV_BIN="$(command -v uv || true)"
if [ -z "$UV_BIN" ]; then
  echo "uv is required but could not be installed" >&2
  exit 1
fi

echo "[setup] Installing Python dependencies system-wide (no virtualenv)..."
INSTALL_CMD=($UV_BIN pip install --system --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt)
if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then
  INSTALL_CMD+=(--extra-index-url "$PIP_EXTRA_INDEX_URL")
fi
if ! "${INSTALL_CMD[@]}"; then
  echo "[setup] Retrying dependency install without extra indexes..."
  "$UV_BIN" pip install --system --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt
fi

# Sanity-check uvicorn availability early
"$PYTHON" - <<'PY'
import importlib.util, sys
name = "uvicorn"
if importlib.util.find_spec(name) is None:
    sys.exit(f"{name} is not installed")
print("uvicorn available")
PY

echo "[setup] Making agent scripts executable..."
chmod +x "$SCRIPT_DIR/agent/search.sh" "$SCRIPT_DIR/agent/install.sh"
if [ ! -x "$SCRIPT_DIR/agent/search.sh" ] || [ ! -x "$SCRIPT_DIR/agent/install.sh" ]; then
  echo "Agent scripts missing or not executable" >&2
  exit 1
fi

"$SCRIPT_DIR/agent/install.sh"

"$PYTHON" - <<'PY'
from backend import db, models, rag
print('Initializing database and embeddings...')
db.init_db(models)
rag.build_embeddings()
print('Ready!')
PY

echo "[run] Starting server on 0.0.0.0:8000..."
UVICORN_BIN="$(command -v uvicorn || true)"
if [ -z "$UVICORN_BIN" ]; then
  echo "uvicorn not found on PATH" >&2
  exit 1
fi
exec "$UVICORN_BIN" backend.main:app --host 0.0.0.0 --port 8000
