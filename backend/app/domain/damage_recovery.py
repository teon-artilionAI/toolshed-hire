"""What a damage report recovers from the customer, which is BR-39 and BR-40.

Whether the customer is charged is decided on every report (BR-40). When the
customer is charged and the report names the rental item of the hire the unit
came back from, the counter states the amount to recover. It is a VAT
inclusive amount, like a late fee, and a DAMAGE_RECOVERY charge is raised on
the rental for it. When the customer is not charged, no amount may be given. A
report outside a hire names no rental item, so there is nobody to charge and
it takes no amount either.

The amount is capped at the replacement value copied onto the booking line of
the unit (BR-20, BR-39). The cap counts what was already recovered for that
unit on that hire, by an earlier report, or by the deposit kept and the
recovery raised when the unit was recorded as lost, so the customer is never
charged more than the unit was worth however many reports name it.

A recovery is owed and is paid from the deposit when the hire is settled, so
it can only be raised while the deposit is still held. Once the deposit has
been settled a report that charges the customer is refused with 409, and a
later correction is a charge of its own (BR-24).
"""

from __future__ import annotations

from typing import Final

from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import ChargeStatus, ChargeType
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.rental import Rental, RentalItem
from app.domain.settlement import deposit_was_settled

RECOVERY_RULE: Final[str] = "BR-39"
CHARGEABLE_RULE: Final[str] = "BR-40"
RECOVERY_FIELD: Final[str] = "recovery_amount"
# The charges that recover the value of a unit from the customer.
RECOVERED_BY: Final[frozenset[ChargeType]] = frozenset(
    {ChargeType.DAMAGE_RECOVERY, ChargeType.DEPOSIT_FORFEIT}
)
# The standings of a charge that the customer pays or has paid.
COUNTED_STANDINGS: Final[frozenset[ChargeStatus]] = frozenset(
    {ChargeStatus.PENDING, ChargeStatus.SETTLED}
)

AMOUNT_REQUIRED_MESSAGE: Final[str] = (
    "Enter the amount to recover from the customer, including VAT. The customer is charged "
    "for this damage."
)
AMOUNT_NOT_CHARGED_MESSAGE: Final[str] = (
    "Leave the amount to recover out. The customer is not charged for this damage."
)
AMOUNT_OUTSIDE_A_HIRE_MESSAGE: Final[str] = (
    "Leave the amount to recover out. Damage found outside a hire is not charged to a "
    "customer."
)
AMOUNT_NOT_POSITIVE_MESSAGE: Final[str] = "Enter an amount to recover above R0.00."
DEPOSIT_ALREADY_SETTLED_MESSAGE: Final[str] = (
    "The deposit of this hire has already been settled, so the customer can no longer be "
    "charged for damage on it. File the report as not chargeable."
)


def ensure_recovery_decided(
    *, chargeable: bool, names_rental_item: bool, recovery_amount: Money | None
) -> None:
    """Refuse an amount to recover that does not follow from the chargeable decision (BR-40).

    Args:
        chargeable: Whether the customer is charged for the damage.
        names_rental_item: Whether the report names the hire the unit came back from.
        recovery_amount: The amount to recover the counter gave, or None.

    Raises:
        ValidationFailure: Naming `recovery_amount` when an amount is missing
            for a chargeable report on a hire, is given when the customer is
            not charged or there is no hire, or is not above nothing.

    """
    if recovery_amount is None:
        if chargeable and names_rental_item:
            raise _refused(AMOUNT_REQUIRED_MESSAGE, CHARGEABLE_RULE)
        return
    if not chargeable:
        raise _refused(AMOUNT_NOT_CHARGED_MESSAGE, CHARGEABLE_RULE)
    if not names_rental_item:
        raise _refused(AMOUNT_OUTSIDE_A_HIRE_MESSAGE, CHARGEABLE_RULE)
    if not recovery_amount.rounded() > Money.zero():
        raise _refused(AMOUNT_NOT_POSITIVE_MESSAGE, RECOVERY_RULE)


def already_recovered(rental: Rental, item: RentalItem) -> Money:
    """Return what the customer was already charged towards the value of one unit of a hire."""
    total = Money.zero()
    for charge in rental.charges:
        if (
            charge.rental_item_id == item.id
            and charge.charge_type in RECOVERED_BY
            and charge.status in COUNTED_STANDINGS
        ):
            total = total.add(charge.total())
    return total.rounded()


def recovery_cap(*, replacement_value: Money, already: Money) -> Money:
    """Return the most a new report may still recover for a unit, never below nothing (BR-39).

    Args:
        replacement_value: The replacement value copied onto the unit's booking line.
        already: What was already recovered for the unit on the same hire.

    """
    left = replacement_value.subtract(already).rounded()
    return left if left > Money.zero() else Money.zero().rounded()


def ensure_recovery_within_cap(
    amount: Money, *, replacement_value: Money, already: Money
) -> None:
    """Refuse an amount to recover above what the unit was worth (BR-39).

    Args:
        amount: The amount to recover, including VAT.
        replacement_value: The replacement value copied onto the unit's booking line.
        already: What was already recovered for the unit on the same hire.

    Raises:
        ValidationFailure: Naming `recovery_amount`, with the most that may be
            recovered in the sentence.

    """
    cap = recovery_cap(replacement_value=replacement_value, already=already)
    if amount.rounded() <= cap:
        return
    value = replacement_value.rounded()
    message = f"The amount to recover cannot be more than R{cap.amount}."
    if cap < value:
        charged = already.rounded().amount
        message += f" R{charged} of the replacement value of R{value.amount} is already charged."
    else:
        message += " That is the replacement value copied onto the booking."
    raise _refused(message, RECOVERY_RULE)


def ensure_deposit_still_held(rental: Rental) -> None:
    """Refuse a recovery on a hire whose deposit was already settled.

    Raises:
        StateTransitionError: If the deposit of the rental was settled.

    """
    if not deposit_was_settled(rental):
        return
    raise StateTransitionError(
        DEPOSIT_ALREADY_SETTLED_MESSAGE,
        from_status=rental.status.value,
        to_status=rental.status.value,
        rule=RECOVERY_RULE,
    )


def _refused(message: str, rule: str) -> ValidationFailure:
    """Return the refusal of the amount to recover."""
    return ValidationFailure(message, {REFUSED_FIELD: RECOVERY_FIELD}, rule=rule)
