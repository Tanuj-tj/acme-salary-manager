"""Shared test fixtures.

Every test runs against an in-memory SQLite database inside a transaction that
is rolled back afterwards, so tests are isolated and order-independent without
recreating the schema each time.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Environment, Settings
from app.db.base import Base
from app.db.session import _apply_sqlite_pragmas, get_session
from app.main import create_app
from app.models import Employee, SalaryRecord  # noqa: F401  (registers metadata)


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """One in-memory database shared by the whole session.

    StaticPool keeps every connection pointed at the same in-memory database;
    without it each connection would get a fresh, empty one.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _configure_connection(dbapi_connection: Any, connection_record: Any) -> None:
        # Mirror production: foreign keys are off by default in SQLite, and a
        # suite that does not enable them will not catch broken references.
        _apply_sqlite_pragmas(dbapi_connection, connection_record)
        # Hand transaction control to SQLAlchemy. pysqlite otherwise manages
        # BEGIN implicitly, which stops SAVEPOINTs nesting properly and would
        # make the per-test rollback below a silent no-op.
        dbapi_connection.isolation_level = None

    @event.listens_for(test_engine, "begin")
    def _emit_begin(conn: Any) -> None:
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    """A session wrapped in a transaction that is always rolled back.

    ``join_transaction_mode="create_savepoint"`` lets service code call
    ``commit()`` for real while the outer transaction still discards
    everything at the end of the test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    test_session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield test_session
    finally:
        test_session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.CI, database_url="sqlite://", debug=True)


@pytest.fixture
def client(session: Session, settings: Settings) -> Generator[TestClient, None, None]:
    """API client bound to the test session, so requests share test state."""
    app = create_app(settings)

    def override_get_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
