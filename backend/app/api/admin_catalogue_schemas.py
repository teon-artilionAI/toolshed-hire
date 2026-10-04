"""Request and response models of the admin catalogue, `AdminCategory` and `AdminModel`.

Field names on the wire are camelCase, as everywhere else at this boundary.
Money is a string with two decimals, both ways, so no amount passes through a
float. A request may carry a minus sign, so the rule that an amount is zero or
more answers in its own sentence. An instant is ISO 8601 with the offset of
Cape Town, and a list is `{"items": [...], "page": 1, "pageSize": 20,
"total": 0}`.

A creation names its fields and an edit names any of them. A field an edit
leaves out keeps its value. A field it sends as null is cleared, which only
`description`, `parentCategoryId` and `longDescription` allow. Any other
field sent as null is refused, naming it. Every body refuses a field it does
not know, so an edit that sends the SKU of a model, which never changes, is
refused naming `sku`.

The widths are those of the columns. A code and a SKU are capital letters and
digits, a slug small letters and digits, each in words joined by single
hyphens, which the domain checks and says in a sentence.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Final
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from app.api.account_schemas import StrictRequest
from app.api.admin_schemas import SIGNED_MONEY_PATTERN
from app.api.catalogue_schemas import Money
from app.api.reservation_schemas import Timestamp
from app.api.schemas import CamelModel, ProblemDetail
from app.domain import catalogue_entry_rules as model_rules
from app.domain import category_rules

# The longest text a description may be. The columns are TEXT, and these keep
# one request from storing a book.
DESCRIPTION_MAX_LENGTH: Final[int] = 2000
LONG_DESCRIPTION_MAX_LENGTH: Final[int] = 4000
NOT_EMPTY_MESSAGE: Final[str] = "This cannot be empty. Leave it out to keep what it holds."
STARTS_UNPUBLISHED_MESSAGE: Final[str] = (
    "A new model starts unpublished. Publish it once it is ready."
)

MoneyText = Annotated[str, StringConstraints(strip_whitespace=True, pattern=SIGNED_MONEY_PATTERN)]
CodeText = Annotated[str, Field(max_length=category_rules.CODE_MAX_LENGTH)]
CategoryNameText = Annotated[str, Field(max_length=category_rules.NAME_MAX_LENGTH)]
CategorySlugText = Annotated[str, Field(max_length=category_rules.SLUG_MAX_LENGTH)]
DescriptionText = Annotated[str, Field(max_length=DESCRIPTION_MAX_LENGTH)]
SkuText = Annotated[str, Field(max_length=model_rules.SKU_MAX_LENGTH)]
ModelNameText = Annotated[str, Field(max_length=model_rules.NAME_MAX_LENGTH)]
ModelSlugText = Annotated[str, Field(max_length=model_rules.SLUG_MAX_LENGTH)]
ManufacturerText = Annotated[str, Field(max_length=model_rules.MANUFACTURER_MAX_LENGTH)]
ModelNumberText = Annotated[str, Field(max_length=model_rules.MODEL_NUMBER_MAX_LENGTH)]
ShortDescriptionText = Annotated[
    str, Field(max_length=model_rules.SHORT_DESCRIPTION_MAX_LENGTH)
]
LongDescriptionText = Annotated[str, Field(max_length=LONG_DESCRIPTION_MAX_LENGTH)]

UNKNOWN_CATEGORY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such category.",
}
UNKNOWN_MODEL_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such product model.",
}


def refuse_null(value: object) -> object:
    """Refuse null for a field that may not be empty, so an edit cannot blank it.

    Raises:
        ValueError: If the value is null.

    """
    if value is None:
        raise ValueError(NOT_EMPTY_MESSAGE)
    return value


class CategoryCreateRequest(StrictRequest):
    """A new category. It starts active, at the top unless a parent is named."""

    code: CodeText
    name: CategoryNameText
    slug: CategorySlugText
    description: DescriptionText | None = None
    parent_category_id: UUID | None = Field(default=None, validation_alias="parentCategoryId")
    sort_order: int = Field(
        default=category_rules.DEFAULT_SORT_ORDER, validation_alias="sortOrder"
    )


class CategoryUpdateRequest(StrictRequest):
    """The fields of a category to change, any of them, and whether it is active."""

    code: CodeText | None = None
    name: CategoryNameText | None = None
    slug: CategorySlugText | None = None
    description: DescriptionText | None = None
    parent_category_id: UUID | None = Field(default=None, validation_alias="parentCategoryId")
    sort_order: int | None = Field(default=None, validation_alias="sortOrder")
    is_active: bool | None = Field(default=None, validation_alias="isActive")

    @field_validator("code", "name", "slug", "sort_order", "is_active", mode="before")
    @classmethod
    def not_null(cls, value: object) -> object:
        """Refuse null for a field of a category that may not be empty."""
        return refuse_null(value)


class ModelCreateRequest(StrictRequest):
    """A new product model, with every figure a booking will copy. It starts unpublished."""

    sku: SkuText
    name: ModelNameText
    slug: ModelSlugText
    category_id: UUID = Field(validation_alias="categoryId")
    manufacturer: ManufacturerText
    model_number: ModelNumberText = Field(validation_alias="modelNumber")
    short_description: ShortDescriptionText = Field(validation_alias="shortDescription")
    long_description: LongDescriptionText | None = Field(
        default=None, validation_alias="longDescription"
    )
    daily_rate: MoneyText = Field(validation_alias="dailyRate")
    weekly_rate: MoneyText = Field(validation_alias="weeklyRate")
    deposit_amount: MoneyText = Field(validation_alias="depositAmount")
    late_fee_per_day: MoneyText = Field(validation_alias="lateFeePerDay")
    replacement_value: MoneyText = Field(validation_alias="replacementValue")
    min_hire_days: int = Field(validation_alias="minHireDays")
    max_hire_days: int = Field(validation_alias="maxHireDays")
    is_published: bool = Field(default=False, validation_alias="isPublished")

    model_config = ConfigDict(protected_namespaces=())

    @field_validator("is_published")
    @classmethod
    def starts_unpublished(cls, value: bool) -> bool:
        """Refuse a new model that asks to be published before anyone has looked at it."""
        if value:
            raise ValueError(STARTS_UNPUBLISHED_MESSAGE)
        return value


class ModelUpdateRequest(StrictRequest):
    """The fields of a product model to change, any of them but the SKU."""

    name: ModelNameText | None = None
    slug: ModelSlugText | None = None
    category_id: UUID | None = Field(default=None, validation_alias="categoryId")
    manufacturer: ManufacturerText | None = None
    model_number: ModelNumberText | None = Field(default=None, validation_alias="modelNumber")
    short_description: ShortDescriptionText | None = Field(
        default=None, validation_alias="shortDescription"
    )
    long_description: LongDescriptionText | None = Field(
        default=None, validation_alias="longDescription"
    )
    daily_rate: MoneyText | None = Field(default=None, validation_alias="dailyRate")
    weekly_rate: MoneyText | None = Field(default=None, validation_alias="weeklyRate")
    deposit_amount: MoneyText | None = Field(default=None, validation_alias="depositAmount")
    late_fee_per_day: MoneyText | None = Field(default=None, validation_alias="lateFeePerDay")
    replacement_value: MoneyText | None = Field(
        default=None, validation_alias="replacementValue"
    )
    min_hire_days: int | None = Field(default=None, validation_alias="minHireDays")
    max_hire_days: int | None = Field(default=None, validation_alias="maxHireDays")
    is_published: bool | None = Field(default=None, validation_alias="isPublished")

    model_config = ConfigDict(protected_namespaces=())

    @field_validator(
        "name",
        "slug",
        "category_id",
        "manufacturer",
        "model_number",
        "short_description",
        "daily_rate",
        "weekly_rate",
        "deposit_amount",
        "late_fee_per_day",
        "replacement_value",
        "min_hire_days",
        "max_hire_days",
        "is_published",
        mode="before",
    )
    @classmethod
    def not_null(cls, value: object) -> object:
        """Refuse null for a field of a model that may not be empty."""
        return refuse_null(value)


class PublicationRequest(StrictRequest):
    """Whether the model is to be in the public catalogue."""

    published: bool


class AdminCategoryResponse(CamelModel):
    """One category as the administrator sees it. `modelCount` counts its own models."""

    id: UUID
    code: str
    name: str
    slug: str
    description: str | None
    parent_category_id: UUID | None = Field(serialization_alias="parentCategoryId")
    parent_name: str | None = Field(serialization_alias="parentName")
    sort_order: int = Field(serialization_alias="sortOrder")
    is_active: bool = Field(serialization_alias="isActive")
    model_count: int = Field(serialization_alias="modelCount")

    model_config = ConfigDict(protected_namespaces=())


class AdminCategoryPageResponse(CamelModel):
    """Every category, active or not, each parent followed by its children."""

    items: list[AdminCategoryResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


class AdminModelResponse(CamelModel):
    """One product model as the administrator sees it, published or not.

    `assetCount` is every unit of the fleet that realises it, whatever its status.
    """

    id: UUID
    sku: str
    name: str
    slug: str
    category_id: UUID = Field(serialization_alias="categoryId")
    category_name: str = Field(serialization_alias="categoryName")
    manufacturer: str
    model_number: str = Field(serialization_alias="modelNumber")
    short_description: str = Field(serialization_alias="shortDescription")
    long_description: str | None = Field(serialization_alias="longDescription")
    daily_rate: Money = Field(serialization_alias="dailyRate")
    weekly_rate: Money = Field(serialization_alias="weeklyRate")
    deposit_amount: Money = Field(serialization_alias="depositAmount")
    late_fee_per_day: Money = Field(serialization_alias="lateFeePerDay")
    replacement_value: Money = Field(serialization_alias="replacementValue")
    min_hire_days: int = Field(serialization_alias="minHireDays")
    max_hire_days: int = Field(serialization_alias="maxHireDays")
    is_published: bool = Field(serialization_alias="isPublished")
    asset_count: int = Field(serialization_alias="assetCount")
    updated_at: Timestamp = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(protected_namespaces=())


class AdminModelPageResponse(CamelModel):
    """One page of the product models, by name."""

    items: list[AdminModelResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


def amount_of(text: str) -> Decimal:
    """Return an amount a request wrote as text, which its pattern already holds to digits."""
    return Decimal(text)


__all__ = [
    "AdminCategoryPageResponse",
    "AdminCategoryResponse",
    "AdminModelPageResponse",
    "AdminModelResponse",
    "CategoryCreateRequest",
    "CategoryUpdateRequest",
    "ModelCreateRequest",
    "ModelUpdateRequest",
    "PublicationRequest",
    "amount_of",
]
