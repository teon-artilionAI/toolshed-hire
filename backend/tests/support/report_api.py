"""Paths, members and helpers for the tests of the report routes and the admin dashboard.

The clock of the booking tests stands still on Monday the second of March
2026 at ten in the morning in Cape Town, so the report of March is the month
the hires of those tests fall in.

The member sets are the ones the contract gives each shape, and nothing else.
"""

from __future__ import annotations

from typing import Final

from fastapi import status
from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient

REPORT_PATH: Final[str] = "/api/admin/reports/utilisation"
CSV_PATH: Final[str] = "/api/admin/reports/utilisation.csv"
ADMIN_DASHBOARD_PATH: Final[str] = "/api/admin/dashboard"
MARCH: Final[dict[str, str]] = {"from": "2026-03-01", "to": "2026-04-01"}

REPORT_MEMBERS: Final[frozenset[str]] = frozenset(
    {"from", "to", "groupBy", "definitions", "totals", "items", "page", "pageSize", "total"}
)
FIGURE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "assetCount", "daysOnHire", "serviceableDays", "utilisationPercent", "hireRevenueExVat",
        "lateFeesExVat", "damageRecoveryExVat", "repairCosts", "grossContribution",
    }
)  # fmt: skip
LINE_MEMBERS: Final[frozenset[str]] = FIGURE_MEMBERS | {
    "key", "label", "branchCode", "categoryName", "modelName", "assetTag", "status",
}  # fmt: skip
DASHBOARD_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "date", "branches", "totals", "monthToDate", "openDamageReports", "customersOnHold",
        "failedNotifications",
    }
)  # fmt: skip
COUNT_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "collectionsDue", "returnsDue", "overdue", "onHire", "quarantined", "underRepair",
        "available",
    }
)
BRANCH_MEMBERS: Final[frozenset[str]] = COUNT_MEMBERS | {"branchCode", "branchName"}
MONTH_MEMBERS: Final[frozenset[str]] = frozenset(
    {"from", "to", "utilisationPercent", "grossContribution"}
)


def read_report(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the report as `account`, for March unless the test names the period."""
    return booking.client.get(
        REPORT_PATH, params={**MARCH, **params}, headers=booking.headers(account)
    )


def read_csv(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the report as CSV as `account`, for March unless the test names the period."""
    return booking.client.get(
        CSV_PATH, params={**MARCH, **params}, headers=booking.headers(account)
    )


def read_admin_dashboard(booking: BookingClient, account: UserAccount) -> Response:
    """Read the admin dashboard as `account`."""
    return booking.client.get(ADMIN_DASHBOARD_PATH, headers=booking.headers(account))


def refused_fields(response: Response) -> set[str]:
    """Return the fields a 422 names under `errors.fields`."""
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    errors = response.json()["errors"]
    assert isinstance(errors, dict)
    return set(errors["fields"])
