"""The rental read, which is the counter's view of a hire once it has gone out.

`GET /api/rentals/{id}` returns one rental with its items and its charges, for
counter staff and administrators at any branch. `{id}` is the key of the
rental or its reference. One that does not exist is answered 404.

The routes that return items, settle a balance and list rentals come with the
changes after this one.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.booking_deps import actor_of
from app.api.deps import CounterUser
from app.api.hire_deps import ReadRentalsDependency
from app.api.hire_presenter import (
    HIRE_TAG,
    READ_RENTAL_ROUTE_NAME,
    RENTALS_PREFIX,
    RentalPathKey,
    rental_response,
)
from app.api.hire_schemas import UNKNOWN_RENTAL_RESPONSE, RentalResponse
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import RentalCommand

router = APIRouter(prefix=RENTALS_PREFIX, tags=[HIRE_TAG])


@router.get(
    "/{id}",
    name=READ_RENTAL_ROUTE_NAME,
    response_model=RentalResponse,
    summary="Return one rental, by its key or its reference",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_RENTAL_RESPONSE},
)
def read_rental(
    rental_key: RentalPathKey, user: CounterUser, reads: ReadRentalsDependency
) -> RentalResponse:
    """Return the rental, or 404 when it does not exist.

    Raises:
        NotFound: If there is no such rental. HTTP 404.

    """
    command = RentalCommand(actor=actor_of(user), key=RentalKey.parse(rental_key))
    return rental_response(reads.one(command))
