FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/api

RUN pip install --no-cache-dir uv
COPY api/pyproject.toml api/uv.lock api/README.md ./
COPY api/incident_atlas ./incident_atlas
COPY api/migrations ./migrations
COPY api/alembic.ini ./alembic.ini
RUN uv sync --locked --no-dev --extra observability

COPY api/docker-entrypoint.sh ./docker-entrypoint.sh
RUN uv sync --locked --no-dev --extra observability

WORKDIR /app
COPY data ./data
WORKDIR /app/api
RUN chmod +x ./docker-entrypoint.sh && useradd --create-home --uid 10001 atlas
USER atlas

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=4s --start-period=30s --retries=3 \
  CMD python -c "import os; from urllib.request import urlopen; urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/readyz', timeout=3)"

ENTRYPOINT ["/app/api/docker-entrypoint.sh"]
CMD ["/bin/sh", "-c", "exec uv run uvicorn incident_atlas.main:app --app-dir . --host 0.0.0.0 --port \"${PORT:-8000}\""]
