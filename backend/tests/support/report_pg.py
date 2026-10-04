"""Rows of a fleet with a history, built for the report tests on PostgreSQL.

The report reads hires, bookings, charges, damage reports and recorded
changes of status, so a test of it needs those rows with their dates set by
hand and without driving each of them through the routes. `FleetBuilder`
writes them in the shape the schema requires, and a test names only the dates
and amounts it worked out by hand.

Every instant is given as a day and a time on a clock in Cape Town. Like the
other factories it flushes and never commits, so the test owns the
transaction.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final

from app.domain.business_time import business_instant
from app.domain.enums import (
    AssetStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    ReleaseReason,
    RentalStatus,
    ReservationStatus,
)
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    AuditEvent,
    Branch,
    Charge,
    CustomerProfile,
    DamageReport,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
    UserAccount,
)
from tests.support.factories import Factory

MORNING: Final[time] = time(10, 0)
NOTHING: Final[Decimal] = Decimal("0.00")
ACQUISITION_COST: Final[Decimal] = Decimal("3980.00")
WAIVER_REASON: Final[str] = "Waived as a goodwill gesture."
VAT_PERCENT: Final[Decimal] = Decimal("15.00")
NO_VAT_PERCENT: Final[Decimal] = Decimal("0.00")
ASSET_ENTITY: Final[str] = "asset"
STATUS_CHANGED: Final[str] = "asset.status_changed"
DEPOSIT_TYPES: Final[frozenset[ChargeType]] = frozenset(
    {ChargeType.DEPOSIT_HOLD, ChargeType.DEPOSIT_RELEASE, ChargeType.DEPOSIT_FORFEIT}
)

_numbers: Final[itertools.count[int]] = itertools.count(1)


def cape_town(day: date, wall_time: time = MORNING) -> datetime:
    """Return the instant a clock in Cape Town shows a time on a day, in UTC."""
    return business_instant(day, wall_time).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a booking, the units it holds and its amount excluding VAT."""

    model: ProductModel
    units: list[Asset]
    amount: Decimal = NOTHING


@dataclass
class Booking:
    """A reservation built by the builder, with the allocation of each unit by its key."""

    reservation: Reservation
    allocations: dict[object, AssetAllocation] = field(default_factory=dict)


