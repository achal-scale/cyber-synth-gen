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

# Copy our custom API endpoint
COPY custom_api/ /var/www/html/custom/

# Ensure proper permissions
RUN chown -R www-data:www-data /var/www/html/custom/

# Replace the stock installer's initializeDatabase() (imports ~756 tables/
# keys/functions/data files one mysql process each -- 2+ hours observed)
# with a single bulk-import mysql session (same file order and comment-
# stripping, just batched -- see docker-run-fast.sh for the diff rationale).
COPY docker-run-fast.sh /usr/local/bin/docker-run.sh
RUN chmod +x /usr/local/bin/docker-run.sh

COPY entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh
ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
CMD ["apache2-foreground"]

EXPOSE 80
