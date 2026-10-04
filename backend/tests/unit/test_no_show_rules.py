"""The rules of a booking nobody collected, with no database anywhere (BR-17, BR-18).

When a confirmed booking becomes a no show is the reservation state's to
decide. The sweep may call it once the collection branch has closed on the
first day of the hire, and staff at the counter from the start of that day.
These pin the moment either way, the booking that was already collected, and
the sentence each refusal says.

The other rules are the domain's too. The strike window is the twelve months
that end today, counted by the start dates of the reservations. Only an
account in good standing goes on hold, at the third strike. The diary's button
reads `no_show_refusal`, and a customer on hold is told why. The late fee the
dashboard shows is the late fee policy's, pinned in
tests/unit/test_late_fee_policy.py.

Instants are written in UTC. Cape Town is two hours ahead all year, so 17:00
there is 15:00 here and midnight there is 22:00 the evening before here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final
from uuid import uuid4

import pytest

from app.domain.enums import AccountStatus, ReleaseReason, ReservationStatus
from app.domain.errors import AccountOnHoldError, StateTransitionError
from app.domain.identity import CustomerProfile
from app.domain.no_show import (
    STRIKE_LIMIT,
    no_show_refusal,
    standing_after_strikes,
    strike_window_opens_after,
)
from app.domain.states.guards import BRANCH_STILL_OPEN_MESSAGE, FIRST_DAY_NOT_COME_MESSAGE
from tests.support.reservations import (
    NINTH,
    ONE_DAY,
    ONE_LINE,
    ONE_SECOND,
    a_reservation_in,
    refused_and_untouched,
    releases_of,
)

UNITS: Final[int] = 2
# The branch shuts at 17:00 in Cape Town on the ninth, the first day of the hire.
BRANCH_CLOSED_AT: Final[datetime] = datetime(2026, 3, 9, 15, 0, tzinfo=UTC)
# Midnight in Cape Town at the start of the ninth.
FIRST_DAY_BEGINS: Final[datetime] = datetime(2026, 3, 8, 22, 0, tzinfo=UTC)


class TestWhenTheSweepMayCallANoShow:
    """Once the branch has closed on the first day, and not a moment before."""

    def test_before_closing_time_the_booking_can_still_be_collected(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(
                now=BRANCH_CLOSED_AT - ONE_SECOND, branch_closed_at=BRANCH_CLOSED_AT
            )
        assert refused.value.message == BRANCH_STILL_OPEN_MESSAGE
        assert (refused.value.from_status, refused.value.to_status) == ("CONFIRMED", "NO_SHOW")

    def test_at_the_instant_of_closing_the_branch_is_still_open(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(now=BRANCH_CLOSED_AT, branch_closed_at=BRANCH_CLOSED_AT)
        assert refused.value.rule == "BR-17"

    def test_a_second_after_closing_the_booking_is_a_no_show(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        now = BRANCH_CLOSED_AT + ONE_SECOND
        reservation.mark_no_show(now=now, branch_closed_at=BRANCH_CLOSED_AT)
        assert reservation.status is ReservationStatus.NO_SHOW
        assert releases_of(reservation) == [(ReleaseReason.NO_SHOW, now)] * UNITS

    def test_the_day_after_the_booking_is_a_no_show(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        now = BRANCH_CLOSED_AT + ONE_DAY
        reservation.mark_no_show(now=now, branch_closed_at=BRANCH_CLOSED_AT)
        assert reservation.status is ReservationStatus.NO_SHOW
        assert releases_of(reservation) == [(ReleaseReason.NO_SHOW, now)] * UNITS

    def test_a_booking_already_collected_is_never_a_no_show(self) -> None:
        reservation = a_reservation_in(ReservationStatus.COLLECTED, ONE_LINE)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(
                now=BRANCH_CLOSED_AT + ONE_DAY, branch_closed_at=BRANCH_CLOSED_AT
            )
        assert refused.value.message == (
            "This reservation has been collected, so it cannot be marked as not collected."
        )
        assert refused.value.rule == "BR-11"


class TestWhenStaffMayMarkANoShow:
    """From the start of the first day by the clock in Cape Town, whatever the branch hours."""

    def test_before_the_first_day_has_begun_staff_are_refused(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(now=FIRST_DAY_BEGINS - ONE_SECOND, branch_closed_at=None)
        assert refused.value.message == FIRST_DAY_NOT_COME_MESSAGE
        assert (refused.value.to_status, refused.value.rule) == ("NO_SHOW", "BR-17")

    @pytest.mark.parametrize(
        "now",
        [FIRST_DAY_BEGINS, BRANCH_CLOSED_AT - ONE_SECOND, BRANCH_CLOSED_AT + ONE_DAY],
        ids=["at midnight", "before the branch closes", "the day after"],
    )
    def test_from_the_first_day_staff_may_mark_it(self, now: datetime) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, ONE_LINE)
        reservation.mark_no_show(now=now, branch_closed_at=None)
        assert reservation.status is ReservationStatus.NO_SHOW
        assert releases_of(reservation) == [(ReleaseReason.NO_SHOW, now)] * UNITS

    def test_staff_cannot_mark_a_booking_that_is_only_on_hold(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD, ONE_LINE)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.mark_no_show(now=BRANCH_CLOSED_AT, branch_closed_at=None)
        assert refused.value.message == (
            "This reservation is on hold, so it cannot be marked as not collected."
        )


class TestTheStrikeWindow:
    """The twelve months that end today, counted by the start date of each reservation."""

    def test_the_window_opens_after_the_same_day_a_year_earlier(self) -> None:
        assert strike_window_opens_after(date(2026, 10, 3)) == date(2025, 10, 3)

    def test_the_twenty_ninth_of_february_counts_back_to_the_twenty_eighth(self) -> None:
        assert strike_window_opens_after(date(2028, 2, 29)) == date(2027, 2, 28)

    def test_the_first_of_january_counts_back_across_the_year(self) -> None:
        assert strike_window_opens_after(date(2027, 1, 1)) == date(2026, 1, 1)


class TestTheStandingAfterTheStrikes:
    """An account in good standing goes on hold at the third, and nothing else changes."""

    @pytest.mark.parametrize("strikes", [0, 1, STRIKE_LIMIT - 1])
    def test_below_the_limit_an_account_stays_in_good_standing(self, strikes: int) -> None:
        assert standing_after_strikes(AccountStatus.ACTIVE, strikes) is AccountStatus.ACTIVE

    @pytest.mark.parametrize("strikes", [STRIKE_LIMIT, STRIKE_LIMIT + 1])
    def test_at_the_third_strike_an_account_goes_on_hold(self, strikes: int) -> None:
        assert standing_after_strikes(AccountStatus.ACTIVE, strikes) is AccountStatus.ON_HOLD

    @pytest.mark.parametrize("standing", [AccountStatus.ON_HOLD, AccountStatus.BLACKLISTED])
    def test_an_account_not_in_good_standing_keeps_its_standing(
        self, standing: AccountStatus
    ) -> None:
        assert standing_after_strikes(standing, STRIKE_LIMIT + 1) is standing

    def test_the_limit_is_three(self) -> None:
        assert STRIKE_LIMIT == 3


class TestTheButtonOfTheDiary:
    """`no_show_refusal` says what the route would say, or nothing when staff may mark it."""

    def test_a_confirmed_booking_whose_hire_has_started_may_be_marked(self) -> None:
        assert no_show_refusal(ReservationStatus.CONFIRMED, NINTH, NINTH) is None
        assert no_show_refusal(ReservationStatus.CONFIRMED, NINTH, NINTH + ONE_DAY) is None

    def test_a_confirmed_booking_whose_hire_starts_tomorrow_may_not(self) -> None:
        refusal = no_show_refusal(ReservationStatus.CONFIRMED, NINTH, NINTH - ONE_DAY)
        assert refusal == FIRST_DAY_NOT_COME_MESSAGE

    @pytest.mark.parametrize(
        "status",
        [
            ReservationStatus.COLLECTED,
            ReservationStatus.RETURNED,
            ReservationStatus.NO_SHOW,
            ReservationStatus.HELD,
        ],
    )
    def test_a_booking_that_is_not_confirmed_may_not(self, status: ReservationStatus) -> None:
        refusal = no_show_refusal(status, NINTH, NINTH)
        assert refusal is not None
        assert refusal.endswith("so it cannot be marked as not collected.")


class TestACustomerOnHoldIsToldPlainly:
    """The refusal says the account is on hold and to contact a branch, and never why.

    A hold by hand and a hold for three bookings not collected look the same to
    a booking, so a sentence about the three bookings would be false for the
    first. A blacklisted account is told the same.
    """

    @pytest.mark.parametrize("standing", [AccountStatus.ON_HOLD, AccountStatus.BLACKLISTED])
    def test_the_refusal_says_on_hold_and_contact_a_branch(self, standing: AccountStatus) -> None:
        profile = CustomerProfile(
            id=uuid4(),
            user_account_id=uuid4(),
            display_name="Nomsa Dlamini",
            account_status=standing,
            email=None,
        )
        with pytest.raises(AccountOnHoldError) as refused:
            profile.ensure_may_book()
        assert refused.value.message == (
            "This customer account is on hold, so it cannot make a reservation. "
            "Please contact a branch."
        )
        assert "not collected" not in refused.value.message
        assert refused.value.detail == {"account_status": standing.value}

