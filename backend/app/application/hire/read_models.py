"""What the hire module's reads hand back, as small frozen dataclasses.

`RentalDetail` is one rental as it is stored, with its items and its charges.
`CheckoutDetail` is what the counter needs to hand the equipment of one
reservation over, with the units the reservation holds. Neither is a table
row. What a particular caller is shown of either, and what they may do next,
is worked out from these in `app.application.hire.views`.

Money stays `Decimal` all the way to the HTTP boundary, which writes it as a
string with two decimals (BR-22).

A rental is named by its key or by its reference, the same way a reservation
is, so the counter can type the reference off the agreement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.enums import (
    AccountStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    IdDocType,
    RentalStatus,
    ReservationStatus,
)

# The width of the reference column. Nothing longer can be a reference.
REFERENCE_MAX_LENGTH: Final[int] = 16
# The statuses a rental with a unit out past its due date moves to OVERDUE from (BR-52).
OVERDUE_FROM: Final[frozenset[RentalStatus]] = frozenset(
    {RentalStatus.OPEN, RentalStatus.PARTIALLY_RETURNED}
)


@dataclass(frozen=True, slots=True)
class RentalKey:
    """How a caller names one rental, by its key or by its reference.

    Attributes:
        rental_id: The key, when the caller gave a UUID.
        reference: The reference, in upper case, when the caller gave anything else.

    """

    rental_id: UUID | None = None
    reference: str | None = None

    @classmethod
    def parse(cls, text: str) -> RentalKey:
        """Read what a caller typed as a key when it is one, and as a reference otherwise."""
        candidate = text.strip()
        try:
            return cls(rental_id=UUID(candidate))
        except ValueError:
            return cls(reference=candidate.upper()[:REFERENCE_MAX_LENGTH])

    @classmethod
    def of(cls, rental_id: UUID) -> RentalKey:
        """Return the key that names a rental by its id."""
        return cls(rental_id=rental_id)

    def __str__(self) -> str:
        """Return the key or the reference, whichever the caller gave."""
        return str(self.rental_id) if self.rental_id is not None else str(self.reference)


@dataclass(frozen=True, slots=True)
class RentalItemDetail:
    """One unit handed over on a rental, as it is stored.

    Attributes:
        id: The item key.
        asset_tag: The tag of the unit. None in what a customer is shown.
        model_name: The name of the model the unit realises.
        model_slug: Its slug.
        condition_out: The grade it went out in.
        condition_in: The grade it came back in.
        hour_meter_out: The meter reading as it went out.
        hour_meter_in: The meter reading as it came back.
        accessories_out: What went out with it.
        accessories_in: What came back with it.
        returned_at: When it came back. None while it is out.
        days_late: The whole days it came back late, worked out at return.
        late_fee_per_day: The late fee copied onto its reservation line (BR-20).
        flagged_for_damage: Whether the counter flagged it as it came back.
        damage_reported: Whether a damage report names it.
        replacement_value: The replacement value copied onto its reservation
            line, which caps a damage recovery (BR-39). None in what a
            customer is shown.

    """

    id: UUID
    asset_tag: str | None
    model_name: str
    model_slug: str
    condition_out: ConditionGrade
    condition_in: ConditionGrade | None
    hour_meter_out: int | None
    hour_meter_in: int | None
    accessories_out: str | None
    accessories_in: str | None
    returned_at: datetime | None
    days_late: int
    late_fee_per_day: Decimal
    flagged_for_damage: bool = False
    damage_reported: bool = False
    replacement_value: Decimal | None = None

    def is_out(self) -> bool:
        """Return True while the unit is still with the customer."""
        return self.returned_at is None


@dataclass(frozen=True, slots=True)
class ChargeDetail:
    """One money line on a rental, as it is stored."""

    id: UUID
    charge_type: ChargeType
    description: str
    amount_ex_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    amount_inc_vat: Decimal
    status: ChargeStatus
    raised_at: datetime
    rental_item_id: UUID | None


@dataclass(frozen=True, slots=True)
class RentalDetail:
    """One rental with its items and its charges, as it is stored.

    Attributes:
        id: The rental key.
        reference: The rental reference, for example TSH-H-26-000099.
        status: Where the hire stands.
        reservation_id: The reservation it fulfils.
        reservation_reference: That reservation's reference.
        branch_id: The branch the equipment went out from.
        branch_code: Its short code.
        branch_name: Its display name.
        customer_profile_id: The customer the hire belongs to.
        customer_name: The name staff see for that customer.
        customer_phone: The number the branch can reach them on.
        start_date: The first day of the hire.
        due_back_on: The day it is due back.
        checked_out_at: When it was handed over.
        returned_at: When the last unit came back.
        items: The units, in line order and then tag order.
        charges: The money lines, in the order they were raised.
        deposit_held: The deposit taken at checkout.
        deposit_withheld: How much of it was kept.
        deposit_refunded: How much of it was given back.
        balance_due: What the customer still owes.
        settled_at: When the account was settled.
        agreement_signed: Whether the customer signed the hire agreement.

    """

    id: UUID
    reference: str
    status: RentalStatus
    reservation_id: UUID
    reservation_reference: str
    branch_id: UUID
    branch_code: str
    branch_name: str
    customer_profile_id: UUID
    customer_name: str
    customer_phone: str
    start_date: date
    due_back_on: date
    checked_out_at: datetime
    returned_at: datetime | None
    items: tuple[RentalItemDetail, ...]
    charges: tuple[ChargeDetail, ...]
    deposit_held: Decimal
    deposit_withheld: Decimal
    deposit_refunded: Decimal
    balance_due: Decimal
    settled_at: datetime | None
    agreement_signed: bool

    def is_stored_short_of_overdue(self, today: date) -> bool:
        """Return True when a unit is out past the due date and the stored status says otherwise.

        Nothing wakes up when a due date passes, so the status stored for a
        hire can lag a day behind what it reads as (BR-52). The read of one
        rental asks this before it answers, and moves the rental on first.
        """
        return (
            self.status in OVERDUE_FROM
            and today > self.due_back_on
            and any(item.is_out() for item in self.items)
        )


@dataclass(frozen=True, slots=True)
class CheckoutCustomer:
    """The customer a counter assistant checks the equipment out to."""

    id: UUID
    display_name: str
    phone: str
    id_document_type: IdDocType
    id_document_last4: str
    account_status: AccountStatus


@dataclass(frozen=True, slots=True)
class CheckoutUnit:
    """One unit the reservation holds, as the counter hands it over.

    Attributes:
        allocation_id: The allocation the unit is held under.
        asset_tag: The tag painted on the unit.
        model_name: The name of its model.
        model_slug: Its slug.
        condition_grade: The grade recorded the last time it went out or came back.
        hour_meter: Its last meter reading, for a unit with a meter.
        deposit_per_unit: The deposit copied onto its reservation line.

    """

    allocation_id: UUID
    asset_tag: str
    model_name: str
    model_slug: str
    condition_grade: ConditionGrade
    hour_meter: int | None
    deposit_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class CheckoutDetail:
    """A reservation as the counter sees it at the moment of handing it over.

    Attributes:
        reservation_id: The reservation key.
        reference: Its reference.
        status: Where it stands.
        branch_id: The collection branch.
        branch_code: Its short code.
        branch_name: Its display name.
        customer: The customer it belongs to.
        start_date: The first day of the hire.
        end_date: The day the equipment comes back.
        units: The units it holds right now, in line order and then tag order.
        hire_total_inc_vat: The hire as stored on the reservation, with VAT.
        rental_id: The rental opened from it, once it has been collected.

    """

    reservation_id: UUID
    reference: str
    status: ReservationStatus
    branch_id: UUID
    branch_code: str
    branch_name: str
    customer: CheckoutCustomer
    start_date: date
    end_date: date
    units: tuple[CheckoutUnit, ...]
    hire_total_inc_vat: Decimal
    rental_id: UUID | None

    @property
    def hire_days(self) -> int:
        """Return the number of chargeable days in the hire."""
        return (self.end_date - self.start_date).days
