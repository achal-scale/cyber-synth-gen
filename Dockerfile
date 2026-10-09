# Base pinned by digest. Resolves to python:3.11-slim.
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better caching)
COPY */requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# Copy application code
COPY */ .

# Standalone mode - no MCP server
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Standardized internal port: 8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run on port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
