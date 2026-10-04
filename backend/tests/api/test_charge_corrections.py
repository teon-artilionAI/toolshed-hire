"""Waiving, reversing and adjusting the money of a hire, through HTTP (BR-24, BR-25, US-28).

An administrator corrects a charge, and the deposit, the balance and the
status of the hire are worked out again by the settlement. These follow the
worked example's model through the routes. A hire back two days late owes
R240.00 and is settled from its deposit of R1,200.00, and one back fourteen
days late owes R1,680.00 and is left R480.00 to pay. What is pinned is what
each correction writes, what it leaves exactly as it was, what happens to a
hire already settled, and the audit event it writes in the same transaction.

The refusals are in tests/api/test_charge_correction_refusals.py. These run
against the in memory database, and the clock stands still on Monday the
second of March 2026 until a test moves it.
"""

from __future__ import annotations

import pytest
from fastapi import status
from sqlmodel import Session

from app.application.hire.charge_corrections import (
    CHARGE_ADJUSTED_ACTION,
    CHARGE_REVERSED_ACTION,
    CHARGE_WAIVED_ACTION,
)
from app.application.hire.rental_audit import RENTAL_SETTLEMENT_REWORKED_ACTION
from app.domain.charge_corrections import (
    CREDIT_DESCRIPTION,
    REVERSAL_PREFIX,
    SETTLED_HIRE_MESSAGE,
)
from app.domain.enums import UserRole
from tests.support.admin_api import REASON, adjust, charge_of, reverse, waive
from tests.support.booking_api import BookingClient, answered
from tests.support.checkout_api import read_rental
from tests.support.correction_api import (
    FOURTEEN_DAYS_LATE,
    TWO_DAYS_LATE,
    Desk,
    charges_of_type,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.rental_api import (
    item_ids,
    on_hire,
    pay_balance,
    return_body,
    take_back,
    worked_example_world,
)


@pytest.fixture
def desk(booking: BookingClient, session: Session, factory: Factory) -> Desk:
    """Return two units of the worked example, a counter assistant and an administrator."""
    world = worked_example_world(session, factory, units=2)
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    administrator = factory.user(role=UserRole.ADMIN)
    session.commit()
    return Desk(booking, session, world, assistant, administrator)


class TestAWaiver:
    """A charge still owed is let go with a reason, and a settled one never is."""

    def test_a_late_fee_on_a_hire_still_partly_out_is_waived_and_nothing_else_moves(
        self, desk: Desk
    ) -> None:
        rental = desk.partly_back_late()
        fee = charge_of(rental, "LATE_FEE")
        after = answered(waive(desk.booking, desk.administrator, fee["id"]))

        waived = charge_of(after, "LATE_FEE")
        assert (waived["status"], waived["reason"], waived["amountIncVat"]) == (
            "WAIVED", REASON, "240.00"
        )
        assert (after["status"], after["settlementWaitingOn"]) == (
            rental["status"], "ITEMS_OUT"
        )
        assert (after["depositWithheld"], after["balanceDue"]) == ("0.00", "0.00")

    def test_the_settlement_that_follows_leaves_the_waived_fee_out(self, desk: Desk) -> None:
        rental = desk.partly_back_late()
        answered(waive(desk.booking, desk.administrator, charge_of(rental, "LATE_FEE")["id"]))
        last = item_ids(rental)[1]
        back = answered(take_back(desk.booking, desk.assistant, rental["id"], return_body(last)))

        assert (back["depositWithheld"], back["depositRefunded"]) == ("240.00", "2160.00")
        assert back["status"] == "SETTLED"
        assert sorted(fee["status"] for fee in charges_of_type(back, "LATE_FEE")) == [
            "SETTLED", "WAIVED"
        ]

    def test_waiving_what_a_balance_waits_on_settles_the_hire_and_releases_the_deposit(
        self, desk: Desk
    ) -> None:
        rental = desk.returned(FOURTEEN_DAYS_LATE)
        assert (rental["status"], rental["balanceDue"], rental["depositWithheld"]) == (
            "RETURNED", "480.00", "1200.00"
        )
        after = answered(
            waive(desk.booking, desk.administrator, charge_of(rental, "LATE_FEE")["id"])
        )

        assert (after["status"], after["balanceDue"], after["settlementWaitingOn"]) == (
            "SETTLED", "0.00", None
        )
        assert (after["depositWithheld"], after["depositRefunded"]) == ("0.00", "1200.00")
        assert after["settledAt"] == after["returnedAt"]
        release = charge_of(after, "DEPOSIT_RELEASE")
        assert (release["amountIncVat"], release["status"]) == ("-1200.00", "SETTLED")


class TestAReversal:
    """A settled charge is undone by a new negated one, and the original is never touched."""

    def test_the_worked_example_late_fee_is_reversed_and_the_hire_stays_settled(
        self, desk: Desk
    ) -> None:
        rental = desk.returned(TWO_DAYS_LATE)
        original = charge_of(rental, "LATE_FEE")
        after = answered(reverse(desk.booking, desk.administrator, original["id"]))

        kept, reversal = charges_of_type(after, "LATE_FEE")
        assert kept == original
        assert (reversal["amountExVat"], reversal["vatAmount"], reversal["amountIncVat"]) == (
            "-208.70", "-31.30", "-240.00"
        )
        assert (reversal["vatRate"], reversal["status"], reversal["reason"]) == (
            "15.00", "SETTLED", REASON
        )
        assert reversal["reversesChargeId"] == original["id"]
        assert reversal["rentalItemId"] == original["rentalItemId"]
        assert str(reversal["description"]).startswith(REVERSAL_PREFIX)
        assert (after["status"], after["settledAt"]) == ("SETTLED", rental["settledAt"])
        assert (after["depositWithheld"], after["depositRefunded"], after["balanceDue"]) == (
            "240.00", "960.00", "0.00"
        )

    def test_reversing_the_hire_charge_of_a_hire_still_out_is_set_against_its_return(
        self, desk: Desk
    ) -> None:
        rental = on_hire(desk.booking, desk.world, desk.assistant)
        hire = charge_of(rental, "HIRE")
        after = answered(reverse(desk.booking, desk.administrator, hire["id"]))
        _, credit = charges_of_type(after, "HIRE")
        assert (credit["status"], credit["amountIncVat"]) == (
            "PENDING", f"-{hire['amountIncVat']}"
        )

        desk.booking.clock.advance(TWO_DAYS_LATE)
        back = answered(
            take_back(desk.booking, desk.assistant, rental["id"], return_body(*item_ids(rental)))
        )
        _, settled_credit = charges_of_type(back, "HIRE")
        assert settled_credit["status"] == charge_of(back, "LATE_FEE")["status"] == "SETTLED"
        assert (back["depositWithheld"], back["depositRefunded"]) == ("0.00", "1200.00")
        assert (back["status"], back["balanceDue"]) == ("SETTLED", "0.00")


class TestAnAdjustment:
    """A new ADJUSTMENT charge, VAT inclusive, that the settlement counts like a late fee."""

    def test_an_amount_owed_is_refused_on_a_settled_hire_and_nothing_changes(
        self, desk: Desk
    ) -> None:
        rental = desk.returned(TWO_DAYS_LATE)
        refused = adjust(desk.booking, desk.administrator, rental["id"], "150.00")

        assert refused.status_code == status.HTTP_409_CONFLICT
        assert problem_code(refused) == "state-transition"
        assert problem_of(refused)["detail"] == SETTLED_HIRE_MESSAGE
        after = answered(read_rental(desk.booking, desk.administrator, rental["id"]))
        unchanged = ("status", "balanceDue", "settledAt", "depositWithheld", "charges")
        assert {key: after[key] for key in unchanged} == {key: rental[key] for key in unchanged}

    def test_a_credit_on_a_settled_hire_is_paid_back_and_it_stays_settled(
        self, desk: Desk
    ) -> None:
        rental = desk.returned(TWO_DAYS_LATE)
        after = answered(adjust(desk.booking, desk.administrator, rental["id"], "-150.00"))

        credit = charge_of(after, "ADJUSTMENT")
        assert (credit["amountExVat"], credit["vatAmount"], credit["amountIncVat"]) == (
            "-130.43", "-19.57", "-150.00"
        )
        assert (credit["status"], credit["reason"]) == ("SETTLED", REASON)
        assert (after["status"], after["balanceDue"], after["settledAt"]) == (
            "SETTLED", "0.00", rental["settledAt"]
        )
        assert (after["depositWithheld"], after["depositRefunded"]) == ("240.00", "960.00")

    def test_a_credit_lowers_a_balance_due(self, desk: Desk) -> None:
        rental = desk.returned(FOURTEEN_DAYS_LATE)
        after = answered(adjust(desk.booking, desk.administrator, rental["id"], "-100.00"))

        credit = charge_of(after, "ADJUSTMENT")
        assert (credit["amountExVat"], credit["vatAmount"], credit["amountIncVat"]) == (
            "-86.96", "-13.04", "-100.00"
        )
        assert credit["description"] == CREDIT_DESCRIPTION
        assert (after["status"], after["balanceDue"]) == ("RETURNED", "380.00")
        paid = answered(pay_balance(desk.booking, desk.assistant, rental["id"], "EFT-0043"))
        assert (paid["status"], paid["balanceDue"]) == ("SETTLED", "0.00")

    def test_a_credit_on_a_hire_still_out_grows_the_deposit_released_at_its_return(
        self, desk: Desk
    ) -> None:
        rental = on_hire(desk.booking, desk.world, desk.assistant)
        answered(adjust(desk.booking, desk.administrator, rental["id"], "-100.00"))
        desk.booking.clock.advance(TWO_DAYS_LATE)
        back = answered(
            take_back(desk.booking, desk.assistant, rental["id"], return_body(*item_ids(rental)))
        )
        assert (back["depositWithheld"], back["depositRefunded"]) == ("140.00", "1060.00")
        assert (back["status"], charge_of(back, "ADJUSTMENT")["status"]) == ("SETTLED", "SETTLED")


class TestTheAuditTrail:
    """Each correction is recorded with its actor and its reason, in its own transaction."""

    def test_a_waiver_names_the_administrator_and_the_reason(self, desk: Desk) -> None:
        rental = desk.returned(FOURTEEN_DAYS_LATE)
        fee = charge_of(rental, "LATE_FEE")
        answered(waive(desk.booking, desk.administrator, fee["id"]))

        (event,) = desk.events(CHARGE_WAIVED_ACTION)
        assert (event.actor_user_id, event.actor_role) == (
            desk.administrator.id, UserRole.ADMIN
        )
        assert (event.entity_type, str(event.entity_id)) == ("charge", fee["id"])
        assert event.before_state == {"status": "PENDING"}
        assert (event.after_state or {})["reason"] == REASON
        assert (event.after_state or {})["status"] == "WAIVED"
        (rework,) = desk.events(RENTAL_SETTLEMENT_REWORKED_ACTION)
        assert (rework.after_state or {})["status"] == "SETTLED"

    def test_a_waiver_before_the_deposit_is_settled_reworks_nothing(self, desk: Desk) -> None:
        rental = desk.partly_back_late()
        answered(waive(desk.booking, desk.administrator, charge_of(rental, "LATE_FEE")["id"]))
        assert len(desk.events(CHARGE_WAIVED_ACTION)) == 1
        assert desk.events(RENTAL_SETTLEMENT_REWORKED_ACTION) == []

    def test_a_reversal_names_the_charge_it_reverses_and_the_new_one(self, desk: Desk) -> None:
        rental = desk.returned(TWO_DAYS_LATE)
        original = charge_of(rental, "LATE_FEE")
        after = answered(reverse(desk.booking, desk.administrator, original["id"]))
        reversal = charges_of_type(after, "LATE_FEE")[1]

        (event,) = desk.events(CHARGE_REVERSED_ACTION)
        assert str(event.entity_id) == original["id"]
        assert (event.after_state or {})["reversal_charge_id"] == reversal["id"]
        assert (event.after_state or {})["reason"] == REASON
        assert event.actor_user_id == desk.administrator.id
        assert len(desk.events(RENTAL_SETTLEMENT_REWORKED_ACTION)) == 1

    def test_an_adjustment_is_recorded_against_the_new_charge(self, desk: Desk) -> None:
        rental = desk.returned(TWO_DAYS_LATE)
        after = answered(adjust(desk.booking, desk.administrator, rental["id"], "-150.00"))

        (event,) = desk.events(CHARGE_ADJUSTED_ACTION)
        assert str(event.entity_id) == charge_of(after, "ADJUSTMENT")["id"]
        assert event.before_state is None
        assert (event.after_state or {})["amount_inc_vat"] == "-150.00"
        assert (event.after_state or {})["reason"] == REASON
        assert (event.after_state or {})["rental_status"] == "SETTLED"
