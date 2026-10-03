"""Paths, members and a few helpers for the tests of the counter's overview routes.

The clock of the booking tests stands still on Monday the second of March
2026 at ten in the morning in Cape Town. The branch closes at 17:00, which is
15:00 UTC, so `AFTER_CLOSING` is the moment a booking for today nobody
collected becomes a no show the next time the sweep runs.

The member sets are the ones the contract gives each shape, and nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, reservation_path

DASHBOARD_PATH: Final[str] = "/api/counter/dashboard"
DIARY_PATH: Final[str] = "/api/counter/diary"
LOCATOR_PATH: Final[str] = "/api/assets/locator"
NO_SHOW_REASON: Final[str] = "Nobody came by closing time and the phone went unanswered."
# A second after 17:00 in Cape Town on the day of the still clock.
AFTER_CLOSING: Final[datetime] = datetime(2026, 3, 2, 15, 0, 1, tzinfo=UTC)

DASHBOARD_MEMBERS: Final[frozenset[str]] = frozenset(
    {"branchCode", "branchName", "date", "counts", "collectionsDue", "returnsDue", "overdue"}
)
COUNTS_MEMBERS: Final[frozenset[str]] = frozenset(
    {"collectionsDue", "returnsDue", "overdue", "onHire", "quarantined"}
)
COLLECTION_DUE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "reservationId", "reference", "customerName", "customerPhone", "from", "to",
        "unitCount", "summary",
    }
)  # fmt: skip
RETURN_DUE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "rentalId", "reference", "customerName", "customerPhone", "dueBackOn", "itemsOut",
        "itemCount", "summary",
    }
)  # fmt: skip
OVERDUE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "rentalId", "reference", "customerName", "customerPhone", "dueBackOn", "daysOverdue",
        "itemsOut", "lateFeeAccrued",
    }
)  # fmt: skip
DIARY_MEMBERS: Final[frozenset[str]] = frozenset({"branchCode", "branchName", "days"})
DIARY_DAY_MEMBERS: Final[frozenset[str]] = frozenset({"date", "collections", "returns"})
DIARY_COLLECTION_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "reservationId", "reference", "status", "customerName", "customerPhone", "from", "to",
        "unitCount", "summary", "canMarkNoShow",
    }
)  # fmt: skip
DIARY_RETURN_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "rentalId", "reference", "status", "customerName", "customerPhone", "dueBackOn",
        "itemsOut", "itemCount", "summary",
    }
)  # fmt: skip
LOCATION_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "assetTag", "modelName", "modelSlug", "categoryName", "branchCode", "branchName",
        "status", "conditionGrade", "dueBackOn", "rentalReference",
    }
)  # fmt: skip
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})


def read_dashboard(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the dashboard as `account`."""
    return booking.client.get(DASHBOARD_PATH, params=params, headers=booking.headers(account))


def read_diary(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the diary as `account`."""
    return booking.client.get(DIARY_PATH, params=params, headers=booking.headers(account))


def locate(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Ask the asset locator as `account`."""
    return booking.client.get(LOCATOR_PATH, params=params, headers=booking.headers(account))


def no_show_path(key: object) -> str:
    """Return the path that marks a reservation as not collected."""
    return f"{reservation_path(key)}/no-show"


def mark_no_show(
    booking: BookingClient, account: UserAccount, key: object, reason: str = NO_SHOW_REASON
) -> Response:
    """Mark a reservation as not collected as `account`."""
    return booking.client.post(
        no_show_path(key), json={"reason": reason}, headers=booking.headers(account)
    )


__all__ = [
    "AFTER_CLOSING",
    "COLLECTION_DUE_MEMBERS",
    "COUNTS_MEMBERS",
    "DASHBOARD_MEMBERS",
    "DASHBOARD_PATH",
    "DIARY_COLLECTION_MEMBERS",
    "DIARY_DAY_MEMBERS",
    "DIARY_MEMBERS",
    "DIARY_PATH",
    "DIARY_RETURN_MEMBERS",
    "LOCATION_MEMBERS",
    "LOCATOR_PATH",
    "NO_SHOW_REASON",
    "OVERDUE_MEMBERS",
    "PAGE_MEMBERS",
    "RETURN_DUE_MEMBERS",
    "locate",
    "mark_no_show",
    "no_show_path",
    "read_dashboard",
    "read_diary",
]
