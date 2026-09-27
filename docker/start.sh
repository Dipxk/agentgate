#!/bin/sh
set -eu
cd /app
agentgate demo
nohup agentgate serve --host 127.0.0.1 --port 8000 >/tmp/agentgate-api.log 2>&1 &
ok=0
i=0
while [ "$i" -lt 50 ]; do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=1)" >/dev/null 2>&1; then
    ok=1
    break
  fi
  i=$((i + 1))
  sleep 0.2
done
if [ "$ok" -ne 1 ]; then
  echo "API did not start" >&2
  cat /tmp/agentgate-api.log >&2 || true
  exit 1
fi
cd /app/frontend
exec npx next start --hostname 0.0.0.0 --port "${PORT:-3000}"
