# Step 5 preflight — open paths and acceptance gates

**Recorded before Step 5 implementation changes.**

This inventory is based on the Step 1–4 handoffs and a fresh workspace inspection on 2026-11-22. It distinguishes prior code checks from end-to-end checks that have not run.

## Incomplete visitor paths and gates

| Area | State before Step 5 | Evidence / required closure |
|---|---|---|
| PostgreSQL migrations and persistence | Unverified. Nine integration tests were skipped; this environment has no PostgreSQL binary or `TEST_DATABASE_URL`. | Execute migrations, seed twice, compare fixture manifests, and run all PostgreSQL-marked tests against a real PostgreSQL service. |
| Public GitHub source | No usable root Git repository or configured remote. The mounted `.git` metadata is unreadable/unwritable in this checkout. | Create or use an authorized writable repository/checkout; publish only after inspecting the staged source and excluding secrets/build artifacts. |
| Persisted replay journey | Frontend client flow is implemented and mock-tested; no real API/PostgreSQL walkthrough has run. | Open incident, inspect telemetry, view replay, follow all cited evidence, approve with acknowledgment, and read back persisted simulation flags. |
| Live AI | Optional server path and failure handling exist, but there is no server credential or completed provider request. | Securely configure a server-side key on an authorized host and verify one structured run, provenance, evidence IDs, token usage, timeout, and refusal/invalid-output handling. |
| Production hosting | No Incident Atlas Netlify site, API service, or database exists. Connected hosting accounts contain unrelated personal projects; those must not be repurposed. | Provision project-specific resources only after current plan limits and any spend are clear; deploy web/API/database and verify public URLs. |
| Desktop/mobile browser verification | Not completed. The Step 4 cloud browser could not reach the local development server. | Walk the deployed site in a browser at desktop and mobile sizes, including loading/error/replay/live/approval states. |
| Container, local orchestration, CI | Not present at preflight. | Add the API image, PostgreSQL Compose environment, health checks, safe migration/seed startup, and CI using a PostgreSQL service. |
| Dataset provenance | The blueprint selects deterministic synthetic OpenTelemetry-shaped fixtures rather than an imported OpenTelemetry Demo dataset. | Preserve that approved path; document the generating source, fixture version, stable hashes, and the separation of evaluation labels from public/live inputs. |

## Known code-level defects or risks to verify

- PostgreSQL-only behavior has not been executed; generated migration SQL is not evidence of working migrations.
- The public deployment must never fall back from a failed API call to fixture content.
- Live analysis requires a server secret; the public replay must continue to work when that secret or provider is unavailable.
- Browser and backend persistence behavior have only been tested separately, so request wiring and CORS need a deployed smoke check.
- Static hosting, API hosting, and database configuration must use project-specific resources; existing unrelated portfolio projects are out of scope.

## Step 5 success record

This inventory is not a completion claim. Final verification outcomes, exact commands, resource URLs, and remaining blockers belong in `step5-handoff.md`.
