"""The real application, with a few extra routes to aim requests at.

The application has no route with an identifier in its path yet and, by design,
no route that fails. The request middleware has to be proved against both, so
this takes the application exactly as `create_app` builds it, with its real
middleware and its real error handlers, and adds three routes under
`/api/probe`. Nothing about the middleware is rebuilt here, which is the point.
A copy of the wiring would only prove the copy.

The probe routes declare that they are public, like every other route. They are
mounted after the factory has checked the route table, so nothing would stop
them being added without a policy, and a probe that set that example would be
a poor one.

`settings_for` builds the settings a deployed environment would load, so the
same factory can be asked for the application staging or production would run.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Final

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import StreamingResponse

from app.api.deps import public_access
from app.config import Environment, Settings
from app.main import create_app

logger = logging.getLogger(__name__)

PROBE_PREFIX: Final[str] = "/api/probe"
RESERVATION_ROUTE_TEMPLATE: Final[str] = "/api/probe/reservations/{reservation_id}"
FAULT_ROUTE_TEMPLATE: Final[str] = "/api/probe/faults/{fault_id}"
BROKEN_STREAM_ROUTE_TEMPLATE: Final[str] = "/api/probe/streams/{stream_id}"

# A fault whose message quotes a connection string, which is what a database
# driver does when it cannot connect. The password must reach neither the
# response nor the log.
FAULT_DATABASE_PASSWORD: Final[str] = "fault_path_database_password"
FAULT_MESSAGE: Final[str] = (
    "could not connect to "
    f"postgresql+psycopg://toolshed_app:{FAULT_DATABASE_PASSWORD}@db.internal:5432/toolshed"
)
FIRST_STREAM_CHUNK: Final[bytes] = b"first chunk\n"

# Values a deployed environment would be given. Long enough and different
# enough from the placeholders that the start-up checks accept them.
DEPLOYED_JWT_SECRET: Final[str] = "a-signing-key-used-only-by-the-test-suite-0123456789"
DEPLOYED_DATABASE_URL: Final[str] = (
    "postgresql+psycopg://toolshed_app:not_a_real_password@ep-example-pooler.example.test/toolshed"
)


def settings_for(environment: Environment, **overrides: str) -> Settings:
    """Build the settings a process in `environment` would load.

    Args:
        environment: The environment the process claims to be running in.
        overrides: Environment variable names and the values to use instead of
            the deployed defaults above, for example `JWT_SECRET="short"`.

    Returns:
        Validated settings. No `.env` file is read, so the result depends on
        the arguments alone.

    """
    values = {
        "ENVIRONMENT": environment.value,
        "JWT_SECRET": DEPLOYED_JWT_SECRET,
        "DATABASE_URL": DEPLOYED_DATABASE_URL,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def build_request_probe_app(configuration: Settings | None = None) -> FastAPI:
    """Build the real application and add the probe routes to it.

    Args:
        configuration: The settings to build for. The process settings when
            omitted, which in the suite means the test environment.

    """
    application = create_app() if configuration is None else create_app(configuration)
    probe = APIRouter(prefix=PROBE_PREFIX, dependencies=[Depends(public_access)])

    @probe.get("/reservations/{reservation_id}")
    def read_reservation(reservation_id: str) -> dict[str, str]:
        """Answer with the identifier, so the path can carry one."""
        return {"reservationId": reservation_id}

    @probe.get("/faults/{fault_id}")
    def raise_fault(fault_id: str) -> dict[str, str]:
        """Fail the way an unplanned defect fails, before any response exists."""
        raise RuntimeError(FAULT_MESSAGE)

    @probe.get("/streams/{stream_id}")
    def break_stream(stream_id: str) -> StreamingResponse:
        """Start a response and then fail part of the way through its body."""

        def chunks() -> Iterator[bytes]:
            """Yield one chunk and then fail."""
            yield FIRST_STREAM_CHUNK
            raise RuntimeError(FAULT_MESSAGE)

        return StreamingResponse(chunks(), media_type="text/plain")

    application.include_router(probe)
    logger.debug("test.request_probe_app_built", extra={"route_count": len(application.routes)})
    return application


__all__ = [
    "BROKEN_STREAM_ROUTE_TEMPLATE",
    "DEPLOYED_DATABASE_URL",
    "DEPLOYED_JWT_SECRET",
    "FAULT_DATABASE_PASSWORD",
    "FAULT_MESSAGE",
    "FAULT_ROUTE_TEMPLATE",
    "FIRST_STREAM_CHUNK",
    "PROBE_PREFIX",
    "RESERVATION_ROUTE_TEMPLATE",
    "build_request_probe_app",
    "settings_for",
]
