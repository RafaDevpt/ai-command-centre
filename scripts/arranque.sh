#!/bin/sh
# Migrações e depois o servidor. Created by Redfox using Claude
set -e
alembic upgrade head
exec uvicorn app.main:app --host "${AICC_HOST:-127.0.0.1}" --port "${AICC_PORT:-3000}" \
  --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header --log-level "${AICC_LOG_LEVEL:-info}"
