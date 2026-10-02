"""The two profile endpoints, for a customer and nobody else (US-05, C-26).

`GET /api/me/profile` returns the caller's own details. `PATCH /api/me/profile`
changes the contact and billing fields that were sent and returns the profile
as it now is.

The profile is found by the account that is signed in. Nothing in the request
names it, so there is no key to guess. An account with no customer profile is
answered 404.

The body of an edit refuses any field that is not one of the eight a customer
may change, with a 422 that names it. A submitted `accountStatus`, `role` or
`tradeDiscountPercent` therefore never reaches the database.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.api.account_deps import ReadProfile, UpdateProfile
from app.api.account_schemas import (
    NO_PROFILE_RESPONSE,
    REFUSED_BODY_RESPONSE,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.api.booking_deps import actor_of
from app.api.deps import CustomerUser
from app.application.identity.profile import ReadProfileQuery, UpdateProfileCommand

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["identity"])


@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Return the signed in customer's own details",
    responses={status.HTTP_404_NOT_FOUND: NO_PROFILE_RESPONSE},
)
def read_profile(user: CustomerUser, use_case: ReadProfile) -> ProfileResponse:
    """Return the caller's profile and the account behind it.

    Raises:
        NotFound: If the account has no customer profile. HTTP 404.

    """
    details = use_case.execute(ReadProfileQuery(actor=actor_of(user)))
    return ProfileResponse.model_validate(details)


@router.patch(
    "/profile",
    response_model=ProfileResponse,
    summary="Change the signed in customer's contact and billing details",
    responses={
        status.HTTP_404_NOT_FOUND: NO_PROFILE_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def patch_profile(
    payload: ProfileUpdateRequest, user: CustomerUser, use_case: UpdateProfile
) -> ProfileResponse:
    """Change the fields that were sent, all of them or none.

    Raises:
        NotFound: If the account has no customer profile. HTTP 404.
        ValidationFailure: If a field is refused. HTTP 422, naming the field.

    """
    actor = actor_of(user)
    details = use_case.execute(
        UpdateProfileCommand(actor=actor, changes=payload.model_dump(exclude_unset=True))
    )
    return ProfileResponse.model_validate(details)
