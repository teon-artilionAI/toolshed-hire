"""Correcting a charge after it was raised, which is BR-24 and BR-25.

An administrator corrects the money of a hire in one of three ways, and none
of them edits a settled row.

A waiver lets a charge that is still owed go. Only a PENDING charge can be
waived, and it is refused through the same guard that settles one,
`Charge.ensure_may_change`, so the guard stays the only way a charge's state
can move. The waived charge keeps the reason.

A reversal undoes a SETTLED charge with a new charge of the same type, every
amount negated, that points back at the original through `reverses_charge_id`
and carries the reason. The original row is never touched, so it stays
SETTLED and the status REVERSED is never written. A charge is reversed once,
a reversal is not itself reversed, and a deposit movement is not reversed,
because the deposit is worked out again after every correction and reversing a
movement of it would count it twice.

An adjustment is a new ADJUSTMENT charge for an amount that includes VAT,
positive when the customer owes more and negative when they are owed, split
for VAT by `split_vat_inclusive` the way a late fee is. A settled hire is never
edited (BR-53), so once a hire is SETTLED only a correction that gives money
back, a reversal or a negative adjustment, can be made to it, and a positive
adjustment is refused.

A reversal and an adjustment are raised PENDING. A positive one is owed like a
late fee, and a negative one is a credit the customer is owed. Either way the
deposit, the balance and the status of the hire are then worked out again by
the settlement, in `app.domain.resettlement`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final
from uuid import UUID

from app.domain.charge import DEPOSIT_CHARGE_TYPES, DESCRIPTION_MAX_LENGTH, Charge
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.override_reason import OVERRIDE_REASON_RULE, written_reason
from app.domain.rental import Rental
from app.domain.vat import split_vat_inclusive

REVERSAL_RULE: Final[str] = "BR-24"
SETTLED_RENTAL_RULE: Final[str] = "BR-53"
AMOUNT_FIELD: Final[str] = "amount_inc_vat"
REVERSAL_PREFIX: Final[str] = "Reversal of "
DEBIT_DESCRIPTION: Final[str] = "Adjustment to the hire, including VAT"
CREDIT_DESCRIPTION: Final[str] = "Credit to the hire, including VAT"

ZERO_ADJUSTMENT_MESSAGE: Final[str] = "An adjustment has to be an amount other than nothing."
NOT_SETTLED_MESSAGE: Final[str] = (
    "Only a settled charge can be reversed. A charge still owed is waived instead."
)
DEPOSIT_MOVEMENT_MESSAGE: Final[str] = (
    "A deposit movement is not reversed. The deposit is worked out again whenever a charge "
    "is corrected."
)
REVERSAL_OF_A_REVERSAL_MESSAGE: Final[str] = (
    "This charge is itself a reversal, so it cannot be reversed. Add an adjustment instead."
)
ALREADY_REVERSED_MESSAGE: Final[str] = "This charge has already been reversed."
SETTLED_HIRE_MESSAGE: Final[str] = (
    "This hire is settled, so only a correction that gives money back can be made to it now."
)


def waive(rental: Rental, charge: Charge, *, reason: str) -> Charge:
    """Waive a charge still owed on a rental, with the reason, and return it waived (BR-25).

    Args:
        rental: The rental, locked by the caller, that carries the charge.
        charge: The charge to waive.
        reason: Why it is waived.

    Raises:
        ValidationFailure: If the reason is too short or too long.
        StateTransitionError: If the charge is settled, waived or reversed.
            A settled charge is reversed, never waived (BR-24).

    """
    written = written_reason(reason)
    charge.ensure_may_change(ChargeStatus.WAIVED)
    waived = replace(charge, status=ChargeStatus.WAIVED, reason=written)
    rental.charges = [waived if kept.id == charge.id else kept for kept in rental.charges]
    return waived


def reverse(
    rental: Rental, charge: Charge, *, reason: str, raised_by: UUID, now: datetime
) -> Charge:
    """Raise the reversal of a settled charge on a rental, and return it (BR-24).

    Args:
        rental: The rental, locked by the caller, that carries the charge.
        charge: The settled charge to reverse.
        reason: Why it is reversed.
        raised_by: The administrator reversing it.
        now: The current instant, from the clock.

    Raises:
        ValidationFailure: If the reason is too short or too long.
        StateTransitionError: If the charge is not settled, is a deposit
            movement, is itself a reversal or has been reversed already.

    """
    written = written_reason(reason)
    _ensure_reversible(rental, charge)
    reversal = Charge(
        rental_id=rental.id,
        charge_type=charge.charge_type,
        description=_reversal_description(charge.description),
        amount_ex_vat=-charge.amount_ex_vat,
        vat_rate=charge.vat_rate,
        vat_amount=-charge.vat_amount,
        amount_inc_vat=-charge.amount_inc_vat,
        status=ChargeStatus.PENDING,
        raised_at=now,
        raised_by_user_id=raised_by,
        rental_item_id=charge.rental_item_id,
        damage_report_id=charge.damage_report_id,
        reverses_charge_id=charge.id,
        reason=written,
    )
    rental.charges.append(reversal)
    return reversal


def adjust(
    rental: Rental, *, amount_inc_vat: Money, reason: str, raised_by: UUID, now: datetime
) -> Charge:
    """Raise an adjustment of a rental for an amount that includes VAT, and return it.

    Args:
        rental: The rental, locked by the caller.
        amount_inc_vat: What the customer owes more, or a negative amount
            they are owed, VAT included.
        reason: Why the hire is adjusted.
        raised_by: The administrator adjusting it.
        now: The current instant, from the clock.

    Raises:
        ValidationFailure: If the reason is too short or too long, or the
            amount is nothing. The detail names the field.
        StateTransitionError: If the amount is owed and the hire is already
            SETTLED, which is never edited (BR-53).

    """
    written = written_reason(reason)
    if amount_inc_vat.rounded() == Money.zero().rounded():
        raise ValidationFailure(
            ZERO_ADJUSTMENT_MESSAGE, {REFUSED_FIELD: AMOUNT_FIELD}, rule=OVERRIDE_REASON_RULE
        )
    if rental.status is RentalStatus.SETTLED and amount_inc_vat > Money.zero():
        raise StateTransitionError(
            SETTLED_HIRE_MESSAGE,
            from_status=rental.status.value,
            to_status=rental.status.value,
            rule=SETTLED_RENTAL_RULE,
        )
    split = split_vat_inclusive(amount_inc_vat)
    owed = Charge.owed(
        rental_id=rental.id,
        charge_type=ChargeType.ADJUSTMENT,
        description=CREDIT_DESCRIPTION if amount_inc_vat.is_negative() else DEBIT_DESCRIPTION,
        amount_ex_vat=split.amount_ex_vat,
        vat_rate=split.vat_rate,
        vat_amount=split.vat_amount,
        raised_at=now,
        raised_by_user_id=raised_by,
    )
    adjustment = replace(owed, reason=written)
    rental.charges.append(adjustment)
    return adjustment


def charge_on(rental: Rental, charge_id: UUID) -> Charge:
    """Return the charge of a rental with this key.

    Raises:
        LookupError: If the rental does not carry it, which means the caller
            locked the wrong rental for the charge.

    """
    for charge in rental.charges:
        if charge.id == charge_id:
            return charge
    raise LookupError(
        f"Attempted to correct charge {charge_id} on rental {rental.reference}, which does "
        "not carry it."
    )


def _ensure_reversible(rental: Rental, charge: Charge) -> None:
    """Refuse a reversal of anything but a settled charge that nothing has reversed."""
    if charge.status is not ChargeStatus.SETTLED:
        raise _refused(charge, NOT_SETTLED_MESSAGE)
    if charge.charge_type in DEPOSIT_CHARGE_TYPES:
        raise _refused(charge, DEPOSIT_MOVEMENT_MESSAGE)
    if charge.reverses_charge_id is not None:
        raise _refused(charge, REVERSAL_OF_A_REVERSAL_MESSAGE)
    if any(other.reverses_charge_id == charge.id for other in rental.charges):
        raise _refused(charge, ALREADY_REVERSED_MESSAGE)


def _refused(charge: Charge, message: str) -> StateTransitionError:
    """Return the refusal of a reversal of a charge."""
    return StateTransitionError(
        message,
        from_status=charge.status.value,
        to_status=ChargeStatus.REVERSED.value,
        rule=REVERSAL_RULE,
    )


def _reversal_description(original: str) -> str:
    """Return what the customer reads beside a reversal, cut to the width of its column."""
    return f"{REVERSAL_PREFIX}{original}"[:DESCRIPTION_MAX_LENGTH]
