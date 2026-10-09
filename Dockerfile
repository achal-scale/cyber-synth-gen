# Base pinned by digest.
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY */requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY */app.py */setup.py */boot.sh ./
RUN chmod +x boot.sh

EXPOSE 8080

CMD ["./boot.sh"]
