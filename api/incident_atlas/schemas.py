from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Severity(StrEnum):
    SEV_1 = "SEV-1"
    SEV_2 = "SEV-2"
    SEV_3 = "SEV-3"
    SEV_4 = "SEV-4"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TelemetryKind(StrEnum):
    METRICS = "metrics"
    LOGS = "logs"
    TRACES = "traces"


class HealthResponse(StrictModel):
    status: Literal["ok", "ready"]
    api_version: str
    request_id: str | None = None


class DemoCapabilities(StrictModel):
    stored_replay_available: bool = True
    live_ai_enabled: bool
    live_label: str = "fresh model inference over synthetic fixture telemetry"
    rate_limit: str
    request_id: str


class ServiceOut(StrictModel):
    id: str
    name: str
    tier: str
    team: str
    description: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class IncidentCard(StrictModel):
    id: str
    title: str
    severity: Severity
    primary_service: str
    started_at: datetime
    ended_at: datetime
    fixture_version: str
    replay_available: bool
    symptom_summary: str

    _started_utc = field_validator("started_at", mode="after")(as_utc)
    _ended_utc = field_validator("ended_at", mode="after")(as_utc)


class IncidentList(StrictModel):
    items: list[IncidentCard]
    next_cursor: str | None
    request_id: str


class IncidentDetail(IncidentCard):
    slug: str
    scenario_seed: str
    display_timezone: str
    services: list[ServiceOut]


class TimelineEventOut(StrictModel):
    evidence_id: str
    occurred_at: datetime
    kind: str
    service_id: str | None
    title: str
    summary: str
    source_record_id: str | None
    fixture_version: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    _occurred_utc = field_validator("occurred_at", mode="after")(as_utc)


class TimelineResponse(StrictModel):
    items: list[TimelineEventOut]
    next_cursor: str | None
    request_id: str


class DependencyNode(StrictModel):
    id: str
    name: str
    tier: str
    team: str
    role: str


class DependencyEdgeOut(StrictModel):
    id: str
    from_service_id: str
    to_service_id: str
    relationship: str
    observed: bool
    attributes: dict[str, Any] = Field(default_factory=dict)


class DependenciesResponse(StrictModel):
    nodes: list[DependencyNode]
    edges: list[DependencyEdgeOut]
    request_id: str


class MetricPointOut(StrictModel):
    evidence_id: str
    kind: Literal["metric"] = "metric"
    series_id: str
    metric_name: str
    service_id: str
    observed_at: datetime
    value: float
    unit: str
    statistic: str
    labels: dict[str, Any]
    fixture_version: str

    _observed_utc = field_validator("observed_at", mode="after")(as_utc)


class LogEventOut(StrictModel):
    evidence_id: str
    kind: Literal["log"] = "log"
    observed_at: datetime
    severity: str
    service_id: str
    message: str
    trace_id: str | None
    span_id: str | None
    attributes: dict[str, Any]
    fixture_version: str

    _observed_utc = field_validator("observed_at", mode="after")(as_utc)


class SpanOut(StrictModel):
    evidence_id: str
    kind: Literal["span"] = "span"
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service_id: str
    operation: str
    started_at: datetime
    duration_ms: float
    status: str
    attributes: dict[str, Any]
    fixture_version: str

    _started_utc = field_validator("started_at", mode="after")(as_utc)


class TelemetryResponse(StrictModel):
    kind: TelemetryKind
    items: list[MetricPointOut | LogEventOut | SpanOut]
    next_cursor: str | None
    request_id: str


class EvidenceItemOut(StrictModel):
    evidence_id: str
    kind: str
    source_record_id: str
    service_id: str | None
    observed_at: datetime
    fixture_version: str
    payload: dict[str, Any]
    snapshot_id: str
    snapshot_sha256: str

    _observed_utc = field_validator("observed_at", mode="after")(as_utc)


class SnapshotMetadata(StrictModel):
    id: str
    incident_id: str
    fixture_version: str
    created_at: datetime
    window_start: datetime
    window_end: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    item_count: int = Field(ge=0)
    request_id: str

    _created_utc = field_validator("created_at", mode="after")(as_utc)
    _window_start_utc = field_validator("window_start", mode="after")(as_utc)
    _window_end_utc = field_validator("window_end", mode="after")(as_utc)


class MitigationProposal(StrictModel):
    id: str
    summary: str
    simulation_only: Literal[True] = True


class HypothesisOut(StrictModel):
    id: str
    rank: int = Field(ge=1, le=3)
    statement: str = Field(min_length=1, max_length=1200)
    confidence: Confidence
    confidence_note: str = Field(min_length=1, max_length=800)
    supporting_evidence_ids: list[str] = Field(max_length=12)
    contradicting_evidence_ids: list[str] = Field(max_length=12)
    next_read_only_check: str = Field(min_length=1, max_length=800)
    mitigation: MitigationProposal | None


class RuleFire(StrictModel):
    rule_id: str
    evidence_ids: list[str]


class RulesBaselineOut(StrictModel):
    version: str
    ranked_labels: list[str]
    fired_rules: list[RuleFire]


class InvestigationReport(StrictModel):
    id: str
    incident_id: str
    fixture_version: str
    source: Literal["live_ai", "stored_replay"]
    model_call_made: bool
    status: str
    started_at: datetime
    completed_at: datetime
    model_id: str
    prompt_version: str
    schema_version: str
    evidence_snapshot_id: str
    evidence_snapshot_sha256: str
    uncertainty: str = Field(min_length=1, max_length=1200)
    hypotheses: list[HypothesisOut] = Field(max_length=3)
    rules_baseline: RulesBaselineOut
    usage: dict[str, int]
    trace_id: str | None
    replay_id: str | None = None
    originally_generated_at: datetime | None = None
    request_id: str

    _started_utc = field_validator("started_at", mode="after")(as_utc)
    _completed_utc = field_validator("completed_at", mode="after")(as_utc)


class InvestigationCreate(StrictModel):
    incident_id: str = Field(min_length=1, max_length=120)
    evidence_window_minutes: int = Field(default=15, ge=5, le=15)


class ApprovalCreate(StrictModel):
    hypothesis_id: str = Field(min_length=1, max_length=180)
    mitigation_id: str = Field(min_length=1, max_length=180)
    simulation_acknowledged: Literal[True]


class ApprovalResponse(StrictModel):
    id: str
    investigation_id: str | None
    replay_id: str | None
    mitigation_id: str
    status: Literal["simulated_approved"]
    simulation_only: Literal[True]
    external_action_performed: Literal[False]
    recorded_at: datetime
    message: Literal["Simulation recorded; no system was changed."]
    request_id: str

    _recorded_utc = field_validator("recorded_at", mode="after")(as_utc)


class Problem(StrictModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    request_id: str
    retryable: bool = False
