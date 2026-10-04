"""Run one planned hire through the domain, the way the counter would have run it.

The planner decides what happened and when. This module makes it happen with
the application's own rules and nothing of its own. The reservation is drafted,
priced by the standard pricing policy from the rates copied onto its lines with
the customer's trade discount, put on hold with the units the planner chose and
confirmed. It is checked out, which raises the hire charge and the deposit
hold. It is returned on the day the planner says, which raises a late fee from
the standard late fee policy when the units came back late and releases every
allocation with the reason RETURNED.

A damaged unit is flagged at the return and a report is filed for it, which
raises a recovery when the customer is charged. The deposit is settled the
moment nothing waits any more, which is the return or the report, exactly as
the use cases do it. A balance the deposit could not cover is paid at the
counter a few minutes later. The report is then sent for repair and resolved
with what the repair cost, and the unit goes back on the shelf.

No audit event is written for any of it. The audit log records what the
application did, and the application did none of this.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation, ReservationLine
from app.domain.catalogue import Asset, ProductModel
from app.domain.charge import PAYMENT_REFERENCE_PREFIX
from app.domain.checkout import HandOver, check_out
from app.domain.damage import DamageReport
from app.domain.damage_filing import DamageFiling, UnitLastHire, file_damage_report
from app.domain.damage_units import back_in_service, sent_for_repair
from app.domain.enums import AssetStatus, DamageStatus, RentalStatus, ReservationStatus
from app.domain.policies import StandardLateFeePolicy, StandardPricingPolicy
from app.domain.quarantine import assessment_of, assessments_due_on
from app.domain.rental import Rental
from app.domain.returns import ClosedUnit, ItemReturn, return_items
from app.domain.settlement import (
    deposit_was_settled,
    record_balance_payment,
    settle_deposit,
    settlement_wait,
)
from seeding.errors import SeedDataError
from seeding.trading_records import PlannedDamage, PlannedHire

PRICING_POLICY: Final[StandardPricingPolicy] = StandardPricingPolicy()
LATE_FEE_POLICY: Final[StandardLateFeePolicy] = StandardLateFeePolicy()
BALANCE_PAID_AFTER: Final[timedelta] = timedelta(minutes=6)
BALANCE_REFERENCE_SUFFIX: Final[str] = "BAL"
NO_OTHER_OPEN_REPORTS: Final[int] = 0
NOTHING_DUE: Final[Decimal] = Decimal("0")


@dataclass(frozen=True, slots=True)
class HireCast:
    """Who one hire involves, resolved from the database.

    Attributes:
        branch_id: The branch the units went out from.
        customer_profile_id: The customer who hired.
        discount_percent: The customer's trade discount at the time.
        booked_by: The account that made the booking, the customer's own
            when they booked online and the counter's otherwise.
        staff_id: The member of staff at the branch who handed over, took
            back, settled and reported.

    """

    branch_id: UUID
    customer_profile_id: UUID
    discount_percent: Decimal
    booked_by: UUID
    staff_id: UUID


@dataclass(frozen=True, slots=True)
class FleetBook:
    """The catalogue and the units, as the domain sees them.

    Attributes:
        models: Every product model by SKU.
        units: Every unit the history may hire, on the shelf, by its key.

    """

    models: Mapping[str, ProductModel]
    units: Mapping[UUID, Asset]


@dataclass(frozen=True, slots=True)
class HireOutcome:
    """What one hire left behind, ready to be written.

    Attributes:
        reservation: The reservation, RETURNED, with its lines and released allocations.
        rental: The rental, SETTLED, with its items and every charge.
        report: The damage report, RESOLVED, or None.

    """

    reservation: Reservation
    rental: Rental
    report: DamageReport | None


class _PlannedUnits:
    """An allocator that holds the units the planner chose for each line."""

    def __init__(self, units_by_model: Mapping[UUID, Sequence[Asset]], at: datetime) -> None:
        """Keep the chosen units by the model they are for, and the moment of the hold."""
        self._units_by_model = units_by_model
        self._at = at

    def allocate(
        self, reservation: Reservation, line: ReservationLine
    ) -> Sequence[AssetAllocation]:
        """Hold the chosen units of the line's model for the reservation's period."""
        return [
            AssetAllocation.hold(
                reservation_line_id=line.id,
                asset=unit,
                period=reservation.period,
                allocated_at=self._at,
            )
            for unit in self._units_by_model[line.product_model_id]
        ]


def run_hire(plan: PlannedHire, cast: HireCast, fleet: FleetBook) -> HireOutcome:
    """Book, check out, return, settle and close one planned hire through the domain.

    Raises:
        SeedDataError: If the hire does not end settled and closed, which would
            mean the plan asked the domain for something it refuses.
        ValidationFailure: If the domain refuses the booking or a return.
        StateTransitionError: If the domain refuses a move of the hire.

    """
    reservation = _booked(plan, cast, fleet)
    on_lines = [fleet.models[line.sku] for line in plan.lines]
    checkout = check_out(
        reservation=reservation,
        hand_overs=_hand_overs(reservation, fleet),
        agreement_signed=True,
        reference=plan.rental_reference,
        model_names={model.id: model.name for model in on_lines},
        units=fleet.units,
        checked_out_by=cast.staff_id,
        now=plan.times.checked_out_at,
        today=plan.period.start,
    )
    rental = checkout.rental
    damaged_id = plan.damage.asset_id if plan.damage is not None else None
    returned = return_items(
        rental=rental,
        reservation=reservation,
        returns=[
            ItemReturn(
                rental_item_id=item.id,
                condition_in=item.condition_out,
                flagged_for_damage=item.asset_id == damaged_id,
            )
            for item in rental.items
        ],
        units={unit.id: unit for unit in checkout.units},
        policy=LATE_FEE_POLICY,
        returned_by=cast.staff_id,
        now=plan.returned_at,
        today=plan.returned_on,
    )
    _settle_when_nothing_waits(rental, cast.staff_id, plan.returned_at)
    report = None
    if plan.damage is not None:
        report = _report_damage(plan.damage, rental, returned.units, cast.staff_id)
    _ensure_closed(plan, reservation, rental)
    return HireOutcome(reservation=reservation, rental=rental, report=report)


def _booked(plan: PlannedHire, cast: HireCast, fleet: FleetBook) -> Reservation:
    """Draft, price, hold and confirm the reservation of a planned hire."""
    reservation = Reservation.draft(
        reference=plan.reservation_reference,
        customer_profile_id=cast.customer_profile_id,
        branch_id=cast.branch_id,
        period=plan.period,
        created_by_user_id=cast.booked_by,
    )
    chosen: dict[UUID, list[Asset]] = {}
    for line in plan.lines:
        model = fleet.models[line.sku]
        reservation.add_line(model, len(line.asset_ids))
        chosen[model.id] = [fleet.units[asset_id] for asset_id in line.asset_ids]
    reservation.price_with(PRICING_POLICY, cast.discount_percent)
    booked_at = plan.times.booked_at
    reservation.hold(
        now=booked_at,
        today=booked_at.date(),
        models={model.id: model for model in fleet.models.values()},
        allocator=_PlannedUnits(chosen, booked_at),
    )
    reservation.confirm(now=plan.times.confirmed_at, email_verified=True)
    return reservation


def _hand_overs(reservation: Reservation, fleet: FleetBook) -> list[HandOver]:
    """Return every held unit as the counter hands it over, in the grade it stands in."""
    return [
        HandOver(
            allocation_id=allocation.id,
            condition_out=fleet.units[allocation.asset_id].condition_grade,
        )
        for line in reservation.lines
        for allocation in line.allocations
    ]


def _report_damage(
    damage: PlannedDamage, rental: Rental, closed: Sequence[ClosedUnit], staff_id: UUID
) -> DamageReport:
    """File the report of the damaged unit, settle the hire, then repair and resolve it."""
    back = next(unit for unit in closed if unit.item.asset_id == damage.asset_id)
    plan = damage.plan
    filed = file_damage_report(
        DamageFiling(
            rental_item_id=back.item.id,
            severity=plan.severity,
            description=plan.description,
            repair_estimate=plan.repair_estimate,
            chargeable_to_customer=plan.recovery_inc_vat is not None,
            recovery_amount=plan.recovery_inc_vat,
        ),
        unit=back.unit,
        rental=rental,
        last_hire=UnitLastHire(back.item.id, rental.reference, assessment_of(back.item)),
        reference=damage.reference,
        reported_by=staff_id,
        now=damage.reported_at,
    )
    _settle_when_nothing_waits(rental, staff_id, damage.reported_at)
    report = filed.report
    report.send_for_repair()
    in_workshop = sent_for_repair(filed.unit)
    report.close(
        DamageStatus.RESOLVED,
        actual_repair_cost=plan.actual_repair_cost,
        notes=plan.resolution_notes,
        now=damage.resolved_at,
    )
    shelved = back_in_service(in_workshop, other_open_reports=NO_OTHER_OPEN_REPORTS)
    if shelved.status is not AssetStatus.AVAILABLE:
        raise SeedDataError(
            f"Unit {shelved.asset_tag} ended report {damage.reference} {shelved.status.value} "
            "and not AVAILABLE, so the history would change today's fleet."
        )
    return report


def _settle_when_nothing_waits(rental: Rental, staff_id: UUID, now: datetime) -> None:
    """Settle the deposit once nothing waits, and pay any balance a few minutes later."""
    waiting = settlement_wait(
        status=rental.status,
        items_out=len(rental.items_out()),
        assessments_due=assessments_due_on(rental),
        balance_due=rental.balance_due,
    )
    if waiting is not None or deposit_was_settled(rental):
        return
    settle_deposit(rental, settled_by=staff_id, now=now)
    if rental.balance_due > NOTHING_DUE:
        record_balance_payment(
            rental,
            payment_reference=(
                f"{PAYMENT_REFERENCE_PREFIX}-{rental.reference}-{BALANCE_REFERENCE_SUFFIX}"
            ),
            now=now + BALANCE_PAID_AFTER,
        )


def _ensure_closed(plan: PlannedHire, reservation: Reservation, rental: Rental) -> None:
    """Refuse a hire the domain did not leave settled, returned and holding no unit.

    Raises:
        SeedDataError: Naming the hire and what was left open.

    """
    open_ends = []
    if rental.status is not RentalStatus.SETTLED:
        open_ends.append(f"rental status {rental.status.value}")
    if reservation.status is not ReservationStatus.RETURNED:
        open_ends.append(f"reservation status {reservation.status.value}")
    if reservation.has_active_allocations():
        open_ends.append("an allocation still holds a unit")
    if rental.deposit_withheld + rental.deposit_refunded != rental.deposit_held:
        open_ends.append("the deposit kept and given back do not add up to the deposit held")
    if open_ends:
        raise SeedDataError(
            f"Hire {plan.reservation_reference} was left open, {', '.join(open_ends)}. The "
            "history writes only hires that are closed and settled."
        )
