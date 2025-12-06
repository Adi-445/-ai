#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}

# Prefer CPU-only PyTorch wheels to avoid pulling NVIDIA CUDA packages automatically
export PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cpu}

if ! command -v pipx >/dev/null 2>&1; then
  "$PYTHON" -m pip install --user pipx
  export PATH="$HOME/.local/bin:$PATH"
fi
pipx ensurepath >/dev/null 2>&1 || true
hash -r

if ! command -v uv >/dev/null 2>&1; then
  pipx install uv
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

INSTALL_CMD=(uv pip install --python .venv/bin/python --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt)
if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then
  INSTALL_CMD+=(--extra-index-url "$PIP_EXTRA_INDEX_URL")
fi
if ! "${INSTALL_CMD[@]}"; then
  echo "Retrying dependency install without extra indexes..."
  uv pip install --python .venv/bin/python --upgrade --index-url https://pypi.org/simple -r backend/requirements.txt
fi

python - <<'PY'
import uvicorn
print(f"uvicorn available: {uvicorn.__version__}")
PY

chmod +x agent/search.sh agent/install.sh
./agent/install.sh

python - <<'PY'
from backend import db, models, rag
print('Initializing database and embeddings...')
db.init_db(models)
rag.build_embeddings()
print('Ready!')
PY

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
