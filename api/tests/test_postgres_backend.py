import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from incident_atlas.config import Settings, get_settings
from incident_atlas.db import SessionLocal, engine
from incident_atlas.errors import ProviderInvalidOutput, ProviderRefusal, ProviderTimeout
from incident_atlas.fixtures import seed_evaluation, seed_runtime
from incident_atlas.models import (
    AuditEvent,
    EvaluationLabel,
    EvidenceSnapshot,
    GuestRateEvent,
    Hypothesis,
    Incident,
    Investigation,
    SimulationApproval,
    SnapshotEvidence,
)
from incident_atlas.provider import DraftHypothesis, InvestigationDraft, ProviderResult

pytestmark = pytest.mark.postgres


def _live_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=os.environ["DATABASE_URL"],
        openai_api_key="test-provider-key",
        live_analysis_enabled=True,
        rate_limit_enabled=True,
    )


def _provider_result(evidence_id: str = "ev-cache-hit-ratio-drop") -> ProviderResult:
    return ProviderResult(
        draft=InvestigationDraft(
            uncertainty="The fixture supports a leading hypothesis, but does not prove causation.",
            hypotheses=[
                DraftHypothesis(
                    rank=1,
                    statement="A release changed the catalog cache namespace.",
                    confidence="medium",
                    confidence_note="The cache and database signals move after the release marker.",
                    supporting_evidence_ids=[evidence_id],
                    contradicting_evidence_ids=[],
                    next_read_only_check="Compare the old and new cache namespace configuration.",
                    mitigation_summary="Simulate reverting the namespace and warming the cache.",
                )
            ],
        ),
        input_tokens=100,
        output_tokens=50,
        provider_request_id="resp_test_001",
    )


def _run_live(client, monkeypatch, result=None, error=None):
    from incident_atlas.main import app

    app.dependency_overrides[get_settings] = _live_settings
    if error:

        def provider(*args, **kwargs):
            raise error
    else:

        def provider(*args, **kwargs):
            return result or _provider_result()

    monkeypatch.setattr("incident_atlas.service.run_responses_inference", provider)
    return client.post(
        "/api/v1/investigations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15},
    )


def test_migration_and_repeatable_seed(clean_postgres):
    from sqlalchemy import func, select

    with SessionLocal() as db:
        first = seed_runtime(db)
        second = seed_runtime(db)
        assert first == second
        assert db.scalar(select(func.count()).select_from(Incident)) == 3
        assert db.scalar(select(func.count()).select_from(EvidenceSnapshot)) == 3
        assert db.scalar(select(func.count()).select_from(SnapshotEvidence)) == sum(
            item["evidence_count"] for item in first["incidents"]
        )
        snapshot_id = first["incidents"][0]["snapshot_id"]
        evidence_id = db.scalar(
            select(SnapshotEvidence.evidence_id).where(SnapshotEvidence.snapshot_id == snapshot_id)
        )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE snapshot_evidence SET payload = '{}' "
                        "WHERE snapshot_id = :snapshot_id AND evidence_id = :evidence_id"
                    ),
                    {"snapshot_id": snapshot_id, "evidence_id": evidence_id},
                )
        labels = seed_evaluation(db)
        assert labels["case_count"] == 3
        assert db.scalar(select(func.count()).select_from(EvaluationLabel)) == 3


def test_runtime_role_cannot_read_evaluation_or_run_migrations(clean_postgres):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from incident_atlas.deployment import _provision_role, apply_runtime_grants

    with SessionLocal() as db:
        seed_runtime(db)

    role_name = "incident_atlas_runtime_ci"
    with engine.begin() as connection:
        _provision_role(connection, "ci-runtime-password", role_name)
        apply_runtime_grants(connection, role_name)

    admin_url = make_url(os.environ["DATABASE_URL"])
    runtime_url = admin_url.set(
        drivername="postgresql+psycopg",
        username=role_name,
        password="ci-runtime-password",
    )
    runtime_engine = create_engine(runtime_url)
    try:
        with runtime_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM public.incidents")) == 3
            assert connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'evaluation', 'USAGE')")
            ) is False
            assert connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, 'public.alembic_version', 'UPDATE')"
                )
            ) is False
            assert connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ) is False
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT * FROM evaluation.labels"))
            connection.rollback()
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("CREATE TABLE public.runtime_role_canary (id integer)")
                )
            connection.rollback()
    finally:
        runtime_engine.dispose()


