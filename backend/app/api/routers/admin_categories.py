"""The categories of the catalogue, kept by an administrator (FR-22, BR-44).

`GET /api/admin/categories` answers every category, switched off or not, each
top level category followed by its children, with how many product models each
classifies itself, published or not. It is one page of up to a hundred unless
another page is asked for, so every category of a catalogue this size arrives
at once.

`POST /api/admin/categories` creates a category, active, and answers 201.
`PATCH /api/admin/categories/{id}` changes the fields it names, `isActive`
among them, and answers 200. Nesting stops at two levels, so a parent has to
be a top level category, and a category with children cannot be put under
another one, each a 422 naming `parentCategoryId`. A code or a slug another
category holds is a 422 naming that field. Nothing is ever deleted, so there
is no DELETE route. A category leaves the catalogue by being switched off.

Every route is for an administrator alone, and every write reads the account
again under a row lock for the length of the change (`FreshAdminUser`).
Counter staff and customers are refused with 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.admin_catalogue_deps import CreateCategory, EditCategory, ReadAdminCatalogueDependency
from app.api.admin_catalogue_presenter import (
    CATALOGUE_TAG,
    CategoryPathKey,
    category_changes,
    category_page_response,
    category_response,
)
from app.api.admin_catalogue_schemas import (
    UNKNOWN_CATEGORY_RESPONSE,
    AdminCategoryPageResponse,
    AdminCategoryResponse,
    CategoryCreateRequest,
    CategoryUpdateRequest,
)
from app.api.admin_presenter import ADMIN_PREFIX
from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.admin_commands import EditCategoryCommand, NewCategoryCommand
from app.application.catalogue.admin_read_models import CATEGORY_PAGE_SIZE, AdminCategorySearch

router = APIRouter(prefix=ADMIN_PREFIX, tags=[CATALOGUE_TAG])


@router.get(
    "/categories",
    response_model=AdminCategoryPageResponse,
    summary="Return every category, active or not, each parent followed by its children",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_categories(
    user: AdminUser,
    reads: ReadAdminCatalogueDependency,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many categories a page holds. Every category fits the default.",
        ),
    ] = CATEGORY_PAGE_SIZE,
) -> AdminCategoryPageResponse:
    """Return one page of every category, each parent followed by its children."""
    search = AdminCategorySearch(page=page, page_size=page_size)
    return category_page_response(reads.categories(actor_of(user), search))


@router.post(
    "/categories",
    response_model=AdminCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category, active",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_category(
    payload: CategoryCreateRequest, user: FreshAdminUser, use_case: CreateCategory
) -> AdminCategoryResponse:
    """Create the category and record it, in one transaction.

    Raises:
        ValidationFailure: If a field breaks a rule, the parent is unknown or
            not at the top, or the code or slug is taken. HTTP 422, naming
            the field.

    """
    command = NewCategoryCommand(
        actor=actor_of(user),
        code=payload.code,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        parent_category_id=payload.parent_category_id,
        sort_order=payload.sort_order,
    )
    return category_response(use_case.execute(command))


@router.patch(
    "/categories/{id}",
    response_model=AdminCategoryResponse,
    summary="Change the fields of a category that are sent, or switch it off",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_CATEGORY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def patch_category(
    category_id: CategoryPathKey,
    payload: CategoryUpdateRequest,
    user: FreshAdminUser,
    use_case: EditCategory,
) -> AdminCategoryResponse:
    """Change the fields that were sent and record what changed, in one transaction.

    Raises:
        NotFound: If there is no such category. HTTP 404.
        ValidationFailure: As for a creation, and when the category has
            children and is to be put under another. HTTP 422, naming the field.

    """
    command = EditCategoryCommand(
        actor=actor_of(user), category_id=category_id, changes=category_changes(payload)
    )
    return category_response(use_case.execute(command))
