# API design

**Status:** Step 1 blueprint  
**Base path:** `/api/v1`  
**Format:** JSON over HTTPS; UTF-8  
**Reviewed:** 2026-11-22

## API conventions

- Public, read-only incident browsing requires no account. No caller-supplied model key or free-form incident prompt is accepted.
- IDs are opaque strings. Timestamps are ISO 8601 UTC. Durations use milliseconds. Metric units are explicit.
- Responses include `request_id`; live results include `source`, `evidence_snapshot_id`, `evidence_snapshot_sha256`, `model_id`, `prompt_version`, and `completed_at`.
- Error responses use `application/problem+json` with stable `code`, short `detail`, `request_id`, and `retryable`; rate limits also return `Retry-After`.
- Configure CORS for the exact public site origin and local development origin. Set maximum request body to 16 KiB. All response bodies are bounded by route limits.
- Live runs accept a client `Idempotency-Key` UUID. Repeating the same key and body returns the original result; using the same key with a different body returns `409`.

## Routes

| Method and path | Purpose | Success |
|---|---|---|
| `GET /healthz` | Liveness signal; no database dependency. | `200` with `status` and API version. |
| `GET /readyz` | Database readiness signal for host health checks. | `200` when PostgreSQL responds; stable `503` problem when unavailable. |
| `GET /api/v1/demo-capabilities` | Tell the UI which public paths are enabled. | `200` with `stored_replay_available`, `live_ai_enabled`, `live_label`, and rate-limit policy summary. |
| `GET /api/v1/incidents` | List fixture incidents, optionally filter by `severity` and `service`. | `200` with incident cards and `next_cursor`. Max 50 rows. |
| `GET /api/v1/incidents/{incident_id}` | Incident summary and display metadata. | `200` incident object. |
| `GET /api/v1/incidents/{incident_id}/timeline` | Chronological incident events. | `200`; optional `cursor`, `limit` (max 100), `from`, `to`; bounded to 15 minutes by default. |
| `GET /api/v1/incidents/{incident_id}/dependencies` | Directed service dependency edges and service summaries. | `200` bounded graph plus equivalent `nodes` and `edges` for a text fallback. |
| `GET /api/v1/incidents/{incident_id}/telemetry` | Query fixture telemetry. `kind` is `metrics`, `logs`, or `traces`; optional service and incident-relative time range. | `200`; cursor pagination, maximum 200 returned records per page and 15-minute range. |
| `GET /api/v1/incidents/{incident_id}/replay` | Return a stored report, with no provider call. | `200` report with `source: "stored_replay"`, `model_call_made: false`, `replay_id`, `fixture_version`, and original creation time. |
| `GET /api/v1/replays/{replay_id}` | Fetch a stored replay by stable ID. | `200` with the same replay provenance; no provider call. |
| `POST /api/v1/investigations` | Run fresh live analysis over fixed fixture data. Body only contains `incident_id` and optional `evidence_window_minutes` (default 15; allowed 5–15); requires an `Idempotency-Key` UUID header. No user prompt or query DSL. | `201` completed report. Synchronous request capped at 18 seconds. |
| `GET /api/v1/investigations/{investigation_id}` | Fetch a persisted live report. | `200` report with `source: "live_ai"` and trace metadata. |
| `POST /api/v1/investigations/{investigation_id}/mitigation-approvals` | Record a simulated approval for a proposal in a live report. | `201` simulation record; no external action. |
| `POST /api/v1/replays/{replay_id}/mitigation-approvals` | Record a simulated approval for a proposal in a stored replay. | `201` simulation record; no external action. This lets a visitor complete the no-key journey. |
| `GET /api/v1/snapshots/{snapshot_id}` | Read immutable evidence snapshot metadata. | `200` with fixture version, window, SHA-256, and item count. |
| `GET /api/v1/snapshots/{snapshot_id}/evidence/{evidence_id}` | Resolve a report citation inside the recorded snapshot. | `200` only when that exact item is present in the snapshot. |

## Response shapes

### Incident card

```json
{
  "id": "inc-cache-collapse-001",
  "title": "Catalog latency after cache key change",
  "severity": "SEV-2",
  "primary_service": "catalog",
  "started_at": "2026-01-15T10:05:00Z",
  "ended_at": "2026-01-15T10:20:00Z",
  "fixture_version": "1.0.0",
  "replay_available": true,
  "symptom_summary": "Catalog p95 latency and checkout timeout rate rose together."
}
```

### Telemetry item

All telemetry responses include `evidence_id`, `kind`, `service_id`, `observed_at`, and `fixture_version`. Metric items additionally include `metric_name`, `value`, `unit`, `statistic`, `labels`, and `series_id`; log items include `severity`, `message`, `trace_id`, `span_id`, and bounded `attributes`; span items include `trace_id`, `span_id`, `parent_span_id`, `operation`, `duration_ms`, `status`, and bounded `attributes`. Timeline events separately expose `source_record_id` when present.

### Investigation report

