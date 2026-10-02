"""The booking entities, which are the reservation and its lines.

A reservation is the aggregate root. It owns its lines, and each line owns the
allocations that hold specific tagged units for it. The allocation itself
belongs to the availability module and lives in `app.domain.availability`.
Nothing here knows how any of it is stored. The repositories in the
infrastructure layer map these dataclasses to the table classes and back.

Two things the design document describes are deliberately not here yet. The
reservation states, which decide the moves a booking may make, arrive with the
booking lifecycle. The pricing policy, which fills the money totals, is built
in `app.domain.policies` (BR-21), and a reservation does not call it yet. Until
it does, a reservation is created held and its totals are written as zero, so
nothing reads as a price that was never calculated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.domain.availability import AssetAllocation
from app.domain.catalogue import ProductModel
from app.domain.enums import ReservationStatus
from app.domain.period import BookingPeriod

REFERENCE_PREFIX: Final[str] = "TSH-R"
REFERENCE_YEAR_MODULUS: Final[int] = 100
FIRST_LINE_POSITION: Final[int] = 1
# What every money total carries until a reservation is priced by the pricing policy.
NOT_YET_PRICED: Final[Decimal] = Decimal("0.00")


def format_reference(year: int, sequence_value: int) -> str:
    """Return a reservation reference, for example TSH-R-26-000124.

    Args:
        year: The calendar year the hire starts in. Only its last two digits
            are used.
        sequence_value: The next value of the reference sequence.

    """
    return f"{REFERENCE_PREFIX}-{year % REFERENCE_YEAR_MODULUS:02d}-{sequence_value:06d}"


@dataclass(slots=True)
class ReservationLine:
    """One product model and a quantity within a reservation, with price snapshots.

    The snapshots are copied from the product model when the line is created,
    so a later price change never rewrites an existing booking (BR-20).

    Attributes:
        id: The line key, generated here so it is known before the insert.
        reservation_id: The reservation the line belongs to.
        product_model_id: The catalogue entry being hired.
        quantity: How many units of it.
        line_position: The position of the line within the reservation.
        daily_rate_snapshot: The daily rate at the time of booking.
        weekly_rate_snapshot: The weekly rate at the time of booking.
        deposit_snapshot: The deposit for one unit at the time of booking.
        late_fee_per_day_snapshot: The late fee at the time of booking.
        replacement_value_snapshot: The replacement value at the time of booking.
        line_subtotal_ex_vat: The output of the pricing policy (BR-21).
        allocations: The units held for this line.

    """

    reservation_id: UUID
    product_model_id: UUID
    quantity: int
    line_position: int
    daily_rate_snapshot: Decimal
    weekly_rate_snapshot: Decimal
    deposit_snapshot: Decimal
    late_fee_per_day_snapshot: Decimal
    replacement_value_snapshot: Decimal
    line_subtotal_ex_vat: Decimal = NOT_YET_PRICED
    allocations: list[AssetAllocation] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)

    def active_allocations(self) -> list[AssetAllocation]:
        """Return the allocations that still occupy a unit."""
        return [allocation for allocation in self.allocations if allocation.is_active()]

    def is_satisfied(self) -> bool:
        """Return True when the line holds exactly as many units as it asks for (BR-08)."""
        return len(self.active_allocations()) == self.quantity


@dataclass(slots=True)
class Reservation:
    """A customer booking of one or more product models at one branch.

    The reservation belongs to a customer profile and not to an account, so a
    walk-in with no login can own a booking history. `created_by_user_id` is
    kept apart from the customer, so a counter booking names both the customer
    and the assistant who raised it.

    Attributes:
        id: The reservation key, generated here so it is known before the insert.
        reference: The reference the customer quotes, unique across bookings.
        customer_profile_id: The customer the booking is for.
        branch_id: The collection branch.
        period: The half open hire period.
        status: Where the booking is in its lifecycle.
        created_by_user_id: The account that raised the booking.
        lines: The lines of the booking, in position order.
        subtotal_ex_vat: The sum of the line subtotals.
        vat_amount: The VAT on the subtotal.
        deposit_total: The deposit across every unit.
        estimated_total_inc_vat: What the customer is told to expect to pay.
        hold_expires_at: When a held booking lapses (BR-12). Not set yet.

    """

    reference: str
    customer_profile_id: UUID
    branch_id: UUID
    period: BookingPeriod
    status: ReservationStatus
    created_by_user_id: UUID
    lines: list[ReservationLine] = field(default_factory=list)
    subtotal_ex_vat: Decimal = NOT_YET_PRICED
    vat_amount: Decimal = NOT_YET_PRICED
    deposit_total: Decimal = NOT_YET_PRICED
    estimated_total_inc_vat: Decimal = NOT_YET_PRICED
    hold_expires_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def held(
        cls,
        *,
        reference: str,
        customer_profile_id: UUID,
        branch_id: UUID,
        period: BookingPeriod,
        created_by_user_id: UUID,
    ) -> Reservation:
        """Build a new reservation in the HELD status with no lines yet.

        Args:
            reference: The reference drawn from the sequence.
            customer_profile_id: The customer the booking is for.
            branch_id: The collection branch.
            period: The half open hire period.
            created_by_user_id: The account raising the booking.

        """
        return cls(
            reference=reference,
            customer_profile_id=customer_profile_id,
            branch_id=branch_id,
            period=period,
            status=ReservationStatus.HELD,
            created_by_user_id=created_by_user_id,
        )

    def add_line(self, product_model: ProductModel, quantity: int) -> ReservationLine:
        """Add a line for a product model, snapshotting its prices (BR-20).

        Args:
            product_model: The catalogue entry being hired.
            quantity: How many units of it.

        Returns:
            The new line, already appended at the next position.

        Raises:
            ValueError: If the reservation already has a line for the product
                model. One model appears once in a booking and its quantity
                says how many.

        """
        if any(line.product_model_id == product_model.id for line in self.lines):
            raise ValueError(
                f"Attempted to add a second line for product model {product_model.sku} to "
                f"reservation {self.reference}. A product model appears once in a booking."
            )
        line = ReservationLine(
            reservation_id=self.id,
            product_model_id=product_model.id,
            quantity=quantity,
            line_position=len(self.lines) + FIRST_LINE_POSITION,
            daily_rate_snapshot=product_model.daily_rate,
            weekly_rate_snapshot=product_model.weekly_rate,
            deposit_snapshot=product_model.deposit_amount,
            late_fee_per_day_snapshot=product_model.late_fee_per_day,
            replacement_value_snapshot=product_model.replacement_value,
        )
        self.lines.append(line)
        return line

    def is_fully_allocated(self) -> bool:
        """Return True when every line holds the units it asks for (BR-08).

        A reservation with no lines is not fully allocated, because there is
        nothing to collect.
        """
        return bool(self.lines) and all(line.is_satisfied() for line in self.lines)
