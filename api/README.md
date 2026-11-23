# Incident Atlas API

FastAPI backend for a public incident investigation demo. It serves deterministic synthetic incidents, immutable evidence snapshots, stored replays, a rules baseline, and an optional evidence-bounded live model path. The live model path is disabled in deployment configuration. No endpoint executes a mitigation.

## Local setup

Requirements: Python 3.12, `uv`, and PostgreSQL 15+ (Docker Compose is the simplest path). From the repository root:

```bash
docker compose up --build
```

Compose starts PostgreSQL, runs the one-shot `bootstrap` service to migrate and seed runtime fixtures, then starts the API and Vite. Open `http://localhost:5173`; the API is at `http://localhost:8000`. Replay and simulated approval need no model key.

To run the API outside Compose, from `api/`:

```bash
cp .env.example .env
uv sync --locked --extra dev --extra observability
uv run python -m incident_atlas.cli bootstrap-runtime
uv run uvicorn incident_atlas.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload
```

`bootstrap-runtime` applies Alembic migrations and idempotently seeds the three public incidents and saved reports. `DATABASE_URL` can use either `postgresql://` (including Render's URL shape) or `postgresql+psycopg://`; both are normalized to Psycopg 3 for the API and migrations.

## API and operations

- Liveness: `GET /healthz`
- Database readiness: `GET /readyz`
- OpenAPI JSON and interactive docs: `/openapi.json`, `/docs`
- Versioned API base: `/api/v1`

The container starts the API without running migrations. Production migrations and runtime seeding run in the Render pre-deploy command with a pinned `MIGRATION_DATABASE_URL`; the API receives a separate `DATABASE_URL` for the `incident_atlas_runtime` role. `RUNTIME_DB_PASSWORD` must match the decoded password in `DATABASE_URL`; percent-encode special characters in the URL. The bootstrap verifies the role, connection, migration permissions, and exact table grants, then strips migration credentials from the running process. The runtime role has table-specific reads and writes, cannot mutate seeded incidents, replay reports, immutable evidence, hypotheses, or approvals, cannot read the `evaluation` schema, create schema objects, or update `alembic_version`. It cannot directly delete rate events; an owned `SECURITY DEFINER` function removes only records older than seven days, the maximum supported rate-limit window.

Production requires `PUBLIC_SITE_ORIGIN` to be one exact HTTPS origin and `CORS_ALLOWED_ORIGINS` to match it exactly. `TRUSTED_PROXY_CIDRS` must contain only verified ingress proxy ranges; forwarded headers are ignored unless the direct peer is in that allowlist. The production API refuses to expose live AI unless the global request cap, rate limiting, trusted proxy setup, a server-side key, and the manual provider-verification flag are all present. The checked-in deployment config keeps live AI off.

## Evaluation data

Ground-truth labels and the expanded evaluation set live under `data/evaluation/`. They are only used by local development and CI evaluation commands. The API image copies only `data/incidents/`; it does not contain the label file. Runtime seeding never loads evaluation labels. To run the deterministic rules reports in local development:

```bash
uv run python -m incident_atlas.cli evaluate-fixtures
uv run python -m incident_atlas.cli evaluate-expanded
```

These are regression checks on authored synthetic data, not real-world incident accuracy. Current coverage is three base cases, six derived variants, and three independent authored cases; no imported OpenTelemetry Demo capture has been scored. Do not run `seed-evaluation` against a production database. The offline [OTLP/JSON adapter](incident_atlas/otel_demo_import.py) can be run from this package via `python -m incident_atlas.otel_demo_import` after following the [import guide](../docs/otel-demo-import.md).

## Tests and checks

Use a disposable PostgreSQL database. The backend integration suite truncates its application tables and verifies migrations, repeatable seeding, least-privilege grants, API contracts, evidence links, replay isolation, rate controls, and persisted simulation approvals.

```bash
uv run pytest -q -rs
uv run ruff check .
uv audit --locked
```

Set `TEST_DATABASE_URL` to use an external disposable PostgreSQL instance. Without it, the suite attempts to start embedded PostgreSQL; constrained sandboxes may block its socket. Skipped database tests are not a PostgreSQL verification. CI uses an actual PostgreSQL service and also builds **and runs** the production API image against production-shaped URL/role settings.

See [deployment instructions](../docs/deployment.md), [Step 6 report](../docs/step6-report.md), and the current [pre-deployment release report](../docs/predeployment-release-report.md) for deployment requirements and verified commit details.
