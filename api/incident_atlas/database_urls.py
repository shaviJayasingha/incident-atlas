"""PostgreSQL URL normalization and deployment credential checks."""

from sqlalchemy.engine import make_url


def normalize_postgres_url(value: str) -> str:
    """Select psycopg 3 explicitly for Render and libpq-style PostgreSQL URLs."""
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def runtime_database_url(database_url: str) -> str:
    return normalize_postgres_url(database_url)


def migration_database_url(database_url: str, migration_url: str | None) -> str:
    return normalize_postgres_url(migration_url or database_url)


def validate_runtime_credentials(
    database_url: str, migration_url: str, runtime_password: str | None
) -> None:
    """Fail closed on mismatched Render runtime URL/password configuration.

    SQLAlchemy decodes percent-escaped URL passwords before this comparison. Error
    messages intentionally never include either URL or password.
    """
    if not runtime_password:
        raise ValueError("RUNTIME_DB_PASSWORD must be configured for deployment bootstrap")
    try:
        runtime = make_url(normalize_postgres_url(database_url))
        migration = make_url(normalize_postgres_url(migration_url))
    except Exception:
        raise ValueError(
            "DATABASE_URL and MIGRATION_DATABASE_URL must be valid PostgreSQL URLs"
        ) from None

    if runtime.drivername != "postgresql+psycopg" or migration.drivername != "postgresql+psycopg":
        raise ValueError("Deployment database URLs must use the psycopg PostgreSQL driver")
    if runtime.username != "incident_atlas_runtime":
        raise ValueError("DATABASE_URL must use the incident_atlas_runtime role")
    if runtime.password != runtime_password:
        raise ValueError("DATABASE_URL password must match RUNTIME_DB_PASSWORD")
    if (
        runtime.host != migration.host
        or runtime.port != migration.port
        or runtime.database != migration.database
    ):
        raise ValueError("Runtime and migration URLs must target the same PostgreSQL database")
