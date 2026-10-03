"""The audit events of damage reports, written in the unit of work of the change (BR-49).

Filing a report, sending it for repair and closing it each write an event for
the report, saying where it stood before and where it stands now. A unit the
report moves writes an `asset.status_changed` of its own, the way a return
writes one, so the history of a unit can be read without its reports. A report
that charges the customer, or completes the assessment of a hire, writes an
event for the rental as well, with the three figures of the deposit.

An event names a unit by its tag. The audit trail is read by staff only, and
the tag is what they know a unit by.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final

from app.application.audit import audit_event_for
from app.application.hire.rental_audit import ASSET_ENTITY_TYPE, ASSET_STATUS_CHANGED_ACTION
from app.application.unit_of_work import UnitOfWork
from app.domain.audit import StateValue
from app.domain.catalogue import Asset
from app.domain.damage import DamageReport
from app.domain.enums import DamageStatus
from app.domain.identity import Actor

DAMAGE_REPORT_ENTITY_TYPE: Final[str] = "damage_report"
DAMAGE_REPORT_FILED_ACTION: Final[str] = "damage_report.filed"
DAMAGE_REPORT_SENT_FOR_REPAIR_ACTION: Final[str] = "damage_report.sent_for_repair"
RENTAL_DAMAGE_ASSESSED_ACTION: Final[str] = "rental.damage_assessed"
# The action of each outcome a report is closed with.
CLOSED_ACTIONS: Final[Mapping[DamageStatus, str]] = MappingProxyType(
    {
        DamageStatus.RESOLVED: "damage_report.resolved",
        DamageStatus.WRITTEN_OFF: "damage_report.written_off",
    }
)


def report_state(report: DamageReport) -> dict[str, StateValue]:
    """Return what an audit event records about where a report stands."""
    return {
        "reference": report.reference,
        "status": report.status.value,
        "severity": report.severity.value,
        "chargeable_to_customer": report.chargeable_to_customer,
        "repair_estimate": str(report.repair_estimate),
        "actual_repair_cost": (
            str(report.actual_repair_cost) if report.actual_repair_cost is not None else None
        ),
        "rental_item_id": str(report.rental_item_id) if report.rental_item_id else None,
    }


def record_report_change(
    uow: UnitOfWork,
    *,
    actor: Actor,
    report: DamageReport,
    action: str,
    occurred_at: datetime,
    before: dict[str, StateValue] | None,
    extra: dict[str, StateValue] | None = None,
) -> None:
    """Record the audit event of one change to a damage report (BR-49).

    Args:
        uow: The open unit of work the change was made in.
        actor: Who made the change.
        report: The report as it is now.
        action: The name of the change, for example `damage_report.filed`.
        occurred_at: When it happened, from the clock.
        before: Where the report stood before, or None when it was filed.
        extra: Anything else the event should say about the change.

    """
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=DAMAGE_REPORT_ENTITY_TYPE,
            entity_id=report.id,
            action=action,
            occurred_at=occurred_at,
            before_state=before,
            after_state={**report_state(report), **(extra or {})},
        )
    )


def record_unit_move(
    uow: UnitOfWork,
    *,
    actor: Actor,
    unit_before: Asset,
    unit: Asset,
    report_reference: str,
    occurred_at: datetime,
) -> bool:
    """Write a unit a report moved and record the move, or do nothing when it did not move.

    Returns:
        True when the unit moved.

    """
    if unit.status is unit_before.status:
        return False
    uow.assets.save_units([unit])
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=ASSET_ENTITY_TYPE,
            entity_id=unit.id,
            action=ASSET_STATUS_CHANGED_ACTION,
            occurred_at=occurred_at,
            before_state={"status": unit_before.status.value},
            after_state={
                "status": unit.status.value,
                "asset_tag": unit.asset_tag,
                "damage_report_reference": report_reference,
                "retired_on": unit.retired_on.isoformat() if unit.retired_on else None,
            },
        )
    )
    return True