```json
{
  "id": "inv_01J...",
  "incident_id": "inc-cache-collapse-001",
  "fixture_version": "1.0.0",
  "source": "live_ai",
  "model_call_made": true,
  "status": "completed",
  "started_at": "2026-11-22T14:00:00Z",
  "completed_at": "2026-11-22T14:00:04Z",
  "model_id": "configured-model-id",
  "prompt_version": "incident-atlas-investigator-v1",
  "schema_version": "investigation-report-v2",
  "evidence_snapshot_id": "evs_01J...",
  "evidence_snapshot_sha256": "f5c6...",
  "uncertainty": "The timing and service signals support this explanation, but the fixture does not show a direct configuration diff.",
  "hypotheses": [
    {
      "id": "hyp_01",
      "rank": 1,
      "statement": "The catalog cache key version changed and caused a sharp rise in misses.",
      "confidence": "high",
      "confidence_note": "Multiple independent signals changed immediately after the deployment marker.",
      "supporting_evidence_ids": ["ev-cache-hit-drop", "ev-catalog-p95", "ev-deploy-042"],
      "contradicting_evidence_ids": [],
      "next_read_only_check": "Compare the configured cache key prefix in the deploy manifest with the previous fixture version.",
      "mitigation": {
        "id": "mit_01",
        "summary": "Roll back the cache key prefix in a controlled change window.",
        "simulation_only": true
      }
    }
  ],
  "rules_baseline": {
    "version": "rules-v2",
    "ranked_labels": ["cache_miss_after_release_signal"],
    "fired_rules": [{
      "rule_id": "cache-miss-after-deploy",
      "label": "cache_miss_after_release_signal",
      "evidence_ids": ["ev-deploy-042", "ev-cache-hit-drop", "ev-catalog-db-read-rise"]
    }]
  },
  "trace_id": null,
  "replay_id": null,
  "usage": {"input_tokens": 0, "output_tokens": 0},
  "request_id": "req_01J..."
}
```

`confidence` is `low`, `medium`, or `high`. A model-provided numeric score is omitted from the public API unless evaluation validates its use; if retained internally, the API labels it `uncalibrated_score` and never calls it a probability. The application validates every evidence ID against the immutable snapshot before returning the report.

Public `ranked_labels` are transparent rule-signal names. The offline evaluator maps fired rule IDs to expected classes using the separate evaluation dataset; expected class labels are not returned by the API or included in the live evidence packet.

Stored replay responses use the same hypothesis shape but must set:

```json
{
  "source": "stored_replay",
  "model_call_made": false,
  "replay_id": "replay-cache-v1",
  "originally_generated_at": "2026-01-15T10:25:00Z"
}
```

The UI must show those values in a persistent, prominent label.

### Simulation approval

Request:

```json
{
  "hypothesis_id": "hyp_01",
  "mitigation_id": "mit_01",
  "simulation_acknowledged": true
}
```

Response:

```json
{
  "id": "sim_01J...",
  "investigation_id": "inv_01J...",
  "mitigation_id": "mit_01",
  "status": "simulated_approved",
  "simulation_only": true,
  "external_action_performed": false,
  "recorded_at": "2026-11-22T14:01:00Z",
  "message": "Simulation recorded; no system was changed."
}
```

Both approval routes accept the same request shape and behavior. They reject false/missing acknowledgment, unknown result/mitigation, or a duplicate approval with a conflicting body. A unique constraint prevents duplicate approval for the same result and mitigation. They never accept a shell command, URL, target account, production resource ID, or executable action.

## Errors

| HTTP | `code` | Meaning and UI response |
|---|---|---|
| `400` | `invalid_cursor`, `invalid_time_range`, `time_range_too_large`, `invalid_idempotency_key` | Malformed cursor/header or impossible range; show the field issue. |
| `404` | `not_found`, `evidence_not_found` | Unknown fixture, result, or snapshot evidence; link to the incident or report. |
| `409` | `idempotency_conflict`, `investigation_in_progress`, `approval_conflict` | Reused key with different request, duplicate in-flight run, or duplicate simulation; do not imply success. |
| `411` | `content_length_required` | Request is missing the bounded body length header. |
| `413` | `request_too_large` | Body exceeds the configured 16 KiB default cap. |
| `422` | `validation_error`, `invalid_approval`, `provider_refused`, `evidence_limit_exceeded` | Unsupported values, refusal, or a bounded packet that exceeds its cap. |
| `429` | `rate_limited`, `live_capacity_reached` | Public quota or in-flight capacity reached; honor `Retry-After`; replay remains available. |
| `502` | `invalid_model_output` | Live output failed schema or evidence validation; no diagnosis is returned. |
| `503` | `live_analysis_disabled`, `provider_unavailable`, `fixture_not_seeded`, `database_unavailable` | Live feature/configuration or a required service is unavailable; offer stored replay when appropriate. |
| `504` | `investigation_timeout` | The one model request exceeded its deadline; show retry/replay options. |
| `500` | `internal_error` | Generic safe message plus request ID; never expose stack, secret, or raw provider payload. |

## Public limits

Initial policy: max 5 live analyses per visitor-source hash per 15 minutes, max 3 in-flight live calls per API process, max 15-minute evidence window, one provider attempt, max 2,000 evidence items in a live packet, max 16 KiB request body, at most 200 telemetry rows per page, and max 10 approval writes per source hash per hour. The API HMACs the client source for rate accounting and does not persist raw IP addresses. Adjust only using measured traffic and provider budget.
