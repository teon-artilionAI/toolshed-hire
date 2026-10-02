"""What one caller is shown of a reservation, and what they may do to it next.

Every use case of the booking module answers with a `ReservationView`. It is
the stored reservation, less anything this caller may not see, together with
three answers, whether the caller may put it on hold, confirm it or cancel it
right now.

Those answers are worked out here, on the server, so a screen never has to
know the rules of the lifecycle. Whether a move is legal from a status is read
off the reservation states themselves, which are the one place that rule is
written (BR-11). What is added here is who is asking and what time it is.

A customer is never shown an asset tag (US-07), so the tags are taken off the
lines before a customer's view is built. Counter staff and administrators see
them, because they are who hands the units over.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from app.application.booking.read_models import ReservationDetail, ReservationPage
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.states import state_for
from app.domain.states.base import CANCEL_MOVE, CONFIRM_MOVE, HOLD_MOVE


@dataclass(frozen=True, slots=True)
class ReservationView:
    """One reservation as one caller sees it.

    Attributes:
        detail: The reservation, with nothing in it the caller may not see.
        can_hold: True when the caller may put it on hold right now.
        can_confirm: True when the caller may confirm it right now.
        can_cancel: True when the caller may cancel it right now.

    """

    detail: ReservationDetail
    can_hold: bool
    can_confirm: bool
    can_cancel: bool


@dataclass(frozen=True, slots=True)
class ReservationViewPage:
    """One page of reservations as one caller sees them, newest first.

    Attributes:
        items: The reservations on the page.
        page: The page this is, counted from one.
        page_size: How many reservations a page holds.
        total: How many reservations match across every page.

    """

    items: tuple[ReservationView, ...]
    page: int
    page_size: int
    total: int


def view_for(actor: Actor, detail: ReservationDetail, now: datetime) -> ReservationView:
    """Build what one caller is shown of a reservation they are allowed to read.

    Args:
        actor: Who is asking, with the role and the branch they hold.
        detail: The reservation as it is stored. The read that fetched it has
            already made sure this caller may see it.
        now: The current instant, from the clock.

    """
    may_act = _may_act_on(actor, detail)
    state = state_for(detail.status)
    hold_stands = not detail.hold_is_overdue(now)
    return ReservationView(
        detail=_as_shown_to(actor, detail),
        can_hold=may_act and state.permits(HOLD_MOVE),
        can_confirm=(
            may_act
            and state.permits(CONFIRM_MOVE)
            and hold_stands
            and _holds_every_unit(detail)
            and _satisfies_the_verification_rule(actor, detail)
        ),
        can_cancel=may_act and state.permits(CANCEL_MOVE) and hold_stands,
    )


def page_for(actor: Actor, page: ReservationPage, now: datetime) -> ReservationViewPage:
    """Build what one caller is shown of a page of reservations."""
    return ReservationViewPage(
        items=tuple(view_for(actor, detail, now) for detail in page.items),
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


def _may_act_on(actor: Actor, detail: ReservationDetail) -> bool:
    """Return True when the caller may change this reservation at all.

    A customer who can read a reservation owns it, because the read is scoped
    to their own. An administrator acts at every branch. Counter staff act at
    their own branch only (BR-43), though they may read any.
    """
    if actor.role is UserRole.COUNTER_STAFF:
        return actor.branch_id == detail.branch_id
    return True


def _holds_every_unit(detail: ReservationDetail) -> bool:
    """Return True when every line holds as many units as it asks for (BR-08)."""
    return bool(detail.lines) and all(
        line.allocated_count == line.quantity for line in detail.lines
    )


def _satisfies_the_verification_rule(actor: Actor, detail: ReservationDetail) -> bool:
    """Return True when a confirmation by this caller would satisfy BR-47.

    A customer has to have proved their address. A member of staff confirming
    for the customer at the counter satisfies the rule by being there.
    """
    return actor.role is not UserRole.CUSTOMER or detail.customer_email_verified


def _as_shown_to(actor: Actor, detail: ReservationDetail) -> ReservationDetail:
    """Return the reservation with the asset tags removed for a customer (US-07)."""
    if actor.role is not UserRole.CUSTOMER:
        return detail
    return replace(detail, lines=tuple(replace(line, asset_tags=()) for line in detail.lines))
