"""What every route of the real application is expected to declare, as data.

tests/api/test_route_policies.py compares the route table with this listing.
A new route has to be added here as well, which is the moment to decide who
may call it. The listing lives in a module of its own so the test that reads
it stays about the checks and not about the list.
"""

from __future__ import annotations

from typing import Final

from app.api.access_policy import AccessKind
from app.domain.enums import UserRole

ALL_ROLES: Final[frozenset[UserRole]] = frozenset(UserRole)
CUSTOMER_ROLE: Final[frozenset[UserRole]] = frozenset({UserRole.CUSTOMER})
STAFF_ROLES: Final[frozenset[UserRole]] = frozenset({UserRole.COUNTER_STAFF, UserRole.ADMIN})
NO_ROLES: Final[frozenset[UserRole]] = frozenset()

EXPECTED_POLICIES: Final[dict[str, tuple[AccessKind, frozenset[UserRole]]]] = {
    "GET /api/health": (AccessKind.PUBLIC, NO_ROLES),
    "POST /api/auth/login": (AccessKind.PUBLIC, NO_ROLES),
    "POST /api/auth/refresh": (AccessKind.REFRESH_COOKIE, NO_ROLES),
    "POST /api/auth/logout": (AccessKind.REFRESH_COOKIE, NO_ROLES),
    "POST /api/auth/register": (AccessKind.PUBLIC, NO_ROLES),
    "POST /api/auth/email-verification": (AccessKind.PUBLIC, NO_ROLES),
    "POST /api/auth/email-verification/resend": (AccessKind.ROLES, ALL_ROLES),
    "POST /api/auth/password-reset/request": (AccessKind.PUBLIC, NO_ROLES),
    "POST /api/auth/password-reset/complete": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/me": (AccessKind.ROLES, ALL_ROLES),
    "GET /api/me/profile": (AccessKind.ROLES, CUSTOMER_ROLE),
    "PATCH /api/me/profile": (AccessKind.ROLES, CUSTOMER_ROLE),
    "GET /api/customers": (AccessKind.ROLES, STAFF_ROLES),
    "POST /api/customers": (AccessKind.ROLES, STAFF_ROLES),
    "GET /api/customers/{id}": (AccessKind.ROLES, STAFF_ROLES),
    "POST /api/reservations": (AccessKind.ROLES, ALL_ROLES),
    "POST /api/reservations/{id}/hold": (AccessKind.ROLES, ALL_ROLES),
    "POST /api/reservations/{id}/confirm": (AccessKind.ROLES, ALL_ROLES),
    "POST /api/reservations/{id}/cancellation": (AccessKind.ROLES, ALL_ROLES),
    "GET /api/reservations": (AccessKind.ROLES, ALL_ROLES),
    "GET /api/reservations/{id}": (AccessKind.ROLES, ALL_ROLES),
    "GET /api/reservations/{id}/checkout": (AccessKind.ROLES, STAFF_ROLES),
    "POST /api/reservations/{id}/checkout": (AccessKind.ROLES, STAFF_ROLES),
    "GET /api/rentals/{id}": (AccessKind.ROLES, STAFF_ROLES),
    "GET /api/branches": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/categories": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/models": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/models/{slug}": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/availability": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/models/{slug}/availability": (AccessKind.PUBLIC, NO_ROLES),
    "GET /api/catalogue/models/{slug}/quote": (AccessKind.PUBLIC, NO_ROLES),
}

__all__ = ["ALL_ROLES", "CUSTOMER_ROLE", "EXPECTED_POLICIES", "STAFF_ROLES"]
