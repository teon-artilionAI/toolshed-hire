"""The refusals of the reallocation route, and of a checkout of a short booking, as data.

Asking for replacement units can be refused for a caller with no credential,
for a customer, for a reservation that is not there, for counter staff of
another branch, for a reservation that is not on hold or confirmed, and when
no unit is free for a short line. A booking a force release left short is
refused at the checkout until it is given a replacement. Each is a case here.
What a case is made of is in `reservation_refusal_cases`.

A case books both units of the world for today as an administrator, releases
one of them by hand, and takes it out of service, so no unit is free to
replace it.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from tests.api.reservation_refusal_cases import (
    ANONYMOUS,
    BRANCH_SCOPE,
    FORBIDDEN_ROLE,
    NO_SUCH_RESERVATION,
    NOT_FOUND,
    OTHER_BRANCH,
    TRANSITION,
    UNAVAILABLE,
    Refusal,
    Stage,
)
from tests.support.admin_api import (
    held_units,
    reallocate,
    reallocation_path,
    release,
    take_out_of_service,
)
from tests.support.booking_api import answered, created
from tests.support.checkout_api import (
    check_out,
    checked_out,
    checkout_body,
    confirmed_today,
    read_checkout,
)

REALLOCATION: Final[str] = "POST /api/reservations/{id}/reallocation"
CHECKOUT: Final[str] = "POST /api/reservations/{id}/checkout"
BOTH_UNITS: Final[int] = 2
A_DRAFT: Final[str] = "This reservation is still a draft, so it cannot be given replacement units."
COLLECTED: Final[str] = (
    "This reservation has been collected, so it cannot be given replacement units."
)
ONE_MISSING: Final[str] = (
    "One unit of this booking is missing. Allocate a replacement before the equipment is "
    "handed over."
)


def _short_of_one(stage: Stage) -> str:
    """Book both units for today, release one by hand, take it out of service, return the key."""
    key = str(
        confirmed_today(stage.booking, stage.world, stage.administrator, quantity=BOTH_UNITS)["id"]
    )
    unit = held_units(stage.booking, stage.administrator, key)[0]
    answered(release(stage.booking, stage.administrator, unit["allocationId"]))
    take_out_of_service(stage.session, unit["assetTag"])
    return key


def _elsewhere(stage: Stage) -> Response:
    """Ask for replacements as counter staff of another branch."""
    return reallocate(stage.booking, stage.assistant_elsewhere, _short_of_one(stage))


def _a_draft(stage: Stage) -> Response:
    """Ask for replacements for a draft."""
    draft = created(
        stage.booking.create(
            stage.administrator, stage.world.payload(customer_profile_id=stage.world.profile.id)
        )
    )
    return reallocate(stage.booking, stage.administrator, draft["id"])


def _collected(stage: Stage) -> Response:
    """Ask for replacements for a reservation that has been checked out."""
    key = str(confirmed_today(stage.booking, stage.world, stage.administrator)["id"])
    checked_out(stage.booking, stage.administrator, key)
    return reallocate(stage.booking, stage.administrator, key)


def _nothing_free(stage: Stage) -> Response:
    """Ask for a replacement when the only other unit is out of service."""
    return reallocate(stage.booking, stage.administrator, _short_of_one(stage))


def _check_out_short(stage: Stage) -> Response:
    """Check out a booking that a force release left one unit short."""
    key = _short_of_one(stage)
    preview = answered(read_checkout(stage.booking, stage.administrator, key))
    return check_out(stage.booking, stage.administrator, key, checkout_body(preview))


REALLOCATION_REFUSALS: Final[list[Refusal]] = [
    Refusal(
        "ask for replacements with no credential",
        REALLOCATION,
        lambda stage: stage.booking.client.post(reallocation_path(uuid4())),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    Refusal(
        "ask for replacements as a customer",
        REALLOCATION,
        lambda stage: reallocate(stage.booking, stage.world.customer, uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    Refusal(
        "ask for replacements for a reservation that does not exist",
        REALLOCATION,
        lambda stage: reallocate(stage.booking, stage.administrator, "TSH-R-26-999999"),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "ask for replacements as counter staff of another branch",
        REALLOCATION,
        _elsewhere,
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    Refusal(
        "ask for replacements for a draft",
        REALLOCATION,
        _a_draft,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        A_DRAFT,
    ),
    Refusal(
        "ask for replacements for a reservation that has been collected",
        REALLOCATION,
        _collected,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        COLLECTED,
    ),
    Refusal(
        "ask for replacements when no unit is free",
        REALLOCATION,
        _nothing_free,
        status.HTTP_409_CONFLICT,
        UNAVAILABLE,
    ),
    Refusal(
        "check out a booking a force release left short",
        CHECKOUT,
        _check_out_short,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ONE_MISSING,
    ),
]

__all__ = ["REALLOCATION", "REALLOCATION_REFUSALS"]
