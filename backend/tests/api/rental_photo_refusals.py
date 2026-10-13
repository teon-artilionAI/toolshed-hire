"""The refusals of the two routes that show a customer the damage photographs of a hire.

Both are for the customer alone. Nobody signed out is answered 401 and staff
are answered 403, and a hire or a photograph the customer cannot reach is a 404
in the words used for one that does not exist. Another customer's hire, which
answers the same, is in tests/api/test_my_damage_photos.py. What a case is made
of is in `rental_refusal_cases`.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from fastapi import status

from app.application.hire.damage_photo_reads import PHOTO_NOT_FOUND_MESSAGE
from tests.api.rental_refusal_cases import NO_SUCH_RENTAL, RentalRefusal, out_on_hire
from tests.api.reservation_refusal_cases import ANONYMOUS, FORBIDDEN_ROLE, NOT_FOUND
from tests.support.photo_api import my_photo_link, my_photos

MY_PHOTOS: Final[str] = "GET /api/me/rentals/{id}/damage-photos"
MY_PHOTO: Final[str] = "GET /api/me/rentals/{id}/damage-photos/{photoId}"

PHOTO_REFUSALS: Final[list[RentalRefusal]] = [
    RentalRefusal(
        "list the photographs of a hire with no credential",
        MY_PHOTOS,
        lambda stage: my_photos(stage.booking, None, uuid4()),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    RentalRefusal(
        "list the photographs of a hire as staff",
        MY_PHOTOS,
        lambda stage: my_photos(stage.booking, stage.administrator, uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "list the photographs of a hire that does not exist",
        MY_PHOTOS,
        lambda stage: my_photos(stage.booking, stage.world.customer, uuid4()),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RENTAL,
    ),
    RentalRefusal(
        "open a photograph of a hire with no credential",
        MY_PHOTO,
        lambda stage: my_photo_link(stage.booking, None, uuid4(), uuid4()),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    RentalRefusal(
        "open a photograph of a hire as staff",
        MY_PHOTO,
        lambda stage: my_photo_link(stage.booking, stage.administrator, uuid4(), uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "open a photograph the customer's own hire does not hold",
        MY_PHOTO,
        lambda stage: my_photo_link(
            stage.booking, stage.world.customer, out_on_hire(stage)["id"], uuid4()
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        PHOTO_NOT_FOUND_MESSAGE,
    ),
]

__all__ = ["PHOTO_REFUSALS"]
