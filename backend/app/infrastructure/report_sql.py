"""The statements of the report that read the units in scope and the hire charges they share.

1. `units_statement` reads every unit in scope with its branch, model and
   category, the status the recorded changes left it in on either side of the
   period and the money charged on it directly within the period. The money is
   summed in two derived tables grouped by unit, one over the charges raised
   within the period through `ix_charge_raised_at` and one over the damage
   reports resolved within it through `ix_damage_report_resolved_at`. The two
   statuses are scalar subqueries that read one row each of the partial index
   `ix_audit_event_asset_status`. A unit is in the answer when it was in the
   fleet during the period, or when money was charged or a repair cost was
   recorded on it within the period after it had left, so the totals keep
   every rand of the period.
2. `shared_hire_statement` reads every hire charge raised on a whole hire
   within the period through `ix_charge_raised_at`, with each unit of its hire
   and the booking line that unit was hired on, through `ix_rental_item_rental`
   and the primary keys. Every unit of such a hire is read, inside the scope or
   not, because a unit's share is weighed against all of them.

A charge counts in the period its business day of `raised_at` falls in, which
is the same as the instant falling between the start of the first day and the
start of the day after the period, in Cape Town. A waived charge counts
nothing. A reversal is a negative row of the same type and counts, so it nets
the charge it reverses off. Hire revenue is the HIRE charges, late fees the
LATE_FEE charges, and damage recovery the DAMAGE_RECOVERY charges and the
deposit kept for a lost unit, which is the part of its replacement value the
deposit paid. Every other type of charge is a deposit movement or a correction
of the hire as a whole and is not part of gross contribution.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Executable,
    ScalarSelect,
    Select,
    Subquery,
    and_,
    case,
    func,
    literal_column,
    or_,
)
from sqlalchemy import select as select_columns
from sqlalchemy.orm import Mapped, aliased
from sqlmodel import col

from app.application.reporting.evidence import ReportScope
from app.domain.enums import ChargeStatus, ChargeType
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    AuditEvent,
    Branch,
    Category,
    Charge,
    DamageReport,
    ProductModel,
    RentalItem,
    ReservationLine,
)

# Written as a literal so the planner can match the predicate of the partial index.
STATUS_CHANGED_LITERAL: Final[str] = "'asset.status_changed'"
SINGLE_ROW: Final[int] = 1
HIRE_TYPES: Final[frozenset[ChargeType]] = frozenset({ChargeType.HIRE})
LATE_FEE_TYPES: Final[frozenset[ChargeType]] = frozenset({ChargeType.LATE_FEE})
RECOVERY_TYPES: Final[frozenset[ChargeType]] = frozenset(
    {ChargeType.DAMAGE_RECOVERY, ChargeType.DEPOSIT_FORFEIT}
)
COUNTED_TYPES: Final[frozenset[ChargeType]] = HIRE_TYPES | LATE_FEE_TYPES | RECOVERY_TYPES


def status_changed() -> ColumnElement[bool]:
    """Return the condition of an audit event that records a unit changing status."""
    return col(AuditEvent.action) == literal_column(STATUS_CHANGED_LITERAL)


def charged_within(scope: ReportScope) -> list[ColumnElement[bool]]:
    """Return the conditions of a charge that counts within the period."""
    return [
        col(Charge.raised_at) >= scope.starts_at,
        col(Charge.raised_at) < scope.ends_at,
        col(Charge.status) != ChargeStatus.WAIVED,
    ]


def scope_conditions(scope: ReportScope) -> list[ColumnElement[bool]]:
    """Return the conditions on a unit and its model that the filters of the report set."""
    conditions: list[ColumnElement[bool]] = []
    if scope.branch_id is not None:
        conditions.append(col(Asset.branch_id) == scope.branch_id)
    if scope.category_slug is not None:
        conditions.append(
            col(ProductModel.category_id).in_(_category_and_children(scope.category_slug))
        )
    return conditions


def units_in_scope(column: Mapped[UUID], scope: ReportScope) -> list[ColumnElement[bool]]:
    """Return a condition that keeps a unit key to the units in scope, or none when unfiltered."""
    conditions = scope_conditions(scope)
    if not conditions:
        return []
    chosen = (
        select_columns(col(Asset.id))
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .where(*conditions)
        .correlate(None)
    )
    return [column.in_(chosen)]


def units_statement(scope: ReportScope) -> Select[tuple[object, ...]]:
    """Return the statement that reads every unit in scope with its money of the period."""
    direct = _direct_money(scope)
    repairs = _repair_costs(scope)
    in_fleet = and_(
        col(Asset.acquired_on) < scope.ends_on,
        or_(col(Asset.retired_on).is_(None), col(Asset.retired_on) > scope.starts_on),
    )
    return (
        select_columns(
            col(Asset.id).label("asset_id"),
            col(Asset.asset_tag),
            col(Asset.status),
            col(Asset.acquired_on),
            col(Asset.retired_on),
            col(Branch.code).label("branch_code"),
            col(Branch.name).label("branch_name"),
            col(ProductModel.slug).label("model_slug"),
            col(ProductModel.name).label("model_name"),
            col(Category.slug).label("category_slug"),
            col(Category.name).label("category_name"),
            _last_state_before(scope).label("entry_state"),
            _first_state_after(scope).label("exit_state"),
            direct.c.hire_revenue,
            direct.c.late_fees,
            direct.c.damage_recovery,
            repairs.c.repair_costs,
        )
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .join(Category, col(Category.id) == col(ProductModel.category_id))
        .join(Branch, col(Branch.id) == col(Asset.branch_id))
        .outerjoin(direct, direct.c.asset_id == col(Asset.id))
        .outerjoin(repairs, repairs.c.asset_id == col(Asset.id))
        .where(
            *scope_conditions(scope),
            or_(in_fleet, direct.c.asset_id.is_not(None), repairs.c.asset_id.is_not(None)),
        )
        .order_by(col(Asset.asset_tag))
    )


def shared_hire_statement(scope: ReportScope) -> Executable:
    """Return the statement that reads each unit of every hire charge raised on a whole hire."""
    conditions = [
        *charged_within(scope),
        col(Charge.charge_type) == ChargeType.HIRE,
        col(Charge.rental_item_id).is_(None),
    ]
    in_scope = units_in_scope(col(RentalItem.asset_id), scope)
    if in_scope:
        touched = select_columns(col(RentalItem.rental_id)).where(*in_scope).correlate(None)
        conditions.append(col(Charge.rental_id).in_(touched))
    return (
        select_columns(
            col(Charge.id).label("charge_id"),
            col(Charge.amount_ex_vat),
            col(RentalItem.asset_id),
            col(ReservationLine.line_subtotal_ex_vat).label("line_amount"),
            col(ReservationLine.quantity).label("units_on_line"),
        )
        .join(RentalItem, col(RentalItem.rental_id) == col(Charge.rental_id))
        .join(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .join(Asset, col(Asset.id) == col(RentalItem.asset_id))
        .where(*conditions)
        .order_by(
            col(Charge.raised_at),
            col(Charge.id),
            col(ReservationLine.line_position),
            col(Asset.asset_tag),
        )
    )


def category_count_statement(slug: str) -> Select[tuple[int]]:
    """Return the statement that counts the categories, active or not, with a slug."""
    return select_columns(func.count()).select_from(Category).where(col(Category.slug) == slug)


def _direct_money(scope: ReportScope) -> Subquery:
    """Return the charges raised on one unit within the period, summed by unit and kind."""
    return (
        select_columns(
            col(RentalItem.asset_id).label("asset_id"),
            _summed_where(HIRE_TYPES).label("hire_revenue"),
            _summed_where(LATE_FEE_TYPES).label("late_fees"),
            _summed_where(RECOVERY_TYPES).label("damage_recovery"),
        )
        .join(RentalItem, col(RentalItem.id) == col(Charge.rental_item_id))
        .where(*charged_within(scope), col(Charge.charge_type).in_(COUNTED_TYPES))
        .group_by(col(RentalItem.asset_id))
        .subquery("direct_money")
    )


def _summed_where(types: Collection[ChargeType]) -> ColumnElement[Decimal]:
    """Return the sum of the amounts ex VAT of the charges of some types, or null for none."""
    return func.sum(case((col(Charge.charge_type).in_(types), col(Charge.amount_ex_vat))))


def _repair_costs(scope: ReportScope) -> Subquery:
    """Return the actual repair costs of the reports resolved within the period, summed by unit."""
    return (
        select_columns(
            col(DamageReport.asset_id).label("asset_id"),
            func.sum(col(DamageReport.actual_repair_cost)).label("repair_costs"),
        )
        .where(
            col(DamageReport.resolved_at) >= scope.starts_at,
            col(DamageReport.resolved_at) < scope.ends_at,
            col(DamageReport.actual_repair_cost).is_not(None),
        )
        .group_by(col(DamageReport.asset_id))
        .subquery("repairs")
    )


def _last_state_before(scope: ReportScope) -> ScalarSelect[object]:
    """Return what the last recorded change of a unit's status before the period left it as."""
    return (
        select_columns(col(AuditEvent.after_state))
        .where(
            status_changed(),
            col(AuditEvent.entity_id) == col(Asset.id),
            col(AuditEvent.occurred_at) < scope.starts_at,
        )
        .order_by(col(AuditEvent.occurred_at).desc(), col(AuditEvent.id).desc())
        .limit(SINGLE_ROW)
        .scalar_subquery()
    )


def _first_state_after(scope: ReportScope) -> ScalarSelect[object]:
    """Return what the first recorded change of a unit's status after the period moved it from."""
    return (
        select_columns(col(AuditEvent.before_state))
        .where(
            status_changed(),
            col(AuditEvent.entity_id) == col(Asset.id),
            col(AuditEvent.occurred_at) >= scope.ends_at,
        )
        .order_by(col(AuditEvent.occurred_at), col(AuditEvent.id))
        .limit(SINGLE_ROW)
        .scalar_subquery()
    )


def _category_and_children(slug: str) -> Select[tuple[UUID]]:
    """Return the keys of the category with this slug and of its children, active or not.

    Both tables are aliased, so the subquery stands on its own inside a
    statement that already joins `category` for the name of each model.
    """
    chosen = aliased(Category)
    member = aliased(Category)
    chosen_id = select_columns(col(chosen.id)).where(col(chosen.slug) == slug).scalar_subquery()
    return select_columns(col(member.id)).where(
        or_(col(member.id) == chosen_id, col(member.parent_category_id) == chosen_id)
    )
