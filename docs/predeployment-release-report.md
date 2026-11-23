# Incident Atlas release report

**Reviewed:** 2026-11-23  
**Application revision verified:** [`b8168985fe2bd7fec807d6691f98824b0f9b4f46`](https://github.com/shaviJayasingha/incident-atlas/commit/b8168985fe2bd7fec807d6691f98824b0f9b4f46)  
**Full CI run for this application revision:** [Run #24 — passed](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45122787848)  
**Repository:** [shaviJayasingha/incident-atlas](https://github.com/shaviJayasingha/incident-atlas)  
**Hosting status:** pre-deployment; no public URL exists.  
**Release ZIP:** generated from the tracked source tree after this report refresh; its application code matches the verified revision above. The ZIP and SHA-256 sidecar are distributed separately.

This is the current verification summary for the source revision above. Earlier reports and measurements remain historical; they do not replace these results.

## Release status

The repository and CI are public. The Netlify site, Render API, and managed PostgreSQL database have **not** been provisioned. There is no public demo URL. Hosting is blocked on an approved monthly spending cap and access to the intended Render and Netlify accounts. No billable resources were created.

The replay journey is designed to work without a visitor account or model key. `LIVE_ANALYSIS_ENABLED=false`; no genuine model request or provider-backed quality result has been verified. No OpenTelemetry Demo capture has been imported or evaluated. The repository has no license because the owner has not selected one; see [licensing-decision.md](licensing-decision.md).

## Verification on commit b816898

GitHub Actions run #24 completed successfully on the commit above. All five jobs passed.

| Gate | Observed result |
|---|---|
| PostgreSQL 17 migrations and repeat seeding | Passed. CI ran Alembic migrations and ran runtime seeding and fixture-manifest generation twice; both output pairs matched. |
| Backend suite | **65 passed** against PostgreSQL 17; no PostgreSQL skips in CI. Includes runtime grant allow/deny checks, bounded seven-day rate cleanup, migration/bootstrap preflight, persisted approvals, and replay/evidence behavior. |
| Python lint and dependency audit | `uv run ruff check .` passed. `uv audit --locked` found no known vulnerabilities or adverse statuses in 62 packages. |
| Frontend tests and types | **11/11 tests passed**; `npm run typecheck` passed. |
| Production frontend build and dependency audit | Build passed with the explicit CI-only reserved `.invalid` API URL. Missing and reserved production URLs were rejected in dedicated checks. `npm audit --audit-level=moderate` found 0 vulnerabilities; the built bundle credential-marker scan passed. |
| API image and runtime | Docker build passed; evaluation answer-key files were absent. With production-shaped PostgreSQL URLs, migration/bootstrap, runtime-role startup, readiness, stored replay, evidence resolution, and persisted simulated approval passed. Approval response had `simulation_only=true` and `external_action_performed=false`. |
| Browser walkthrough | Playwright passed against local CI Vite, FastAPI, and PostgreSQL services: desktop replay, evidence navigation, persisted approval, 390 px mobile layout, and keyboard focus. This is not a public-site walkthrough. [Run #24 screenshot artifact](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45122787848/artifacts/14793888268). |
| Release archive | CI inspected a 102-file tracked-source ZIP; ZIP integrity and exclusion checks passed. The fresh archive delivered with this report is checked against the remote tree for its documentation-refresh revision, with the same application code revision above. |

### Commands represented by CI

The backend job installed locked dependencies, applied migrations, ran seed and manifest commands twice and diffed their output, then ran:

```bash
uv run pytest -q -rs
uv run ruff check .
uv audit --locked
uv run python -m incident_atlas.cli evaluate-fixtures
uv run python -m incident_atlas.cli evaluate-expanded
```

The frontend job ran `npm ci`, `npm test`, `npm run typecheck`, the production API configuration failure checks, `npm run build`, `npm audit --audit-level=moderate`, and the browser-bundle secret-marker scan. The container job built and ran the API image with PostgreSQL. The browser job ran the local Playwright visitor journey. The archive job ran:

```bash
python scripts/build_release_zip.py --output "$RUNNER_TEMP/incident-atlas-release.zip"
```

### Local checks in this workspace

The local backend suite passed **42 tests and skipped 23 PostgreSQL-marked tests** because this sandbox cannot start the embedded PostgreSQL server (`PermissionError: Operation not permitted`). The full PostgreSQL result above comes from CI, not those local skips. Local `ruff`, Python dependency audit, frontend 11/11 tests, typecheck, production build, npm audit, and evaluation commands passed. Docker/Podman are unavailable locally; the CI container job supplies that evidence. The public deployment smoke command was syntax-checked but not run against real origins because none exist.

## Evaluation evidence and limits

The current rules-regression dataset is **12 project-authored synthetic cases**: three base cases, six derived variants, and three independent authored cases. It has eight positive labels and four expected-abstention cases. Dataset SHA-256:

`65f6949e8c0c0d2f258fd65c2760591b2ff7b38fbb1edeb38cc3dc16cbac1527`

CI run #24 measured 1.0000 labeled top-1, 1.0000 mean reciprocal rank, 1.0000 expected-support evidence recall, 1.0000 abstention accuracy, and 1.0000 overall decision accuracy on this fixed dataset. These are **synthetic regression results**, not real-world incident accuracy. The earlier 0.5222 support-recall measurement belongs to the historical Step 5/6 evaluation; the present score is tied to the dataset hash above and should not be generalized beyond it.

The executable OTLP/JSON importer is covered by a synthetic parser fixture only. There is no verified OpenTelemetry Demo version, scenario capture, imported-data hash, label, or Demo evaluation result. Keep all public scenario provenance labeled authored synthetic.

## Deployment, database, and provider gates

- No Render or Netlify resource, production hostname, or managed database exists. The exact blocked action is provisioning those billable resources; required inputs are an approved monthly spending cap and authorized account access.
- CI proves the grants and pre-created-runtime-user fallback on PostgreSQL 17. The actual Render migration user's privileges and the managed PostgreSQL bootstrap remain unverified. The fallback is to create the restricted `incident_atlas_runtime` credential in Render, preserve the original migration URL, and let bootstrap apply and verify the exact grants. Never run the API as a database owner.
- The site origin must be reserved before configuring `PUBLIC_SITE_ORIGIN` and `CORS_ALLOWED_ORIGINS`; the API origin must exist before setting Netlify `VITE_API_BASE_URL`. Follow the staged [deployment runbook](deployment.md), then run `scripts/deployment_smoke.py` and complete public desktop/mobile replay approval checks.
- Live AI stays disabled until a server-side model key, verified deployed proxy trust, request and spend caps, and a genuine provider request are available. Timeout, refusal, invalid output, unknown-citation, provenance, and usage paths have automated/mocked coverage; they have not been exercised against a genuine provider.
- No public-site screenshots, public replay journey, managed-Render role check, OpenTelemetry Demo result, or genuine model result is claimed.

## Owner decision

No license has been selected. Before adding a license, choose **MIT**, **Apache-2.0**, or **no license**. This decision is separate from the technical deployment gate.
