"""Every refusal the reservation routes can give, as data.

Each case names the route it belongs to, makes the request that is refused,
and says what the refusal is expected to be. tests/api/test_reservation_refusals.py
runs them, once for the words and once for the guard that no sentence reads
like a log line.

This module holds what a case is made of and the sentences more than one case
expects. The cases of creating a draft are in `reservation_create_refusals`
and the cases of every other route in `reservation_move_refusals`.

A case sets up what it needs through the routes themselves, so a refusal is
reached the way a customer would reach it. The few things no route can do yet,
putting an account on hold or collecting a reservation, are written to the
database directly.

A value the framework refuses for its type keeps the framework's wording, so
such a case pins which field was named and not the sentence. A value a rule
refuses pins the sentence, because somebody chose it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from httpx import Response
from sqlmodel import Session

from app.domain.enums import AccountStatus
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld

CREATE: Final[str] = "POST /api/reservations"
HOLD: Final[str] = "POST /api/reservations/{id}/hold"
CONFIRM: Final[str] = "POST /api/reservations/{id}/confirm"
CANCEL: Final[str] = "POST /api/reservations/{id}/cancellation"
LIST: Final[str] = "GET /api/reservations"
READ: Final[str] = "GET /api/reservations/{id}"

FRAMEWORK: Final[str] = "request-validation-failure"
RULE: Final[str] = "validation-failure"
NOT_FOUND: Final[str] = "not-found"
TRANSITION: Final[str] = "state-transition"
UNAVAILABLE: Final[str] = "asset-unavailable"
FORBIDDEN_ROLE: Final[str] = "authorisation-failure"
BRANCH_SCOPE: Final[str] = "branch-scope"
ON_HOLD: Final[str] = "account-on-hold"
NOT_VERIFIED: Final[str] = "email-not-verified"
ANONYMOUS: Final[str] = "authentication-failure"

NOT_ACCEPTED: Final[str] = "Some of the details were not accepted. Check each one and try again."
NO_SUCH_RESERVATION: Final[str] = (
    "We could not find that reservation. Check the reference and try again."
)
OTHER_BRANCH: Final[str] = (
    "Counter staff can only work on bookings at their own branch. This one is at another "
    "branch."
)
ACCOUNT_ON_HOLD: Final[str] = (
    "This customer account is on hold because three bookings in the last twelve months "
    "were not collected. It cannot make a reservation until an administrator lifts the "
    "hold. Please speak to the branch."
)


@dataclass(frozen=True, slots=True)
class Stage:
    """A committed world, the routes on a still clock, and three more callers."""

    booking: BookingClient
    session: Session
    world: BookingWorld
    stranger: UserAccount
    assistant_elsewhere: UserAccount
    administrator: UserAccount

    def post(self, body: dict[str, object], account: UserAccount | None = None) -> Response:
        """Post a draft, as the world's customer unless told otherwise."""
        return self.booking.create(account or self.world.customer, body)

    def put_customer_on_hold(self) -> None:
        """Put the account of the world's customer on hold, and commit it."""
        self.world.profile.account_status = AccountStatus.ON_HOLD
        self.session.add(self.world.profile)
        self.session.commit()


@dataclass(frozen=True, slots=True)
class Refusal:
    """One request a route refuses, and what the refusal is expected to say.

    Attributes:
        name: What the case is, for the test id.
        route: The method and path template of the route, as the route table
            names it.
        ask: Makes the request and returns the response.
        status: The status expected.
        code: The problem type expected.
        detail: The sentence expected in `detail`, or None when it is not one
            this change wrote.
        fields: The sentence expected beside each refused field, for a rule.
        field_names: The fields expected to be named, for a value the
            framework refused in its own words.

    """

    name: str
    route: str
    ask: Callable[[Stage], Response]
    status: int
    code: str
    detail: str | None = None
    fields: dict[str, str] | None = None
    field_names: frozenset[str] | None = None
