# Base pinned by digest. Resolves to tuxgasy/dolibarr:17.0.0.
FROM tuxgasy/dolibarr:17.0.0@sha256:09b5304578c0c2daadf9bf83c79fcbb64eff81d5f7486cca5c58627fc3a202e5

# Buster is EOL, switch to archive repos
RUN sed -i 's/deb.debian.org/archive.debian.org/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/archive.debian.org/g' /etc/apt/sources.list && \
    sed -i '/buster-updates/d' /etc/apt/sources.list && \
    echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no-check-valid

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client curl \
    && rm -rf /var/lib/apt/lists/*

# Local overlays for constall.php and core/lib/files.lib.php.
COPY core/lib/files.lib.php /var/www/html/core/lib/files.lib.php
RUN chown www-data:www-data /var/www/html/core/lib/files.lib.php

# Faster bulk-import installer (same import order, batched).
COPY docker-run-fast.sh /usr/local/bin/docker-run.sh
RUN chmod +x /usr/local/bin/docker-run.sh

COPY entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh
ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
CMD ["apache2-foreground"]

EXPOSE 80
