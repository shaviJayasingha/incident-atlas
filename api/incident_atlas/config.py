import json
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", enable_decoding=False
    )

    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://incident_atlas:incident_atlas@localhost:5432/incident_atlas"
    )
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6.1-terra"
    openai_base_url: str = "https://api.openai.com/v1"
    live_analysis_enabled: bool = False
    cors_allowed_origins: list[str] = ["http://localhost:5173"]
    rate_limit_hmac_key: SecretStr = SecretStr("replace-this-local-development-value")
    rate_limit_enabled: bool = True
    rate_live_runs: int = Field(default=5, ge=1, le=100)
    rate_live_window_seconds: int = Field(default=900, ge=60, le=86_400)
    rate_approvals: int = Field(default=10, ge=1, le=200)
    rate_approval_window_seconds: int = Field(default=3600, ge=60, le=86_400)
    max_evidence_window_minutes: int = Field(default=15, ge=5, le=15)
    max_rows_per_signal: int = Field(default=500, ge=1, le=5000)
    max_request_bytes: int = Field(default=16_384, ge=1024, le=65_536)
    max_live_inflight: int = Field(default=3, ge=1, le=32)
    database_query_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    model_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    model_read_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    investigation_deadline_seconds: float = Field(default=18.0, gt=0, le=90)
    otel_exporter_otlp_endpoint: str | None = None
    log_level: str = "INFO"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "CORS_ALLOWED_ORIGINS must be a JSON list or comma list"
                    ) from exc
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @field_validator("openai_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def production_secrets_are_safe(self) -> "Settings":
        if self.environment.lower() in {"production", "prod"}:
            if (
                self.rate_limit_hmac_key.get_secret_value()
                == "replace-this-local-development-value"
            ):
                raise ValueError("RATE_LIMIT_HMAC_KEY must be set outside development")
            if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
                raise ValueError("DATABASE_URL must point to a production database")
        return self

    @property
    def live_enabled(self) -> bool:
        return self.live_analysis_enabled and bool(
            self.openai_api_key and self.openai_api_key.get_secret_value().strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
