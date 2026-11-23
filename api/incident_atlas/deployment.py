"""Explicit database bootstrap and least-privilege production role setup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from incident_atlas.config import Settings, get_settings
from incident_atlas.database_urls import migration_database_url, validate_runtime_credentials
from incident_atlas.fixtures import seed_runtime

API_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROLE = "incident_atlas_runtime"


def _upgrade(database_url: str) -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _provision_role(connection: Connection, password: str, role_name: str) -> None:
    raw_connection = connection.connection.driver_connection
    existing = connection.execute(
        text(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls FROM pg_roles WHERE rolname = :name"
        ),
        {"name": role_name},
    ).one_or_none()
    role_id = sql.Identifier(role_name)
    if existing:
        if (
            not existing.rolcanlogin
            or existing.rolsuper
            or existing.rolcreatedb
            or existing.rolcreaterole
            or existing.rolreplication
            or existing.rolbypassrls
        ):
            raise RuntimeError(
                "The existing runtime database role has unsafe PostgreSQL attributes."
            )
        role_oid = connection.execute(
            text("SELECT oid FROM pg_roles WHERE rolname = :name"), {"name": role_name}
        ).scalar_one()
        membership = connection.execute(
            text("SELECT 1 FROM pg_auth_members WHERE member = :oid LIMIT 1"),
            {"oid": role_oid},
        ).first()
        ownership = connection.execute(
            text(
                "SELECT 1 FROM pg_database WHERE datname = current_database() "
                "AND datdba = :oid "
                "UNION ALL "
                "SELECT 1 FROM pg_namespace WHERE nspname IN ('public', 'evaluation') "
                "AND nspowner = :oid "
                "UNION ALL "
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname IN ('public', 'evaluation') AND c.relowner = :oid LIMIT 1"
            ),
            {"oid": role_oid},
        ).first()
        if membership or ownership:
            raise RuntimeError(
                "The existing runtime database role inherits elevated access or owns database "
                "objects. Use a dedicated non-owner runtime credential."
            )
        # Render-managed credentials are owned by Render. Do not alter their
        # password or role attributes; validate the configured login separately.
        return

    creator = connection.execute(
        text("SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user")
    ).one()
    if not (creator.rolsuper or creator.rolcreaterole):
        raise RuntimeError(
            "The migration user cannot create the runtime role. Create a restricted "
            "incident_atlas_runtime credential in Render, then rerun bootstrap."
        )
    statement = sql.SQL(
        "CREATE ROLE {} WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOREPLICATION NOBYPASSRLS PASSWORD {}"
    ).format(role_id, sql.Literal(password))
    try:
        raw_connection.execute(statement)
    except Exception:
        raise RuntimeError(
            "PostgreSQL rejected runtime-role creation. Check migration-user CREATEROLE "
            "privileges or create the restricted credential in Render."
        ) from None


def _preflight_migration_permissions(connection: Connection) -> None:
    """Check prerequisites before migrations and grants mutate the database."""
    permissions = connection.execute(
        text(
            "SELECT has_database_privilege(current_user, current_database(), 'CREATE') "
            "AS can_create_schema, "
            "has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_public_objects"
        )
    ).one()
    if not permissions.can_create_schema or not permissions.can_create_public_objects:
        raise RuntimeError(
            "The migration user lacks database/schema creation privileges. Use the "
            "Render database owner credential for MIGRATION_DATABASE_URL."
        )

    version_owner = connection.execute(
        text(
            "SELECT pg_get_userbyid(relowner) = current_user "
            "FROM pg_class WHERE oid = to_regclass('public.alembic_version')"
        )
    ).scalar_one_or_none()
    if version_owner is False:
        raise RuntimeError(
            "The migration user does not own public.alembic_version. Use the database "
            "owner credential for MIGRATION_DATABASE_URL."
        )


def apply_runtime_grants(
    connection: Connection, role_name: str = RUNTIME_ROLE
) -> None:
    raw_connection = connection.connection.driver_connection
    role = sql.Identifier(role_name)
    owner_name = connection.execute(text("SELECT current_user")).scalar_one()
    owner = sql.Identifier(owner_name)

    # Start from a clean privilege matrix. This also removes grants left by older
    # releases before any operation-specific privileges are restored below.
    raw_connection.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC"))
    raw_connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC"))
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(role)
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(role)
    )
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
    raw_connection.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(role))
    raw_connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))

    read_tables = (
        "services",
        "incidents",
        "incident_services",
        "dependency_edges",
        "timeline_events",
        "metric_points",
        "log_events",
        "spans",
        "evidence_snapshots",
        "snapshot_evidence",
        "replay_reports",
        "investigations",
        "hypotheses",
        "simulation_approvals",
        "audit_events",
        "guest_rate_events",
    )
    for table_name in read_tables:
        raw_connection.execute(
            sql.SQL("GRANT SELECT ON TABLE public.{} TO {}").format(
                sql.Identifier(table_name), role
            )
        )

    insert_tables = (
        "evidence_snapshots",
        "snapshot_evidence",
        "investigations",
        "hypotheses",
        "simulation_approvals",
        "audit_events",
        "guest_rate_events",
    )
    for table_name in insert_tables:
        raw_connection.execute(
            sql.SQL("GRANT INSERT ON TABLE public.{} TO {}").format(
                sql.Identifier(table_name), role
            )
        )

    raw_connection.execute(
        sql.SQL(
            "GRANT UPDATE (status, completed_at, error_code, input_tokens, output_tokens, "
            "provider_request_id, uncertainty) ON TABLE public.investigations TO {}"
        ).format(role)
    )
    raw_connection.execute(
        sql.SQL(
            "REVOKE ALL ON FUNCTION public.prune_expired_guest_rate_events() FROM {}"
        ).format(role)
    )
    raw_connection.execute(
        sql.SQL(
            "GRANT EXECUTE ON FUNCTION public.prune_expired_guest_rate_events() TO {}"
        ).format(role)
    )
    raw_connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON SEQUENCE public.guest_rate_events_id_seq TO {}").format(
            role
        )
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON TABLE public.alembic_version FROM {}").format(role)
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM {}").format(role)
    )
    raw_connection.execute(
        sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA evaluation FROM {}").format(role)
    )

    # Remove legacy/future default grants. New migrations must explicitly run this
    # release grant matrix after creating objects.
    raw_connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "REVOKE ALL ON TABLES FROM {}"
        ).format(owner, role)
    )
    raw_connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "REVOKE ALL ON SEQUENCES FROM {}"
        ).format(owner, role)
    )


def preflight_and_apply_runtime_grants(
    connection: Connection, role_name: str = RUNTIME_ROLE
) -> None:
    """Prove the grant matrix is accepted, roll it back, then apply it."""
    try:
        connection.exec_driver_sql("SAVEPOINT runtime_grant_preflight")
        apply_runtime_grants(connection, role_name)
        connection.exec_driver_sql("ROLLBACK TO SAVEPOINT runtime_grant_preflight")
        apply_runtime_grants(connection, role_name)
    except Exception:
        try:
            connection.exec_driver_sql("ROLLBACK TO SAVEPOINT runtime_grant_preflight")
        except Exception:
            pass
        raise RuntimeError(
            "Migration user cannot apply the required runtime grants. Ensure it owns "
            "the migrated tables or has permission to grant privileges."
        ) from None


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
    try:
        validate_runtime_credentials(
            cfg.database_url,
            deploy_url,
            cfg.runtime_db_password.get_secret_value(),
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None

    admin_engine = create_engine(deploy_url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            _preflight_migration_permissions(connection)
            _provision_role(
                connection,
                cfg.runtime_db_password.get_secret_value(),
                RUNTIME_ROLE,
            )
        _upgrade(deploy_url)
        with Session(admin_engine) as db:
            manifest = seed_runtime(db)
        with admin_engine.begin() as connection:
            preflight_and_apply_runtime_grants(connection, RUNTIME_ROLE)

        runtime_url = migration_database_url(cfg.database_url, None)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        try:
            with runtime_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            raise RuntimeError(
                "The runtime database credential could not connect. Check DATABASE_URL, "
                "RUNTIME_DB_PASSWORD, and the Render-managed runtime credential."
            ) from None
        finally:
            runtime_engine.dispose()
        return manifest
    finally:
        admin_engine.dispose()
