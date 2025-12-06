#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}

$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install fastapi uvicorn[standard] httpx sentence-transformers numpy

mkdir -p memory agent web
DB_PATH="memory/memory.db"

$PYTHON - <<'PY'
import sqlite3, pathlib, datetime as dt
DB_PATH = pathlib.Path('memory/memory.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, timestamp TEXT NOT NULL)")
cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL, FOREIGN KEY(chat_id) REFERENCES chats(id))")
cur.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, source TEXT, timestamp TEXT NOT NULL)")
cur.execute("CREATE TABLE IF NOT EXISTS search_cache (query TEXT PRIMARY KEY, result TEXT NOT NULL, timestamp TEXT NOT NULL)")
conn.commit()
conn.close()
PY

# start the server
exec $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 7860
