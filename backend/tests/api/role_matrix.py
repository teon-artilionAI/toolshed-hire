"""The role and endpoint matrix, as data (BR-41, C-25).

tests/api/test_route_policies.py asks every row of `MATRIX` as each of the
three roles and as a caller with no credential. A row names a representative
endpoint of a module and who it lets in. Everybody else is refused, an
anonymous caller with 401 and a signed in one with 403. A later change adds a
row here and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from tests.support.probe_app import ADMIN_PATH, COUNTER_PATH, CUSTOMER_PATH, FRESH_ADMIN_PATH

# A key no customer and no reservation carries, so a route that lets the caller
# in answers 404 and one that does not answers 401 or 403 before it looks.
NOBODYS_KEY: Final[str] = "00000000-0000-4000-8000-000000000000"


class Caller(str, Enum):
    """The four kinds of caller the matrix is asked about."""

    ANONYMOUS = "anonymous"
    CUSTOMER = "customer"
    COUNTER = "counter"
    ADMIN = "admin"


EVERYONE: Final[frozenset[Caller]] = frozenset(Caller)
SIGNED_IN: Final[frozenset[Caller]] = EVERYONE - {Caller.ANONYMOUS}
STAFF: Final[frozenset[Caller]] = frozenset({Caller.COUNTER, Caller.ADMIN})
ADMIN_ONLY: Final[frozenset[Caller]] = frozenset({Caller.ADMIN})
CUSTOMER_ONLY: Final[frozenset[Caller]] = frozenset({Caller.CUSTOMER})
API: Final[str] = "api"
PROBE: Final[str] = "probe"


@dataclass(frozen=True, slots=True)
class MatrixRow:
    """One endpoint and the callers it lets in.

    Attributes:
        module: The module the endpoint represents, which is the tag of its
            router. A probe row names the policy it stands in for.
        application: `API` for the real application, `PROBE` for the probe
            application that mounts the policies no real route carries yet.
        method: The HTTP method.
        path: The path to request.
        admits: Who is let in. Everybody else is refused, an anonymous caller
            with 401 and a signed in one with 403.

    """

    module: str
    application: str
    method: str
    path: str
    admits: frozenset[Caller]


# A request carries no body and no query string. A route that lets the caller
# in then answers 422 or its own status, and one that does not answers 401 or
# 403 before it looks at either, so no row needs a valid request.
MATRIX: Final[tuple[MatrixRow, ...]] = (
    MatrixRow("health", API, "GET", "/api/health", EVERYONE),
    MatrixRow("auth", API, "POST", "/api/auth/login", EVERYONE),
    MatrixRow("auth", API, "POST", "/api/auth/register", EVERYONE),
    MatrixRow("auth", API, "POST", "/api/auth/email-verification", EVERYONE),
    MatrixRow("auth", API, "POST", "/api/auth/email-verification/resend", SIGNED_IN),
    MatrixRow("auth", API, "POST", "/api/auth/password-reset/request", EVERYONE),
    MatrixRow("auth", API, "POST", "/api/auth/password-reset/complete", EVERYONE),
    MatrixRow("identity", API, "GET", "/api/me", SIGNED_IN),
    MatrixRow("identity", API, "GET", "/api/me/profile", CUSTOMER_ONLY),
    MatrixRow("identity", API, "PATCH", "/api/me/profile", CUSTOMER_ONLY),
    MatrixRow("identity", API, "GET", "/api/customers", STAFF),
    MatrixRow("identity", API, "POST", "/api/customers", STAFF),
    MatrixRow("identity", API, "GET", f"/api/customers/{NOBODYS_KEY}", STAFF),
    MatrixRow("booking", API, "GET", "/api/reservations", SIGNED_IN),
    MatrixRow("booking", API, "POST", "/api/reservations", SIGNED_IN),
    MatrixRow("hire", API, "GET", f"/api/reservations/{NOBODYS_KEY}/checkout", STAFF),
    MatrixRow("hire", API, "POST", f"/api/reservations/{NOBODYS_KEY}/checkout", STAFF),
    MatrixRow("hire", API, "GET", f"/api/rentals/{NOBODYS_KEY}", STAFF),
    MatrixRow("hire", API, "GET", "/api/rentals", STAFF),
    MatrixRow("hire", API, "POST", f"/api/rentals/{NOBODYS_KEY}/returns", STAFF),
    MatrixRow("hire", API, "POST", f"/api/rentals/{NOBODYS_KEY}/balance-payment", STAFF),
    MatrixRow(
        "hire", API, "POST", f"/api/rentals/{NOBODYS_KEY}/items/{NOBODYS_KEY}/loss", STAFF
    ),
    MatrixRow("hire", API, "GET", "/api/me/rentals", CUSTOMER_ONLY),
    MatrixRow("hire", API, "POST", "/api/damage-reports", STAFF),
    MatrixRow("hire", API, "GET", "/api/damage-reports", STAFF),
    MatrixRow("hire", API, "GET", f"/api/damage-reports/{NOBODYS_KEY}", STAFF),
    MatrixRow("hire", API, "POST", f"/api/damage-reports/{NOBODYS_KEY}/repair", ADMIN_ONLY),
    MatrixRow("hire", API, "POST", f"/api/damage-reports/{NOBODYS_KEY}/resolution", ADMIN_ONLY),
    MatrixRow("hire", API, "GET", "/api/counter/dashboard", STAFF),
    MatrixRow("hire", API, "GET", "/api/counter/diary", STAFF),
    MatrixRow("booking", API, "POST", f"/api/reservations/{NOBODYS_KEY}/no-show", STAFF),
    MatrixRow("catalogue", API, "GET", "/api/assets/locator", STAFF),
    MatrixRow("reporting", API, "GET", "/api/admin/reports/utilisation", ADMIN_ONLY),
    MatrixRow("reporting", API, "GET", "/api/admin/reports/utilisation.csv", ADMIN_ONLY),
    MatrixRow("reporting", API, "GET", "/api/admin/dashboard", ADMIN_ONLY),
    MatrixRow("audit", API, "GET", "/api/admin/audit-events", ADMIN_ONLY),
    MatrixRow("notification", API, "GET", "/api/admin/notifications", ADMIN_ONLY),
    MatrixRow(
        "notification", API, "POST", f"/api/admin/notifications/{NOBODYS_KEY}/resend", ADMIN_ONLY
    ),
    MatrixRow("hire", API, "POST", f"/api/admin/charges/{NOBODYS_KEY}/waiver", ADMIN_ONLY),
    MatrixRow("hire", API, "POST", f"/api/admin/charges/{NOBODYS_KEY}/reversal", ADMIN_ONLY),
    MatrixRow("hire", API, "POST", f"/api/admin/rentals/{NOBODYS_KEY}/adjustments", ADMIN_ONLY),
    MatrixRow(
        "availability", API, "POST", f"/api/admin/allocations/{NOBODYS_KEY}/release", ADMIN_ONLY
    ),
    MatrixRow("booking", API, "POST", f"/api/reservations/{NOBODYS_KEY}/reallocation", STAFF),
    MatrixRow("branches", API, "GET", "/api/branches", EVERYONE),
    MatrixRow("catalogue", API, "GET", "/api/catalogue/categories", EVERYONE),
    MatrixRow("availability", API, "GET", "/api/catalogue/availability", EVERYONE),
    MatrixRow("pricing", API, "GET", "/api/catalogue/models/any-model/quote", EVERYONE),
    MatrixRow("administrator only", PROBE, "GET", ADMIN_PATH, ADMIN_ONLY),
    MatrixRow("administrator, read again", PROBE, "GET", FRESH_ADMIN_PATH, ADMIN_ONLY),
    MatrixRow("counter and administrator", PROBE, "GET", COUNTER_PATH, STAFF),
    MatrixRow("customer only", PROBE, "GET", CUSTOMER_PATH, CUSTOMER_ONLY),
)

__all__ = ["API", "MATRIX", "NOBODYS_KEY", "PROBE", "Caller", "MatrixRow"]
