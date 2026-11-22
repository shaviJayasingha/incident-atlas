# Incident Atlas API

FastAPI backend for the Incident Atlas demo. The service serves deterministic synthetic incidents, immutable evidence snapshots, stored investigation replays, a deterministic rules baseline, and optional live analysis using one OpenAI Responses API request. No route executes a mitigation.

## Requirements

- Python 3.12
- PostgreSQL 15 or newer for the deployed service
- `uv` for locked environment setup (or `pip` with `pyproject.toml`)

The Step 2 workspace has Python 3.12 but no Docker or system PostgreSQL binaries. The dev extra uses the `embedded-postgres` wheel to run an isolated real PostgreSQL server without root or Docker. This execution sandbox blocks Unix-domain socket creation, so its PostgreSQL integration tests are skipped here; use a local PostgreSQL server or set `TEST_DATABASE_URL` to a disposable PostgreSQL 15+ database. See [`docs/backend-handoff.md`](../docs/backend-handoff.md) for the exact check results and blocker.

## Setup

From `api/`:

```bash
cp .env.example .env
uv sync --locked --extra dev --extra observability
```

Update `DATABASE_URL` for a local PostgreSQL instance and change the local HMAC key. Live analysis remains disabled until `LIVE_ANALYSIS_ENABLED=true` and a server-side `OPENAI_API_KEY` are configured. The browser never receives the provider key.

## Database and fixtures

From `api/`:

```bash
uv run alembic upgrade head
uv run python -m incident_atlas.cli seed-runtime
uv run python -m incident_atlas.cli seed-evaluation
uv run python -m incident_atlas.cli fixture-manifest
```

Runtime fixture seeding is idempotent and never loads the ground-truth labels. Evaluation labels are stored in the PostgreSQL `evaluation` schema and loaded only by the explicit evaluation command. The API query layer does not import or query the evaluation model.

Run the offline baseline evaluator directly from versioned fixtures and labels:

```bash
uv run python -m incident_atlas.cli evaluate-fixtures
```

The evaluator is not imported by the API request or live model path. Its `expected_primary_label` output is for local evaluation only; public rules signals use separate names.

## Run the API

```bash
uv run uvicorn incident_atlas.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload
```

- Liveness: `GET /healthz`
- Database readiness: `GET /readyz`
- OpenAPI JSON: `GET /openapi.json`
- Swagger UI: `GET /docs`
- Versioned API base: `/api/v1`

## Run tests

By default, tests start an isolated embedded PostgreSQL server and apply the migrations. Set `TEST_DATABASE_URL` to use a separate disposable PostgreSQL database. The PostgreSQL tests truncate application tables, so do not point it at a shared or production database. Tests deliberately reject SQLite because JSONB, schema separation, advisory locks, database triggers, and constraints are part of the contract.

```bash
TEST_DATABASE_URL=postgresql+psycopg://incident_atlas:incident_atlas@localhost:5432/incident_atlas_test \
  uv run pytest
uv run ruff check .
```

If an execution sandbox blocks Unix sockets, PostgreSQL-marked tests are reported as skipped while database-independent tests still run. Do not treat skipped integration tests as a PostgreSQL pass. Never point `TEST_DATABASE_URL` at production or a shared database.

## Configuration

See `.env.example`. `LIVE_ANALYSIS_ENABLED` is a feature switch; `OPENAI_API_KEY` is required to make a live call. Missing configuration leaves replay and read routes available. Set `CORS_ALLOWED_ORIGINS` to exact browser origins. Set `RATE_LIMIT_HMAC_KEY` to a random secret outside development.

## Safety and provenance

- Model input is one server-built, read-only fixture evidence packet. No model function tools, SQL, shell, arbitrary URL, user prompt, or production credentials are exposed.
- Reports persist evidence snapshot hash, model ID, prompt/schema versions, token usage, request ID, and trace ID.
- Every reported evidence ID is validated against the recorded snapshot. The evidence route reads only within that snapshot.
- Replay reports are stored and always return `source=stored_replay` and `model_call_made=false`.
- Live reports are hypotheses with explicit uncertainty. Invalid output, refusal, unknown evidence, and provider timeout fail explicitly.
- Approval rows are append-only, simulation-only, and never call an external action.
