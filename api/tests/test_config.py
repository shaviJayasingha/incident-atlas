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
