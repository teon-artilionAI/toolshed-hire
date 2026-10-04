"""The admin dashboard query object, which counts every branch and what waits for an administrator.

It implements the `AdminDashboardQuery` port. It runs on the session of the
request and takes no lock.

The branches are counted in one statement, one row for each trading branch,
whose counts are scalar subqueries correlated with the branch. The collections
due, the returns due and the overdue hires are counted with the very
conditions the counter's dashboard counts with, `due_for_collection` and
`still_out` from `app.infrastructure.counter_overview_sql`, so the two
dashboards can never disagree, and they stand on the same indexes,
`ix_reservation_confirmed_start` and `ix_rental_open_due_back`. The units are
counted by status through `ix_asset_branch_status`. Three branches make
twenty one small index reads.

The three counts of what waits are a second statement. The failed messages
stand on the partial index `ix_notification_failed`. The open damage reports
and the customers on hold are counted from tables of a few hundred and a few
thousand rows, which no index is needed for yet. The README names them among
what degrades as the data grows.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

from sqlalchemy import ColumnElement, RowMapping, func, literal_column, true
from sqlalchemy import select as select_columns
from sqlmodel import Session, SQLModel, col

from app.application.reporting.report_models import (
    AttentionCounts,
    BranchCounts,
    BranchPosition,
)
from app.domain.enums import AccountStatus, AssetStatus, DamageStatus
from app.infrastructure.counter_overview_sql import due_for_collection, still_out
from app.infrastructure.models import (
    Asset,
    Branch,
    CustomerProfile,
    DamageReport,
    Notification,
    Rental,
    Reservation,
)

logger = logging.getLogger(__name__)

# Written as the literal the partial index `ix_notification_failed` is filtered on.
FAILED_STATUS_LITERAL: Final[str] = "'FAILED'"
OPEN_REPORT_STATUSES: Final[tuple[DamageStatus, ...]] = (
    DamageStatus.OPEN,
    DamageStatus.UNDER_REPAIR,
)
# Each count of units and the status it counts.
UNIT_COUNTS: Final[tuple[tuple[str, AssetStatus], ...]] = (
    ("on_hire", AssetStatus.ON_HIRE),
    ("quarantined", AssetStatus.QUARANTINED),
    ("under_repair", AssetStatus.UNDER_REPAIR),
    ("available", AssetStatus.AVAILABLE),
)


def _counted(table: type[SQLModel], *conditions: ColumnElement[bool]) -> ColumnElement[int]:
    """Return a subquery that counts the rows of a table meeting the conditions."""
    return (
        select_columns(func.count()).select_from(table).where(*conditions).scalar_subquery()
    )


class SqlAdminDashboard:
    """Counts every branch and what waits for an administrator through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def branch_positions(self, today: date) -> tuple[BranchPosition, ...]:
        """Return what is due today at each trading branch and where its units stand."""
        branch = col(Branch.id)
        unit_counts = [
            _counted(Asset, col(Asset.branch_id) == branch, col(Asset.status) == status).label(
                name
            )
            for name, status in UNIT_COUNTS
        ]
        statement = (
            select_columns(
                col(Branch.code).label("branch_code"),
                col(Branch.name).label("branch_name"),
                _counted(Reservation, *due_for_collection(branch, today)).label(
                    "collections_due"
                ),
                _counted(Rental, *still_out(branch), col(Rental.due_back_on) == today).label(
                    "returns_due"
                ),
                _counted(Rental, *still_out(branch), col(Rental.due_back_on) < today).label(
                    "overdue"
                ),
                *unit_counts,
            )
            .where(col(Branch.is_active) == true())
            .order_by(col(Branch.name), col(Branch.code))
        )
        rows = self._session.execute(statement).mappings().all()
        logger.info(
            "report.branch_positions_read",
            extra={"business_day": today.isoformat(), "branch_count": len(rows)},
        )
        return tuple(_position_of(row) for row in rows)

    def attention_counts(self) -> AttentionCounts:
        """Return the open damage reports, the customers on hold and the failed messages."""
        statement = select_columns(
            _counted(DamageReport, col(DamageReport.status).in_(OPEN_REPORT_STATUSES)).label(
                "open_damage_reports"
            ),
            _counted(
                CustomerProfile, col(CustomerProfile.account_status) == AccountStatus.ON_HOLD
            ).label("customers_on_hold"),
            _counted(
                Notification, col(Notification.status) == literal_column(FAILED_STATUS_LITERAL)
            ).label("failed_notifications"),
        )
        row = self._session.execute(statement).mappings().one()
        counts = AttentionCounts(
            open_damage_reports=int(row["open_damage_reports"]),
            customers_on_hold=int(row["customers_on_hold"]),
            failed_notifications=int(row["failed_notifications"]),
        )
        logger.info(
            "report.attention_counts_read",
            extra={
                "open_damage_reports": counts.open_damage_reports,
                "customers_on_hold": counts.customers_on_hold,
                "failed_notifications": counts.failed_notifications,
            },
        )
        return counts


def _position_of(row: RowMapping) -> BranchPosition:
    """Return one branch read by `branch_positions`, its counts read by their labels."""
    return BranchPosition(
        branch_code=row["branch_code"],
        branch_name=row["branch_name"],
        counts=BranchCounts(
            collections_due=int(row["collections_due"]),
            returns_due=int(row["returns_due"]),
            overdue=int(row["overdue"]),
            on_hire=int(row["on_hire"]),
            quarantined=int(row["quarantined"]),
            under_repair=int(row["under_repair"]),
            available=int(row["available"]),
        ),
    )
