"""The legal moves of a reservation after the hold, with their guards and effects (BR-11).

Each class is one move of the state table in the design document, from every
status that permits it. The move is asked of a reservation that already stands
in that status, on a clock that stands still. A guard that fails has to leave
the reservation exactly as it was, so a refusal here is compared with a copy
taken before the move was asked.

Instants are written in UTC. Cape Town is two hours ahead all year, so 17:00
there is 15:00 here.

The move from DRAFT to HELD is in test_reservation_hold_move.py, and the moves
the table does not list are in test_reservation_state_refusals.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final

import pytest

from app.domain.booking import Reservation
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import (
    AuthorisationFailure,
    EmailNotVerifiedError,
    StateTransitionError,
    ValidationFailure,
)
from tests.support.reservations import (
    CONFIRMED_AT,
    HOLD_EXPIRES_AT,
    NINTH,
    NOW,
    ONE_DAY,
    ONE_LINE,
    ONE_SECOND,
    REFERENCE,
    RELEASED_AT,
    TWO_LINES,
    a_draft,
    a_reservation_in,
    an_allocation,
    refused_and_untouched,
    releases_of,
)

# The units that two hammers and one mixer come to.
UNITS: Final[int] = 3
REASON: Final[str] = "The job was postponed."
# 17:00 in Cape Town on the eighth, the day before the hire starts (BR-16).
LATE_CUTOFF: Final[datetime] = datetime(2026, 3, 8, 15, 0, tzinfo=UTC)
# The branch shuts at 17:00 in Cape Town on the first day of the hire.
BRANCH_CLOSED_AT: Final[datetime] = datetime(2026, 3, 9, 15, 0, tzinfo=UTC)
RETURNED_AT: Final[datetime] = datetime(2026, 3, 12, 7, 30, tzinfo=UTC)


def short_of_a_unit(reservation: Reservation) -> Reservation:
    """Return the reservation with one unit of its last line let go, so the line is short."""
    reservation.lines[-1].allocations[0].release(ReleaseReason.REALLOCATED, RELEASED_AT)
    return reservation


class TestCancelling:
    """DRAFT, HELD and CONFIRMED to CANCELLED. Only the owner or the staff may."""

    @pytest.mark.parametrize(
        "status",
        [ReservationStatus.DRAFT, ReservationStatus.HELD, ReservationStatus.CONFIRMED],
    )
    def test_somebody_who_is_neither_the_owner_nor_staff_is_refused(
        self, status: ReservationStatus
    ) -> None:
        reservation = a_reservation_in(status)
        with refused_and_untouched(reservation, AuthorisationFailure) as refused:
            reservation.cancel(now=NOW, reason=REASON, by_owner_or_staff=False)
        assert refused.value.rule == "BR-15"

    def test_a_draft_is_abandoned_with_the_time_and_the_reason(self) -> None:
        reservation = a_draft(*ONE_LINE)
        reservation.cancel(now=NOW, reason=REASON, by_owner_or_staff=True)
        assert reservation.status is ReservationStatus.CANCELLED
        assert (reservation.cancelled_at, reservation.cancellation_reason) == (NOW, REASON)
        assert not reservation.is_late_cancellation

    def test_a_draft_that_holds_a_unit_cannot_be_cancelled_as_a_draft(self) -> None:
        reservation = a_draft(*ONE_LINE)
        line = reservation.lines[0]
        line.allocations.append(an_allocation(line, branch_id=reservation.branch_id))
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.cancel(now=NOW, reason=None, by_owner_or_staff=True)
        assert (refused.value.from_status, refused.value.to_status) == ("DRAFT", "CANCELLED")
        assert refused.value.rule == "BR-15"

    def test_a_cancelled_hold_releases_its_units_and_loses_its_expiry(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD, TWO_LINES)
        reservation.cancel(now=CONFIRMED_AT, reason=REASON, by_owner_or_staff=True)
        assert reservation.status is ReservationStatus.CANCELLED
        assert reservation.hold_expires_at is None
        assert (reservation.cancelled_at, reservation.cancellation_reason) == (CONFIRMED_AT, REASON)
        assert releases_of(reservation) == [(ReleaseReason.CANCELLED, CONFIRMED_AT)] * UNITS
        assert not reservation.is_late_cancellation

    @pytest.mark.parametrize(
        ("now", "late"),
        [
            (NOW, False),
            (LATE_CUTOFF, False),
            (LATE_CUTOFF + ONE_SECOND, True),
            (LATE_CUTOFF + ONE_DAY, True),
        ],
        ids=["a week ahead", "at 17:00 exactly", "a second after 17:00", "on the first day"],
    )
    def test_a_confirmed_booking_cancelled_after_five_on_the_day_before_is_late(
        self, now: datetime, late: bool
    ) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, TWO_LINES)
        reservation.cancel(now=now, reason=REASON, by_owner_or_staff=True)
        assert reservation.status is ReservationStatus.CANCELLED
        assert (reservation.cancelled_at, reservation.cancellation_reason) == (now, REASON)
        assert reservation.is_late_cancellation is late
        assert releases_of(reservation) == [(ReleaseReason.CANCELLED, now)] * UNITS

    def test_a_confirmed_booking_already_out_on_hire_cannot_be_cancelled(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.cancel(now=NOW, reason=REASON, by_owner_or_staff=True, has_rental=True)
        assert (refused.value.to_status, refused.value.rule) == ("CANCELLED", "BR-15")


class TestConfirmingAHold:
    """HELD to CONFIRMED. Inside the hold, with every unit held and the address proved."""

    @pytest.mark.parametrize(
        "now", [CONFIRMED_AT, HOLD_EXPIRES_AT], ids=["inside the hold", "at the instant it ends"]
    )
    def test_a_hold_confirmed_in_time_keeps_its_units_and_loses_its_expiry(
        self, now: datetime
    ) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD, TWO_LINES)
        reservation.confirm(now=now, email_verified=True)
        assert reservation.status is ReservationStatus.CONFIRMED
        assert (reservation.hold_expires_at, reservation.confirmed_at) == (None, now)
        assert reservation.is_fully_allocated()

    def test_a_hold_that_has_run_out_cannot_be_confirmed(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.confirm(now=HOLD_EXPIRES_AT + ONE_SECOND, email_verified=True)
        assert (refused.value.to_status, refused.value.rule) == ("CONFIRMED", "BR-13")

    def test_a_hold_with_a_line_short_of_a_unit_cannot_be_confirmed(self) -> None:
        reservation = short_of_a_unit(a_reservation_in(ReservationStatus.HELD, TWO_LINES))
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.confirm(now=CONFIRMED_AT, email_verified=True)
        assert (refused.value.to_status, refused.value.rule) == ("CONFIRMED", "BR-08")

    def test_a_customer_who_has_not_verified_their_email_cannot_confirm(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD)
        with refused_and_untouched(reservation, EmailNotVerifiedError) as refused:
            reservation.confirm(now=CONFIRMED_AT, email_verified=False)
        assert refused.value.rule == "BR-47"
        assert refused.value.detail == {"reference": REFERENCE}


class TestExpiringAHold:
    """HELD to EXPIRED. Only once the hold has run out."""

    def test_a_hold_that_has_run_out_expires_and_releases_its_units(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD, TWO_LINES)
        lapsed_at = HOLD_EXPIRES_AT + ONE_SECOND
        reservation.expire(now=lapsed_at)
        assert reservation.status is ReservationStatus.EXPIRED
        assert reservation.hold_expires_at is None
        assert releases_of(reservation) == [(ReleaseReason.EXPIRED, lapsed_at)] * UNITS

    @pytest.mark.parametrize(
        "now", [NOW, HOLD_EXPIRES_AT], ids=["inside the hold", "at the instant it expires at"]
    )
    def test_a_hold_that_is_still_running_cannot_be_expired(self, now: datetime) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.expire(now=now)
        assert (refused.value.to_status, refused.value.rule) == ("EXPIRED", "BR-13")


class TestCollectingAConfirmedBooking:
    """CONFIRMED to COLLECTED. From the first day of the hire, with every unit held."""

    @pytest.mark.parametrize(
        "today", [NINTH, NINTH + ONE_DAY], ids=["on the first day", "on the second day"]
    )
    def test_it_is_collected_from_the_first_day_and_keeps_its_units(self, today: date) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, TWO_LINES)
        reservation.collect(today=today)
        assert reservation.status is ReservationStatus.COLLECTED
        assert reservation.is_fully_allocated()

    def test_it_cannot_be_collected_before_the_first_day_of_the_hire(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED)
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.collect(today=NINTH - ONE_DAY)
        assert refused.value.rule == "BR-26"
        assert refused.value.detail == {"start_date": "2026-03-09", "today": "2026-03-08"}

    def test_a_booking_with_a_line_short_of_a_unit_cannot_be_collected(self) -> None:
        reservation = short_of_a_unit(a_reservation_in(ReservationStatus.CONFIRMED, TWO_LINES))
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.collect(today=NINTH)
        assert (refused.value.to_status, refused.value.rule) == ("COLLECTED", "BR-08")


class TestMarkingANoShow:
    """CONFIRMED to NO_SHOW. Only once the branch has closed on the first day."""

    def test_after_the_branch_has_closed_the_units_are_released_as_a_no_show(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, TWO_LINES)
        now = BRANCH_CLOSED_AT + ONE_SECOND
        reservation.mark_no_show(now=now, branch_closed_at=BRANCH_CLOSED_AT)
        assert reservation.status is ReservationStatus.NO_SHOW
        assert releases_of(reservation) == [(ReleaseReason.NO_SHOW, now)] * UNITS

    @pytest.mark.parametrize(
        "now",
        [BRANCH_CLOSED_AT - ONE_SECOND, BRANCH_CLOSED_AT],
        ids=["a second before closing", "at the instant of closing"],
    )
    def test_until_the_branch_has_closed_it_can_still_be_collected(self, now: datetime) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(now=now, branch_closed_at=BRANCH_CLOSED_AT)
        assert (refused.value.to_status, refused.value.rule) == ("NO_SHOW", "BR-17")


class TestClosingACollectedBooking:
    """COLLECTED to RETURNED. No unit stays held for a booking that is over."""

    def test_closing_releases_every_unit_still_held_as_returned(self) -> None:
        reservation = a_reservation_in(ReservationStatus.COLLECTED, TWO_LINES)
        reservation.close(now=RETURNED_AT)
        assert reservation.status is ReservationStatus.RETURNED
        assert releases_of(reservation) == [(ReleaseReason.RETURNED, RETURNED_AT)] * UNITS

    def test_a_unit_let_go_earlier_keeps_the_reason_and_the_time_it_already_had(self) -> None:
        reservation = short_of_a_unit(a_reservation_in(ReservationStatus.COLLECTED))
        reservation.close(now=RETURNED_AT)
        assert releases_of(reservation) == [
            (ReleaseReason.REALLOCATED, RELEASED_AT),
            (ReleaseReason.RETURNED, RETURNED_AT),
        ]
