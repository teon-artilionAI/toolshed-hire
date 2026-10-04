"""What the trading history reads about the fleet before it writes anything.

Three reads, each one query or a handful. Whether any of the history is there
already, counted in one round trip over the reserved reference ranges and the
walk in phone block. The units on the shelf with their model, category and
branch, and the catalogue as the domain sees it. And the days any of those
units is already away in the season, from allocations, hires and damage
reports, so the history never puts a unit out on a day it really was out. The
people the history needs are read by `trading_people`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, ScalarSelect, and_, func, or_
from sqlalchemy import select as select_columns
from sqlalchemy.orm import Mapped
from sqlmodel import Session, col, select

from app.domain import catalogue as domain
from app.domain.enums import AssetStatus, ReleaseReason
from app.domain.money import Money
from app.domain.report_days import DaySpan
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Category,
    Charge,
    CustomerProfile,
    DamageReport,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)
from seeding.trading_customers import PHONE_BLOCK
from seeding.trading_demand import SEASON_FIRST_DAY, SEASON_LAST_DAY
from seeding.trading_records import DAMAGE_RANGE, RENTAL_RANGE, RESERVATION_RANGE, FleetUnit
from seeding.worked_example import SOUTH_AFRICA_STANDARD_TIME

ONE_DAY: Final[timedelta] = timedelta(days=1)
SEASON_ENDS: Final[date] = SEASON_LAST_DAY + ONE_DAY
LIKE_ANYTHING: Final[str] = "%"


@dataclass(frozen=True, slots=True)
class HistoryCounts:
    """How many rows of each kind of the history the database holds."""

    customer_profile: int
    reservation: int
    reservation_line: int
    asset_allocation: int
    rental: int
    rental_item: int
    damage_report: int
    charge: int

    def by_kind(self) -> dict[str, int]:
        """Return the counts by the kind each is reported under."""
        return {
            "customer_profile": self.customer_profile,
            "reservation": self.reservation,
            "reservation_line": self.reservation_line,
            "asset_allocation": self.asset_allocation,
            "rental": self.rental,
            "rental_item": self.rental_item,
            "damage_report": self.damage_report,
            "charge": self.charge,
        }


@dataclass(frozen=True, slots=True)
class FleetRead:
    """The units on the shelf and the catalogue, as the planner and the domain need them."""

    units: tuple[FleetUnit, ...]
    domain_units: Mapping[UUID, domain.Asset]
    models: Mapping[str, domain.ProductModel]
    branch_ids: Mapping[str, UUID]


def count_history(session: Session) -> HistoryCounts:
    """Return how much of the history is there, in one round trip."""
    reservations = _between(col(Reservation.reference), RESERVATION_RANGE)
    rentals = _between(col(Rental.reference), RENTAL_RANGE)
    of_reservation = col(ReservationLine.reservation_id) == col(Reservation.id)
    of_line = col(AssetAllocation.reservation_line_id) == col(ReservationLine.id)
    statement = select_columns(
        _count(col(CustomerProfile.id), _walk_in_phone()),
        _count(col(Reservation.id), reservations),
        _count(col(ReservationLine.id), reservations, of_reservation),
        _count(col(AssetAllocation.id), reservations, of_reservation, of_line),
        _count(col(Rental.id), rentals),
        _count(col(RentalItem.id), rentals, col(RentalItem.rental_id) == col(Rental.id)),
        _count(col(DamageReport.id), _between(col(DamageReport.reference), DAMAGE_RANGE)),
        _count(col(Charge.id), rentals, col(Charge.rental_id) == col(Rental.id)),
    )
    row = session.execute(statement).one()
    return HistoryCounts(*(int(count) for count in row))


def read_fleet(session: Session) -> FleetRead:
    """Return every unit on the shelf with its model, category and branch, and the catalogue."""
    models = {row.sku: _domain_model(row) for row in session.exec(select(ProductModel)).all()}
    branch_ids = {branch.code: branch.id for branch in session.exec(select(Branch)).all()}
    statement = (
        select(Asset, col(ProductModel.sku), col(Category.code), col(Branch.code))
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .join(Category, col(Category.id) == col(ProductModel.category_id))
        .join(Branch, col(Branch.id) == col(Asset.branch_id))
        .where(col(Asset.status) == AssetStatus.AVAILABLE)
        .order_by(col(Asset.asset_tag))
    )
    units: list[FleetUnit] = []
    domain_units: dict[UUID, domain.Asset] = {}
    for asset, sku, category_code, branch_code in session.exec(statement).all():
        units.append(
            FleetUnit(
                asset_id=asset.id,
                asset_tag=asset.asset_tag,
                sku=sku,
                category_code=category_code,
                branch_code=branch_code,
                acquired_on=asset.acquired_on,
                replacement_value=Money.create(models[sku].replacement_value),
            )
        )
        domain_units[asset.id] = _domain_asset(asset)
    return FleetRead(tuple(units), domain_units, models, branch_ids)


def read_already_away(session: Session) -> dict[UUID, list[DaySpan]]:
    """Return the days in the season each unit is already held, out or in the workshop.

    A booking that holds a unit, or held it until the unit came back, counts its
    own days. A hire counts from the day the unit went out to the day it came
    back, and a damage report from the day it was filed to the day it was
    resolved. Anything still open runs to the end of the season. The day a unit
    is due or came back is counted as well, because the history does not know
    the hour, and leaving that day to the counter is what keeps a unit off two
    hires at once.
    """
    away: dict[UUID, list[DaySpan]] = {}
    for asset_id, span in (*_held(session), *_out_or_repaired(session)):
        away.setdefault(asset_id, []).append(span)
    return away


def _held(session: Session) -> list[tuple[UUID, DaySpan]]:
    """Return the booked days in the season of each allocation that held or still holds a unit."""
    begins, ends = col(AssetAllocation.start_date), col(AssetAllocation.end_date)
    statement = select(col(AssetAllocation.asset_id), begins, ends).where(
        begins < SEASON_ENDS,
        ends > SEASON_FIRST_DAY,
        or_(
            col(AssetAllocation.released_at).is_(None),
            col(AssetAllocation.release_reason) == ReleaseReason.RETURNED,
        ),
    )
    return [
        (asset_id, DaySpan(first, after + ONE_DAY))
        for asset_id, first, after in session.exec(statement)
    ]


def _out_or_repaired(session: Session) -> list[tuple[UUID, DaySpan]]:
    """Return the days in the season each unit was out on a hire or named by a damage report."""
    season_starts = _instant(SEASON_FIRST_DAY)
    season_ends = _instant(SEASON_ENDS)
    out = select(
        col(RentalItem.asset_id), col(RentalItem.checked_out_at), col(RentalItem.returned_at)
    ).where(
        col(RentalItem.checked_out_at) < season_ends,
        or_(col(RentalItem.returned_at).is_(None), col(RentalItem.returned_at) >= season_starts),
    )
    resolved_at = col(DamageReport.resolved_at)
    repaired = select(
        col(DamageReport.asset_id), col(DamageReport.reported_at), resolved_at
    ).where(
        col(DamageReport.reported_at) < season_ends,
        or_(resolved_at.is_(None), resolved_at >= season_starts),
    )
    return [
        (asset_id, _span_of(began_at, ended_at))
        for statement in (out, repaired)
        for asset_id, began_at, ended_at in session.exec(statement)
    ]


def _between(column: Mapped[str], bounds: tuple[str, str]) -> ColumnElement[bool]:
    """Return the condition of a reference inside a reserved range, served by its unique index."""
    first, last = bounds
    return and_(column >= first, column <= last)


def _walk_in_phone() -> ColumnElement[bool]:
    """Return the condition of a walk in customer of the history, by the phone block."""
    return and_(
        col(CustomerProfile.user_account_id).is_(None),
        col(CustomerProfile.contact_phone).like(f"{PHONE_BLOCK}{LIKE_ANYTHING}"),
    )


def _count(key: Mapped[UUID], *conditions: ColumnElement[bool]) -> ScalarSelect[int]:
    """Return a scalar count of the rows that meet every condition, for one select."""
    return select_columns(func.count(key)).where(*conditions).scalar_subquery()


def _instant(day: date) -> datetime:
    """Return the start of a day on a clock in Cape Town."""
    return datetime.combine(day, datetime.min.time(), tzinfo=SOUTH_AFRICA_STANDARD_TIME)


def _span_of(began_at: datetime, ended_at: datetime | None) -> DaySpan:
    """Return the business days from one instant to another and the day after, or to the end."""
    begins = began_at.astimezone(SOUTH_AFRICA_STANDARD_TIME).date()
    if ended_at is None:
        return DaySpan(begins, max(SEASON_ENDS, begins + ONE_DAY))
    return DaySpan(begins, ended_at.astimezone(SOUTH_AFRICA_STANDARD_TIME).date() + ONE_DAY)


def _domain_model(row: ProductModel) -> domain.ProductModel:
    """Return the product model as the domain prices it, as the catalogue repository maps it."""
    return domain.ProductModel(
        id=row.id,
        sku=row.sku,
        name=row.name,
        slug=row.slug,
        daily_rate=row.daily_rate,
        weekly_rate=row.weekly_rate,
        deposit_amount=row.deposit_amount,
        late_fee_per_day=row.late_fee_per_day,
        replacement_value=row.replacement_value,
        min_hire_days=row.min_hire_days,
        max_hire_days=row.max_hire_days,
    )


def _domain_asset(row: Asset) -> domain.Asset:
    """Return the unit as the domain moves it."""
    return domain.Asset(
        id=row.id,
        asset_tag=row.asset_tag,
        product_model_id=row.product_model_id,
        branch_id=row.branch_id,
        status=row.status,
        condition_grade=row.condition_grade,
        hour_meter_reading=row.hour_meter_reading,
        retired_on=row.retired_on,
    )
