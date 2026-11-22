import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from incident_atlas.config import Settings
from incident_atlas.database_urls import migration_database_url, runtime_database_url


def test_cors_origins_accept_json_and_comma_separated_environment_values(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://demo.example, https://preview.example")
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == [
        "https://demo.example",
        "https://preview.example",
    ]

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://demo.example"]')
    assert Settings(_env_file=None).cors_allowed_origins == ["https://demo.example"]


def test_render_postgres_urls_use_psycopg_for_api_and_alembic():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://runtime:runtime-pass@db.internal:5432/incident_atlas",
        migration_database_url=(
            "postgresql://migrator:migrate-pass@db.internal:5432/incident_atlas"
        ),
    )

    runtime = runtime_database_url(settings.database_url)
    migration = migration_database_url(settings.database_url, settings.migration_database_url)
    assert make_url(runtime).drivername == "postgresql+psycopg"
    assert make_url(migration).drivername == "postgresql+psycopg"

    app_engine = create_engine(runtime)
    migration_engine = create_engine(migration)
    try:
        assert app_engine.dialect.driver == "psycopg"
        assert migration_engine.dialect.driver == "psycopg"
    finally:
        app_engine.dispose()
        migration_engine.dispose()


def test_production_live_ai_requires_manual_provider_and_proxy_verification():
    base = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://incident_atlas_runtime:pass@db.example/incident_atlas",
        "rate_limit_hmac_key": "production-rate-limit-secret",
        "cors_allowed_origins": ["https://incident-atlas.example"],
        "public_site_origin": "https://incident-atlas.example",
        "live_analysis_enabled": True,
        "openai_api_key": "server-side-test-key",
    }
    assert Settings(**base).live_enabled is False
    assert Settings(**base, live_provider_verified=True).live_enabled is False
    configured = Settings(
        **base,
        live_provider_verified=True,
        trusted_proxy_cidrs=["198.51.100.0/24"],
    )
    assert configured.live_enabled is True


def test_production_rejects_plaintext_model_transport():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(
            environment="production",
            rate_limit_hmac_key="a-long-non-default-secret",
            database_url="postgresql+psycopg://incident_atlas_runtime@db.example/incident_atlas",
            openai_base_url="http://model.example/v1",
            cors_allowed_origins=["https://incident-atlas.example"],
            public_site_origin="https://incident-atlas.example",
        )


def test_model_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        Settings(openai_base_url="https://user:password@model.example/v1")


@pytest.mark.parametrize(
    "origin",
    ["*", "http://demo.example", "https://demo.example/path", "https://user@demo.example"],
)
def test_production_rejects_non_exact_or_insecure_cors_origins(origin):
    with pytest.raises(ValueError, match="exact HTTPS origin"):
        Settings(
            environment="production",
            rate_limit_hmac_key="a-long-non-default-secret",
            database_url="postgresql+psycopg://incident_atlas_runtime@db.example/incident_atlas",
            cors_allowed_origins=[origin],
            public_site_origin=origin,
        )


def test_production_cors_must_match_the_site_origin_and_runtime_role():
    base = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://incident_atlas_runtime:pass@db.example/incident_atlas",
        "rate_limit_hmac_key": "production-rate-limit-secret",
        "cors_allowed_origins": ["https://incident-atlas.example"],
        "public_site_origin": "https://incident-atlas.example",
    }
    with pytest.raises(ValueError, match="exactly match"):
        Settings(**{**base, "cors_allowed_origins": ["https://other.example"]})
    with pytest.raises(ValueError, match="limited incident_atlas_runtime role"):
        Settings(
            **{**base, "database_url": "postgresql://owner:pass@db.example/incident_atlas"}
        )


def test_production_rejects_wildcard_trusted_proxy_cidr():
    with pytest.raises(ValueError, match="cannot trust every address"):
        Settings(
            environment="production",
            rate_limit_hmac_key="a-long-non-default-secret",
            database_url="postgresql://incident_atlas_runtime@db.example/incident_atlas",
            cors_allowed_origins=["https://demo.example"],
            public_site_origin="https://demo.example",
            trusted_proxy_cidrs=["0.0.0.0/0"],
        )
