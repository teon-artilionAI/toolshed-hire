"""Fixtures for the backend suite.

There are two fixture families and they are kept apart on purpose, because the
pipeline runs them as two separate jobs and a test that quietly reaches for the
wrong one turns a clean split into intermittent failure.

THE FAST FAMILY, no database required
    `sqlite_engine`, `session`, `factory`, `client` and `probe_client`. An in
    memory SQLite database behind a StaticPool, so the one connection holding
    the schema is the one the request handler is given. These run in the "not
    postgres" job and must never open a network connection.

THE POSTGRES FAMILY, marked `postgres`
    `postgres_engine`, `postgres_session` and `postgres_factory`. A real
    PostgreSQL read from DATABASE_URL, migrated with Alembic, holding the GiST
    exclusion constraint that SQLite cannot express. Absent DATABASE_URL these
    skip with a message saying what to set, rather than erroring in a way that
    reads as a broken checkout.

What SQLite cannot prove is stated once here so no reader has to guess. It has
no `btree_gist`, no `daterange`, no exclusion constraint and no meaningful row
level locking. Everything that depends on those is marked `postgres` and lives
under tests/integration.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
from sqlmodel import Session

from app.config import settings
from app.infrastructure.database import get_session
from app.main import app as production_app
from tests.support.factories import Factory
from tests.support.pg import truncate_skeleton_tables
from tests.support.probe_app import build_role_probe_app
from tests.support.sqlite_dialect import build_sqlite_engine

logger = logging.getLogger(__name__)

BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ALEMBIC_CONFIG_PATH: Final[Path] = BACKEND_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION: Final[Path] = BACKEND_ROOT / "alembic"
ALEMBIC_HEAD: Final[str] = "head"
DATABASE_URL_VARIABLE: Final[str] = "DATABASE_URL"
POSTGRES_MARKER: Final[str] = "postgres"

SKIP_NO_DATABASE_URL: Final[str] = (
    f"{DATABASE_URL_VARIABLE} is not set, so there is no PostgreSQL to test against. "
    "These tests prove the daterange exclusion constraint and genuine transaction "
    "concurrency, neither of which SQLite can express, so they are skipped rather "
    "than weakened. To run them, start PostgreSQL 16 and set "
    f"{DATABASE_URL_VARIABLE}=postgresql+psycopg://user:password@host:5432/database."
)
SKIP_NOT_A_DISPOSABLE_DATABASE: Final[str] = (
    "These tests truncate every table in the schema between cases, so they refuse to "
    f"run against environment {settings.environment.value!r}. Set ENVIRONMENT=test and "
    f"point {DATABASE_URL_VARIABLE} at a database you are willing to lose."
)


def pytest_configure(config: pytest.Config) -> None:
    """Register the `postgres` marker so an unknown marker cannot pass silently.

    The marker is also declared in pyproject.toml. It is registered here as
    well so that running pytest against this directory with a different
    configuration file still selects and deselects correctly.
    """
    config.addinivalue_line(
        "markers",
        f"{POSTGRES_MARKER}: requires a real PostgreSQL reached through "
        f"{DATABASE_URL_VARIABLE}. Excluded by `pytest -m \"not {POSTGRES_MARKER}\"`.",
    )


# ---------------------------------------------------------------------------
# The fast family. In memory SQLite, no network, no database required.
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Yield a fresh in memory SQLite engine with the schema created.

    One engine per test, so no test can be made to pass or fail by the rows
    another test left behind.
    """
    engine = build_sqlite_engine()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(sqlite_engine: Engine) -> Iterator[Session]:
    """Yield a session on the in memory database."""
    with Session(sqlite_engine) as open_session:
        yield open_session


@pytest.fixture
def factory(session: Session) -> Factory:
    """Return object factories bound to the in memory session."""
    return Factory(session=session)


