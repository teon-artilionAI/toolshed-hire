"""The report query object, which reads the fleet for the utilisation report.

It implements the `FleetReportQuery` port and returns the frozen read models of
`app.application.reporting.evidence`. It runs on the session of the request
and takes no lock, because a read writes nothing.

A read is three statements however many units there are, which are the units
in scope with their money, every dated fact about them and the units of every
hire charge raised on a whole hire. A report narrowed to a category asks one
more first, whether the category exists. The statements and the indexes they
stand on are described in `app.infrastructure.report_sql` and
`app.infrastructure.report_dated_sql`.

A stored instant is handed on with its time zone, and one that lost it on the
in memory database of the fast tests is given UTC, the zone every instant is
written in. A recorded status is read out of the `status` member of the state
an audit event stored, and a state that holds no known status is read as
nothing known.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import RowMapping
from sqlmodel import Session

from app.application.reporting.evidence import (
    DatedRow,
    EvidenceKind,
    FleetEvidence,
    ReportScope,
    SharedHireRow,
    UnitRow,
)
from app.domain.enums import AssetStatus
from app.infrastructure.booking_mapping import in_utc
from app.infrastructure.query_log import logged_query
from app.infrastructure.report_dated_sql import dated_statement
from app.infrastructure.report_sql import (
    category_count_statement,
    shared_hire_statement,
    units_statement,
)

logger = logging.getLogger(__name__)

STATUS_MEMBER: Final[str] = "status"
NO_MONEY: Final[Decimal] = Decimal("0.00")
NONE_FOUND: Final[int] = 0
KNOWN_STATUSES: Final[frozenset[str]] = frozenset(AssetStatus.values())


class SqlFleetReport:
    """Reads the fleet for the utilisation report through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def evidence(self, scope: ReportScope) -> FleetEvidence:
        """Return every unit in scope and everything dated about them that touches the period."""
        filters: dict[str, object] = {
            "from": scope.starts_on.isoformat(),
            "to": scope.ends_on.isoformat(),
            "branch_id": str(scope.branch_id) if scope.branch_id is not None else None,
            "category_slug": scope.category_slug,
        }
        with logged_query(logger, "report.fleet", filters) as outcome:
            units = tuple(
                _unit_of(row)
                for row in self._session.execute(units_statement(scope)).mappings().all()
            )
            dated = tuple(
                _dated_of(row)
                for row in self._session.execute(dated_statement(scope)).mappings().all()
            )
            shared = tuple(
                _shared_of(row)
                for row in self._session.execute(shared_hire_statement(scope)).mappings().all()
            )
            outcome.row_count = len(units) + len(dated) + len(shared)
        return FleetEvidence(units=units, dated=dated, shared_hire=shared)

    def category_exists(self, slug: str) -> bool:
        """Return True when a category, active or not, has this slug."""
        found = self._session.execute(category_count_statement(slug)).scalar_one()
        logger.debug("report.category_checked", extra={"category_slug": slug, "found": found})
        return int(found) > NONE_FOUND


def status_in(state: object) -> AssetStatus | None:
    """Return the status an audit event's state records, or None when it records none."""
    if not isinstance(state, Mapping):
        return None
    value = state.get(STATUS_MEMBER)
    return AssetStatus(value) if isinstance(value, str) and value in KNOWN_STATUSES else None


def _unit_of(row: RowMapping) -> UnitRow:
    """Return one unit read by `units_statement`."""
    return UnitRow(
        asset_id=row["asset_id"],
        asset_tag=row["asset_tag"],
        status=AssetStatus(row["status"]),
        acquired_on=row["acquired_on"],
        retired_on=row["retired_on"],
        branch_code=row["branch_code"],
        branch_name=row["branch_name"],
        model_slug=row["model_slug"],
        model_name=row["model_name"],
        category_slug=row["category_slug"],
        category_name=row["category_name"],
        held_on_entry=status_in(row["entry_state"]),
        held_on_exit=status_in(row["exit_state"]),
        hire_revenue=_money(row["hire_revenue"]),
        late_fees=_money(row["late_fees"]),
        damage_recovery=_money(row["damage_recovery"]),
        repair_costs=_money(row["repair_costs"]),
    )


def _dated_of(row: RowMapping) -> DatedRow:
    """Return one fact read by `dated_statement`."""
    return DatedRow(
        asset_id=row["asset_id"],
        kind=EvidenceKind(row["kind"]),
        began_at=_instant(row["began_at"]),
        ended_at=_instant(row["ended_at"]),
        begins_on=row["begins_on"],
        ends_on=row["ends_on"],
        moved_from=status_in(row["before_state"]),
        moved_to=status_in(row["after_state"]),
    )


def _shared_of(row: RowMapping) -> SharedHireRow:
    """Return one unit of a shared hire charge read by `shared_hire_statement`."""
    return SharedHireRow(
        charge_id=row["charge_id"],
        amount_ex_vat=_money(row["amount_ex_vat"]),
        asset_id=row["asset_id"],
        line_amount=_money(row["line_amount"]),
        units_on_line=int(row["units_on_line"]),
    )


def _instant(value: object) -> datetime | None:
    """Return a stored instant with its time zone, or None."""
    return in_utc(value) if isinstance(value, datetime) else None


def _money(value: object) -> Decimal:
    """Return a stored amount as an exact Decimal, nought when the database summed nothing."""
    if value is None:
        return NO_MONEY
    return value if isinstance(value, Decimal) else Decimal(str(value))
