# Step 6 — Testing and Security

**Date:** 2026-11-22  
**Audited GitHub `main` before changes:** [`e1c1f64cfbc39de602d9d0ac9736a041ed899159`](https://github.com/shaviJayasingha/incident-atlas/commit/e1c1f64cfbc39de602d9d0ac9736a041ed899159)  
**Step 6 implementation commit:** Pending publication and CI verification.

## Findings and fixes

| Severity | Finding | Result |
|---|---|---|
| Medium, release hardening | The API, runtime fixture seeder, and offline evaluation commands use the same PostgreSQL credential. Runtime code does not query the `evaluation` schema and tests verify labels stay out of public responses and model packets, but the database role does not enforce that boundary. | Open. Production needs a least-privilege runtime role without `evaluation` schema access and a separate migration credential. No production database exists to verify this. |
| Medium | Approval uniqueness was global per report and mitigation, so one anonymous visitor could prevent a different visitor from recording the same simulation. | Fixed. Approval uniqueness and duplicate detection now include the HMAC-derived source hash. Approvals are protected by a database trigger against update/delete. |
| Medium | The investigation deadline was checked after the provider returned; HTTPX read timeouts alone allow a slow trickle response to outlive the intended wall-clock cap. | Fixed with an async request and enforced overall deadline. A slow mocked provider test covers cancellation and timeout mapping. |
| Medium | A completed live request reused through its idempotency key could still return HTTP 201 because request IDs are per request. | Fixed. The service returns an explicit reuse flag; a stored completion returns 200 and does not call the provider again. Concurrent requests test the in-progress 409 and completed 200 paths. |
| Low | Guest rate-event rows had no expiry and could accumulate indefinitely. | Fixed. Old HMAC-only rows are pruned before rate checks using the longest configured rate window; an index supports cleanup. |
| Low | Production configuration accepted an HTTP model endpoint or wildcard/non-origin CORS values. | Fixed. Production settings require HTTPS for the model endpoint and exact HTTPS site origins. Tests cover wildcard, HTTP, path, and embedded-credential rejection. |

The API has no public telemetry-upload or user-prompt endpoint. Telemetry strings are treated as untrusted text in the live system prompt; the provider test injects instruction-like log text and confirms the request has no tools and `store=false`. Evidence IDs must be non-empty and resolve inside the recorded snapshot. Schema validation and citation membership checks do not prove that a model's wording is semantically supported by its cited records; that remains a review and evaluation limitation.

Public replay and evidence records are intentionally readable without authentication: the product has no accounts, uses synthetic public fixtures, and supports deep links without session state. Anonymous rate/approval deduplication is scoped by an HMAC of the request source address, not a durable browser identity.

## Evidence-recall investigation and evaluation

The original `labels-v1` evaluation measurement was **0.5222 mean expected supporting-evidence recall** (3 cases; dataset SHA-256 `8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca`). The rules chose the correct top label in all three cases, but citation selection omitted corroborating records:

| Case | Original recall | Expected support IDs not cited |
|---|---:|---|
| `case-cache-v1` | 0.5000 (3/6) | `ev-catalog-p95-rise`, `ev-trace-cache-miss-17`, `ev-trace-db-query-17` |
| `case-pool-v1` | 0.4000 (2/5) | `ev-worker-release-118`, `ev-log-pool-timeout-9`, `ev-trace-db-acquire-31` |
| `case-gateway-v1` | 0.6667 (4/6) | `ev-trace-gateway-slow-44`, `ev-trace-retry-44` |

The rules cited threshold metrics but left out the first elevated service symptom, causal spans, release signal, and pool timeout evidence. Rules v2 now selects those records from the same evidence packet; every added citation still resolves against the stored snapshot. The old 0.5222 score and dataset hash remain unchanged in the original Step 5 artifacts; current evaluation does not overwrite that historical result.

Measured rules-only results from `uv run python -m incident_atlas.cli evaluate-fixtures`:

- `labels-v1`, 3 base cases, SHA-256 `8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca`: top-1 **1.0000**, MRR **1.0000**, expected-support recall **1.0000**, abstention rate **0.0000**.
- `variants-v1`, 9 cases (3 base, 3 severity-shifted positives, 3 ambiguous/expected-abstain), SHA-256 `2fe129b3cda3fdd34d8525c48da2770097f78a95a4b5555af7ffb21a22312392`: labeled top-1 **1.0000**, MRR **1.0000**, expected-support recall **1.0000**, abstention accuracy **1.0000**, overall decision accuracy **1.0000**.

These are deterministic, fixture-derived regression results, not a measure of real incident accuracy. No genuine live-model result exists, so no live-AI score is compared with the rules baseline. Provider coverage is mocked only.

## Verification status

Local checks run against the Step 6 working tree:

- `cd api && uv run ruff check .` — passed.
- `cd api && uv run pytest -q -rs` — **29 passed, 15 PostgreSQL cases skipped** because this sandbox denies the local PostgreSQL process/socket needed by `embedded-postgres`. Those skipped cases include migration/seed, evidence resolution, replay isolation, rate/CORS bounds, persisted approvals, timeout/refusal/invalid-output behavior, and idempotency concurrency. They are not counted as passed here.
- `cd api && uv audit --locked` — passed after upgrading the vulnerable development dependency `pytest 8.4.2` to `pytest 9.2.0`; no known vulnerabilities in 62 audited packages.
- `cd web && npm test` — 7 passed; `npm run typecheck` and `npm run build` — passed; `npm audit --audit-level=moderate` — 0 vulnerabilities.
- Browser bundle scan for `OPENAI_API_KEY` and key-like markers — passed. `node --check web/tests/browser-smoke.mjs` and CI workflow YAML parsing — passed.
- Local `docker build` could not run because Docker is not installed in this environment. The hosted container build is pending CI.
- A Playwright job now starts PostgreSQL, migrates/seeds, starts the real API and Vite, and walks the replay/evidence/approval flow at desktop width plus a mobile layout/focus check. CI result is pending; this is a local CI browser run, not a deployed-site walkthrough.

**Hosted PostgreSQL, repeat-seed, container, and Playwright results:** Pending publication of the implementation commit. They will be recorded here with the actual GitHub Actions run URL and commit SHA before this report is finalized.

## Remaining release gates

- Create no paid hosting resource until the user gives a spending cap. No Incident Atlas site, API, or production database is deployed.
- No genuine provider request was made because no server-side model key is available. Mocked tests do not verify provider account access, current model availability, live structured output, or billed usage.
- The public deployed desktop/mobile browser walkthrough remains open because there is no deployed URL.
- Separate the runtime database role from migration/evaluation access and verify grants on a production-like PostgreSQL instance.
- Semantic grounding of validly cited live claims remains a human-review/evaluation concern; the test set is nine small synthetic cases.
