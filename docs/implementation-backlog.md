# Ordered implementation backlog

**Status:** Step 1 blueprint complete; implementation not started  
**Reviewed:** 2026-11-22

## Ordered phases

### Step 2 — Backend Development

Deliver the repository foundation and backend contract first. Exact acceptance criteria are below.

1. Initialize the `incident-atlas` Git repository and public GitHub remote when available; add repository README, license decision, `.gitignore`, and contribution/setup notes. Keep secrets out of source.
2. Establish API source tree, supported Python version, lockfile, FastAPI app, health route, structured logging, configuration validation, and OpenAPI schema.
3. Define SQLAlchemy models and Alembic migrations for the entities in [data design](data-design.md); add database readiness checks and least-privilege connection configuration.
4. Implement deterministic, idempotent seed data for all three scenarios and evaluation labels in separate runtime/evaluation paths. Generate evidence IDs and stored replay responses with provenance.
5. Implement bounded read APIs for capabilities, incident catalogue/detail, timeline, dependencies, telemetry, and replay. Enforce all row/time/body caps and explicit source labels.
6. Implement investigation service: fixed read-only query pack, deterministic evidence snapshot and SHA-256, rules baseline, one structured AI inference when enabled, output validation, evidence-link validation, timeout/refusal/error recording, and safe persistence.
7. Implement GET investigation and append-only simulated mitigation approval endpoint. Prove by schema/route design that no external action path exists.
8. Add API contract docs, environment example without real credentials, backend README, and operations notes. No live model key is required for local replay development.

### Step 3 — Public website

Build the routes and complete no-key journey in [product requirements](product-requirements.md). Add accessible timeline, service dependency view, linked telemetry, prominent live/replay labels, live-off fallback to replay, and explicit simulated-approval confirmation.

### Step 4 — Evaluation and hardening

Implement evaluation transforms and metrics in [evaluation plan](evaluation-plan.md), deterministic CI tests, boundary tests, browser journey, and accessibility checks. Run budgeted live evaluation manually or on an explicitly budgeted schedule.

### Step 5 — Deployment and public launch

Add Docker Compose, Netlify/Render configuration, GitHub Actions, rate limits, provider spend alert, backups, kill switch, preview smoke checks, rollback notes, and methodology results page. Verify the public demo as a recruiter with no login and no API key.

## Step 2 — Backend Development acceptance criteria

Step 2 is complete when all of the following are reviewable in the repository:

### Repository and startup

- Git repository exists with the agreed public GitHub remote or a documented remote-creation blocker; initial branch and ignored secret files are clear.
- Backend README states supported Python version, locked dependencies, configuration variables, migration and seed commands, and local API startup.
- A clean local PostgreSQL instance can be migrated and seeded reproducibly. Seeding twice produces no duplicate records and the same fixture logical content/snapshot hashes.
- `GET /healthz` reports readiness safely; interactive OpenAPI is available locally without exposing secrets.

### Data and read APIs

- All three scenario definitions in `incident-scenarios.md` are present, linked to stable timeline, metric, log, span, and dependency evidence, and use versioned synthetic timestamps and values.
- The API contract routes in `api-design.md` exist with typed schemas, documented success/error shapes, UTC timestamps, bounded pagination/windows, and useful 404/422 behavior.
- Fixture labels are kept separate from runtime analysis context. A test or equivalent automated check proves ground-truth labels are never serialized to the public API or model packet.
- Stored replay is returned without a model call, carries `source=stored_replay`, `model_call_made=false`, replay timestamp and fixture version, and all evidence links resolve.

### Investigation and safety boundary

- Live analysis is disabled cleanly when the provider key/feature flag is absent; no visitor key is requested.
- When enabled, one fixed read-only evidence packet and one structured provider request are used, under the specified query and timeout caps. No arbitrary SQL, web, shell, or provider tool execution is exposed to the model.
- A completed run persists the evidence snapshot/hash, model/prompt/schema versions, usage/timings, validated report, and request ID. Each cited evidence ID resolves within that snapshot.
- Provider timeout, unavailable service, refusal, incomplete/schema-invalid output, and unknown evidence reference are explicit failure states; none silently becomes a replay or a proven cause.
- The rules baseline produces a versioned, deterministic ranked-label result on the same snapshot.
- Mitigation approval works for both a live report and a stored replay, requires explicit simulation acknowledgment, appends a record with `simulation_only=true` and `external_action_performed=false`, and cannot call an external target.

### Security and observability

- Exact-origin CORS, parameterized DB reads, size/time/row caps, public live-run rate limits, server-only secrets, and safe error responses are implemented.
- API operational traces/metrics can be enabled with OpenTelemetry configuration; fixture telemetry remains distinct from app telemetry.
- No raw visitor IP, API secret, hidden model reasoning, or unbounded telemetry content is written to application logs.

### Step 2 handoff artifacts

- Backend source and migrations; locked dependency file; seed scenario data; local no-key replay path; OpenAPI contract; environment template; operational README; evaluation runner interface or documented entry point; and a concise backend test/evaluation result report.
- The report includes the exact commands used, deterministic fixture/snapshot hashes, rules baseline outcome for the three base scenarios, timeout/error-path evidence, and any known gap before Step 3.

**Not Step 2 deliverables:** complete visitor UI, production deployment, real telemetry ingestion, account system, or mitigation execution. Those remain later steps.
