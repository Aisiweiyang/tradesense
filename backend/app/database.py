"""Database engine and session management.

SQLite differences (e.g. foreign_keys pragma, check_same_thread) are handled
here so the rest of the code stays database-agnostic.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

# SQLite file DBs live under a directory (backend/data/) that must exist
# before the engine connects; in-memory / non-sqlite URLs are untouched.
if settings.database_url.startswith("sqlite"):
    _sqlite_file = settings.database_url.replace("sqlite:///", "", 1)
    if _sqlite_file and _sqlite_file != ":memory:":
        Path(_sqlite_file).parent.mkdir(parents=True, exist_ok=True)

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        # 并发写时等锁而不是立刻抛 database is locked
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
