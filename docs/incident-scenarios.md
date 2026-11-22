# Reproducible incident scenarios

**Status:** Approved deterministic synthetic public dataset (Steps 1–5)  
**Fixture version:** `1.0.0`  
**Reviewed:** 2026-11-22

These are deterministic synthetic incidents shaped like OpenTelemetry metrics, logs, and spans. They are authored in `data/incidents/scenarios.json` and `data/incidents/replays.json`; they were not imported from the OpenTelemetry Demo repository or captured from a running service. The generation path is the checked-in JSON plus `incident_atlas.fixtures.build_evidence_items` and the idempotent `seed-runtime` command. It does not access external telemetry or a service stack. The same scenario seed, event ordering, values, and evidence IDs produce identical fixture rows and replay output. A scenario's `T0` is its displayed incident start; fixture timestamps are fixed UTC instants and the UI shows **simulated fixture time**.

This is the approved ADR-002 synthetic path. Dataset provenance is synthetic authoring by the Incident Atlas project, fixture version `1.0.0`, with per-file SHA-256 values recorded in `docs/backend-handoff.md`. Evaluation truth is sourced separately from `data/evaluation/labels.json`; runtime seeding never loads it and the API/model packet do not expose it. These examples illustrate OTel-like semantics but are not OpenTelemetry Demo scenarios, production customer telemetry, or a live telemetry import.

Each fixture has a 15-minute investigation window: `T-5m` baseline and `T0` through `T+10m` incident behavior. Metrics are one-minute samples. Trace and log IDs below are part of the expected stable evidence set. `expected_primary_label` is ground truth for evaluation only and must never be returned by a runtime API or included in the model packet.

## Scenario A — Cache key version mismatch

| Field | Definition |
|---|---|
| Fixture ID / seed | `inc-cache-collapse-001` / `atlas-cache-v1-seed-241` |
| Primary affected service | `catalog`; dependency path `checkout → catalog → redis` and `catalog → catalog-db` |
| Symptoms | Catalog p95 rises from 85 ms baseline to 1.4 s within two minutes of T0; checkout timeout rate rises from 0.2% to 8%; catalog DB read rate increases while Redis remains reachable. |
| Synthetic trigger / known cause | At T0, deployment marker `deploy-catalog-042` changes the cache key prefix from `catalog:v3:` to `catalog:v4:` while prewarmed keys remain under v3. Requests miss the cache and fall through to the database. |
| Telemetry | `catalog.cache.hit_ratio`: 0.97 baseline, 0.21 by T+2m; `catalog.http.server.duration.p95`: 85→1400 ms; `catalog-db.query.duration.p95`: 18→310 ms; Redis spans remain `OK` but record `cache.result=miss`; catalog `SELECT product_by_id` spans lengthen. |
| Expected evidence IDs | `ev-deploy-catalog-042`, `ev-cache-hit-ratio-drop`, `ev-catalog-p95-rise`, `ev-catalog-db-read-rise`, `ev-trace-cache-miss-17`, `ev-trace-db-query-17`, `ev-log-cache-prefix-v4`. |
| Decoys / counterevidence | Redis availability and error rate remain normal; DB CPU is elevated but follows miss-rate change. A standalone DB-capacity claim does not explain the cache evidence. |
| Evaluation label | `cache_key_version_mismatch`; acceptable secondary `cache_warmup_mismatch`. Expected ranking: cache/key explanation first; no claim that the deployment alone proves causality. |
| Rules baseline | Rank the cache label when hit ratio drops by at least 50 percentage points after a deploy marker and DB p95 rises at least 3×. |

## Scenario B — Inventory connection pool exhaustion

