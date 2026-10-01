"""Catalogue and fleet: Category, ProductModel and Asset.

This is the entity split the whole design rests on. ProductModel is what a
customer shops for. Asset is the individually tagged unit that is actually
allocated, collected and returned. Availability is allocation of specific
assets and never a quantity counter.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.domain.enums import (
    ASSET_STATUS_TYPE,
    CONDITION_GRADE_TYPE,
    AssetStatus,
    ConditionGrade,
)
from app.infrastructure.models.columns import (
    created_at_column,
    enum_column,
    flag,
    money,
    small_int,
    updated_at_column,
    uuid_fk,
    uuid_pk,
    varchar,
)

ASSET_TAG_MAX_LENGTH = 16
DEFAULT_MIN_HIRE_DAYS = 1
DEFAULT_MAX_HIRE_DAYS = 28


class Category(SQLModel, table=True):
    """The navigation and reporting grouping for the catalogue.

    One optional level of nesting and no deeper. The database stops a category
    parenting itself, and the cap of two levels is a domain rule.
    """

    __tablename__ = "category"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    code: str = Field(sa_column=varchar(16, unique=True))
    name: str = Field(sa_column=varchar(80))
    slug: str = Field(sa_column=varchar(80, unique=True))
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    parent_category_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("category.id", nullable=True)
    )
    sort_order: int = Field(default=0, sa_column=small_int())
    is_active: bool = Field(default=True, sa_column=flag(default=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class ProductModel(SQLModel, table=True):
    """A catalogue entry. Never hired directly, only realised by Assets."""

    __tablename__ = "product_model"
    # pydantic reserves the `model_` prefix for its own methods and warns about
    # any field that uses it. `model_number` is the documented column name and
    # collides with nothing, so the reservation is lifted for this one class.
    model_config = {"protected_namespaces": ()}

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    sku: str = Field(sa_column=varchar(24, unique=True))
    name: str = Field(sa_column=varchar(120))
    slug: str = Field(sa_column=varchar(140, unique=True))
    category_id: UUID = Field(sa_column=uuid_fk("category.id"))
    manufacturer: str = Field(sa_column=varchar(80))
    model_number: str = Field(sa_column=varchar(60))
    short_description: str = Field(sa_column=varchar(300))
    long_description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Rates exclude VAT. The weekly rate is what the taper policy charges for
    # each complete seven days (BR-21).
    daily_rate: Decimal = Field(sa_column=money())
    weekly_rate: Decimal = Field(sa_column=money())
    deposit_amount: Decimal = Field(sa_column=money())
    late_fee_per_day: Decimal = Field(sa_column=money())
    # Caps damage recovery (BR-39).
    replacement_value: Decimal = Field(sa_column=money())
    min_hire_days: int = Field(
        default=DEFAULT_MIN_HIRE_DAYS, sa_column=small_int(default=str(DEFAULT_MIN_HIRE_DAYS))
    )
    max_hire_days: int = Field(
        default=DEFAULT_MAX_HIRE_DAYS, sa_column=small_int(default=str(DEFAULT_MAX_HIRE_DAYS))
    )
    image_path: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    is_published: bool = Field(default=False, sa_column=flag(default=False))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class Asset(SQLModel, table=True):
    """One individually tagged physical unit, for example TSH-DR-0042.

    The composite unique keys on (id, branch_id) and (id, product_model_id)
    exist so a child table can carry a composite foreign key. AssetAllocation
    uses the first, so the database itself refuses an allocation that claims a
    unit is at a branch where it is not.
    """

    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("id", "branch_id", name="uq_asset_id_branch"),
        UniqueConstraint("id", "product_model_id", name="uq_asset_id_product_model"),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    # Painted on the machine and immutable once assigned (BR-34).
    asset_tag: str = Field(sa_column=varchar(ASSET_TAG_MAX_LENGTH, unique=True))
    product_model_id: UUID = Field(sa_column=uuid_fk("product_model.id"))
    branch_id: UUID = Field(sa_column=uuid_fk("branch.id"))
    serial_number: str | None = Field(default=None, sa_column=varchar(60, nullable=True))
    status: AssetStatus = Field(sa_column=enum_column(AssetStatus, ASSET_STATUS_TYPE))
    condition_grade: ConditionGrade = Field(
        sa_column=enum_column(ConditionGrade, CONDITION_GRADE_TYPE)
    )
    acquired_on: date = Field(sa_column=Column(Date, nullable=False))
    acquisition_cost: Decimal = Field(sa_column=money())
    hour_meter_reading: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Set when, and only when, the status is RETIRED.
    retired_on: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())
