"""The list of rentals, as a page of read models, in four statements however long the page is.

One statement counts every rental that matches. One reads the rentals of the
page with their reservations, branches and customers. One reads the items of
every rental on the page and one their charges, through
`SqlRentalReads.details_of`. A page that finds nothing skips the last two.

The scope of the reader goes into both statements. A customer's rentals are
reached through their reservations, by the account their profile belongs to,
so a rental that is not theirs is never read (BR-42).

The order puts the overdue rentals first when the search asks for it. A rental
is overdue while a unit is still out, which is while it has no `returned_at`,
and the day it was due back has passed (BR-52). The most overdue is the one
due back earliest. Every other rental follows, newest first by when it went
out. The same condition is the overdue filter, and it is the predicate of the
partial index `ix_rental_open_due_back`, so a filtered read of the overdue
hires stands on that index.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

from sqlalchemy import ColumnElement, and_, case, func
from sqlalchemy import select as select_columns
from sqlmodel import Session, col, select
from sqlmodel.sql.expression import Select as EntitySelect

from app.application.hire.list_models import RentalPage, RentalSearch
from app.application.ownership import OwnerScope
from app.infrastructure.models import Branch, CustomerProfile, Rental, Reservation
from app.infrastructure.query_log import logged_query
from app.infrastructure.rental_query import RentalRow, SqlRentalReads

logger = logging.getLogger(__name__)

OVERDUE_RANK: Final[int] = 0
OTHER_RANK: Final[int] = 1


def overdue_on(today: date) -> ColumnElement[bool]:
    """Return the condition of a rental with a unit still out after the day it was due back."""
    return and_(col(Rental.returned_at).is_(None), col(Rental.due_back_on) < today)


class SqlRentalList:
    """Reads pages of rentals through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the list to the session of the unit of work."""
        self._session = session
        self._reads = SqlRentalReads(session)

    def search(self, search: RentalSearch, scope: OwnerScope) -> RentalPage:
        """Return one page of the rentals the scope lets the caller see."""
        conditions = _conditions_of(search, scope)
        filters: dict[str, object] = {
            "branch_id": str(search.branch_id) if search.branch_id else None,
            "status": search.status.value if search.status else None,
            "overdue_only": search.overdue_only,
            "restricted_to_owner": scope.is_restricted,
            "page": search.page,
            "page_size": search.page_size,
        }
        with logged_query(logger, "hire.rental_list", filters) as outcome:
            total = self._session.execute(
                select_columns(func.count())
                .select_from(Rental)
                .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
                .join(
                    CustomerProfile,
                    col(CustomerProfile.id) == col(Reservation.customer_profile_id),
                )
                .where(*conditions)
            ).scalar_one()
            statement = (
                select(Rental, Reservation, Branch, CustomerProfile)
                .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
                .join(Branch, col(Branch.id) == col(Rental.branch_id))
                .join(
                    CustomerProfile,
                    col(CustomerProfile.id) == col(Reservation.customer_profile_id),
                )
                .where(*conditions)
            )
            rows = self._session.exec(
                _ordered(statement, search).offset(search.offset).limit(search.page_size)
            ).all()
            outcome.row_count = len(rows)
        return RentalPage(
            items=tuple(self._reads.details_of(rows)),
            page=search.page,
            page_size=search.page_size,
            total=int(total),
        )


def _conditions_of(search: RentalSearch, scope: OwnerScope) -> list[ColumnElement[bool]]:
    """Return the conditions a rental has to meet to be on the list."""
    conditions: list[ColumnElement[bool]] = []
    if scope.customer_user_id is not None:
        conditions.append(col(CustomerProfile.user_account_id) == scope.customer_user_id)
    if search.branch_id is not None:
        conditions.append(col(Rental.branch_id) == search.branch_id)
    if search.status is not None:
        conditions.append(col(Rental.status) == search.status)
    if search.customer_profile_id is not None:
        conditions.append(col(Reservation.customer_profile_id) == search.customer_profile_id)
    if search.overdue_only:
        conditions.append(overdue_on(search.today))
    return conditions


def _ordered(
    statement: EntitySelect[RentalRow], search: RentalSearch
) -> EntitySelect[RentalRow]:
    """Return the statement in the order of the list, the overdue first when the search asks."""
    newest_first = (col(Rental.checked_out_at).desc(), col(Rental.reference).desc())
    if not search.overdue_first:
        return statement.order_by(*newest_first)
    overdue = overdue_on(search.today)
    return statement.order_by(
        case((overdue, OVERDUE_RANK), else_=OTHER_RANK),
        case((overdue, col(Rental.due_back_on)), else_=None).asc().nulls_last(),
        *newest_first,
    )
