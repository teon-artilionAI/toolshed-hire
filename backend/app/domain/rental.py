"""The rental, which is the hire once the equipment has left the counter.

A reservation is the promise and a rental is the fulfilment. A rental is
opened at checkout from a confirmed reservation, and from then on it is what
the counter works with. It records who handed the equipment over and when,
what deposit was taken, when each unit came back and how the account was
settled.

A rental owns its items and its charges. An item is one physical unit handed
over, made from exactly one allocation of the reservation (BR-28), and it is
the thing that comes back, so a partial return is a return of some items and
not others. A charge is one money line, and every amount on a hire is one,
the deposit included (`app.domain.charge`).

An item carries the figures its return is charged by, copied onto its booking
line when the booking was made (BR-20). They are `UnitTerms`, and they are
read from the line and never stored on the item a second time.

An item is closed when it came back or when it was recorded as lost. A lost
unit is closed with the time it was recorded and with no condition, because
nobody inspected it, and a unit that came back always has one. The rental's
status follows its items and its due date, and `status_on` is the one place
that decides it (BR-29, BR-52).

What a rental reads as waiting on before its deposit is settled, and whether
a returned unit waits for its damage to be assessed, are `SettlementWait` and
`DamageAssessment`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Final
from uuid import UUID, uuid4

from app.domain.charge import Charge
from app.domain.enums import ConditionGrade, RentalStatus

RENTAL_REFERENCE_PREFIX: Final[str] = "TSH-H"
REFERENCE_YEAR_MODULUS: Final[int] = 100
NOTHING_YET: Final[Decimal] = Decimal("0.00")
NO_DAYS_LATE: Final[int] = 0


def format_rental_reference(year: int, sequence_value: int) -> str:
    """Return a rental reference, for example TSH-H-26-000099.

    Args:
        year: The calendar year the hire starts in. Only its last two digits
            are used, the same way a reservation reference uses them.
        sequence_value: The next value of the rental reference sequence.

    """
    return f"{RENTAL_REFERENCE_PREFIX}-{year % REFERENCE_YEAR_MODULUS:02d}-{sequence_value:06d}"


class DamageAssessment(str, Enum):
    """Whether a unit that came back still waits for its damage to be assessed."""

    NOT_NEEDED = "NOT_NEEDED"
    REQUIRED = "REQUIRED"
    DONE = "DONE"


class SettlementWait(str, Enum):
    """What a rental is waiting on before its deposit can be settled."""

    ITEMS_OUT = "ITEMS_OUT"
    DAMAGE_ASSESSMENT = "DAMAGE_ASSESSMENT"
    BALANCE_PAYMENT = "BALANCE_PAYMENT"


@dataclass(frozen=True, slots=True)
class UnitTerms:
    """The figures copied onto the booking line of a unit that its return is charged by (BR-20).

    Attributes:
        late_fee_per_day: The late fee for each day it is late, including VAT.
        deposit: The deposit held for the unit.
        replacement_value: The most a customer is charged for the unit (BR-39).

    """

    late_fee_per_day: Decimal
    deposit: Decimal
    replacement_value: Decimal


@dataclass(slots=True)
class RentalItem:
    """One physical unit handed over on a rental.

    Attributes:
        rental_id: The rental the item is on.
        asset_allocation_id: The allocation it was made from. Each allocation
            becomes one item at most (BR-28).
        asset_id: The unit. The database refuses one that disagrees with the
            allocation, through a composite foreign key.
        condition_out: The grade recorded at the counter as it went out.
        checked_out_at: When it was handed over, from the clock.
        terms: The figures its booking line carries for it.
        hour_meter_out: The meter reading as it went out, for a unit with a meter.
        accessories_out: What went out with it, for example a chuck key.
        condition_in: The grade recorded as it came back. None while it is
            out, and None for a unit recorded as lost.
        hour_meter_in: The meter reading as it came back.
        accessories_in: What came back with it.
        returned_at: When it came back or was recorded as lost. None while it is out.
        days_late: The whole days it came back late, worked out at return.
        notes: Anything the counter wrote about it.
        damage_reported: True once a damage report names the unit. It is read
            with the item and never stored on it, because the report is.
        id: The item key, generated here so it is known before the insert.

    """

    rental_id: UUID
    asset_allocation_id: UUID
    asset_id: UUID
    condition_out: ConditionGrade
    checked_out_at: datetime
    terms: UnitTerms
    hour_meter_out: int | None = None
    accessories_out: str | None = None
    condition_in: ConditionGrade | None = None
    hour_meter_in: int | None = None
    accessories_in: str | None = None
    returned_at: datetime | None = None
    days_late: int = NO_DAYS_LATE
    notes: str | None = None
    damage_reported: bool = False
    id: UUID = field(default_factory=uuid4)

    def is_out(self) -> bool:
        """Return True while the unit is still with the customer."""
        return self.returned_at is None

    def is_lost(self) -> bool:
        """Return True when the unit was recorded as lost rather than brought back (BR-31)."""
        return self.returned_at is not None and self.condition_in is None


@dataclass(slots=True)
class Rental:
    """The hire of the units of one reservation, from checkout until it is settled.

    Attributes:
        reference: The reference the counter quotes, for example TSH-H-26-000099.
        reservation_id: The reservation it fulfils. One rental per reservation.
        branch_id: The branch the equipment went out from.
        checked_out_at: When it was handed over, from the clock.
        checked_out_by_user_id: The member of staff who handed it over.
        due_back_on: The day it is due back, copied from the end of the
            reservation, which is not a day of the hire.
        deposit_held: The deposit taken at checkout (BR-27).
        agreement_signed: Whether the customer signed the hire agreement.
        status: Where the hire stands.
        items: The units handed over.
        charges: Every money line on the hire, the deposit included, in the
            order they were raised.
        returned_at: When the last unit came back.
        returned_to_user_id: The member of staff who took it back.
        deposit_refunded: How much of the deposit was given back.
        deposit_withheld: How much of the deposit was kept.
        balance_due: What the customer still owes once the deposit is offset.
        settled_at: When the account of the hire was settled.
        id: The rental key, generated here so it is known before the insert.

    """

    reference: str
    reservation_id: UUID
    branch_id: UUID
    checked_out_at: datetime
    checked_out_by_user_id: UUID
    due_back_on: date
    deposit_held: Decimal
    agreement_signed: bool
    status: RentalStatus = RentalStatus.OPEN
    items: list[RentalItem] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    returned_at: datetime | None = None
    returned_to_user_id: UUID | None = None
    deposit_refunded: Decimal = NOTHING_YET
    deposit_withheld: Decimal = NOTHING_YET
    balance_due: Decimal = NOTHING_YET
    settled_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    def items_out(self) -> list[RentalItem]:
        """Return the units that are still with the customer."""
        return [item for item in self.items if item.is_out()]

    def is_all_back(self) -> bool:
        """Return True when every unit came back or was recorded as lost."""
        return bool(self.items) and not self.items_out()

    def item_with_id(self, item_id: UUID) -> RentalItem | None:
        """Return the item with this key, or None when it is not on this rental."""
        return next((item for item in self.items if item.id == item_id), None)

    def status_on(self, today: date) -> RentalStatus:
        """Return the status the rental reads as on a day, from its items and its due date.

        A rental with every unit back is RETURNED, and one with a unit still
        out after the day it was due back is OVERDUE (BR-52). Otherwise it is
        PARTIALLY_RETURNED once a unit is back and OPEN before then (BR-29). A
        settled rental stays SETTLED, because nothing about it changes again.

        Args:
            today: The current business day, from the clock.

        """
        if self.status is RentalStatus.SETTLED:
            return RentalStatus.SETTLED
        if self.is_all_back():
            return RentalStatus.RETURNED
        if today > self.due_back_on:
            return RentalStatus.OVERDUE
        if len(self.items_out()) < len(self.items):
            return RentalStatus.PARTIALLY_RETURNED
        return RentalStatus.OPEN

    def charge_position(self, charge: Charge) -> int:
        """Return where a charge stands among the charges of the rental, counted from one.

        Raises:
            ValueError: If the charge is not on this rental, which means the
                calling code is settling a charge it did not read from it.

        """
        for position, candidate in enumerate(self.charges, start=1):
            if candidate.id == charge.id:
                return position
        raise ValueError(
            f"Attempted to number charge {charge.id} on rental {self.reference}, which does "
            "not carry it."
        )
