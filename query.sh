#!/usr/bin/env bash
set -euo pipefail
PORT="${NGINX_HTTP_PORT:-8081}"
curl -sS -X POST "http://localhost:${PORT}/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"${1:-С какого года компания занимается банкротством?\"}" | \
  python3 -m json.tool
