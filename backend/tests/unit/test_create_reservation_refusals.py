"""What the reservation use case refuses, and that a refusal leaves no trace.

Run against ports and nothing else, like test_create_reservation_use_case.py.
Every refusal here happens inside or before the unit of work, so the test for
each one ends by looking at what was committed, which must be nothing.

The date rules are the reason the use case takes a clock. A hire may not start
before today (BR-04) or more than ninety days ahead (BR-05), and today is the
business day in Cape Town, not the day the server's clock happens to be on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Final

import pytest

from app.domain.enums import ReservationStatus
from app.domain.errors import AllocationConflictError, NotFound, ValidationFailure
from app.domain.period import MAXIMUM_DAYS_AHEAD, BookingPeriod
from tests.support.clock import FixedClock
from tests.support.memory_world import build_memory_world, wire_use_case

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))


class TestWhatIsRefusedBeforeAnythingIsWritten:
    """A refusal leaves no trace, because nothing was committed."""

    def test_a_hire_starting_before_today_is_refused(self) -> None:
        """BR-04."""
        world = build_memory_world()
        use_case = wire_use_case(world, clock=FixedClock(datetime(2026, 3, 10, tzinfo=UTC)))
        with pytest.raises(ValidationFailure) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail == {"start_date": "2026-03-09", "today": "2026-03-10"}

    def test_today_is_the_business_day_in_cape_town_and_not_the_utc_day(self) -> None:
        """At 22:30 UTC on the ninth it is already the tenth at the counter."""
        world = build_memory_world()
        late_evening = FixedClock(datetime(2026, 3, 9, 22, 30, tzinfo=UTC))
        use_case = wire_use_case(world, clock=late_evening)
        with pytest.raises(ValidationFailure) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail["today"] == "2026-03-10"

    def test_a_hire_starting_today_is_accepted(self) -> None:
        world = build_memory_world()
        clock = FixedClock(datetime(2026, 3, 9, 6, 0, tzinfo=UTC))
        use_case = wire_use_case(world, clock=clock)
        assert use_case.execute(world.command(FIRST_HIRE)).status is ReservationStatus.HELD

    def test_a_hire_beyond_the_booking_horizon_is_refused(self) -> None:
        """BR-05."""
        world = build_memory_world()
        clock = FixedClock()
        start = clock.today() + timedelta(days=MAXIMUM_DAYS_AHEAD + 1)
        too_far = BookingPeriod(start, start + timedelta(days=3))
        use_case = wire_use_case(world, clock=clock)
        with pytest.raises(ValidationFailure) as refused:
            use_case.execute(world.command(too_far))
        assert refused.value.detail == {
            "days_ahead": MAXIMUM_DAYS_AHEAD + 1,
            "maximum_days_ahead": MAXIMUM_DAYS_AHEAD,
        }

    def test_a_hire_on_the_last_day_of_the_horizon_is_accepted(self) -> None:
        world = build_memory_world()
        clock = FixedClock()
        start = clock.today() + timedelta(days=MAXIMUM_DAYS_AHEAD)
        use_case = wire_use_case(world, clock=clock)
        view = use_case.execute(world.command(BookingPeriod(start, start + timedelta(days=3))))
        assert view.status is ReservationStatus.HELD

    def test_an_unknown_branch_is_not_found(self) -> None:
        world = build_memory_world()
        world.store.branches.clear()
        use_case = wire_use_case(world)
        with pytest.raises(NotFound) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail == {"branch_id": str(world.branch.id)}

    def test_an_unknown_product_model_is_not_found(self) -> None:
        world = build_memory_world()
        world.store.product_models.clear()
        use_case = wire_use_case(world)
        with pytest.raises(NotFound) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail == {"product_model_id": str(world.product_model.id)}

    def test_an_account_with_no_customer_profile_is_not_found(self) -> None:
        world = build_memory_world()
        world.store.profiles.clear()
        use_case = wire_use_case(world)
        with pytest.raises(NotFound) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail == {"customer_user_id": str(world.customer_account_id)}

    @pytest.mark.parametrize("quantity", [0, 11])
    def test_a_quantity_outside_one_to_ten_is_refused(self, quantity: int) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        with pytest.raises(ValidationFailure) as refused:
            use_case.execute(world.command(FIRST_HIRE, quantity=quantity))
        assert refused.value.detail["received"] == quantity
        assert world.store.committed.reservations == []


class TestTooFewFreeUnitsIsAConflictAndNothingIsKept:
    """BR-09. A booking that cannot be filled completely is not made at all."""

    def test_a_second_booking_of_the_only_unit_is_a_conflict(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE))
        with pytest.raises(AllocationConflictError) as refused:
            use_case.execute(world.command(FIRST_HIRE))
        assert refused.value.detail["available_quantity"] == 0
        assert refused.value.detail["requested_quantity"] == 1
        assert refused.value.detail["period"] == FIRST_HIRE.as_postgres_daterange()

    def test_asking_for_more_units_than_are_free_keeps_none_of_them(self) -> None:
        world = build_memory_world(asset_count=2)
        use_case = wire_use_case(world)
        with pytest.raises(AllocationConflictError) as refused:
            use_case.execute(world.command(FIRST_HIRE, quantity=3))
        assert refused.value.detail["available_quantity"] == 2
        committed = world.store.committed
        assert committed.reservations == []
        assert committed.allocations == []
        assert committed.audit_events == []
        assert committed.notifications == {}

    def test_a_hire_starting_the_day_the_first_one_ends_takes_the_same_unit(self) -> None:
        """BR-02. A return on the twelfth frees the twelfth."""
        world = build_memory_world()
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE))
        adjacent = BookingPeriod(date(2026, 3, 12), date(2026, 3, 15))
        view = use_case.execute(world.command(adjacent))
        assert [item.asset_tag for item in view.allocated] == ["TSH-DR-0001"]
