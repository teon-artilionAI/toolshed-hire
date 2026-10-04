"""What the routes of the admin catalogue share, the path keys, the commands and the responses.

A request body becomes a command here and a read model becomes a response
here, once, so the two routers stay about their routes. Nothing is worked out
in it.

An edit becomes a set of `Change`s, one for each field the request named. The
fields a request named are the ones pydantic says were set, so a field left
out is told apart from a field sent as null. A field that may not be empty
cannot arrive as null, because its request model refuses that first.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Final
from uuid import UUID

from fastapi import Path
from pydantic import BaseModel

from app.api.admin_catalogue_schemas import (
    AdminCategoryPageResponse,
    AdminCategoryResponse,
    AdminModelPageResponse,
    AdminModelResponse,
    CategoryUpdateRequest,
    ModelCreateRequest,
    ModelUpdateRequest,
    amount_of,
)
from app.application.catalogue.admin_commands import CategoryChanges, Change, ModelChanges
from app.application.catalogue.admin_read_models import (
    AdminCategoryEntry,
    AdminCategoryPage,
    AdminModelEntry,
    AdminModelPage,
)
from app.domain import catalogue_entry_rules as model_fields
from app.domain import category_rules as category_fields
from app.domain.catalogue_entry_rules import ModelTerms

# The tag of both routers, which is the module they belong to.
CATALOGUE_TAG: Final[str] = "catalogue"

CategoryPathKey = Annotated[UUID, Path(alias="id", description="The key of the category.")]
ModelPathKey = Annotated[UUID, Path(alias="id", description="The key of the product model.")]


def sent[ValueT](request: BaseModel, field: str, value: ValueT | None) -> Change[ValueT] | None:
    """Return the change of a field that may not be empty, or None when the request left it out."""
    return Change(value) if field in request.model_fields_set and value is not None else None


def cleared_or_sent[ValueT](
    request: BaseModel, field: str, value: ValueT | None
) -> Change[ValueT | None] | None:
    """Return the change of a field that may be empty, null included, or None when left out."""
    return Change(value) if field in request.model_fields_set else None


def _amount(text: str | None) -> Decimal | None:
    """Return an amount a request may have left out."""
    return amount_of(text) if text is not None else None


def category_changes(request: CategoryUpdateRequest) -> CategoryChanges:
    """Return the fields of a category an edit named."""
    return CategoryChanges(
        code=sent(request, category_fields.CODE, request.code),
        name=sent(request, category_fields.NAME, request.name),
        slug=sent(request, category_fields.SLUG, request.slug),
        description=cleared_or_sent(request, category_fields.DESCRIPTION, request.description),
        parent_category_id=cleared_or_sent(
            request, category_fields.PARENT_CATEGORY_ID, request.parent_category_id
        ),
        sort_order=sent(request, category_fields.SORT_ORDER, request.sort_order),
        is_active=sent(request, category_fields.IS_ACTIVE, request.is_active),
    )


def model_terms(request: ModelCreateRequest) -> ModelTerms:
    """Return every field of a new product model."""
    return ModelTerms(
        sku=request.sku,
        name=request.name,
        slug=request.slug,
        category_id=request.category_id,
        manufacturer=request.manufacturer,
        model_number=request.model_number,
        short_description=request.short_description,
        long_description=request.long_description,
        daily_rate=amount_of(request.daily_rate),
        weekly_rate=amount_of(request.weekly_rate),
        deposit_amount=amount_of(request.deposit_amount),
        late_fee_per_day=amount_of(request.late_fee_per_day),
        replacement_value=amount_of(request.replacement_value),
        min_hire_days=request.min_hire_days,
        max_hire_days=request.max_hire_days,
    )


def model_changes(request: ModelUpdateRequest) -> ModelChanges:
    """Return the fields of a product model an edit named."""
    return ModelChanges(
        name=sent(request, model_fields.NAME, request.name),
        slug=sent(request, model_fields.SLUG, request.slug),
        category_id=sent(request, model_fields.CATEGORY_ID, request.category_id),
        manufacturer=sent(request, model_fields.MANUFACTURER, request.manufacturer),
        model_number=sent(request, model_fields.MODEL_NUMBER, request.model_number),
        short_description=sent(
            request, model_fields.SHORT_DESCRIPTION, request.short_description
        ),
        long_description=cleared_or_sent(
            request, model_fields.LONG_DESCRIPTION, request.long_description
        ),
        daily_rate=sent(request, model_fields.DAILY_RATE, _amount(request.daily_rate)),
        weekly_rate=sent(request, model_fields.WEEKLY_RATE, _amount(request.weekly_rate)),
        deposit_amount=sent(
            request, model_fields.DEPOSIT_AMOUNT, _amount(request.deposit_amount)
        ),
        late_fee_per_day=sent(
            request, model_fields.LATE_FEE_PER_DAY, _amount(request.late_fee_per_day)
        ),
        replacement_value=sent(
            request, model_fields.REPLACEMENT_VALUE, _amount(request.replacement_value)
        ),
        min_hire_days=sent(request, model_fields.MIN_HIRE_DAYS, request.min_hire_days),
        max_hire_days=sent(request, model_fields.MAX_HIRE_DAYS, request.max_hire_days),
        is_published=sent(request, model_fields.IS_PUBLISHED, request.is_published),
    )


def category_response(entry: AdminCategoryEntry) -> AdminCategoryResponse:
    """Write one category in the shape the contract gives `AdminCategory`."""
    return AdminCategoryResponse(
        id=entry.id,
        code=entry.code,
        name=entry.name,
        slug=entry.slug,
        description=entry.description,
        parent_category_id=entry.parent_category_id,
        parent_name=entry.parent_name,
        sort_order=entry.sort_order,
        is_active=entry.is_active,
        model_count=entry.model_count,
    )


def category_page_response(page: AdminCategoryPage) -> AdminCategoryPageResponse:
    """Write one page of the categories in the shape the contract gives a list."""
    return AdminCategoryPageResponse(
        items=[category_response(entry) for entry in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


def model_response(entry: AdminModelEntry) -> AdminModelResponse:
    """Write one product model in the shape the contract gives `AdminModel`."""
    return AdminModelResponse(
        id=entry.id,
        sku=entry.sku,
        name=entry.name,
        slug=entry.slug,
        category_id=entry.category_id,
        category_name=entry.category_name,
        manufacturer=entry.manufacturer,
        model_number=entry.model_number,
        short_description=entry.short_description,
        long_description=entry.long_description,
        daily_rate=entry.daily_rate,
        weekly_rate=entry.weekly_rate,
        deposit_amount=entry.deposit_amount,
        late_fee_per_day=entry.late_fee_per_day,
        replacement_value=entry.replacement_value,
        min_hire_days=entry.min_hire_days,
        max_hire_days=entry.max_hire_days,
        is_published=entry.is_published,
        asset_count=entry.asset_count,
        updated_at=entry.updated_at,
    )


def model_page_response(page: AdminModelPage) -> AdminModelPageResponse:
    """Write one page of the product models in the shape the contract gives a list."""
    return AdminModelPageResponse(
        items=[model_response(entry) for entry in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
