"""Releasing a unit of a booking by hand and topping the booking up again (US-32, BR-08, BR-09).

The force release lets one active allocation of a booking on hold or confirmed
go with the reason REALLOCATED, and refuses one already released or a unit out
on hire on its booking. A booking short of a unit cannot be collected, and it
says how many it is short of. It is given replacements line by line through an
allocator, all or nothing. No database is used. The allocator here holds a
made up unit for whatever a line is short of, unless a test tells it to come
up short.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.hire.checkout_models import CheckoutCustomer, CheckoutDetail
from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation, ReservationLine
from app.domain.checkout import collection_refusal, ensure_collectable
from app.domain.enums import (
    AccountStatus,
    IdDocType,
    ReleaseReason,
    ReservationStatus,
)
from app.domain.errors import AllocationConflictError, StateTransitionError
from app.domain.reallocation import (
    ALREADY_RELEASED_MESSAGE,
    ON_HIRE_MESSAGE,
    force_release,
    give_replacement_units,
    units_missing_message,
    units_short_of,
)
from tests.support.checkout_domain import a_confirmed
from tests.support.reservations import (
    HIRE,
    NINTH,
    ONE_LINE,
    a_draft,
    a_reservation_in,
    an_allocation,
)

NOW: Final[datetime] = datetime(2026, 3, 9, 7, 0, tzinfo=UTC)
ONE_MISSING: Final[str] = (
    "One unit of this booking is missing. Allocate a replacement before the equipment is "
    "handed over."
)


class Allocator:
    """Holds a made up unit for every unit a line is short of, or fewer when told to."""

    def __init__(self, *, short_by: int = 0) -> None:
        """Remember how many fewer units than asked for each line is given."""
        self._short_by = short_by
        self.asked: list[int] = []

    def allocate(
        self, reservation: Reservation, line: ReservationLine
    ) -> Sequence[AssetAllocation]:
        """Return an allocation for each unit the line is short of, less the shortfall set."""
        self.asked.append(line.shortfall())
        return [
            an_allocation(line, branch_id=reservation.branch_id)
            for _ in range(line.shortfall() - self._short_by)
        ]


def released_one(reservation: Reservation) -> AssetAllocation:
    """Release the first unit of a reservation by hand and return its allocation."""
    first = reservation.lines[0].active_allocations()[0]
    return force_release(reservation, first.id, NOW)


class TestTheForceRelease:
    """One active allocation goes, with the reason REALLOCATED."""

    def test_a_confirmed_booking_lets_one_unit_go_and_is_short_of_it(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        assert units_short_of(reservation) == 0
        released = released_one(reservation)

        assert (released.released_at, released.release_reason) == (
            NOW, ReleaseReason.REALLOCATED
        )
        assert units_short_of(reservation) == 1
        assert reservation.lines[0].shortfall() == 1
        assert reservation.status is ReservationStatus.CONFIRMED

    def test_a_unit_already_released_is_refused(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        released = released_one(reservation)
        with pytest.raises(StateTransitionError, match=ALREADY_RELEASED_MESSAGE) as refused:
            force_release(reservation, released.id, NOW)
        assert refused.value.rule == "BR-44"

    def test_a_unit_out_on_hire_on_its_booking_is_refused(self) -> None:
        reservation = a_reservation_in(ReservationStatus.COLLECTED)
        first = reservation.lines[0].allocations[0]
        with pytest.raises(StateTransitionError, match=ON_HIRE_MESSAGE):
            force_release(reservation, first.id, NOW)
        assert first.is_active()

    def test_an_allocation_the_booking_does_not_hold_is_a_fault_in_the_caller(self) -> None:
        with pytest.raises(LookupError, match="does not hold it"):
            force_release(a_confirmed(ONE_LINE), uuid4(), NOW)


class TestAShortBookingIsNotCollected:
    """BR-08 holds at the counter as well as at the confirmation."""

    def test_the_sentence_says_how_many_are_missing(self) -> None:
        assert units_missing_message(1) == ONE_MISSING
        assert units_missing_message(3).startswith("3 units of this booking are missing.")

    def test_the_checkout_of_a_short_booking_is_refused_on_its_first_day(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        released_one(reservation)
        with pytest.raises(StateTransitionError, match=ONE_MISSING) as refused:
            ensure_collectable(reservation, NINTH)
        assert refused.value.detail == {"from_status": "CONFIRMED", "to_status": "COLLECTED"}

    def test_the_status_and_the_date_are_refused_before_the_missing_units(self) -> None:
        assert collection_refusal(ReservationStatus.CONFIRMED, NINTH, NINTH, 2) == (
            units_missing_message(2)
        )
        assert collection_refusal(ReservationStatus.CONFIRMED, NINTH, date(2026, 3, 8), 2) == (
            "This reservation cannot be collected before the first day of the hire."
        )
        assert collection_refusal(ReservationStatus.CONFIRMED, NINTH, NINTH) is None

    @pytest.mark.parametrize(
        ("status", "short"),
        [
            (ReservationStatus.CONFIRMED, 1),
            (ReservationStatus.HELD, 1),
            (ReservationStatus.COLLECTED, 0),
            (ReservationStatus.CANCELLED, 0),
        ],
    )
    def test_the_checkout_read_counts_the_missing_units_of_a_booking_waiting_for_them(
        self, status: ReservationStatus, short: int
    ) -> None:
        detail = CheckoutDetail(
            reservation_id=uuid4(),
            reference="TSH-R-26-000124",
            status=status,
            branch_id=uuid4(),
            branch_code="CBD",
            branch_name="Cape Town CBD",
            customer=CheckoutCustomer(
                id=uuid4(),
                display_name="Nomsa Dlamini",
                phone="082 441 7719",
                id_document_type=IdDocType.SA_ID,
                id_document_last4="0087",
                account_status=AccountStatus.ACTIVE,
            ),
            start_date=HIRE.start,
            end_date=HIRE.end,
            units=(),
            hire_total_inc_vat=Decimal("966.00"),
            rental_id=None,
            units_wanted=1,
        )
        assert detail.units_short == short


class TestReplacementUnits:
    """Every short line is topped up through the allocator, all or nothing."""

    def test_the_short_line_is_given_what_it_is_short_of(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        released_one(reservation)
        allocator = Allocator()
        taken = give_replacement_units(reservation, allocator)

        assert (len(taken), allocator.asked) == (1, [1])
        assert units_short_of(reservation) == 0
        assert reservation.is_fully_allocated()

    def test_a_booking_short_of_nothing_takes_nothing(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        allocator = Allocator()
        assert give_replacement_units(reservation, allocator) == []
        assert allocator.asked == []

    def test_a_line_that_cannot_be_topped_up_in_full_leaves_the_booking_as_it_was(self) -> None:
        reservation = a_confirmed(ONE_LINE)
        released_one(reservation)
        released_one(reservation)
        with pytest.raises(AllocationConflictError):
            give_replacement_units(reservation, Allocator(short_by=1))
        assert units_short_of(reservation) == 2

    @pytest.mark.parametrize(
        ("status", "words"),
        [
            (ReservationStatus.DRAFT, "is still a draft"),
            (ReservationStatus.COLLECTED, "has been collected"),
            (ReservationStatus.CANCELLED, "has been cancelled"),
        ],
    )
    def test_only_a_booking_on_hold_or_confirmed_is_topped_up(
        self, status: ReservationStatus, words: str
    ) -> None:
        reservation = a_draft(*ONE_LINE) if status is ReservationStatus.DRAFT else (
            a_reservation_in(status)
        )
        with pytest.raises(StateTransitionError) as refused:
            give_replacement_units(reservation, Allocator())
        assert refused.value.message == (
            f"This reservation {words}, so it cannot be given replacement units."
        )
        assert refused.value.rule == "BR-09"
