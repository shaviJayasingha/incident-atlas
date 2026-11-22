# Step 6 — Testing and Security

**Date:** 2026-11-22  
**Audited GitHub `main` before changes:** [`e1c1f64cfbc39de602d9d0ac9736a041ed899159`](https://github.com/shaviJayasingha/incident-atlas/commit/e1c1f64cfbc39de602d9d0ac9736a041ed899159)  
**Step 6 code-under-test commit:** [`d3cdc86cb7b86f5c190a25277e0886b044ceb73b`](https://github.com/shaviJayasingha/incident-atlas/commit/d3cdc86cb7b86f5c190a25277e0886b044ceb73b)

**Hosted CI:** [Run 10 — all jobs passed](https://github.com/shaviJayasingha/incident-atlas/actions/runs/45063045683)

## Findings and fixes

| Severity | Finding | Result |
|---|---|---|
| Medium, release hardening | The API, runtime fixture seeder, and offline evaluation commands use the same PostgreSQL credential. Runtime code does not query the `evaluation` schema and tests verify labels stay out of public responses and model packets, but the database role does not enforce that boundary. | Open. Production needs a least-privilege runtime role without `evaluation` schema access and a separate migration credential. No production database exists to verify this. |
| Medium | Approval uniqueness was global per report and mitigation, so one anonymous visitor could prevent a different visitor from recording the same simulation. | Fixed. Approval uniqueness and duplicate detection now include the HMAC-derived source hash. Approvals are protected by a database trigger against update/delete. |
| Medium | The investigation deadline was checked after the provider returned; HTTPX read timeouts alone allow a slow trickle response to outlive the intended wall-clock cap. | Fixed with an async request and enforced overall deadline. A slow mocked provider test covers cancellation and timeout mapping. |
| Medium | A completed live request reused through its idempotency key could still return HTTP 201 because request IDs are per request. | Fixed. The service returns an explicit reuse flag; a stored completion returns 200 and does not call the provider again. Concurrent requests test the in-progress 409 and completed 200 paths. |
| Low | Guest rate-event rows had no expiry and could accumulate indefinitely. | Fixed. Old HMAC-only rows are pruned before rate checks using the longest configured rate window; an index supports cleanup. |
| Low | Production configuration accepted an HTTP model endpoint or wildcard/non-origin CORS values. | Fixed. Production settings require HTTPS for the model endpoint and exact HTTPS site origins. Tests cover wildcard, HTTP, path, and embedded-credential rejection. |
| Low, intentional public boundary | Live report IDs can be opened from another visitor context. | The public demo has no accounts and accepts only fixed synthetic evidence, so report deep links are intentionally shareable. A PostgreSQL-backed integration test confirms this behavior and verifies that answer-key fields are absent. Do not use this design for private or customer telemetry. |

The API has no public telemetry-upload or user-prompt endpoint. Telemetry strings are treated as untrusted text in the live system prompt; provider tests put prompt-like text in log messages and nested hostile evidence fields, then verify they remain JSON data, the system instruction is unchanged, the request has no tools, and `store=false`. Evidence IDs must be non-empty and resolve inside the recorded snapshot. Empty-support hypotheses, malformed output, refusals, timeouts, and unknown evidence IDs are rejected. Schema validation and citation membership checks do not prove that a model's wording is semantically supported by a real cited record; that remains a human-review and evaluation limitation.

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

Local checks run against the Step 6 working tree. The local sandbox still cannot start PostgreSQL, so PostgreSQL coverage below comes from hosted CI rather than the local run:

- `cd api && uv run ruff check .` — passed.
- `cd api && uv run pytest -q -rs` — **29 passed, 16 PostgreSQL cases skipped** because this sandbox denies the local PostgreSQL process/socket needed by `embedded-postgres`. They are counted as passed only in the PostgreSQL CI run below.
- `cd api && uv audit --locked` — passed after upgrading the vulnerable development dependency `pytest 8.4.2` to `pytest 9.2.0`; no known vulnerabilities in 62 audited packages.
- `cd web && npm test` — 7 passed; `npm run typecheck` and `npm run build` — passed; `npm audit --audit-level=moderate` — 0 vulnerabilities.
- Browser bundle scan for `OPENAI_API_KEY` and key-like markers — passed. `node --check web/tests/browser-smoke.mjs` and CI workflow YAML parsing — passed. The web project has no separate lint script; frontend tests, TypeScript checks, and production build are the available source checks.

Hosted GitHub Actions run 10 passed on code-under-test commit `d3cdc86cb7b86f5c190a25277e0886b044ceb73b`:

- PostgreSQL 17: `uv run alembic upgrade head` passed; runtime seeding and fixture-manifest generation ran twice, with both output pairs identical; `uv run pytest -q -rs` passed **45/45 tests**; Ruff passed; `uv audit --locked` reported no known vulnerabilities or adverse project statuses across 62 packages.
- Evaluation commands `uv run python -m incident_atlas.cli evaluate-fixtures` and `evaluate-expanded` passed in CI with the metrics and dataset hashes recorded above.
- Frontend: `npm ci`, 7 `npm test` cases, typecheck, production build, `npm audit --audit-level=moderate`, and the server-key bundle scan all passed.
- API container image build passed.
- Playwright started PostgreSQL, applied migrations, seeded fixtures, started the real local FastAPI API and Vite site, and passed the desktop replay → evidence link → persisted simulated approval journey. It also passed a 390 px mobile layout overflow check and keyboard-focus check. This is a CI-hosted local-app walkthrough, not a deployed-site walkthrough.

The first hosted CI attempts exposed test assertions that did not match the documented flat error envelope and duplicated approval UI text. Both assertions were corrected; the final run above is green. The implementation was verified on the code-under-test SHA; the report-only commit follows that run.

## Remaining release gates

- Create no paid hosting resource until the user gives a spending cap. No Incident Atlas site, API, or production database is deployed.
- No genuine provider request was made because no server-side model key is available. Mocked tests do not verify provider account access, current model availability, live structured output, or billed usage.
- The public deployed desktop/mobile browser walkthrough remains open because there is no deployed URL.
- Separate the runtime database role from migration/evaluation access and verify grants on a production-like PostgreSQL instance.
- Semantic grounding of validly cited live claims remains a human-review/evaluation concern; the test set is nine small synthetic cases.
- Production proxy/IP handling, hosted CORS origins, public rate limits, and secret configuration remain deployment-dependent and were not exercised against a deployed service. No frontend lint target is configured; `npm run lint` is not an available command.
