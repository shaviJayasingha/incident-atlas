import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from incident_atlas.models import (
    DependencyEdge,
    EvaluationLabel,
    EvidenceSnapshot,
    Hypothesis,
    Incident,
    IncidentService,
    LogEvent,
    MetricPoint,
    ReplayReport,
    Service,
    SnapshotEvidence,
    Span,
    TimelineEvent,
)

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = ROOT / "data" / "incidents" / "scenarios.json"
REPLAYS_PATH = ROOT / "data" / "incidents" / "replays.json"
LABELS_PATH = ROOT / "data" / "evaluation" / "labels.json"
FIXTURE_VERSION = "1.0.0"
SNAPSHOT_PAYLOAD_VERSION = "evidence-v1"


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"fixture timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenarios() -> list[dict[str, Any]]:
    payload = load_json(SCENARIOS_PATH)
    if payload.get("fixture_version") != FIXTURE_VERSION:
        raise ValueError("scenario fixture version does not match the loader")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        raise ValueError("expected exactly three deterministic incident scenarios")
    return scenarios


def load_replays() -> dict[str, dict[str, Any]]:
    payload = load_json(REPLAYS_PATH)
    return {item["incident_id"]: item for item in payload["reports"]}


def build_evidence_items(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    started_at = parse_dt(scenario["started_at"])
    fixture_version = FIXTURE_VERSION
    items: list[dict[str, Any]] = []

    for event in scenario["timeline"]:
        observed_at = started_at + timedelta(minutes=event["offset_minutes"])
        payload = {
            "title": event["title"],
            "summary": event["summary"],
            "kind": event["kind"],
            "attributes": event.get("attributes", {}),
        }
        items.append(
            {
                "evidence_id": event["id"],
                "kind": "timeline",
                "source_record_id": event["id"],
                "service_id": event.get("service_id"),
                "observed_at": observed_at,
                "fixture_version": fixture_version,
                "payload": payload,
            }
        )

    for series in scenario["metrics"]:
        anchors = {
            int(position): evidence_id
            for position, evidence_id in series.get("evidence_ids", {}).items()
        }
        for index, value in enumerate(series["values"]):
            evidence_id = anchors.get(index, f"ev-{series['series_id']}-{index:02d}")
            observed_at = started_at + timedelta(minutes=index - 5)
            items.append(
                {
                    "evidence_id": evidence_id,
                    "kind": "metric",
                    "source_record_id": evidence_id,
                    "service_id": series["service_id"],
                    "observed_at": observed_at,
                    "fixture_version": fixture_version,
                    "payload": {
                        "series_id": series["series_id"],
                        "metric_name": series["metric_name"],
                        "value": float(value),
                        "unit": series["unit"],
                        "statistic": series["statistic"],
                        "labels": series.get("labels", {}),
                    },
                }
            )

    for log in scenario["logs"]:
        observed_at = started_at + timedelta(minutes=log["offset_minutes"])
        items.append(
            {
                "evidence_id": log["id"],
                "kind": "log",
                "source_record_id": log["id"],
                "service_id": log["service_id"],
                "observed_at": observed_at,
                "fixture_version": fixture_version,
                "payload": {
                    "severity": log["severity"],
                    "message": log["body"],
                    "trace_id": log.get("trace_id"),
                    "span_id": log.get("span_id"),
                    "attributes": log.get("attributes", {}),
                },
            }
        )

    for span in scenario["spans"]:
        started = started_at + timedelta(minutes=span["offset_minutes"])
        items.append(
            {
                "evidence_id": span["id"],
                "kind": "span",
                "source_record_id": span["id"],
                "service_id": span["service_id"],
                "observed_at": started,
                "fixture_version": fixture_version,
                "payload": {
                    "trace_id": span["trace_id"],
                    "span_id": span["span_id"],
                    "parent_span_id": span.get("parent_span_id"),
                    "operation": span["operation"],
                    "duration_ms": float(span["duration_ms"]),
                    "status": span["status"],
                    "attributes": span.get("attributes", {}),
                },
            }
        )

    items.sort(key=lambda item: (item["observed_at"], item["evidence_id"]))
    if len({item["evidence_id"] for item in items}) != len(items):
        raise ValueError(f"duplicate evidence ID in fixture {scenario['id']}")
    return items


def seed_runtime(db: Session) -> dict[str, Any]:
    scenarios = load_scenarios()
    replays = load_replays()
    replay_source = load_json(REPLAYS_PATH)
    replay_version = replay_source["replay_version"]
    manifest: dict[str, Any] = {"fixture_version": FIXTURE_VERSION, "incidents": []}

    for scenario in scenarios:
        incident_id = scenario["id"]
        replay = replays.get(incident_id)
        if replay is None:
            raise ValueError(f"missing replay for fixture {incident_id}")
        snapshot_id = f"snap-{incident_id}-{FIXTURE_VERSION}"
        evidence_items = build_evidence_items(scenario)
        evidence_hash = sha256_json(evidence_items)
        scenario_hash = sha256_json(scenario)

        old_snapshot = db.get(EvidenceSnapshot, snapshot_id)
        if old_snapshot and old_snapshot.sha256 != evidence_hash:
            raise ValueError(
                f"fixture content changed without a fixture version bump: {incident_id}"
            )

        for service in scenario["services"]:
            db.merge(Service(**service))
        db.flush()

        db.merge(
            Incident(
                id=incident_id,
                slug=scenario["slug"],
                title=scenario["title"],
                severity=scenario["severity"],
                primary_service_id=scenario["primary_service_id"],
                summary=scenario["summary"],
                started_at=parse_dt(scenario["started_at"]),
                ended_at=parse_dt(scenario["ended_at"]),
                fixture_version=FIXTURE_VERSION,
                scenario_seed=scenario["scenario_seed"],
                display_timezone="UTC",
                created_at=parse_dt(scenario["started_at"]),
            )
        )
        db.flush()

        for membership in scenario["incident_services"]:
            db.merge(IncidentService(incident_id=incident_id, **membership))
        for edge in scenario["dependencies"]:
            db.merge(
                DependencyEdge(
                    id=edge["id"],
                    incident_id=incident_id,
                    from_service_id=edge["from_service_id"],
                    to_service_id=edge["to_service_id"],
                    relationship="calls",
                    observed=True,
                    attributes={},
                )
            )
        for event in scenario["timeline"]:
            db.merge(
                TimelineEvent(
                    id=event["id"],
                    incident_id=incident_id,
                    occurred_at=parse_dt(scenario["started_at"])
                    + timedelta(minutes=event["offset_minutes"]),
                    kind=event["kind"],
                    service_id=event.get("service_id"),
                    title=event["title"],
                    summary=event["summary"],
                    source_record_id=event.get("source_record_id"),
                    fixture_version=FIXTURE_VERSION,
                    attributes=event.get("attributes", {}),
                )
            )
        for series in scenario["metrics"]:
            anchors = {
                int(position): evidence_id
                for position, evidence_id in series.get("evidence_ids", {}).items()
            }
            for index, value in enumerate(series["values"]):
                evidence_id = anchors.get(index, f"ev-{series['series_id']}-{index:02d}")
                db.merge(
                    MetricPoint(
                        id=evidence_id,
                        incident_id=incident_id,
                        series_id=series["series_id"],
                        metric_name=series["metric_name"],
                        service_id=series["service_id"],
                        observed_at=parse_dt(scenario["started_at"]) + timedelta(minutes=index - 5),
                        value=value,
                        unit=series["unit"],
                        statistic=series["statistic"],
                        labels=series.get("labels", {}),
                        fixture_version=FIXTURE_VERSION,
                    )
                )
        for log in scenario["logs"]:
            db.merge(
                LogEvent(
                    id=log["id"],
                    incident_id=incident_id,
                    observed_at=parse_dt(scenario["started_at"])
                    + timedelta(minutes=log["offset_minutes"]),
                    severity=log["severity"],
                    service_id=log["service_id"],
                    body=log["body"],
                    trace_id=log.get("trace_id"),
                    span_id=log.get("span_id"),
                    attributes=log.get("attributes", {}),
                    fixture_version=FIXTURE_VERSION,
                )
            )
        for span in scenario["spans"]:
            db.merge(
                Span(
                    id=span["id"],
                    incident_id=incident_id,
                    trace_id=span["trace_id"],
                    span_id=span["span_id"],
                    parent_span_id=span.get("parent_span_id"),
                    service_id=span["service_id"],
                    operation=span["operation"],
                    started_at=parse_dt(scenario["started_at"])
                    + timedelta(minutes=span["offset_minutes"]),
                    duration_ms=span["duration_ms"],
                    status=span["status"],
                    attributes=span.get("attributes", {}),
                    fixture_version=FIXTURE_VERSION,
                )
            )

        db.merge(
            EvidenceSnapshot(
                id=snapshot_id,
                incident_id=incident_id,
                fixture_version=FIXTURE_VERSION,
                created_at=parse_dt(replay["created_at"]),
                window_start=parse_dt(scenario["started_at"]) - timedelta(minutes=5),
                window_end=parse_dt(scenario["started_at"]) + timedelta(minutes=10),
                sha256=evidence_hash,
                item_count=len(evidence_items),
                payload_version=SNAPSHOT_PAYLOAD_VERSION,
            )
        )
        db.flush()
        for item in evidence_items:
            db.merge(
                SnapshotEvidence(
                    snapshot_id=snapshot_id,
                    evidence_id=item["evidence_id"],
                    kind=item["kind"],
                    source_record_id=item["source_record_id"],
                    service_id=item["service_id"],
                    observed_at=item["observed_at"],
                    payload=item["payload"],
                )
            )

        report_payload = replay
        db.merge(
            ReplayReport(
                id=replay["id"],
                incident_id=incident_id,
                fixture_version=FIXTURE_VERSION,
                created_at=parse_dt(replay["created_at"]),
                snapshot_id=snapshot_id,
                report_payload=report_payload,
                rules_version="rules-v1",
            )
        )
        db.flush()
        for hypothesis in replay["hypotheses"]:
            db.merge(
                Hypothesis(
                    id=hypothesis["id"],
                    investigation_id=None,
                    replay_report_id=replay["id"],
                    rank=hypothesis["rank"],
                    statement=hypothesis["statement"],
                    confidence=hypothesis["confidence"],
                    confidence_note=hypothesis["confidence_note"],
                    supporting_evidence_ids=hypothesis["supporting_evidence_ids"],
                    contradicting_evidence_ids=hypothesis["contradicting_evidence_ids"],
                    next_read_only_check=hypothesis["next_read_only_check"],
                    mitigation_id=hypothesis["mitigation_id"],
                    mitigation_summary=hypothesis["mitigation_summary"],
                )
            )

        manifest["incidents"].append(
            {
                "incident_id": incident_id,
                "scenario_sha256": scenario_hash,
                "snapshot_id": snapshot_id,
                "snapshot_sha256": evidence_hash,
                "evidence_count": len(evidence_items),
                "replay_id": replay["id"],
                "replay_version": replay_version,
            }
        )

    db.commit()
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest


def seed_evaluation(db: Session) -> dict[str, Any]:
    payload = load_json(LABELS_PATH)
    labels = payload["cases"]
    for label in labels:
        db.merge(
            EvaluationLabel(
                case_id=label["case_id"],
                incident_id=label["incident_id"],
                fixture_version=label["fixture_version"],
                expected_primary_label=label["expected_primary_label"],
                acceptable_secondary_labels=label["acceptable_secondary_labels"],
                expected_supporting_evidence_ids=label["expected_supporting_evidence_ids"],
                expected_contradicting_evidence_ids=label["expected_contradicting_evidence_ids"],
                expected_abstention=label["expected_abstention"],
                label_version=payload["label_version"],
                notes=label["notes"],
            )
        )
    db.commit()
    return {
        "label_version": payload["label_version"],
        "case_count": len(labels),
        "labels_sha256": sha256_json(payload),
    }


def fixture_manifest(db: Session) -> dict[str, Any]:
    scenarios = load_scenarios()
    items = []
    for scenario in scenarios:
        snapshot_id = f"snap-{scenario['id']}-{FIXTURE_VERSION}"
        snapshot = db.get(EvidenceSnapshot, snapshot_id)
        if snapshot is None:
            raise ValueError(f"runtime fixture not seeded: {scenario['id']}")
        items.append(
            {
                "incident_id": scenario["id"],
                "scenario_sha256": sha256_json(scenario),
                "snapshot_id": snapshot_id,
                "snapshot_sha256": snapshot.sha256,
                "evidence_count": snapshot.item_count,
            }
        )
    result: dict[str, Any] = {"fixture_version": FIXTURE_VERSION, "incidents": items}
    result["manifest_sha256"] = sha256_json(result)
    return result
