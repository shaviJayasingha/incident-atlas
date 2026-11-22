import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from incident_atlas.config import Settings
from incident_atlas.errors import (
    ApiError,
    ProviderInvalidOutput,
    ProviderRefusal,
    ProviderTimeout,
    ProviderUnavailable,
)
from incident_atlas.fixtures import (
    FIXTURE_VERSION,
    SNAPSHOT_PAYLOAD_VERSION,
    sha256_json,
)
from incident_atlas.models import (
    AuditEvent,
    EvidenceSnapshot,
    Hypothesis,
    Incident,
    Investigation,
    ReplayReport,
    SnapshotEvidence,
)
from incident_atlas.provider import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    run_responses_inference,
)
from incident_atlas.rules import evaluate_rules
from incident_atlas.schemas import (
    Confidence,
    HypothesisOut,
    InvestigationReport,
    MitigationProposal,
    RulesBaselineOut,
)
from incident_atlas.security import (
    acquire_live_slot,
    fingerprint,
    idempotency_hash,
    release_live_slot,
)


def current_trace_id() -> str | None:
    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        return f"{span_context.trace_id:032x}" if span_context.is_valid else None
    except ImportError:
        return None


def _snapshot_items(
    db: Session, incident_id: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    seeded_snapshot_id = f"snap-{incident_id}-{FIXTURE_VERSION}"
    source_rows = db.scalars(
        select(SnapshotEvidence)
        .where(
            SnapshotEvidence.snapshot_id == seeded_snapshot_id,
            SnapshotEvidence.observed_at >= start,
            SnapshotEvidence.observed_at <= end,
        )
        .order_by(SnapshotEvidence.observed_at, SnapshotEvidence.evidence_id)
        .limit(2500)
    ).all()
    if not source_rows:
        raise ApiError(
            503, "fixture_not_seeded", "Incident evidence is not available yet.", retryable=True
        )
    return [
        {
            "evidence_id": row.evidence_id,
            "kind": row.kind,
            "source_record_id": row.source_record_id,
            "service_id": row.service_id,
            "observed_at": row.observed_at,
            "fixture_version": FIXTURE_VERSION,
            "payload": row.payload,
        }
        for row in source_rows
    ]


def _record_snapshot(
    db: Session,
    incident: Incident,
    items: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
    created_at: datetime,
) -> EvidenceSnapshot:
    snapshot_id = f"snap-live-{uuid.uuid4().hex}"
    digest = sha256_json(items)
    snapshot = EvidenceSnapshot(
        id=snapshot_id,
        incident_id=incident.id,
        fixture_version=incident.fixture_version,
        created_at=created_at,
        window_start=window_start,
        window_end=window_end,
        sha256=digest,
        item_count=len(items),
        payload_version=SNAPSHOT_PAYLOAD_VERSION,
    )
    db.add(snapshot)
    db.flush()
    db.add_all(
        [
            SnapshotEvidence(
                snapshot_id=snapshot_id,
                evidence_id=item["evidence_id"],
                kind=item["kind"],
                source_record_id=item["source_record_id"],
                service_id=item["service_id"],
                observed_at=item["observed_at"],
                payload=item["payload"],
            )
            for item in items
        ]
    )
    db.flush()
    return snapshot


def _build_packet(
    db: Session, incident: Incident, items: list[dict[str, Any]], start: datetime, end: datetime
) -> dict[str, Any]:
    from incident_atlas.models import DependencyEdge, IncidentService, Service

    service_rows = db.execute(
        select(Service, IncidentService.role)
        .join(IncidentService, IncidentService.service_id == Service.id)
        .where(IncidentService.incident_id == incident.id)
        .order_by(Service.id)
    ).all()
    service_ids = [service.id for service, _ in service_rows]
    edges = db.scalars(
        select(DependencyEdge)
        .where(DependencyEdge.incident_id == incident.id)
        .order_by(DependencyEdge.id)
    ).all()
    return {
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "severity": incident.severity,
            "primary_service_id": incident.primary_service_id,
            "summary": incident.summary,
            "started_at": incident.started_at,
            "fixture_version": incident.fixture_version,
        },
        "window": {"start": start, "end": end},
        "services": [
            {"id": service.id, "name": service.name, "tier": service.tier, "role": role}
            for service, role in service_rows
        ],
        "dependencies": [
            {
                "from_service_id": edge.from_service_id,
                "to_service_id": edge.to_service_id,
                "relationship": edge.relationship,
            }
            for edge in edges
            if edge.from_service_id in service_ids and edge.to_service_id in service_ids
        ],
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "kind": item["kind"],
                "service_id": item["service_id"],
                "observed_at": item["observed_at"],
                "payload": item["payload"],
            }
            for item in items
        ],
    }


