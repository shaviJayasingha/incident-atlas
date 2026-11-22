# Pre-deployment release report

**Reviewed:** 2026-11-22  
**Code-under-test commit:** [8ea94a4adb57ac3826df325240dee974260072ad](https://github.com/shaviJayasingha/incident-atlas/commit/8ea94a4adb57ac3826df325240dee974260072ad)  
**Hosted verification:** [GitHub Actions run #16 — all jobs passed](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45071401490)  
**Repository:** [shaviJayasingha/incident-atlas](https://github.com/shaviJayasingha/incident-atlas)  
**Change review:** [Pull request #1](https://github.com/shaviJayasingha/incident-atlas/pull/1)

## Release status

The code and CI checks are ready for deployment configuration. No Incident Atlas website, API service, or production database has been deployed. There is no public demo URL. No hosting resources were created because no recurring spending cap was approved. The Netlify site origin and Render API origin therefore do not exist yet and cannot be set as production variables.

Live AI is disabled in render.yaml. No server-side OPENAI_API_KEY was present in the workspace, so no genuine provider request, live usage record, or provider-backed result was verified.

## Defects fixed

- Normalized Render postgresql:// and postgres:// DSNs to SQLAlchemy's explicit postgresql+psycopg:// driver in the shared settings path used by FastAPI and Alembic. A settings test checks the Render-shaped application and migration URLs; CI runs PostgreSQL migrations with that URL shape.
- Made production browser builds fail closed unless VITE_API_BASE_URL is an absolute HTTPS /api/v1 endpoint. CI verifies an unset value fails. Netlify's real build value remains deployment configuration because there is no Render API URL yet.
- Require the exact production PUBLIC_SITE_ORIGIN to match the sole HTTPS CORS_ALLOWED_ORIGINS entry. Production configuration rejects mismatches and missing origins.
- Trust X-Forwarded-For only when the direct peer address is inside configured trusted proxy CIDRs. Tests cover spoofed headers from untrusted peers, trusted proxy chains, and malformed chains. The Render manifest leaves live AI disabled until actual proxy ranges and provider use are verified.
- Added an atomic PostgreSQL-backed global cap on model calls across visitors and application instances. A concurrency test rotates source addresses and confirms only one provider call is admitted at a one-call limit.
- Split the deployment migration credential from the incident_atlas_runtime role. The deployment bootstrap migrates and seeds before granting runtime table access; it revokes evaluation-schema access, public schema creation, and alembic_version access. A PostgreSQL test confirms runtime reads work while evaluation reads and migration privileges fail.
- Excluded data/evaluation, labels, and answer-key patterns from the API image. The container job confirms the answer-key path is absent inside the built image.
- Removed per-view audit writes from public replay GETs. A PostgreSQL test opens both replay routes 25 times and confirms the audit row count does not grow.
- Replaced the GitHub placeholder with the repository link, corrected current README status, added a portfolio case study, and committed real screenshots from a passing CI browser run.

## Verification performed

| Check | Observed result |
|---|---|
| PostgreSQL 17 migrations and repeat seed | Passed in run #16. Runtime seed output and fixture manifests matched across two seed runs. |
| Full backend suite | Passed: 55 tests (55 dots in the hosted pytest output), including PostgreSQL cases skipped in this workspace. |
| PostgreSQL role grants | Passed: runtime can read public incident data but cannot access evaluation tables, create in public, or update migration metadata. |
| API image build and runtime | Passed: image built; evaluation answer keys were absent; migration/bootstrap and seed ran with Render-shaped URLs; API became ready with runtime credentials; stored replay, citation resolution, persisted simulation approval, and duplicate approval conflict all passed. |
| Frontend tests and TypeScript | Passed: 10/10 frontend tests and npm run typecheck. |
| Production frontend build | Passed with an HTTPS .invalid API URL reserved for build verification. CI separately confirmed an unset URL fails closed. This is not a configured production API URL. |
| Dependency audits | Passed: npm audit --audit-level=moderate found 0 vulnerabilities; uv audit --locked found no known vulnerabilities or adverse statuses in 62 packages. |
| Ruff | Passed: uv run ruff check . |
| Browser walkthrough | Passed in CI against local Vite + FastAPI + PostgreSQL: desktop incident/replay/evidence/approval path, 390 px mobile overflow check, and keyboard-focus check. This is not a deployed-site walkthrough. |
| Local PostgreSQL | Not available in this sandbox: embedded PostgreSQL failed with PermissionError: Operation not permitted; 19 PostgreSQL-marked tests were skipped locally. Hosted PostgreSQL CI ran the full 55-test suite. |
| Local container runtime | Not installed in this sandbox. Docker build and runtime were exercised by the hosted container job. |
| Public deployment / deployed desktop and mobile | Not run; no public website or API exists yet. |
| Genuine live AI | Not run; server-side model key absent. Live AI remains disabled. |

Exact hosted check URLs:

- [Run #16 — commit 8ea94a4](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45071401490) passed backend-postgres, frontend, container, and browser-e2e.
- The browser job uploaded a [CI screenshots artifact](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45071401490). The five images in this repository are captured from that local CI stack and are labeled as such in the [portfolio case study](portfolio-case-study.md).

The container job initially found two test-only configuration defects: its production DSN used a loopback hostname rejected by the production guard, and the replay smoke request read the mitigation ID from the wrong response field. CI now uses the runner's non-loopback host address and follows the API's hypothesis.mitigation.id contract. Both were fixed before run #16.

These commands were run locally:

- api: uv run pytest -q -rs; uv run ruff check .; uv audit --locked; uv run python -m incident_atlas.cli evaluate-fixtures; uv run python -m incident_atlas.cli evaluate-expanded
- web: npm test; npm run typecheck; VITE_API_BASE_URL=https://incident-atlas-api.example.invalid/api/v1 npm run build; npm audit --audit-level=moderate

The local API suite reported 36 passed and 19 skipped for the unavailable embedded PostgreSQL server. Hosted PostgreSQL results, rather than those skips, are the evidence for the database acceptance gate. This frontend has no separate lint script; its checked source gates are Node tests, TypeScript, and the production build.

## Dataset and evaluation limits

Public incident records are deterministic, project-authored synthetic telemetry shaped like OpenTelemetry records. They were not imported from OpenTelemetry Demo or a real production environment. Answer labels remain separate from public API data and the production API image.

The rules baseline measured:

| Set | Cases | Top-1 | MRR | Expected-support recall | Abstention / decision |
|---|---:|---:|---:|---:|---:|
| labels-v1 | 3 base cases | 1.0000 | 1.0000 | 1.0000 | 0.0000 abstention rate |
| variants-v1 | 9 synthetic regression cases | 1.0000 labeled top-1 | 1.0000 | 1.0000 | 1.0000 abstention accuracy; 1.0000 overall decision accuracy |

Dataset hashes: labels-v1 = 8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca; variants-v1 = 2fe129b3cda3fdd34d8525c48da2770097f78a95a4b5555af7ffb21a22312392. These tiny, fixed synthetic sets are regression checks, not real-world incident accuracy. The historical 0.5222 mean support-recall result and missing evidence by case remain documented in the [Step 6 report](step6-report.md); the rules citation-selection fix now measures 1.0000 on the same three base labels. There are no genuine live-AI quality measurements.

## Remaining release gates

1. Approve a recurring hosting spending cap and confirm the billing/account setup before provisioning Render and Netlify resources.
2. Provision the project-specific Render PostgreSQL/API and Netlify site. Set Netlify VITE_API_BASE_URL to the real Render HTTPS origin plus /api/v1; set Render PUBLIC_SITE_ORIGIN and CORS_ALLOWED_ORIGINS to the exact Netlify HTTPS origin.
3. Configure only the trusted proxy CIDRs observed in the deployed request path. Complete desktop and mobile walkthroughs against the deployed site and API, including the persisted no-key replay approval.
4. Keep live AI disabled unless the global spend cap is retained, a server-side provider key is configured, current proxy trust is verified, and a genuine live request passes output/citation/provenance checks. No visitor key is required for the stored replay path.
