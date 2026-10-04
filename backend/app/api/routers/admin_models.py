"""The product models of the catalogue, kept by an administrator (FR-22, US-30, BR-44).

`GET /api/admin/models` answers one page of the models, published or not, by
name, narrowed by `q`, `categoryId` and `published`, each with how many units
the fleet holds of it. `GET /api/admin/models/{id}` answers one.

`POST /api/admin/models` creates a model, unpublished, and answers 201.
`PATCH /api/admin/models/{id}` changes the fields it names and never the SKU,
which is a 422 naming `sku` when it is sent. A duplicate SKU or slug, an
amount below zero, a weekly rate above seven days at the daily rate, a
shortest hire longer than the longest and a category that is switched off are
each a 422 naming the field.

`POST /api/admin/models/{id}/publication` with `{"published": true}` puts the
model in the public catalogue, and with false takes it out at once, from the
search, the availability search and the quote alike. Existing bookings of it
are left alone.

A rate, a deposit, a late fee or a replacement value changed here reaches the
next booking and never an existing reservation line or rental, which hold
their own copies (BR-20). The audit event records the figures before and after.

Every route is for an administrator alone, and every write reads the account
again under a row lock for the length of the change (`FreshAdminUser`).
Counter staff and customers are refused with 403.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.admin_catalogue_deps import (
    CreateModel,
    EditModel,
    PublishModel,
    ReadAdminCatalogueDependency,
)
from app.api.admin_catalogue_presenter import (
    CATALOGUE_TAG,
    ModelPathKey,
    model_changes,
    model_page_response,
    model_response,
    model_terms,
)
from app.api.admin_catalogue_schemas import (
    UNKNOWN_MODEL_RESPONSE,
    AdminModelPageResponse,
    AdminModelResponse,
    ModelCreateRequest,
    ModelUpdateRequest,
    PublicationRequest,
)
from app.api.admin_presenter import ADMIN_PREFIX
from app.api.booking_deps import actor_of
from app.api.catalogue_deps import SearchText
from app.api.deps import AdminUser
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.admin_commands import (
    EditModelCommand,
    NewModelCommand,
    PublicationCommand,
)
from app.application.catalogue.admin_read_models import AdminModelSearch

router = APIRouter(prefix=ADMIN_PREFIX, tags=[CATALOGUE_TAG])

WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_MODEL_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
}


@router.get(
    "/models",
    response_model=AdminModelPageResponse,
    summary="Return one page of the product models, published or not, by name",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_models(
    user: AdminUser,
    reads: ReadAdminCatalogueDependency,
    q: Annotated[
        SearchText | None,
        Query(description="Free text matched against SKU, name, manufacturer and model number."),
    ] = None,
    category_id: Annotated[
        UUID | None, Query(alias="categoryId", description="Only the models of this category.")
    ] = None,
    published: Annotated[
        bool | None,
        Query(description="True for the published models only, false for the hidden ones."),
    ] = None,
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
) -> AdminModelPageResponse:
    """Return one page of the product models that match, by name."""
    search = AdminModelSearch(
        text=q, category_id=category_id, published=published, page=page, page_size=page_size
    )
    return model_page_response(reads.models(actor_of(user), search))


@router.get(
    "/models/{id}",
    response_model=AdminModelResponse,
    summary="Return one product model, published or not",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_MODEL_RESPONSE,
    },
)
def read_model(
    model_id: ModelPathKey, user: AdminUser, reads: ReadAdminCatalogueDependency
) -> AdminModelResponse:
    """Return the product model.

    Raises:
        NotFound: If there is no such model. HTTP 404.

    """
    return model_response(reads.model(actor_of(user), model_id))


@router.post(
    "/models",
    response_model=AdminModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product model, unpublished",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_model(
    payload: ModelCreateRequest, user: FreshAdminUser, use_case: CreateModel
) -> AdminModelResponse:
    """Create the model and record it, in one transaction.

    Raises:
        ValidationFailure: If a field breaks a rule, the category is unknown
            or switched off, or the SKU or slug is taken. HTTP 422, naming
            the field.

    """
    command = NewModelCommand(actor=actor_of(user), terms=model_terms(payload))
    return model_response(use_case.execute(command))


@router.patch(
    "/models/{id}",
    response_model=AdminModelResponse,
    summary="Change the fields of a product model that are sent, never its SKU",
    responses=WRITE_RESPONSES,
)
def patch_model(
    model_id: ModelPathKey, payload: ModelUpdateRequest, user: FreshAdminUser, use_case: EditModel
) -> AdminModelResponse:
    """Change the fields that were sent and record the figures before and after.

    Raises:
        NotFound: If there is no such model. HTTP 404.
        ValidationFailure: As for a creation, and when the SKU is sent. HTTP
            422, naming the field.

    """
    command = EditModelCommand(
        actor=actor_of(user), model_id=model_id, changes=model_changes(payload)
    )
    return model_response(use_case.execute(command))


@router.post(
    "/models/{id}/publication",
    response_model=AdminModelResponse,
    summary="Publish a product model, or take it out of the public catalogue",
    responses=WRITE_RESPONSES,
)
def post_publication(
    model_id: ModelPathKey,
    payload: PublicationRequest,
    user: FreshAdminUser,
    use_case: PublishModel,
) -> AdminModelResponse:
    """Publish or hide the model and record it, in one transaction.

    Raises:
        NotFound: If there is no such model. HTTP 404.

    """
    command = PublicationCommand(
        actor=actor_of(user), model_id=model_id, published=payload.published
    )
    return model_response(use_case.execute(command))
