import os
import tempfile
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
_TEMP_SERVER_DIR: tempfile.TemporaryDirectory[str] | None = None
_POSTGRES_ERROR: str | None = None

if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    try:
        from embedded_postgres import get_server

        _TEMP_SERVER_DIR = tempfile.TemporaryDirectory(prefix="incident-atlas-postgres-")
        server = get_server(Path(_TEMP_SERVER_DIR.name) / "pgdata", cleanup_mode="delete")
        server.ensure_postgres_running()
        os.environ["DATABASE_URL"] = server.get_uri().replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    except Exception as exc:  # A sandbox may disallow local sockets or starting processes.
        _POSTGRES_ERROR = f"{type(exc).__name__}: {exc}"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if _POSTGRES_ERROR:
        marker = pytest.mark.skip(reason=f"PostgreSQL test server unavailable: {_POSTGRES_ERROR}")
        for item in items:
            if "postgres" in item.keywords:
                item.add_marker(marker)


@pytest.fixture(scope="session")
def migrated_postgres() -> None:
    if _POSTGRES_ERROR:
        pytest.skip(f"PostgreSQL test server unavailable: {_POSTGRES_ERROR}")

    from alembic import command
    from alembic.config import Config

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%"))
    command.upgrade(config, "head")


@pytest.fixture
def clean_postgres(migrated_postgres):
    from sqlalchemy import text

    from incident_atlas.db import SessionLocal

    tables = [
        "evaluation.labels",
        "public.simulation_approvals",
        "public.audit_events",
        "public.guest_rate_events",
        "public.hypotheses",
        "public.investigations",
        "public.replay_reports",
        "public.snapshot_evidence",
        "public.evidence_snapshots",
        "public.spans",
        "public.log_events",
        "public.metric_points",
        "public.timeline_events",
        "public.dependency_edges",
        "public.incident_services",
        "public.incidents",
        "public.services",
    ]
    with SessionLocal.bind.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def pg_client(clean_postgres):
    from fastapi.testclient import TestClient

    from incident_atlas.config import Settings, get_settings
    from incident_atlas.db import SessionLocal, get_db
    from incident_atlas.fixtures import seed_runtime
    from incident_atlas.main import app

    with SessionLocal() as db:
        seed_runtime(db)

    def get_test_db():
        with SessionLocal() as db:
            yield db

    def settings_override() -> Settings:
        return Settings(
            environment="test",
            database_url=os.environ["DATABASE_URL"],
            openai_api_key=None,
            live_analysis_enabled=False,
            rate_limit_enabled=False,
        )

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_settings] = settings_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
