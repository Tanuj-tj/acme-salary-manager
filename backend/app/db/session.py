"""Engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _apply_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable foreign key enforcement on SQLite.

    SQLite ships with foreign keys *off*, so without this a broken reference
    that PostgreSQL rejects passes silently in local development. This is the
    single most common source of SQLite/PostgreSQL drift.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()

    connect_args: dict[str, Any] = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )

    if settings.is_sqlite:
        event.listen(engine, "connect", _apply_sqlite_pragmas)

    return engine


engine: Engine = create_db_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session.

    Commit is the service layer's decision; this only guarantees the session is
    rolled back on error and always closed.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
