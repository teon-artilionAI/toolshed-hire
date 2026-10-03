"""Every refusal of a damage report as it is filed, through HTTP, and that it changes nothing.

The decision on the charge has no default, so a report without one is a 422
naming `chargeableToCustomer` (BR-40). The amount to recover follows from the
decision and stays at or under the replacement value copied onto the booking,
or it is a 422 naming `recoveryAmount` (BR-39). A unit on hire, a retired unit,
a unit that waits for the report of its own return and a hire already settled
are refused with 409, and a report at another branch with 403. The world's
model is worth R4,200.00.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlmodel import Session, select

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import DamageReport, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.damage_api import (
    close_report,
    file_report,
    only_item,
    refusal_of,
    refused_fields,
    report_body,
    returned_worse,
    unit_status,
)
from tests.support.factories import Factory
from tests.support.rental_api import (
    item_ids,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

TWO_UNITS: Final[int] = 2
CONFLICT: Final[int] = 409
FORBIDDEN: Final[int] = 403
UNKNOWN_KEY: Final[str] = "00000000-0000-4000-8000-000000000007"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the deposit of the worked example."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def reports_in(session: Session) -> int:
    """Return how many damage reports are stored."""
    return len(session.exec(select(DamageReport)).all())


class TestTheFieldsOfAReport:
    """Each wrong field is a 422 that names it, and nothing is stored."""

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"chargeableToCustomer": None}, "body.chargeableToCustomer"),
            ({"chargeableToCustomer": "true"}, "body.chargeableToCustomer"),
            ({"repairEstimate": 450}, "body.repairEstimate"),
            ({"repairEstimate": "4,50"}, "body.repairEstimate"),
            ({"description": "   "}, "body.description"),
            ({"severity": "SCRATCHED"}, "body.severity"),
            ({"assetTag": "TSH-NO-0000"}, "body.assetTag"),
            ({"photoPath": "a.jpg"}, "body.photoPath"),
        ],
        ids=["null decision", "decision as text", "amount as a number", "amount with a comma",
             "blank description", "unknown severity", "unknown tag", "a field it does not take"],
    )  # fmt: skip
    def test_a_wrong_field_is_named(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
        change: dict[str, object],
        field: str,
    ) -> None:
        body = {**report_body(world.assets[0].asset_tag, chargeable=False), **change}
        assert field in refused_fields(file_report(booking, assistant, body))
        assert reports_in(session) == 0

    def test_a_report_with_no_decision_is_refused_because_there_is_no_default(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        body = report_body(world.assets[0].asset_tag, chargeable=False)
        del body["chargeableToCustomer"]
        assert set(refused_fields(file_report(booking, assistant, body))) == {
            "body.chargeableToCustomer"
        }
        assert unit_status(session, world.assets[0].asset_tag) is AssetStatus.AVAILABLE


class TestTheAmountToRecover:
    """Required when charged on a hire, refused otherwise, and capped at the value."""

    @pytest.mark.parametrize(
        ("chargeable", "amount", "sentence"),
        [
            (True, None, "Enter the amount to recover"),
            (False, "100.00", "not charged for this damage"),
            (True, "0.00", "above R0.00"),
            (True, "4200.01", "cannot be more than R4200.00"),
        ],
        ids=["missing when charged", "given when not charged", "nothing", "above the value"],
    )
    def test_an_amount_that_does_not_follow_is_refused_by_name(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
        chargeable: bool,
        amount: str | None,
        sentence: str,
    ) -> None:
        item = only_item(returned_worse(booking, world, assistant))
        body = report_body(
            item["assetTag"],
            chargeable=chargeable,
            rental_item_id=item["id"],
            recovery_amount=amount,
        )
        fields = refused_fields(file_report(booking, assistant, body))
        assert sentence in fields["body.recoveryAmount"]
        assert reports_in(session) == 0

    def test_the_replacement_value_itself_may_be_recovered(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        item = only_item(returned_worse(booking, world, assistant))
        body = report_body(
            item["assetTag"], chargeable=True, rental_item_id=item["id"], recovery_amount="4200.00"
        )
        assert created(file_report(booking, assistant, body))["recoveryCharged"] == "4200.00"

    def test_an_amount_outside_a_hire_is_refused(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        body = report_body(world.assets[0].asset_tag, chargeable=True, recovery_amount="50.00")
        fields = refused_fields(file_report(booking, assistant, body))
        assert "outside a hire" in fields["body.recoveryAmount"]


class TestTheRentalItem:
    """The item has to be a hire of the unit the report is about."""

    def test_an_unknown_item_and_the_item_of_another_unit_are_refused(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant, quantity=TWO_UNITS)
        first, second = item_ids(rental)
        answered(take_back(booking, assistant, rental["id"], return_body(first, second)))
        tag = world.assets[0].asset_tag
        for item_key in (UNKNOWN_KEY, second):
            body = report_body(tag, chargeable=False, rental_item_id=item_key)
            assert set(refused_fields(file_report(booking, assistant, body))) == {
                "body.rentalItemId"
            }


class TestTheStandingOfTheUnitAndTheHire:
    """A unit on hire, retired or waiting for its return's report, and a settled hire."""

    def test_a_unit_out_on_hire_is_refused(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        rental = on_hire(booking, world, assistant)
        item = only_item(rental)
        body = report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"])
        assert "out on hire" in refusal_of(file_report(booking, assistant, body), CONFLICT)
        assert unit_status(session, item["assetTag"]) is AssetStatus.ON_HIRE

    def test_a_retired_unit_is_refused(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        factory.session.commit()
        tag = world.assets[0].asset_tag
        report = created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        answered(close_report(booking, administrator, report["id"], {"outcome": "WRITTEN_OFF"}))
        refused = file_report(booking, assistant, report_body(tag, chargeable=False))
        assert "is retired" in refusal_of(refused, CONFLICT)

    def test_a_unit_waiting_for_the_report_of_its_return_must_be_reported_from_it(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        back = returned_worse(booking, world, assistant)
        tag = only_item(back)["assetTag"]
        refused = file_report(booking, assistant, report_body(tag, chargeable=False))
        assert str(back["reference"]) in refusal_of(refused, CONFLICT)
        assert reports_in(session) == 0

    def test_a_charge_on_a_hire_already_settled_is_refused(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant)
        back = answered(take_back(booking, assistant, rental["id"], return_body(*item_ids(rental))))
        assert back["status"] == "SETTLED"
        item = only_item(back)
        body = report_body(
            item["assetTag"], chargeable=True, rental_item_id=item["id"], recovery_amount="10.00"
        )
        assert "already been settled" in refusal_of(file_report(booking, assistant, body), CONFLICT)

    def test_counter_staff_of_another_branch_are_refused(
        self, booking: BookingClient, world: BookingWorld, factory: Factory, session: Session
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        body = report_body(world.assets[0].asset_tag, chargeable=False)
        refusal_of(file_report(booking, elsewhere, body), FORBIDDEN)
        assert reports_in(session) == 0
