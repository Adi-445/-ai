#!/usr/bin/env bash
set -e
if ! command -v curl >/dev/null; then
  echo "curl is required for search agent"
  exit 1
fi
chmod +x search.sh
