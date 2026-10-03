"""The charges a return, a loss and a settlement raise (BR-23, BR-30 to BR-32).

Four kinds of money line are raised after checkout.

A late fee belongs to the unit that came back late. It is owed, not paid, so
it is raised PENDING, and the settlement of the deposit is what pays it. The
fee is quoted including VAT (BR-30), so it is taken apart by
`split_vat_inclusive` and written as the part before VAT and the VAT, which
always add back to the fee.

A recovery charge for a unit recorded as lost is owed in the same way, and it
is quoted including VAT for the same reason. A damage report raises one too in
the change after this one.

The deposit forfeited for a lost unit and the deposit released at settlement
are deposit movements, so they carry no VAT (BR-23). Both happen at the moment
they are written, so both are written settled, numbered on the rental the way
the charges of a checkout are. A release is a negative amount, because it is
money going back to the customer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from app.domain.charge import NO_VAT_PERCENT, Charge, payment_reference
from app.domain.enums import ChargeType
from app.domain.money import Money
from app.domain.policies.late_fee import LateFee
from app.domain.rental import Rental, RentalItem
from app.domain.vat import split_vat_inclusive

SINGLE_DAY: Final[int] = 1
# Charges are numbered on a rental from one, so the next is one past the count.
POSITION_STEP: Final[int] = 1
FORFEIT_DESCRIPTION: Final[str] = "Deposit kept for a unit recorded as lost"
RECOVERY_DESCRIPTION: Final[str] = (
    "Replacement of a unit recorded as lost, less the deposit kept for it"
)
RELEASE_IN_FULL_DESCRIPTION: Final[str] = "Deposit released in full"


def next_position(rental: Rental) -> int:
    """Return where the next charge raised on a rental will stand, counted from one."""
    return len(rental.charges) + POSITION_STEP


def late_fee_charge(
    *, rental: Rental, item: RentalItem, late_fee: LateFee, raised_by: UUID, now: datetime
) -> Charge:
    """Return the late fee of one unit, owed and split into the part before VAT and the VAT.

    Args:
        rental: The rental the unit is on.
        item: The unit that came back late or was recorded as lost.
        late_fee: What the late fee policy said the unit owes.
        raised_by: The member of staff recording the return.
        now: The current instant, from the clock.

    """
    days = late_fee.chargeable_days
    in_words = f"{days} day" if days == SINGLE_DAY else f"{days} days"
    split = split_vat_inclusive(late_fee.amount)
    return Charge.owed(
        rental_id=rental.id,
        charge_type=ChargeType.LATE_FEE,
        description=(
            f"Late fee for {in_words} at R{item.terms.late_fee_per_day} a day, including VAT"
        ),
        amount_ex_vat=split.amount_ex_vat,
        vat_rate=split.vat_rate,
        vat_amount=split.vat_amount,
        raised_at=now,
        raised_by_user_id=raised_by,
        rental_item_id=item.id,
    )


def recovery_charge(
    *, rental: Rental, item: RentalItem, amount_inc_vat: Money, raised_by: UUID, now: datetime
) -> Charge:
    """Return the recovery charge for a unit recorded as lost, owed and split for VAT (BR-31).

    Args:
        rental: The rental the unit is on.
        item: The unit recorded as lost.
        amount_inc_vat: What is recovered, including VAT.
        raised_by: The member of staff recording the loss.
        now: The current instant, from the clock.

    """
    split = split_vat_inclusive(amount_inc_vat)
    return Charge.owed(
        rental_id=rental.id,
        charge_type=ChargeType.DAMAGE_RECOVERY,
        description=RECOVERY_DESCRIPTION,
        amount_ex_vat=split.amount_ex_vat,
        vat_rate=split.vat_rate,
        vat_amount=split.vat_amount,
        raised_at=now,
        raised_by_user_id=raised_by,
        rental_item_id=item.id,
    )


def deposit_forfeit_charge(
    *, rental: Rental, item: RentalItem, forfeited: Money, raised_by: UUID, now: datetime
) -> Charge:
    """Return the deposit kept for a unit recorded as lost, settled from the deposit held.

    Args:
        rental: The rental the unit is on.
        item: The unit recorded as lost.
        forfeited: The deposit held for that unit.
        raised_by: The member of staff recording the loss.
        now: The current instant, from the clock.

    """
    return Charge.settled_at_the_counter(
        rental_id=rental.id,
        charge_type=ChargeType.DEPOSIT_FORFEIT,
        description=FORFEIT_DESCRIPTION,
        amount_ex_vat=forfeited,
        vat_rate=NO_VAT_PERCENT,
        vat_amount=Money.zero(),
        raised_at=now,
        raised_by_user_id=raised_by,
        reference=payment_reference(rental.reference, next_position(rental)),
        rental_item_id=item.id,
    )


def deposit_release_charge(
    *, rental: Rental, released: Money, withheld: Money, raised_by: UUID, now: datetime
) -> Charge:
    """Return the part of the deposit given back at settlement, as a negative amount (BR-32).

    Args:
        rental: The rental being settled.
        released: What is given back, a positive amount.
        withheld: What was kept, which the description names.
        raised_by: The member of staff settling it.
        now: The current instant, from the clock.

    """
    kept = withheld.rounded().amount
    return Charge.settled_at_the_counter(
        rental_id=rental.id,
        charge_type=ChargeType.DEPOSIT_RELEASE,
        description=(
            f"Deposit released after R{kept} was withheld"
            if withheld > Money.zero()
            else RELEASE_IN_FULL_DESCRIPTION
        ),
        amount_ex_vat=Money.zero().subtract(released),
        vat_rate=NO_VAT_PERCENT,
        vat_amount=Money.zero(),
        raised_at=now,
        raised_by_user_id=raised_by,
        reference=payment_reference(rental.reference, next_position(rental)),
    )
