"""FastAPI application factory.

The startup check does two things that are worth keeping. It logs the resolved
configuration with every secret removed, so an operator can see what the
process actually loaded without the log becoming a credential store. And it
probes the database for `btree_gist`, because the exclusion constraint that
makes double booking impossible cannot exist without that extension, and a
service that starts happily without it would fail later at the worst moment.

CORS is configured but is not the primary defence. In production the browser
talks to Vercel, which rewrites `/api/*` to Cloud Run server side, so there is
no cross origin request to permit. The middleware exists for local development,
where the Vite dev server is a genuinely different origin.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.errors import register_exception_handlers
from app.api.routers import api_router
from app.config import settings
from app.infrastructure.database import (
    check_database_reachable,
    check_extension_installed,
    describe_pool,
    engine,
)
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

APPLICATION_TITLE = "Toolshed Hire API"
APPLICATION_VERSION = "0.1.0"
APPLICATION_DESCRIPTION = (
    "Rental system for Toolshed Hire. Availability is the allocation of specific "
    "tagged assets over half open date periods, enforced by a PostgreSQL GiST "
    "exclusion constraint."
)
ALLOWED_METHODS = ["GET", "POST", "PATCH", "PUT"]
ALLOWED_HEADERS = ["Authorization", "Content-Type"]


def run_startup_checks() -> None:
    """Log the resolved configuration and verify the database prerequisites.

    A failed probe is logged at error level and does not stop the process. The
    health endpoint reports the same two facts and answers 503 while either is
    false, which lets the platform decide whether to route traffic rather than
    having the container crash loop before anyone can read the reason.
    """
    logger.info("startup.configuration_resolved", extra=settings.redacted())
    logger.info("startup.database_pool", extra=describe_pool())
    with Session(engine) as session:
        reachable = check_database_reachable(session)
        extension_present = check_extension_installed(session) if reachable else False
    if not reachable:
        logger.error(
            "startup.database_unreachable",
            extra={"attempted": "SELECT 1 against the configured DATABASE_URL"},
        )
    elif not extension_present:
        logger.error(
            "startup.btree_gist_missing",
            extra={
                "attempted": "verify the btree_gist extension is installed",
                "consequence": "the allocation exclusion constraint cannot exist",
                "remedy": "run the Alembic migrations against this database",
            },
        )
    else:
        logger.info("startup.database_ready", extra={"btree_gist_installed": True})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the startup checks once, then dispose the pool on shutdown."""
    run_startup_checks()
    logger.info(
        "startup.application_ready",
        extra={"routes": len(app.routes), "environment": settings.environment.value},
    )
    yield
    engine.dispose()
    logger.info("shutdown.connection_pool_disposed")


def create_app() -> FastAPI:
    """Build the application with its routers, middleware and error handlers."""
    configure_logging()
    app = FastAPI(
        title=APPLICATION_TITLE,
        version=APPLICATION_VERSION,
        description=APPLICATION_DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    logger.info(
        "startup.application_built",
        extra={
            "title": APPLICATION_TITLE,
            "version": APPLICATION_VERSION,
            "cors_origins": settings.cors_origins,
        },
    )
    return app


app = create_app()
