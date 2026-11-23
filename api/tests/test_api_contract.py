from fastapi.testclient import TestClient

from incident_atlas.main import app


def test_openapi_exposes_typed_backend_contracts():
    schema = app.openapi()
    assert len(schema["paths"]) == 16
    assert "SnapshotMetadata" in schema["components"]["schemas"]
    assert "/api/v1/incidents/{incident_id}/timeline" in schema["paths"]
    assert "/api/v1/investigations/{investigation_id}/mitigation-approvals" in schema["paths"]
    assert "/api/v1/replays/{replay_id}/mitigation-approvals/{mitigation_id}" in schema["paths"]
    assert (
        "/api/v1/investigations/{investigation_id}/mitigation-approvals/{mitigation_id}"
        in schema["paths"]
    )
    error = schema["paths"]["/api/v1/incidents/{incident_id}/timeline"]["get"]["responses"]["422"]
    assert "application/problem+json" in error["content"]
    assert "code" in error["content"]["application/problem+json"]["schema"]["properties"]


def test_public_capability_and_error_contracts_work_without_database_access():
    with TestClient(app) as client:
        capabilities = client.get("/api/v1/demo-capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["stored_replay_available"] is True
        assert capabilities.json()["live_ai_enabled"] is False
        assert capabilities.headers["x-request-id"].startswith("req_")

        missing_route = client.get("/missing")
        assert missing_route.status_code == 404
        assert missing_route.headers["content-type"].startswith("application/problem+json")
        assert missing_route.json()["code"] == "not_found"

        oversized = client.post("/api/v1/investigations", content=b"x" * 17_000)
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "request_too_large"
