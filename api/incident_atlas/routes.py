import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from incident_atlas.config import Settings, get_settings
from incident_atlas.db import get_db
from incident_atlas.errors import ApiError
from incident_atlas.models import (
    AuditEvent,
    DependencyEdge,
    EvidenceSnapshot,
    Hypothesis,
    Incident,
    IncidentService,
    Investigation,
    LogEvent,
    MetricPoint,
    ReplayReport,
    Service,
    SimulationApproval,
    SnapshotEvidence,
    Span,
    TimelineEvent,
)
from incident_atlas.pagination import decode_cursor, encode_cursor, validate_window
from incident_atlas.schemas import (
    ApprovalCreate,
    ApprovalResponse,
    DemoCapabilities,
    DependenciesResponse,
    DependencyEdgeOut,
    DependencyNode,
    EvidenceItemOut,
    HealthResponse,
    IncidentCard,
    IncidentDetail,
    IncidentList,
    InvestigationCreate,
    InvestigationReport,
    LogEventOut,
    MetricPointOut,
    Problem,
    ServiceOut,
    SnapshotMetadata,
    SpanOut,
    TelemetryKind,
    TelemetryResponse,
    TimelineEventOut,
    TimelineResponse,
)
from incident_atlas.security import enforce_rate_limit
from incident_atlas.service import (
    create_live_investigation,
    get_investigation,
    get_replay,
    get_replay_for_incident,
)


def _problem_response(description: str) -> dict[str, object]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": Problem.model_json_schema()}},
    }


router = APIRouter(
    prefix="/api/v1",
    responses={
        400: _problem_response("Invalid filter or cursor."),
        404: _problem_response("The requested resource does not exist."),
        409: _problem_response("The request conflicts with existing state."),
        411: _problem_response("A bounded Content-Length is required."),
        413: _problem_response("The request body exceeds its limit."),
        422: _problem_response("The request or live output is invalid."),
        429: _problem_response("The public demo limit or live capacity was reached."),
        500: _problem_response("The server encountered an internal error."),
        502: _problem_response("The live report did not pass validation."),
        503: _problem_response("A required service is unavailable."),
        504: _problem_response("The live model request timed out."),
    },
)
Db = Annotated[Session, Depends(get_db)]
Cfg = Annotated[Settings, Depends(get_settings)]


