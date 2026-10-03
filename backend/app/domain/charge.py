"""The charge, which is one money line on a rental (BR-22, BR-23, BR-24).

Every amount that changes hands on a hire is a charge, the deposit movements
included, so the account of a hire is a single list a customer can read and a
settlement is a single sum. A charge is written once. A settled one is never
edited, and a correction is a new charge that points back at it (BR-24).

The amounts arrive as `Money` and are rounded here, half up to the cent, which
is the point a charge is written (BR-22). The amount including VAT is the two
rounded amounts added together, so the three always agree to the cent, which
the database checks again with `ck_charge_inclusive_amount`. A deposit
movement carries no VAT, because a deposit that is held and given back is not
a supply (BR-23).

Settlement is simulated (BR-33). A charge settled at the counter carries a
reference of the form `SIM-TSH-H-26-000099-01`, which names the rental and the
place of the charge on it, and no payment gateway is ever called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.domain.enums import ChargeStatus, ChargeType
from app.domain.money import Money

DEPOSIT_CHARGE_TYPES: Final[frozenset[ChargeType]] = frozenset(
    {ChargeType.DEPOSIT_HOLD, ChargeType.DEPOSIT_RELEASE, ChargeType.DEPOSIT_FORFEIT}
)
NO_VAT_PERCENT: Final[Decimal] = Decimal("0.00")
# The width of the column a description is stored in.
DESCRIPTION_MAX_LENGTH: Final[int] = 200
PAYMENT_REFERENCE_PREFIX: Final[str] = "SIM"


def payment_reference(rental_reference: str, position: int) -> str:
    """Return the simulated settlement reference of a charge, for example SIM-TSH-H-26-000099-01.

    Args:
        rental_reference: The reference of the rental the charge is on.
        position: Where the charge stands among the charges of that rental,
            counted from one.

    """
    return f"{PAYMENT_REFERENCE_PREFIX}-{rental_reference}-{position:02d}"


@dataclass(frozen=True, slots=True)
class Charge:
    """One money line on a rental, positive or negative.

    Attributes:
        rental_id: The rental the charge is on.
        charge_type: What the charge is for.
        description: What the customer reads beside the amount.
        amount_ex_vat: The amount before VAT, signed. A release is negative.
        vat_rate: The VAT rate it was charged at, zero for a deposit movement.
        vat_amount: The VAT on the amount.
        amount_inc_vat: The amount and its VAT together.
        status: Where the charge stands.
        raised_at: When it was raised, from the clock.
        raised_by_user_id: The account that raised it.
        rental_item_id: The unit the charge belongs to, or None for the hire
            as a whole.
        settled_at: When it was settled, if it has been.
        payment_reference: The simulated settlement reference, if settled.
        id: The charge key, generated here so it is known before the insert.

    """

    rental_id: UUID
    charge_type: ChargeType
    description: str
    amount_ex_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    amount_inc_vat: Decimal
    status: ChargeStatus
    raised_at: datetime
    raised_by_user_id: UUID
    rental_item_id: UUID | None = None
    settled_at: datetime | None = None
    payment_reference: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Refuse a charge whose figures disagree or whose description cannot be stored.

        Raises:
            ValueError: If the amount including VAT is not the other two added,
                if a deposit movement carries VAT, or if the description is
                blank or wider than its column. Each means the calling code
                built the charge wrongly.

        """
        if self.amount_inc_vat != self.amount_ex_vat + self.vat_amount:
            raise ValueError(
                f"Attempted to build a {self.charge_type.value} charge of {self.amount_ex_vat} "
                f"plus {self.vat_amount} VAT that claims to total {self.amount_inc_vat}."
            )
        if self.charge_type in DEPOSIT_CHARGE_TYPES and (self.vat_rate or self.vat_amount):
            raise ValueError(
                f"Attempted to build a {self.charge_type.value} charge carrying VAT at "
                f"{self.vat_rate} percent. A deposit movement carries none (BR-23)."
            )
        if not self.description.strip() or len(self.description) > DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"Attempted to build a {self.charge_type.value} charge with a description of "
                f"{len(self.description)} characters. It must be between one and "
                f"{DESCRIPTION_MAX_LENGTH}."
            )

    @classmethod
    def settled_at_the_counter(
        cls,
        *,
        rental_id: UUID,
        charge_type: ChargeType,
        description: str,
        amount_ex_vat: Money,
        vat_rate: Decimal,
        vat_amount: Money,
        raised_at: datetime,
        raised_by_user_id: UUID,
        reference: str,
        rental_item_id: UUID | None = None,
    ) -> Charge:
        """Build a charge that was paid the moment it was raised, rounding it as it is written.

        Args:
            rental_id: The rental the charge is on.
            charge_type: What the charge is for.
            description: What the customer reads beside the amount.
            amount_ex_vat: The amount before VAT, exact.
            vat_rate: The rate the VAT was worked out at.
            vat_amount: The VAT, exact.
            raised_at: When it was raised and paid, from the clock.
            raised_by_user_id: The account that took the payment.
            reference: The simulated settlement reference.
            rental_item_id: The unit it belongs to, or None for the whole hire.

        """
        before_vat = amount_ex_vat.rounded()
        vat = vat_amount.rounded()
        return cls(
            rental_id=rental_id,
            charge_type=charge_type,
            description=description,
            amount_ex_vat=before_vat.amount,
            vat_rate=vat_rate,
            vat_amount=vat.amount,
            amount_inc_vat=before_vat.add(vat).amount,
            status=ChargeStatus.SETTLED,
            raised_at=raised_at,
            raised_by_user_id=raised_by_user_id,
            rental_item_id=rental_item_id,
            settled_at=raised_at,
            payment_reference=reference,
        )
