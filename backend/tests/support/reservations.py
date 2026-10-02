"""Builders and doubles for the tests of a reservation and its states.

A reservation is built here the way a repository would hand it back, with its
lines and their allocations already in place for the status it is in. No move
of the state machine is used to get it there, so a test of one move does not
lean on another move being right.

Every instant is fixed. Monday 2 March 2026 at 08:00 UTC is the moment of the
booking, and the hire is the worked example, the ninth to the twelfth of March.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation
from app.domain.booking_line import ReservationLine
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AssetStatus, ConditionGrade, ReleaseReason, ReservationStatus
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from app.domain.states import HOLD_DURATION

# One model and how many of it, which is all a line is asked with.
type LineRequest = tuple[ProductModel, int]

NINTH: Final[date] = date(2026, 3, 9)
TWELFTH: Final[date] = date(2026, 3, 12)
HIRE: Final[BookingPeriod] = BookingPeriod(NINTH, TWELFTH)
TODAY: Final[date] = date(2026, 3, 2)
NOW: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
HOLD_EXPIRES_AT: Final[datetime] = NOW + HOLD_DURATION
CONFIRMED_AT: Final[datetime] = NOW + timedelta(minutes=10)
RELEASED_AT: Final[datetime] = datetime(2026, 3, 3, 9, 30, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ONE_DAY: Final[timedelta] = timedelta(days=1)
REFERENCE: Final[str] = "TSH-R-26-000124"
LATE_FEE: Final[str] = "140.00"
REPLACEMENT_VALUE: Final[str] = "6500.00"
NO_UNIT_FREE_MESSAGE: Final[str] = "No unit is free for these dates."

# The reason the units of a finished reservation were let go with.
_RELEASED_AS: Final[Mapping[ReservationStatus, ReleaseReason]] = {
    ReservationStatus.RETURNED: ReleaseReason.RETURNED,
    ReservationStatus.CANCELLED: ReleaseReason.CANCELLED,
    ReservationStatus.NO_SHOW: ReleaseReason.NO_SHOW,
    ReservationStatus.EXPIRED: ReleaseReason.EXPIRED,
}
# The statuses a reservation can only have reached by being confirmed.
_ONCE_CONFIRMED: Final[frozenset[ReservationStatus]] = frozenset(
    {
        ReservationStatus.CONFIRMED,
        ReservationStatus.COLLECTED,
        ReservationStatus.RETURNED,
        ReservationStatus.NO_SHOW,
    }
)


def a_product_model(
    *,
    sku: str = "TSH-PM-0001",
    name: str = "GBH 2-26 DRE Rotary Hammer",
    daily: str = "280.00",
    weekly: str = "1120.00",
    deposit: str = "1200.00",
) -> ProductModel:
    """Return a catalogue entry with five distinct figures, so a mix up shows.

    The defaults are the rotary hammer of the worked example. It may be hired
    for anything from one day to twenty eight.
    """
    return ProductModel(
        id=uuid4(),
        sku=sku,
        name=name,
        slug=sku.lower(),
        daily_rate=Decimal(daily),
        weekly_rate=Decimal(weekly),
        deposit_amount=Decimal(deposit),
        late_fee_per_day=Decimal(LATE_FEE),
        replacement_value=Decimal(REPLACEMENT_VALUE),
        min_hire_days=1,
        max_hire_days=28,
    )


HAMMER: Final[ProductModel] = a_product_model()
MIXER: Final[ProductModel] = a_product_model(
    sku="TSH-PM-0002",
    name="Concrete Mixer 140L",
    daily="450.00",
    weekly="1800.00",
    deposit="2000.00",
)
CATALOGUE: Final[Mapping[UUID, ProductModel]] = {HAMMER.id: HAMMER, MIXER.id: MIXER}
ONE_LINE: Final[tuple[LineRequest, ...]] = ((HAMMER, 2),)
TWO_LINES: Final[tuple[LineRequest, ...]] = ((HAMMER, 2), (MIXER, 1))


def an_asset(*, status: AssetStatus = AssetStatus.AVAILABLE, tag: str = "TSH-DR-0042") -> Asset:
    """Return one tagged unit in the given status."""
    return Asset(
        id=uuid4(),
        asset_tag=tag,
        product_model_id=HAMMER.id,
        branch_id=uuid4(),
        status=status,
        condition_grade=ConditionGrade.A,
    )


def an_allocation(
    line: ReservationLine,
    *,
    branch_id: UUID,
    period: BookingPeriod = HIRE,
    released_as: ReleaseReason | None = None,
) -> AssetAllocation:
    """Return the hold of one made up unit for a line.

    The hold is active unless a release reason is given. A released one was
    let go at `RELEASED_AT`.
    """
    return AssetAllocation(
        reservation_line_id=line.id,
        asset_id=uuid4(),
        branch_id=branch_id,
        period=period,
        allocated_at=NOW,
        released_at=None if released_as is None else RELEASED_AT,
        release_reason=released_as,
    )


def a_draft(*lines: LineRequest) -> Reservation:
    """Return a draft for the worked example hire, with a line for each model and quantity."""
    reservation = Reservation.draft(
        reference=REFERENCE,
        customer_profile_id=uuid4(),
        branch_id=uuid4(),
        period=HIRE,
        created_by_user_id=uuid4(),
    )
    for model, quantity in lines:
        reservation.add_line(model, quantity)
    return reservation


def a_reservation_in(
    status: ReservationStatus, lines: Sequence[LineRequest] = ONE_LINE
) -> Reservation:
    """Return a reservation as it stands in a status, with the allocations that go with it.

    A draft holds nothing. A held, confirmed or collected reservation holds
    every unit it asks for. A finished one has let every unit go, with the
    reason its ending gives. Only a held one carries a hold expiry.
    """
    reservation = a_draft(*lines)
    if status is not ReservationStatus.DRAFT:
        for line in reservation.lines:
            line.allocations.extend(
                an_allocation(
                    line, branch_id=reservation.branch_id, released_as=_RELEASED_AS.get(status)
                )
                for _ in range(line.quantity)
            )
    if status is ReservationStatus.HELD:
        reservation.hold_expires_at = HOLD_EXPIRES_AT
    if status in _ONCE_CONFIRMED:
        reservation.confirmed_at = CONFIRMED_AT
    if status is ReservationStatus.CANCELLED:
        reservation.cancelled_at = RELEASED_AT
    reservation.status = status
    return reservation


def releases_of(reservation: Reservation) -> list[tuple[ReleaseReason | None, datetime | None]]:
    """Return the release reason and time of every allocation, in line order."""
    return [
        (allocation.release_reason, allocation.released_at)
        for line in reservation.lines
        for allocation in line.allocations
    ]


@contextmanager
def refused_and_untouched[E: Exception](
    reservation: Reservation, error: type[E]
) -> Iterator[pytest.ExceptionInfo[E]]:
    """Expect the move asked inside the block to be refused, and to change nothing.

    The reservation is compared with a copy taken before the move, with its
    lines and their allocations included.
    """
    before = deepcopy(reservation)
    with pytest.raises(error) as refused:
        yield refused
    assert reservation == before, "The refused move changed the reservation."


@dataclass(slots=True)
class FakeAllocator:
    """A unit allocator that hands back made up units and remembers who asked.

    Left as it is built, it gives every line exactly its quantity, at the
    collection branch and for the hire period. Each attribute below makes it
    go wrong in one way.

    Attributes:
        surplus: How many units more than the line asks for. Negative for fewer.
        branch_id: The branch the units stand at, when it is not the collection branch.
        period: The period the units are held for, when it is not the hire period.
        serves: How many lines it serves before it finds no unit free, as a
            repository does on a conflict. None when it serves every line.
        asked_for: The key of every line it was asked about, in order.

    """

    surplus: int = 0
    branch_id: UUID | None = None
    period: BookingPeriod | None = None
    serves: int | None = None
    asked_for: list[UUID] = field(default_factory=list)

    def allocate(self, reservation: Reservation, line: ReservationLine) -> list[AssetAllocation]:
        """Return the allocations for one line, or raise the conflict a repository raises."""
        self.asked_for.append(line.id)
        if self.serves is not None and len(self.asked_for) > self.serves:
            raise AllocationConflictError(
                NO_UNIT_FREE_MESSAGE,
                branch_id=reservation.branch_id,
                period=reservation.period.as_postgres_daterange(),
                requested_quantity=line.quantity,
                available_quantity=0,
            )
        return [
            an_allocation(
                line,
                branch_id=self.branch_id or reservation.branch_id,
                period=self.period or reservation.period,
            )
            for _ in range(line.quantity + self.surplus)
        ]
