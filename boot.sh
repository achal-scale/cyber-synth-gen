#!/usr/bin/env bash
set -e

echo "[gateway] Waiting for w backend..."
for i in $(seq 1 120); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://appserver:8000/api/health" 2>/dev/null || true)
    if [ -n "$code" ] && [ "$code" != "000" ]; then
        echo "[gateway] backend responding (HTTP $code)"
        break
    fi
    sleep 3
done

echo "[gateway] Running setup..."
python3 /app/setup.py

echo "[gateway] Starting gateway server..."
exec gunicorn -b 0.0.0.0:8080 -w 1 --timeout 60 app:app
