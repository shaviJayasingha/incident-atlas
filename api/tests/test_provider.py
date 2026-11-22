import json

import httpx
import pytest

from incident_atlas.config import Settings
from incident_atlas.errors import (
    ProviderInvalidOutput,
    ProviderRefusal,
    ProviderTimeout,
    ProviderUnavailable,
)
from incident_atlas.provider import run_responses_inference


def _response(text: str, *, status: str = "completed") -> dict[str, object]:
    return {
        "id": "resp_test_001",
        "status": status,
        "output": [
            {"content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 15, "output_tokens": 21},
    }


def test_responses_call_is_single_bounded_structured_request(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return _response(json.dumps({"uncertainty": "Limited fixture.", "hypotheses": []}))

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("incident_atlas.provider.httpx.post", fake_post)
    settings = Settings(openai_api_key="test-secret", live_analysis_enabled=True)
    result = run_responses_inference(settings, {"evidence": []})

    assert result.draft.hypotheses == []
    assert result.input_tokens == 15
    assert captured["url"].endswith("/responses")
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["strict"] is True
    assert "tools" not in captured["json"]


def test_provider_refusal_is_explicit(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "completed",
                "output": [{"content": [{"type": "refusal", "refusal": "declined"}]}],
            }

    monkeypatch.setattr(
        "incident_atlas.provider.httpx.post", lambda *args, **kwargs: FakeResponse()
    )
    with pytest.raises(ProviderRefusal):
        run_responses_inference(Settings(openai_api_key="test-secret"), {})


def test_incomplete_provider_output_is_explicit(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return _response("{}", status="incomplete")

    monkeypatch.setattr(
        "incident_atlas.provider.httpx.post", lambda *args, **kwargs: FakeResponse()
    )
    with pytest.raises(ProviderInvalidOutput):
        run_responses_inference(Settings(openai_api_key="test-secret"), {})


def test_malformed_structured_output_is_explicit(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return _response('{"unexpected":"shape"}')

    monkeypatch.setattr(
        "incident_atlas.provider.httpx.post", lambda *args, **kwargs: FakeResponse()
    )
    with pytest.raises(ProviderInvalidOutput):
        run_responses_inference(Settings(openai_api_key="test-secret"), {})


def test_http_timeout_is_explicit(monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("test")

    monkeypatch.setattr("incident_atlas.provider.httpx.post", timeout)
    with pytest.raises(ProviderTimeout):
        run_responses_inference(Settings(openai_api_key="test-secret"), {})


def test_provider_unavailable_response_is_explicit(monkeypatch):
    class FakeResponse:
        status_code = 503

    monkeypatch.setattr(
        "incident_atlas.provider.httpx.post", lambda *args, **kwargs: FakeResponse()
    )
    with pytest.raises(ProviderUnavailable):
        run_responses_inference(Settings(openai_api_key="test-secret"), {})
