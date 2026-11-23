# Incident Atlas release report

**Reviewed:** 2026-11-23  
**Release-candidate source revision:** [`b5eceed9c087b19dafcf377cded164dbaffe18cc`](https://github.com/shaviJayasingha/incident-atlas/commit/b5eceed9c087b19dafcf377cded164dbaffe18cc), proposed by [PR #5](https://github.com/shaviJayasingha/incident-atlas/pull/5).  
**Full CI run for this source revision:** [Run #28 — passed](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45147520680); all five jobs succeeded.  
**Repository:** [shaviJayasingha/incident-atlas](https://github.com/shaviJayasingha/incident-atlas)  
**Hosting status:** pre-deployment; no public URL exists.  
**Release ZIP:** CI generates a tracked-source archive and SHA-256 sidecar for the tested commit and uploads both as a 14-day workflow artifact. The final-tree artifact is available from the latest successful PR validation run; it is checked against the Git tree as part of that job.

This report distinguishes the release-candidate source revision from the still-unmerged `main` branch. The linked run verifies the current source and archive. The application changes were first checked in run #27; run #28 reran the gates after refreshing report references and the tracked approval screenshot. Earlier reports and measurements remain historical; they do not replace these results.

## Release status

The repository and CI are public. The Netlify site, Render API, and managed PostgreSQL database have **not** been provisioned. There is no public demo URL. Hosting is blocked on an approved monthly spending cap and access to the intended Render and Netlify accounts. No billable resources were created.

The replay journey is designed to work without a visitor account or model key. `LIVE_ANALYSIS_ENABLED=false`; no genuine model request or provider-backed quality result has been verified. No OpenTelemetry Demo capture has been imported or evaluated. The repository has no license because the owner has not selected one; see [licensing-decision.md](licensing-decision.md).

## Verification of the release candidate

GitHub Actions run #28 completed successfully for the source tree in PR #5. All five jobs passed. The workflow artifact was built from GitHub's PR merge commit; its Git tree is identical to the PR head tree.

| Gate | Observed result |
|---|---|
| PostgreSQL 17 migrations and repeat seeding | Passed. CI ran Alembic migrations and ran runtime seeding and fixture-manifest generation twice; both output pairs matched. |
| Backend suite | **65 passed** against PostgreSQL 17; no PostgreSQL skips in CI. Includes runtime grant allow/deny checks, bounded seven-day rate cleanup, migration/bootstrap preflight, persisted approvals, and replay/evidence behavior. |
| Python lint and dependency audit | `uv run ruff check .` passed. `uv audit --locked` found no known vulnerabilities or adverse statuses in 62 packages. |
| Frontend tests and types | **13/13 tests passed**; `npm run typecheck` passed. Tests cover approval read-back and stable anonymous browser identity across reload. |
| Production frontend build and dependency audit | Build passed with the explicit CI-only reserved `.invalid` API URL. Missing and reserved production URLs were rejected in dedicated checks. `npm audit --audit-level=moderate` found 0 vulnerabilities; the built bundle credential-marker scan passed. |
| API image and runtime | Docker build passed; evaluation answer-key files were absent. With production-shaped PostgreSQL URLs, migration/bootstrap, runtime-role startup, readiness, stored replay, evidence resolution, and persisted simulated approval passed. Approval response had `simulation_only=true` and `external_action_performed=false`. |
| Browser walkthrough | Playwright passed against local CI Vite, FastAPI, and PostgreSQL services: desktop and mobile replay, every citation, persisted approval after reload, a second browser sharing the same IP, no horizontal overflow, and keyboard focus. This is not a public-site walkthrough. [Run #27 screenshot artifact](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45145232854/artifacts/14804016664). |
| Release archive | CI inspected a **106-file** tracked-source ZIP, checked ZIP integrity/exclusions and uploaded the ZIP plus SHA-256 sidecar as a commit-scoped artifact. The release job compares every archived path and blob to the tested Git tree. The final report/screenshot refresh triggers the same check again. |

### Commands represented by CI

The backend job installed locked dependencies, applied migrations, ran seed and manifest commands twice and diffed their output, then ran:

```bash
uv run pytest -q -rs
uv run ruff check .
uv audit --locked
uv run python -m incident_atlas.cli evaluate-fixtures
uv run python -m incident_atlas.cli evaluate-expanded
```

The frontend job ran `npm ci`, `npm test` (13 tests), `npm run typecheck`, the production API configuration failure checks, `npm run build`, `npm audit --audit-level=moderate`, and the browser-bundle secret-marker scan. The container job built and ran the API image with PostgreSQL. The browser job ran the local Playwright visitor journey. The archive job ran:

```bash
python scripts/build_release_zip.py --output "$RUNNER_TEMP/incident-atlas-release.zip"
```

### Local checks in this workspace

The local backend suite passed **42 tests and skipped 23 PostgreSQL-marked tests** because this sandbox cannot start the embedded PostgreSQL server (`PermissionError: Operation not permitted`). The full PostgreSQL result above comes from CI, not those local skips. Local `ruff`, Python dependency audit, frontend 13/13 tests, typecheck, production build, npm audit, and evaluation commands passed. Local Playwright could not launch Chromium because sandbox socket/ptrace permissions blocked the browser; Docker/Podman are unavailable locally. GitHub-hosted CI supplies the PostgreSQL, container, and browser evidence. The public deployment smoke command was syntax-checked but not run against real origins because none exist.

## Evaluation evidence and limits

The current rules-regression dataset is **12 project-authored synthetic cases**: three base cases, six derived variants, and three independent authored cases. It has eight positive labels and four expected-abstention cases. Dataset SHA-256:

`65f6949e8c0c0d2f258fd65c2760591b2ff7b38fbb1edeb38cc3dc16cbac1527`

CI run #28 measured 1.0000 labeled top-1, 1.0000 mean reciprocal rank, 1.0000 expected-support evidence recall, 1.0000 abstention accuracy, and 1.0000 overall decision accuracy on this fixed dataset. These are **synthetic regression results**, not real-world incident accuracy. The earlier 0.5222 support-recall measurement belongs to the historical Step 5/6 evaluation; the present score is tied to the dataset hash above and should not be generalized beyond it.

The executable OTLP/JSON importer is covered by a synthetic parser fixture only. There is no verified OpenTelemetry Demo version, scenario capture, imported-data hash, label, or Demo evaluation result. Keep all public scenario provenance labeled authored synthetic.

## Deployment, database, and provider gates

- No Render or Netlify resource, production hostname, or managed database exists. The exact blocked action is provisioning those billable resources; required inputs are an approved monthly spending cap and authorized account access.
- CI proves the grants and pre-created-runtime-user fallback on PostgreSQL 17. The actual Render migration user's privileges and the managed PostgreSQL bootstrap remain unverified. The fallback is to create the restricted `incident_atlas_runtime` credential in Render, preserve the original migration URL, and let bootstrap apply and verify the exact grants. Never run the API as a database owner.
- The site origin must be reserved before configuring `PUBLIC_SITE_ORIGIN` and `CORS_ALLOWED_ORIGINS`; the API origin must exist before setting Netlify `VITE_API_BASE_URL`. Follow the staged [deployment runbook](deployment.md), then run `scripts/deployment_smoke.py` and complete public desktop/mobile replay approval checks.
- Live AI stays disabled until a server-side model key, verified deployed proxy trust, request and spend caps, and a genuine provider request are available. Timeout, refusal, invalid output, unknown-citation, provenance, and usage paths have automated/mocked coverage; they have not been exercised against a genuine provider.
- No public-site screenshots, public replay journey, managed-Render role check, OpenTelemetry Demo result, or genuine model result is claimed.

## Owner decision

No license has been selected. Before adding a license, choose **MIT**, **Apache-2.0**, or **no license**. This decision is separate from the technical deployment gate.
