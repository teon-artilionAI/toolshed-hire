"""Recording a unit as lost, which is BR-31.

Late fee stops accruing on a unit after the number of days the late fee policy
names, which is fourteen. A unit still out after that may be recorded as lost.
I read the rule as four things, done together.

1. The unit is charged the late fee for the days the policy charges, which is
   fourteen days and no more.
2. Its allocation is let go first, because a unit may not be marked lost while
   it holds an active allocation (BR-37). There is no release reason for a
   loss, so it is let go with the reason RETURNED, which is the reason that
   ends a hire. The unit then moves from ON_HIRE to LOST through the asset
   state model.
3. The deposit held for that one unit, copied onto its booking line, is kept
   as a DEPOSIT_FORFEIT charge, settled from the deposit already held.
4. What the unit is worth beyond that deposit is recovered. The recovery is
   the replacement value copied onto the booking less the deposit kept, never
   below nothing and so never above the replacement value. It is a
   DAMAGE_RECOVERY charge that includes VAT and is owed like a late fee.

So a lost unit costs the customer its replacement value and fourteen days of
late fee, and the deposit pays what it can of that when the hire is settled.

The unit is closed on the rental at the moment it is recorded, with no
condition, so the rental moves on as though it had come back. When it was the
last unit out, the hire is closed and the reservation with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.domain.asset_lifecycle import moved
from app.domain.booking import Reservation
from app.domain.catalogue import Asset
from app.domain.charge import Charge
from app.domain.enums import AssetStatus, RentalStatus
from app.domain.errors import NotFound, StateTransitionError
from app.domain.money import Money
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.rental import Rental
from app.domain.return_charges import deposit_forfeit_charge, late_fee_charge, recovery_charge
from app.domain.returns import (
    ClosedUnit,
    close_if_all_back,
    ensure_still_out,
    late_fee_of,
    release_allocation_of,
)

LOSS_RULE: Final[str] = "BR-31"
LOST_NOTE: Final[str] = "Recorded as lost. Not returned more than fourteen days after it was due."
ITEM_NOT_ON_RENTAL_MESSAGE: Final[str] = (
    "We could not find that unit on this rental. Check the rental and try again."
)
NOT_LATE_ENOUGH_MESSAGE: Final[str] = (
    "This unit is not late enough to be recorded as lost. A unit can be recorded as lost "
    "once it is more than fourteen days past its due date."
)


@dataclass(frozen=True, slots=True)
class LossOutcome:
    """What recording a loss did, for the caller to store and to record.

    Attributes:
        unit: The unit, closed, with its late fee.
        forfeit_charge: The deposit kept for it, or None when it carried none.
        recovery_charge: The recovery raised, or None when the deposit
            already covered the replacement value.
        status_before: The status of the rental before the loss.
        closed_the_hire: True when it was the last unit out.

    """

    unit: ClosedUnit
    forfeit_charge: Charge | None
    recovery_charge: Charge | None
    status_before: RentalStatus
    closed_the_hire: bool


def record_loss(
    *,
    rental: Rental,
    reservation: Reservation,
    rental_item_id: UUID,
    units: Mapping[UUID, Asset],
    policy: LateFeePolicy,
    recorded_by: UUID,
    now: datetime,
    today: date,
) -> LossOutcome:
    """Record one unit that never came back as lost, and charge for it (BR-31).

    Args:
        rental: The rental, locked by the caller, with its items and charges.
        reservation: The reservation it was opened from, locked by the caller.
        rental_item_id: The unit, by the key of its rental item.
        units: The unit, by its key, locked by the caller.
        policy: The late fee policy, which also says when a unit is beyond accrual.
        recorded_by: The member of staff recording the loss.
        now: The current instant, from the clock.
        today: The current business day, from the clock.

    Raises:
        NotFound: If the unit is not on this rental.
        StateTransitionError: If the unit is already back, or is not yet late
            enough to be recorded as lost.

    """
    item = rental.item_with_id(rental_item_id)
    if item is None:
        raise NotFound(ITEM_NOT_ON_RENTAL_MESSAGE, {"rental_item_id": str(rental_item_id)})
    ensure_still_out(item)
    late = late_fee_of(rental, item, policy, today)
    if not late.beyond_accrual:
        raise StateTransitionError(
            NOT_LATE_ENOUGH_MESSAGE,
            from_status=AssetStatus.ON_HIRE.value,
            to_status=AssetStatus.LOST.value,
            rule=LOSS_RULE,
        )
    status_before = rental.status
    item.returned_at = now
    item.days_late = late.days_late
    item.notes = LOST_NOTE
    release_allocation_of(reservation, item, now)
    unit = units[item.asset_id]
    # The forfeit is raised first. It is settled the moment it is raised, so
    # it is numbered then, and the two owed charges raised in the same instant
    # are read back after it, which keeps the number the settlement gives
    # each of them from ever being one the forfeit already carries.
    forfeited = Money.create(item.terms.deposit).rounded()
    forfeit = None
    if forfeited > Money.zero():
        forfeit = deposit_forfeit_charge(
            rental=rental, item=item, forfeited=forfeited, raised_by=recorded_by, now=now
        )
        rental.charges.append(forfeit)
    fee = None
    if late.is_due():
        fee = late_fee_charge(
            rental=rental, item=item, late_fee=late, raised_by=recorded_by, now=now
        )
        rental.charges.append(fee)
    recovery = None
    recovered = recovery_after_forfeit(Money.create(item.terms.replacement_value), forfeited)
    if recovered > Money.zero():
        recovery = recovery_charge(
            rental=rental, item=item, amount_inc_vat=recovered, raised_by=recorded_by, now=now
        )
        rental.charges.append(recovery)
    return LossOutcome(
        unit=ClosedUnit(
            item=item,
            unit_before=unit,
            unit=moved(unit, AssetStatus.LOST),
            late_fee=late,
            late_fee_charge=fee,
        ),
        forfeit_charge=forfeit,
        recovery_charge=recovery,
        status_before=status_before,
        closed_the_hire=close_if_all_back(rental, reservation, recorded_by, now, today),
    )


def recovery_after_forfeit(replacement_value: Money, forfeited: Money) -> Money:
    """Return what is recovered for a lost unit beyond the deposit kept for it (BR-31, BR-39).

    It is the replacement value less the deposit kept, never below nothing,
    and so never above the replacement value. Rounded to the cent.
    """
    remainder = replacement_value.subtract(forfeited).rounded()
    return remainder if remainder > Money.zero() else Money.zero().rounded()
