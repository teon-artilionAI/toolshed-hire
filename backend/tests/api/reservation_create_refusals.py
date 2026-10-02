"""The refusals of creating a draft, as data.

`POST /api/reservations` can refuse a body the framework cannot read, a field
a rule does not accept, a caller who may not book for the customer named and a
customer who may not book at all. Each is a case here. What a case is made of
is in `reservation_refusal_cases`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from app.domain.period import BookingPeriod
from tests.api.reservation_refusal_cases import (
    ACCOUNT_ON_HOLD,
    ANONYMOUS,
    BRANCH_SCOPE,
    CREATE,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    NOT_ACCEPTED,
    ON_HOLD,
    OTHER_BRANCH,
    Refusal,
    Stage,
)
from tests.support.booking_api import FIRST_HIRE, RESERVATIONS_PATH

NO_SUCH_TOOL: Final[str] = "We could not find that tool. Browse the catalogue to choose another."
NO_SUCH_BRANCH: Final[str] = (
    "We do not have a branch with that code. Choose a branch from the list."
)
NOTES_TOO_LONG: Final[int] = 1001
YESTERDAY: Final[str] = "2026-03-01"
BEYOND_THE_HORIZON: Final[str] = "2026-06-01"


def _body(stage: Stage, **changes: object) -> dict[str, object]:
    """Return the world's draft body with some members replaced."""
    return {**stage.world.payload(), **changes}


def _line(stage: Stage, **changes: object) -> dict[str, object]:
    """Return one line for the world's model with some members replaced."""
    return {"modelSlug": stage.world.product_model.slug, "quantity": 1, **changes}


def _shorten_the_longest_hire(stage: Stage) -> Response:
    """Let the model be hired for two days at most, then ask for three."""
    stage.world.product_model.max_hire_days = 2
    stage.session.add(stage.world.product_model)
    stage.session.commit()
    return stage.post(_body(stage))


def _post_while_on_hold(stage: Stage) -> Response:
    """Put the customer on hold, then ask for a draft."""
    stage.put_customer_on_hold()
    return stage.post(_body(stage))


def _twenty_nine_days(stage: Stage) -> Response:
    """Ask for a hire of twenty nine days."""
    period = BookingPeriod(FIRST_HIRE.start, FIRST_HIRE.start + timedelta(days=28))
    return stage.post(_body(stage, to=(period.end + timedelta(days=1)).isoformat()))


CREATE_REFUSALS: Final[list[Refusal]] = [
    Refusal(
        "create with an empty body",
        CREATE,
        lambda stage: stage.post({}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.branchCode", "body.from", "body.to", "body.lines"}),
    ),
    Refusal(
        "create with a start that is not a date",
        CREATE,
        lambda stage: stage.post(_body(stage, **{"from": "next Monday"})),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.from"}),
    ),
    Refusal(
        "create with no lines",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.lines"}),
    ),
    Refusal(
        "create with a quantity of nought",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[_line(stage, quantity=0)])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.lines.0.quantity"}),
    ),
    Refusal(
        "create with a quantity of eleven",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[_line(stage, quantity=11)])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.lines.0.quantity"}),
    ),
    Refusal(
        "create with a blank model slug",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[_line(stage, modelSlug="  ")])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.lines.0.modelSlug"}),
    ),
    Refusal(
        "create with a customer profile that is not a key",
        CREATE,
        lambda stage: stage.post(_body(stage, customerProfileId="the Dlamini account")),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.customerProfileId"}),
    ),
    Refusal(
        "create with notes that are too long",
        CREATE,
        lambda stage: stage.post(_body(stage, notes="x" * NOTES_TOO_LONG)),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.notes"}),
    ),
    Refusal(
        "create with a return on the start date",
        CREATE,
        lambda stage: stage.post(_body(stage, to=FIRST_HIRE.start.isoformat())),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.to": "The return date has to be after the start date."},
    ),
    Refusal(
        "create for twenty nine days",
        CREATE,
        _twenty_nine_days,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.to": "A hire can be at most 28 days."},
    ),
    Refusal(
        "create starting yesterday",
        CREATE,
        lambda stage: stage.post(_body(stage, **{"from": YESTERDAY})),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.from": "The hire has to start today or later."},
    ),
    Refusal(
        "create starting beyond the horizon",
        CREATE,
        lambda stage: stage.post(_body(stage, **{"from": BEYOND_THE_HORIZON, "to": "2026-06-03"})),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.from": "A hire can start at most 90 days from today."},
    ),
    Refusal(
        "create for longer than the model allows",
        CREATE,
        _shorten_the_longest_hire,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.to": "GBH 2-26 DRE Rotary Hammer can be hired for at most 2 days."},
    ),
    Refusal(
        "create at a branch that does not exist",
        CREATE,
        lambda stage: stage.post(_body(stage, branchCode="XYZ")),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.branchCode": NO_SUCH_BRANCH},
    ),
    Refusal(
        "create with a model nobody can see",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[_line(stage, modelSlug="no-such-model")])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.lines.0.modelSlug": NO_SUCH_TOOL},
    ),
    Refusal(
        "create with one model twice",
        CREATE,
        lambda stage: stage.post(_body(stage, lines=[_line(stage), _line(stage)])),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={
            "body.lines.1.modelSlug": (
                "Each tool can appear once in a reservation. Change the quantity instead."
            )
        },
    ),
    Refusal(
        "create as staff with no customer named",
        CREATE,
        lambda stage: stage.post(_body(stage), stage.administrator),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.customerProfileId": "Choose the customer this reservation is for."},
    ),
    Refusal(
        "create as staff for a customer that does not exist",
        CREATE,
        lambda stage: stage.post(
            _body(stage, customerProfileId=str(uuid4())), stage.administrator
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={
            "body.customerProfileId": (
                "We could not find that customer. Choose a customer from the list."
            )
        },
    ),
    Refusal(
        "create as a customer who names a profile",
        CREATE,
        lambda stage: stage.post(_body(stage, customerProfileId=str(stage.world.profile.id))),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
        "Only a member of staff can make a reservation for another customer.",
    ),
    Refusal(
        "create as counter staff of another branch",
        CREATE,
        lambda stage: stage.post(
            _body(stage, customerProfileId=str(stage.world.profile.id)),
            stage.assistant_elsewhere,
        ),
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    Refusal(
        "create for a customer who is on hold",
        CREATE,
        _post_while_on_hold,
        status.HTTP_403_FORBIDDEN,
        ON_HOLD,
        ACCOUNT_ON_HOLD,
    ),
    Refusal(
        "create with no credential",
        CREATE,
        lambda stage: stage.booking.client.post(RESERVATIONS_PATH, json=_body(stage)),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
]