def _append_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    request_id: str,
    actor_hash: str | None,
    attributes: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=f"audit-{uuid.uuid4().hex}",
            occurred_at=datetime.now(UTC),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            actor_hash=actor_hash,
            attributes=attributes or {},
        )
    )


def _report_hypotheses(
    db: Session, *, investigation_id: str | None = None, replay_id: str | None = None
) -> list[HypothesisOut]:
    query = select(Hypothesis).order_by(Hypothesis.rank)
    query = (
        query.where(Hypothesis.investigation_id == investigation_id)
        if investigation_id
        else query.where(Hypothesis.replay_report_id == replay_id)
    )
    rows = db.scalars(query).all()
    return [
        HypothesisOut(
            id=row.id,
            rank=row.rank,
            statement=row.statement,
            confidence=Confidence(row.confidence),
            confidence_note=row.confidence_note,
            supporting_evidence_ids=row.supporting_evidence_ids,
            contradicting_evidence_ids=row.contradicting_evidence_ids,
            next_read_only_check=row.next_read_only_check,
            mitigation=(
                MitigationProposal(
                    id=row.mitigation_id, summary=row.mitigation_summary, simulation_only=True
                )
                if row.mitigation_id and row.mitigation_summary
                else None
            ),
        )
        for row in rows
    ]


def _require_snapshot_references(
    db: Session,
    snapshot_id: str,
    hypotheses: list[HypothesisOut],
    rules: RulesBaselineOut,
) -> None:
    expected_ids = {
        evidence_id
        for hypothesis in hypotheses
        for evidence_id in (
            hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
        )
    }
    expected_ids.update(
        evidence_id for rule in rules.fired_rules for evidence_id in rule.evidence_ids
    )
    if not expected_ids:
        return
    available_ids = set(
        db.scalars(
            select(SnapshotEvidence.evidence_id).where(
                SnapshotEvidence.snapshot_id == snapshot_id,
                SnapshotEvidence.evidence_id.in_(expected_ids),
            )
        ).all()
    )
    missing = expected_ids - available_ids
    if missing:
        raise ApiError(
            500,
            "report_evidence_integrity_error",
            "A report referenced evidence outside its recorded snapshot.",
        )


def _validate_evidence_references(draft: Any, available_ids: set[str]) -> None:
    for hypothesis in draft.hypotheses:
        references = hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
        if not references:
            raise ProviderInvalidOutput("each hypothesis must cite at least one evidence item")
        unknown = sorted(set(references) - available_ids)
        if unknown:
            raise ProviderInvalidOutput(
                "report cited an evidence ID outside the investigation snapshot"
            )
        if len(set(references)) != len(references):
            raise ProviderInvalidOutput("report contains duplicate evidence references")


def _failure_response(status: str, code: str) -> ApiError:
    if status == "timed_out":
        return ApiError(
            504,
            "investigation_timeout",
            "The live model request timed out. The stored replay is still available.",
            retryable=True,
        )
    if status == "refused":
        return ApiError(
            422, "provider_refused", "The model declined to analyze this evidence packet."
        )
    if status == "invalid_output":
        return ApiError(
            502,
            "invalid_model_output",
            "The model response failed report validation. No diagnosis was returned.",
            retryable=True,
        )
    return ApiError(
        503,
        code or "provider_unavailable",
        "Live analysis is temporarily unavailable. The stored replay is still available.",
        retryable=True,
    )


def report_for_investigation(
    db: Session, investigation: Investigation, request_id: str
) -> InvestigationReport:
    snapshot = db.get(EvidenceSnapshot, investigation.snapshot_id)
    if snapshot is None:
        raise ApiError(500, "snapshot_missing", "The investigation snapshot could not be loaded.")
    if investigation.status != "completed":
        raise _failure_response(
            investigation.status, investigation.error_code or "provider_unavailable"
        )
    hypotheses = _report_hypotheses(db, investigation_id=investigation.id)
    rules = RulesBaselineOut.model_validate(investigation.rules_result or {})
    _require_snapshot_references(db, snapshot.id, hypotheses, rules)
    return InvestigationReport(
        id=investigation.id,
        incident_id=investigation.incident_id,
        fixture_version=snapshot.fixture_version,
        source="live_ai",
        model_call_made=True,
        status="completed",
        started_at=investigation.started_at,
        completed_at=investigation.completed_at or investigation.started_at,
        model_id=investigation.model_id,
        prompt_version=investigation.prompt_version,
        schema_version=investigation.schema_version,
        evidence_snapshot_id=snapshot.id,
        evidence_snapshot_sha256=snapshot.sha256,
        uncertainty=investigation.uncertainty or "Uncertainty was not recorded.",
        hypotheses=hypotheses,
        rules_baseline=rules,
        usage={
            "input_tokens": investigation.input_tokens,
            "output_tokens": investigation.output_tokens,
        },
        trace_id=investigation.trace_id,
        request_id=request_id,
    )