def test_runtime_role_has_only_required_table_operations(clean_postgres):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from incident_atlas.deployment import _provision_role, apply_runtime_grants

    with SessionLocal() as db:
        seed_runtime(db)

    role_name = "incident_atlas_runtime_ci"
    with engine.begin() as connection:
        _provision_role(connection, "ci-runtime-password", role_name)
        apply_runtime_grants(connection, role_name)

    admin_url = make_url(os.environ["DATABASE_URL"])
    runtime_url = admin_url.set(
        drivername="postgresql+psycopg",
        username=role_name,
        password="ci-runtime-password",
    )
    runtime_engine = create_engine(runtime_url)
    now = datetime.now(UTC)
    snapshot_id = "snap-permission-matrix-ci"
    investigation_id = "inv-permission-matrix-ci"
    hypothesis_id = "hyp-permission-matrix-ci"
    try:
        with runtime_engine.begin() as connection:
            assert connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.incidents', 'SELECT')")
            )
            assert not connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.incidents', 'UPDATE')")
            )
            assert not connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.replay_reports', 'DELETE')")
            )
            assert not connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, 'public.guest_rate_events', 'DELETE')"
                )
            )
            assert connection.scalar(
                text(
                    "SELECT has_function_privilege(current_user, "
                    "'public.prune_expired_guest_rate_events()', 'EXECUTE')"
                )
            )
            assert not connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'public.simulation_approvals', 'UPDATE')"
                )
            )
            assert not connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'public.evidence_snapshots', 'UPDATE')"
                )
            )
            assert connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user, 'public.investigations', "
                    "'status', 'UPDATE')"
                )
            )
            assert not connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user, 'public.investigations', "
                    "'model_id', 'UPDATE')"
                )
            )

            connection.execute(
                text(
                    "INSERT INTO public.evidence_snapshots "
                    "(id, incident_id, fixture_version, created_at, window_start, window_end, "
                    "sha256, item_count, payload_version) VALUES "
                    "(:id, :incident, '1.0.0', :now, :start, :end, :hash, 1, 'v1')"
                ),
                {
                    "id": snapshot_id,
                    "incident": "inc-cache-collapse-001",
                    "now": now,
                    "start": now - timedelta(minutes=1),
                    "end": now,
                    "hash": "0" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO public.snapshot_evidence "
                    "(snapshot_id, evidence_id, kind, source_record_id, observed_at, payload) "
                    "VALUES (:snapshot, 'ev-permission-matrix-ci', 'log', 'log-ci', :now, '{}')"
                ),
                {"snapshot": snapshot_id, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO public.investigations "
                    "(id, incident_id, status, snapshot_id, model_id, prompt_version, "
                    "schema_version, started_at) VALUES "
                    "(:id, 'inc-cache-collapse-001', 'running', :snapshot, 'model', "
                    "'prompt-v1', 'schema-v1', :now)"
                ),
                {"id": investigation_id, "snapshot": snapshot_id, "now": now},
            )
            connection.execute(
                text(
                    "UPDATE public.investigations SET status='failed', completed_at=:now, "
                    "error_code='test' WHERE id=:id"
                ),
                {"id": investigation_id, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO public.hypotheses "
                    "(id, investigation_id, rank, statement, confidence, confidence_note, "
                    "supporting_evidence_ids, contradicting_evidence_ids, next_read_only_check, "
                    "mitigation_id, mitigation_summary) VALUES "
                    "(:id, :investigation, 1, 'synthetic claim', 'medium', 'uncertain', "
                    "'[]', '[]', 'check again', 'mit-ci', 'simulate mitigation')"
                ),
                {"id": hypothesis_id, "investigation": investigation_id},
            )
            connection.execute(
                text(
                    "INSERT INTO public.simulation_approvals "
                    "(id, investigation_id, hypothesis_id, mitigation_id, status, "
                    "simulation_only, external_action_performed, recorded_at, request_id) "
                    "VALUES ('approval-permission-matrix-ci', :investigation, :hypothesis, "
                    "'mit-ci', 'simulated_approved', true, false, :now, :request_id)"
                ),
                {
                    "investigation": investigation_id,
                    "hypothesis": hypothesis_id,
                    "now": now,
                    "request_id": "a" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO public.audit_events "
                    "(id, occurred_at, action, entity_type, entity_id, request_id, attributes) "
                    "VALUES ('audit-permission-matrix-ci', :now, 'test', 'test', 'test', "
                    ":request_id, '{}')"
                ),
                {"now": now, "request_id": "b" * 64},
            )
            rate_id = connection.scalar(
                text(
                    "INSERT INTO public.guest_rate_events (subject_hash, action) "
                    "VALUES (:subject, 'approval') RETURNING id"
                ),
                {"subject": "c" * 64},
            )
            assert connection.scalar(
                text("SELECT public.prune_expired_guest_rate_events()")
            ) == 0
            assert connection.scalar(
                text("SELECT count(*) FROM public.guest_rate_events WHERE id=:id"),
                {"id": rate_id},
            ) == 1

        denied_mutations = (
            "UPDATE public.incidents SET summary=summary WHERE id='inc-cache-collapse-001'",
            "DELETE FROM public.incidents WHERE id='inc-cache-collapse-001'",
            "UPDATE public.replay_reports SET rules_version=rules_version "
            "WHERE id='replay-cache-v1'",
            "DELETE FROM public.replay_reports WHERE id='replay-cache-v1'",
            f"UPDATE public.evidence_snapshots SET item_count=item_count WHERE id='{snapshot_id}'",
            f"DELETE FROM public.evidence_snapshots WHERE id='{snapshot_id}'",
            f"UPDATE public.snapshot_evidence SET payload=payload "
            f"WHERE snapshot_id='{snapshot_id}'",
            f"DELETE FROM public.snapshot_evidence WHERE snapshot_id='{snapshot_id}'",
            f"UPDATE public.hypotheses SET statement=statement WHERE id='{hypothesis_id}'",
            f"DELETE FROM public.hypotheses WHERE id='{hypothesis_id}'",
            f"UPDATE public.investigations SET model_id=model_id WHERE id='{investigation_id}'",
            "UPDATE public.simulation_approvals SET status=status "
            "WHERE id='approval-permission-matrix-ci'",
            "DELETE FROM public.simulation_approvals "
            "WHERE id='approval-permission-matrix-ci'",
            "UPDATE public.audit_events SET action=action "
            "WHERE id='audit-permission-matrix-ci'",
            "DELETE FROM public.audit_events WHERE id='audit-permission-matrix-ci'",
            f"DELETE FROM public.guest_rate_events WHERE id='{rate_id}'",
            "UPDATE public.guest_rate_events SET action=action WHERE false",
        )
        for statement in denied_mutations:
            with pytest.raises(DBAPIError):
                with runtime_engine.begin() as connection:
                    connection.execute(text(statement))
    finally:
        runtime_engine.dispose()