@dataclass
class FleetBuilder:
    """Writes the rows of a fleet with a history, through one session."""

    factory: Factory
    staff: UserAccount
    customer: CustomerProfile

    def unit(
        self,
        tag: str,
        model: ProductModel,
        branch: Branch,
        *,
        acquired_on: date,
        status: AssetStatus = AssetStatus.AVAILABLE,
        retired_on: date | None = None,
    ) -> Asset:
        """Write one unit with the tag, the day it was acquired and its status now."""
        unit = Asset(
            asset_tag=tag,
            product_model_id=model.id,
            branch_id=branch.id,
            status=status,
            condition_grade=ConditionGrade.A,
            acquired_on=acquired_on,
            acquisition_cost=ACQUISITION_COST,
            retired_on=retired_on,
        )
        self._flushed(unit)
        return unit

    def booking(
        self,
        branch: Branch,
        period: BookingPeriod,
        lines: list[Line],
        *,
        status: ReservationStatus,
        released: ReleaseReason | None = None,
        hold_expires_at: datetime | None = None,
    ) -> Booking:
        """Write a reservation in a status with its lines and one allocation for each unit."""
        reservation = self.factory.reservation(
            profile=self.customer, created_by=self.staff, branch=branch, period=period
        )
        reservation.status = status
        reservation.hold_expires_at = hold_expires_at
        reservation.subtotal_ex_vat = sum((line.amount for line in lines), NOTHING)
        self._flushed(reservation)
        booking = Booking(reservation=reservation)
        for position, line in enumerate(lines, start=1):
            row = ReservationLine(
                reservation_id=reservation.id,
                product_model_id=line.model.id,
                quantity=len(line.units),
                line_position=position,
                daily_rate_snapshot=line.model.daily_rate,
                weekly_rate_snapshot=line.model.weekly_rate,
                deposit_snapshot=line.model.deposit_amount,
                late_fee_per_day_snapshot=line.model.late_fee_per_day,
                replacement_value_snapshot=line.model.replacement_value,
                line_subtotal_ex_vat=line.amount,
            )
            self._flushed(row)
            for unit in line.units:
                allocation = self.factory.allocation(
                    line=row,
                    asset=unit,
                    period=period,
                    released_at=cape_town(period.start) if released is not None else None,
                    release_reason=released,
                )
                self._flushed(allocation)
                booking.allocations[unit.id] = allocation
        return booking

    def rental(
        self,
        booking: Booking,
        *,
        out: date,
        returns: dict[object, tuple[datetime, ConditionGrade | None]],
    ) -> dict[object, RentalItem]:
        """Write the rental of a collected booking and an item for each unit, some come back.

        Args:
            booking: The collected booking.
            out: The day every unit went out, at ten in the morning.
            returns: When each unit that is back came back, by its key, with
                the grade it came back in, or None for a unit recorded as lost.

        """
        reservation = booking.reservation
        all_back = len(returns) == len(booking.allocations)
        rental = Rental(
            reference=f"TSH-H-26-{900000 + next(_numbers):06d}",
            reservation_id=reservation.id,
            branch_id=reservation.branch_id,
            status=RentalStatus.RETURNED if all_back else RentalStatus.OPEN,
            checked_out_at=cape_town(out),
            checked_out_by_user_id=self.staff.id,
            due_back_on=reservation.end_date,
            deposit_held=NOTHING,
            returned_at=max(back for back, _grade in returns.values()) if all_back else None,
            agreement_signed=True,
        )
        self._flushed(rental)
        items: dict[object, RentalItem] = {}
        for unit_id, allocation in booking.allocations.items():
            back, grade = returns.get(unit_id, (None, None))
            item = RentalItem(
                rental_id=rental.id,
                asset_allocation_id=allocation.id,
                asset_id=allocation.asset_id,
                condition_out=ConditionGrade.A,
                condition_in=grade,
                checked_out_at=cape_town(out),
                returned_at=back,
            )
            self._flushed(item)
            items[unit_id] = item
        return items

    def charge(
        self,
        item: RentalItem,
        charge_type: ChargeType,
        amount_ex_vat: str,
        raised_on: date,
        *,
        on_the_unit: bool = True,
        status: ChargeStatus = ChargeStatus.SETTLED,
        reverses: Charge | None = None,
    ) -> Charge:
        """Write a charge on the rental of an item, on the unit itself or on the whole hire."""
        amount = Decimal(amount_ex_vat)
        rate = NO_VAT_PERCENT if charge_type in DEPOSIT_TYPES else VAT_PERCENT
        vat = (amount * rate / Decimal(100)).quantize(Decimal("0.01"))
        charge = Charge(
            rental_id=item.rental_id,
            rental_item_id=item.id if on_the_unit else None,
            charge_type=charge_type,
            description=f"{charge_type.value} for the report test",
            amount_ex_vat=amount,
            vat_rate=rate,
            vat_amount=vat,
            amount_inc_vat=amount + vat,
            status=status,
            raised_at=cape_town(raised_on),
            raised_by_user_id=self.staff.id,
            reverses_charge_id=reverses.id if reverses is not None else None,
            waiver_reason=WAIVER_REASON if status is ChargeStatus.WAIVED else None,
        )
        self._flushed(charge)
        return charge

    def damage(
        self,
        unit: Asset,
        reported_at: datetime,
        *,
        status: DamageStatus,
        resolved_at: datetime | None = None,
        actual_repair_cost: str | None = None,
        item: RentalItem | None = None,
    ) -> DamageReport:
        """Write a damage report of a unit, open or closed."""
        report = DamageReport(
            reference=f"TSH-D-26-{90000 + next(_numbers):05d}",
            asset_id=unit.id,
            rental_item_id=item.id if item is not None else None,
            severity=DamageSeverity.MAJOR,
            status=status,
            description="Damage found and recorded for the report test.",
            repair_estimate=Decimal("400.00"),
            actual_repair_cost=Decimal(actual_repair_cost) if actual_repair_cost else None,
            chargeable_to_customer=item is not None,
            reported_by_user_id=self.staff.id,
            reported_at=reported_at,
            resolved_at=resolved_at,
        )
        self._flushed(report)
        return report

    def moved(
        self, unit: Asset, at: datetime, moved_from: AssetStatus, moved_to: AssetStatus
    ) -> None:
        """Write the audit event of a unit's status changing, the way the application writes it."""
        self._flushed(
            AuditEvent(
                occurred_at=at,
                actor_user_id=self.staff.id,
                actor_role=self.staff.role,
                entity_type=ASSET_ENTITY,
                entity_id=unit.id,
                action=STATUS_CHANGED,
                before_state={"status": moved_from.value},
                after_state={"status": moved_to.value, "asset_tag": unit.asset_tag},
            )
        )

    def _flushed(self, row: object) -> None:
        """Add a row and flush it, so its keys and defaults exist."""
        self.factory.session.add(row)
        self.factory.session.flush()
