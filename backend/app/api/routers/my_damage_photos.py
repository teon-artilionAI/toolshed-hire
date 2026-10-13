"""The photographs of damage on the customer's own hire, which is the customer's half of #112.

`GET /api/me/rentals/{id}/damage-photos` lists the photographs of every damage
report filed against the signed in customer's hire, oldest first, because they
are the evidence for what was kept back from the deposit.
`GET /api/me/rentals/{id}/damage-photos/{photoId}` answers with a link that
opens one of them for five minutes, as a download.

Both are for customers only. The customer goes into the query, so another
customer's hire, or a photograph on it, is a 404 in the same words as one that
does not exist (BR-42), and a caller who is not signed in is a 401. Both answer
503 while photographs are switched off.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Path, status

from app.api.booking_deps import actor_of
from app.api.damage_photo_deps import PhotosSwitchedOn, ReadMyDamagePhotosDependency
from app.api.damage_photo_presenter import PhotoPathKey, link_response, photo_list_response
from app.api.damage_photo_schemas import (
    PHOTOS_SWITCHED_OFF_RESPONSE,
    UNKNOWN_HIRE_PHOTO_RESPONSE,
    DamagePhotoListResponse,
    PhotoLinkResponse,
)
from app.api.deps import CustomerUser
from app.api.hire_presenter import HIRE_TAG

MY_DAMAGE_PHOTOS_PATH: Final[str] = "/me/rentals/{id}/damage-photos"

router = APIRouter(tags=[HIRE_TAG])

RentalPathKey = Annotated[UUID, Path(alias="id", description="The key of the customer's hire.")]


@router.get(
    MY_DAMAGE_PHOTOS_PATH,
    response_model=DamagePhotoListResponse,
    summary="List the damage photographs on the signed in customer's own hire",
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_HIRE_PHOTO_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: PHOTOS_SWITCHED_OFF_RESPONSE,
    },
)
def list_my_damage_photos(
    rental_id: RentalPathKey,
    user: CustomerUser,
    _switched_on: PhotosSwitchedOn,
    reads: ReadMyDamagePhotosDependency,
) -> DamagePhotoListResponse:
    """Return the photographs of every damage report on the hire.

    Raises:
        NotFound: If the hire does not exist or is not the caller's. HTTP 404.
        FeatureSwitchedOff: If photographs are switched off. HTTP 503.

    """
    return photo_list_response(reads.of_rental(actor_of(user), rental_id))


@router.get(
    f"{MY_DAMAGE_PHOTOS_PATH}/{{photoId}}",
    response_model=PhotoLinkResponse,
    summary="Return a five minute link that opens one damage photograph on the customer's hire",
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_HIRE_PHOTO_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: PHOTOS_SWITCHED_OFF_RESPONSE,
    },
)
def read_my_damage_photo_link(
    rental_id: RentalPathKey,
    photo_id: PhotoPathKey,
    user: CustomerUser,
    _switched_on: PhotosSwitchedOn,
    reads: ReadMyDamagePhotosDependency,
) -> PhotoLinkResponse:
    """Return a signed link to the photograph, served as a download.

    Raises:
        NotFound: If the hire is not the caller's or holds no such photograph. HTTP 404.
        FeatureSwitchedOff: If photographs are switched off. HTTP 503.

    """
    return link_response(reads.link(actor_of(user), rental_id, photo_id))
