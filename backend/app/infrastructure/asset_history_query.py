"""The facts a unit's history is built from, read in four statements (FR-23, SC-21).

A unit's life is recorded in four tables, and each is read by one statement
that stands on indexes leading with the unit, so the history is four
statements however long the unit has been in the fleet.

1. Its allocations, the released ones through `ix_asset_allocation_released`
   of revision 0010 and the active ones through the GiST index of the
   exclusion constraint, in two halves of one statement, joined to their
   booking's reference by primary keys.
2. Its rental items, through `ix_rental_item_asset` of the baseline, joined
   to their rental's reference and due date by its primary key.
3. Its damage reports, through `ix_damage_report_asset` of revision 0005.
4. Its audit events, through `ix_audit_event_entity_id` of revision 0008,
   read backwards.

Each statement returns at most `limit` rows, ordered by the latest instant a
row carries, its release, its return or its resolution when it has one and its
start when it has not. An entry of the history is one of those instants, so
the newest `limit` entries are always among the rows read. A unit's own rows
are a few hundred over its life, so sorting them inside the statement is
cheap, and only the audit events, which grow fastest, are read off the end of
their index in the order they are wanted.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final
from uuid import UUID

from sqlalchemy import Executable, RowMapping, Subquery, func, union_all
from sqlalchemy import select as select_columns
from sqlmodel import Session, col

from app.application.catalogue.asset_changes import ASSET_ENTITY_TYPE
from app.application.catalogue.asset_read_models import (
    AllocationFact,
    AssetHistoryFacts,
    AuditFact,
    DamageFact,
    HireFact,
)
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    AssetAllocation,
    AuditEvent,
    DamageReport,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

type Statement = Executable

STATUS_KEY: Final[str] = "status"
REASON_KEY: Final[str] = "reason"
# The keys under which a change of status names the hire or the report it
# belongs to, as checkout, a return, a loss and a damage report write them.
REFERENCE_KEYS: Final[tuple[str, ...]] = ("rental_reference", "damage_report_reference")
ALLOCATED_AT_COLUMN: Final[str] = "asset_allocation.allocated_at"
OCCURRED_AT_COLUMN: Final[str] = "audit_event.occurred_at"
RELEASED_SUBQUERY: Final[str] = "released"
ACTIVE_SUBQUERY: Final[str] = "active"
ALLOCATIONS_SUBQUERY: Final[str] = "allocations"


def history_facts(session: Session, asset_id: UUID, limit: int) -> AssetHistoryFacts:
    """Return the facts of one unit's history, at most `limit` of each kind, newest first."""
    with logged_query(
        logger, "asset.register_history", {"asset_id": str(asset_id), "limit": limit}
    ) as outcome:
        allocations = _rows(session, _allocations(asset_id, limit))
        hires = _rows(session, _hires(asset_id, limit))
        reports = _rows(session, _reports(asset_id, limit))
        events = _rows(session, _events(asset_id, limit))
        outcome.row_count = len(allocations) + len(hires) + len(reports) + len(events)
    return AssetHistoryFacts(
        allocations=tuple(_allocation_of(row) for row in allocations),
        hires=tuple(_hire_of(row) for row in hires),
        damage_reports=tuple(_damage_of(row) for row in reports),
        audit_events=tuple(_audit_of(row) for row in events),
    )


def _rows(session: Session, statement: Statement) -> list[RowMapping]:
    """Run one statement and return its rows as mappings."""
    return list(session.execute(statement).mappings().all())


def _allocations(asset_id: UUID, limit: int) -> Statement:
    """Return the statement of the unit's allocations, the latest instant first.

    The allocations the unit was released from and the ones that hold it now
    are read by two halves of one statement, each written with the predicate
    of the index that holds its rows, so each half stands on its own index.
    """
    released = _allocation_half(asset_id, released=True, limit=limit)
    active = _allocation_half(asset_id, released=False, limit=limit)
    both = union_all(select_columns(released), select_columns(active)).subquery(
        ALLOCATIONS_SUBQUERY
    )
    latest = func.coalesce(both.c.released_at, both.c.allocated_at)
    return (
        select_columns(both)
        .order_by(latest.desc(), both.c.allocation_id.desc())
        .limit(limit)
    )


def _allocation_half(asset_id: UUID, *, released: bool, limit: int) -> Subquery:
    """Return the unit's released or active allocations, the latest instant first.

    A released allocation is ordered by when it was let go and an active one
    by when it was taken, which is the latest instant each carries.
    """
    released_at = col(AssetAllocation.released_at)
    held = released_at.is_not(None) if released else released_at.is_(None)
    latest = released_at if released else col(AssetAllocation.allocated_at)
    return (
        select_columns(
            col(AssetAllocation.id).label("allocation_id"),
            col(AssetAllocation.allocated_at).label("allocated_at"),
            released_at.label("released_at"),
            col(AssetAllocation.release_reason).label("release_reason"),
            col(Reservation.reference).label("reservation_reference"),
            col(AssetAllocation.start_date).label("start_date"),
            col(AssetAllocation.end_date).label("end_date"),
        )
        .select_from(AssetAllocation)
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .join(Reservation, col(Reservation.id) == col(ReservationLine.reservation_id))
        .where(col(AssetAllocation.asset_id) == asset_id, held)
        .order_by(latest.desc(), col(AssetAllocation.id).desc())
        .limit(limit)
        .subquery(RELEASED_SUBQUERY if released else ACTIVE_SUBQUERY)
    )


