#!/usr/bin/env bash
set -e

# Wait for appserver
echo "[gateway] Waiting for appserver..."
for i in $(seq 1 180); do
    if curl -s -o /dev/null -w '%{http_code}' http://appserver/ 2>/dev/null | grep -qE '200|302'; then
        echo "[gateway] Appserver is up"
        break
    fi
    sleep 3
done

# Wait for DB with user table populated
echo "[gateway] Waiting for database..."
for i in $(seq 1 120); do
    COUNT=$(mysql --skip-ssl -h db -u dolibarr -p"${DOLI_DB_PASSWORD:-dolibarr}" dolibarr -N -B -e "SELECT COUNT(*) FROM llx_user" 2>/dev/null)
    if [ -n "$COUNT" ] && [ "$COUNT" -ge 1 ]; then
        echo "[gateway] Database ready with $COUNT users"
        break
    fi
    sleep 3
done

# Run setup script
echo "[gateway] Running setup..."
python3 /app/setup.py

echo "[gateway] Starting gateway server..."
exec gunicorn -b 0.0.0.0:8080 -w 1 --timeout 60 app:app
