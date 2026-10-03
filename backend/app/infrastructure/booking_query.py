"""The reads of the booking module that return read models.

One reservation, or one page of them, with the lines and the units held for
each line. A page takes four statements however many reservations it holds,
one for the count, one for the page, one for all of its lines and one for all
of the units those lines hold. Nothing loops over the database.

Ownership is in the query (BR-42). A restricted scope adds a condition on the
account of the customer profile to the same statement that finds the
reservation, so a reservation that belongs to somebody else is never read. A
customer's list also leaves out a reservation that was cancelled without ever
holding a unit, which is an abandoned basket and not a cancelled booking.

A list is ordered newest first. The reference breaks a tie between two
reservations created in the same instant. It comes from a sequence, so the
later one always sorts first and the order is the same on every call.

The page is found with LIMIT and OFFSET and the total with a count. Both are
fine for a customer's own list, which is short and reached through the index
on the customer. The list staff ask for with no filter sorts every reservation
by its creation time, and that is the query to move to a keyed page first.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_
from sqlmodel import Session, col, select
from sqlmodel.sql.expression import Select

from app.application.booking.read_models import (
    ReservationDetail,
    ReservationKey,
    ReservationLineDetail,
    ReservationPage,
    ReservationSearch,
)
from app.application.ownership import OwnerScope
from app.domain.enums import ReservationStatus
from app.domain.policies.pricing import NO_DISCOUNT_PERCENT
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    CustomerProfile,
    ProductModel,
    Reservation,
    ReservationLine,
    UserAccount,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

# One row of the statement that finds reservations. The reservation itself,
# its branch, the name of its customer and the moment that customer proved
# their address, when they have an account and have.
type _Found = tuple[Reservation, Branch, str, datetime | None]

CREATED_AT_COLUMN: Final[str] = "reservation.created_at"


def key_condition(key: ReservationKey) -> ColumnElement[bool]:
    """Return the condition that picks one reservation by its key or its reference."""
    if key.reservation_id is not None:
        return col(Reservation.id) == key.reservation_id
    return col(Reservation.reference) == key.reference


class SqlReservationReads:
    """Reads reservations as read models through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the unit of work."""
        self._session = session

    def find_detail(self, key: ReservationKey, scope: OwnerScope) -> ReservationDetail | None:
        """Return one reservation, if it exists and the scope lets the caller see it."""
        statement = _found_statement().where(key_condition(key), *_scope_conditions(scope))
        with logged_query(
            logger,
            "booking.reservation_lookup",
            {"reservation": str(key), "restricted_to_owner": scope.is_restricted},
        ) as outcome:
            found = self._session.exec(statement).first()
            outcome.row_count = 0 if found is None else 1
        if found is None:
            return None
        return self._details_of([found])[0]

    def search(self, search: ReservationSearch, scope: OwnerScope) -> ReservationPage:
        """Return one page of the reservations that match, newest first.

        A customer's own list leaves out the baskets they abandoned, in the
        statement itself, so the count and the page agree.
        """
        conditions = [*_search_conditions(search), *_scope_conditions(scope)]
        if scope.is_restricted:
            conditions.append(_not_an_abandoned_basket())
        filters: dict[str, object] = {
            "status": search.status.value if search.status else None,
            "narrowed_to_customer": search.customer_profile_id is not None,
            "narrowed_to_branch": search.branch_id is not None,
            "restricted_to_owner": scope.is_restricted,
            "page": search.page,
            "page_size": search.page_size,
        }
        count_statement = (
            select(func.count())
            .select_from(Reservation)
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .where(*conditions)
        )
        page_statement = (
            _found_statement()
            .where(*conditions)
            .order_by(col(Reservation.created_at).desc(), col(Reservation.reference).desc())
            .limit(search.page_size)
            .offset(search.offset)
        )
        with logged_query(logger, "booking.reservation_search", filters) as outcome:
            total = self._session.exec(count_statement).one()
            found = self._session.exec(page_statement).all()
            outcome.row_count = len(found)
        return ReservationPage(
            items=tuple(self._details_of(found)),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def _details_of(self, found: Sequence[_Found]) -> list[ReservationDetail]:
        """Return the read model of each found reservation, with its lines."""
        if not found:
            return []
        reservation_ids = [row[0].id for row in found]
        line_rows = self._session.exec(
            select(ReservationLine, col(ProductModel.slug), col(ProductModel.name))
            .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
            .where(col(ReservationLine.reservation_id).in_(reservation_ids))
            .order_by(col(ReservationLine.reservation_id), col(ReservationLine.line_position))
        ).all()
        tags_by_line = self._held_tags_by_line([line.id for line, _slug, _name in line_rows])

        lines_by_reservation: dict[UUID, list[ReservationLineDetail]] = defaultdict(list)
        discount_by_reservation: dict[UUID, Decimal] = {}
        for line, slug, name in line_rows:
            tags = tuple(tags_by_line[line.id])
            discount_by_reservation.setdefault(line.reservation_id, Decimal(line.discount_percent))
            lines_by_reservation[line.reservation_id].append(
                ReservationLineDetail(
                    model_slug=slug,
                    model_name=name,
                    quantity=line.quantity,
                    daily_rate=Decimal(line.daily_rate_snapshot),
                    weekly_rate=Decimal(line.weekly_rate_snapshot),
                    deposit_per_unit=Decimal(line.deposit_snapshot),
                    line_subtotal_ex_vat=Decimal(line.line_subtotal_ex_vat),
                    allocated_count=len(tags),
                    asset_tags=tags,
                )
            )
        return [
            _detail_of(
                row,
                tuple(lines_by_reservation[row[0].id]),
                discount_by_reservation.get(row[0].id, NO_DISCOUNT_PERCENT),
            )
            for row in found
        ]

    def _held_tags_by_line(self, line_ids: Sequence[UUID]) -> dict[UUID, list[str]]:
        """Return the tags of the units each line holds right now, in tag order."""
        tags_by_line: dict[UUID, list[str]] = defaultdict(list)
        if not line_ids:
            return tags_by_line
        held = self._session.exec(
            select(col(AssetAllocation.reservation_line_id), col(Asset.asset_tag))
            .join(Asset, col(Asset.id) == col(AssetAllocation.asset_id))
            .where(
                col(AssetAllocation.reservation_line_id).in_(line_ids),
                col(AssetAllocation.released_at).is_(None),
            )
            .order_by(col(Asset.asset_tag))
        ).all()
        for line_id, tag in held:
            tags_by_line[line_id].append(tag)
        return tags_by_line


def _found_statement() -> Select[_Found]:
    """Return the statement every read starts from, before it is narrowed.

    The join to the account is an outer one, because a walk-in has a customer
    profile and no account.
    """
    return (
        select(
            Reservation,
            Branch,
            col(CustomerProfile.display_name),
            col(UserAccount.email_verified_at),
        )
        .join(Branch, col(Branch.id) == col(Reservation.branch_id))
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .outerjoin(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
    )


def _scope_conditions(scope: OwnerScope) -> list[ColumnElement[bool]]:
    """Return the condition that limits a read to one customer's reservations."""
    if scope.customer_user_id is None:
        return []
    return [col(CustomerProfile.user_account_id) == scope.customer_user_id]


