"""Engine and session factory.

Three settings here are not decoration.

`pool_pre_ping` issues a cheap liveness check before a pooled connection is
handed out. Without it, a connection that the pooler or the network dropped
while it was idle surfaces as an intermittent 500 on the next request, which is
the classic failure of a serverless application in front of a pooled PostgreSQL
endpoint.

`pool_recycle` is set below the idle timeout of a typical pooler, so this side
of the connection is retired before the far side does it silently.

`pool_size` and `max_overflow` are sized against the deployment. Cloud Run is
capped at four instances, so a pool of five with no overflow keeps the peak at
twenty connections, which is the arithmetic NFR-15 relies on.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.config import settings

logger = logging.getLogger(__name__)

# Below the idle timeout of a pooled endpoint, which is commonly five minutes.
POOL_RECYCLE_SECONDS = 240
POOL_SIZE = 5
MAX_OVERFLOW = 0
POOL_TIMEOUT_SECONDS = 10
# A pooled Neon endpoint carries this marker in its host name. Direct endpoints
# do not, and a direct endpoint behind Cloud Run runs out of connections.
POOLED_ENDPOINT_MARKER = "-pooler"
REQUIRED_EXTENSION = "btree_gist"


def _build_engine() -> Engine:
    """Create the process wide engine and log the pool shape it was given."""
    if POOLED_ENDPOINT_MARKER not in settings.database_url and not settings.environment.is_relaxed:
        logger.warning(
            "database.endpoint_not_pooled",
            extra={
                "environment": settings.environment.value,
                "expected_marker": POOLED_ENDPOINT_MARKER,
                "action": "point DATABASE_URL at the pooled endpoint before go live",
            },
        )
    engine = create_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args={"application_name": f"toolshed-hire-{settings.environment.value}"},
    )
    logger.info(
        "database.engine_created",
        extra={
            "pool_size": POOL_SIZE,
            "max_overflow": MAX_OVERFLOW,
            "pool_recycle_seconds": POOL_RECYCLE_SECONDS,
            "pre_ping": True,
        },
    )
    return engine


engine: Engine = _build_engine()


def get_session() -> Generator[Session, None, None]:
    """Yield a request scoped session, used as a FastAPI dependency.

    The session is not committed here. A use case that writes owns its own
    transaction boundary, which keeps a partial allocation from ever being
    committed by an accident of dependency ordering (BR-09).
    """
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Yield a session that commits on success and rolls back on any exception.

    Used by scripts and by tests. Request handlers use `get_session` and manage
    their own commit, because they need to translate a failure into a response
    rather than only re raise it.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("database.session_rolled_back")
        raise
    finally:
        session.close()


def check_database_reachable(session: Session) -> bool:
    """Return True when a trivial query succeeds against the database.

    Args:
        session: An open session to probe with.

    Returns:
        True if the round trip succeeded, False if the driver raised.

    """
    logger.debug("database.health_probe_started")
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error(
            "database.health_probe_failed",
            extra={"attempted": "SELECT 1", "error": str(exc)},
        )
        return False
    logger.debug("database.health_probe_succeeded")
    return True


def check_extension_installed(session: Session, extension_name: str = REQUIRED_EXTENSION) -> bool:
    """Return True when the named PostgreSQL extension is installed.

    The exclusion constraint that prevents double booking cannot exist without
    `btree_gist`, so its absence is a fatal deployment fault rather than a
    degraded feature. The health endpoint reports it explicitly.

    Args:
        session: An open session to probe with.
        extension_name: The extension to look for in `pg_extension`.

    Returns:
        True if the extension is present, False if it is absent or the probe
        failed.

    """
    logger.debug("database.extension_probe_started", extra={"extension": extension_name})
    try:
        result = session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = :name"),
            {"name": extension_name},
        )
        found = result.first() is not None
    except SQLAlchemyError as exc:
        logger.error(
            "database.extension_probe_failed",
            extra={"extension": extension_name, "error": str(exc)},
        )
        return False
    logger.debug(
        "database.extension_probe_finished",
        extra={"extension": extension_name, "installed": found},
    )
    return found


def describe_pool() -> dict[str, int | str]:
    """Return the pool configuration for the startup log and the health payload."""
    return {
        "environment": settings.environment.value,
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        "pool_recycle_seconds": POOL_RECYCLE_SECONDS,
        "pool_timeout_seconds": POOL_TIMEOUT_SECONDS,
    }


__all__ = [
    "check_database_reachable",
    "check_extension_installed",
    "describe_pool",
    "engine",
    "get_session",
    "session_scope",
]
