# Cacti 1.2.26, built from official Cacti project source (GPL-2.0).
# This release predates the fixes for:
#   - CVE-2024-31445  (SQLi in automation_get_new_graphs_sql, fixed in 1.2.27)
#   - CVE-2024-25641  (path traversal in import_package, fixed in 1.2.27)
# The application is shipped UNMODIFIED.
FROM php:8.1-apache-bookworm@sha256:a935f4a5717427519337269d5d1c89968cc27ab84d1c8d5d7b5363672d800cd5

ENV DEBIAN_FRONTEND=noninteractive
ENV CACTI_VERSION=1.2.26

# Install system dependencies and MariaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    mariadb-server mariadb-client \
    rrdtool librrd-dev \
    libsnmp-dev snmp snmpd \
    libfreetype6-dev libjpeg62-turbo-dev libpng-dev libwebp-dev \
    libgmp-dev libldap2-dev libicu-dev libzip-dev libonig-dev libxml2-dev \
    curl wget ca-certificates \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install PHP extensions needed by Cacti
RUN docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp && \
    docker-php-ext-install -j$(nproc) \
    gd gmp intl ldap mbstring mysqli pdo pdo_mysql \
    snmp xml zip sockets posix gettext && \
    a2enmod rewrite

# Download official Cacti 1.2.26 source
# Cacti ${CACTI_VERSION} source tarball vendored into the build context (no build-time
# GitHub fetch); integrity checked against its pinned sha256.
COPY cacti-1.2.26.tar.gz /tmp/cacti.tar.gz
RUN cd /tmp && \
    echo "03e4e224e0e01aa9d13e6a8c3f15f2e446c47ffd3143a76b538b24db062df5fa  /tmp/cacti.tar.gz" | sha256sum -c - && \
    tar xzf cacti.tar.gz && \
    mv cacti-release-${CACTI_VERSION} /var/www/html/cacti && \
    rm cacti.tar.gz

# Set ownership and permissions
RUN chown -R www-data:www-data /var/www/html/cacti && \
    chmod -R 775 /var/www/html/cacti/resource \
                 /var/www/html/cacti/cache \
                 /var/www/html/cacti/log \
                 /var/www/html/cacti/scripts \
                 /var/www/html/cacti/rra

# Configure PHP
RUN echo "memory_limit = 512M" >> /usr/local/etc/php/conf.d/cacti.ini && \
    echo "max_execution_time = 60" >> /usr/local/etc/php/conf.d/cacti.ini && \
    echo "date.timezone = UTC" >> /usr/local/etc/php/conf.d/cacti.ini && \
    echo "mysqli.default_socket = /run/mysqld/mysqld.sock" >> /usr/local/etc/php/conf.d/cacti.ini && \
    echo "pdo_mysql.default_socket = /run/mysqld/mysqld.sock" >> /usr/local/etc/php/conf.d/cacti.ini

# Disable dangerous PHP functions to prevent RCE from path-traversal-written files
# proc_open/popen are kept because Cacti/RRDtool needs them
RUN echo "disable_functions = exec,passthru,shell_exec,system,pcntl_exec,pcntl_fork" \
    >> /usr/local/etc/php/conf.d/security.ini

# Apache: only execute PHP inside /var/www/html/cacti/ — files written 
# elsewhere by path traversal cannot be served as PHP
RUN printf '<Directory />\n\
    php_admin_flag engine off\n\
</Directory>\n\
<Directory /var/www/html/cacti>\n\
    php_admin_flag engine on\n\
    Options Indexes FollowSymLinks\n\
    AllowOverride All\n\
    Require all granted\n\
</Directory>\n' > /etc/apache2/conf-available/cacti.conf && \
    a2enconf cacti

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
