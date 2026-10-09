#!/bin/bash
set -e

DB_NAME="cacti"
DB_USER="cactiuser"
DB_PASS="${DB_PASSWORD:?DB_PASSWORD not set}"

# Start MariaDB
echo "Starting MariaDB..."
install -d -m 755 -o mysql -g mysql /run/mysqld
mysqld_safe &
for i in $(seq 1 30); do
    if mysqladmin ping --silent 2>/dev/null; then break; fi
    sleep 1
done
echo "MariaDB is ready."

# Initialize database
mysql -u root << EOSQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME};
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'127.0.0.1';
GRANT SELECT ON mysql.time_zone_name TO '${DB_USER}'@'localhost';
GRANT SELECT ON mysql.time_zone_name TO '${DB_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
EOSQL

# Load timezone data
mysql_tzinfo_to_sql /usr/share/zoneinfo 2>/dev/null | mysql -u root mysql 2>/dev/null || true

# Import Cacti schema
echo "Importing Cacti schema..."
mysql -u root ${DB_NAME} < /var/www/html/cacti/cacti.sql

# Set the version to 1.2.26 to skip the installer
mysql -u root ${DB_NAME} -e "UPDATE version SET cacti='1.2.26';"

# Configure Cacti database connection
cat > /var/www/html/cacti/include/config.php << 'PHPEOF'
<?php
$database_type     = 'mysql';
$database_default  = 'cacti';
$database_hostname = '127.0.0.1';
$database_username = 'cactiuser';
$database_password = 'cactipass';
$database_port     = '3306';
$database_retries  = 5;
$database_ssl      = false;
$database_ssl_key  = '';
$database_ssl_cert = '';
$database_ssl_ca   = '';

$url_path = '/cacti/';
PHPEOF
sed -i "s|'cactipass'|'${DB_PASS}'|" /var/www/html/cacti/include/config.php
chown www-data:www-data /var/www/html/cacti/include/config.php

# Set up admin user with a per-boot rotated password
ADMIN_HASH=$(php -r "echo password_hash('${CACTI_ADMIN_PASSWORD:?CACTI_ADMIN_PASSWORD not set}', PASSWORD_DEFAULT);")
mysql -u root ${DB_NAME} -e "UPDATE user_auth SET password='${ADMIN_HASH}', must_change_password='', enabled='on' WHERE username='admin';"

# Remove default guest (id=3 from cacti.sql) and create fresh one
mysql -u root ${DB_NAME} -e "DELETE FROM user_auth WHERE username='guest';"
GUEST_HASH=$(php -r "echo password_hash('guest', PASSWORD_DEFAULT);")
mysql -u root ${DB_NAME} -e "INSERT INTO user_auth (username, password, realm, full_name, must_change_password, enabled, login_opts, policy_graphs, policy_trees, policy_hosts, policy_graph_templates) VALUES ('guest', '${GUEST_HASH}', 0, 'Guest Account', '', 'on', 1, 1, 1, 1, 1);"

# Give guest user basic graph viewing permission (realm 7 = view graphs)
GUEST_ID=$(mysql -u root -N -e "SELECT id FROM user_auth WHERE username='guest' LIMIT 1" ${DB_NAME} | tr -d '[:space:]')
echo "Guest user ID: ${GUEST_ID}"
if [ -n "$GUEST_ID" ]; then
    mysql -u root ${DB_NAME} -e "INSERT IGNORE INTO user_auth_realm (realm_id, user_id) VALUES (7, ${GUEST_ID});"
fi

# Settings to skip installer checks
mysql -u root ${DB_NAME} << 'EOSQL'
REPLACE INTO settings (name, value) VALUES ('install_complete', '1');
REPLACE INTO settings (name, value) VALUES ('path_rrdtool', '/usr/bin/rrdtool');
REPLACE INTO settings (name, value) VALUES ('path_snmpwalk', '/usr/bin/snmpwalk');
REPLACE INTO settings (name, value) VALUES ('path_snmpget', '/usr/bin/snmpget');
REPLACE INTO settings (name, value) VALUES ('path_snmpbulkwalk', '/usr/bin/snmpbulkwalk');
REPLACE INTO settings (name, value) VALUES ('path_snmpgetnext', '/usr/bin/snmpgetnext');
REPLACE INTO settings (name, value) VALUES ('path_php_binary', '/usr/local/bin/php');
REPLACE INTO settings (name, value) VALUES ('path_cactilog', '/var/www/html/cacti/log/cacti.log');
REPLACE INTO settings (name, value) VALUES ('rrdtool_version', 'rrd-1.7.x');
REPLACE INTO settings (name, value) VALUES ('default_datechar', '1');
EOSQL

# Ensure log file exists
touch /var/www/html/cacti/log/cacti.log
chown www-data:www-data /var/www/html/cacti/log/cacti.log

# Seed monitored devices
mysql -u root ${DB_NAME} <<'EOSQL' || true
INSERT INTO host (host_template_id, description, hostname, snmp_community, snmp_version, availability_method, ping_method, status, disabled)
VALUES
 (0,'Core Router','10.0.0.1','public',2,0,1,3,''),
 (0,'Edge Firewall','10.0.0.2','public',2,0,1,3,''),
 (0,'App Server 01','10.0.1.10','public',2,0,1,3,''),
 (0,'App Server 02','10.0.1.11','public',2,0,1,3,''),
 (0,'DB Server 01','10.0.1.20','public',2,0,1,3,''),
 (0,'Core Switch A','10.0.0.10','public',2,0,1,3,''),
 (0,'Core Switch B','10.0.0.11','public',2,0,1,3,'');
EOSQL

echo "Cacti initialization complete."
exec apache2-foreground
