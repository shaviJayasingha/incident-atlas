# Backend handoff report

**Status:** Step 2 implementation prepared; PostgreSQL integration gate is blocked in this execution environment.  
**Fixture version:** `1.0.0`  
**Label dataset:** `labels-v1`  
**Reviewed:** 2026-11-22

## What is implemented

- FastAPI service with versioned incident, timeline, dependency, telemetry, snapshot evidence, replay, live investigation, approval, capabilities, liveness, and readiness contracts. OpenAPI is served at `/openapi.json`.
- PostgreSQL SQLAlchemy models and an Alembic initial migration for runtime data and the separate `evaluation` schema. PostgreSQL triggers reject updates or deletes to snapshot and snapshot-evidence rows.
- Idempotent deterministic seeding for three synthetic cases, immutable evidence snapshots with SHA-256 hashes, curated replay payloads, and a separate explicit label seeding command.
- Stored replay path that returns `source=stored_replay`, `model_call_made=false`, zero model usage, and no provider call.
- Rules baseline and offline evaluator. Public rule signal labels differ from the evaluation answer-key labels. The offline evaluator is not imported by the API or live provider path.
- Optional one-request OpenAI Responses workflow using a server-side key, strict JSON schema, no tools, bounded evidence, explicit uncertainty, server-validated snapshot citations, recorded usage/model/prompt/schema/trace metadata, and explicit failure statuses.
- Replay and live approval routes that require `simulation_acknowledged=true` and persist `simulation_only=true`, `external_action_performed=false`. No mitigation executor exists.
- CORS, request-size and query-window caps, page limits, HMAC-keyed guest limits, an in-process live concurrency cap, SQL statement timeouts, safe request logging, optional OpenTelemetry instrumentation, and health endpoints.
- PostgreSQL integration tests and database-independent rules/provider tests.

## Setup and run commands

Use Python 3.12 and PostgreSQL 15 or newer. From a clean checkout:

```bash
cd api
cp .env.example .env
uv sync --locked --extra dev --extra observability
```

Set `DATABASE_URL` in the untracked `.env` to a local PostgreSQL database. Set a non-placeholder `RATE_LIMIT_HMAC_KEY` outside development. Keep `LIVE_ANALYSIS_ENABLED=false` unless the API host has a server-side `OPENAI_API_KEY`.

Migrate, seed runtime fixtures, and seed labels separately:

```bash
uv run alembic upgrade head
uv run python -m incident_atlas.cli seed-runtime
uv run python -m incident_atlas.cli seed-evaluation
uv run python -m incident_atlas.cli fixture-manifest
```

Start the service and open its API docs:

```bash
uv run uvicorn incident_atlas.main:app --app-dir . --host 127.0.0.1 --port 8000
```

`GET /healthz` checks liveness; `GET /readyz` checks PostgreSQL readiness; `GET /docs` and `GET /openapi.json` expose generated API documentation. To inspect the offline baseline without a database, run:

```bash
uv run python -m incident_atlas.cli evaluate-fixtures
```

For database checks, use a disposable PostgreSQL database. The test fixture truncates its application tables before each integration case:

```bash
TEST_DATABASE_URL=postgresql+psycopg://incident_atlas:incident_atlas@localhost:5432/incident_atlas_test \
  uv run pytest -q -rs
uv run ruff check .
```

Without `TEST_DATABASE_URL`, the dev extra attempts to start an isolated embedded PostgreSQL server. A sandbox runner that prohibits local sockets may skip the marked PostgreSQL tests; the handoff below records what happened here.

## Fixture hashes

Snapshot hashes use canonical JSON over the exact timestamped evidence items built by the seed loader. They can be regenerated with `fixture-manifest` after migrating and seeding.

| Incident | Evidence count | Scenario SHA-256 | Snapshot ID | Snapshot SHA-256 | Replay ID |
|---|---:|---|---|---|---|
| `inc-cache-collapse-001` | 71 | `428325f2a1185cdec21e0b84a6fa4a96e3660b9f5f9f38ed831aeda48e6f6bc4` | `snap-inc-cache-collapse-001-1.0.0` | `7d09c04c3856d9fcc5e1c9b1a07581bbe5447e162d85dca700c7aa139d55d15d` | `replay-cache-v1` |
| `inc-inventory-pool-002` | 71 | `a49a23b5310ac87954df2fd43d97c7818c1d2f1c25d9445e46936252bc780252` | `snap-inc-inventory-pool-002-1.0.0` | `7ee8b70c152ea0e654758c62c7146b7b0df646f6c9c8cd0a717b59e5bd13f75d` | `replay-pool-v1` |
| `inc-payment-gateway-003` | 87 | `244cf1449c76dea0ba474ff635c6f5a8dbbe0cad9bdc7a9b854aab2740f6ffd2` | `snap-inc-payment-gateway-003-1.0.0` | `a15f0a87598bd002d7123600578911f98e84087d3eca35e6be4cb0256ab92ed6` | `replay-gateway-v1` |

