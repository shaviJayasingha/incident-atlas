from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from incident_atlas.config import get_settings
from incident_atlas.database_urls import runtime_database_url

settings = get_settings()
engine = create_engine(
    runtime_database_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={
        "options": f"-c statement_timeout={int(settings.database_query_timeout_seconds * 1000)}"
    },
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
