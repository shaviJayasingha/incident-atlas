# Step 4 handoff — frontend integration

**Status:** API-backed frontend implemented; PostgreSQL and browser end-to-end gates remain unverified in this runner.  
**Reviewed:** 2026-11-22

## Implemented visitor paths

- Normal mode uses `ApiClient` and FastAPI at `/api/v1`. It never switches to fixture data when an API read fails.
- Incident catalogue, detail, timeline, dependency, metrics/logs/traces, replay, and snapshot evidence reads are normalized to the page view types in the typed client. Paginated reads follow cursors with explicit page caps. Timestamps continue to render in UTC.
- Stored replays open by their replay ID and always request `source=stored_replay`. The report must confirm `source=stored_replay` and `model_call_made=false`; otherwise it is withheld. Replay GETs do not invoke a model.
- Live analysis appears only after `/demo-capabilities` reports `live_ai_enabled=true`. It shows a running state, posts the bounded 15-minute request with an idempotency key, and routes to a report with `source=live_ai`. An uncertain retry reuses its key. Live report responses must confirm `source=live_ai` and `model_call_made=true`. No failed live request falls back to a replay.
- Stable `application/problem+json` fields and request IDs are surfaced. Read requests are cancellable, time out, and retry at most once when the server marks the error retryable. Writes are not automatically retried. Rate-limit `Retry-After` is shown and honored by the live retry control.
- Report citations preserve both `evidence_id` and `evidence_snapshot_id`; the detail panel resolves the cited record through the snapshot evidence route. Evidence lookup failures show an error rather than substitute data.
- Mitigation approval requires a checked acknowledgment, posts to the replay or live approval route according to report provenance, and renders the returned persisted record, including `simulation_only` and `external_action_performed`. No external action is possible in the backend contract.
- Fixture preview remains available only via `VITE_DATA_MODE=fixtures` in Vite development mode. The UI labels it as a development preview, records approval locally, and the production bundle omits the fixture JSON chunk.

No backend API contract changes were needed. Production hosting must set `VITE_API_BASE_URL` to the public API base ending in `/api/v1` and configure exact-origin API CORS. Model credentials remain on the API host.

## Local setup

Start PostgreSQL, migrate/seed the API using [`api/README.md`](../api/README.md), and run FastAPI on `127.0.0.1:8000`. Then:

```bash
cd web
npm ci
npm run dev
```

Vite proxies `/api/*` to FastAPI. To use the separate fixture preview, run from `web/`:

```bash
cp .env.development.fixture.example .env.development.local
npm run dev
```

Verification commands:

```bash
npm test
npm run typecheck
npm run build
```

## Checks run

| Command or check | Result |
|---|---|
| `cd web && npm test` | Passed: 7 Node integration tests for replay reads, pagination, snapshot citation resolution/integrity, live capability states, source-specific live reads, live idempotency, problem errors, safe GET retry, request cancellation, and replay/live approvals. |
| `cd web && npm run typecheck` | Passed. |
| `cd web && npm run build` | Passed: TypeScript build and Vite production bundle. Fixture scenario/replay data was absent from the generated production assets. |
| `cd api && ./.venv/bin/pytest -q -rs` | 18 passed; 9 PostgreSQL cases skipped. |
| Local connected browser walkthrough | Not completed. Vite started on `127.0.0.1:5173`, but the cloud browser returned `ERR_CONNECTION_REFUSED`; its URL policy then denied page observation. No desktop/mobile layout or complete click-through is claimed. |

The frontend tests use mocked HTTP contracts; they verify the client journey and route selection, not a live API/database deployment. No live model request or approval was sent to an external system during verification.

## PostgreSQL gate

**UNVERIFIED.** The backend suite was rerun in this environment. It passed 18 database-independent cases, but all 9 PostgreSQL integration cases skipped because the embedded server failed while creating its local socket with `PermissionError: [Errno 1] Operation not permitted`. The environment has no `docker`, `psql`, or `pg_isready` command and no `TEST_DATABASE_URL`. No authorized CI runner or disposable database connection was available here. Therefore migrations, repeated seeding, PostgreSQL route persistence, evidence snapshot constraints, and both approval persistence paths remain unverified against PostgreSQL.

Run the previously documented PostgreSQL command on a runner that permits PostgreSQL 15+ or provides a disposable database:

```bash
cd api
TEST_DATABASE_URL=postgresql+psycopg://incident_atlas:incident_atlas@localhost:5432/incident_atlas_test \
  uv run pytest -q -rs
uv run alembic upgrade head
uv run python -m incident_atlas.cli seed-runtime
uv run python -m incident_atlas.cli fixture-manifest
uv run python -m incident_atlas.cli seed-runtime
uv run python -m incident_atlas.cli fixture-manifest
```

Compare both fixture manifests with the hashes in [`backend-handoff.md`](backend-handoff.md), and require the PostgreSQL suite to complete without skips before accepting the database gate.

## Browser gate and remaining work

**UNVERIFIED.** A local Vite server started, but the connected browser could not reach it from this runner. The browser policy also denied observation of the refused localhost tab. Desktop and mobile widths, keyboard navigation in a rendered browser, API proxy behavior, evidence deep links, modal submission, and the complete persisted replay/approval journey need a browser environment that can reach both frontend and API.

Remaining acceptance work:

1. Run the PostgreSQL migration, repeated-seed/hash comparison, and all 9 database integration cases in an authorized database runner.
2. Run the connected desktop/mobile browser walkthrough with the API seeded. Confirm the no-key replay journey, evidence links, explicit acknowledgment, and persisted approval flags on screen.
3. Run one explicitly enabled live smoke test only after the deployment has a server-held model credential and a budgeted test environment; the local frontend checks did not call a model.
4. Configure and verify production `VITE_API_BASE_URL`, exact-origin CORS, and static hosting. Public deployment is outside Step 4.

The existing Step 2 Git initialization/remote blocker also remains: the workspace Git metadata mount is read-only and no supplied repository remote is configured.
