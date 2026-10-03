"""The two charges a checkout raises, which are the hire and the deposit hold (BR-20, BR-27).

Both are paid at the counter, so both are written settled, with a simulated
settlement reference that numbers them on the rental (BR-33).

The hire charge is the figures already stored on the reservation, its
subtotal and its VAT, and is never worked out again from the catalogue or the
pricing policy (BR-20). On a hire of one unit it belongs to that unit, as the
worked example of the design document does. On a hire of several it belongs to
the hire as a whole, because the stored figures are the sum of lines that may
have been rounded and discounted separately, and splitting them between units
would invent a cent here and there.

The deposit hold is the deposit copied onto each line, once for every unit of
the line that is collected (BR-27). It is added up unit by unit, so no amount
is multiplied here, and it carries no VAT (BR-23).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.booking import Reservation
from app.domain.charge import DESCRIPTION_MAX_LENGTH, NO_VAT_PERCENT, Charge, payment_reference
from app.domain.enums import ChargeType
from app.domain.money import Money
from app.domain.rental import Rental
from app.domain.vat import VAT_RATE_PERCENT

DEPOSIT_HOLD_DESCRIPTION: Final[str] = "Refundable deposit held at collection"
# Where the two charges of a checkout stand among the charges of the rental.
HIRE_CHARGE_POSITION: Final[int] = 1
DEPOSIT_CHARGE_POSITION: Final[int] = 2
SINGLE_UNIT: Final[int] = 1
SINGLE_DAY: Final[int] = 1
LINE_SEPARATOR: Final[str] = "; "


def deposit_to_hold(per_unit_deposits: Iterable[Decimal]) -> Money:
    """Return the deposit taken at checkout, one unit's deposit for every unit collected (BR-27).

    Args:
        per_unit_deposits: The deposit copied onto the line of each unit
            collected, once for every unit.

    """
    total = Money.zero()
    for deposit in per_unit_deposits:
        total = total.add(Money.create(deposit))
    return total.rounded()


def hire_description(
    lines: Sequence[tuple[str, int]], hire_days: int, discount_percent: Decimal
) -> str:
    """Return what the customer reads beside the hire charge.

    Args:
        lines: The name of each model collected and how many of its units, in
            line order.
        hire_days: The days of the hire.
        discount_percent: The trade discount the hire was priced with.

    Returns:
        For example "Bosch GBH 2-26, 3 days" or "2 x Bosch GBH 2-26; Concrete
        Mixer 140L, 3 days, less 10.00% trade discount". A list too long for
        the column is written as a count of units instead.

    """
    days = f"{hire_days} day" if hire_days == SINGLE_DAY else f"{hire_days} days"
    discount = f", less {discount_percent}% trade discount" if discount_percent else ""
    named = LINE_SEPARATOR.join(
        name if count == SINGLE_UNIT else f"{count} x {name}" for name, count in lines
    )
    description = f"{named}, {days}{discount}"
    if len(description) > DESCRIPTION_MAX_LENGTH:
        unit_count = sum(count for _name, count in lines)
        description = f"Hire of {unit_count} units, {days}{discount}"
    return description


def hire_charge(
    *,
    rental: Rental,
    reservation: Reservation,
    units_by_line: Mapping[UUID, int],
    model_names: Mapping[UUID, str],
    raised_by: UUID,
) -> Charge:
    """Return the hire charge of a checkout, from the figures stored on the reservation.

    Args:
        rental: The rental being opened, with its items.
        reservation: The reservation it is opened from.
        units_by_line: How many units of each line are collected, by the key
            of the line.
        model_names: The name of each model on the reservation, by its key.
        raised_by: The member of staff taking the payment.

    """
    lines = [
        (model_names[line.product_model_id], units_by_line[line.id])
        for line in reservation.lines
        if units_by_line.get(line.id)
    ]
    return Charge.settled_at_the_counter(
        rental_id=rental.id,
        charge_type=ChargeType.HIRE,
        description=hire_description(
            lines, reservation.period.days, reservation.discount_percent()
        ),
        amount_ex_vat=reservation.subtotal_ex_vat(),
        vat_rate=VAT_RATE_PERCENT,
        vat_amount=Money.create(reservation.vat_amount),
        raised_at=rental.checked_out_at,
        raised_by_user_id=raised_by,
        reference=payment_reference(rental.reference, HIRE_CHARGE_POSITION),
        rental_item_id=rental.items[0].id if len(rental.items) == SINGLE_UNIT else None,
    )


def deposit_hold_charge(*, rental: Rental, deposit: Money, raised_by: UUID) -> Charge:
    """Return the deposit hold of a checkout, which belongs to the hire as a whole.

    Args:
        rental: The rental being opened.
        deposit: The deposit taken, from `deposit_to_hold`.
        raised_by: The member of staff taking the payment.

    """
    return Charge.settled_at_the_counter(
        rental_id=rental.id,
        charge_type=ChargeType.DEPOSIT_HOLD,
        description=DEPOSIT_HOLD_DESCRIPTION,
        amount_ex_vat=deposit,
        vat_rate=NO_VAT_PERCENT,
        vat_amount=Money.zero(),
        raised_at=rental.checked_out_at,
        raised_by_user_id=raised_by,
        reference=payment_reference(rental.reference, DEPOSIT_CHARGE_POSITION),
    )
