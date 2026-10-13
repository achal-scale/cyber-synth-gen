# Base pinned by digest.
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl dnsutils jq && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir requests

# Create log directories
RUN mkdir -p /logs/verifier

WORKDIR /work

CMD ["sh", "-c", "i=0; while [ $i -lt 60 ]; do getent hosts web >/dev/null 2>&1 && break; sleep 2; i=$((i+1)); done; exec sleep infinity"]
