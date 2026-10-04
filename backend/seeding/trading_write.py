"""Write the rows of the trading history in bulk, and say what was written.

Each table is written with one bulk insert that hands back the keys it wrote.
That is what makes SQLAlchemy send the rows as multi row statements of a
thousand rows each, about twenty in all, so the step costs a handful of round
trips however far away the database is. The keys handed back are counted
against the rows sent, so a short write stops the seed instead of passing.

The log line says what the season holds, where its references start and end,
and how long the reads and the plan, the domain and the writes each took, so a
slow deployment shows where it was slow.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import insert, literal_column
from sqlmodel import Session, SQLModel

from app.infrastructure.models import (
    AssetAllocation,
    Charge,
    CustomerProfile,
    DamageReport,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)
from seeding.errors import SeedDataError
from seeding.trading_demand import SEASON_FIRST_DAY, SEASON_LAST_DAY
from seeding.trading_records import PlannedHire
from seeding.trading_rows import HistoryRows, Row, counts_of

logger = logging.getLogger("seed")

# Rows in one insert statement. The widest table has twenty columns, so a
# statement stays far below the 65535 parameters PostgreSQL accepts.
INSERT_BATCH_ROWS: Final[int] = 1000
KEY_COLUMN: Final[str] = "id"
MILLISECONDS: Final[int] = 1000


@dataclass(frozen=True, slots=True)
class Timings:
    """When each phase of the step finished, as readings of the performance counter."""

    started: float
    planned: float
    run: float
    written: float


def insert_history(session: Session, rows: HistoryRows) -> int:
    """Write every table of the history in multi row inserts, parents first.

    Args:
        session: The open session of the seed. The caller owns the commit.
        rows: Every row of the history, by table.

    Returns:
        How many insert statements were sent.

    Raises:
        SeedDataError: If a table hands back fewer keys than it was sent rows.

    """
    tables: tuple[tuple[type[SQLModel], list[Row]], ...] = (
        (CustomerProfile, rows.customer_profiles),
        (Reservation, rows.reservations),
        (ReservationLine, rows.reservation_lines),
        (AssetAllocation, rows.asset_allocations),
        (Rental, rows.rentals),
        (RentalItem, rows.rental_items),
        (DamageReport, rows.damage_reports),
        (Charge, rows.charges),
    )
    connection = session.connection().execution_options(
        insertmanyvalues_page_size=INSERT_BATCH_ROWS
    )
    statements = 0
    for table, table_rows in tables:
        if not table_rows:
            continue
        written = len(
            connection.execute(
                insert(table).returning(literal_column(KEY_COLUMN)), table_rows
            ).all()
        )
        if written != len(table_rows):
            raise SeedDataError(
                f"Wrote {written} of {len(table_rows)} rows of {table.__name__}. The "
                "transaction is rolled back and nothing of the history is kept."
            )
        statements += -(-len(table_rows) // INSERT_BATCH_ROWS)
    return statements


def log_created(
    plan: Sequence[PlannedHire], rows: HistoryRows, statements: int, timings: Timings
) -> None:
    """Say what the season holds, where its references are and how long each phase took."""
    reports = [hire.damage for hire in plan if hire.damage is not None]
    logger.info(
        "seed.trading_history_created",
        extra={
            "season": f"{SEASON_FIRST_DAY.isoformat()} to {SEASON_LAST_DAY.isoformat()}",
            "hire_count": len(plan),
            "late_return_count": sum(hire.returned_on > hire.period.end for hire in plan),
            "damaged_count": len(reports),
            "chargeable_damage_count": sum(
                report.plan.recovery_inc_vat is not None for report in reports
            ),
            "reservation_references": _first_and_last(
                hire.reservation_reference for hire in plan
            ),
            "rental_references": _first_and_last(hire.rental_reference for hire in plan),
            "damage_references": _first_and_last(report.reference for report in reports),
            "rows_by_table": dict(counts_of(rows)),
            "insert_statements": statements,
            "read_and_plan_ms": _milliseconds(timings.started, timings.planned),
            "domain_ms": _milliseconds(timings.planned, timings.run),
            "insert_ms": _milliseconds(timings.run, timings.written),
            "elapsed_ms": _milliseconds(timings.started, timings.written),
        },
    )


def _milliseconds(begun: float, ended: float) -> int:
    """Return the whole milliseconds between two readings of the performance counter."""
    return round((ended - begun) * MILLISECONDS)


def _first_and_last(references: Iterable[str]) -> str:
    """Return the first and the last of some references, or none when there are none."""
    ordered = sorted(references)
    return f"{ordered[0]} to {ordered[-1]}" if ordered else "none"
