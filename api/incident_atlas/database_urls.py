"""PostgreSQL URL normalization shared by the API and Alembic."""


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
