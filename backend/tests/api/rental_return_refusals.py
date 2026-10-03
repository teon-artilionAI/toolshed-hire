"""The refusals of the return route, as data.

Taking units back can be refused for a caller who is not staff, for counter
staff of another branch, for a rental that is not there, for a unit that is
already back, and for a list that is wrong, which is a unit that is not on the
rental, one listed twice, a meter reading below the one it went out with, an
empty list or a value the framework cannot read. What a case is made of is in
`rental_refusal_cases`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from tests.api.rental_refusal_cases import (
    ALREADY_BACK,
    NO_SUCH_RENTAL,
    RETURN,
    RentalRefusal,
    RentalStage,
    back_already,
    out_on_hire,
)
from tests.api.reservation_refusal_cases import (
    ANONYMOUS,
    BRANCH_SCOPE,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    NOT_ACCEPTED,
    NOT_FOUND,
    OTHER_BRANCH,
    TRANSITION,
)
from tests.support.booking_api import answered, created
from tests.support.checkout_api import (
    check_out,
    checkout_body,
    confirmed_today,
    read_checkout,
    rental_path,
)
from tests.support.rental_api import TODAY_TO_THE_SIXTH, item_ids, return_body, take_back

NOT_ON_RENTAL: Final[str] = "This unit is not on this rental."
LISTED_TWICE: Final[str] = "This unit is already in the list. List each unit once."
METER_BELOW: Final[str] = (
    "The meter reading cannot be lower than the reading the unit went out with."
)
HOUR_METER_OUT: Final[int] = 400


def _return_as_admin(stage: RentalStage, body_of: Callable[[str], dict[str, object]]) -> Response:
    """Put a hire out and post the return body built from its unit's key."""
    rental = out_on_hire(stage)
    (key,) = item_ids(rental)
    return take_back(stage.booking, stage.administrator, rental["id"], body_of(key))


def _returned_again(stage: RentalStage) -> Response:
    """Return a unit that is already back."""
    rental, key = back_already(stage)
    return take_back(stage.booking, stage.administrator, rental["id"], return_body(key))


def _with_meter_below(stage: RentalStage) -> Response:
    """Return a unit with a meter reading lower than the one it went out with."""
    reservation = confirmed_today(
        stage.booking, stage.world, stage.administrator, period=TODAY_TO_THE_SIXTH
    )
    preview = answered(read_checkout(stage.booking, stage.administrator, reservation["id"]))
    rental = created(
        check_out(
            stage.booking,
            stage.administrator,
            reservation["id"],
            checkout_body(preview, hourMeterOut=HOUR_METER_OUT),
        )
    )
    (key,) = item_ids(rental)
    body = return_body(key, hourMeterIn=HOUR_METER_OUT - 1)
    return take_back(stage.booking, stage.administrator, rental["id"], body)


def _elsewhere(stage: RentalStage) -> Response:
    """Take a unit back as counter staff of another branch."""
    rental = out_on_hire(stage)
    return take_back(
        stage.booking, stage.assistant_elsewhere, rental["id"], return_body(*item_ids(rental))
    )


RETURN_REFUSALS: Final[list[RentalRefusal]] = [
    RentalRefusal(
        "return with no credential",
        RETURN,
        lambda stage: stage.booking.client.post(
            f"{rental_path(uuid4())}/returns", json=return_body(str(uuid4()))
        ),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    RentalRefusal(
        "return as a customer",
        RETURN,
        lambda stage: take_back(
            stage.booking, stage.world.customer, uuid4(), return_body(str(uuid4()))
        ),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "return at another branch",
        RETURN,
        _elsewhere,
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    RentalRefusal(
        "return on a rental that does not exist",
        RETURN,
        lambda stage: take_back(
            stage.booking, stage.administrator, "TSH-H-26-999999", return_body(str(uuid4()))
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RENTAL,
    ),
    RentalRefusal(
        "return a unit that is already back",
        RETURN,
        _returned_again,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ALREADY_BACK,
    ),
    RentalRefusal(
        "return a unit that is not on the rental",
        RETURN,
        lambda stage: _return_as_admin(stage, lambda _key: return_body(str(uuid4()))),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items.0.rentalItemId": NOT_ON_RENTAL},
    ),
    RentalRefusal(
        "return one unit twice in one list",
        RETURN,
        lambda stage: _return_as_admin(stage, lambda key: return_body(key, key)),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items.1.rentalItemId": LISTED_TWICE},
    ),
    RentalRefusal(
        "return a unit with a meter reading below the one it went out with",
        RETURN,
        _with_meter_below,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items.0.hourMeterIn": METER_BELOW},
    ),
    RentalRefusal(
        "return a unit with a meter reading below nought",
        RETURN,
        lambda stage: _return_as_admin(stage, lambda key: return_body(key, hourMeterIn=-1)),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.hourMeterIn"}),
    ),
    RentalRefusal(
        "return listing no unit",
        RETURN,
        lambda stage: take_back(stage.booking, stage.administrator, uuid4(), {"items": []}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items"}),
    ),
    RentalRefusal(
        "return with a condition that is not a grade",
        RETURN,
        lambda stage: _return_as_admin(stage, lambda key: return_body(key, conditionIn="D")),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.conditionIn"}),
    ),
    RentalRefusal(
        "return naming the tag of a unit, which the contract does not take",
        RETURN,
        lambda stage: _return_as_admin(stage, lambda key: return_body(key, assetTag="TSH-1")),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.assetTag"}),
    ),
]

__all__ = ["RETURN_REFUSALS"]
