"""Paths, bodies and helpers for the tests of damage reports and quarantine.

The clock of the booking tests stands still on Monday the second of March 2026.
`returned_worse` puts a hire of one unit out and takes it back a grade worse,
so a test starts from a unit in quarantine whose deposit waits for its report.
The world's model is worth R4,200.00 and holds a deposit of R1,200.00, which
is what a recovery is capped at and what the deposit can pay.

Request bodies are built in the camelCase names the React client posts. A test
that wants a member left out removes it from the body it was given.
"""

from __future__ import annotations

from typing import Final

from httpx import Response
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus
from app.infrastructure.models import Asset, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.http import problem_of
from tests.support.rental_api import item_ids, on_hire, return_body, take_back

DAMAGE_REPORTS_PATH: Final[str] = "/api/damage-reports"
UNPROCESSABLE: Final[int] = 422
DESCRIPTION: Final[str] = "Cracked gearbox housing"
REPAIR_ESTIMATE: Final[str] = "450.00"
# The members the contract gives a damage report, and nothing else.
REPORT_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "reference", "assetTag", "modelName", "branchCode", "rentalId", "rentalReference",
        "rentalItemId", "severity", "status", "description", "repairEstimate", "actualRepairCost",
        "chargeableToCustomer", "recoveryCharged", "replacementValue", "reportedAt",
        "reportedByName", "resolvedAt", "resolutionNotes",
    }
)  # fmt: skip


def report_path(key: object) -> str:
    """Return the path of one report, by its key or its reference."""
    return f"{DAMAGE_REPORTS_PATH}/{key}"


def report_body(
    asset_tag: object,
    *,
    chargeable: bool,
    rental_item_id: object | None = None,
    recovery_amount: str | None = None,
    **changes: object,
) -> dict[str, object]:
    """Return the report the counter posts about one unit."""
    return {
        "assetTag": asset_tag,
        "rentalItemId": None if rental_item_id is None else str(rental_item_id),
        "severity": "MINOR",
        "description": DESCRIPTION,
        "repairEstimate": REPAIR_ESTIMATE,
        "chargeableToCustomer": chargeable,
        "recoveryAmount": recovery_amount,
        **changes,
    }


def file_report(booking: BookingClient, account: UserAccount, body: dict[str, object]) -> Response:
    """Post a damage report as `account`."""
    return booking.client.post(DAMAGE_REPORTS_PATH, json=body, headers=booking.headers(account))


def read_report(booking: BookingClient, account: UserAccount, key: object) -> Response:
    """Read one damage report as `account`."""
    return booking.client.get(report_path(key), headers=booking.headers(account))


def list_reports(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """List damage reports as `account`."""
    return booking.client.get(DAMAGE_REPORTS_PATH, params=params, headers=booking.headers(account))


def send_for_repair(booking: BookingClient, account: UserAccount, key: object) -> Response:
    """Send a report for repair as `account`."""
    return booking.client.post(f"{report_path(key)}/repair", headers=booking.headers(account))


def close_report(
    booking: BookingClient, account: UserAccount, key: object, body: dict[str, object]
) -> Response:
    """Close a report as `account`."""
    return booking.client.post(
        f"{report_path(key)}/resolution", json=body, headers=booking.headers(account)
    )


def returned_worse(
    booking: BookingClient, world: BookingWorld, staff: UserAccount, **changes: object
) -> dict[str, object]:
    """Put one unit out today and take it back a grade worse, and return the rental."""
    rental = on_hire(booking, world, staff)
    body = return_body(*item_ids(rental), conditionIn="B", **changes)
    return answered(take_back(booking, staff, rental["id"], body))


def only_item(rental: dict[str, object]) -> dict[str, object]:
    """Return the one item of a rental of one unit."""
    items = rental["items"]
    assert isinstance(items, list) and len(items) == 1, items
    item = items[0]
    assert isinstance(item, dict)
    return item


def refused_fields(response: Response) -> dict[str, str]:
    """Return the sentence of every field a 422 named, keyed by where the field travelled."""
    assert response.status_code == UNPROCESSABLE, response.text
    errors = problem_of(response)["errors"]
    assert isinstance(errors, dict)
    fields = errors["fields"]
    assert isinstance(fields, dict)
    return {str(name): str(sentence) for name, sentence in fields.items()}


def refusal_of(response: Response, status_code: int) -> str:
    """Return the sentence of a refusal, checking its status first."""
    assert response.status_code == status_code, response.text
    return str(problem_of(response)["detail"])


def unit_status(session: Session, asset_tag: object) -> AssetStatus:
    """Return the status the database holds for a unit, read again."""
    unit = session.exec(select(Asset).where(col(Asset.asset_tag) == asset_tag)).one()
    session.refresh(unit)
    return unit.status


__all__ = [
    "DAMAGE_REPORTS_PATH",
    "DESCRIPTION",
    "REPAIR_ESTIMATE",
    "REPORT_MEMBERS",
    "close_report",
    "file_report",
    "list_reports",
    "only_item",
    "read_report",
    "refusal_of",
    "refused_fields",
    "report_body",
    "report_path",
    "returned_worse",
    "send_for_repair",
    "unit_status",
]
