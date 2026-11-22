import json
import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from incident_atlas.config import Settings, get_settings
from incident_atlas.db import SessionLocal, engine
from incident_atlas.errors import ProviderInvalidOutput, ProviderRefusal, ProviderTimeout
from incident_atlas.fixtures import seed_evaluation, seed_runtime
from incident_atlas.models import (
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
        rate_limit_enabled=False,
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
    assert report["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert report["evidence_snapshot_sha256"]
    evidence_id = report["hypotheses"][0]["supporting_evidence_ids"][0]
    assert (
        pg_client.get(
            f"/api/v1/snapshots/{report['evidence_snapshot_id']}/evidence/{evidence_id}"
        ).status_code
        == 200
    )


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
        assert db.scalar(select(func.count()).select_from(GuestRateEvent)) == 0
