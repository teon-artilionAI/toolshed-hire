"""Paths, members, bodies and helpers for the tests of the asset register routes.

The member sets are the ones the contract gives `AdminAsset` and its history,
and nothing else. A body is built in the camelCase names the React client
posts, as one that keeps every rule, and a test changes the one member it is
about. Money is written as a string, as the contract asks.

The routes are driven through `BookingClient`, which signs a request in as a
chosen account on the still clock of Monday the second of March 2026, so these
work on the in memory database and on PostgreSQL alike.
"""

from __future__ import annotations

from typing import Final

from httpx import Response
from sqlmodel import Session, col, select

from app.infrastructure.models import (
    Asset,
    AuditEvent,
    Reservation,
    ReservationLine,
    UserAccount,
)
from tests.support.booking_api import BookingClient
from tests.support.http import problem_of

ASSETS_PATH: Final[str] = "/api/admin/assets"
NEW_TAG: Final[str] = "TSH-DR-0099"
REASON: Final[str] = "Failed its inspection on arrival."

ASSET_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "assetTag", "modelId", "modelName", "modelSlug", "categoryName", "branchCode",
        "branchName", "serialNumber", "status", "conditionGrade", "acquiredOn",
        "acquisitionCost", "hourMeterReading", "notes", "retiredOn", "activeAllocationCount",
        "openDamageReports", "allowedTransitions",
    }
)  # fmt: skip
DETAIL_MEMBERS: Final[frozenset[str]] = ASSET_MEMBERS | {"history"}
HISTORY_MEMBERS: Final[frozenset[str]] = frozenset({"at", "kind", "summary", "reference"})


def asset_path(tag: object) -> str:
    """Return the path of one unit, by its tag."""
    return f"{ASSETS_PATH}/{tag}"


def transitions_path(tag: object) -> str:
    """Return the path that moves a unit through its lifecycle."""
    return f"{asset_path(tag)}/transitions"


def asset_body(model_id: object, branch_code: str, **members: object) -> dict[str, object]:
    """Return the body of a new hammer at a branch, with any member changed."""
    return {
        "assetTag": NEW_TAG,
        "modelId": str(model_id),
        "branchCode": branch_code,
        "serialNumber": "SN-882731",
        "conditionGrade": "A",
        "acquiredOn": "2026-02-01",
        "acquisitionCost": "3900.00",
        "hourMeterReading": None,
        "notes": None,
        **members,
    }


def list_assets(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the register as `account`."""
    return booking.client.get(ASSETS_PATH, params=params, headers=booking.headers(account))


def read_asset(booking: BookingClient, account: UserAccount, tag: object) -> Response:
    """Read one unit with its history as `account`."""
    return booking.client.get(asset_path(tag), headers=booking.headers(account))


def create_asset(
    booking: BookingClient, account: UserAccount, body: dict[str, object]
) -> Response:
    """Register a unit as `account`."""
    return booking.client.post(ASSETS_PATH, json=body, headers=booking.headers(account))


def edit_asset(
    booking: BookingClient, account: UserAccount, tag: object, body: dict[str, object]
) -> Response:
    """Edit the paperwork of a unit as `account`."""
    return booking.client.patch(asset_path(tag), json=body, headers=booking.headers(account))


def move_asset(
    booking: BookingClient,
    account: UserAccount,
    tag: object,
    to: object,
    reason: object | None = REASON,
) -> Response:
    """Move a unit through its lifecycle as `account`."""
    return booking.client.post(
        transitions_path(tag), json={"to": to, "reason": reason}, headers=booking.headers(account)
    )


def stored_tags(session: Session) -> list[str]:
    """Return the tags of every stored unit."""
    return list(session.exec(select(Asset.asset_tag)).all())


def stored_events(session: Session) -> list[str]:
    """Return the action of every stored audit event about a unit."""
    statement = select(AuditEvent.action).where(col(AuditEvent.entity_type) == "asset")
    return list(session.exec(statement).all())


def refused_with(response: Response, status_code: int) -> dict[str, object]:
    """Return the problem document of a refusal, checking its status first."""
    assert response.status_code == status_code, response.text
    return problem_of(response)


def booking_holding(session: Session, line_id: object) -> str:
    """Return the reference of the booking a reservation line belongs to."""
    line = session.get(ReservationLine, line_id)
    assert line is not None
    reservation = session.get(Reservation, line.reservation_id)
    assert reservation is not None
    return reservation.reference


__all__ = [
    "ASSETS_PATH",
    "ASSET_MEMBERS",
    "DETAIL_MEMBERS",
    "HISTORY_MEMBERS",
    "NEW_TAG",
    "REASON",
    "asset_body",
    "asset_path",
    "booking_holding",
    "create_asset",
    "edit_asset",
    "list_assets",
    "move_asset",
    "read_asset",
    "refused_with",
    "stored_events",
    "stored_tags",
    "transitions_path",
]
