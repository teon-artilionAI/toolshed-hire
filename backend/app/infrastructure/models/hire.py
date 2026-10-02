"""Hire and money: Rental, RentalItem, DamageReport and Charge.

A reservation is the promise and a rental is the fulfilment, which is what
makes late fees, partial returns and no-shows expressible. Every money line on
a hire lives in the one Charge table, deposits included, so settlement is a
single sum and gross contribution per asset is a single grouped query.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, ForeignKeyConstraint, Integer, Text, text
from sqlmodel import Field, SQLModel

from app.domain.enums import (
    CHARGE_STATUS_TYPE,
    CHARGE_TYPE_TYPE,
    CONDITION_GRADE_TYPE,
    DAMAGE_SEVERITY_TYPE,
    DAMAGE_STATUS_TYPE,
    RENTAL_STATUS_TYPE,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    RentalStatus,
)
from app.infrastructure.models.columns import (
    ON_DELETE,
    created_at_column,
    enum_column,
    flag,
    money,
    percent,
    timestamp,
    updated_at_column,
    uuid_column,
    uuid_fk,
    uuid_pk,
    varchar,
)

REFERENCE_MAX_LENGTH = 16
NOTHING_YET = Decimal("0")


class Rental(SQLModel, table=True):
    """The hire once the customer has actually walked out with the goods.

    One rental per reservation. It records who handed the equipment over, what
    deposit was taken, when the last item came back and how the account was
    settled.
    """

    __tablename__ = "rental"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    reference: str = Field(sa_column=varchar(REFERENCE_MAX_LENGTH, unique=True))
    reservation_id: UUID = Field(sa_column=uuid_fk("reservation.id", unique=True))
    branch_id: UUID = Field(sa_column=uuid_fk("branch.id"))
    status: RentalStatus = Field(sa_column=enum_column(RentalStatus, RENTAL_STATUS_TYPE))
    checked_out_at: datetime = Field(sa_column=timestamp(nullable=False))
    checked_out_by_user_id: UUID = Field(sa_column=uuid_fk("user_account.id"))
    # Copied from the reservation end date.
    due_back_on: date = Field(sa_column=Column(Date, nullable=False))
    # Set when the last item is back.
    returned_at: datetime | None = Field(default=None, sa_column=timestamp())
    returned_to_user_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("user_account.id", nullable=True)
    )
    deposit_held: Decimal = Field(sa_column=money())
    deposit_refunded: Decimal = Field(default=NOTHING_YET, sa_column=money(default="0"))
    deposit_withheld: Decimal = Field(default=NOTHING_YET, sa_column=money(default="0"))
    # What the customer still owes after the deposit has been offset (BR-32).
    balance_due: Decimal = Field(default=NOTHING_YET, sa_column=money(default="0"))
    settled_at: datetime | None = Field(default=None, sa_column=timestamp())
    agreement_signed: bool = Field(default=False, sa_column=flag(default=False))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class RentalItem(SQLModel, table=True):
    """One physical asset handed over on a rental, with its condition out and back.

    The composite foreign key to AssetAllocation (id, asset_id) means the
    database refuses an item whose `asset_id` disagrees with the allocation it
    came from. The denormalised column is safe because it cannot drift.
    """

    __tablename__ = "rental_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_allocation_id", "asset_id"],
            ["asset_allocation.id", "asset_allocation.asset_id"],
            name="fk_rental_item_allocation_asset",
            ondelete=ON_DELETE,
        ),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    rental_id: UUID = Field(sa_column=uuid_fk("rental.id"))
    # Unique, because an allocation is collected once (BR-28).
    asset_allocation_id: UUID = Field(sa_column=uuid_column(unique=True))
    asset_id: UUID = Field(sa_column=uuid_column())
    condition_out: ConditionGrade = Field(
        sa_column=enum_column(ConditionGrade, CONDITION_GRADE_TYPE)
    )
    condition_in: ConditionGrade | None = Field(
        default=None, sa_column=enum_column(ConditionGrade, CONDITION_GRADE_TYPE, nullable=True)
    )
    hour_meter_out: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    hour_meter_in: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    accessories_out: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    accessories_in: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    checked_out_at: datetime = Field(sa_column=timestamp(nullable=False))
    returned_at: datetime | None = Field(default=None, sa_column=timestamp())
    # Whole days, computed at return (BR-30).
    days_late: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class DamageReport(SQLModel, table=True):
    """A record that a specific asset came back damaged, and what it cost.

    `chargeable_to_customer` has no default on purpose. Fair wear and tear is
    not charged, and whether this is that is an explicit decision recorded on
    every report (BR-40).
    """

    __tablename__ = "damage_report"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    reference: str = Field(sa_column=varchar(REFERENCE_MAX_LENGTH, unique=True))
    asset_id: UUID = Field(sa_column=uuid_fk("asset.id"))
    # Null when the damage was found outside a hire.
    rental_item_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("rental_item.id", nullable=True)
    )
    severity: DamageSeverity = Field(sa_column=enum_column(DamageSeverity, DAMAGE_SEVERITY_TYPE))
    status: DamageStatus = Field(sa_column=enum_column(DamageStatus, DAMAGE_STATUS_TYPE))
    description: str = Field(sa_column=Column(Text, nullable=False))
    # An object key in the private photograph bucket, never a public path.
    photo_path: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    repair_estimate: Decimal = Field(sa_column=money())
    # The direct cost the gross contribution report subtracts.
    actual_repair_cost: Decimal | None = Field(default=None, sa_column=money(nullable=True))
    chargeable_to_customer: bool = Field(sa_column=flag(default=None))
    reported_by_user_id: UUID = Field(sa_column=uuid_fk("user_account.id"))
    reported_at: datetime = Field(sa_column=timestamp(nullable=False))
    resolved_at: datetime | None = Field(default=None, sa_column=timestamp())
    resolution_notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class Charge(SQLModel, table=True):
    """Every money line on a rental, positive or negative, deposits included.

    `amount_ex_vat` is signed. A refund or a deposit release is a negative
    amount, so the three amount columns are the only money in the schema with
    no floor. A settled charge is never edited. A correction is a new row that
    points back at the original through `reverses_charge_id` (BR-24).
    """

    __tablename__ = "charge"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    rental_id: UUID = Field(sa_column=uuid_fk("rental.id"))
    # Set when the charge is attributable to one asset. Null is hire level.
    rental_item_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("rental_item.id", nullable=True)
    )
    damage_report_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("damage_report.id", nullable=True)
    )
    charge_type: ChargeType = Field(sa_column=enum_column(ChargeType, CHARGE_TYPE_TYPE))
    description: str = Field(sa_column=varchar(200))
    amount_ex_vat: Decimal = Field(sa_column=money())
    # Zero on a deposit movement, because a deposit is not consideration.
    vat_rate: Decimal = Field(sa_column=percent())
    vat_amount: Decimal = Field(sa_column=money())
    amount_inc_vat: Decimal = Field(sa_column=money())
    status: ChargeStatus = Field(sa_column=enum_column(ChargeStatus, CHARGE_STATUS_TYPE))
    raised_at: datetime = Field(sa_column=timestamp(nullable=False))
    raised_by_user_id: UUID = Field(sa_column=uuid_fk("user_account.id"))
    settled_at: datetime | None = Field(default=None, sa_column=timestamp())
    # A simulated settlement reference. No payment gateway is called (BR-33).
    payment_reference: str | None = Field(default=None, sa_column=varchar(40, nullable=True))
    reverses_charge_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("charge.id", nullable=True)
    )
    # Mandatory when the status is WAIVED (BR-25).
    waiver_reason: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())
