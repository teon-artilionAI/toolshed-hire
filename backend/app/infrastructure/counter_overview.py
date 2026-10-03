"""The counter overview query object, which reads the dashboard and the diary of a branch.

It implements the `CounterOverviewQuery` port and returns the frozen read
models of `app.application.hire.overview_models`. It runs on the session of
the request and takes no lock, because a read writes nothing.

Each read takes a bounded number of statements however many rows come back.
The dashboard is six. One counts all five totals, three find the collections
due, the returns due and the overdue hires, each capped at the list limit, one
reads the lines of every collection found and one reads the units of every
rental found. The diary is four, the collections and the returns of the run of
days and then their lines and their units. A read that finds no collection or
no rental skips the statement that would read its lines or its units. Nothing
loops over the database. The statements and the indexes they stand on are in
`app.infrastructure.counter_overview_sql`.

What degrades first as the data grows is the diary of a busy branch. Its lists
are not capped, because the contract shows every booking of a day, so seven
days at a branch with hundreds of hires a day is a few thousand rows held in
memory at once. The dashboard is bounded by its list limit whatever happens.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlmodel import Session, col

from app.application.hire.overview_models import (
    BookedLine,
    DashboardRows,
    DiaryRows,
    HiredUnit,
)
from app.infrastructure.counter_overview_sql import (
    DIARY_STATUSES,
    CollectionRow,
    RentalRow,
    collection_entries,
    collections_statement,
    counts_of,
    counts_statement,
    due_for_collection,
    lines_by_reservation,
    lines_statement,
    rentals_statement,
    return_entries,
    still_out,
    units_by_rental,
    units_statement,
)
from app.infrastructure.models import Rental, Reservation
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)


class SqlCounterOverview:
    """Reads the dashboard and the diary of a branch through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def dashboard(self, branch_id: UUID, today: date, list_limit: int) -> DashboardRows:
        """Return what is due at a branch today, each list capped and the counts in full."""
        filters: dict[str, object] = {
            "branch_id": str(branch_id),
            "business_day": today.isoformat(),
            "list_limit": list_limit,
        }
        with logged_query(logger, "hire.counter_dashboard", filters) as outcome:
            totals = self._session.execute(counts_statement(branch_id, today)).mappings().one()
            counts = counts_of(totals)
            collections = self._session.exec(
                collections_statement(branch_id)
                .where(*due_for_collection(branch_id, today))
                .limit(list_limit)
            ).all()
            returns_due = self._session.exec(
                rentals_statement(branch_id)
                .where(*still_out(branch_id), col(Rental.due_back_on) == today)
                .limit(list_limit)
            ).all()
            overdue = self._session.exec(
                rentals_statement(branch_id)
                .where(*still_out(branch_id), col(Rental.due_back_on) < today)
                .limit(list_limit)
            ).all()
            lines = self._lines_of(collections)
            units = self._units_of([*returns_due, *overdue])
            outcome.row_count = len(collections) + len(returns_due) + len(overdue)
        return DashboardRows(
            counts=counts,
            collections_due=collection_entries(collections, lines),
            returns_due=return_entries(returns_due, units),
            overdue=return_entries(overdue, units),
        )

    def diary(self, branch_id: UUID, first_day: date, last_day: date) -> DiaryRows:
        """Return the collections and the returns of a branch from one day to another."""
        filters: dict[str, object] = {
            "branch_id": str(branch_id),
            "first_day": first_day.isoformat(),
            "last_day": last_day.isoformat(),
        }
        with logged_query(logger, "hire.counter_diary", filters) as outcome:
            collections = self._session.exec(
                collections_statement(branch_id).where(
                    col(Reservation.status).in_(DIARY_STATUSES),
                    col(Reservation.start_date) >= first_day,
                    col(Reservation.start_date) <= last_day,
                )
            ).all()
            returns = self._session.exec(
                rentals_statement(branch_id).where(
                    col(Rental.due_back_on) >= first_day, col(Rental.due_back_on) <= last_day
                )
            ).all()
            lines = self._lines_of(collections)
            units = self._units_of(returns)
            outcome.row_count = len(collections) + len(returns)
        return DiaryRows(
            collections=collection_entries(collections, lines),
            returns=return_entries(returns, units),
        )

    def _lines_of(self, collections: Sequence[CollectionRow]) -> dict[UUID, list[BookedLine]]:
        """Return the lines of every reservation found, in one statement, or none for none."""
        if not collections:
            return {}
        reservation_ids = [reservation.id for reservation, _name, _phone in collections]
        return lines_by_reservation(self._session.exec(lines_statement(reservation_ids)).all())

    def _units_of(self, rentals: Sequence[RentalRow]) -> dict[UUID, list[HiredUnit]]:
        """Return the units of every rental found, in one statement, or none for none."""
        if not rentals:
            return {}
        rental_ids = [rental.id for rental, _name, _phone in rentals]
        return units_by_rental(self._session.exec(units_statement(rental_ids)).all())
