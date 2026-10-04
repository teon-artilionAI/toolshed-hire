"""The statement of the report that reads every dated fact about the units in scope.

Five kinds of fact are read by one `UNION ALL`, each kind narrowed to what
touches the period and to the units in scope, and each standing on an index.

1. A hire is a rental item out at any moment of the period, which is one that
   went out before the period ended and is still out or came back after it
   began. `ix_rental_item_returned_at` finds the second half of that, the
   items still out and the items back since the period began.
2. A loss is a rental item closed with no condition, which is how a lost unit
   is told from one that came back. It runs to the next recorded change of the
   unit's status, a scalar subquery on `ix_audit_event_asset_status`. Lost
   items are few, and `ix_rental_item_lost` holds them and nothing else.
3. A booking is an allocation still active whose reservation is confirmed, or
   held by a hold that has not run out, and whose dates touch the period. The
   reservations are found through the partial indexes
   `ix_reservation_confirmed_start` and `ix_reservation_hold_expiry`, which is
   why each status is written as the literal those indexes are filtered on. A
   confirmed or held reservation has not been collected, so none of its units
   is also a hire. A released allocation is never a booking.
4. A damage report open at any moment of the period, found the way a hire is,
   through `ix_damage_report_resolved_at`.
5. A recorded change of status within the period, through
   `ix_audit_event_occurred_at`.

The columns a kind does not use are typed nulls, so the union has one shape.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Date,
    DateTime,
    Executable,
    Label,
    SelectBase,
    String,
    and_,
    cast,
    func,
    literal_column,
    null,
    or_,
    union_all,
)
from sqlalchemy import select as select_columns
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import col

from app.application.reporting.evidence import EvidenceKind, ReportScope
from app.infrastructure.booking import CONFIRMED_STATUS_LITERAL, HELD_STATUS_LITERAL
from app.infrastructure.models import (
    AssetAllocation,
    AuditEvent,
    DamageReport,
    RentalItem,
    Reservation,
    ReservationLine,
)
from app.infrastructure.report_sql import status_changed, units_in_scope

ORDER_COLUMNS: Final[tuple[str, ...]] = ("asset_id", "began_at", "begins_on", "ordinal")


def dated_statement(scope: ReportScope) -> Executable:
    """Return the one statement that reads every dated fact about the units in scope."""
    union = union_all(
        _hires(scope), _losses(scope), _bookings(scope), _damage(scope), _changes(scope)
    )
    return union.order_by(*(union.selected_columns[name] for name in ORDER_COLUMNS))


def _hires(scope: ReportScope) -> SelectBase:
    """Return the rental items out at any moment of the period."""
    return select_columns(
        col(RentalItem.asset_id).label("asset_id"),
        _kind(EvidenceKind.HIRE),
        col(RentalItem.checked_out_at).label("began_at"),
        col(RentalItem.returned_at).label("ended_at"),
        *_no_dates(),
        *_no_states(),
        _no_ordinal(),
    ).where(
        col(RentalItem.checked_out_at) < scope.ends_at,
        or_(col(RentalItem.returned_at).is_(None), col(RentalItem.returned_at) >= scope.starts_at),
        *units_in_scope(col(RentalItem.asset_id), scope),
    )


def _losses(scope: ReportScope) -> SelectBase:
    """Return every loss recorded before the period ended, up to the next change of status."""
    next_change = (
        select_columns(func.min(col(AuditEvent.occurred_at)))
        .where(
            status_changed(),
            col(AuditEvent.entity_id) == col(RentalItem.asset_id),
            col(AuditEvent.occurred_at) > col(RentalItem.returned_at),
        )
        .scalar_subquery()
    )
    return select_columns(
        col(RentalItem.asset_id).label("asset_id"),
        _kind(EvidenceKind.LOSS),
        col(RentalItem.returned_at).label("began_at"),
        next_change.label("ended_at"),
        *_no_dates(),
        *_no_states(),
        _no_ordinal(),
    ).where(
        col(RentalItem.returned_at).is_not(None),
        col(RentalItem.condition_in).is_(None),
        col(RentalItem.returned_at) < scope.ends_at,
        *units_in_scope(col(RentalItem.asset_id), scope),
    )


def _bookings(scope: ReportScope) -> SelectBase:
    """Return the active allocations of bookings not yet collected that touch the period."""
    confirmed = and_(
        col(Reservation.status) == literal_column(CONFIRMED_STATUS_LITERAL),
        col(Reservation.start_date) < scope.ends_on,
    )
    held = and_(
        col(Reservation.status) == literal_column(HELD_STATUS_LITERAL),
        col(Reservation.hold_expires_at) > scope.now,
    )
    return (
        select_columns(
            col(AssetAllocation.asset_id).label("asset_id"),
            _kind(EvidenceKind.BOOKING),
            *_no_instants(),
            col(AssetAllocation.start_date).label("begins_on"),
            col(AssetAllocation.end_date).label("ends_on"),
            *_no_states(),
            _no_ordinal(),
        )
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .join(Reservation, col(Reservation.id) == col(ReservationLine.reservation_id))
        .where(
            or_(confirmed, held),
            col(AssetAllocation.released_at).is_(None),
            col(AssetAllocation.start_date) < scope.ends_on,
            col(AssetAllocation.end_date) > scope.starts_on,
            *units_in_scope(col(AssetAllocation.asset_id), scope),
        )
    )


def _damage(scope: ReportScope) -> SelectBase:
    """Return the damage reports open at any moment of the period."""
    return select_columns(
        col(DamageReport.asset_id).label("asset_id"),
        _kind(EvidenceKind.DAMAGE),
        col(DamageReport.reported_at).label("began_at"),
        col(DamageReport.resolved_at).label("ended_at"),
        *_no_dates(),
        *_no_states(),
        _no_ordinal(),
    ).where(
        col(DamageReport.reported_at) < scope.ends_at,
        or_(
            col(DamageReport.resolved_at).is_(None),
            col(DamageReport.resolved_at) >= scope.starts_at,
        ),
        *units_in_scope(col(DamageReport.asset_id), scope),
    )


def _changes(scope: ReportScope) -> SelectBase:
    """Return the changes of status recorded within the period."""
    return select_columns(
        col(AuditEvent.entity_id).label("asset_id"),
        _kind(EvidenceKind.STATUS),
        col(AuditEvent.occurred_at).label("began_at"),
        cast(null(), DateTime(timezone=True)).label("ended_at"),
        *_no_dates(),
        col(AuditEvent.before_state).label("before_state"),
        col(AuditEvent.after_state).label("after_state"),
        col(AuditEvent.id).label("ordinal"),
    ).where(
        status_changed(),
        col(AuditEvent.occurred_at) >= scope.starts_at,
        col(AuditEvent.occurred_at) < scope.ends_at,
        *units_in_scope(col(AuditEvent.entity_id), scope),
    )


def _kind(kind: EvidenceKind) -> ColumnElement[str]:
    """Return the kind of a fact as a column, written as a literal."""
    return literal_column(f"'{kind.value}'", String).label("kind")


def _no_instants() -> tuple[Label[datetime], Label[datetime]]:
    """Return the two instant columns of a fact that has days instead."""
    return (
        cast(null(), DateTime(timezone=True)).label("began_at"),
        cast(null(), DateTime(timezone=True)).label("ended_at"),
    )


def _no_dates() -> tuple[Label[date], Label[date]]:
    """Return the two day columns of a fact that has instants instead."""
    return (cast(null(), Date).label("begins_on"), cast(null(), Date).label("ends_on"))


def _no_states() -> tuple[Label[object], Label[object]]:
    """Return the two status columns of a fact that is not a change of status."""
    return (
        cast(null(), JSONB).label("before_state"),
        cast(null(), JSONB).label("after_state"),
    )


def _no_ordinal() -> Label[int]:
    """Return the order column of a fact that is not a change of status."""
    return cast(null(), BigInteger).label("ordinal")