| Field | Definition |
|---|---|
| Fixture ID / seed | `inc-inventory-pool-002` / `atlas-pool-v1-seed-582` |
| Primary affected service | `inventory`; dependency path `checkout → inventory → inventory-db` |
| Symptoms | Inventory request p95 rises from 90 ms to 2.2 s; checkout receives inventory timeouts and order failures rise from 0.3% to 11%; database CPU and query p95 remain near baseline. |
| Synthetic trigger / known cause | A worker release at T0 leaves acquired database connections checked out on an error path. New requests queue waiting for a connection until the pool is exhausted. |
| Telemetry | `inventory.db.pool.in_use`: 12/40 to 40/40; `inventory.db.pool.wait_ms.p95`: 4→1800 ms; `inventory.http.server.duration.p95`: 90→2200 ms; `inventory-db.query.duration.p95`: 22→25 ms; logs show `PoolTimeout` and `connection_returned=false`; traces show long `db.acquire` wait spans before fast SQL execution. |
| Expected evidence IDs | `ev-worker-release-118`, `ev-pool-in-use-full`, `ev-pool-wait-rise`, `ev-log-pool-timeout-9`, `ev-trace-db-acquire-31`, `ev-inventory-p95-rise`, `ev-db-query-stable`. |
| Decoys / counterevidence | SQL duration and DB CPU remain stable; this weakens the hypothesis of a slow database query. The deploy marker is temporally associated, but the pool evidence is the stronger mechanism. |
| Evaluation label | `inventory_connection_leak`; acceptable secondary `connection_pool_exhaustion`. Explanation must mention pool wait/utilization rather than blame the database's query engine. |
| Rules baseline | Rank pool exhaustion when pool use is ≥95%, acquisition wait exceeds 500 ms, and the DB query p95 is less than 2× baseline. |

## Scenario C — Slow payment gateway and retry amplification

| Field | Definition |
|---|---|
| Fixture ID / seed | `inc-payment-gateway-003` / `atlas-gateway-v1-seed-936` |
| Primary affected service | `payment`; dependency path `checkout → payment → card-gateway-sim` |
| Symptoms | Payment authorization p95 rises from 180 ms to 3.4 s; checkout latency and payment failures increase; catalog, inventory, and internal database latency remain stable. |
| Synthetic trigger / known cause | At T0 the synthetic card-gateway dependency begins responding after 3.2 seconds, beyond the 2-second payment deadline. The client retries once, amplifying load and duplicate timeout records. |
| Telemetry | `card_gateway.authorize.duration.p95`: 160→3200 ms; `payment.authorization.timeout_rate`: 0.1%→18%; payment retry count per request: 0.02→0.94; trace trees show a slow downstream `card-gateway-sim.authorize` span followed by one retry; `payment-db.query.duration.p95` remains stable. |
| Expected evidence IDs | `ev-gateway-latency-start`, `ev-payment-timeout-rate`, `ev-payment-retry-rise`, `ev-trace-gateway-slow-44`, `ev-trace-retry-44`, `ev-payment-db-stable`, `ev-checkout-payment-tail`. |
| Decoys / counterevidence | No payment deploy occurs; internal DB health remains stable. A local database regression is inconsistent with the slow gateway child span. |
| Evaluation label | `upstream_payment_gateway_latency`; acceptable secondary `retry_amplification`. The report must distinguish the gateway fault signal from retries that amplify symptoms. |
| Rules baseline | Rank upstream dependency latency when a downstream span exceeds its deadline, parent timeouts rise, retries increase, and the service's own database remains stable. |

## Reproducibility contract

- Store source fixture definitions under a future `data/incidents/` path and evaluation labels in a separate `data/evaluation/` path.
- Seeded data has fixed `fixture_version`, `scenario_seed`, UTC timestamps, sample values, ordered events, trace IDs, and evidence IDs. Re-running the seed is an upsert that produces the same logical rows and snapshot hash.
- Baseline windows and incident windows use the same durations and metric sampling interval for all scenarios.
- Every evidence item must link to a scenario row and be selectable from its timeline/telemetry display.
- A stable stored replay is generated against one named model/prompt/schema version, or authored as a canonical response fixture. Its UI label always identifies it as a replay; the model used to create it does not imply a current model call.
- Evaluation variants may hide one expected key item or add one unrelated decoy. The original full case remains unchanged and is the reproducibility source of truth.
