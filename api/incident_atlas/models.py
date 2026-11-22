from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_seed: Mapped[str] = mapped_column(String(120), nullable=False)
    display_timezone: Mapped[str] = mapped_column(String(48), default="UTC", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "severity IN ('SEV-1','SEV-2','SEV-3','SEV-4')", name="ck_incident_severity"
        ),
        CheckConstraint("ended_at > started_at", name="ck_incident_time_order"),
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(40), nullable=False)
    team: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class IncidentService(Base):
    __tablename__ = "incident_services"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('affected','dependency','upstream')", name="ck_incident_service_role"
        ),
    )


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    from_service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    to_service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    relationship: Mapped[str] = mapped_column(String(64), default="calls", nullable=False)
    observed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("from_service_id <> to_service_id", name="ck_dependency_not_self"),
        UniqueConstraint(
            "incident_id", "from_service_id", "to_service_id", name="uq_dependency_edge"
        ),
    )


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(180))
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (Index("ix_timeline_incident_time", "incident_id", "occurred_at", "id"),)


class MetricPoint(Base):
    __tablename__ = "metric_points"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    series_id: Mapped[str] = mapped_column(String(180), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(240), nullable=False)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(48), nullable=False)
    statistic: Mapped[str] = mapped_column(String(32), nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index(
            "ix_metric_incident_name_service_time",
            "incident_id",
            "metric_name",
            "service_id",
            "observed_at",
        ),
    )


class LogEvent(Base):
    __tablename__ = "log_events"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    span_id: Mapped[str | None] = mapped_column(String(32))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index("ix_log_incident_service_time", "incident_id", "service_id", "observed_at"),
    )


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    span_id: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(32))
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(240), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Numeric(16, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("incident_id", "trace_id", "span_id", name="uq_span_trace_span"),
        Index("ix_span_incident_service_time", "incident_id", "service_id", "started_at"),
        Index("ix_span_incident_trace", "incident_id", "trace_id", "parent_span_id"),
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_version: Mapped[str] = mapped_column(String(32), nullable=False)

    items: Mapped[list["SnapshotEvidence"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("window_end > window_start", name="ck_snapshot_window"),)


class SnapshotEvidence(Base):
    __tablename__ = "snapshot_evidence"

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(180), nullable=False)
    service_id: Mapped[str | None] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    snapshot: Mapped[EvidenceSnapshot] = relationship(back_populates="items")

    __table_args__ = (Index("ix_snapshot_evidence_lookup", "evidence_id", "snapshot_id"),)


class ReplayReport(Base):
    __tablename__ = "replay_reports"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(120), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(180))
    trace_id: Mapped[str | None] = mapped_column(String(32))
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    uncertainty: Mapped[str | None] = mapped_column(Text)
    rules_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','failed','timed_out','refused','invalid_output')",
            name="ck_investigation_status",
        ),
        UniqueConstraint(
            "source_hash", "idempotency_key_hash", name="uq_investigation_idempotency"
        ),
        Index("ix_investigation_incident_started", "incident_id", "started_at"),
    )


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    replay_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("replay_reports.id", ondelete="CASCADE")
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_note: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    contradicting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    next_read_only_check: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation_id: Mapped[str | None] = mapped_column(String(180))
    mitigation_summary: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "(investigation_id IS NULL) <> (replay_report_id IS NULL)",
            name="ck_hypothesis_one_result",
        ),
        CheckConstraint("confidence IN ('low','medium','high')", name="ck_hypothesis_confidence"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_hypothesis_rank"),
    )


class SimulationApproval(Base):
    __tablename__ = "simulation_approvals"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="RESTRICT")
    )
    replay_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("replay_reports.id", ondelete="RESTRICT")
    )
    hypothesis_id: Mapped[str] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="RESTRICT"), nullable=False
    )
    mitigation_id: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="simulated_approved", nullable=False)
    simulation_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    external_action_performed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visitor_session_hash: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(investigation_id IS NULL) <> (replay_report_id IS NULL)",
            name="ck_approval_one_result",
        ),
        CheckConstraint("status = 'simulated_approved'", name="ck_approval_simulated_status"),
        CheckConstraint(
            "simulation_only IS TRUE AND external_action_performed IS FALSE",
            name="ck_approval_no_external_action",
        ),
        UniqueConstraint(
            "investigation_id",
            "mitigation_id",
            "visitor_session_hash",
            name="uq_investigation_mitigation_approval",
        ),
        UniqueConstraint(
            "replay_report_id",
            "mitigation_id",
            "visitor_session_hash",
            name="uq_replay_mitigation_approval",
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(180), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_hash: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (Index("ix_audit_entity_time", "entity_type", "entity_id", "occurred_at"),)


class GuestRateEvent(Base):
    __tablename__ = "guest_rate_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_guest_rate_subject_action_time", "subject_hash", "action", "occurred_at"),
        Index("ix_guest_rate_occurred_at", "occurred_at"),
    )


class EvaluationLabel(Base):
    __tablename__ = "labels"
    __table_args__ = {"schema": "evaluation"}

    case_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_primary_label: Mapped[str] = mapped_column(String(100), nullable=False)
    acceptable_secondary_labels: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_contradicting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_abstention: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    label_version: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
