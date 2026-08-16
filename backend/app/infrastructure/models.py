"""SQLModel table classes for the walking skeleton.

Only the tables needed to prove the load bearing decisions are modelled:
identity and role, the branch, the catalogue split into ProductModel and Asset,
and the booking chain Reservation, ReservationLine and AssetAllocation. The
remaining entities in the canonical model are deliberately absent and are added
when the flow that needs them is built.

Two things are worth reading closely.

AssetAllocation stores plain `start_date` and `end_date` date columns. The
`daterange` is built inside the exclusion constraint expression rather than
being exposed as a range column, so ordinary queries and reports read normal
date columns and SQLModel stays simple.

Enum columns bind to native PostgreSQL enum types with `create_type=False`.
The types are created by the migration, which is also the only place tables are
created. `SQLModel.metadata.create_all` is never used against a real database.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

from app.domain.enums import (
    ALLOCATION_STATUS_TYPE,
    ASSET_STATUS_TYPE,
    CONDITION_GRADE_TYPE,
    RESERVATION_STATUS_TYPE,
    USER_ROLE_TYPE,
    AllocationStatus,
    AssetStatus,
    ConditionGrade,
    DomainEnum,
    ReservationStatus,
    UserRole,
)

MONEY_PRECISION = 12
MONEY_SCALE = 2
EMAIL_MAX_LENGTH = 254
REFERENCE_MAX_LENGTH = 16
ASSET_TAG_MAX_LENGTH = 16
BRANCH_CODE_MAX_LENGTH = 4


def _pk() -> Column[UUID]:
    """Return a fresh application generated UUID primary key column."""
    return Column(PGUUID(as_uuid=True), primary_key=True, nullable=False)


def _fk(target: str, *, nullable: bool = False) -> Column[UUID]:
    """Return a UUID foreign key column with ON DELETE RESTRICT.

    Nothing in Toolshed Hire is ever hard deleted (BR-51), so every foreign key
    restricts rather than cascades. A cascade would be a delete path by another
    name.
    """
    return Column(
        PGUUID(as_uuid=True),
        ForeignKey(target, ondelete="RESTRICT"),
        nullable=nullable,
    )


def _money(*, nullable: bool = False) -> Column[Decimal]:
    """Return a NUMERIC(12,2) column. Money is never floating point (BR-22)."""
    return Column(Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=nullable)


def _enum(
    python_enum: type[DomainEnum], type_name: str, *, nullable: bool = False
) -> Column[str]:
    """Return a column bound to an existing native PostgreSQL enum type."""
    return Column(
        ENUM(
            python_enum,
            name=type_name,
            create_type=False,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=nullable,
    )


def _flag(*, default: bool) -> Column[bool]:
    """Return a NOT NULL boolean column with a database side default."""
    return Column(
        Boolean,
        nullable=False,
        server_default=text("true") if default else text("false"),
    )


def _created_at() -> Column[datetime]:
    """Return the standard creation timestamp column, defaulted by the database."""
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Column[datetime]:
    """Return the standard update timestamp column, defaulted by the database."""
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Branch(SQLModel, table=True):
    """A physical trading location. There are exactly three."""

    __tablename__ = "branches"

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    code: str = Field(sa_column=Column(String(BRANCH_CODE_MAX_LENGTH), nullable=False, unique=True))
    name: str = Field(sa_column=Column(String(80), nullable=False))
    suburb: str = Field(sa_column=Column(String(80), nullable=False))
    city: str = Field(sa_column=Column(String(80), nullable=False))
    is_active: bool = Field(default=True, sa_column=_flag(default=True))
    created_at: datetime | None = Field(default=None, sa_column=_created_at())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at())


class UserAccount(SQLModel, table=True):
    """The sign in identity. Carries exactly one role and nothing about hires.

    The role stored here is the only authority on what the holder may do. A
    role claim inside a token is never trusted, because a token issued before a
    demotion would otherwise outlive the demotion.
    """

    __tablename__ = "user_accounts"

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    email: str = Field(sa_column=Column(CITEXT(), nullable=False, unique=True))
    password_hash: str = Field(sa_column=Column(String(120), nullable=False))
    role: UserRole = Field(sa_column=_enum(UserRole, USER_ROLE_TYPE))
    full_name: str = Field(sa_column=Column(String(120), nullable=False))
    phone: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    branch_id: UUID | None = Field(default=None, sa_column=_fk("branches.id", nullable=True))
    is_active: bool = Field(default=True, sa_column=_flag(default=True))
    last_login_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(default=None, sa_column=_created_at())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at())


class ProductModel(SQLModel, table=True):
    """A catalogue entry. Never hired directly, only realised by Assets."""

    __tablename__ = "product_models"

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    sku: str = Field(sa_column=Column(String(24), nullable=False, unique=True))
    name: str = Field(sa_column=Column(String(120), nullable=False))
    slug: str = Field(sa_column=Column(String(140), nullable=False, unique=True))
    manufacturer: str = Field(sa_column=Column(String(80), nullable=False))
    short_description: str = Field(sa_column=Column(String(300), nullable=False))
    daily_rate: Decimal = Field(sa_column=_money())
    deposit_amount: Decimal = Field(sa_column=_money())
    late_fee_per_day: Decimal = Field(sa_column=_money())
    replacement_value: Decimal = Field(sa_column=_money())
    is_published: bool = Field(default=False, sa_column=_flag(default=False))
    created_at: datetime | None = Field(default=None, sa_column=_created_at())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at())


class Asset(SQLModel, table=True):
    """One individually tagged physical unit, for example TSH-DR-0042.

    The composite unique key on (id, branch_id) exists so AssetAllocation can
    carry a composite foreign key and the database itself refuses an allocation
    that claims a unit is at a branch where it is not.
    """

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("id", "branch_id", name="uq_assets_id_branch"),)

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    asset_tag: str = Field(
        sa_column=Column(String(ASSET_TAG_MAX_LENGTH), nullable=False, unique=True)
    )
    product_model_id: UUID = Field(sa_column=_fk("product_models.id"))
    branch_id: UUID = Field(sa_column=_fk("branches.id"))
    serial_number: str | None = Field(default=None, sa_column=Column(String(60), nullable=True))
    status: AssetStatus = Field(sa_column=_enum(AssetStatus, ASSET_STATUS_TYPE))
    condition_grade: ConditionGrade = Field(sa_column=_enum(ConditionGrade, CONDITION_GRADE_TYPE))
    acquired_on: date = Field(sa_column=Column(Date, nullable=False))
    acquisition_cost: Decimal = Field(sa_column=_money())
    hour_meter_reading: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=_created_at())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at())


class Reservation(SQLModel, table=True):
    """A customer booking of one or more product models at one branch.

    The skeleton points `customer_user_id` at user_accounts. The full model
    routes this through CustomerProfile so a walk in with no login can still
    own a booking history. That table arrives with the walk in flow.
    """

    __tablename__ = "reservations"

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    reference: str = Field(
        sa_column=Column(String(REFERENCE_MAX_LENGTH), nullable=False, unique=True)
    )
    customer_user_id: UUID = Field(sa_column=_fk("user_accounts.id"))
    branch_id: UUID = Field(sa_column=_fk("branches.id"))
    status: ReservationStatus = Field(sa_column=_enum(ReservationStatus, RESERVATION_STATUS_TYPE))
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date = Field(sa_column=Column(Date, nullable=False))
    created_by_user_id: UUID = Field(sa_column=_fk("user_accounts.id"))
    notes: str | None = Field(default=None, sa_column=Column(String(300), nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=_created_at())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at())


class ReservationLine(SQLModel, table=True):
    """One product model and a quantity within a reservation, with price snapshots."""

    __tablename__ = "reservation_lines"
    __table_args__ = (
        UniqueConstraint(
            "reservation_id", "product_model_id", name="uq_reservation_lines_model_once"
        ),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    reservation_id: UUID = Field(sa_column=_fk("reservations.id"))
    product_model_id: UUID = Field(sa_column=_fk("product_models.id"))
    quantity: int = Field(sa_column=Column(SmallInteger, nullable=False))
    line_position: int = Field(sa_column=Column(SmallInteger, nullable=False))
    daily_rate_snapshot: Decimal = Field(sa_column=_money())
    deposit_snapshot: Decimal = Field(sa_column=_money())
    created_at: datetime | None = Field(default=None, sa_column=_created_at())


class AssetAllocation(SQLModel, table=True):
    """The reservation of one specific asset for one specific half open period.

    This is the table that makes double booking impossible. The exclusion
    constraint `ex_asset_allocations_no_active_overlap` is created by raw DDL in
    the migration, because Alembic autogenerate will not invent one. The check
    constraints on the period and on the release state are created there too,
    alongside it, so the whole invariant lives in one place.
    """

    __tablename__ = "asset_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_id", "branch_id"],
            ["assets.id", "assets.branch_id"],
            name="fk_asset_allocations_asset_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "asset_id", name="uq_asset_allocations_id_asset"),
        CheckConstraint("end_date > start_date", name="ck_asset_allocations_period"),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=_pk())
    reservation_line_id: UUID = Field(sa_column=_fk("reservation_lines.id"))
    asset_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    branch_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date = Field(sa_column=Column(Date, nullable=False))
    status: AllocationStatus = Field(sa_column=_enum(AllocationStatus, ALLOCATION_STATUS_TYPE))
    allocated_at: datetime | None = Field(default=None, sa_column=_created_at())
    released_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
