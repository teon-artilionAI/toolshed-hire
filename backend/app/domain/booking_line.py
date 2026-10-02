"""The reservation line, which is one product model and a quantity.

A line carries the figures of its product model as they stood when the line
was added (BR-20). The pricing policy is handed a copy of those figures and
never the catalogue entry, so the price of a line cannot move when the
catalogue does.

A line also owns the allocations that hold specific tagged units for it. From
the moment a reservation is on hold a line holds exactly as many active
allocations as its quantity, and a draft line holds none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.domain.availability import AssetAllocation
from app.domain.catalogue import ProductModel
from app.domain.enums import ReleaseReason
from app.domain.errors import ValidationFailure
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies.pricing import (
    MINIMUM_LINE_QUANTITY,
    NO_DISCOUNT_PERCENT,
    HireQuote,
    LineSnapshot,
    PricingPolicy,
)

# What a line subtotal carries until the pricing policy has priced the line.
NOT_YET_PRICED: Final[Decimal] = Decimal("0.00")
MAXIMUM_LINE_QUANTITY: Final[int] = 10
QUANTITY_OUT_OF_RANGE_MESSAGE: Final[str] = (
    f"You can hire between {MINIMUM_LINE_QUANTITY} and {MAXIMUM_LINE_QUANTITY} of one tool "
    "at a time."
)


@dataclass(slots=True)
class ReservationLine:
    """One product model and a quantity within a reservation, with price snapshots.

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
        discount_percent: The trade discount at the time of booking.
        line_subtotal_ex_vat: The hire of the line after the discount, which
            is the output of the pricing policy (BR-21).
        allocations: The units held for this line, released ones included.

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
    discount_percent: Decimal = NO_DISCOUNT_PERCENT
    line_subtotal_ex_vat: Decimal = NOT_YET_PRICED
    allocations: list[AssetAllocation] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def for_model(
        cls, *, reservation_id: UUID, product_model: ProductModel, quantity: int, position: int
    ) -> ReservationLine:
        """Build a line for a product model, copying its figures onto it (BR-20).

        Args:
            reservation_id: The reservation the line belongs to.
            product_model: The catalogue entry being hired.
            quantity: How many units of it.
            position: The position of the line within the reservation.

        Raises:
            ValidationFailure: If the quantity is outside the permitted range.

        """
        if not MINIMUM_LINE_QUANTITY <= quantity <= MAXIMUM_LINE_QUANTITY:
            raise ValidationFailure(
                QUANTITY_OUT_OF_RANGE_MESSAGE,
                {
                    "minimum": MINIMUM_LINE_QUANTITY,
                    "maximum": MAXIMUM_LINE_QUANTITY,
                    "received": quantity,
                },
            )
        return cls(
            reservation_id=reservation_id,
            product_model_id=product_model.id,
            quantity=quantity,
            line_position=position,
            daily_rate_snapshot=product_model.daily_rate,
            weekly_rate_snapshot=product_model.weekly_rate,
            deposit_snapshot=product_model.deposit_amount,
            late_fee_per_day_snapshot=product_model.late_fee_per_day,
            replacement_value_snapshot=product_model.replacement_value,
        )

    def active_allocations(self) -> list[AssetAllocation]:
        """Return the allocations that still occupy a unit."""
        return [allocation for allocation in self.allocations if allocation.is_active()]

    def is_satisfied(self) -> bool:
        """Return True when the line holds exactly as many units as it asks for (BR-08)."""
        return len(self.active_allocations()) == self.quantity

    def snapshot(self) -> LineSnapshot:
        """Return the figures the pricing policy prices this line from."""
        return LineSnapshot(
            daily_rate=Money.create(self.daily_rate_snapshot),
            weekly_rate=Money.create(self.weekly_rate_snapshot),
            deposit=Money.create(self.deposit_snapshot),
            quantity=self.quantity,
        )

    def price_with(
        self, policy: PricingPolicy, period: BookingPeriod, discount_percent: Decimal
    ) -> HireQuote:
        """Price the line from its snapshots and keep the subtotal and the discount.

        Args:
            policy: The pricing policy. It is the only thing that works out a price.
            period: The hire period of the reservation.
            discount_percent: The trade discount of the customer.

        Returns:
            The quote, so the reservation can add the quotes of its lines up.

        """
        quote = policy.quote(self.snapshot(), period, discount_percent)
        self.discount_percent = quote.discount_percent
        self.line_subtotal_ex_vat = quote.amount_ex_vat.amount
        return quote

    def release_all(self, reason: ReleaseReason, now: datetime) -> int:
        """Let go of every unit the line still holds, and return how many there were.

        Args:
            reason: Why the units are being let go.
            now: The moment of the release, from the clock.

        """
        held = self.active_allocations()
        for allocation in held:
            allocation.release(reason, now)
        return len(held)