def report_for_replay(db: Session, replay: ReplayReport, request_id: str) -> InvestigationReport:
    snapshot = db.get(EvidenceSnapshot, replay.snapshot_id)
    incident = db.get(Incident, replay.incident_id)
    if snapshot is None or incident is None:
        raise ApiError(500, "replay_snapshot_missing", "The stored replay is incomplete.")
    payload = replay.report_payload
    rules = payload.get("rules_baseline") or {
        "version": replay.rules_version,
        "ranked_labels": [],
        "fired_rules": [],
    }
    hypotheses = _report_hypotheses(db, replay_id=replay.id)
    rules_out = RulesBaselineOut.model_validate(rules)
    _require_snapshot_references(db, snapshot.id, hypotheses, rules_out)
    return InvestigationReport(
        id=replay.id,
        incident_id=replay.incident_id,
        fixture_version=snapshot.fixture_version,
        source="stored_replay",
        model_call_made=False,
        status="completed",
        started_at=incident.started_at,
        completed_at=replay.created_at,
        model_id="curated-fixture",
        prompt_version="curated-replay-v1",
        schema_version=SCHEMA_VERSION,
        evidence_snapshot_id=snapshot.id,
        evidence_snapshot_sha256=snapshot.sha256,
        uncertainty=payload["uncertainty"],
        hypotheses=hypotheses,
        rules_baseline=rules_out,
        usage={"input_tokens": 0, "output_tokens": 0},
        trace_id=None,
        replay_id=replay.id,
        originally_generated_at=replay.created_at,
        request_id=request_id,
    )


def _set_failed(
    db: Session, run: Investigation, status: str, code: str, request_id: str, actor_hash: str
) -> None:
    run.status = status
    run.error_code = code
    run.completed_at = datetime.now(UTC)
    _append_audit(
        db,
        f"investigation_{status}",
        "investigation",
        run.id,
        request_id,
        actor_hash,
        {"error_code": code},
    )
    db.commit()


