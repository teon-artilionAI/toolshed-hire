"""The booking entities, with no database anywhere.

The reservation, its lines and their allocations are plain dataclasses. These
tests build them by hand and ask them the questions the use cases ask, which is
the point of keeping the domain free of the ORM. A rule proved here holds
whatever stores the booking.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.availability import AssetAllocation
from app.domain.booking import NOT_YET_PRICED, Reservation, ReservationLine, format_reference
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AssetStatus, ConditionGrade, ReleaseReason, ReservationStatus
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod

NINTH: Final[date] = date(2026, 3, 9)
TWELFTH: Final[date] = date(2026, 3, 12)
FIFTEENTH: Final[date] = date(2026, 3, 15)
FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(NINTH, TWELFTH)
ADJACENT_HIRE: Final[BookingPeriod] = BookingPeriod(TWELFTH, FIFTEENTH)
OVERLAPPING_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 11), FIFTEENTH)
HELD_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
RELEASED_AT: Final[datetime] = datetime(2026, 3, 3, 9, 30, tzinfo=UTC)
REFERENCE: Final[str] = "TSH-R-26-000124"


def a_product_model(*, sku: str = "TSH-PM-0001") -> ProductModel:
    """Return a catalogue entry with five distinct prices, so a mix up shows."""
    return ProductModel(
        id=uuid4(),
        sku=sku,
        name="GBH 2-26 DRE Rotary Hammer",
        daily_rate=Decimal("185.00"),
        weekly_rate=Decimal("740.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("4200.00"),
    )


def an_asset(*, status: AssetStatus = AssetStatus.AVAILABLE, tag: str = "TSH-DR-0042") -> Asset:
    """Return one tagged unit in the given status."""
    return Asset(
        id=uuid4(),
        asset_tag=tag,
        product_model_id=uuid4(),
        branch_id=uuid4(),
        status=status,
        condition_grade=ConditionGrade.A,
    )


def a_held_reservation() -> Reservation:
    """Return a held reservation for the first hire, with no lines yet."""
    return Reservation.held(
        reference=REFERENCE,
        customer_profile_id=uuid4(),
        branch_id=uuid4(),
        period=FIRST_HIRE,
        created_by_user_id=uuid4(),
    )


def an_allocation(asset: Asset, period: BookingPeriod) -> AssetAllocation:
    """Return an active allocation of the asset for the period."""
    return AssetAllocation.hold(
        reservation_line_id=uuid4(), asset=asset, period=period, allocated_at=HELD_AT
    )


class TestTheReference:
    """The reference a customer quotes at the counter."""

    def test_it_is_the_prefix_the_year_and_a_six_digit_number(self) -> None:
        assert format_reference(2026, 124) == "TSH-R-26-000124"

    def test_only_the_last_two_digits_of_the_year_are_used(self) -> None:
        assert format_reference(2031, 7) == "TSH-R-31-000007"


class TestAnAssetMayOnlyBeHeldWhenItIsAvailable:
    """A unit under repair or on hire is not a candidate, whatever the dates say."""

    def test_an_available_asset_is_allocatable(self) -> None:
        assert an_asset(status=AssetStatus.AVAILABLE).is_allocatable()

    @pytest.mark.parametrize(
        "status", [status for status in AssetStatus if status is not AssetStatus.AVAILABLE]
    )
    def test_no_other_status_is_allocatable(self, status: AssetStatus) -> None:
        assert not an_asset(status=status).is_allocatable()

    def test_holding_a_unit_that_is_not_available_is_a_conflict(self) -> None:
        quarantined = an_asset(status=AssetStatus.QUARANTINED)
        with pytest.raises(AllocationConflictError) as refused:
            an_allocation(quarantined, FIRST_HIRE)
        assert refused.value.detail["asset_tag"] == quarantined.asset_tag
        assert refused.value.detail["period"] == FIRST_HIRE.as_postgres_daterange()


class TestAnAllocation:
    """One unit, one half open period, and whether it still occupies the unit."""

    def test_a_new_hold_is_active_and_carries_the_asset_and_its_branch(self) -> None:
        asset = an_asset()
        allocation = an_allocation(asset, FIRST_HIRE)
        assert allocation.is_active()
        assert allocation.asset_id == asset.id
        assert allocation.branch_id == asset.branch_id
        assert allocation.allocated_at == HELD_AT

    def test_every_allocation_gets_a_key_of_its_own(self) -> None:
        asset = an_asset()
        assert an_allocation(asset, FIRST_HIRE).id != an_allocation(asset, FIRST_HIRE).id

    def test_a_released_allocation_is_not_active(self) -> None:
        asset = an_asset()
        released = AssetAllocation(
            reservation_line_id=uuid4(),
            asset_id=asset.id,
            branch_id=asset.branch_id,
            period=FIRST_HIRE,
            allocated_at=HELD_AT,
            released_at=RELEASED_AT,
            release_reason=ReleaseReason.CANCELLED,
        )
        assert not released.is_active()

    def test_a_release_time_without_a_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="half recorded release"):
            AssetAllocation(
                reservation_line_id=uuid4(),
                asset_id=uuid4(),
                branch_id=uuid4(),
                period=FIRST_HIRE,
                allocated_at=HELD_AT,
                released_at=RELEASED_AT,
            )

    def test_a_release_reason_without_a_time_is_refused(self) -> None:
        with pytest.raises(ValueError, match="half recorded release"):
            AssetAllocation(
                reservation_line_id=uuid4(),
                asset_id=uuid4(),
                branch_id=uuid4(),
                period=FIRST_HIRE,
                allocated_at=HELD_AT,
                release_reason=ReleaseReason.EXPIRED,
            )


class TestTwoAllocationsConflictExactlyWhenTheConstraintSaysSo:
    """The rule the exclusion constraint enforces, stated once more in the domain."""

    def test_overlapping_holds_of_one_asset_conflict(self) -> None:
        asset = an_asset()
        assert an_allocation(asset, FIRST_HIRE).conflicts_with(
            an_allocation(asset, OVERLAPPING_HIRE)
        )

    def test_a_hold_starting_on_the_day_the_other_ends_does_not_conflict(self) -> None:
        asset = an_asset()
        assert not an_allocation(asset, FIRST_HIRE).conflicts_with(
            an_allocation(asset, ADJACENT_HIRE)
        )

    def test_the_same_period_on_a_different_asset_does_not_conflict(self) -> None:
        assert not an_allocation(an_asset(), FIRST_HIRE).conflicts_with(
            an_allocation(an_asset(tag="TSH-DR-0043"), FIRST_HIRE)
        )

    def test_a_released_hold_conflicts_with_nothing(self) -> None:
        asset = an_asset()
        released = AssetAllocation(
            reservation_line_id=uuid4(),
            asset_id=asset.id,
            branch_id=asset.branch_id,
            period=FIRST_HIRE,
            allocated_at=HELD_AT,
            released_at=RELEASED_AT,
            release_reason=ReleaseReason.CANCELLED,
        )
        assert not released.conflicts_with(an_allocation(asset, FIRST_HIRE))
        assert not an_allocation(asset, FIRST_HIRE).conflicts_with(released)


class TestAReservationAndItsLines:
    """The aggregate root owns its lines, and a line snapshots the prices."""

    def test_a_new_reservation_is_held_unpriced_and_has_no_expiry_yet(self) -> None:
        reservation = a_held_reservation()
        assert reservation.status is ReservationStatus.HELD
        assert reservation.lines == []
        assert reservation.subtotal_ex_vat == NOT_YET_PRICED
        assert reservation.estimated_total_inc_vat == NOT_YET_PRICED
        assert reservation.hold_expires_at is None

    def test_a_line_snapshots_every_price_on_the_product_model(self) -> None:
        """BR-20. A later catalogue price change must not rewrite this booking."""
        model = a_product_model()
        line = a_held_reservation().add_line(model, 2)
        assert line.quantity == 2
        assert line.daily_rate_snapshot == model.daily_rate
        assert line.weekly_rate_snapshot == model.weekly_rate
        assert line.deposit_snapshot == model.deposit_amount
        assert line.late_fee_per_day_snapshot == model.late_fee_per_day
        assert line.replacement_value_snapshot == model.replacement_value
        assert line.line_subtotal_ex_vat == NOT_YET_PRICED

    def test_a_line_belongs_to_its_reservation_and_takes_the_next_position(self) -> None:
        reservation = a_held_reservation()
        first = reservation.add_line(a_product_model(sku="TSH-PM-0001"), 1)
        second = reservation.add_line(a_product_model(sku="TSH-PM-0002"), 1)
        assert [first.reservation_id, second.reservation_id] == [reservation.id, reservation.id]
        assert [first.line_position, second.line_position] == [1, 2]
        assert reservation.lines == [first, second]

    def test_a_product_model_appears_once_in_a_booking(self) -> None:
        reservation = a_held_reservation()
        model = a_product_model()
        reservation.add_line(model, 1)
        with pytest.raises(ValueError, match="appears once in a booking"):
            reservation.add_line(model, 1)


class TestAReservationIsFullyAllocatedWhenEveryLineHoldsItsUnits:
    """BR-08. A booking is only collectable when each line holds what it asks for."""

    def a_line_wanting(self, quantity: int) -> tuple[Reservation, ReservationLine]:
        """Return a reservation with one line asking for `quantity` units."""
        reservation = a_held_reservation()
        return reservation, reservation.add_line(a_product_model(), quantity)

    def test_a_reservation_with_no_lines_is_not_fully_allocated(self) -> None:
        assert not a_held_reservation().is_fully_allocated()

    def test_a_line_short_of_units_is_not_satisfied(self) -> None:
        reservation, line = self.a_line_wanting(2)
        line.allocations.append(an_allocation(an_asset(), FIRST_HIRE))
        assert not line.is_satisfied()
        assert not reservation.is_fully_allocated()

    def test_a_line_holding_what_it_asks_for_is_satisfied(self) -> None:
        reservation, line = self.a_line_wanting(2)
        line.allocations.append(an_allocation(an_asset(tag="TSH-DR-0042"), FIRST_HIRE))
        line.allocations.append(an_allocation(an_asset(tag="TSH-DR-0043"), FIRST_HIRE))
        assert line.is_satisfied()
        assert reservation.is_fully_allocated()

    def test_a_released_allocation_does_not_count_towards_the_line(self) -> None:
        reservation, line = self.a_line_wanting(1)
        asset = an_asset()
        line.allocations.append(
            AssetAllocation(
                reservation_line_id=line.id,
                asset_id=asset.id,
                branch_id=asset.branch_id,
                period=FIRST_HIRE,
                allocated_at=HELD_AT,
                released_at=RELEASED_AT,
                release_reason=ReleaseReason.CANCELLED,
            )
        )
        assert line.active_allocations() == []
        assert not reservation.is_fully_allocated()
