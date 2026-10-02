"""The reservation, which is the aggregate root of a booking.

A reservation owns its lines, and each line owns the allocations that hold
specific tagged units for it. The line is in `app.domain.booking_line` and the
allocation in `app.domain.availability`. Nothing here knows how any of it is
stored. The repositories in the infrastructure layer map these dataclasses to
the table classes and back.

A reservation never changes its own status. Every move is asked of the state
it is in (BR-11), which is the State pattern the design document names. The
states live in `app.domain.states`. Each one permits the moves that are legal
from it and refuses every other with `StateTransitionError`, so a move nobody
thought to check is refused and not allowed by accident. The guards and the
effects of each move are documented on the state that permits it.

The money on a reservation is the output of the pricing policy (BR-21). The
rates are copied onto a line when it is added (BR-20), the policy prices each
line from that copy, and the totals are those answers added up. A later change
to the catalogue therefore never alters a reservation that already exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final
from uuid import UUID, uuid4

from app.domain.booking_line import (
    MAXIMUM_LINE_QUANTITY,
    NOT_YET_PRICED,
    QUANTITY_OUT_OF_RANGE_MESSAGE,
    ReservationLine,
)
from app.domain.booking_reference import format_reference
from app.domain.catalogue import ProductModel
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies.pricing import MINIMUM_LINE_QUANTITY, NO_DISCOUNT_PERCENT, PricingPolicy
from app.domain.policies.totals import totals_of
from app.domain.states import state_for

if TYPE_CHECKING:
    from app.domain.states.base import ReservationState, UnitAllocator

__all__ = [
    "MAXIMUM_LINE_QUANTITY",
    "MINIMUM_LINE_QUANTITY",
    "NOT_YET_PRICED",
    "QUANTITY_OUT_OF_RANGE_MESSAGE",
    "Reservation",
    "ReservationLine",
    "format_reference",
]

FIRST_LINE_POSITION: Final[int] = 1

MODEL_ALREADY_ON_RESERVATION_MESSAGE: Final[str] = (
    "Each tool can appear once in a reservation. Change the quantity instead."
)
LINES_ARE_FIXED_MESSAGE: Final[str] = (
    "The tools on this reservation can only be changed while it is still a draft."
)


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
        status: Where the booking is in its lifecycle. Only a state changes it.
        created_by_user_id: The account that raised the booking.
        lines: The lines of the booking, in position order.
        vat_amount: The VAT on the subtotal.
        deposit_total: The deposit across every unit.
        estimated_total_inc_vat: What the customer is told to expect to pay.
        hold_expires_at: When a held booking lapses (BR-12). Set only while held.
        confirmed_at: When the booking was confirmed.
        cancelled_at: When the booking was cancelled.
        cancellation_reason: Why it was cancelled, when a reason was given.
        notes: Anything the customer or the assistant wrote on the booking.
        is_late_cancellation: True when a cancellation fell after the cutoff
            of BR-16. It is not stored on the booking. The use case reads it to
            count the late cancellation on the customer's profile.

    """

    reference: str
    customer_profile_id: UUID
    branch_id: UUID
    period: BookingPeriod
    status: ReservationStatus
    created_by_user_id: UUID
    lines: list[ReservationLine] = field(default_factory=list)
    vat_amount: Decimal = NOT_YET_PRICED
    deposit_total: Decimal = NOT_YET_PRICED
    estimated_total_inc_vat: Decimal = NOT_YET_PRICED
    hold_expires_at: datetime | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    notes: str | None = None
    is_late_cancellation: bool = False
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def draft(
        cls,
        *,
        reference: str,
        customer_profile_id: UUID,
        branch_id: UUID,
        period: BookingPeriod,
        created_by_user_id: UUID,
        notes: str | None = None,
    ) -> Reservation:
        """Build a new reservation in the DRAFT status with no lines yet.

        This is how a reservation enters its lifecycle. A draft is a basket.
        It holds no unit, so it affects nobody else.
        """
        return cls(
            reference=reference,
            customer_profile_id=customer_profile_id,
            branch_id=branch_id,
            period=period,
            status=ReservationStatus.DRAFT,
            created_by_user_id=created_by_user_id,
            notes=notes,
        )

    @property
    def state(self) -> ReservationState:
        """Return the state the reservation is in, which decides its next moves."""
        return state_for(self.status)

    # Lines and money.

    def add_line(self, product_model: ProductModel, quantity: int) -> ReservationLine:
        """Add a line for a product model, snapshotting its prices (BR-20).

        Returns:
            The new line, already appended at the next position. It carries no
            subtotal until `price_with` has run.

        Raises:
            StateTransitionError: If the reservation is no longer a draft.
            ValidationFailure: If the quantity is outside the permitted range,
                or the reservation already has a line for the product model.
                One model appears once in a booking and its quantity says how
                many.

        """
        self._ensure_still_a_draft()
        if any(line.product_model_id == product_model.id for line in self.lines):
            raise ValidationFailure(
                MODEL_ALREADY_ON_RESERVATION_MESSAGE,
                {"sku": product_model.sku, "reference": self.reference},
            )
        line = ReservationLine.for_model(
            reservation_id=self.id,
            product_model=product_model,
            quantity=quantity,
            position=len(self.lines) + FIRST_LINE_POSITION,
        )
        self.lines.append(line)
        return line

    def price_with(self, policy: PricingPolicy, discount_percent: Decimal) -> None:
        """Price every line from its snapshots and keep the totals (BR-21).

        Args:
            policy: The pricing policy. Nothing else works out a hire price.
            discount_percent: The trade discount of the customer.

        Raises:
            StateTransitionError: If the reservation is no longer a draft. The
                figures of a booking are fixed once it holds units.

        """
        self._ensure_still_a_draft()
        totals = totals_of(
            [line.price_with(policy, self.period, discount_percent) for line in self.lines]
        )
        self.vat_amount = totals.vat_amount.amount
        self.deposit_total = totals.deposit_total.amount
        self.estimated_total_inc_vat = totals.estimated_total_inc_vat.amount

    def subtotal_ex_vat(self) -> Money:
        """Return the hire of every line after the discount, excluding VAT.

        It is the line subtotals added together, so it cannot disagree with
        them. Each one is the output of the pricing policy.
        """
        subtotal = Money.zero()
        for line in self.lines:
            subtotal = subtotal.add(Money.create(line.line_subtotal_ex_vat))
        return subtotal

    def discount_percent(self) -> Decimal:
        """Return the trade discount the reservation was priced with.

        Every line carries the same one, because it is the discount of the one
        customer the reservation belongs to.
        """
        return self.lines[0].discount_percent if self.lines else NO_DISCOUNT_PERCENT

    # Questions the states ask.

    def is_fully_allocated(self) -> bool:
        """Return True when every line holds the units it asks for (BR-08).

        A reservation with no lines is not fully allocated, because there is
        nothing to collect.
        """
        return bool(self.lines) and all(line.is_satisfied() for line in self.lines)

    def has_active_allocations(self) -> bool:
        """Return True while any line still holds a unit."""
        return any(line.active_allocations() for line in self.lines)

    def hold_has_expired(self, now: datetime) -> bool:
        """Return True when the reservation carries a hold that has run out (BR-13).

        The hold stands up to and including the instant it expires at. A
        reservation with no expiry set has no hold to run out.
        """
        return self.hold_expires_at is not None and now > self.hold_expires_at

    def release_allocations(self, reason: ReleaseReason, now: datetime) -> int:
        """Let go of every unit still held, and return how many there were (BR-14)."""
        return sum(line.release_all(reason, now) for line in self.lines)

    # The moves. Each one is asked of the current state and of nothing else.

    def hold(
        self,
        *,
        now: datetime,
        today: date,
        models: Mapping[UUID, ProductModel],
        allocator: UnitAllocator,
    ) -> None:
        """Put the reservation on hold, taking named units for every line (BR-12)."""
        self.state.hold(self, now=now, today=today, models=models, allocator=allocator)

    def confirm(self, *, now: datetime, email_verified: bool) -> None:
        """Confirm a reservation that is on hold (BR-08, BR-47).

        `email_verified` is True when the customer has proved their address,
        or when a member of staff is confirming on their behalf.
        """
        self.state.confirm(self, now=now, email_verified=email_verified)

    def cancel(
        self,
        *,
        now: datetime,
        reason: str | None,
        by_owner_or_staff: bool,
        has_rental: bool = False,
    ) -> None:
        """Cancel the reservation and let its units go (BR-14, BR-15, BR-16)."""
        self.state.cancel(
            self, now=now, reason=reason, by_owner_or_staff=by_owner_or_staff, has_rental=has_rental
        )

    def collect(self, *, today: date) -> None:
        """Record that the equipment has been collected (BR-26)."""
        self.state.collect(self, today=today)

    def expire(self, *, now: datetime) -> None:
        """Lapse a hold that has run out and let its units go (BR-13)."""
        self.state.expire(self, now=now)

    def mark_no_show(self, *, now: datetime, branch_closed_at: datetime) -> None:
        """Record that a confirmed reservation was never collected (BR-17).

        `branch_closed_at` is the instant the collection branch closed on the
        first day of the hire.
        """
        self.state.mark_no_show(self, now=now, branch_closed_at=branch_closed_at)

    def close(self, *, now: datetime) -> None:
        """Close a collected reservation once everything is back (BR-29)."""
        self.state.close(self, now=now)

    def _ensure_still_a_draft(self) -> None:
        """Refuse a change to the lines or the figures of a booking that holds units.

        Raises:
            StateTransitionError: If the reservation is no longer a draft.

        """
        if self.status is not ReservationStatus.DRAFT:
            raise StateTransitionError(
                LINES_ARE_FIXED_MESSAGE,
                from_status=self.status.value,
                to_status=self.status.value,
            )
