# Deployment and staged release runbook

**Target:** GitHub → Netlify React/Vite site → Render FastAPI and PostgreSQL.
**Current state:** configuration and CI are prepared; no Render or Netlify resources have been provisioned. Do not create recurring resources until the account, billing setup, and monthly spending cap are approved.

## Local Docker Compose

From the repository root:

```bash
docker compose up --build
```

Compose starts PostgreSQL 17, waits for readiness, and runs a one-shot bootstrap container. It applies migrations and idempotently seeds runtime incidents and replays. FastAPI starts separately and does not run migrations at request-service startup. The web app is at `http://localhost:5173`, API readiness is at `http://localhost:8000/readyz`, and live AI is off by default. The stored replay and simulated approval work without a model key.

## Release prerequisites

1. Approve a recurring spending cap and confirm the Render and Netlify accounts have billing and project access. Include the database plan, web-service plan, backups, bandwidth, and any usage charges in the cap.
2. Keep `LIVE_ANALYSIS_ENABLED=false`. No model key is needed for the public replay journey. Do not add a model key until the shared request cap, real proxy trust path, and provider verification are ready.
3. Confirm the repository revision has green CI and the release ZIP inspection job passed. No license decision is part of the technical deployment gate; see [license decision](licensing-decision.md).

## Staged deployment order

The three hostnames become known at different stages. Follow this order so the site origin is known before CORS is configured, and the API origin is known before Vite builds the public bundle.

### Stage 1 — reserve the Netlify site and record its origin

1. In the authorized Netlify account, create or reserve the Incident Atlas site name from the GitHub repository. Pause automatic production publishing until the API is ready.
2. Record the exact default HTTPS site origin, such as `https://<reserved-name>.netlify.app`, in the deployment worksheet. Do not invent the origin or add a path or trailing slash to the stored value.
3. A custom domain can be attached later. If it is used, use that exact origin consistently for both Render CORS variables and the smoke command.

### Stage 2 — provision Render PostgreSQL and preserve the migration credential

1. Create the PostgreSQL database in the same Render region as the API service.
2. Before adding or rotating any database credential, copy the initial database connection string into the protected `MIGRATION_DATABASE_URL` Render environment variable. This value is secret. Do not put it in Git, a shell transcript, a screenshot, or a report.
3. Use the internal database connection hostname for the Render-hosted API and migration job. `DATABASE_URL` and `MIGRATION_DATABASE_URL` must point to the same host, port, and database.

### Stage 3 — prepare the restricted runtime database user

The pre-deploy command checks the configured runtime username, URL-encoded password, target database, PostgreSQL role attributes, migration privileges, and the exact table grants. It returns a short non-secret error if the checks fail. It never prints either database URL or password.