def create_live_investigation(
    db: Session,
    settings: Settings,
    incident_id: str,
    evidence_window_minutes: int,
    request_id: str,
    subject_hash: str,
    idempotency_key: str,
) -> InvestigationReport:
    if evidence_window_minutes > settings.max_evidence_window_minutes:
        raise ApiError(
            422,
            "time_range_too_large",
            f"The evidence window cannot exceed {settings.max_evidence_window_minutes} minutes.",
        )
    if not settings.live_enabled:
        raise ApiError(
            503,
            "live_analysis_disabled",
            "Live analysis is disabled; use the stored replay.",
            retryable=True,
        )

    body_fingerprint = fingerprint(
        json.dumps(
            {"incident_id": incident_id, "evidence_window_minutes": evidence_window_minutes},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    key_digest = idempotency_hash(idempotency_key)
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"idempotency:{subject_hash}:{key_digest}"},
    )
    existing = db.scalar(
        select(Investigation).where(
            Investigation.source_hash == subject_hash,
            Investigation.idempotency_key_hash == key_digest,
        )
    )
    if existing:
        db.rollback()
        if existing.request_fingerprint != body_fingerprint:
            raise ApiError(
                409,
                "idempotency_conflict",
                "This idempotency key was already used for a different request.",
            )
        if existing.status == "running":
            raise ApiError(
                409,
                "investigation_in_progress",
                "This investigation is already running.",
                retryable=True,
            )
        return report_for_investigation(db, existing, request_id)

    incident = db.get(Incident, incident_id)
    if incident is None:
        db.rollback()
        raise ApiError(404, "not_found", "The requested incident does not exist.")

    pre_minutes = min(5, max(1, evidence_window_minutes // 3))
    window_start = max(
        incident.started_at - timedelta(minutes=pre_minutes),
        incident.started_at - timedelta(minutes=5),
    )
    window_end = min(
        incident.started_at + timedelta(minutes=evidence_window_minutes - pre_minutes),
        incident.ended_at,
    )
    items = _snapshot_items(db, incident_id, window_start, window_end)
    if len(items) > settings.max_rows_per_signal * 4:
        db.rollback()
        raise ApiError(
            422,
            "evidence_limit_exceeded",
            "The bounded evidence packet exceeds its configured limit.",
        )

    now = datetime.now(UTC)
    snapshot = _record_snapshot(db, incident, items, window_start, window_end, now)
    rules = evaluate_rules(incident.id, incident.started_at, items)
    run = Investigation(
        id=f"inv_{uuid.uuid4().hex}",
        incident_id=incident.id,
        status="running",
        snapshot_id=snapshot.id,
        model_id=settings.openai_model,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        started_at=now,
        input_tokens=0,
        output_tokens=0,
        trace_id=current_trace_id(),
        idempotency_key_hash=key_digest,
        source_hash=subject_hash,
        request_fingerprint=body_fingerprint,
        rules_result=rules,
    )
    db.add(run)
    _append_audit(
        db,
        "investigation_started",
        "investigation",
        run.id,
        request_id,
        subject_hash,
        {"snapshot_id": snapshot.id},
    )
    db.commit()

    packet = _build_packet(db, incident, items, window_start, window_end)
    started = time.monotonic()
    slot_acquired = False
    try:
        acquire_live_slot(settings.max_live_inflight)
        slot_acquired = True
        provider_result = run_responses_inference(settings, packet)
        if time.monotonic() - started > settings.investigation_deadline_seconds:
            raise ProviderTimeout("overall investigation deadline was exceeded")
        evidence_ids = {item["evidence_id"] for item in items}
        _validate_evidence_references(provider_result.draft, evidence_ids)
    except ProviderTimeout:
        _set_failed(db, run, "timed_out", "investigation_timeout", request_id, subject_hash)
        raise _failure_response("timed_out", "investigation_timeout") from None
    except ProviderRefusal:
        _set_failed(db, run, "refused", "provider_refused", request_id, subject_hash)
        raise _failure_response("refused", "provider_refused") from None
    except ProviderInvalidOutput:
        _set_failed(db, run, "invalid_output", "invalid_model_output", request_id, subject_hash)
        raise _failure_response("invalid_output", "invalid_model_output") from None
    except ProviderUnavailable:
        _set_failed(db, run, "failed", "provider_unavailable", request_id, subject_hash)
        raise _failure_response("failed", "provider_unavailable") from None
    except ApiError as exc:
        _set_failed(db, run, "failed", exc.code, request_id, subject_hash)
        raise
    finally:
        if slot_acquired:
            release_live_slot()

    completed_at = datetime.now(UTC)
    run.status = "completed"
    run.completed_at = completed_at
    run.uncertainty = provider_result.draft.uncertainty
    run.input_tokens = provider_result.input_tokens
    run.output_tokens = provider_result.output_tokens
    run.provider_request_id = provider_result.provider_request_id
    _append_audit(
        db,
        "investigation_completed",
        "investigation",
        run.id,
        request_id,
        subject_hash,
        {
            "snapshot_id": snapshot.id,
            "input_tokens": provider_result.input_tokens,
            "output_tokens": provider_result.output_tokens,
            "provider_request_id": provider_result.provider_request_id,
        },
    )
    for draft in provider_result.draft.hypotheses:
        db.add(
            Hypothesis(
                id=f"hyp_{run.id}_{draft.rank}",
                investigation_id=run.id,
                replay_report_id=None,
                rank=draft.rank,
                statement=draft.statement,
                confidence=draft.confidence,
                confidence_note=draft.confidence_note,
                supporting_evidence_ids=draft.supporting_evidence_ids,
                contradicting_evidence_ids=draft.contradicting_evidence_ids,
                next_read_only_check=draft.next_read_only_check,
                mitigation_id=f"mit_{run.id}_{draft.rank}",
                mitigation_summary=draft.mitigation_summary,
            )
        )
    db.commit()
    return report_for_investigation(db, run, request_id)


def get_investigation(db: Session, investigation_id: str, request_id: str) -> InvestigationReport:
    run = db.get(Investigation, investigation_id)
    if run is None:
        raise ApiError(404, "not_found", "The requested investigation does not exist.")
    return report_for_investigation(db, run, request_id)


def get_replay_for_incident(db: Session, incident_id: str, request_id: str) -> InvestigationReport:
    replay = db.scalar(select(ReplayReport).where(ReplayReport.incident_id == incident_id))
    if replay is None:
        if db.get(Incident, incident_id) is None:
            raise ApiError(404, "not_found", "The requested incident does not exist.")
        raise ApiError(
            503,
            "replay_unavailable",
            "The stored replay is temporarily unavailable.",
            retryable=True,
        )
    return report_for_replay(db, replay, request_id)


def get_replay(db: Session, replay_id: str, request_id: str) -> InvestigationReport:
    replay = db.get(ReplayReport, replay_id)
    if replay is None:
        raise ApiError(404, "not_found", "The requested replay does not exist.")
    return report_for_replay(db, replay, request_id)
