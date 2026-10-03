"""The dependencies of the public read side, which is the catalogue and availability.

Four things live here.

The first is the read side half of the composition root. `app/api/deps.py`
wires the use cases that write. This module wires the query objects that read,
and it is the only place that knows `SqlCatalogueQuery`, `SqlBranchDirectory`
and `SearchAvailabilityQuery` stand behind the three read ports. A read needs
no unit of work, because it writes nothing, so each query object is handed the
request scoped session and the request closes it. The availability search is
also handed the sweep that lapses expired holds, from `app/api/sweep_deps.py`,
and runs it before it answers (BR-13).

The second is the query string of a model search, which the model list and the
availability search share. The parameter names are the ones the contract uses,
`category`, `q`, `sort`, `page` and `pageSize`, so a refusal names the field a
screen has an input for.

The third is the hire period as a request spells it, `from` and `to`. The
availability routes and the quote route read it the same way.

The fourth is the two cache policies. A catalogue response is the same for
every visitor and changes rarely, so it may be kept for a minute. An
availability answer is out of date the moment somebody books, so it is never
stored. A request that carried a credential is answered `no-store` whatever is
set here, which the security headers middleware sees to.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from fastapi import Depends, Query, Response
from pydantic import StringConstraints

from app.api.catalogue_schemas import SORT_FROM_WIRE, ModelSortParameter
from app.api.deps import ClockDependency, SessionDependency
from app.api.security_headers import CACHE_CONTROL_HEADER, CACHE_CONTROL_NO_STORE_VALUE
from app.api.sweep_deps import ExpiredHoldSweeper
from app.application.availability.ports import AvailabilityQuery
from app.application.availability.search import SearchAvailability
from app.application.catalogue.browse import BrowseCatalogue
from app.application.catalogue.ports import CatalogueQuery
from app.application.catalogue.read_models import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MAXIMUM_SEARCH_LENGTH,
    MINIMUM_PAGE_SIZE,
    MINIMUM_SEARCH_LENGTH,
    ModelSearch,
)
from app.application.identity.ports import BranchDirectory
from app.infrastructure.availability_search import SearchAvailabilityQuery
from app.infrastructure.branch_directory import SqlBranchDirectory
from app.infrastructure.catalogue_query import SqlCatalogueQuery

PUBLIC_CACHE_SECONDS: Final[int] = 60
CACHE_CONTROL_PUBLIC_VALUE: Final[str] = f"public, max-age={PUBLIC_CACHE_SECONDS}"


def cache_briefly(response: Response) -> None:
    """Let a catalogue response be kept for a minute by any cache."""
    response.headers[CACHE_CONTROL_HEADER] = CACHE_CONTROL_PUBLIC_VALUE


def never_cache(response: Response) -> None:
    """Forbid any cache from keeping an availability answer."""
    response.headers[CACHE_CONTROL_HEADER] = CACHE_CONTROL_NO_STORE_VALUE


# Surrounding spaces are removed before the length is checked, so a search for
# two spaces is refused like any other search that is too short.
SearchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MINIMUM_SEARCH_LENGTH,
        max_length=MAXIMUM_SEARCH_LENGTH,
    ),
]


def model_search_parameters(
    category: Annotated[
        str | None,
        Query(description="A category slug. A parent category includes its children."),
    ] = None,
    q: Annotated[
        SearchText | None,
        Query(description="Free text matched against name, manufacturer and model number."),
    ] = None,
    sort: Annotated[
        ModelSortParameter, Query(description="The order of the list.")
    ] = ModelSortParameter.NAME,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many models a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> ModelSearch:
    """Read the query string of a model search into the application's own type."""
    return ModelSearch(
        category_slug=category,
        text=q,
        sort=SORT_FROM_WIRE[sort],
        page=page,
        page_size=page_size,
    )


ModelSearchParameters = Annotated[ModelSearch, Depends(model_search_parameters)]

# The period is half open. `to` is the day the equipment comes back.
FromDate = Annotated[date, Query(alias="from", description="The first day of the hire.")]
ToDate = Annotated[
    date,
    Query(alias="to", description="The day the equipment comes back. It is free again that day."),
]


# ---------------------------------------------------------------------------
# The read side of the composition root. Each function returns a port, and the
# body chooses the implementation behind it.
# ---------------------------------------------------------------------------


def get_branch_directory(session: SessionDependency) -> BranchDirectory:
    """Return the SQL branch directory over the request scoped session."""
    return SqlBranchDirectory(session)


BranchDirectoryDependency = Annotated[BranchDirectory, Depends(get_branch_directory)]


def get_catalogue_query(session: SessionDependency) -> CatalogueQuery:
    """Return the SQL catalogue query object over the request scoped session."""
    return SqlCatalogueQuery(session)


CatalogueQueryDependency = Annotated[CatalogueQuery, Depends(get_catalogue_query)]


def get_availability_query(session: SessionDependency) -> AvailabilityQuery:
    """Return the SQL availability query object over the request scoped session."""
    return SearchAvailabilityQuery(session)


AvailabilityQueryDependency = Annotated[AvailabilityQuery, Depends(get_availability_query)]


def get_browse_catalogue(catalogue: CatalogueQueryDependency) -> BrowseCatalogue:
    """Return the catalogue browsing service, wired to its query object."""
    return BrowseCatalogue(catalogue)


BrowseCatalogueDependency = Annotated[BrowseCatalogue, Depends(get_browse_catalogue)]


def get_search_availability(
    availability: AvailabilityQueryDependency,
    catalogue: CatalogueQueryDependency,
    branches: BranchDirectoryDependency,
    clock: ClockDependency,
    lapse_expired_holds: ExpiredHoldSweeper,
) -> SearchAvailability:
    """Return the availability search, wired to its query objects, its clock and the sweep."""
    return SearchAvailability(availability, catalogue, branches, clock, lapse_expired_holds)


SearchAvailabilityDependency = Annotated[SearchAvailability, Depends(get_search_availability)]
