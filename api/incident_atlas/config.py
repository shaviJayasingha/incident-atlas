import ipaddress
import json
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from incident_atlas.database_urls import normalize_postgres_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", enable_decoding=False
    )

    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://incident_atlas:incident_atlas@localhost:5432/incident_atlas"
    )
    migration_database_url: str | None = None
    runtime_db_password: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6.1-terra"
    openai_base_url: str = "https://api.openai.com/v1"
    live_analysis_enabled: bool = False
    live_provider_verified: bool = False
    cors_allowed_origins: list[str] = ["http://localhost:5173"]
    public_site_origin: str | None = None
    trusted_proxy_cidrs: list[str] = []
    rate_limit_hmac_key: SecretStr = SecretStr("replace-this-local-development-value")
    rate_limit_enabled: bool = True
    rate_live_runs: int = Field(default=5, ge=1, le=100)
    rate_live_window_seconds: int = Field(default=900, ge=60, le=86_400)
    rate_live_global_runs: int = Field(default=5, ge=1, le=100)
    rate_live_global_window_seconds: int = Field(default=86_400, ge=60, le=604_800)
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

    @field_validator("database_url", "migration_database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("database URLs must be strings")
        return normalize_postgres_url(value)

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def split_trusted_proxy_cidrs(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "TRUSTED_PROXY_CIDRS must be a JSON list or comma list"
                    ) from exc
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("openai_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("OPENAI_BASE_URL must be an absolute URL without embedded credentials")
        return normalized

    @model_validator(mode="after")
    def production_secrets_are_safe(self) -> "Settings":
        for cidr in self.trusted_proxy_cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError("TRUSTED_PROXY_CIDRS must contain valid IP networks") from exc
            if network.prefixlen == 0:
                raise ValueError("TRUSTED_PROXY_CIDRS cannot trust every address")
        if self.environment.lower() in {"production", "prod"}:
            if (
                self.rate_limit_hmac_key.get_secret_value()
                == "replace-this-local-development-value"
            ):
                raise ValueError("RATE_LIMIT_HMAC_KEY must be set outside development")
            if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
                raise ValueError("DATABASE_URL must point to a production database")
            if urlsplit(self.openai_base_url).scheme.lower() != "https":
                raise ValueError("OPENAI_BASE_URL must be an HTTPS URL in production")
            if not self.cors_allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must include the public HTTPS site origin")
            if not self.public_site_origin:
                raise ValueError("PUBLIC_SITE_ORIGIN must be the exact public HTTPS site origin")
            if self.cors_allowed_origins != [self.public_site_origin]:
                raise ValueError("CORS_ALLOWED_ORIGINS must exactly match PUBLIC_SITE_ORIGIN")
            parsed_site = urlsplit(self.public_site_origin)
            if (
                parsed_site.scheme != "https"
                or not parsed_site.hostname
                or parsed_site.path
                or parsed_site.query
                or parsed_site.fragment
                or parsed_site.username
                or parsed_site.password
            ):
                raise ValueError("PUBLIC_SITE_ORIGIN must be an exact HTTPS origin")
            runtime_username = urlsplit(self.database_url).username
            if runtime_username != "incident_atlas_runtime":
                raise ValueError("DATABASE_URL must use the limited incident_atlas_runtime role")
            if self.live_analysis_enabled and self.rate_live_global_runs < 1:
                raise ValueError("A global live request cap is required before enabling live AI")
            for origin in self.cors_allowed_origins:
                parsed_origin = urlsplit(origin)
                if (
                    origin == "*"
                    or parsed_origin.scheme.lower() != "https"
                    or not parsed_origin.hostname
                    or parsed_origin.username
                    or parsed_origin.password
                    or parsed_origin.path not in {"", "/"}
                    or parsed_origin.query
                    or parsed_origin.fragment
                ):
                    raise ValueError("CORS_ALLOWED_ORIGINS must contain exact HTTPS origins")
        return self

    @property
    def live_enabled(self) -> bool:
        configured = self.live_analysis_enabled and self.rate_limit_enabled and bool(
            self.openai_api_key and self.openai_api_key.get_secret_value().strip()
        )
        if not configured:
            return False
        if self.environment.lower() in {"production", "prod"}:
            return self.live_provider_verified and bool(self.trusted_proxy_cidrs)
        return True


@lru_cache
def get_settings() -> Settings:
    return Settings()
