"""The reservation line and the allocation, with no database anywhere.

A line is one product model and a quantity, and it owns the allocations that
hold specific tagged units for it. An allocation is one unit and one half open
period. Availability is made of these and never of a counter, so the rules
here are the ones a double booking would have to get past. A line is satisfied
by exactly its quantity of active units, a release is recorded with its reason
and its time together, and two holds of one unit conflict exactly when the
exclusion constraint in the database says they do.

The reservation that owns the lines is in test_domain_booking.py.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final
from uuid import uuid4

import pytest

from app.domain.availability import AssetAllocation
from app.domain.catalogue import Asset
from app.domain.enums import AssetStatus, ReleaseReason, ReservationStatus
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from app.domain.policies import LineSnapshot
from tests.support.pricing import rand
from tests.support.reservations import (
    HAMMER,
    HIRE,
    NOW,
    ONE_DAY,
    RELEASED_AT,
    TWELFTH,
    a_draft,
    a_reservation_in,
    an_allocation,
    an_asset,
)

FIFTEENTH: Final[date] = date(2026, 3, 15)
ADJACENT_HIRE: Final[BookingPeriod] = BookingPeriod(TWELFTH, FIFTEENTH)
OVERLAPPING_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 11), FIFTEENTH)
LATER: Final[datetime] = RELEASED_AT + ONE_DAY


def a_hold_of(asset: Asset, period: BookingPeriod) -> AssetAllocation:
    """Return an active allocation of the asset for the period."""
    return AssetAllocation.hold(
        reservation_line_id=uuid4(), asset=asset, period=period, allocated_at=NOW
    )


class TestAReservationLine:
    """One model and a quantity, with the units held for it."""

    def test_the_snapshot_is_the_copied_figures_as_money_with_the_quantity(self) -> None:
        assert a_draft((HAMMER, 2)).lines[0].snapshot() == LineSnapshot(
            daily_rate=rand("280.00"),
            weekly_rate=rand("1120.00"),
            deposit=rand("1200.00"),
            quantity=2,
        )

    def test_a_draft_line_holds_nothing_and_is_not_satisfied(self) -> None:
        line = a_draft((HAMMER, 2)).lines[0]
        assert line.active_allocations() == []
        assert not line.is_satisfied()

    def test_a_line_is_satisfied_by_exactly_as_many_active_units_as_it_asks_for(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD)
        line = reservation.lines[0]
        first, second = line.allocations
        assert line.is_satisfied()
        line.allocations.append(an_allocation(line, branch_id=reservation.branch_id))
        assert not line.is_satisfied()
        del line.allocations[-1]
        first.release(ReleaseReason.REALLOCATED, RELEASED_AT)
        assert line.active_allocations() == [second]
        assert not line.is_satisfied()

    def test_releasing_a_line_returns_how_many_units_it_still_held(self) -> None:
        line = a_reservation_in(ReservationStatus.HELD).lines[0]
        line.allocations[0].release(ReleaseReason.REALLOCATED, RELEASED_AT)
        assert line.release_all(ReleaseReason.EXPIRED, LATER) == 1
        assert line.active_allocations() == []
        assert line.release_all(ReleaseReason.EXPIRED, LATER) == 0

    def test_releasing_a_line_keeps_the_release_a_unit_already_had(self) -> None:
        line = a_reservation_in(ReservationStatus.HELD).lines[0]
        line.allocations[0].release(ReleaseReason.REALLOCATED, RELEASED_AT)
        line.release_all(ReleaseReason.EXPIRED, LATER)
        assert [(unit.release_reason, unit.released_at) for unit in line.allocations] == [
            (ReleaseReason.REALLOCATED, RELEASED_AT),
            (ReleaseReason.EXPIRED, LATER),
        ]


class TestAnAllocation:
    """One unit, one half open period, and whether it still occupies the unit."""

    @pytest.mark.parametrize("status", list(AssetStatus))
    def test_only_an_available_asset_may_be_held(self, status: AssetStatus) -> None:
        assert an_asset(status=status).is_allocatable() is (status is AssetStatus.AVAILABLE)

    def test_holding_a_unit_that_is_not_available_is_a_conflict(self) -> None:
        quarantined = an_asset(status=AssetStatus.QUARANTINED)
        with pytest.raises(AllocationConflictError) as refused:
            a_hold_of(quarantined, HIRE)
        assert refused.value.detail["asset_tag"] == quarantined.asset_tag
        assert refused.value.detail["period"] == HIRE.as_postgres_daterange()

    def test_a_new_hold_is_active_and_carries_the_asset_and_its_branch(self) -> None:
        asset = an_asset()
        allocation = a_hold_of(asset, HIRE)
        assert allocation.is_active()
        assert (allocation.asset_id, allocation.branch_id) == (asset.id, asset.branch_id)
        assert allocation.allocated_at == NOW
        assert allocation.id != a_hold_of(asset, HIRE).id

    def test_a_release_sets_the_reason_and_the_time_and_only_the_first_one_stands(self) -> None:
        allocation = a_hold_of(an_asset(), HIRE)
        allocation.release(ReleaseReason.CANCELLED, RELEASED_AT)
        assert not allocation.is_active()
        allocation.release(ReleaseReason.EXPIRED, LATER)
        assert (allocation.release_reason, allocation.released_at) == (
            ReleaseReason.CANCELLED,
            RELEASED_AT,
        )

    @pytest.mark.parametrize(
        ("released_at", "release_reason"),
        [(RELEASED_AT, None), (None, ReleaseReason.EXPIRED)],
        ids=["a time without a reason", "a reason without a time"],
    )
    def test_a_half_recorded_release_is_refused(
        self, released_at: datetime | None, release_reason: ReleaseReason | None
    ) -> None:
        with pytest.raises(ValueError, match="half recorded release"):
            AssetAllocation(
                reservation_line_id=uuid4(),
                asset_id=uuid4(),
                branch_id=uuid4(),
                period=HIRE,
                allocated_at=NOW,
                released_at=released_at,
                release_reason=release_reason,
            )


class TestTwoAllocationsConflictExactlyWhenTheConstraintSaysSo:
    """The rule the exclusion constraint enforces, stated once more in the domain."""

    def test_overlapping_holds_of_one_asset_conflict(self) -> None:
        asset = an_asset()
        assert a_hold_of(asset, HIRE).conflicts_with(a_hold_of(asset, OVERLAPPING_HIRE))

    def test_a_hold_starting_on_the_day_the_other_ends_does_not_conflict(self) -> None:
        asset = an_asset()
        assert not a_hold_of(asset, HIRE).conflicts_with(a_hold_of(asset, ADJACENT_HIRE))

    def test_the_same_period_on_a_different_asset_does_not_conflict(self) -> None:
        other = an_asset(tag="TSH-DR-0043")
        assert not a_hold_of(an_asset(), HIRE).conflicts_with(a_hold_of(other, HIRE))

    def test_a_released_hold_conflicts_with_nothing(self) -> None:
        asset = an_asset()
        released = a_hold_of(asset, HIRE)
        released.release(ReleaseReason.CANCELLED, RELEASED_AT)
        assert not released.conflicts_with(a_hold_of(asset, HIRE))
        assert not a_hold_of(asset, HIRE).conflicts_with(released)
