#!/bin/sh
set -eu

# Deploys migrate and upsert the public runtime fixture set before serving.
# Evaluation labels stay out of the application bootstrap path.
uv run alembic upgrade head
uv run python -m incident_atlas.cli seed-runtime

exec "$@"
