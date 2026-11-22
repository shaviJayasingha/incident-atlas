"""Explicit database bootstrap and least-privilege production role setup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from incident_atlas.config import Settings, get_settings
from incident_atlas.database_urls import migration_database_url
from incident_atlas.fixtures import seed_runtime

API_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROLE = "incident_atlas_runtime"


def _upgrade(database_url: str) -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _provision_role(connection: Connection, password: str, role_name: str) -> None:
    raw_connection = connection.connection.driver_connection
    present = connection.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": role_name}
    ).scalar()
    role_id = sql.Identifier(role_name)
    password_literal = sql.Literal(password)
    if present:
        statement = sql.SQL(
            "ALTER ROLE {} WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(role_id, password_literal)
    else:
        statement = sql.SQL(
            "CREATE ROLE {} WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(role_id, password_literal)
    raw_connection.execute(statement)


def apply_runtime_grants(
    connection: Connection, role_name: str = RUNTIME_ROLE
) -> None:
    raw_connection = connection.connection.driver_connection
    role = sql.Identifier(role_name)
    owner_name = connection.execute(text("SELECT current_user")).scalar_one()
    owner = sql.Identifier(owner_name)

    raw_connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    raw_connection.execute(sql.SQL("REVOKE ALL ON SCHEMA evaluation FROM PUBLIC"))
    raw_connection.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM PUBLIC"))
    raw_connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA evaluation FROM PUBLIC"))

    raw_connection.execute(sql.SQL("REVOKE ALL ON SCHEMA evaluation FROM {} ").format(role))
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM {} ").format(role)
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA evaluation FROM {} ").format(role)
    )
    raw_connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {} ").format(role))
    raw_connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {} ").format(role))
    raw_connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON ALL TABLES IN SCHEMA public TO {} "
        ).format(role)
    )
    raw_connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {} ").format(role)
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON TABLE public.alembic_version FROM {} ").format(role)
    )
    raw_connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(owner, role)
    )
    raw_connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(owner, role)
    )


def _seed_with_engine(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            return seed_runtime(db)
    finally:
        engine.dispose()


def bootstrap_local_database(settings: Settings | None = None) -> dict[str, object]:
    """Migrate and seed a local database (where one owner role is acceptable)."""
    cfg = settings or get_settings()
    url = migration_database_url(cfg.database_url, cfg.migration_database_url)
    _upgrade(url)
    return _seed_with_engine(url)


def bootstrap_deployment_database(settings: Settings | None = None) -> dict[str, object]:
    """Migrate/seed as the deploy role, then grant the API its limited runtime role."""
    cfg = settings or get_settings()
    if not cfg.migration_database_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for production bootstrap")
    if not cfg.runtime_db_password or not cfg.runtime_db_password.get_secret_value():
        raise RuntimeError("RUNTIME_DB_PASSWORD is required for production bootstrap")

    deploy_url = migration_database_url(cfg.database_url, cfg.migration_database_url)
    admin_engine = create_engine(deploy_url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            _provision_role(
                connection,
                cfg.runtime_db_password.get_secret_value(),
                RUNTIME_ROLE,
            )
        _upgrade(deploy_url)
        with Session(admin_engine) as db:
            manifest = seed_runtime(db)
        with admin_engine.begin() as connection:
            apply_runtime_grants(connection, RUNTIME_ROLE)
        return manifest
    finally:
        admin_engine.dispose()
