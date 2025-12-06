#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}

"$PYTHON" - <<'PY'
print('Setting up virtual environment...')
PY

if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
# Prefer CPU-only PyTorch wheels to avoid pulling NVIDIA CUDA packages automatically
export PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cpu}
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

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