def test_bootstrap_preflight_reports_managed_database_privilege_blockers(clean_postgres):
    from incident_atlas.deployment import _preflight_migration_permissions, _provision_role

    limited_role = "incident_atlas_migration_limited_ci"
    runtime_role = "incident_atlas_runtime_missing_ci"
    secret = "must-never-appear-in-an-error"
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE ROLE {limited_role} LOGIN")
        try:
            connection.exec_driver_sql(f"SET ROLE {limited_role}")
            with pytest.raises(RuntimeError, match="lacks database/schema creation privileges"):
                _preflight_migration_permissions(connection)
            with pytest.raises(RuntimeError, match="cannot create the runtime role") as error:
                _provision_role(connection, secret, runtime_role)
            assert secret not in str(error.value)
        finally:
            connection.exec_driver_sql("RESET ROLE")
            connection.exec_driver_sql(f"DROP ROLE IF EXISTS {limited_role}")


def test_precreated_runtime_credential_does_not_require_createrole(clean_postgres):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from incident_atlas.deployment import _provision_role

    migration_role = "incident_atlas_migration_nocreate_ci"
    runtime_role = "incident_atlas_runtime_managed_ci"
    runtime_password = "managed-runtime-password"
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE ROLE {migration_role} LOGIN")
        connection.exec_driver_sql(
            f"CREATE ROLE {runtime_role} LOGIN PASSWORD '{runtime_password}' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        )
        try:
            connection.exec_driver_sql(f"SET ROLE {migration_role}")
            _provision_role(connection, "must-not-rotate-managed-password", runtime_role)
        finally:
            connection.exec_driver_sql("RESET ROLE")

    base_url = make_url(os.environ["DATABASE_URL"])
    runtime_url = base_url.set(
        drivername="postgresql+psycopg", username=runtime_role, password=runtime_password
    )
    runtime_engine = create_engine(runtime_url)
    try:
        with runtime_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == runtime_role
    finally:
        runtime_engine.dispose()
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP ROLE IF EXISTS {runtime_role}")
            connection.exec_driver_sql(f"DROP ROLE IF EXISTS {migration_role}")


def test_grant_preflight_fails_clearly_when_migration_user_is_not_object_owner(clean_postgres):
    from incident_atlas.deployment import preflight_and_apply_runtime_grants

    migration_role = "incident_atlas_migration_nogrant_ci"
    runtime_role = "incident_atlas_runtime_nogrant_ci"
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE ROLE {migration_role} LOGIN")
        connection.exec_driver_sql(
            f"CREATE ROLE {runtime_role} LOGIN PASSWORD 'grant-test-password' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        )
        try:
            connection.exec_driver_sql(f"SET ROLE {migration_role}")
            with pytest.raises(RuntimeError, match="cannot apply the required runtime grants"):
                preflight_and_apply_runtime_grants(connection, runtime_role)
        finally:
            connection.exec_driver_sql("RESET ROLE")
            connection.exec_driver_sql(f"DROP ROLE IF EXISTS {runtime_role}")
            connection.exec_driver_sql(f"DROP ROLE IF EXISTS {migration_role}")


def test_public_api_contract_hidden_labels_and_replay_evidence(pg_client, monkeypatch):
    def should_not_call_model(*args, **kwargs):
        raise AssertionError("stored replay must not call the live provider")

    monkeypatch.setattr("incident_atlas.service.run_responses_inference", should_not_call_model)
    with SessionLocal() as db:
        seed_evaluation(db)
        incident = db.get(Incident, "inc-cache-collapse-001")
        snapshot = db.get(EvidenceSnapshot, "snap-inc-cache-collapse-001-1.0.0")
        source_items = [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "service_id": item.service_id,
                "observed_at": item.observed_at,
                "payload": item.payload,
            }
            for item in db.scalars(
                select(SnapshotEvidence).where(SnapshotEvidence.snapshot_id == snapshot.id)
            ).all()
        ]
        from incident_atlas.fixtures import jsonable
        from incident_atlas.service import _build_packet

        packet = _build_packet(
            db, incident, source_items, snapshot.window_start, snapshot.window_end
        )
        packet_text = json.dumps(jsonable(packet))
        for label in (
            "cache_key_version_mismatch",
            "inventory_connection_leak",
            "upstream_payment_gateway_latency",
        ):
            assert label not in packet_text
        assert "expected_primary_label" not in packet_text

    openapi = pg_client.get("/openapi.json").json()
    for route in (
        "/api/v1/incidents",
        "/api/v1/incidents/{incident_id}/timeline",
        "/api/v1/incidents/{incident_id}/dependencies",
        "/api/v1/incidents/{incident_id}/telemetry",
        "/api/v1/incidents/{incident_id}/replay",
        "/api/v1/investigations",
        "/api/v1/replays/{replay_id}/mitigation-approvals",
        "/api/v1/replays/{replay_id}/mitigation-approvals/{mitigation_id}",
        "/api/v1/investigations/{investigation_id}/mitigation-approvals/{mitigation_id}",
    ):
        assert route in openapi["paths"]

    cases = [
        "cache_key_version_mismatch",
        "inventory_connection_leak",
        "upstream_payment_gateway_latency",
    ]
    list_body = pg_client.get("/api/v1/incidents").json()
    detail = pg_client.get("/api/v1/incidents/inc-cache-collapse-001").json()
    assert len(list_body["items"]) == 3
    assert detail["id"] == "inc-cache-collapse-001"
    assert pg_client.get("/healthz").status_code == 200
    assert pg_client.get("/readyz").status_code == 200
    assert pg_client.get("/api/v1/demo-capabilities").json()["live_ai_enabled"] is False
    oversized = pg_client.post("/api/v1/investigations", content=b"x" * 17000)
    assert oversized.status_code == 413
    assert pg_client.get("/api/v1/incidents/inc-cache-collapse-001/timeline").status_code == 200
    assert pg_client.get("/api/v1/incidents/inc-cache-collapse-001/dependencies").status_code == 200
    assert (
        pg_client.get(
            "/api/v1/incidents/inc-cache-collapse-001/telemetry?kind=metrics&limit=20"
        ).status_code
        == 200
    )

    response = pg_client.get("/api/v1/incidents/inc-cache-collapse-001/replay")
    assert response.status_code == 200
    report = response.json()
    assert report["source"] == "stored_replay"
    assert report["model_call_made"] is False
    serialized = json.dumps([list_body, detail, report])
    for label in cases:
        assert label not in serialized
    assert "expected_primary_label" not in serialized

    for hypothesis in report["hypotheses"]:
        for evidence_id in (
            hypothesis["supporting_evidence_ids"] + hypothesis["contradicting_evidence_ids"]
        ):
            evidence = pg_client.get(
                f"/api/v1/snapshots/{report['evidence_snapshot_id']}/evidence/{evidence_id}"
            )
            assert evidence.status_code == 200
            assert evidence.json()["snapshot_sha256"] == report["evidence_snapshot_sha256"]
    for rule in report["rules_baseline"]["fired_rules"]:
        for evidence_id in rule["evidence_ids"]:
            evidence = pg_client.get(
                f"/api/v1/snapshots/{report['evidence_snapshot_id']}/evidence/{evidence_id}"
            )
            assert evidence.status_code == 200


def test_query_window_is_bounded_when_only_one_boundary_is_given(pg_client):
    response = pg_client.get(
        "/api/v1/incidents/inc-cache-collapse-001/timeline?from=2026-01-01T00:00:00Z"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "time_range_too_large"


def test_query_limit_validation_and_cors_allowlist(pg_client):
    invalid_limit = pg_client.get(
        "/api/v1/incidents/inc-cache-collapse-001/telemetry?kind=metrics&limit=201"
    )
    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["code"] == "validation_error"

    allowed = pg_client.options(
        "/api/v1/replays/replay-cache-v1/mitigation-approvals",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-incident-atlas-visitor-id",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-incident-atlas-visitor-id" in allowed.headers[
        "access-control-allow-headers"
    ].lower()
    denied = pg_client.options(
        "/api/v1/replays/replay-cache-v1/mitigation-approvals",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in denied.headers


def test_guest_live_rate_limit_returns_stable_error(pg_client):
    from incident_atlas.config import Settings
    from incident_atlas.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=os.environ["DATABASE_URL"],
        rate_limit_enabled=True,
        rate_live_runs=1,
        rate_live_window_seconds=900,
        openai_api_key=None,
        live_analysis_enabled=False,
    )
    with SessionLocal() as db:
        db.add(
            GuestRateEvent(
                subject_hash="a" * 64,
                action="live",
                occurred_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        db.commit()
    body = {"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15}
    first = pg_client.post(
        "/api/v1/investigations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    second = pg_client.post(
        "/api/v1/investigations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert first.status_code == 503
    assert second.status_code == 429
    assert second.json()["code"] == "rate_limited"
    with SessionLocal() as db:
        events = db.scalars(select(GuestRateEvent)).all()
        assert len(events) == 1
        assert {event.action for event in events} == {"live"}
        assert all(len(event.subject_hash) == 64 for event in events)


def test_rate_event_retention_cleanup_is_indexed_and_window_safe(pg_client):
    with SessionLocal() as db:
        db.add(
            GuestRateEvent(
                subject_hash="b" * 64,
                action="live",
                occurred_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        db.add(
            GuestRateEvent(
                subject_hash="d" * 64,
                action="live",
                occurred_at=datetime.now(UTC) - timedelta(days=6),
            )
        )
        db.commit()
    # The live rate test below triggers cleanup before checking the current window.
    from incident_atlas.config import Settings
    from incident_atlas.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=os.environ["DATABASE_URL"],
        rate_limit_enabled=True,
        rate_live_runs=10,
        rate_live_window_seconds=900,
        rate_approval_window_seconds=3600,
        openai_api_key=None,
        live_analysis_enabled=False,
    )
    pg_client.post(
        "/api/v1/investigations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15},
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GuestRateEvent)) == 2


def test_global_live_request_cap_survives_rotating_client_addresses(pg_client, monkeypatch):
    from fastapi.testclient import TestClient

    from incident_atlas.config import Settings
    from incident_atlas.main import app

    provider_calls = []

    def provider(*args, **kwargs):
        provider_calls.append(True)
        return _provider_result()

    monkeypatch.setattr("incident_atlas.service.run_responses_inference", provider)
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=os.environ["DATABASE_URL"],
        openai_api_key="test-provider-key",
        live_analysis_enabled=True,
        rate_limit_enabled=True,
        rate_live_runs=20,
        rate_live_global_runs=1,
        rate_live_global_window_seconds=3600,
    )
    body = {"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15}
    with (
        TestClient(app, client=("203.0.113.10", 51234)) as first_visitor,
        TestClient(app, client=("203.0.113.11", 51234)) as second_visitor,
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda visitor: visitor.post(
                        "/api/v1/investigations",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json=body,
                    ),
                    [first_visitor, second_visitor],
                )
            )

    assert sorted(response.status_code for response in responses) == [201, 429]
    blocked = next(response for response in responses if response.status_code == 429)
    assert blocked.json()["code"] == "live_global_limit_reached"
    assert len(provider_calls) == 1
    with SessionLocal() as db:
        global_events = db.scalars(
            select(GuestRateEvent).where(GuestRateEvent.action == "live_global")
        ).all()
        assert len(global_events) == 1


def test_public_replay_reads_do_not_append_unbounded_audit_events(pg_client):
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditEvent))

    for _ in range(25):
        by_id = pg_client.get("/api/v1/replays/replay-cache-v1")
        by_incident = pg_client.get("/api/v1/incidents/inc-cache-collapse-001/replay")
        assert by_id.status_code == 200
        assert by_incident.status_code == 200

    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(AuditEvent))
    assert after == before


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ProviderTimeout("test"), 504, "investigation_timeout"),
        (ProviderRefusal("test"), 422, "provider_refused"),
        (ProviderInvalidOutput("test"), 502, "invalid_model_output"),
    ],
)
def test_live_failure_paths_are_explicit(pg_client, monkeypatch, error, status, code):
    response = _run_live(pg_client, monkeypatch, error=error)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert "diagnosis" not in response.text.lower() or status == 502
    with SessionLocal() as db:
        run = db.scalar(select(Investigation).order_by(Investigation.started_at.desc()))
        assert run is not None
        assert run.status in {"timed_out", "refused", "invalid_output"}
        assert run.completed_at is not None


