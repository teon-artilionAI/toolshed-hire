"""What a refusal of a rental route is made of, and the sentences more than one case expects.

Each case names the route it belongs to, makes the request that is refused,
and says what the refusal is expected to be, in the shape the reservation
cases use (`tests/api/reservation_refusal_cases.py`). The cases of the return
are in `rental_return_refusals` and those of every other rental route in
`rental_settlement_refusals`. tests/api/test_rental_refusals.py runs them.

A case sets up what it needs through the routes themselves. A rental is put
out by an administrator, who may act at any branch, so a case only names the
caller it is about. The clock stands still on Monday the second of March 2026,
the first day of every hire here, which is due back on the sixth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.rental_api import item_ids, on_hire, return_body, take_back

RETURN: Final[str] = "POST /api/rentals/{id}/returns"
LOSS: Final[str] = "POST /api/rentals/{id}/items/{itemId}/loss"
BALANCE: Final[str] = "POST /api/rentals/{id}/balance-payment"
LIST: Final[str] = "GET /api/rentals"
READ: Final[str] = "GET /api/rentals/{id}"
MINE: Final[str] = "GET /api/me/rentals"

NO_SUCH_RENTAL: Final[str] = "We could not find that rental. Check the reference and try again."
ALREADY_BACK: Final[str] = "This unit is already back, so it cannot be returned again."
PAYMENT_REFERENCE: Final[str] = "EFT-1"


@dataclass(frozen=True, slots=True)
class RentalStage:
    """A committed world, the routes on a still clock, and the callers the cases are asked by."""

    booking: BookingClient
    world: BookingWorld
    assistant_elsewhere: UserAccount
    administrator: UserAccount


@dataclass(frozen=True, slots=True)
class RentalRefusal:
    """One request a rental route refuses, and what the refusal is expected to say.

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
    ask: Callable[[RentalStage], Response]
    status: int
    code: str
    detail: str | None = None
    fields: dict[str, str] | None = None
    field_names: frozenset[str] | None = None


def out_on_hire(stage: RentalStage) -> dict[str, object]:
    """Put a hire of one unit out as the administrator and return the rental."""
    return on_hire(stage.booking, stage.world, stage.administrator)


def back_already(stage: RentalStage) -> tuple[dict[str, object], str]:
    """Put a hire out, take its unit back, and return the rental and the unit's key."""
    rental = out_on_hire(stage)
    (key,) = item_ids(rental)
    answered(take_back(stage.booking, stage.administrator, rental["id"], return_body(key)))
    return rental, key


__all__ = [
    "ALREADY_BACK",
    "BALANCE",
    "LIST",
    "LOSS",
    "MINE",
    "NO_SUCH_RENTAL",
    "PAYMENT_REFERENCE",
    "READ",
    "RETURN",
    "RentalRefusal",
    "RentalStage",
    "back_already",
    "out_on_hire",
]
