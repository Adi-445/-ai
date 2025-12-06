#!/usr/bin/env bash
set -euo pipefail
QUERY=${1:-""}
if [ -z "$QUERY" ]; then
  echo "No query provided" >&2
  exit 1
fi

API_URL="https://api.duckduckgo.com/?q=$(python - <<'PY'
import urllib.parse, os
print(urllib.parse.quote(os.environ['QUERY']))
PY
)&format=json&no_redirect=1&no_html=1"

response=$(curl -s "$API_URL")

# Parse top related topics
summary=$(python - <<'PY'
import json, sys
resp = json.loads('''${response}''')
lines = []
added = 0
for item in resp.get("RelatedTopics", []):
    if added >= 3:
        break
    if isinstance(item, dict) and item.get("Text"):
        lines.append(item["Text"])
        added += 1
    elif isinstance(item, dict) and item.get("Topics"):
        for sub in item.get("Topics", []):
            if added >= 3:
                break
            if isinstance(sub, dict) and sub.get("Text"):
                lines.append(sub["Text"])
                added += 1
print("\n".join(lines) if lines else resp.get("AbstractText", "No summary found"))
PY
)

# Insert into SQLite cache
SUMMARY="$summary" python - <<'PY'
import sqlite3, datetime as dt, os, pathlib
BASE = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = BASE / "memory" / "memory.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS search_cache(query TEXT PRIMARY KEY, result TEXT NOT NULL, timestamp TEXT NOT NULL)")
cur.execute(
    "INSERT OR REPLACE INTO search_cache(query, result, timestamp) VALUES (?,?,?)",
    (os.environ['QUERY'], os.environ.get('SUMMARY', ''), dt.datetime.utcnow().isoformat()),
)
conn.commit()
conn.close()
PY

echo "$summary"
