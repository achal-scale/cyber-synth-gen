#!/bin/bash
# Pre-flight: ensure Dolibarr auto-installer has finished
# The tuxgasy image runs its own setup on first boot

echo "[seed] Checking if Dolibarr installation is complete..."
for i in $(seq 1 90); do
    if mysql --skip-ssl -h db -u dolibarr -p"${DOLI_DB_PASSWORD:-dolibarr}" dolibarr -e "SELECT COUNT(*) FROM llx_user" >/dev/null 2>&1; then
        count=$(mysql --skip-ssl -h db -u dolibarr -p"${DOLI_DB_PASSWORD:-dolibarr}" dolibarr -N -B -e "SELECT COUNT(*) FROM llx_user")
        if [ "$count" -ge 1 ]; then
            echo "[seed] Dolibarr user table has $count users, setup appears complete."
            break
        fi
    fi
    echo "[seed] Waiting for Dolibarr setup to complete... ($i)"
    sleep 3
done

# Enable API module if not already enabled
mysql --skip-ssl -h db -u dolibarr -p"${DOLI_DB_PASSWORD:-dolibarr}" dolibarr -e "
INSERT IGNORE INTO llx_const (name, value, type, entity, visible)
VALUES ('MAIN_MODULE_API', '1', 'chaine', 0, 0);
" 2>/dev/null || true

# Enable needed modules
mysql --skip-ssl -h db -u dolibarr -p"${DOLI_DB_PASSWORD:-dolibarr}" dolibarr -e "
INSERT IGNORE INTO llx_const (name, value, type, entity, visible)
VALUES ('MAIN_MODULE_FACTURE', '1', 'chaine', 0, 0);
INSERT IGNORE INTO llx_const (name, value, type, entity, visible)
VALUES ('MAIN_MODULE_SOCIETE', '1', 'chaine', 0, 0);
INSERT IGNORE INTO llx_const (name, value, type, entity, visible)
VALUES ('MAIN_MODULE_PRODUCT', '1', 'chaine', 0, 0);
INSERT IGNORE INTO llx_const (name, value, type, entity, visible)
VALUES ('MAIN_MODULE_SERVICE', '1', 'chaine', 0, 0);
" 2>/dev/null || true

echo "[seed] Module activation complete."

# Create documents directory structure
mkdir -p /var/www/documents/invoices 2>/dev/null || true
echo "Invoice documents directory" > /var/www/documents/invoices/readme.txt 2>/dev/null || true

echo "[seed] Seed complete."
