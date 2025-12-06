#!/usr/bin/env bash
query="$*"
encoded=$(python - <<PY
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1]))
PY
"$query")
url="https://duckduckgo.com/html/?q=${encoded}&ia=web"
response=$(curl -sL "$url" | sed -n 's/.*<a rel="nofollow" class="result__a" href="[^"]*">\(.*\)<\/a>.*/\1/p' | head -n 5)
if [ -z "$response" ]; then
  response=$(curl -sL "https://api.duckduckgo.com/?q=${encoded}&format=json" | python - <<PY
import json,sys
j=json.load(sys.stdin)
ans=j.get('AbstractText') or j.get('Abstract') or ''
print(ans)
PY
)
fi
echo "$response"
