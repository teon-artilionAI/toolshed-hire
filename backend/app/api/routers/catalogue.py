"""The catalogue endpoints, which are FR-02.

Public by declaration. A visitor browses the categories, lists the published
models and opens one model with no account. Only published models are ever
returned, and a model that is not published answers 404 exactly as a slug
nobody used does.

The router does no work of its own beyond the HTTP boundary. It reads the query
string, hands it to the browsing service and shapes what comes back. The
service arrives already wired to its query object.

A catalogue response is the same for every visitor, so it may be cached for a
minute.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.catalogue_deps import BrowseCatalogueDependency, ModelSearchParameters, cache_briefly
from app.api.catalogue_schemas import (
    REFUSED_QUERY_RESPONSE,
    UNKNOWN_MODEL_RESPONSE,
    CategoryListResponse,
    CategoryResponse,
    ModelDetailResponse,
    ModelPageResponse,
    ModelSummaryResponse,
)
from app.api.deps import public_access

router = APIRouter(
    prefix="/catalogue", tags=["catalogue"], dependencies=[Depends(public_access)]
)


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    summary="List the catalogue categories",
    dependencies=[Depends(cache_briefly)],
)
def list_categories(catalogue: BrowseCatalogueDependency) -> CategoryListResponse:
    """Return every active category, each parent followed by its children.

    `modelCount` counts the published models of a category, and for a parent
    it includes the models of its children.
    """
    return CategoryListResponse(
        items=[CategoryResponse.model_validate(entry) for entry in catalogue.categories()]
    )


@router.get(
    "/models",
    response_model=ModelPageResponse,
    summary="List the published models",
    dependencies=[Depends(cache_briefly)],
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE},
)
def list_models(
    search: ModelSearchParameters, catalogue: BrowseCatalogueDependency
) -> ModelPageResponse:
    """Return one page of the published models that match the query.

    Raises:
        ValidationFailure: If the category is unknown. Mapped to HTTP 422.

    """
    page = catalogue.models(search)
    return ModelPageResponse(
        items=[ModelSummaryResponse.model_validate(item) for item in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


@router.get(
    "/models/{slug}",
    response_model=ModelDetailResponse,
    summary="Return one published model",
    dependencies=[Depends(cache_briefly)],
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_MODEL_RESPONSE},
)
def read_model(slug: str, catalogue: BrowseCatalogueDependency) -> ModelDetailResponse:
    """Return the published model with this slug.

    Raises:
        NotFound: If no published model carries the slug. Mapped to HTTP 404.

    """
    return ModelDetailResponse.model_validate(catalogue.model(slug))