1. If the migration login can create the restricted `incident_atlas_runtime` role, the bootstrap creates it with login only and no superuser, database-creation, role-creation, replication, or RLS-bypass attributes.
2. If role creation is denied, do not use the migration login as the API runtime user. Before the first pre-deploy run, create a Render-managed PostgreSQL credential named `incident_atlas_runtime` in the database credentials UI or API. The migration URL stays pinned to the original database owner; migrations create the tables, then the bootstrap grants the already-created runtime role only the privileges it needs. Render documents that adding a managed credential makes it the database's new default; the previous user remains valid, but its password is no longer shown in the dashboard. That is why `MIGRATION_DATABASE_URL` must be saved as a protected secret before creating the runtime credential. See [Render's credential rotation guide](https://render.com/docs/postgresql-credentials).
3. Copy the new runtime credential into `DATABASE_URL` and set `RUNTIME_DB_PASSWORD` to its decoded password. Percent-encode special characters in the URL password. Bootstrap compares the decoded URL password against `RUNTIME_DB_PASSWORD`, so the values cannot drift silently. It rejects a runtime role that owns the database/schema/tables or inherits privileges through role membership.
4. The migration login must be able to create schemas and public objects, own the migration table, and grant privileges on the resulting tables. Bootstrap checks database/schema creation and migration-table ownership before migrating, then runs the exact runtime grant matrix inside a rollbackable preflight and applies it only if PostgreSQL accepts the grant set. If this fails, stop. Use the database's authorized original owner credential for `MIGRATION_DATABASE_URL` or arrange the grants through the authorized database administration path. Do not work around the check by giving the API a broad owner credential.

Render does not provide PostgreSQL superuser access; `CREATE ROLE` requires `CREATEROLE` or superuser privileges. The managed-credential path above is the provisioning alternative when role creation is unavailable. The runtime grant matrix still has to pass; the managed credential itself does not count as proof that the API role is least-privileged. See [PostgreSQL `CREATE ROLE`](https://www.postgresql.org/docs/current/sql-createrole.html).

### Stage 4 — configure Render and start the API

Set these values in the Render API service before the first deploy:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `MIGRATION_DATABASE_URL` | The pinned migration connection URL from Stage 2. Keep it secret and static; `render.yaml` intentionally uses `sync: false`. |
| `DATABASE_URL` | The runtime credential URL, on the same internal host, port, and database. Username must be `incident_atlas_runtime`. |
| `RUNTIME_DB_PASSWORD` | The decoded password matching `DATABASE_URL`. |
| `PUBLIC_SITE_ORIGIN` | The exact HTTPS origin recorded in Stage 1. |
| `CORS_ALLOWED_ORIGINS` | A one-item list containing the exact same origin. |
| `TRUSTED_PROXY_CIDRS` | Only proxy CIDRs verified from the actual Render ingress path. Leave live AI off until this is verified. |
| `RATE_LIMIT_HMAC_KEY` | A long random secret. Render can generate it through the Blueprint. |
| `RATE_LIMIT_ENABLED` | `true`. |
| `RATE_LIVE_GLOBAL_RUNS` / `RATE_LIVE_GLOBAL_WINDOW_SECONDS` | Keep the shared cap at 5 requests per 86,400 seconds or lower while live AI is disabled. |
| `LIVE_ANALYSIS_ENABLED` / `LIVE_PROVIDER_VERIFIED` | Both `false`. |

The API's `preDeployCommand` runs `uv run --no-sync python -m incident_atlas.cli deploy-bootstrap`. It checks the managed-PostgreSQL role/grant path, runs Alembic migrations, seeds only public runtime fixtures, applies the table-by-table grant matrix, then connects once using `DATABASE_URL` to verify the configured runtime login. It never starts the API if role creation, grants, or runtime authentication fail. The API startup script removes `MIGRATION_DATABASE_URL` and `RUNTIME_DB_PASSWORD` from the long-running process environment.

The runtime database role receives read access to incident and replay reference data. It can insert snapshots, evidence rows, investigations, hypotheses, audit records, simulated approvals, and rate events; update only the completion, error, usage, provider-request, and uncertainty columns of investigations; and execute one fixed cleanup function. The function can delete only rate events older than seven days, the longest supported rate window. The runtime role cannot directly delete rate records or update/delete seeded incident/reference data, stored replays, evidence snapshots, hypotheses, or approvals; it cannot read the evaluation schema, create public objects, or alter migrations.

Once the Render deploy is healthy, record the actual public API origin, such as `https://<service>.onrender.com`. Verify `/readyz` before proceeding.

### Stage 5 — publish Netlify with the real API URL

1. Set Netlify's build environment variable `VITE_API_BASE_URL` to the actual Render API origin plus exactly `/api/v1`, for example `https://<real-service>.onrender.com/api/v1`.
2. Run the production build. It fails if the value is missing, relative, not HTTPS, uses a reserved example/test hostname, embeds credentials, or has a path other than `/api/v1`.
3. Publish the site from the same Git commit that passed CI. Do not set a fake API base or a visitor/model credential in any `VITE_` variable.

### Stage 6 — post-deployment smoke and browser verification

Run this from a trusted workstation after both services are deployed:

```bash
python scripts/deployment_smoke.py \
  --api-origin https://<actual-render-api-origin> \
  --site-origin https://<actual-netlify-site-origin>
```

The command checks JSON readiness, JSON API responses with CORS headers, the exact API URL embedded in the built JavaScript, and a browser-style POST preflight from the real website origin. It never submits an approval or changes application data. Then open the public site on desktop and mobile and complete the replay journey manually: choose an incident, inspect telemetry, open its stored replay, follow each citation, acknowledge the simulated mitigation, and verify the persisted response has `simulation_only=true` and `external_action_performed=false`.

Record only observed URLs, command output, and browser outcomes in the release report. CI screenshots are local test evidence; they are not public-deployment screenshots.

## CI and release archive

GitHub Actions runs PostgreSQL migrations, repeated seed/hash checks, backend integration tests, Python lint and dependency audit, rules evaluation, frontend tests/typecheck/build/dependency audit, API image build/runtime smoke, and local desktop/mobile Playwright checks. The database and browser jobs run on GitHub-hosted CI; local sandbox failures to start PostgreSQL or Docker are not reported as passing checks.

Create and inspect a release archive in a real Git checkout:

```bash
python scripts/build_release_zip.py --output /tmp/incident-atlas-release.zip
```

The command reads the tracked Git file list, writes only eligible tracked project files, checks required files and ZIP integrity, and rejects Git metadata, `.codex` configuration, generated output, local environments, caches, database files, and secret-shaped files. The CI packaging check runs this same command.

## OpenTelemetry Demo import path

The public scenarios remain authored synthetic fixtures until an actual Demo capture is imported and labeled. The project includes an offline OTLP/JSON trace adapter and a separate import guide. It records a source hash and requires an explicit Demo version and scenario name; it does not infer ground truth or insert imported telemetry into the public database. See [OpenTelemetry Demo import](otel-demo-import.md).

## Rollback and provenance

- If the API is unhealthy, disable live analysis and redeploy; stored replays remain available.
- Deploy API and static web from the same tested commit. Migrations run as an explicit pre-deploy task; request-service startup never migrates.
- The three base incidents, six derived variants, and three independent authored cases are deterministic synthetic regression data. They are not real-world incident accuracy measurements.
- A successful OpenTelemetry importer unit test does not mean the OpenTelemetry Demo itself was run or imported. A source capture must be independently versioned, hashed, reviewed, and labeled before it enters an evaluation dataset.
- The daily live-call cap is an application usage cutoff, not a provider billing limit. Configure provider-side spend limits before enabling live inference.
