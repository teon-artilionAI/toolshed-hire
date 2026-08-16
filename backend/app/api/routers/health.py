"""Health endpoint.

Deliberately public. It is the one endpoint with no role policy, because the
shallow availability check runs from Cloud Scheduler with no credential. It
reports what it actually verified rather than a bare "ok": whether the database
answered, and whether `btree_gist` is installed, since the exclusion constraint
that prevents double booking cannot exist without it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from app.api.deps import SessionDependency
from app.api.schemas import HealthResponse
from app.config import settings
from app.infrastructure.database import check_database_reachable, check_extension_installed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"


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
    )
