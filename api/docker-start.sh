#!/bin/sh
set -eu

# Render also exposes pre-deploy secrets to the one-off deploy command. Remove
# them before the API process starts; the running API only receives its limited
# DATABASE_URL and never inherits the migration role password.
unset MIGRATION_DATABASE_URL RUNTIME_DB_PASSWORD

exec uv run --no-sync uvicorn incident_atlas.main:app \
  --app-dir . \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --no-proxy-headers