Additional content hashes:

- `data/incidents/scenarios.json` file SHA-256: `6a8eea31a04e09e59d0c3ade764995c13761638c1f9994316c1596cb2ad7c2cf`
- `data/incidents/replays.json` file SHA-256: `bf79365af69e27495e325804456a03297e16f71cc60860f03930b35106c973d9`
- Canonical evaluation dataset SHA-256: `8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca`

## Rules-baseline results

Measured offline by `uv run python -m incident_atlas.cli evaluate-fixtures` against all three deterministic cases. This executes the same rules function as the API against fixture-built telemetry and reads labels only in the offline evaluator.

| Case | Predicted primary label | Expected evidence recall | Reciprocal rank | Top-1 |
|---|---|---:|---:|---:|
| Cache collapse | `cache_key_version_mismatch` | 0.50 | 1.00 | Correct |
| Inventory pool saturation | `inventory_connection_leak` | 0.40 | 1.00 | Correct |
| Payment gateway latency | `upstream_payment_gateway_latency` | 0.67 | 1.00 | Correct |
| **Aggregate** |  | **0.5222 mean** | **1.00 MRR** | **1.00 accuracy** |

Aggregate abstention rate was `0.00` on these three base cases. This is a small synthetic set, not a production reliability estimate. Exact per-case evidence IDs and metric output are reproducible through the command above.

## Checks actually run here

| Command | Result |
|---|---|
| `./.venv/bin/ruff check .` | Passed: all checks passed. |
| `./.venv/bin/python -m compileall -q incident_atlas migrations tests` | Passed. |
| SQLAlchemy `configure_mappers()` | Passed. |
| `./.venv/bin/alembic upgrade head --sql` | Passed as offline PostgreSQL SQL generation only; no database was contacted. |
| `./.venv/bin/python -m incident_atlas.cli evaluate-fixtures` | Passed; measured outcomes shown above. |
| `./.venv/bin/pytest -q -rs` | 18 passed; 9 PostgreSQL integration cases skipped. |

The embedded PostgreSQL helper failed during server startup with `PermissionError: [Errno 1] Operation not permitted` while the sandbox attempted to create a local Unix-domain socket. This runner also has no Docker or system PostgreSQL executable. Therefore the database migration, repeated database seeding, API/database integration, live route failure statuses, snapshot trigger behavior, and approval persistence were **not executed against PostgreSQL here**. Those checks exist in `api/tests/test_postgres_backend.py` and must pass against a disposable PostgreSQL 15+ database before the Step 2 database gate can be called complete.

Database-independent error-path checks did run:

| Condition | Provider/service behavior tested | Intended API result |
|---|---|---|
| Provider read timeout | Raises `ProviderTimeout`; status mapper verified. | `504 investigation_timeout` |
| Provider refusal | Raises `ProviderRefusal`; status mapper verified. | `422 provider_refused` |
| Incomplete/malformed structured output | Raises `ProviderInvalidOutput`; schema parser test passed. | `502 invalid_model_output` |
| Unknown or missing/duplicate evidence citation | Snapshot-reference validator rejected it. | `502 invalid_model_output` |
| Provider HTTP 503 | Raises `ProviderUnavailable`; status mapper verified. | `503 provider_unavailable` |

The one-request strict-schema request construction test also passed. PostgreSQL-backed route persistence/error response cases remain skipped as stated above. No live OpenAI request was sent; no provider secret was available or needed.

## Repository and remote blockers

`git init -b main` was attempted and failed because the workspace mounts `.git` as an empty read-only directory (`0555`): Git could not create `.git/description`. `git status --short` consequently reports that this workspace is not a Git repository. The connected GitHub interface had no Incident Atlas repository and exposed no create-repository action; no supplied remote URL exists. No remote was invented or configured. Repository initialization and the remote setup must happen from a writable clone or after a repository URL is supplied through the GitHub workflow.

## Known gaps and handoff conditions

- Run the PostgreSQL integration suite on a runner that can start PostgreSQL or connect to a disposable PostgreSQL database. Confirm clean migration, two identical seed runs, all route responses, live timeout/refusal/schema/evidence failures, and both approval types.
- Confirm a production OpenAI model identifier and make one explicitly enabled smoke request with a server-held key before publishing live analysis. Replay works without that key.
- Step 2 does not add the React/Vite site, Compose file, CI pipeline, hosting resources, or external mitigation action; those remain future implementation/deployment work in the ordered backlog.
- Git repository initialization and remote wiring remain blocked by the read-only Git metadata mount and unavailable create-repository operation described above.

The API does not claim successful diagnosis: model outputs and curated replay findings are hypotheses, evidence-linked to a recorded snapshot, and user approvals only record a simulation.
