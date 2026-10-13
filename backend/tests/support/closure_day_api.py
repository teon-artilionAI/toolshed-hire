"""Paths, members, bodies and helpers for the tests of the owner's closure days.

The member sets are the ones the contract gives each answer, and nothing else.
A body is built in the camelCase names the React client posts, as one that
keeps every rule, and a test changes the one member it is about. The helpers
drive the four routes as a chosen account through a `BookingClient`, so they
work on the in memory database and on PostgreSQL alike.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient

CLOSURE_DAYS_PATH: Final[str] = "/api/admin/closure-days"
IMPACT_PATH: Final[str] = f"{CLOSURE_DAYS_PATH}/impact"
# A Friday, eighteen days after the still clock's Monday 2 March 2026.
STOCKTAKE_DAY: Final[date] = date(2026, 3, 20)
STOCKTAKE: Final[str] = "Stocktake"

CLOSURE_MEMBERS: Final[frozenset[str]] = frozenset(
    {"id", "branchCode", "day", "reason", "createdAt", "cancelledAt"}
)
CLOSED_DAY_MEMBERS: Final[frozenset[str]] = frozenset(
    {"day", "branchCode", "reason", "kind", "closureId"}
)
STRANDED_MEMBERS: Final[frozenset[str]] = frozenset(
    {"reference", "branchCode", "customerName", "customerPhone", "from", "to", "hireDay"}
)


def cancel_path(closure_id: object) -> str:
    """Return the path that cancels a closure day."""
    return f"{CLOSURE_DAYS_PATH}/{closure_id}/cancel"


def closure_body(branch_code: str | None, **members: object) -> dict[str, object]:
    """Return the body of a stocktake on the twentieth, with any member changed."""
    return {
        "branchCode": branch_code,
        "day": STOCKTAKE_DAY.isoformat(),
        "reason": STOCKTAKE,
        **members,
    }


def add_closure(booking: BookingClient, account: UserAccount, body: dict[str, object]) -> Response:
    """Close a day as `account`."""
    return booking.client.post(CLOSURE_DAYS_PATH, json=body, headers=booking.headers(account))


def cancel_closure(booking: BookingClient, account: UserAccount, closure_id: object) -> Response:
    """Cancel a closure day as `account`."""
    return booking.client.post(cancel_path(closure_id), headers=booking.headers(account))


def list_closed_days(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the closed days as `account`."""
    return booking.client.get(CLOSURE_DAYS_PATH, params=params, headers=booking.headers(account))


def read_impact(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the bookings a closure would strand as `account`."""
    return booking.client.get(IMPACT_PATH, params=params, headers=booking.headers(account))


__all__ = [
    "CLOSED_DAY_MEMBERS",
    "CLOSURE_DAYS_PATH",
    "CLOSURE_MEMBERS",
    "IMPACT_PATH",
    "STOCKTAKE",
    "STOCKTAKE_DAY",
    "STRANDED_MEMBERS",
    "add_closure",
    "cancel_closure",
    "cancel_path",
    "closure_body",
    "list_closed_days",
    "read_impact",
]