def _client_for(application: FastAPI, open_session: Session) -> Iterator[TestClient]:
    """Yield a test client whose request sessions are the one the test holds.

    The application is entered without its lifespan. The startup check probes
    the configured PostgreSQL for `btree_gist`, and running it here would make
    every fast test attempt a network connection that the fast job does not
    have and does not need.

    The override rolls back at the end of every request. A request scoped
    session in production is discarded when the request ends, so anything a
    failed use case left pending never reaches the database. Sharing one session
    with the test would otherwise leave that pending work visible to the next
    assertion, which is a difference between the test and production that would
    eventually be mistaken for a bug in one of them. The consequence is that a
    test must commit its setup before it makes a request.
    """

    def _override_session() -> Iterator[Session]:
        """Hand the request the test's session and discard uncommitted work after."""
        try:
            yield open_session
        finally:
            open_session.rollback()

    application.dependency_overrides[get_session] = _override_session
    try:
        yield TestClient(application)
    finally:
        application.dependency_overrides.pop(get_session, None)


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """Yield a client for the real application, backed by the in memory database."""
    yield from _client_for(production_app, session)


@pytest.fixture
def probe_client(session: Session) -> Iterator[TestClient]:
    """Yield a client for the role policy probe application."""
    yield from _client_for(build_role_probe_app(), session)


# ---------------------------------------------------------------------------
# The PostgreSQL family. Marked `postgres`, skipped cleanly when absent.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Return the DSN of a disposable PostgreSQL, or skip with an explanation.

    Returns:
        The normalised DSN from the application settings, which forces the
        psycopg driver prefix, rather than the raw environment string.

    """
    if not os.environ.get(DATABASE_URL_VARIABLE):
        pytest.skip(SKIP_NO_DATABASE_URL)
    if not settings.environment.is_relaxed:
        pytest.skip(SKIP_NOT_A_DISPOSABLE_DATABASE)
    return settings.database_url


def _apply_migrations() -> None:
    """Migrate the configured database to head with Alembic.

    Run in process rather than shelling out, so a failure surfaces as a Python
    traceback in the test output. Alembic reads the same DATABASE_URL the
    application does, and upgrading a database already at head is a no operation,
    so this is safe to run in a pipeline that has already migrated.

    Alembic is imported here rather than at module scope on purpose. This module
    is loaded by every run including the database free one, and importing a
    migration tool that the fast job never uses would make an unrelated
    installation problem look like a test failure. The submodules are imported
    by their full names because `backend/alembic` is also a directory, and the
    import sorter classifies the two spellings differently.
    """
    import alembic.command
    import alembic.config

    config = alembic.config.Config(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    logger.info(
        "test.migrations_started",
        extra={"config": str(ALEMBIC_CONFIG_PATH), "revision": ALEMBIC_HEAD},
    )
    alembic.command.upgrade(config, ALEMBIC_HEAD)
    logger.info("test.migrations_finished", extra={"revision": ALEMBIC_HEAD})


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on the real database, migrated to head.

    NullPool is deliberate. The concurrency tests need two genuinely
    independent connections held at the same time, and a pooled engine that
    hands the same connection to both threads would serialise the very race the
    test exists to run.
    """
    engine = create_engine(postgres_url, poolclass=NullPool, echo=False)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        pytest.fail(
            f"{DATABASE_URL_VARIABLE} is set but the database did not answer. Attempted "
            f"SELECT 1 against {_safe_host(postgres_url)}. Start PostgreSQL or unset "
            f"{DATABASE_URL_VARIABLE} to skip these tests instead. Cause: {exc}"
        )
    _apply_migrations()
    logger.info("test.postgres_engine_ready", extra={"host": _safe_host(postgres_url)})
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def postgres_session(postgres_engine: Engine) -> Iterator[Session]:
    """Yield a session on the real database, with the tables emptied around it.

    Truncating before as well as after means a test still starts clean when the
    previous run was killed part way through.
    """
    truncate_skeleton_tables(postgres_engine)
    open_session = Session(postgres_engine)
    try:
        yield open_session
    finally:
        open_session.close()
        truncate_skeleton_tables(postgres_engine)


@pytest.fixture
def postgres_factory(postgres_session: Session) -> Factory:
    """Return object factories bound to the real database session."""
    return Factory(session=postgres_session)


def _safe_host(database_url: str) -> str:
    """Return the host and database from a DSN with the credentials removed."""
    without_scheme = database_url.split("://", 1)[-1]
    return without_scheme.rsplit("@", 1)[-1] if "@" in without_scheme else without_scheme