def _not_an_abandoned_basket() -> ColumnElement[bool]:
    """Return the condition that leaves out a reservation cancelled before it held a unit.

    Such a reservation is a draft that was thrown away or replaced by a changed
    basket. A reservation that ever held a unit keeps the allocation as
    history, because nothing is deleted (BR-51), so one with no allocation at
    all never held one. The two indexes the existence test reads through are
    the unique key on a line's reservation and model, and
    `ix_asset_allocation_line`.
    """
    ever_held_a_unit = (
        select(col(AssetAllocation.id))
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .where(col(ReservationLine.reservation_id) == col(Reservation.id))
        .exists()
    )
    return or_(col(Reservation.status) != ReservationStatus.CANCELLED, ever_held_a_unit)


def _search_conditions(search: ReservationSearch) -> list[ColumnElement[bool]]:
    """Return the conditions a list was narrowed with."""
    conditions: list[ColumnElement[bool]] = []
    if search.status is not None:
        conditions.append(col(Reservation.status) == search.status)
    if search.customer_profile_id is not None:
        conditions.append(col(Reservation.customer_profile_id) == search.customer_profile_id)
    if search.branch_id is not None:
        conditions.append(col(Reservation.branch_id) == search.branch_id)
    return conditions


def _detail_of(
    found: _Found, lines: tuple[ReservationLineDetail, ...], discount_percent: Decimal
) -> ReservationDetail:
    """Return the read model for one found reservation and its lines."""
    row, branch, customer_name, email_verified_at = found
    return ReservationDetail(
        id=row.id,
        reference=row.reference,
        status=row.status,
        branch_id=row.branch_id,
        branch_code=branch.code,
        branch_name=branch.name,
        start_date=row.start_date,
        end_date=row.end_date,
        lines=lines,
        subtotal_ex_vat=Decimal(row.subtotal_ex_vat),
        discount_percent=discount_percent,
        vat_amount=Decimal(row.vat_amount),
        estimated_total_inc_vat=Decimal(row.estimated_total_inc_vat),
        deposit_total=Decimal(row.deposit_total),
        hold_expires_at=in_utc(row.hold_expires_at),
        confirmed_at=in_utc(row.confirmed_at),
        cancelled_at=in_utc(row.cancelled_at),
        cancellation_reason=row.cancellation_reason,
        customer_profile_id=row.customer_profile_id,
        customer_name=customer_name,
        customer_email_verified=email_verified_at is not None,
        created_at=required_utc(row.created_at, CREATED_AT_COLUMN),
    )
