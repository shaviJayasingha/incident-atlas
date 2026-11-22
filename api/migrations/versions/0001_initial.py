"""Initial Incident Atlas schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS evaluation"))

    op.create_table(
        "services",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("tier", sa.String(40), nullable=False),
        sa.Column("team", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column(
            "primary_service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.Column("scenario_seed", sa.String(120), nullable=False),
        sa.Column("display_timezone", sa.String(48), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('SEV-1','SEV-2','SEV-3','SEV-4')", name="ck_incident_severity"
        ),
        sa.CheckConstraint("ended_at > started_at", name="ck_incident_time_order"),
    )
    op.create_table(
        "incident_services",
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "role IN ('affected','dependency','upstream')", name="ck_incident_service_role"
        ),
    )
    op.create_table(
        "dependency_edges",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relationship", sa.String(64), nullable=False, server_default="calls"),
        sa.Column("observed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.CheckConstraint("from_service_id <> to_service_id", name="ck_dependency_not_self"),
        sa.UniqueConstraint(
            "incident_id", "from_service_id", "to_service_id", name="uq_dependency_edge"
        ),
    )
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("service_id", sa.String(120), sa.ForeignKey("services.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.String(180)),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_timeline_incident_time", "timeline_events", ["incident_id", "occurred_at", "id"]
    )
    op.create_table(
        "metric_points",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("series_id", sa.String(180), nullable=False),
        sa.Column("metric_name", sa.String(240), nullable=False),
        sa.Column(
            "service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(48), nullable=False),
        sa.Column("statistic", sa.String(32), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("fixture_version", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_metric_incident_name_service_time",
        "metric_points",
        ["incident_id", "metric_name", "service_id", "observed_at"],
    )
    op.create_table(
        "log_events",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column(
            "service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("span_id", sa.String(32)),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("fixture_version", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_log_incident_service_time", "log_events", ["incident_id", "service_id", "observed_at"]
    )
    op.create_table(
        "spans",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("span_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(32)),
        sa.Column(
            "service_id",
            sa.String(120),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(240), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Numeric(16, 3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("incident_id", "trace_id", "span_id", name="uq_span_trace_span"),
    )
    op.create_index(
        "ix_span_incident_service_time", "spans", ["incident_id", "service_id", "started_at"]
    )
    op.create_index(
        "ix_span_incident_trace", "spans", ["incident_id", "trace_id", "parent_span_id"]
    )
    op.create_table(
        "evidence_snapshots",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("payload_version", sa.String(32), nullable=False),
        sa.CheckConstraint("window_end > window_start", name="ck_snapshot_window"),
    )
    op.create_table(
        "snapshot_evidence",
        sa.Column(
            "snapshot_id",
            sa.String(180),
            sa.ForeignKey("evidence_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("evidence_id", sa.String(180), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source_record_id", sa.String(180), nullable=False),
        sa.Column("service_id", sa.String(120)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_snapshot_evidence_lookup", "snapshot_evidence", ["evidence_id", "snapshot_id"]
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_evidence_snapshot_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'evidence snapshots are append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER evidence_snapshots_append_only "
            "BEFORE UPDATE OR DELETE ON evidence_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION reject_evidence_snapshot_mutation()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER snapshot_evidence_append_only "
            "BEFORE UPDATE OR DELETE ON snapshot_evidence "
            "FOR EACH ROW EXECUTE FUNCTION reject_evidence_snapshot_mutation()"
        )
    )
    op.create_table(
        "replay_reports",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.String(180),
            sa.ForeignKey("evidence_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("report_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rules_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.String(180),
            sa.ForeignKey("evidence_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("schema_version", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_request_id", sa.String(180)),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("idempotency_key_hash", sa.String(64)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("request_fingerprint", sa.String(64)),
        sa.Column("uncertainty", sa.Text()),
        sa.Column("rules_result", postgresql.JSONB(astext_type=sa.Text())),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','timed_out','refused','invalid_output')",
            name="ck_investigation_status",
        ),
        sa.UniqueConstraint(
            "source_hash", "idempotency_key_hash", name="uq_investigation_idempotency"
        ),
    )
    op.create_index(
        "ix_investigation_incident_started", "investigations", ["incident_id", "started_at"]
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(180),
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "replay_report_id",
            sa.String(180),
            sa.ForeignKey("replay_reports.id", ondelete="CASCADE"),
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("confidence_note", sa.Text(), nullable=False),
        sa.Column(
            "supporting_evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "contradicting_evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("next_read_only_check", sa.Text(), nullable=False),
        sa.Column("mitigation_id", sa.String(180)),
        sa.Column("mitigation_summary", sa.Text()),
        sa.CheckConstraint(
            "(investigation_id IS NULL) <> (replay_report_id IS NULL)",
            name="ck_hypothesis_one_result",
        ),
        sa.CheckConstraint(
            "confidence IN ('low','medium','high')", name="ck_hypothesis_confidence"
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_hypothesis_rank"),
    )
    op.create_table(
        "simulation_approvals",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(180),
            sa.ForeignKey("investigations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "replay_report_id",
            sa.String(180),
            sa.ForeignKey("replay_reports.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "hypothesis_id",
            sa.String(180),
            sa.ForeignKey("hypotheses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mitigation_id", sa.String(180), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="simulated_approved"),
        sa.Column("simulation_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "external_action_performed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visitor_session_hash", sa.String(64)),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "(investigation_id IS NULL) <> (replay_report_id IS NULL)",
            name="ck_approval_one_result",
        ),
        sa.CheckConstraint("status = 'simulated_approved'", name="ck_approval_simulated_status"),
        sa.CheckConstraint(
            "simulation_only IS TRUE AND external_action_performed IS FALSE",
            name="ck_approval_no_external_action",
        ),
        sa.UniqueConstraint(
            "investigation_id", "mitigation_id", name="uq_investigation_mitigation_approval"
        ),
        sa.UniqueConstraint(
            "replay_report_id", "mitigation_id", name="uq_replay_mitigation_approval"
        ),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(180), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("actor_hash", sa.String(64)),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_audit_entity_time", "audit_events", ["entity_type", "entity_id", "occurred_at"]
    )
    op.create_table(
        "guest_rate_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_guest_rate_subject_action_time",
        "guest_rate_events",
        ["subject_hash", "action", "occurred_at"],
    )
    op.create_table(
        "labels",
        sa.Column("case_id", sa.String(180), primary_key=True),
        sa.Column("incident_id", sa.String(120), nullable=False),
        sa.Column("fixture_version", sa.String(32), nullable=False),
        sa.Column("expected_primary_label", sa.String(100), nullable=False),
        sa.Column(
            "acceptable_secondary_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "expected_supporting_evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "expected_contradicting_evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expected_abstention", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("label_version", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("labels", schema="evaluation")
    op.drop_index("ix_guest_rate_subject_action_time", table_name="guest_rate_events")
    op.drop_table("guest_rate_events")
    op.drop_index("ix_audit_entity_time", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("simulation_approvals")
    op.drop_table("hypotheses")
    op.drop_index("ix_investigation_incident_started", table_name="investigations")
    op.drop_table("investigations")
    op.drop_table("replay_reports")
    op.drop_index("ix_snapshot_evidence_lookup", table_name="snapshot_evidence")
    op.drop_table("snapshot_evidence")
    op.drop_table("evidence_snapshots")
    op.drop_index("ix_span_incident_trace", table_name="spans")
    op.drop_index("ix_span_incident_service_time", table_name="spans")
    op.drop_table("spans")
    op.drop_index("ix_log_incident_service_time", table_name="log_events")
    op.drop_table("log_events")
    op.drop_index("ix_metric_incident_name_service_time", table_name="metric_points")
    op.drop_table("metric_points")
    op.drop_index("ix_timeline_incident_time", table_name="timeline_events")
    op.drop_table("timeline_events")
    op.drop_table("dependency_edges")
    op.drop_table("incident_services")
    op.drop_table("incidents")
    op.drop_table("services")
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_evidence_snapshot_mutation()"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS evaluation"))
