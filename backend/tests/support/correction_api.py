"""Hires in the states a charge correction is tried on, for the tests of the corrections.

Each builder takes a hire of the worked example's model through the routes,
the way the counter would. The deposit is R1,200.00 a unit and the late fee
R120.00 a day, the clock stands still on Monday the second of March 2026, and
the hire is due back on Friday the sixth. So a hire back two days late owes
R240.00, which the deposit pays, and one back fourteen days late owes
R1,680.00, which leaves R480.00 due once the deposit has paid what it can.

The audit trail is read through the session of the test, because the events
are written by the requests and committed with them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from uuid import uuid4

from httpx import Response
from sqlmodel import Session, col, select

from app.infrastructure.models import AuditEvent, UserAccount
from tests.support.admin_api import (
    REASON,
    adjust,
    adjustments_path,
    charge_of,
    reversal_path,
    reverse,
    waive,
    waiver_path,
)
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.rental_api import ONE_DAY, item_ids, on_hire, return_body, take_back

# The day the hires of these tests are due back is four days after today.
DAYS_TO_THE_DUE_DATE: Final[int] = 4
TWO_DAYS_LATE: Final[timedelta] = ONE_DAY * (DAYS_TO_THE_DUE_DATE + 2)
FOURTEEN_DAYS_LATE: Final[timedelta] = ONE_DAY * (DAYS_TO_THE_DUE_DATE + 14)
ON_THE_DUE_DATE: Final[timedelta] = ONE_DAY * DAYS_TO_THE_DUE_DATE
TWO_UNITS: Final[int] = 2
# The three corrections and the three callers a refusal case names.
WAIVE: Final[str] = "waive"
REVERSE: Final[str] = "reverse"
ADJUST: Final[str] = "adjust"
COUNTER: Final[str] = "counter"
CUSTOMER: Final[str] = "customer"
NOBODY: Final[str] = "nobody"
SMALL_AMOUNT: Final[str] = "10.00"


@dataclass(frozen=True, slots=True)
class Desk:
    """The routes on a still clock, a committed world and the people at the counter."""

    booking: BookingClient
    session: Session
    world: BookingWorld
    assistant: UserAccount
    administrator: UserAccount

    def returned(self, late_by: timedelta, *, quantity: int = 1) -> dict[str, object]:
        """Hire units today, move the clock on and take every unit back, returning the rental."""
        rental = on_hire(self.booking, self.world, self.assistant, quantity=quantity)
        self.booking.clock.advance(late_by)
        return answered(
            take_back(self.booking, self.assistant, rental["id"], return_body(*item_ids(rental)))
        )

    def partly_back_late(self) -> dict[str, object]:
        """Hire two units today and take one back two days late, returning the rental."""
        rental = on_hire(self.booking, self.world, self.assistant, quantity=TWO_UNITS)
        self.booking.clock.advance(TWO_DAYS_LATE)
        first = item_ids(rental)[0]
        return answered(take_back(self.booking, self.assistant, rental["id"], return_body(first)))

    def events(self, action: str) -> list[AuditEvent]:
        """Return the audit events of one action, in the order they were written."""
        self.session.expire_all()
        return list(
            self.session.exec(
                select(AuditEvent)
                .where(col(AuditEvent.action) == action)
                .order_by(col(AuditEvent.id))
            )
        )


@dataclass(frozen=True, slots=True)
class Case:
    """One request a correction refuses, and what the refusal is expected to say.

    Attributes:
        name: What the case is, for the test id.
        ask: Makes the request and returns the response.
        status: The status expected.
        code: The problem type expected.
        detail: The sentence expected in `detail`, or None.
        fields: The fields expected under `errors.fields`, or None.
        sentences: The sentence expected beside each field, for a rule.

    """

    name: str
    ask: Callable[[Desk], Response]
    status: int
    code: str
    detail: str | None = None
    fields: frozenset[str] | None = None
    sentences: dict[str, str] | None = None


def settled_hire(desk: Desk) -> dict[str, object]:
    """Return the worked example hire, back two days late and settled from its deposit."""
    return desk.returned(TWO_DAYS_LATE)


def settled_fee(desk: Desk) -> object:
    """Return the key of the settled late fee of the worked example."""
    return charge_of(settled_hire(desk), "LATE_FEE")["id"]


def post_as_administrator(desk: Desk, path: str, body: dict[str, object]) -> Response:
    """Post a body to a correction route as the administrator."""
    headers = desk.booking.headers(desk.administrator)
    return desk.booking.client.post(path, json=body, headers=headers)


def reversed_twice(desk: Desk) -> Response:
    """Reverse the settled late fee, and then reverse it again."""
    fee = settled_fee(desk)
    answered(reverse(desk.booking, desk.administrator, fee))
    return reverse(desk.booking, desk.administrator, fee)


def reversal_reversed(desk: Desk) -> Response:
    """Reverse the settled late fee, and then reverse the reversal."""
    after = answered(reverse(desk.booking, desk.administrator, settled_fee(desk)))
    return reverse(desk.booking, desk.administrator, charges_of_type(after, "LATE_FEE")[1]["id"])


def deposit_movement_reversed(charge_type: str) -> Callable[[Desk], Response]:
    """Return a case that reverses a deposit movement of the settled hire."""
    return lambda desk: reverse(
        desk.booking, desk.administrator, charge_of(settled_hire(desk), charge_type)["id"]
    )


def pending_fee_reversed(desk: Desk) -> Response:
    """Reverse a late fee still owed on a hire with a unit still out."""
    fee = charge_of(desk.partly_back_late(), "LATE_FEE")["id"]
    return reverse(desk.booking, desk.administrator, fee)


def asked_by(role: str, correction: str) -> Callable[[Desk], Response]:
    """Return a case that asks for a correction as counter staff, a customer or nobody."""

    def ask(desk: Desk) -> Response:
        """Make the request as the caller named."""
        rental = settled_hire(desk)
        body: dict[str, object] = {"reason": REASON}
        if correction == ADJUST:
            path = adjustments_path(rental["id"])
            body["amountIncVat"] = SMALL_AMOUNT
        else:
            route = waiver_path if correction == WAIVE else reversal_path
            path = route(charge_of(rental, "LATE_FEE")["id"])
        if role == NOBODY:
            return desk.booking.client.post(path, json=body)
        account = desk.assistant if role == COUNTER else desk.world.customer
        return desk.booking.client.post(path, json=body, headers=desk.booking.headers(account))

    return ask


def adjusted_by(amount: object) -> Callable[[Desk], Response]:
    """Return a case that adjusts the settled hire by the amount given."""
    return lambda desk: adjust(desk.booking, desk.administrator, settled_hire(desk)["id"], amount)


def posted_with(correction: str, body: dict[str, object]) -> Callable[[Desk], Response]:
    """Return a case that posts a correction of the settled hire with the body given."""

    def ask(desk: Desk) -> Response:
        """Post the body."""
        rental = settled_hire(desk)
        if correction == ADJUST:
            sent = {"amountIncVat": SMALL_AMOUNT, **body}
            return post_as_administrator(desk, adjustments_path(rental["id"]), sent)
        fee = charge_of(rental, "LATE_FEE")["id"]
        return post_as_administrator(desk, waiver_path(fee), body)

    return ask


def unknown(correction: str) -> Callable[[Desk], Response]:
    """Return a case that corrects a charge or a hire nobody issued."""
    if correction == ADJUST:
        return lambda desk: adjust(desk.booking, desk.administrator, uuid4(), SMALL_AMOUNT)
    act = waive if correction == WAIVE else reverse
    return lambda desk: act(desk.booking, desk.administrator, uuid4())


def charges_of_type(rental: dict[str, object], charge_type: str) -> list[dict[str, object]]:
    """Return every charge of one type on a rental, in the order it lists them."""
    charges = rental["charges"]
    assert isinstance(charges, list)
    return [charge for charge in charges if charge["type"] == charge_type]


__all__ = [
    "FOURTEEN_DAYS_LATE",
    "ON_THE_DUE_DATE",
    "TWO_DAYS_LATE",
    "ADJUST",
    "COUNTER",
    "CUSTOMER",
    "NOBODY",
    "REVERSE",
    "SMALL_AMOUNT",
    "TWO_UNITS",
    "WAIVE",
    "Case",
    "Desk",
    "adjusted_by",
    "asked_by",
    "charges_of_type",
    "deposit_movement_reversed",
    "pending_fee_reversed",
    "post_as_administrator",
    "posted_with",
    "reversal_reversed",
    "reversed_twice",
    "settled_fee",
    "settled_hire",
    "unknown",
]
