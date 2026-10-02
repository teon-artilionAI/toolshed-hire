"""The four states a reservation can still move from.

Each class overrides the moves that are legal from it and inherits a refusal
for every other. A move checks its guards first and changes the reservation
only when all of them pass, so a refused move leaves the reservation exactly
as it was.

DRAFT is a basket. HELD has named units and thirty minutes to be confirmed
(BR-12). CONFIRMED keeps its units until collection. COLLECTED is the point of
no return, and the only move left from it is closing.

A guard that fails because of the state of the booking raises
`StateTransitionError`. A guard that fails because of a date raises
`ValidationFailure`, and the one about an unproved email address raises
`EmailNotVerifiedError`, so the API can answer each with the status it means.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.domain.business_time import business_instant
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import EmailNotVerifiedError, StateTransitionError, ValidationFailure
from app.domain.period import ensure_within_booking_window
from app.domain.states.base import ReservationState, UnitAllocator
from app.domain.states.guards import (
    ALREADY_ON_HIRE_MESSAGE,
    BRANCH_STILL_OPEN_MESSAGE,
    CANCELLATION_RULE,
    COLLECTION_DAY_RULE,
    DRAFT_HOLDS_UNITS_MESSAGE,
    EMAIL_NOT_VERIFIED_MESSAGE,
    FULL_ALLOCATION_RULE,
    HOLD_DURATION,
    HOLD_EXPIRY_RULE,
    HOLD_RAN_OUT_MESSAGE,
    HOLD_STILL_RUNNING_MESSAGE,
    LATE_CANCELLATION_CUTOFF,
    NO_LINES_MESSAGE,
    NO_SHOW_RULE,
    NOT_EVERY_UNIT_HELD_MESSAGE,
    ONE_DAY,
    TOO_EARLY_TO_COLLECT_MESSAGE,
    VERIFIED_EMAIL_RULE,
    ensure_every_unit_is_held,
    ensure_owner_or_staff,
    mark_cancelled,
)

if TYPE_CHECKING:
    from app.domain.booking import Reservation
    from app.domain.catalogue import ProductModel

class DraftState(ReservationState):
    """A basket. Nothing is held, so nobody else is affected."""

    status = ReservationStatus.DRAFT

    def hold(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        today: date,
        models: Mapping[UUID, ProductModel],
        allocator: UnitAllocator,
    ) -> None:
        """Take named units for every line and start the hold (BR-07, BR-09, BR-12).

        The period was already built as a `BookingPeriod`, so it ends after it
        starts. The dates are checked again here, because a draft made last
        week can have slipped into the past since. Units are taken only once
        every date guard has passed. They are attached to the lines only once
        every line has been given all of its units, so a refused hold leaves
        the draft holding nothing. The caller's unit of work is what undoes
        the units the allocator had already taken.

        Raises:
            ValidationFailure: If the hire starts in the past or too far
                ahead, is outside the hire limits of a model, or the
                reservation has no line.
            AllocationConflictError: If a line could not be given every unit
                it asks for at the collection branch.

        """
        if not reservation.lines:
            raise ValidationFailure(NO_LINES_MESSAGE, {"reference": reservation.reference})
        ensure_within_booking_window(reservation.period, today)
        for line in reservation.lines:
            models[line.product_model_id].ensure_can_be_hired_for(reservation.period)
        taken = {
            line.id: list(allocator.allocate(reservation, line)) for line in reservation.lines
        }
        ensure_every_unit_is_held(reservation, taken)
        for line in reservation.lines:
            line.allocations.extend(taken[line.id])
        reservation.hold_expires_at = now + HOLD_DURATION
        reservation.status = ReservationStatus.HELD

    def cancel(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        reason: str | None,
        by_owner_or_staff: bool,
        has_rental: bool,
    ) -> None:
        """Abandon the basket. There is nothing to release.

        Raises:
            AuthorisationFailure: If the caller is neither the owner nor staff.
            StateTransitionError: If the draft holds a unit, which a draft
                never should.

        """
        ensure_owner_or_staff(by_owner_or_staff)
        if reservation.has_active_allocations():
            raise StateTransitionError(
                DRAFT_HOLDS_UNITS_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.CANCELLED.value,
                rule=CANCELLATION_RULE,
            )
        mark_cancelled(reservation, now, reason)


class HeldState(ReservationState):
    """Named units are off the market, for thirty minutes."""

    status = ReservationStatus.HELD

    def confirm(self, reservation: Reservation, *, now: datetime, email_verified: bool) -> None:
        """Confirm inside the hold, and clear the expiry (BR-08, BR-47).

        Raises:
            StateTransitionError: If the hold has run out, or a line does not
                hold every unit it asks for.
            EmailNotVerifiedError: If the customer has not proved their
                address and nobody on the staff is confirming for them.

        """
        if reservation.hold_has_expired(now):
            raise StateTransitionError(
                HOLD_RAN_OUT_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.CONFIRMED.value,
                rule=HOLD_EXPIRY_RULE,
            )
        if not reservation.is_fully_allocated():
            raise StateTransitionError(
                NOT_EVERY_UNIT_HELD_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.CONFIRMED.value,
                rule=FULL_ALLOCATION_RULE,
            )
        if not email_verified:
            raise EmailNotVerifiedError(
                EMAIL_NOT_VERIFIED_MESSAGE,
                {"reference": reservation.reference},
                rule=VERIFIED_EMAIL_RULE,
            )
        reservation.hold_expires_at = None
        reservation.confirmed_at = now
        reservation.status = ReservationStatus.CONFIRMED

    def cancel(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        reason: str | None,
        by_owner_or_staff: bool,
        has_rental: bool,
    ) -> None:
        """Let the held units go, with the reason CANCELLED (BR-14).

        Raises:
            AuthorisationFailure: If the caller is neither the owner nor staff.

        """
        ensure_owner_or_staff(by_owner_or_staff)
        reservation.release_allocations(ReleaseReason.CANCELLED, now)
        reservation.hold_expires_at = None
        mark_cancelled(reservation, now, reason)

    def expire(self, reservation: Reservation, *, now: datetime) -> None:
        """Lapse a hold that has run out, and let its units go (BR-13).

        Raises:
            StateTransitionError: If the hold has not run out yet.

        """
        if not reservation.hold_has_expired(now):
            raise StateTransitionError(
                HOLD_STILL_RUNNING_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.EXPIRED.value,
                rule=HOLD_EXPIRY_RULE,
            )
        reservation.release_allocations(ReleaseReason.EXPIRED, now)
        reservation.hold_expires_at = None
        reservation.status = ReservationStatus.EXPIRED


class ConfirmedState(ReservationState):
    """The booking stands, and its units wait for collection."""

    status = ReservationStatus.CONFIRMED

    def collect(self, reservation: Reservation, *, today: date) -> None:
        """Record the collection, from the first day of the hire onward (BR-26).

        Raises:
            ValidationFailure: If the hire has not started yet.
            StateTransitionError: If a line does not hold every unit it asks for.

        """
        if today < reservation.period.start:
            raise ValidationFailure(
                TOO_EARLY_TO_COLLECT_MESSAGE,
                {"start_date": reservation.period.start.isoformat(), "today": today.isoformat()},
                rule=COLLECTION_DAY_RULE,
            )
        if not reservation.is_fully_allocated():
            raise StateTransitionError(
                NOT_EVERY_UNIT_HELD_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.COLLECTED.value,
                rule=FULL_ALLOCATION_RULE,
            )
        reservation.status = ReservationStatus.COLLECTED

    def cancel(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        reason: str | None,
        by_owner_or_staff: bool,
        has_rental: bool,
    ) -> None:
        """Let the units go, and note a cancellation that came late (BR-14, BR-16).

        A cancellation is late when it is made after 17:00, by the clock in
        Cape Town, on the day before collection. Nothing is charged for it.
        The use case counts it on the customer's profile.

        Raises:
            AuthorisationFailure: If the caller is neither the owner nor staff.
            StateTransitionError: If a rental already exists for the booking.

        """
        ensure_owner_or_staff(by_owner_or_staff)
        if has_rental:
            raise StateTransitionError(
                ALREADY_ON_HIRE_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.CANCELLED.value,
                rule=CANCELLATION_RULE,
            )
        cutoff = business_instant(reservation.period.start - ONE_DAY, LATE_CANCELLATION_CUTOFF)
        reservation.is_late_cancellation = now > cutoff
        reservation.release_allocations(ReleaseReason.CANCELLED, now)
        mark_cancelled(reservation, now, reason)

    def mark_no_show(
        self, reservation: Reservation, *, now: datetime, branch_closed_at: datetime
    ) -> None:
        """Record that nobody came, once the branch has closed on the first day (BR-17).

        Raises:
            StateTransitionError: If the branch has not closed yet.

        """
        if now <= branch_closed_at:
            raise StateTransitionError(
                BRANCH_STILL_OPEN_MESSAGE,
                from_status=self.status.value,
                to_status=ReservationStatus.NO_SHOW.value,
                rule=NO_SHOW_RULE,
            )
        reservation.release_allocations(ReleaseReason.NO_SHOW, now)
        reservation.status = ReservationStatus.NO_SHOW


class CollectedState(ReservationState):
    """The equipment is out. The booking is history and can only be closed."""

    status = ReservationStatus.COLLECTED

    def close(self, reservation: Reservation, *, now: datetime) -> None:
        """Close the booking, so that no unit is still held for it (BR-29)."""
        reservation.release_allocations(ReleaseReason.RETURNED, now)
        reservation.status = ReservationStatus.RETURNED
