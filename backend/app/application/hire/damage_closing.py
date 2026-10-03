"""The use cases that send a damage report for repair and close it (US-38, BR-37, BR-38).

Both are for an administrator, and the routes admit nobody else. In one unit
of work the report is locked and then its unit, so two administrators acting
on one report, or on two reports of one unit, take turns, and the second sees
what the first committed.

Sending an OPEN report for repair moves it to UNDER_REPAIR and the unit with
it. Closing a report is RESOLVED, with the actual cost of the repair, which
puts the unit back on the shelf once no other report against it is open, or
WRITTEN_OFF, which retires the unit, stamps the day and keeps its row, and is
refused while a booking still holds the unit (BR-37). The rules are the
domain's (`app.domain.damage` and `app.domain.damage_units`). Audit events are
written for the report and for a unit that moved (BR-49).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.hire.damage_audit import (
    CLOSED_ACTIONS,
    DAMAGE_REPORT_SENT_FOR_REPAIR_ACTION,
    record_report_change,
    record_unit_move,
    report_state,
)
from app.application.hire.damage_models import DamageReportDetail, DamageReportKey
from app.application.hire.damage_reads import REPORT_NOT_FOUND_MESSAGE, read_report
from app.application.identity.account_rules import refused_field
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.catalogue import Asset
from app.domain.damage import DamageReport
from app.domain.damage_units import back_in_service, retired, sent_for_repair
from app.domain.enums import DamageStatus
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor, ensure_branch_scope
from app.domain.money import Money

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RepairCommand:
    """A request to send one damage report for repair.

    Attributes:
        actor: The administrator.
        key: The report, by its key or its reference.

    """

    actor: Actor
    key: DamageReportKey


@dataclass(frozen=True, slots=True)
class CloseReportCommand:
    """A request to close one damage report.

    Attributes:
        actor: The administrator.
        key: The report, by its key or its reference.
        outcome: RESOLVED or WRITTEN_OFF.
        actual_repair_cost: What the repair cost. Required to resolve.
        resolution_notes: What the administrator wrote, or None.

    """

    actor: Actor
    key: DamageReportKey
    outcome: DamageStatus
    actual_repair_cost: Money | None
    resolution_notes: str | None


class SendForRepairUseCase(UseCase[RepairCommand, DamageReportDetail]):
    """Send an open report for repair, and its unit with it."""

    def execute(self, command: RepairCommand) -> DamageReportDetail:
        """Send the report for repair, or refuse and change nothing.

        Raises:
            NotFound: If there is no such report.
            StateTransitionError: If the report is not OPEN, or its unit may
                not go for repair.

        """
        actor = command.actor
        _log_requested("damage_report.repair_requested", actor, command.key, None)
        now = self._clock.now()
        with self._uow as uow:
            report, unit = _load_for_change(uow, actor, command.key)
            before = report_state(report)
            report.send_for_repair()
            repaired = sent_for_repair(unit)
            uow.damage_reports.save(report)
            record_unit_move(
                uow,
                actor=actor,
                unit_before=unit,
                unit=repaired,
                report_reference=report.reference,
                occurred_at=now,
            )
            record_report_change(
                uow,
                actor=actor,
                report=report,
                action=DAMAGE_REPORT_SENT_FOR_REPAIR_ACTION,
                occurred_at=now,
                before=before,
            )
            detail = read_report(uow, DamageReportKey.of(report.id))
            uow.commit()
        _log_finished("damage_report.sent_for_repair", detail, repaired)
        return detail


class CloseDamageReportUseCase(UseCase[CloseReportCommand, DamageReportDetail]):
    """Close a report as resolved or written off, and move its unit on."""

    def execute(self, command: CloseReportCommand) -> DamageReportDetail:
        """Close the report, or refuse and change nothing.

        Raises:
            NotFound: If there is no such report.
            ValidationFailure: Naming `actualRepairCost` when a report is
                resolved without it or a cost is below nothing.
            StateTransitionError: If the report is already closed, or a write
                off would retire a unit a booking still holds (BR-37).

        """
        actor = command.actor
        _log_requested("damage_report.close_requested", actor, command.key, command.outcome)
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            report, unit = _load_for_change(uow, actor, command.key)
            before = report_state(report)
            try:
                report.close(
                    command.outcome,
                    actual_repair_cost=command.actual_repair_cost,
                    notes=command.resolution_notes,
                    now=now,
                )
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            if command.outcome is DamageStatus.WRITTEN_OFF:
                after = retired(
                    unit,
                    today=today,
                    holds_active_allocation=uow.damage_reports.holds_active_allocation(unit.id),
                )
            else:
                others = uow.damage_reports.other_open_reports(unit.id, report.id)
                after = back_in_service(unit, other_open_reports=others)
            uow.damage_reports.save(report)
            record_unit_move(
                uow,
                actor=actor,
                unit_before=unit,
                unit=after,
                report_reference=report.reference,
                occurred_at=now,
            )
            record_report_change(
                uow,
                actor=actor,
                report=report,
                action=CLOSED_ACTIONS[command.outcome],
                occurred_at=now,
                before=before,
            )
            detail = read_report(uow, DamageReportKey.of(report.id))
            uow.commit()
        _log_finished("damage_report.closed", detail, after)
        return detail


def _load_for_change(
    uow: UnitOfWork, actor: Actor, key: DamageReportKey
) -> tuple[DamageReport, Asset]:
    """Return the report a caller wants to change and its unit, both locked, or refuse.

    Raises:
        NotFound: If there is no such report.
        BranchScopeError: If the actor is counter staff and the unit is at
            another branch. The routes admit administrators only, so this is
            the second line.

    """
    report = uow.damage_reports.find_for_update(key)
    if report is None:
        logger.info("damage_report.not_found", extra={"damage_report": str(key)})
        raise NotFound(REPORT_NOT_FOUND_MESSAGE, {"damage_report": str(key)})
    (unit,) = uow.assets.lock_units([report.asset_id])
    ensure_branch_scope(actor, unit.branch_id)
    return report, unit


def _log_requested(
    event: str, actor: Actor, key: DamageReportKey, outcome: DamageStatus | None
) -> None:
    """Write the line that says a change to a report was asked for."""
    logger.info(
        event,
        extra={
            "actor_user_id": str(actor.user_id),
            "actor_role": actor.role.value,
            "damage_report": str(key),
            "outcome": outcome.value if outcome is not None else None,
        },
    )


def _log_finished(event: str, detail: DamageReportDetail, unit: Asset) -> None:
    """Write the line that says what a change to a report did."""
    logger.info(
        event,
        extra={
            "reference": detail.reference,
            "damage_report_id": str(detail.id),
            "status": detail.status.value,
            "asset_tag": detail.asset_tag,
            "unit_status": unit.status.value,
        },
    )
