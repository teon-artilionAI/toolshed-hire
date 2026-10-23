"""Health endpoint.

Public by declaration, because the smoke test in each deployment and any
uptime check call it with no credential.
It reports what it actually verified rather than a bare "ok": whether the database
answered, and whether `btree_gist` is installed, since the exclusion constraint
that prevents double booking cannot exist without it.

It also names the revision that answered. Cloud Run sets `K_REVISION` on every
instance, so after a deployment I can ask the service which revision is serving
and compare it with the one I just released. Away from Cloud Run it says
`local`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import SessionDependency, public_access
from app.api.schemas import HealthResponse, LiveHealthResponse
from app.config import settings
from app.infrastructure.database import check_database_reachable, check_extension_installed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"], dependencies=[Depends(public_access)])

STATUS_HEALTHY = "healthy"
LIVE_PATH = "/health/live"
STATUS_DEGRADED = "degraded"


@router.get(
    LIVE_PATH,
    response_model=LiveHealthResponse,
    summary="Report that the process is alive, without opening a session",
)
def read_liveness() -> LiveHealthResponse:
    """Answer from the process alone, so an uptime check never wakes the database.

    The route has no session dependency on purpose. An uptime check calling it
    every five minutes must not keep Neon's compute awake all month, and this is
    the proof that it cannot.
    """
    logger.debug("health.liveness_checked")
    return LiveHealthResponse(
        status=STATUS_HEALTHY,
        environment=settings.environment.value,
        revision=settings.revision,
    )


@router.get("/health", response_model=HealthResponse, summary="Report dependency health")
def read_health(session: SessionDependency, response: Response) -> HealthResponse:
    """Report database reachability and the presence of the btree_gist extension.

    Returns 200 when everything the application needs is present, and 503 when
    it is not, so an uptime check does not have to parse the body to decide
    whether the service is usable.
    """
    logger.debug("health.check_started")
    database_reachable = check_database_reachable(session)
    extension_installed = check_extension_installed(session) if database_reachable else False
    healthy = database_reachable and extension_installed
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.error(
            "health.check_degraded",
            extra={
                "database_reachable": database_reachable,
                "btree_gist_installed": extension_installed,
            },
        )
    else:
        logger.debug("health.check_healthy")
    return HealthResponse(
        status=STATUS_HEALTHY if healthy else STATUS_DEGRADED,
        environment=settings.environment.value,
        database_reachable=database_reachable,
        btree_gist_installed=extension_installed,
        revision=settings.revision,
    )