def test_unknown_live_evidence_id_is_rejected(pg_client, monkeypatch):
    with SessionLocal() as db:
        seeded_hypothesis_count = db.scalar(select(func.count()).select_from(Hypothesis))
    response = _run_live(pg_client, monkeypatch, result=_provider_result("ev-not-in-snapshot"))
    assert response.status_code == 502
    assert response.json()["code"] == "invalid_model_output"
    with SessionLocal() as db:
        run = db.scalar(select(Investigation).order_by(Investigation.started_at.desc()))
        assert run.status == "invalid_output"
        # The rejection must not persist model hypotheses; the three fixture
        # replay hypotheses seeded for this test remain unchanged.
        assert db.scalar(select(func.count()).select_from(Hypothesis)) == seeded_hypothesis_count


def test_live_success_persists_trace_provenance_and_snapshot_links(pg_client, monkeypatch):
    response = _run_live(pg_client, monkeypatch, result=_provider_result())
    assert response.status_code == 201
    report = response.json()
    assert report["source"] == "live_ai"
    assert report["model_call_made"] is True
    assert report["schema_version"] == "investigation-report-v2"
    assert report["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert report["evidence_snapshot_sha256"]
    evidence_id = report["hypotheses"][0]["supporting_evidence_ids"][0]
    assert (
        pg_client.get(
            f"/api/v1/snapshots/{report['evidence_snapshot_id']}/evidence/{evidence_id}"
        ).status_code
        == 200
    )


def test_synthetic_live_report_deep_link_is_readable_across_visitors(pg_client, monkeypatch):
    from fastapi.testclient import TestClient

    from incident_atlas.main import app

    created = _run_live(pg_client, monkeypatch)
    assert created.status_code == 201
    report_id = created.json()["id"]

    # Live reports only use public synthetic fixtures, and deep links intentionally need no
    # visitor session. This test documents the sharing boundary; it is not private user data.
    with TestClient(app, client=("203.0.113.19", 51234)) as another_visitor:
        response = another_visitor.get(f"/api/v1/investigations/{report_id}")

    assert response.status_code == 200
    report = response.json()
    assert report["source"] == "live_ai"
    assert report["model_call_made"] is True
    assert "expected_primary_label" not in json.dumps(report)


def test_replay_and_live_approvals_are_acknowledged_simulations(pg_client, monkeypatch):
    replay_report = pg_client.get("/api/v1/replays/replay-cache-v1").json()
    hypothesis = replay_report["hypotheses"][0]
    rejected = pg_client.post(
        f"/api/v1/replays/{replay_report['id']}/mitigation-approvals",
        json={
            "hypothesis_id": hypothesis["id"],
            "mitigation_id": hypothesis["mitigation"]["id"],
            "simulation_acknowledged": False,
        },
    )
    assert rejected.status_code == 422

    replay_approval = pg_client.post(
        f"/api/v1/replays/{replay_report['id']}/mitigation-approvals",
        json={
            "hypothesis_id": hypothesis["id"],
            "mitigation_id": hypothesis["mitigation"]["id"],
            "simulation_acknowledged": True,
        },
    )
    assert replay_approval.status_code == 201
    assert replay_approval.json()["simulation_only"] is True
    assert replay_approval.json()["external_action_performed"] is False
    replay_duplicate = pg_client.post(
        f"/api/v1/replays/{replay_report['id']}/mitigation-approvals",
        json={
            "hypothesis_id": hypothesis["id"],
            "mitigation_id": hypothesis["mitigation"]["id"],
            "simulation_acknowledged": True,
        },
    )
    assert replay_duplicate.status_code == 409

    live = _run_live(pg_client, monkeypatch)
    live_hypothesis = live.json()["hypotheses"][0]
    live_approval = pg_client.post(
        f"/api/v1/investigations/{live.json()['id']}/mitigation-approvals",
        json={
            "hypothesis_id": live_hypothesis["id"],
            "mitigation_id": live_hypothesis["mitigation"]["id"],
            "simulation_acknowledged": True,
        },
    )
    assert live_approval.status_code == 201
    with SessionLocal() as db:
        approvals = db.scalars(select(SimulationApproval)).all()
        assert len(approvals) == 2
        assert all(
            item.simulation_only and not item.external_action_performed for item in approvals
        )
        rate_actions = db.scalars(select(GuestRateEvent.action)).all()
        assert sorted(rate_actions) == ["approval", "live", "live_global"]


def test_replay_approval_is_deduplicated_per_visitor(pg_client):
    from fastapi.testclient import TestClient

    from incident_atlas.main import app

    report = pg_client.get("/api/v1/replays/replay-cache-v1").json()
    hypothesis = report["hypotheses"][0]
    body = {
        "hypothesis_id": hypothesis["id"],
        "mitigation_id": hypothesis["mitigation"]["id"],
        "simulation_acknowledged": True,
    }
    first_visitor = {"X-Incident-Atlas-Visitor-ID": "68d6fe47-b586-4c94-9ed8-7a401a1b4cf1"}
    second_visitor = {"X-Incident-Atlas-Visitor-ID": "e70e2e8d-2ed3-4e88-9ce2-0fef841c9baa"}
    with (
        TestClient(app, client=("203.0.113.17", 51234)) as first_browser,
        TestClient(app, client=("203.0.113.17", 51235)) as second_browser,
    ):
        first = first_browser.post(
            f"/api/v1/replays/{report['id']}/mitigation-approvals",
            json=body,
            headers=first_visitor,
        )
        duplicate = first_browser.post(
            f"/api/v1/replays/{report['id']}/mitigation-approvals",
            json=body,
            headers=first_visitor,
        )
        second = second_browser.post(
            f"/api/v1/replays/{report['id']}/mitigation-approvals",
            json=body,
            headers=second_visitor,
        )
        # A reload sends the same browser ID and restores that browser's saved result.
        restored = first_browser.get(
            f"/api/v1/replays/{report['id']}/mitigation-approvals/{hypothesis['mitigation']['id']}",
            headers=first_visitor,
        )
        unknown_browser = first_browser.get(
            f"/api/v1/replays/{report['id']}/mitigation-approvals/{hypothesis['mitigation']['id']}",
            headers={"X-Incident-Atlas-Visitor-ID": "ba59f2a5-4853-4e4d-b22c-3937b36fc790"},
        )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert second.status_code == 201
    assert second.json()["simulation_only"] is True
    assert second.json()["external_action_performed"] is False
    assert first.json()["id"] != second.json()["id"]

    assert restored.status_code == 200
    assert restored.json()["id"] == first.json()["id"]
    assert unknown_browser.status_code == 404
    assert unknown_browser.json()["code"] == "approval_not_found"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SimulationApproval)) == 2
        approval_id = db.scalar(
            select(SimulationApproval.id).order_by(SimulationApproval.id).limit(1)
        )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE simulation_approvals SET status = status WHERE id = :id"),
                {"id": approval_id},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM simulation_approvals WHERE id = :id"), {"id": approval_id}
            )


