import pytest

from incident_atlas.config import Settings


def test_cors_origins_accept_json_and_comma_separated_environment_values(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://demo.example, https://preview.example")
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == [
        "https://demo.example",
        "https://preview.example",
    ]

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://demo.example"]')
    assert Settings(_env_file=None).cors_allowed_origins == ["https://demo.example"]


def test_production_rejects_plaintext_model_transport():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(
            environment="production",
            rate_limit_hmac_key="a-long-non-default-secret",
            database_url="postgresql+psycopg://db.example/incident_atlas",
            openai_base_url="http://model.example/v1",
        )


def test_model_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        Settings(openai_base_url="https://user:password@model.example/v1")


@pytest.mark.parametrize(
    "origin",
    ["*", "http://demo.example", "https://demo.example/path", "https://user@demo.example"],
)
def test_production_rejects_non_exact_or_insecure_cors_origins(origin):
    with pytest.raises(ValueError, match="exact HTTPS origins"):
        Settings(
            environment="production",
            rate_limit_hmac_key="a-long-non-default-secret",
            database_url="postgresql+psycopg://db.example/incident_atlas",
            cors_allowed_origins=[origin],
        )
