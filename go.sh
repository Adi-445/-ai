#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}

# Prefer CPU-only PyTorch wheels to avoid pulling NVIDIA CUDA packages automatically
export PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cpu}

if ! command -v pipx >/dev/null 2>&1; then
  "$PYTHON" -m pip install --user pipx || "$PYTHON" -m ensurepip --upgrade
  export PATH="$HOME/.local/bin:$PATH"
fi
pipx ensurepath >/dev/null 2>&1 || true
hash -r

if ! command -v uv >/dev/null 2>&1; then
  # Install uv via pipx, then fall back to python -m pip inside user space if needed
  if ! pipx install uv >/dev/null 2>&1; then
    "$PYTHON" -m pip install --user uv
    export PATH="$HOME/.local/bin:$PATH"
  fi
  hash -r
fi

"$PYTHON" - <<'PY'
print('Setting up virtual environment with uv...')
PY

if [ ! -d .venv ] || [ ! -f .venv/bin/activate ]; then
  rm -rf .venv
  uv venv --python "$PYTHON" .venv
fi
source .venv/bin/activate

# Prefer uv in the venv; if not present, fall back to the global one
UV_BIN=".venv/bin/uv"
if [ ! -x "$UV_BIN" ]; then
  UV_BIN="$(command -v uv)"
fi

INSTALL_CMD=($UV_BIN pip install --python .venv/bin/python --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt)
if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then
  INSTALL_CMD+=(--extra-index-url "$PIP_EXTRA_INDEX_URL")
fi
if ! "${INSTALL_CMD[@]}"; then
  echo "Retrying dependency install without extra indexes..."
  "$UV_BIN" pip install --python .venv/bin/python --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt
fi

python - <<'PY'
import uvicorn
print(f"uvicorn available: {uvicorn.__version__}")
PY

chmod +x ./agent/search.sh ./agent/install.sh
if [ ! -x ./agent/search.sh ] || [ ! -x ./agent/install.sh ]; then
  echo "Agent scripts missing or not executable" >&2
  exit 1
fi
./agent/install.sh

python - <<'PY'
from backend import db, models, rag
print('Initializing database and embeddings...')
db.init_db(models)
rag.build_embeddings()
print('Ready!')
PY

UVICORN_BIN=".venv/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
  UVICORN_BIN="$(command -v uvicorn)"
fi
exec "$UVICORN_BIN" backend.main:app --host 0.0.0.0 --port 8000
