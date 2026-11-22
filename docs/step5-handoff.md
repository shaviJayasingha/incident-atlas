# Step 5 handoff — completion and verification status

**Status:** Full source is public on GitHub. PostgreSQL-backed CI, repeatable seeding, all backend tests, frontend checks, and the API container build pass. Production deployment, provider-backed live AI, and deployed browser walkthrough remain blocked and unverified.
**Reviewed:** 2026-11-22

This report records the original Step 5 handoff. The container startup and database-role procedure have since changed; see the current [deployment plan](deployment.md) and [pre-deployment release report](predeployment-release-report.md).

## Preflight findings

Before Step 5 changes, the implementation had no Incident Atlas deployment, container, Compose configuration, or CI workflow. The workspace Git metadata directory was read-only. The nine PostgreSQL tests had not run because the runner blocks the embedded PostgreSQL socket. The UI client journey was mocked in tests but had never reached a real API/database from a browser. No server-side OpenAI key was configured. The synthetic fixtures were approved in ADR-002 but needed an explicit provenance statement for launch.

The full inventory is in [`step5-preflight.md`](step5-preflight.md).

## Changes delivered

- Added a non-root FastAPI container image at [`Dockerfile`](../Dockerfile). It runs the Alembic migration and idempotent runtime fixture seed before serving, reads Render's injected `PORT`, and probes database readiness at `/readyz`.
- Added [`compose.yaml`](../compose.yaml) for PostgreSQL 17, the API, and Vite. The API and web wait for dependency health. Live AI is off by default and credentials remain API-only.
- Added [`ci.yml`](../.github/workflows/ci.yml). Its PostgreSQL service job migrates, seeds twice, compares manifests, runs the full backend suite and Ruff; a dependent job builds the API container. Its frontend job runs tests, typecheck, and production build.
- Added [`netlify.toml`](../netlify.toml) for a static Vite build and client route fallback, plus [`render.yaml`](../render.yaml) for the API container and managed PostgreSQL.
- Made the Vite API proxy target configurable for Compose while retaining `127.0.0.1:8000` as the local default.
- Documented that the public dataset is authored deterministic synthetic OpenTelemetry-shaped data, not imported from OpenTelemetry Demo. The source JSON, loader, fixture version, seeds, and hashes define the reproducible generation path. Ground-truth labels remain separate.
- Created and verified the public GitHub repository [`shaviJayasingha/incident-atlas`](https://github.com/shaviJayasingha/incident-atlas); the full source tree is on `main`. The original checkout's `.git` directory remains read-only; local repository metadata now lives in the writable `.git-step5` directory and is used with `git --git-dir="$PWD/.git-step5" --work-tree="$PWD"`.
- Fixed two real contract/test failures found by the PostgreSQL CI runs: the API's rules response now includes each fired rule label, and invalid live output is checked against the seeded hypothesis count rather than assuming only one replay hypothesis exists.

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
| `uv run alembic upgrade head` in GitHub Actions, with PostgreSQL 17 | Passed on the hosted GitHub runner. |
| `uv run python -m incident_atlas.cli seed-runtime` twice, plus two `fixture-manifest` runs and `diff -u` for both outputs | Passed on the hosted PostgreSQL 17 runner; both seed outputs and both manifests matched byte-for-byte. |
| `uv run pytest -q -rs` on the hosted PostgreSQL 17 runner | Passed: all 27 tests reached 100%, including all nine PostgreSQL integration tests, with no skips. The test suite used the real FastAPI app and PostgreSQL service. |
| `uv run ruff check .` on the hosted PostgreSQL 17 runner | Passed: `All checks passed!` |
| `docker build -f Dockerfile -t incident-atlas-api:ci .` | Passed on the hosted GitHub runner. This verifies the API image build; it is not a production deployment. |

The PostgreSQL suite emitted a Starlette deprecation warning for using `httpx` with `TestClient`; it did not fail the suite.

### PostgreSQL run record

GitHub Actions run [#4](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45055077841) for commit `3a0fabacdc0247b53e6cf587cc93c7a428ca01e6` completed successfully. All three jobs passed: `backend-postgres`, `frontend`, and `container`. The database job ran migrations, seed-twice comparisons, fixture manifest comparisons, the complete 27-test suite, and Ruff against the PostgreSQL 17 service. The frontend job passed `npm test` (7/7), `npm run typecheck`, and `npm run build`.

The actual verified fixture manifest from that run had hash `918505f67592c5b482c1d008d51bc642aca0cdfaf79b74edf27975f11ef868c3` and recorded:

| Incident | Evidence rows | Scenario SHA-256 | Immutable snapshot SHA-256 |
|---|---:|---|---|
| `inc-cache-collapse-001` | 71 | `428325f2a1185cdec21e0b84a6fa4a96e3660b9f5f9f38ed831aeda48e6f6bc4` | `7d09c04c3856d9fcc5e1c9b1a07581bbe5447e162d85dca700c7aa139d55d15d` |
| `inc-inventory-pool-002` | 71 | `a49a23b5310ac87954df2fd43d97c7818c1d2f1c25d9445e46936252bc780252` | `7ee8b70c152ea0e654758c62c7146b7b0df646f6c9c8cd0a717b59e5bd13f75d` |
| `inc-payment-gateway-003` | 87 | `244cf1449c76dea0ba474ff635c6f5a8dbbe0cad9bdc7a9b854aab2740f6ffd2` | `a15f0a87598bd002d7123600578911f98e84087d3eca35e6be4cb0256ab92ed6` |

These are the runner's observed outputs, not values inferred from generated migration SQL.

## Dataset and evaluation provenance

The public fixture inputs are `data/incidents/scenarios.json` and `data/incidents/replays.json`, version `1.0.0`. They are project-authored synthetic records and are converted to runtime evidence by the deterministic fixture loader. They are not real production telemetry and were not fetched from an OpenTelemetry Demo deployment. The separate answer-key file is `data/evaluation/labels.json` (`labels-v1`) and is never loaded by public runtime seeding or included in live model input.

Observed raw file SHA-256 values:

| Source | SHA-256 |
|---|---|
| `data/incidents/scenarios.json` | `6a8eea31a04e09e59d0c3ade764995c13761638c1f9994316c1596cb2ad7c2cf` |
| `data/incidents/replays.json` (Step 5 contract-aligned source) | `438c73cd36dcbe214cc3669d19188c5e63a266822090f9da5b8c263af75a46b5` |
| `data/evaluation/labels.json` | `a50413a43dce171cf80d6a9a1c5e1845b0db078a2f22c19d718c2d8ef0164e63` |

The evaluator's canonical labels dataset hash is `8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca`. The hosted PostgreSQL seed run reproduced the fixture scenario and immutable snapshot hashes in the table above.

## Hosting limits checked before launch

The public hosting plan is still Netlify static + Render API/PostgreSQL. Official pricing and plan docs were checked on 2026-11-22:

- Render lists low-end always-on API compute at $7/month and the smallest paid PostgreSQL compute at $6/month (about $13/month before storage, transfer, and tax). Render Free web services sleep after 15 minutes idle; Free Postgres is limited to 1 GB and expires after 30 days without backups. See [Render pricing](https://render.com/pricing) and [free service limits](https://render.com/docs/free).
- Netlify Free lists 300 monthly usage credits with a hard limit; production deploys use 15 credits, bandwidth 20 credits/GB, and web requests 2 credits/10,000. It has no Free auto-recharge. See [Netlify pricing](https://www.netlify.com/pricing/) and [credit plan details](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/).

No Incident Atlas hosting resources have been provisioned. Creating the persistent API and PostgreSQL services in `render.yaml` incurs recurring charges; the approximately $13/month hosting envelope is an estimate, not a price authorization. Production deployment also requires the API URL for Netlify's public `VITE_API_BASE_URL` and the exact Netlify origin in Render CORS.

## Verification gates still open

| Gate | State | Exact next action |
|---|---|---|
| GitHub publication | **Passed.** Public repository contains the project source and CI configuration. The verified source commit is [3a0fabac](https://github.com/shaviJayasingha/incident-atlas/commit/3a0fabacdc0247b53e6cf587cc93c7a428ca01e6); the handoff update is published after this tested change. | No blocker for source access. |
| PostgreSQL integration | **Passed in GitHub Actions.** PostgreSQL 17 migration, repeat seed/hash checks, all 27 tests (including the nine formerly skipped tests), Ruff, and frontend checks passed. | The CI database is ephemeral; this does not verify a production database. |
| API container build | **Passed in GitHub Actions.** | Production image deployment and runtime health checks remain unverified. |
| Public Netlify/Render deployment | **Blocked before provisioning.** No Incident Atlas service or database has been created. The durable Render plan is approximately $13/month at the prices checked, before storage, transfer, and tax; no spending limit was provided. | Approve a recurring hosting budget and authorize project-specific resources on the hosting account. Then provision the services, configure exact CORS and frontend API origin, and deploy the tested source. |
| No-key API/database journey | **Backend integration path passed in CI** using the real API routes and PostgreSQL: catalogue/detail, telemetry, stored replay isolation, evidence resolution, and persisted simulation approvals are covered. The end-to-end browser journey on a public deployment is **not verified** because no services are deployed. | After deployment, complete the same journey in the browser and read back the persisted `simulation_only=true` and `external_action_performed=false` approval. |
| Live AI | **Unverified.** CI uses mocked provider outputs to cover structured validation, provenance, evidence references, timeout/refusal/invalid output. No genuine live model request was made because no server-side `OPENAI_API_KEY` is available. | Add the model secret only in the API host, enable live analysis explicitly, and run a real provider request. Keep the no-key stored replay path available. |
| Desktop/mobile deployed browser walkthrough | **Unverified.** No deployed website or API URL exists. | After deployment, test loading, API unavailable, replay/live availability, evidence navigation, and simulated approval at desktop and mobile widths. |
| Docker Compose runtime | **Unverified.** Docker and Podman are unavailable in this runner; only the API Docker image build passed in CI. | Run `docker compose up --build` on a Docker-capable host and complete the local no-key flow. |

No public Incident Atlas website or API URL is claimed at this handoff. No genuine live model request, production-hosted migration, production approval, or deployed browser walkthrough is claimed as successful. The remaining external launch blockers are the approved recurring hosting spend/account and a server-side model key for live-AI verification.
