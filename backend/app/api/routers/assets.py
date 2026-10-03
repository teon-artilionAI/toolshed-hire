"""The asset locator, which is FR-15 and US-10.

`GET /api/assets/locator` finds units at every branch by part of the asset tag
or of the model name, for counter staff and administrators alike. It only
reads, so it is never scoped by branch (BR-43). The text is two to eighty
characters and a page holds one to fifty units, in tag order. A unit on hire
carries the day it is due back and the rental it is out on.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Query, status
from pydantic import StringConstraints

from app.api.booking_deps import actor_of
from app.api.counter_deps import LocateAssetsDependency
from app.api.counter_presenter import locator_response
from app.api.counter_schemas import AssetLocationPageResponse
from app.api.deps import CounterUser
from app.api.reservation_schemas import REFUSED_QUERY_RESPONSE
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.locator import (
    MAXIMUM_LOCATOR_SEARCH_LENGTH,
    MINIMUM_LOCATOR_SEARCH_LENGTH,
    AssetSearch,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE

ASSETS_PREFIX: Final[str] = "/assets"
# The module the locator belongs to, which is the catalogue and its fleet.
CATALOGUE_TAG: Final[str] = "catalogue"

router = APIRouter(prefix=ASSETS_PREFIX, tags=[CATALOGUE_TAG])

# Surrounding spaces are removed before the length is checked, so a search for
# two spaces is refused like any other search that is too short.
LocatorText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MINIMUM_LOCATOR_SEARCH_LENGTH,
        max_length=MAXIMUM_LOCATOR_SEARCH_LENGTH,
    ),
]


@router.get(
    "/locator",
    response_model=AssetLocationPageResponse,
    summary="Find units at every branch by tag or model name",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE},
)
def locate_assets(
    user: CounterUser,
    locator: LocateAssetsDependency,
    q: Annotated[LocatorText, Query(description="Part of an asset tag or of a model name.")],
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many units a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> AssetLocationPageResponse:
    """Return one page of the units the text matches, at every branch."""
    found = locator.search(
        actor_of(user), AssetSearch(text=q, page=page, page_size=page_size)
    )
    return locator_response(found)
