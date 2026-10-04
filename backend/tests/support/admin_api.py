"""Paths, members and helpers for the tests of the admin operations.

The clock of the booking tests stands still on Monday the second of March 2026
at ten in the morning in Cape Town. A hire booked for today at the counter can
be checked out at once, so a test starts from a rental that is out, or from a
confirmed booking whose units the checkout read lists with their allocations.

The member sets are the ones the contract gives each shape, and nothing else.
Request bodies are built in the camelCase names the React client posts.
"""

from __future__ import annotations

from typing import Final

from httpx import Response
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus
from app.infrastructure.models import Asset, UserAccount
from tests.support.booking_api import BookingClient, answered, reservation_path
from tests.support.checkout_api import read_checkout

AUDIT_EVENTS_PATH: Final[str] = "/api/admin/audit-events"
NOTIFICATIONS_PATH: Final[str] = "/api/admin/notifications"
REASON: Final[str] = "The customer was told the fee would not be charged."

AUDIT_EVENT_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "occurredAt", "actorUserId", "actorName", "actorRole", "entityType", "entityId",
        "action", "beforeState", "afterState", "requestId",
    }
)  # fmt: skip
NOTIFICATION_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "reservationId", "reservationReference", "type", "recipientEmail", "subject",
        "status", "attempts", "lastError", "queuedAt", "sentAt", "resendOf",
    }
)  # fmt: skip
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})


def waiver_path(charge_id: object) -> str:
    """Return the path that waives a charge."""
    return f"/api/admin/charges/{charge_id}/waiver"


def reversal_path(charge_id: object) -> str:
    """Return the path that reverses a charge."""
    return f"/api/admin/charges/{charge_id}/reversal"


def adjustments_path(rental_key: object) -> str:
    """Return the path that adjusts a rental."""
    return f"/api/admin/rentals/{rental_key}/adjustments"


def release_path(allocation_id: object) -> str:
    """Return the path that releases one allocation by hand."""
    return f"/api/admin/allocations/{allocation_id}/release"


def reallocation_path(reservation_key: object) -> str:
    """Return the path that gives a short reservation replacement units."""
    return f"{reservation_path(reservation_key)}/reallocation"


def resend_path(notification_id: object) -> str:
    """Return the path that sends a failed notification again."""
    return f"{NOTIFICATIONS_PATH}/{notification_id}/resend"


def waive(
    booking: BookingClient, account: UserAccount, charge_id: object, reason: object = REASON
) -> Response:
    """Waive a charge as `account`."""
    return booking.client.post(
        waiver_path(charge_id), json={"reason": reason}, headers=booking.headers(account)
    )


def reverse(
    booking: BookingClient, account: UserAccount, charge_id: object, reason: object = REASON
) -> Response:
    """Reverse a charge as `account`."""
    return booking.client.post(
        reversal_path(charge_id), json={"reason": reason}, headers=booking.headers(account)
    )


def adjust(
    booking: BookingClient,
    account: UserAccount,
    rental_key: object,
    amount: object,
    reason: object = REASON,
) -> Response:
    """Adjust a rental by an amount that includes VAT, as `account`."""
    return booking.client.post(
        adjustments_path(rental_key),
        json={"amountIncVat": amount, "reason": reason},
        headers=booking.headers(account),
    )


def release(
    booking: BookingClient, account: UserAccount, allocation_id: object, reason: object = REASON
) -> Response:
    """Release one allocation by hand as `account`."""
    return booking.client.post(
        release_path(allocation_id), json={"reason": reason}, headers=booking.headers(account)
    )


def reallocate(booking: BookingClient, account: UserAccount, reservation_key: object) -> Response:
    """Ask for replacement units for a reservation as `account`."""
    return booking.client.post(
        reallocation_path(reservation_key), headers=booking.headers(account)
    )


def read_audit(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the audit log as `account`."""
    return booking.client.get(AUDIT_EVENTS_PATH, params=params, headers=booking.headers(account))


def read_notifications(
    booking: BookingClient, account: UserAccount, **params: object
) -> Response:
    """Read the notification log as `account`."""
    return booking.client.get(
        NOTIFICATIONS_PATH, params=params, headers=booking.headers(account)
    )


def resend(booking: BookingClient, account: UserAccount, notification_id: object) -> Response:
    """Send a failed notification again as `account`."""
    return booking.client.post(resend_path(notification_id), headers=booking.headers(account))


def held_units(
    booking: BookingClient, account: UserAccount, reservation_key: object
) -> list[dict[str, object]]:
    """Return the units the checkout read lists for a reservation, with their allocations."""
    units = answered(read_checkout(booking, account, reservation_key))["units"]
    assert isinstance(units, list)
    return units


def take_out_of_service(session: Session, asset_tag: object) -> None:
    """Move a unit to QUARANTINED and commit it, so no booking can be given it."""
    unit = session.exec(select(Asset).where(col(Asset.asset_tag) == asset_tag)).one()
    unit.status = AssetStatus.QUARANTINED
    session.add(unit)
    session.commit()


def charge_of(rental: dict[str, object], charge_type: str) -> dict[str, object]:
    """Return the one charge of a type on a rental."""
    charges = rental["charges"]
    assert isinstance(charges, list)
    (found,) = [charge for charge in charges if charge["type"] == charge_type]
    assert isinstance(found, dict)
    return found


__all__ = [
    "AUDIT_EVENTS_PATH",
    "AUDIT_EVENT_MEMBERS",
    "NOTIFICATIONS_PATH",
    "NOTIFICATION_MEMBERS",
    "PAGE_MEMBERS",
    "REASON",
    "adjust",
    "adjustments_path",
    "charge_of",
    "held_units",
    "read_audit",
    "read_notifications",
    "reallocate",
    "reallocation_path",
    "release",
    "release_path",
    "resend",
    "resend_path",
    "reversal_path",
    "reverse",
    "take_out_of_service",
    "waive",
    "waiver_path",
]