def _request_id(request: Request) -> str:
    return request.state.request_id


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def _effective_window(
    incident: Incident,
    from_time: datetime | None,
    to_time: datetime | None,
    maximum_minutes: int,
) -> tuple[datetime, datetime]:
    pre_minutes = min(5, max(1, maximum_minutes // 3))
    start = from_time or incident.started_at - timedelta(minutes=pre_minutes)
    end = to_time or incident.started_at + timedelta(minutes=maximum_minutes - pre_minutes)
    validate_window(start, end, maximum_minutes)
    return start, end


def _incident_card(db: Session, incident: Incident) -> IncidentCard:
    primary = db.get(Service, incident.primary_service_id)
    has_replay = (
        db.scalar(select(ReplayReport.id).where(ReplayReport.incident_id == incident.id).limit(1))
        is not None
    )
    return IncidentCard(
        id=incident.id,
        title=incident.title,
        severity=incident.severity,
        primary_service=primary.name if primary else incident.primary_service_id,
        started_at=incident.started_at,
        ended_at=incident.ended_at,
        fixture_version=incident.fixture_version,
        replay_available=has_replay,
        symptom_summary=incident.summary,
    )


@router.get("/demo-capabilities", response_model=DemoCapabilities)
def demo_capabilities(request: Request, settings: Cfg) -> DemoCapabilities:
    limit = (
        f"{settings.rate_live_runs} live runs per "
        f"{settings.rate_live_window_seconds // 60} minutes per visitor hash"
    )
    return DemoCapabilities(
        live_ai_enabled=settings.live_enabled,
        rate_limit=limit,
        request_id=_request_id(request),
    )


@router.get("/incidents", response_model=IncidentList)
def list_incidents(
    request: Request,
    db: Db,
    severity: Annotated[str | None, Query(pattern=r"^SEV-[1-4]$")] = None,
    service: Annotated[str | None, Query(max_length=120)] = None,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> IncidentList:
    query = select(Incident).order_by(Incident.id)
    if severity:
        query = query.where(Incident.severity == severity)
    if service:
        query = query.join(IncidentService, IncidentService.incident_id == Incident.id).where(
            IncidentService.service_id == service
        )
    if cursor:
        parsed = decode_cursor(cursor)
        assert parsed is not None
        query = query.where(Incident.id > parsed[1])
    rows = db.scalars(query.limit(limit + 1)).unique().all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None
    return IncidentList(
        items=[_incident_card(db, row) for row in rows],
        next_cursor=next_cursor,
        request_id=_request_id(request),
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident_detail(incident_id: str, request: Request, db: Db) -> IncidentDetail:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, "not_found", "The requested incident does not exist.")
    services = db.execute(
        select(Service, IncidentService.role)
        .join(IncidentService, IncidentService.service_id == Service.id)
        .where(IncidentService.incident_id == incident_id)
        .order_by(Service.id)
    ).all()
    return IncidentDetail(
        **_incident_card(db, incident).model_dump(),
        slug=incident.slug,
        scenario_seed=incident.scenario_seed,
        display_timezone=incident.display_timezone,
        services=[
            ServiceOut.model_validate(service, from_attributes=True) for service, _ in services
        ],
    )


@router.get("/incidents/{incident_id}/timeline", response_model=TimelineResponse)
def incident_timeline(
    incident_id: str,
    request: Request,
    db: Db,
    settings: Cfg,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
) -> TimelineResponse:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, "not_found", "The requested incident does not exist.")
    start, end = _effective_window(
        incident, from_time, to_time, settings.max_evidence_window_minutes
    )
    query = select(TimelineEvent).where(
        TimelineEvent.incident_id == incident_id,
        TimelineEvent.occurred_at >= start,
        TimelineEvent.occurred_at <= end,
    )
    if cursor:
        parsed = decode_cursor(cursor)
        assert parsed is not None
        query = query.where(
            tuple_(TimelineEvent.occurred_at, TimelineEvent.id) > tuple_(parsed[0], parsed[1])
        )
    rows = db.scalars(
        query.order_by(TimelineEvent.occurred_at, TimelineEvent.id).limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return TimelineResponse(
        items=[
            TimelineEventOut(
                evidence_id=row.id,
                occurred_at=row.occurred_at,
                kind=row.kind,
                service_id=row.service_id,
                title=row.title,
                summary=row.summary,
                source_record_id=row.source_record_id,
                fixture_version=row.fixture_version,
                attributes=row.attributes,
            )
            for row in rows
        ],
        next_cursor=encode_cursor(rows[-1].occurred_at, rows[-1].id) if more and rows else None,
        request_id=_request_id(request),
    )


@router.get("/incidents/{incident_id}/dependencies", response_model=DependenciesResponse)
def dependencies(incident_id: str, request: Request, db: Db) -> DependenciesResponse:
    if db.get(Incident, incident_id) is None:
        raise ApiError(404, "not_found", "The requested incident does not exist.")
    nodes = db.execute(
        select(Service, IncidentService.role)
        .join(IncidentService, IncidentService.service_id == Service.id)
        .where(IncidentService.incident_id == incident_id)
        .order_by(Service.id)
    ).all()
    edge_rows = db.scalars(
        select(DependencyEdge)
        .where(DependencyEdge.incident_id == incident_id)
        .order_by(DependencyEdge.id)
    ).all()
    return DependenciesResponse(
        nodes=[
            DependencyNode(id=s.id, name=s.name, tier=s.tier, team=s.team, role=role)
            for s, role in nodes
        ],
        edges=[
            DependencyEdgeOut(
                id=e.id,
                from_service_id=e.from_service_id,
                to_service_id=e.to_service_id,
                relationship=e.relationship,
                observed=e.observed,
                attributes=e.attributes,
            )
            for e in edge_rows
        ],
        request_id=_request_id(request),
    )


@router.get("/incidents/{incident_id}/telemetry", response_model=TelemetryResponse)
def telemetry(
    incident_id: str,
    request: Request,
    db: Db,
    settings: Cfg,
    kind: TelemetryKind,
    service: Annotated[str | None, Query(max_length=120)] = None,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> TelemetryResponse:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, "not_found", "The requested incident does not exist.")
    start, end = _effective_window(
        incident, from_time, to_time, settings.max_evidence_window_minutes
    )

    if kind == TelemetryKind.METRICS:
        query = select(MetricPoint).where(
            MetricPoint.incident_id == incident_id,
            MetricPoint.observed_at >= start,
            MetricPoint.observed_at <= end,
        )
        if service:
            query = query.where(MetricPoint.service_id == service)
        if cursor:
            parsed = decode_cursor(cursor)
            assert parsed is not None
            query = query.where(
                tuple_(MetricPoint.observed_at, MetricPoint.id) > tuple_(parsed[0], parsed[1])
            )
        rows = db.scalars(
            query.order_by(MetricPoint.observed_at, MetricPoint.id).limit(limit + 1)
        ).all()
        more = len(rows) > limit
        rows = rows[:limit]
        items = [
            MetricPointOut(
                evidence_id=row.id,
                series_id=row.series_id,
                metric_name=row.metric_name,
                service_id=row.service_id,
                observed_at=row.observed_at,
                value=float(row.value),
                unit=row.unit,
                statistic=row.statistic,
                labels=row.labels,
                fixture_version=row.fixture_version,
            )
            for row in rows
        ]
        next_cursor = encode_cursor(rows[-1].observed_at, rows[-1].id) if more and rows else None
    elif kind == TelemetryKind.LOGS:
        query = select(LogEvent).where(
            LogEvent.incident_id == incident_id,
            LogEvent.observed_at >= start,
            LogEvent.observed_at <= end,
        )
        if service:
            query = query.where(LogEvent.service_id == service)
        if cursor:
            parsed = decode_cursor(cursor)
            assert parsed is not None
            query = query.where(
                tuple_(LogEvent.observed_at, LogEvent.id) > tuple_(parsed[0], parsed[1])
            )
        rows = db.scalars(query.order_by(LogEvent.observed_at, LogEvent.id).limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        items = [
            LogEventOut(
                evidence_id=row.id,
                observed_at=row.observed_at,
                severity=row.severity,
                service_id=row.service_id,
                message=row.body,
                trace_id=row.trace_id,
                span_id=row.span_id,
                attributes=row.attributes,
                fixture_version=row.fixture_version,
            )
            for row in rows
        ]
        next_cursor = encode_cursor(rows[-1].observed_at, rows[-1].id) if more and rows else None
    else:
        query = select(Span).where(
            Span.incident_id == incident_id, Span.started_at >= start, Span.started_at <= end
        )
        if service:
            query = query.where(Span.service_id == service)
        if cursor:
            parsed = decode_cursor(cursor)
            assert parsed is not None
            query = query.where(tuple_(Span.started_at, Span.id) > tuple_(parsed[0], parsed[1]))
        rows = db.scalars(query.order_by(Span.started_at, Span.id).limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        items = [
            SpanOut(
                evidence_id=row.id,
                trace_id=row.trace_id,
                span_id=row.span_id,
                parent_span_id=row.parent_span_id,
                service_id=row.service_id,
                operation=row.operation,
                started_at=row.started_at,
                duration_ms=float(row.duration_ms),
                status=row.status,
                attributes=row.attributes,
                fixture_version=row.fixture_version,
            )
            for row in rows
        ]
        next_cursor = encode_cursor(rows[-1].started_at, rows[-1].id) if more and rows else None
    return TelemetryResponse(
        kind=kind, items=items, next_cursor=next_cursor, request_id=_request_id(request)
    )


@router.get("/snapshots/{snapshot_id}/evidence/{evidence_id}", response_model=EvidenceItemOut)
def snapshot_evidence(
    snapshot_id: str, evidence_id: str, request: Request, db: Db
) -> EvidenceItemOut:
    row = db.get(SnapshotEvidence, {"snapshot_id": snapshot_id, "evidence_id": evidence_id})
    snapshot = db.get(EvidenceSnapshot, snapshot_id)
    if row is None or snapshot is None:
        raise ApiError(
            404, "evidence_not_found", "That evidence item is not present in this snapshot."
        )
    return EvidenceItemOut(
        evidence_id=row.evidence_id,
        kind=row.kind,
        source_record_id=row.source_record_id,
        service_id=row.service_id,
        observed_at=row.observed_at,
        fixture_version=snapshot.fixture_version,
        payload=row.payload,
        snapshot_id=snapshot.id,
        snapshot_sha256=snapshot.sha256,
    )


@router.get("/incidents/{incident_id}/replay", response_model=InvestigationReport)
def replay_for_incident(incident_id: str, request: Request, db: Db) -> InvestigationReport:
    report = get_replay_for_incident(db, incident_id, _request_id(request))
    db.add(
        AuditEvent(
            id=f"audit-{uuid.uuid4().hex}",
            occurred_at=datetime.now(UTC),
            action="replay_served",
            entity_type="replay",
            entity_id=report.id,
            request_id=_request_id(request),
            actor_hash=None,
            attributes={"model_call_made": False},
        )
    )
    db.commit()
    return report


@router.get("/replays/{replay_id}", response_model=InvestigationReport)
def replay_by_id(replay_id: str, request: Request, db: Db) -> InvestigationReport:
    return get_replay(db, replay_id, _request_id(request))


@router.post("/investigations", response_model=InvestigationReport, status_code=201)
def run_investigation(
    body: InvestigationCreate,
    request: Request,
    db: Db,
    settings: Cfg,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=36, max_length=36)],
) -> InvestigationReport:
    try:
        parsed_key = uuid.UUID(idempotency_key)
    except ValueError:
        raise ApiError(400, "invalid_idempotency_key", "Idempotency-Key must be a UUID.") from None
    actor = enforce_rate_limit(db, settings, _client_host(request), "live")
    report, reused = create_live_investigation(
        db=db,
        settings=settings,
        incident_id=body.incident_id,
        evidence_window_minutes=body.evidence_window_minutes,
        request_id=_request_id(request),
        subject_hash=actor,
        idempotency_key=str(parsed_key),
    )
    if reused:
        response.status_code = 200
    return report


@router.get("/investigations/{investigation_id}", response_model=InvestigationReport)
def investigation_by_id(investigation_id: str, request: Request, db: Db) -> InvestigationReport:
    return get_investigation(db, investigation_id, _request_id(request))


def _create_approval(
    *,
    db: Session,
    settings: Settings,
    request: Request,
    result_id: str,
    source: Literal["live_ai", "stored_replay"],
    body: ApprovalCreate,
) -> ApprovalResponse:
    actor = enforce_rate_limit(db, settings, _client_host(request), "approval")
    if source == "live_ai":
        result = db.get(Investigation, result_id)
        if result is None:
            raise ApiError(404, "not_found", "The requested investigation does not exist.")
        hypothesis = db.get(Hypothesis, body.hypothesis_id)
        valid = hypothesis is not None and hypothesis.investigation_id == result_id
        investigation_id, replay_id = result_id, None
    else:
        result = db.get(ReplayReport, result_id)
        if result is None:
            raise ApiError(404, "not_found", "The requested replay does not exist.")
        hypothesis = db.get(Hypothesis, body.hypothesis_id)
        valid = hypothesis is not None and hypothesis.replay_report_id == result_id
        investigation_id, replay_id = None, result_id
    if not valid or hypothesis is None or hypothesis.mitigation_id != body.mitigation_id:
        raise ApiError(
            422,
            "invalid_approval",
            "The mitigation must belong to a hypothesis in the selected report.",
        )

    prior_query = select(AuditEvent).where(
        AuditEvent.entity_type == "simulation_approval",
        AuditEvent.entity_id == f"{source}:{result_id}:{body.mitigation_id}:{actor}",
    )
    prior = db.scalar(prior_query)
    if prior:
        raise ApiError(
            409, "approval_conflict", "This mitigation simulation has already been recorded."
        )

    now = datetime.now(UTC)
    approval_id = f"sim_{uuid.uuid4().hex}"
    approval = SimulationApproval(
        id=approval_id,
        investigation_id=investigation_id,
        replay_report_id=replay_id,
        hypothesis_id=hypothesis.id,
        mitigation_id=body.mitigation_id,
        status="simulated_approved",
        simulation_only=True,
        external_action_performed=False,
        recorded_at=now,
        visitor_session_hash=actor,
        request_id=_request_id(request),
    )
    db.add(approval)
    db.add(
        AuditEvent(
            id=f"audit-{uuid.uuid4().hex}",
            occurred_at=now,
            action="simulation_approved",
            entity_type="simulation_approval",
            entity_id=f"{source}:{result_id}:{body.mitigation_id}:{actor}",
            request_id=_request_id(request),
            actor_hash=actor,
            attributes={"simulation_only": True, "external_action_performed": False},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(
            409, "approval_conflict", "This mitigation simulation has already been recorded."
        ) from None
    return ApprovalResponse(
        id=approval_id,
        investigation_id=investigation_id,
        replay_id=replay_id,
        mitigation_id=body.mitigation_id,
        status="simulated_approved",
        simulation_only=True,
        external_action_performed=False,
        recorded_at=now,
        message="Simulation recorded; no system was changed.",
        request_id=_request_id(request),
    )


@router.post(
    "/investigations/{investigation_id}/mitigation-approvals",
    response_model=ApprovalResponse,
    status_code=201,
)
def approve_live_simulation(
    investigation_id: str,
    body: ApprovalCreate,
    request: Request,
    db: Db,
    settings: Cfg,
) -> ApprovalResponse:
    return _create_approval(
        db=db,
        settings=settings,
        request=request,
        result_id=investigation_id,
        source="live_ai",
        body=body,
    )


@router.post(
    "/replays/{replay_id}/mitigation-approvals", response_model=ApprovalResponse, status_code=201
)
def approve_replay_simulation(
    replay_id: str,
    body: ApprovalCreate,
    request: Request,
    db: Db,
    settings: Cfg,
) -> ApprovalResponse:
    return _create_approval(
        db=db,
        settings=settings,
        request=request,
        result_id=replay_id,
        source="stored_replay",
        body=body,
    )


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotMetadata)
def snapshot_metadata(snapshot_id: str, request: Request, db: Db) -> SnapshotMetadata:
    snapshot = db.get(EvidenceSnapshot, snapshot_id)
    if snapshot is None:
        raise ApiError(404, "not_found", "The requested evidence snapshot does not exist.")
    return SnapshotMetadata(
        id=snapshot.id,
        incident_id=snapshot.incident_id,
        fixture_version=snapshot.fixture_version,
        created_at=snapshot.created_at,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        sha256=snapshot.sha256,
        item_count=snapshot.item_count,
        request_id=_request_id(request),
    )


def liveness() -> HealthResponse:
    return HealthResponse(status="ok", api_version="0.1.0")


def readiness(db: Session, request: Request) -> HealthResponse:
    try:
        db.execute(select(1))
    except Exception:
        db.rollback()
        raise ApiError(
            503, "database_unavailable", "Database readiness check failed.", retryable=True
        ) from None
    return HealthResponse(status="ready", api_version="0.1.0", request_id=_request_id(request))