def test_completed_live_idempotency_key_reuses_report_with_ok_status(pg_client, monkeypatch):
    from incident_atlas.main import app

    app.dependency_overrides[get_settings] = _live_settings
    provider_calls = 0

    def provider(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return _provider_result()

    monkeypatch.setattr("incident_atlas.service.run_responses_inference", provider)
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key}
    body = {"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15}
    first = pg_client.post("/api/v1/investigations", headers=headers, json=body)
    repeated = pg_client.post("/api/v1/investigations", headers=headers, json=body)
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert first.json()["id"] == repeated.json()["id"]
    assert provider_calls == 1


def test_concurrent_live_idempotency_returns_in_progress_then_reuses(pg_client, monkeypatch):
    from incident_atlas.main import app

    app.dependency_overrides[get_settings] = _live_settings
    provider_entered = Event()
    provider_release = Event()
    provider_calls = 0

    def blocked_provider(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        provider_entered.set()
        if not provider_release.wait(timeout=5):
            raise TimeoutError("test provider release timed out")
        return _provider_result()

    monkeypatch.setattr("incident_atlas.service.run_responses_inference", blocked_provider)
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key}
    body = {"incident_id": "inc-cache-collapse-001", "evidence_window_minutes": 15}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(
            pg_client.post, "/api/v1/investigations", headers=headers, json=body
        )
        assert provider_entered.wait(timeout=5)
        concurrent = pg_client.post("/api/v1/investigations", headers=headers, json=body)
        assert concurrent.status_code == 409
        assert concurrent.json()["code"] == "investigation_in_progress"
        provider_release.set()
        first = first_future.result(timeout=10)
    repeated = pg_client.post("/api/v1/investigations", headers=headers, json=body)
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert first.json()["id"] == repeated.json()["id"]
    assert provider_calls == 1
