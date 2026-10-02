"""The second line of defence in the booking module, which no request should reach.

The HTTP boundary validates a quantity, a page and a page size before a use
case ever sees them. The foreign keys keep a reservation pointing at a customer
and a model that exist. Each of those has a second check further in all the
same, so a caller inside the system cannot hand a repository a negative offset
or allocate eleven units to one line, and so a fault in the data is reported
as the fault it is and not as something a customer did wrong.

These tests reach those checks directly, because nothing that goes through a
route can.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import uuid4

import pytest

from app.application.availability.allocation import AllocationCommand, allocate_assets
from app.application.booking.read_models import (
    REFERENCE_MAX_LENGTH,
    ReservationKey,
    ReservationSearch,
)
from app.domain.business_time import BUSINESS_TIME_ZONE, in_business_time
from app.domain.enums import ReservationStatus
from app.domain.errors import ValidationFailure
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.memory import InMemoryUnitOfWork
from tests.support.memory_world import FIRST_HIRE, build_memory_world, open_desk

REFERENCE: Final[str] = "TSH-R-26-000124"


class TestTheAllocationAlgorithmRefusesAQuantityNoLineCanCarry:
    """One to ten units to a line, whoever is asking."""

    @pytest.mark.parametrize("quantity", [0, 11])
    def test_a_quantity_outside_one_to_ten_is_refused_before_any_unit_is_locked(
        self, quantity: int
    ) -> None:
        world = build_memory_world(asset_count=12)
        command = AllocationCommand(
            reservation_line_id=uuid4(),
            product_model_id=world.product_model.id,
            branch_id=world.branch.id,
            period=FIRST_HIRE,
            quantity=quantity,
        )
        with InMemoryUnitOfWork(world.store) as uow, pytest.raises(ValidationFailure) as refusal:
            allocate_assets(uow.assets, FixedClock(), command)
        assert refusal.value.detail == {"minimum": 1, "maximum": 10, "received": quantity}
        assert world.store.committed.allocations == []


class TestAListCannotBeAskedForOutOfRange:
    """The page and the page size are bounded where the search is built."""

    @pytest.mark.parametrize("page", [0, -1, 10_001])
    def test_a_page_outside_the_range_cannot_be_built(self, page: int) -> None:
        with pytest.raises(ValueError, match="A page is between 1 and 10000"):
            ReservationSearch(page=page)

    @pytest.mark.parametrize("page_size", [0, 51])
    def test_a_page_size_outside_the_range_cannot_be_built(self, page_size: int) -> None:
        with pytest.raises(ValueError, match="between 1 and 50 reservations"):
            ReservationSearch(page_size=page_size)

    def test_the_offset_is_the_reservations_before_the_page(self) -> None:
        assert ReservationSearch(page=3, page_size=20).offset == 40
        assert ReservationSearch().offset == 0


class TestAReservationIsNamedByItsKeyOrItsReference:
    """Whatever a caller typed is read as a key when it is one, and a reference otherwise."""

    def test_a_uuid_is_read_as_the_key(self) -> None:
        reservation_id = uuid4()
        key = ReservationKey.parse(f"  {reservation_id}  ")
        assert key == ReservationKey.of(reservation_id)
        assert str(key) == str(reservation_id)

    def test_anything_else_is_read_as_a_reference_in_upper_case(self) -> None:
        key = ReservationKey.parse(" tsh-r-26-000124 ")
        assert key.reservation_id is None
        assert key.reference == REFERENCE
        assert str(key) == REFERENCE

    def test_a_reference_is_never_longer_than_its_column(self) -> None:
        assert len(str(ReservationKey.parse("x" * 40).reference)) == REFERENCE_MAX_LENGTH


class TestAFaultInTheDataIsReportedAsOne:
    """A reservation whose customer or model cannot be read is not the caller's mistake."""

    def test_a_reservation_whose_customer_profile_is_gone_fails_loudly(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        world.store.profiles.clear()
        with pytest.raises(LookupError, match="customer profile"):
            desk.hold.execute(desk.command_for(draft, actor=world.assistant()))

    def test_a_line_whose_product_model_is_gone_fails_loudly(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        world.store.product_models.clear()
        with pytest.raises(LookupError, match="product model"):
            desk.hold.execute(desk.command_for(draft))
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT


class TestBusinessTime:
    """An instant is read on a clock in Cape Town, and one with no zone is refused."""

    def test_an_instant_in_utc_is_two_hours_later_in_cape_town(self) -> None:
        local = in_business_time(DEFAULT_INSTANT)
        assert (local.hour, local.minute) == (10, 0)
        assert str(local.tzinfo) == BUSINESS_TIME_ZONE

    def test_an_instant_with_no_zone_is_refused(self) -> None:
        with pytest.raises(ValueError, match="has no time zone"):
            in_business_time(datetime(2026, 3, 2, 8, 0))

    def test_a_status_prints_as_its_stored_value(self) -> None:
        assert str(ReservationStatus.NO_SHOW) == "NO_SHOW"
