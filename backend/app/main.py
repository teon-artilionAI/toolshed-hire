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

The order of the middleware matters and is easy to get backwards, because the
one added last is the one a request meets first. The security headers are
outermost, so no response can leave without them. The request context is next.
It binds the request id, writes the access log and answers an unhandled fault,
and whatever it sends passes back out through the security headers. CORS is
innermost.

The interactive documentation and the OpenAPI document are served in
development and test only. A deployed service that describes every endpoint to
anyone who asks has done an attacker's reconnaissance for them.

The email gateway is chosen here as well, from the configuration. With no API
key the application still starts. It logs one warning, and every booking
confirmation is then recorded as not sent.

The application refuses to start while any route has not declared who may call
it (BR-41). The route table is walked when the application is built and again
when it starts serving, so a route mounted after the factory returned is caught
as well. The refresh cookie and the origins it may be used from are set here
too, from the configuration, so an application built for production marks the
cookie `Secure` whatever the process around it is configured as.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.access_policy import enforce_declared_policies
from app.api.deps import NOTIFICATION_GATEWAY_STATE_KEY
from app.api.errors import register_exception_handlers
from app.api.identity_deps import ALLOWED_ORIGINS_STATE_KEY, normalise_origin
from app.api.refresh_cookie import REFRESH_COOKIE_STATE_KEY, RefreshCookie
from app.api.request_middleware import RequestContextMiddleware
from app.api.routers import api_router
from app.api.security_headers import SecurityHeadersMiddleware
from app.config import Settings, settings
from app.infrastructure.database import (
    check_database_reachable,
    check_extension_installed,
    describe_pool,
    engine,
)
from app.infrastructure.notification import build_notification_gateway
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

APPLICATION_TITLE = "Toolshed Hire API"
APPLICATION_VERSION = "0.2.0"
APPLICATION_DESCRIPTION = (
    "Rental system for Toolshed Hire. Availability is the allocation of specific "
    "tagged assets over half open date periods, enforced by a PostgreSQL GiST "
    "exclusion constraint."
)
ALLOWED_METHODS = ["GET", "POST", "PATCH", "PUT"]
ALLOWED_HEADERS = ["Authorization", "Content-Type"]
DOCS_PATH = "/docs"
REDOC_PATH = "/redoc"
OPENAPI_PATH = "/openapi.json"
# The two documentation pages are HTML that loads a script, which the JSON only
# content security policy would block. They are answered without it.
DOCUMENTATION_PAGE_PATHS = frozenset({DOCS_PATH, REDOC_PATH})
# Every path the framework serves by itself. None of them has a dependency
# tree to carry a policy, so the route table check is told they are public.
# They exist in development and test only.
FRAMEWORK_ROUTE_PATHS = frozenset(
    {DOCS_PATH, f"{DOCS_PATH}/oauth2-redirect", REDOC_PATH, OPENAPI_PATH}
)


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
    """Run the startup checks once, then dispose the pool on shutdown.

    The route table is checked first and without a database, so a route with
    no declared policy stops the process before it opens a connection.
    """
    enforce_declared_policies(app, framework_paths=FRAMEWORK_ROUTE_PATHS)
    run_startup_checks()
    logger.info(
        "startup.application_ready",
        extra={"routes": len(app.routes), "environment": settings.environment.value},
    )
    yield
    engine.dispose()
    logger.info("shutdown.connection_pool_disposed")


def create_app(configuration: Settings = settings) -> FastAPI:
    """Build the application with its routers, middleware and error handlers.

    Args:
        configuration: The settings that decide what the application exposes.
            The process settings by default. A test passes its own to build the
            application a deployed environment would run.

    """
    configure_logging()
    relaxed = configuration.environment.is_relaxed
    app = FastAPI(
        title=APPLICATION_TITLE,
        version=APPLICATION_VERSION,
        description=APPLICATION_DESCRIPTION,
        lifespan=lifespan,
        docs_url=DOCS_PATH if relaxed else None,
        redoc_url=REDOC_PATH if relaxed else None,
        openapi_url=OPENAPI_PATH if relaxed else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        strict_transport=not relaxed,
        content_security_policy_exempt_paths=DOCUMENTATION_PAGE_PATHS if relaxed else frozenset(),
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    enforce_declared_policies(app, framework_paths=FRAMEWORK_ROUTE_PATHS)
    setattr(app.state, REFRESH_COOKIE_STATE_KEY, RefreshCookie(secure=not relaxed))
    setattr(
        app.state,
        ALLOWED_ORIGINS_STATE_KEY,
        frozenset(normalise_origin(origin) for origin in configuration.cors_origins),
    )
    # Chosen once, here, so a missing API key is reported once at start-up and
    # every request is served by the same gateway.
    setattr(
        app.state,
        NOTIFICATION_GATEWAY_STATE_KEY,
        build_notification_gateway(
            api_key=configuration.resend_api_key,
            sender=configuration.email_from,
            allowed_recipient=configuration.email_allowed_recipient,
        ),
    )
    logger.info(
        "startup.application_built",
        extra={
            "title": APPLICATION_TITLE,
            "version": APPLICATION_VERSION,
            "environment": configuration.environment.value,
            "api_documentation_served": relaxed,
            "strict_transport_security": not relaxed,
            "refresh_credential_secure": not relaxed,
            "cors_origins": configuration.cors_origins,
        },
    )
    return app


app = create_app()
