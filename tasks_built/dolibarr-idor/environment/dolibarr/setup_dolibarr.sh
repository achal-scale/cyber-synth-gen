#!/bin/bash
# This script is called by the gateway at boot to set up users, API keys, and seed data
# It waits for Dolibarr + MySQL to be ready, then configures everything

set -e

DOLI_DB_HOST="${DOLI_DB_HOST:-db}"
DOLI_DB_NAME="${DOLI_DB_NAME:-dolibarr}"
DOLI_DB_USER="${DOLI_DB_USER:-dolibarr}"
DOLI_DB_PASSWORD="${DOLI_DB_PASSWORD:-dolibarr}"

wait_for_db() {
    for i in $(seq 1 60); do
        if mysql -h "$DOLI_DB_HOST" -u "$DOLI_DB_USER" -p"$DOLI_DB_PASSWORD" "$DOLI_DB_NAME" -e "SELECT 1" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

echo "Waiting for database..."
wait_for_db

echo "Running custom SQL init..."
mysql -h "$DOLI_DB_HOST" -u "$DOLI_DB_USER" -p"$DOLI_DB_PASSWORD" "$DOLI_DB_NAME" < /docker-entrypoint-initdb.d/init_data.sql 2>/dev/null || true

echo "Setup complete"
