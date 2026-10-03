"""A hire can start today only while the collection branch is open, with no database (BR-04).

Once the branch has closed for the day nobody can collect, and the sweep would
call a confirmed booking for today a no show the moment after it was made. So
today stops being a start date anybody can book the moment the branch closes,
by the clock in Cape Town. The branch is still open at the very instant it
closes, which is the instant the no show sweep counts from, so the two rules
meet without a gap.

The rule is the domain's, `ensure_branch_open_for_start`, beside the booking
window. Creating a draft refuses the start date by name, and putting a draft
on hold or confirming it asks again, because a draft made before closing can
be acted on after it.

The branch closes at 17:00 in Cape Town, which is 15:00 UTC, on Monday the
second of March 2026.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Final

import pytest

from app.application.refusal import refused_parameter_of
from app.domain.enums import ReservationStatus
from app.domain.errors import ValidationFailure
from app.domain.period import (
    BRANCH_CLOSED_FOR_TODAY_MESSAGE,
    BookingPeriod,
    ensure_branch_open_for_start,
)
from tests.support.memory_world import build_memory_world, open_desk

CLOSES_AT: Final[time] = time(17, 0)
TODAY: Final[date] = date(2026, 3, 2)
TODAY_HIRE: Final[BookingPeriod] = BookingPeriod(TODAY, date(2026, 3, 4))
TOMORROW_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 3), date(2026, 3, 5))
CLOSING_INSTANT: Final[datetime] = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)


class TestTheRule:
    """Either side of closing time, and the day after."""

    @pytest.mark.parametrize(
        "now",
        [CLOSING_INSTANT - timedelta(hours=8), CLOSING_INSTANT - ONE_SECOND, CLOSING_INSTANT],
        ids=["in the morning", "a second before closing", "at closing exactly"],
    )
    def test_today_can_be_booked_while_the_branch_is_open(self, now: datetime) -> None:
        ensure_branch_open_for_start(TODAY_HIRE, now=now, closes_at=CLOSES_AT)

    def test_today_cannot_be_booked_a_second_after_the_branch_closes(self) -> None:
        with pytest.raises(ValidationFailure) as refused:
            ensure_branch_open_for_start(
                TODAY_HIRE, now=CLOSING_INSTANT + ONE_SECOND, closes_at=CLOSES_AT
            )
        assert refused.value.message == BRANCH_CLOSED_FOR_TODAY_MESSAGE
        assert refused.value.rule == "BR-04"
        assert refused.value.detail == {"start_date": "2026-03-02", "closes_at": "17:00:00"}

    def test_tomorrow_can_still_be_booked_after_closing(self) -> None:
        ensure_branch_open_for_start(
            TOMORROW_HIRE, now=CLOSING_INSTANT + timedelta(hours=5), closes_at=CLOSES_AT
        )


class TestTheBookingUseCases:
    """Creating names the start date, and holding and confirming ask again."""

    def test_a_draft_for_today_after_closing_is_refused_by_its_start_date(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.clock.instant = CLOSING_INSTANT + ONE_SECOND
        with pytest.raises(ValidationFailure) as refused:
            desk.drafted(world.draft_command(TODAY_HIRE))
        assert refused.value.message == BRANCH_CLOSED_FOR_TODAY_MESSAGE
        assert refused_parameter_of(refused.value) == "from"
        assert world.store.committed.reservations == []

    def test_a_draft_for_today_before_closing_is_made(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.clock.instant = CLOSING_INSTANT - ONE_SECOND
        assert desk.drafted(world.draft_command(TODAY_HIRE)).detail.status is (
            ReservationStatus.DRAFT
        )

    def test_a_draft_made_before_closing_cannot_be_held_after_it(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.clock.instant = CLOSING_INSTANT - ONE_SECOND
        draft = desk.drafted(world.draft_command(TODAY_HIRE))
        desk.clock.instant = CLOSING_INSTANT + ONE_SECOND
        with pytest.raises(ValidationFailure, match="closed for today"):
            desk.hold.execute(desk.command_for(draft))
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT

    def test_a_hold_made_before_closing_cannot_be_confirmed_after_it(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.clock.instant = CLOSING_INSTANT - timedelta(minutes=5)
        held = desk.held(world.draft_command(TODAY_HIRE))
        desk.clock.instant = CLOSING_INSTANT + ONE_SECOND
        with pytest.raises(ValidationFailure, match="closed for today"):
            desk.confirm.execute(desk.command_for(held))
        assert world.stored(held.detail.id).status is ReservationStatus.HELD

    def test_a_reservation_whose_branch_cannot_be_read_is_a_fault_in_the_data(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted(world.draft_command(TODAY_HIRE))
        world.store.branches.clear()
        with pytest.raises(LookupError, match="could not be read"):
            desk.hold.execute(desk.command_for(draft))
