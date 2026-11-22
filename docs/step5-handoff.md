# Step 5 handoff — completion and verification status

**Status:** Source and launch configuration prepared and published. Production deployment, provider-backed live AI, and deployed browser walkthrough remain unverified.  
**Reviewed:** 2026-11-22

## Preflight findings

Before Step 5 changes, the implementation had no Incident Atlas deployment, container, Compose configuration, or CI workflow. The workspace Git metadata directory was read-only. The nine PostgreSQL tests had not run because the runner blocks the embedded PostgreSQL socket. The UI client journey was mocked in tests but had never reached a real API/database from a browser. No server-side OpenAI key was configured. The synthetic fixtures were approved in ADR-002 but needed an explicit provenance statement for launch.

The full inventory is in [`step5-preflight.md`](step5-preflight.md).

## Changes delivered

- Added a non-root FastAPI container image at [`Dockerfile`](../Dockerfile). It runs the Alembic migration and idempotent runtime fixture seed before serving, reads Render's injected `PORT`, and probes database readiness at `/readyz`.
- Added [`compose.yaml`](../compose.yaml) for PostgreSQL 17, the API, and Vite. The API and web wait for dependency health. Live AI is off by default and credentials remain API-only.
- Added [`ci.yml`](../.github/workflows/ci.yml). Its PostgreSQL service job migrates, seeds twice, compares manifests, runs the full backend suite and Ruff. Its frontend job runs tests, typecheck, and production build.
- Added [`netlify.toml`](../netlify.toml) for a static Vite build and client route fallback, plus [`render.yaml`](../render.yaml) for the API container and managed PostgreSQL.
- Made the Vite API proxy target configurable for Compose while retaining `127.0.0.1:8000` as the local default.
- Documented that the public dataset is authored deterministic synthetic OpenTelemetry-shaped data, not imported from OpenTelemetry Demo. The source JSON, loader, fixture version, seeds, and hashes define the reproducible generation path. Ground-truth labels remain separate.
- Created the public GitHub repository [`shaviJayasingha/incident-atlas`](https://github.com/shaviJayasingha/incident-atlas). The original checkout's `.git` directory remains read-only; local repository metadata now lives in the writable `.git-step5` directory and is used with `git --git-dir="$PWD/.git-step5" --work-tree="$PWD"`.

## Commands run and observed results

| Command | Result |
|---|---|
| `cd api && ./.venv/bin/pytest -q -rs` | 18 passed; 9 PostgreSQL tests skipped. The embedded server failed with `PermissionError: [Errno 1] Operation not permitted`; no `TEST_DATABASE_URL`, Docker, Podman, `psql`, or `pg_isready` is available here. This is not a PostgreSQL pass. |
| `cd api && ./.venv/bin/ruff check .` | Passed: all checks passed. |
| `cd api && ./.venv/bin/python -m incident_atlas.cli evaluate-fixtures` | Ran against the unchanged fixture/label sources: 3/3 top-1 labels correct, MRR 1.0, mean supporting evidence recall 0.5222, abstention 0.0. This is the rules baseline, not live AI. |
| `cd web && npm test` | Passed: 7/7 integration tests. |
| `cd web && npm run typecheck` | Passed. |
| `cd web && npm run build` | Passed with Vite 8.3.8. |
| `docker compose up --build` | Not run: Docker and Podman are not installed. |
| PostgreSQL migrations + repeated seed + all nine database tests | Not run against PostgreSQL in this runner. The new GitHub Actions workflow is configured to execute them; its run must be checked before accepting this gate. |

The test output includes a Starlette deprecation warning for `httpx` with `TestClient`; it did not fail the suite.

## Dataset and evaluation provenance

The public fixture inputs are `data/incidents/scenarios.json` and `data/incidents/replays.json`, version `1.0.0`. They are project-authored synthetic records and are converted to runtime evidence by the deterministic fixture loader. They are not real production telemetry and were not fetched from an OpenTelemetry Demo deployment. The separate answer-key file is `data/evaluation/labels.json` (`labels-v1`) and is never loaded by public runtime seeding or included in live model input.

Observed raw file SHA-256 values:

| Source | SHA-256 |
|---|---|
| `data/incidents/scenarios.json` | `6a8eea31a04e09e59d0c3ade764995c13761638c1f9994316c1596cb2ad7c2cf` |
| `data/incidents/replays.json` (Step 5 contract-aligned source) | `438c73cd36dcbe214cc3669d19188c5e63a266822090f9da5b8c263af75a46b5` |
| `data/evaluation/labels.json` | `a50413a43dce171cf80d6a9a1c5e1845b0db078a2f22c19d718c2d8ef0164e63` |

The evaluator's canonical labels dataset hash is `8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca`. Existing per-snapshot evidence hashes and evidence counts are recorded in [`backend-handoff.md`](backend-handoff.md); Step 5 has not regenerated them against a PostgreSQL server.

## Hosting limits checked before launch

The public hosting plan is still Netlify static + Render API/PostgreSQL. Official pricing and plan docs were checked on 2026-11-22:

- Render lists low-end always-on API compute at $7/month and the smallest paid PostgreSQL compute at $6/month (about $13/month before storage, transfer, and tax). Render Free web services sleep after 15 minutes idle; Free Postgres is limited to 1 GB and expires after 30 days without backups. See [Render pricing](https://render.com/pricing) and [free service limits](https://render.com/docs/free).
- Netlify Free lists 300 monthly usage credits with a hard limit; production deploys use 15 credits, bandwidth 20 credits/GB, and web requests 2 credits/10,000. It has no Free auto-recharge. See [Netlify pricing](https://www.netlify.com/pricing/) and [credit plan details](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/).

The connected Netlify and Supabase accounts showed unrelated portfolio resources; they were not reused. There is no connected Render deployment capability/account available in this environment. Render's durable plan would incur recurring charges and has not been provisioned. The approximately $13/month hosting envelope is not a price approval. Production deployment also requires the API URL for Netlify's public `VITE_API_BASE_URL` and the exact Netlify origin in Render CORS.

## Verification gates still open

| Gate | State | Exact next action |
|---|---|---|
| GitHub publication | Repository created; final source publication and Actions result must be verified. | Confirm `main` contains the full tree and check the CI run on the pushed commit. |
| PostgreSQL integration | Unverified here. | Wait for GitHub CI to migrate its PostgreSQL 17 service, seed twice with matching output, and pass every test without skips. If the workflow is not enabled, run the commands in `backend-handoff.md` from a PostgreSQL-enabled runner. |
| Public Netlify/Render deployment | Not provisioned. | Provision project-specific resources after accepting the recurring Render plan charge; set CORS and public API URL, deploy the same tested Git SHA, then verify both health endpoints. |
| No-key real API/database journey | Not run. | From the deployed site, complete incident → telemetry → stored replay → all evidence citations → acknowledged approval; read back persisted `simulation_only=true` and `external_action_performed=false`. |
| Live AI | Not run; no server-side provider secret is available. | Configure `OPENAI_API_KEY` only in the API host, enable live analysis explicitly, then verify a valid structured report, snapshot citations, model/prompt/schema provenance, usage, and timeout/refusal/invalid-output states. Keep replay enabled if live AI remains off. |
| Desktop/mobile deployed browser walkthrough | Not run. No public API/web deployment exists yet. | Test deployed loading, unavailable API, replay, live-off/live-on, evidence navigation, and simulated approval on desktop and mobile. |
| Docker Compose runtime | Not run in this runner. | Execute `docker compose up --build` on a Docker-capable host and complete the local no-key flow. |

No public Incident Atlas website or API URL is claimed at this handoff. No live model request, hosted migration, persisted approval, or deployed browser walkthrough is claimed as successful.