def _hires(asset_id: UUID, limit: int) -> Statement:
    """Return the statement of the unit's rental items, the latest instant first."""
    latest = func.coalesce(col(RentalItem.returned_at), col(RentalItem.checked_out_at))
    return (
        select_columns(
            col(RentalItem.checked_out_at).label("checked_out_at"),
            col(RentalItem.returned_at).label("returned_at"),
            col(Rental.reference).label("rental_reference"),
            col(RentalItem.condition_out).label("condition_out"),
            col(RentalItem.condition_in).label("condition_in"),
            col(Rental.due_back_on).label("due_back_on"),
        )
        .select_from(RentalItem)
        .join(Rental, col(Rental.id) == col(RentalItem.rental_id))
        .where(col(RentalItem.asset_id) == asset_id)
        .order_by(latest.desc(), col(RentalItem.id).desc())
        .limit(limit)
    )


def _reports(asset_id: UUID, limit: int) -> Statement:
    """Return the statement of the unit's damage reports, the latest instant first."""
    latest = func.coalesce(col(DamageReport.resolved_at), col(DamageReport.reported_at))
    return (
        select_columns(
            col(DamageReport.reported_at).label("reported_at"),
            col(DamageReport.resolved_at).label("resolved_at"),
            col(DamageReport.reference).label("reference"),
            col(DamageReport.severity).label("severity"),
            col(DamageReport.status).label("status"),
        )
        .where(col(DamageReport.asset_id) == asset_id)
        .order_by(latest.desc(), col(DamageReport.id).desc())
        .limit(limit)
    )


def _events(asset_id: UUID, limit: int) -> Statement:
    """Return the statement of the unit's audit events, the newest first."""
    return (
        select_columns(
            col(AuditEvent.occurred_at).label("occurred_at"),
            col(AuditEvent.action).label("action"),
            col(AuditEvent.before_state).label("before_state"),
            col(AuditEvent.after_state).label("after_state"),
        )
        .where(
            col(AuditEvent.entity_id) == asset_id,
            col(AuditEvent.entity_type) == ASSET_ENTITY_TYPE,
        )
        .order_by(col(AuditEvent.occurred_at).desc(), col(AuditEvent.id).desc())
        .limit(limit)
    )


def _allocation_of(row: RowMapping) -> AllocationFact:
    """Return the fact of one allocation row."""
    return AllocationFact(
        allocated_at=required_utc(row["allocated_at"], ALLOCATED_AT_COLUMN),
        released_at=in_utc(row["released_at"]),
        release_reason=row["release_reason"],
        reservation_reference=row["reservation_reference"],
        start_date=row["start_date"],
        end_date=row["end_date"],
    )


def _hire_of(row: RowMapping) -> HireFact:
    """Return the fact of one rental item row."""
    return HireFact(
        checked_out_at=required_utc(row["checked_out_at"], "rental_item.checked_out_at"),
        returned_at=in_utc(row["returned_at"]),
        rental_reference=row["rental_reference"],
        condition_out=row["condition_out"],
        condition_in=row["condition_in"],
        due_back_on=row["due_back_on"],
    )


def _damage_of(row: RowMapping) -> DamageFact:
    """Return the fact of one damage report row."""
    return DamageFact(
        reported_at=required_utc(row["reported_at"], "damage_report.reported_at"),
        resolved_at=in_utc(row["resolved_at"]),
        reference=row["reference"],
        severity=row["severity"],
        status=row["status"],
    )


def _audit_of(row: RowMapping) -> AuditFact:
    """Return the fact of one audit event row, with the parts of its states the history reads."""
    before: Mapping[str, object] = row["before_state"] or {}
    after: Mapping[str, object] = row["after_state"] or {}
    references = (_text(after.get(key)) for key in REFERENCE_KEYS)
    return AuditFact(
        occurred_at=required_utc(row["occurred_at"], OCCURRED_AT_COLUMN),
        action=row["action"],
        before_status=_text(before.get(STATUS_KEY)),
        after_status=_text(after.get(STATUS_KEY)),
        reason=_text(after.get(REASON_KEY)),
        reference=next((reference for reference in references if reference), None),
        changed_fields=tuple(after),
    )


def _text(value: object) -> str | None:
    """Return a value of a stored state when it is text, and None otherwise."""
    return value if isinstance(value, str) else None
