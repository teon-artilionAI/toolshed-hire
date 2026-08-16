"""A minimal application that mounts one endpoint per role policy.

The skeleton ships no administrator only endpoint yet, so there is no real
route on which to prove that `require_roles` refuses the wrong role. Rather
than skip the case until such a route exists, or assert against the dependency
function in isolation and miss the exception handling entirely, this builds a
real FastAPI application that uses the real dependencies and the real error
handlers, and mounts nothing but the policies.

What it proves is exactly what the production application relies on: that the
chain of `get_bearer_token`, `get_authenticated_user`, `get_active_user` and
`require_roles` answers 401, 403 or 200, and that the answer is a problem
document rather than a stack trace.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import FastAPI, status

from app.api.deps import AdminUser, AnyRoleUser, CounterUser, CustomerUser
from app.api.errors import register_exception_handlers
from app.infrastructure.models import UserAccount

logger = logging.getLogger(__name__)

ADMIN_PATH: Final[str] = "/probe/admin-only"
COUNTER_PATH: Final[str] = "/probe/counter-only"
CUSTOMER_PATH: Final[str] = "/probe/customer-only"
ANY_ROLE_PATH: Final[str] = "/probe/any-role"
PROBE_TITLE: Final[str] = "Role policy probe"


def _describe(user: UserAccount) -> dict[str, str]:
    """Return the account that was admitted, so a test can prove which one it was."""
    return {"userId": str(user.id), "role": user.role.value, "email": user.email}


def build_role_probe_app() -> FastAPI:
    """Build the probe application with one endpoint per role policy.

    Returns:
        A FastAPI application with the production exception handlers attached.
        The caller is expected to override `get_session` before using it.

    """
    app = FastAPI(title=PROBE_TITLE)
    register_exception_handlers(app)

    @app.get(ADMIN_PATH, status_code=status.HTTP_200_OK)
    def read_admin_only(user: AdminUser) -> dict[str, str]:
        """Admit administrators only."""
        return _describe(user)

    @app.get(COUNTER_PATH, status_code=status.HTTP_200_OK)
    def read_counter_only(user: CounterUser) -> dict[str, str]:
        """Admit counter staff and administrators."""
        return _describe(user)

    @app.get(CUSTOMER_PATH, status_code=status.HTTP_200_OK)
    def read_customer_only(user: CustomerUser) -> dict[str, str]:
        """Admit customers only."""
        return _describe(user)

    @app.get(ANY_ROLE_PATH, status_code=status.HTTP_200_OK)
    def read_any_role(user: AnyRoleUser) -> dict[str, str]:
        """Admit any signed in, active account."""
        return _describe(user)

    logger.debug("test.role_probe_app_built", extra={"route_count": len(app.routes)})
    return app


__all__ = [
    "ADMIN_PATH",
    "ANY_ROLE_PATH",
    "COUNTER_PATH",
    "CUSTOMER_PATH",
    "build_role_probe_app",
]
