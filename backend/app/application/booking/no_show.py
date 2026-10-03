"""Recording a no show and counting the strike it is, for the sweep and for staff alike (BR-17).

A confirmed reservation that nobody collected becomes NO_SHOW in one of two
ways. The lazy sweep does it once the collection branch has closed on the
first day of the hire, and a member of staff at the counter can do it from the
start of that day. Both go through `mark_as_no_show`, so both make the same
move through the reservation's state, release every unit with the reason
`NO_SHOW` and count the same strike. What differs is who the audit event names.
The sweep is nobody, and staff are themselves, with the reason they gave.

Counting the strike locks the customer profile first. Two no shows of one
customer recorded at the same moment therefore take turns, and the second one
counts the first, so a third strike can never be missed because two arrived
together. The running total on the profile goes up by one in the database. The
hold is decided from the reservations themselves, by `standing_after_strikes`
in the domain, and putting an account on hold writes an event of its own
(BR-18, BR-49).

`mark_due_no_shows` is the half of the sweep that finds the bookings. It takes
at most a batch of them, locked, and checks each one again before it acts,
because a booking can be collected or cancelled between being found and being
locked.

Nothing here commits. The caller owns the transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.booking.access import RESERVATION_NO_SHOW_ACTION, record_change, state_of
from app.application.unit_of_work import UnitOfWork
from app.domain.booking import Reservation
from app.domain.business_time import business_instant
from app.domain.identity import Actor
from app.domain.no_show import standing_after_strikes, strike_window_opens_after
from app.domain.states.base import NO_SHOW_MOVE
from app.domain.states.guards import branch_has_closed

logger = logging.getLogger(__name__)

CUSTOMER_ENTITY_TYPE: Final[str] = "customer_profile"
CUSTOMER_PUT_ON_HOLD_ACTION: Final[str] = "customer.put_on_hold"
NO_SHOW_REASON_KEY: Final[str] = "no_show_reason"


@dataclass(frozen=True, slots=True)
class NoShowOutcome:
    """What recording one no show did.

    Attributes:
        reference: The reference of the reservation.
        released_count: How many units it let go.
        strikes_in_window: The customer's no shows in the rolling twelve
            months, this one included.
        put_on_hold: True when this no show put the customer on hold.

    """

    reference: str
    released_count: int
    strikes_in_window: int
    put_on_hold: bool


@dataclass(frozen=True, slots=True)
class NoShowSweep:
    """What one pass of the no show half of the sweep did.

    Attributes:
        due_count: How many reservations the query found and locked.
        marked: The references of the ones it marked as no shows.
        customers_put_on_hold: The customers those no shows put on hold.

    """

    due_count: int
    marked: tuple[str, ...]
    customers_put_on_hold: tuple[UUID, ...]


def mark_as_no_show(
    uow: UnitOfWork,
    reservation: Reservation,
    *,
    actor: Actor | None,
    now: datetime,
    today: date,
    branch_closed_at: datetime | None,
    reason: str | None = None,
) -> NoShowOutcome:
    """Move one locked reservation to NO_SHOW, count the strike and record both.

    Args:
        uow: The open unit of work that holds the lock on the reservation.
        reservation: The reservation, read for a change.
        actor: The member of staff marking it, or None for the sweep.
        now: The current instant, from the clock.
        today: The current business day, which the strike window ends on.
        branch_closed_at: When the branch closed on the first day, for the
            sweep. None for staff, who may mark it from the start of that day.
        reason: Why staff marked it. The sweep gives none.

    Raises:
        StateTransitionError: If the reservation is not confirmed, or it is
            too soon to call it a no show.

    """
    before = state_of(reservation)
    held_before = sum(len(line.active_allocations()) for line in reservation.lines)
    reservation.mark_no_show(now=now, branch_closed_at=branch_closed_at)
    uow.reservations.save(reservation)
    record_change(
        uow,
        actor=actor,
        reservation=reservation,
        action=RESERVATION_NO_SHOW_ACTION,
        occurred_at=now,
        before=before,
        extra={NO_SHOW_REASON_KEY: reason},
    )
    strikes, put_on_hold = _count_the_strike(uow, reservation, actor, now, today)
    outcome = NoShowOutcome(
        reference=reservation.reference,
        released_count=held_before,
        strikes_in_window=strikes,
        put_on_hold=put_on_hold,
    )
    logger.info(
        "reservation.no_show_recorded",
        extra={
            "reference": reservation.reference,
            "reservation_id": str(reservation.id),
            "customer_profile_id": str(reservation.customer_profile_id),
            "by_staff": actor is not None,
            "released_count": outcome.released_count,
            "strikes_in_window": strikes,
            "put_on_hold": put_on_hold,
        },
    )
    return outcome


def mark_due_no_shows(uow: UnitOfWork, now: datetime, today: date, limit: int) -> NoShowSweep:
    """Mark every confirmed booking whose branch has closed on its first day, a batch at a time.

    Args:
        uow: The open unit of work the sweep runs in.
        now: The current instant, from the clock.
        today: The current business day.
        limit: The most reservations to take in this pass.

    """
    due = uow.reservations.lock_due_no_shows(now, limit)
    marked: list[str] = []
    held: list[UUID] = []
    for found in due:
        reservation = found.reservation
        closed_at = business_instant(reservation.period.start, found.branch_closes_at)
        if not (reservation.state.permits(NO_SHOW_MOVE) and branch_has_closed(now, closed_at)):
            continue
        outcome = mark_as_no_show(
            uow, reservation, actor=None, now=now, today=today, branch_closed_at=closed_at
        )
        marked.append(outcome.reference)
        if outcome.put_on_hold:
            held.append(reservation.customer_profile_id)
    return NoShowSweep(due_count=len(due), marked=tuple(marked), customers_put_on_hold=tuple(held))


def _count_the_strike(
    uow: UnitOfWork, reservation: Reservation, actor: Actor | None, now: datetime, today: date
) -> tuple[int, bool]:
    """Count one no show on the customer and put them on hold at the third (BR-18).

    Returns:
        The no shows in the rolling twelve months, this one included, and
        whether the customer was put on hold by it.

    Raises:
        LookupError: If the profile cannot be read. A reservation carries a
            foreign key to its profile and nothing is ever deleted, so this is
            a fault in the data.

    """
    customer = uow.customers.get_for_update(reservation.customer_profile_id)
    if customer is None:
        raise LookupError(
            f"Attempted to count a no show on customer profile {reservation.customer_profile_id} "
            f"of reservation {reservation.reference}, and the profile could not be read."
        )
    uow.customers.record_no_show(customer.id)
    strikes = uow.reservations.count_no_shows_since(customer.id, strike_window_opens_after(today))
    standing = standing_after_strikes(customer.account_status, strikes)
    if standing is customer.account_status:
        return strikes, False
    uow.customers.save_account_status(customer.id, standing)
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=CUSTOMER_ENTITY_TYPE,
            entity_id=customer.id,
            action=CUSTOMER_PUT_ON_HOLD_ACTION,
            occurred_at=now,
            before_state={"account_status": customer.account_status.value},
            after_state={
                "account_status": standing.value,
                "no_shows_in_twelve_months": strikes,
                "reservation_reference": reservation.reference,
            },
        )
    )
    logger.info(
        "customer.put_on_hold",
        extra={
            "customer_profile_id": str(customer.id),
            "strikes_in_window": strikes,
            "reservation_reference": reservation.reference,
            "by_staff": actor is not None,
        },
    )
    return strikes, True
