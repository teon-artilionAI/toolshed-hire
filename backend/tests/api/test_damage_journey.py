"""The whole path of a damaged return, through HTTP, from checkout to a settled deposit.

A counter assistant checks a unit out with a deposit of R1,200.00 and takes it
back the same day one grade worse. The unit goes to quarantine and the deposit
waits for the damage report. The assistant files a report that charges the
customer R450.00, under the R4,200.00 replacement value, and the deposit is
settled in the same transaction with the recovery withheld. R450.00 is stored
as R391.30 plus R58.70 VAT, R750.00 is released and nothing is due. An
administrator then resolves the report and the unit is back on the shelf.

It runs against the in memory database on a clock that stands still on Monday
the second of March 2026.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import AuditEvent, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.checkout_api import read_rental
from tests.support.damage_api import (
    close_report,
    file_report,
    only_item,
    read_report,
    report_body,
    returned_worse,
    unit_status,
)
from tests.support.factories import Factory
from tests.support.rental_api import charges_of, worked_example_world


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of one unit with the deposit of the worked example."""
    return worked_example_world(session, factory)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def test_a_damaged_return_is_charged_and_settled_and_the_unit_comes_back(
    booking: BookingClient,
    world: BookingWorld,
    assistant: UserAccount,
    administrator: UserAccount,
    session: Session,
) -> None:
    back = returned_worse(booking, world, assistant)
    item = only_item(back)
    assert (back["depositHeld"], back["depositWithheld"], back["depositRefunded"]) == (
        "1200.00", "0.00", "0.00"
    )
    assert (back["status"], back["settlementWaitingOn"], item["damageAssessment"]) == (
        "RETURNED", "DAMAGE_ASSESSMENT", "REQUIRED"
    )
    assert unit_status(session, item["assetTag"]) is AssetStatus.QUARANTINED
    assert item["replacementValue"] == "4200.00"

    body = report_body(
        item["assetTag"], chargeable=True, rental_item_id=item["id"], recovery_amount="450.00"
    )
    report = created(file_report(booking, assistant, body))
    assert (report["recoveryCharged"], report["replacementValue"]) == ("450.00", "4200.00")
    assert report["rentalReference"] == back["reference"]

    settled = answered(read_rental(booking, assistant, back["id"]))
    assert (settled["depositWithheld"], settled["depositRefunded"], settled["balanceDue"]) == (
        "450.00", "750.00", "0.00"
    )
    assert (settled["status"], settled["settlementWaitingOn"]) == ("SETTLED", None)
    assert settled["settledAt"] == "2026-03-02T10:00:00+02:00"
    assert only_item(settled)["damageAssessment"] == "DONE"
    (recovery,) = charges_of(settled, "DAMAGE_RECOVERY")
    assert (recovery["amountExVat"], recovery["vatAmount"], recovery["amountIncVat"]) == (
        "391.30", "58.70", "450.00"
    )
    assert (recovery["status"], recovery["rentalItemId"]) == ("SETTLED", item["id"])
    (release,) = charges_of(settled, "DEPOSIT_RELEASE")
    assert (release["amountIncVat"], release["description"]) == (
        "-750.00", "Deposit released after R450.00 was withheld"
    )
    actions = {event.action for event in session.exec(select(AuditEvent))}
    assert {"damage_report.filed", "rental.damage_assessed", "rental.deposit_settled"} <= actions

    body = {"outcome": "RESOLVED", "actualRepairCost": "380.00", "resolutionNotes": "New housing"}
    answered(close_report(booking, administrator, report["id"], body))
    assert unit_status(session, item["assetTag"]) is AssetStatus.AVAILABLE
    closed = answered(read_report(booking, assistant, report["reference"]))
    assert (closed["status"], closed["actualRepairCost"]) == ("RESOLVED", "380.00")
