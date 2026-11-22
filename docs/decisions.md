# Architecture decisions

**Status:** Accepted for blueprint and Step 2 implementation  
**Reviewed:** 2026-11-22

## ADR-001 — Keep the visitor application static

**Decision:** React + TypeScript + Vite builds static files for CDN hosting; a separate FastAPI service owns dynamic API and secrets.

**Context:** The visitor experience is a public demo with a small fixed set of routes and data. It needs no account state or server-rendered personalization. Live model credentials must remain off the browser.

**Consequences:** The UI can be served cheaply and independently; API origin/CORS are explicit. The UI must handle API loading/failure states and client-side deep-link fallback. There is no server-side UI session.

## ADR-002 — Use deterministic synthetic incident telemetry

**Decision:** Start with versioned synthetic OpenTelemetry-shaped data instead of requiring an OpenTelemetry Demo deployment or connection to a running service.

**Context:** A public recruiter demo needs repeatable, safe, low-cost scenarios and stable evaluation labels.

**Consequences:** It is not a live observability product or representative of every production failure. Scenarios must be transparent and deterministic. OpenTelemetry is used for signal semantics and for monitoring the Incident Atlas API itself.

## ADR-003 — Use a relational database for fixtures and reports

**Decision:** PostgreSQL stores incident, service, telemetry, replay, snapshot, investigation, and simulation audit records; JSONB is limited to extensible attributes and validated reports.

**Context:** Evidence references must resolve to known records and stable snapshots, while scenario metadata can evolve.

**Consequences:** Schema migrations and seed idempotency are required. Relational constraints can prevent invalid links. Ground-truth evaluation labels remain isolated from runtime evidence queries.

## ADR-004 — Use one explicit model inference with no autonomous tools

**Decision:** FastAPI performs the fixed reads, prepares a bounded evidence packet, makes one structured Responses API call, validates the returned report, and persists it. The model does not execute queries or tools.

**Context:** The only task is evidence-ranked explanation for fixed cases; autonomous access would add risk, cost, and irreproducibility.

**Consequences:** Each live run has bounded latency and one model cost. The product gives up open-ended exploration. The backend must show when evidence is insufficient and reject unlinked citations.

## ADR-005 — Make replay first-class and visibly separate

**Decision:** Every incident has an immutable stored replay independent of the AI provider; live and replay responses carry distinct source markers and persistent UI labels.

**Context:** Recruiters need a dependable no-key journey, and visitors must not confuse a saved response with a current model inference or current telemetry.

**Consequences:** Replays need fixture/model/schema provenance. Live inference must never fall back to replay without an explicit user choice.

## ADR-006 — Treat mitigation approval as a simulation only

**Decision:** A separate endpoint records an append-only simulation approval with fixed `simulation_only=true` and `external_action_performed=false`; no executor or production credential is included.

**Context:** The product requirement includes a human approval boundary but the demo must not change a system.

**Consequences:** UI language must be unmistakable, the endpoint cannot accept arbitrary action parameters, and no future integration should reuse this route as a real change API.

## ADR-007 — Host static frontend separately from API and database

**Decision:** Use Netlify for the static frontend and Render for the FastAPI container and managed PostgreSQL for the initial public plan.

**Context:** This keeps the frontend static and the API/database on a managed container platform with a simple cost envelope. Local Docker Compose remains the portable developer path.

**Consequences:** Two hosting vendors, CORS and deployment coordination are required. Hosting plan details may change; verify live pricing and quotas before provisioning. The plan is a practical default, not a lock-in requirement.

## ADR-008 — Keep public rule signals separate from evaluation labels

**Decision:** The public rules baseline returns operational signal names such as `cache_miss_after_release_signal`. The offline evaluator maps fired rule IDs to expected evaluation classes; exact answer-key labels remain in the separate `evaluation` schema and source dataset.

**Context:** Returning a rules class with the same value as `expected_primary_label` would expose the evaluation answer key in public responses even if no labels table were serialized.

**Consequences:** Baseline scoring is performed by the offline evaluator. Step 2 keeps evaluation and runtime tables in distinct schemas and the live packet builder does not query labels. The current configured database credential is shared, so production should use a least-privilege runtime role without access to `evaluation`.
