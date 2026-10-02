"""The availability endpoints, which are FR-03 and FR-04.

Public by declaration. A visitor asks where the catalogue is free for a period
before there is any account, which is the point of US-07.

Both answers are a boolean for each branch and nothing else. No asset tag, no
serial number and no count of units is in either response, and the response
models have no field one could travel in.

The period is half open. `to` is the day the equipment comes back, so a unit
returned on the twelfth is free for a hire that starts on the twelfth.

Neither answer may be cached. It is true when it is given and can be wrong a
second later, when somebody books.

The router does no work of its own beyond the HTTP boundary. The search service
owns the rules about the period, and every refusal it raises names the query
parameter it refused.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.catalogue_deps import (
    ModelSearchParameters,
    SearchAvailabilityDependency,
    never_cache,
)
from app.api.catalogue_schemas import (
    REFUSED_QUERY_RESPONSE,
    UNKNOWN_MODEL_RESPONSE,
    AvailabilityPageResponse,
    BranchAvailabilityResponse,
    ModelAvailabilityResponse,
    ModelAvailabilityRowResponse,
    ModelSummaryResponse,
)
from app.api.deps import public_access
from app.api.schemas import MAXIMUM_QUANTITY, MINIMUM_QUANTITY

router = APIRouter(
    prefix="/catalogue", tags=["availability"], dependencies=[Depends(public_access)]
)

FromDate = Annotated[date, Query(alias="from", description="The first day of the hire.")]
ToDate = Annotated[
    date,
    Query(alias="to", description="The day the equipment comes back. It is free again that day."),
]


@router.get(
    "/availability",
    response_model=AvailabilityPageResponse,
    summary="Search availability across the catalogue",
    dependencies=[Depends(never_cache)],
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE},
)
def search_availability(
    from_date: FromDate,
    to_date: ToDate,
    models: ModelSearchParameters,
    availability: SearchAvailabilityDependency,
    branch: Annotated[
        str | None,
        Query(description="A branch code. Only models free at this branch are listed."),
    ] = None,
) -> AvailabilityPageResponse:
    """Return one page of models with an answer from every active branch.

    Raises:
        ValidationFailure: If the period, the category or the branch is
            refused. Mapped to HTTP 422, naming the parameter.

    """
    page = availability.across_catalogue(from_date, to_date, models, branch)
    return AvailabilityPageResponse(
        from_date=page.period.start,
        to_date=page.period.end,
        hire_days=page.period.days,
        items=[
            ModelAvailabilityRowResponse(
                model=ModelSummaryResponse.model_validate(item.model),
                branches=[
                    BranchAvailabilityResponse.model_validate(answer) for answer in item.branches
                ],
            )
            for item in page.items
        ],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


@router.get(
    "/models/{slug}/availability",
    response_model=ModelAvailabilityResponse,
    summary="Return where one model is free",
    dependencies=[Depends(never_cache)],
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_MODEL_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_model_availability(
    slug: str,
    from_date: FromDate,
    to_date: ToDate,
    availability: SearchAvailabilityDependency,
    quantity: Annotated[
        int,
        Query(
            ge=MINIMUM_QUANTITY,
            le=MAXIMUM_QUANTITY,
            description="How many units are wanted at one branch.",
        ),
    ] = MINIMUM_QUANTITY,
) -> ModelAvailabilityResponse:
    """Return the branches where at least `quantity` units are free for the period.

    Raises:
        NotFound: If no published model carries the slug. Mapped to HTTP 404.
        ValidationFailure: If the period or the quantity is refused, or the
            period is outside the hire limits of the model. Mapped to HTTP 422.

    """
    answer = availability.for_model(slug, from_date, to_date, quantity)
    return ModelAvailabilityResponse(
        from_date=answer.period.start,
        to_date=answer.period.end,
        hire_days=answer.period.days,
        quantity=answer.quantity,
        branches=[
            BranchAvailabilityResponse.model_validate(branch) for branch in answer.branches
        ],
    )
