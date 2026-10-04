"""How a change to the asset register is recorded in the audit trail (FR-23, BR-34, BR-49).

Every change to a unit writes one audit event in the transaction of the change
(BR-49), about the unit itself, so the history of a unit reads them back by
its key.

1. `asset.registered` records every field of the new unit as it became, with
   the code of its branch, and its status, which is INTAKE.
2. `asset.updated` records the paperwork that changed and nothing else, each
   field as it was and as it became.
3. `asset.status_changed` is the action checkout, a return, a loss and every
   move of a damage report already write when a unit changes status, and the
   utilisation report rebuilds a unit's days out of service from it. A move by
   hand writes the same shape, the status before, and after it the status, the
   tag and the day it was retired, with the reason the administrator gave
   beside them.

Money is written as text with two decimals, a day as `YYYY-MM-DD` and a key as
text, so an event never holds a float.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.catalogue.catalogue_changes import MONEY_TEXT, State
from app.application.hire.rental_audit import ASSET_ENTITY_TYPE, ASSET_STATUS_CHANGED_ACTION
from app.application.unit_of_work import UnitOfWork
from app.domain import asset_register as unit_fields
from app.domain.asset_register import RegisteredUnit, UnitDetails
from app.domain.asset_transitions import HandMove
from app.domain.identity import Actor

UNIT_REGISTERED_ACTION: Final[str] = "asset.registered"
UNIT_UPDATED_ACTION: Final[str] = "asset.updated"
STATUS_KEY: Final[str] = "status"
TAG_KEY: Final[str] = "asset_tag"
RETIRED_ON_KEY: Final[str] = "retired_on"
REASON_KEY: Final[str] = "reason"


def details_state(details: UnitDetails) -> State:
    """Return the paperwork of a unit as an audit event records it."""
    return {
        unit_fields.SERIAL_NUMBER: details.serial_number,
        unit_fields.CONDITION_GRADE: details.condition_grade.value,
        unit_fields.HOUR_METER_READING: details.hour_meter_reading,
        unit_fields.NOTES: details.notes,
    }


def unit_state(registered: RegisteredUnit, branch_code: str) -> State:
    """Return every field of a new unit as an audit event records it."""
    unit = registered.unit
    return {
        TAG_KEY: unit.asset_tag,
        unit_fields.MODEL_ID: str(unit.product_model_id),
        unit_fields.BRANCH_CODE: branch_code,
        STATUS_KEY: unit.status.value,
        unit_fields.ACQUIRED_ON: registered.acquired_on.isoformat(),
        unit_fields.ACQUISITION_COST: MONEY_TEXT.format(registered.acquisition_cost),
        **details_state(registered.details),
    }


def record_unit_change(
    uow: UnitOfWork,
    *,
    actor: Actor,
    registered: RegisteredUnit,
    action: str,
    now: datetime,
    before: State | None,
    after: State,
) -> None:
    """Record the audit event of a registration or an edit, in the transaction of the change."""
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=ASSET_ENTITY_TYPE,
            entity_id=registered.unit.id,
            action=action,
            occurred_at=now,
            before_state=before,
            after_state=after,
        )
    )


def record_hand_move(uow: UnitOfWork, *, actor: Actor, move: HandMove, now: datetime) -> None:
    """Record a move by hand in the shape every change of a unit's status is recorded in."""
    unit = move.unit
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=ASSET_ENTITY_TYPE,
            entity_id=unit.id,
            action=ASSET_STATUS_CHANGED_ACTION,
            occurred_at=now,
            before_state={STATUS_KEY: move.unit_before.status.value},
            after_state={
                STATUS_KEY: unit.status.value,
                TAG_KEY: unit.asset_tag,
                RETIRED_ON_KEY: unit.retired_on.isoformat() if unit.retired_on else None,
                REASON_KEY: move.reason,
            },
        )
    )


__all__ = [
    "ASSET_ENTITY_TYPE",
    "ASSET_STATUS_CHANGED_ACTION",
    "UNIT_REGISTERED_ACTION",
    "UNIT_UPDATED_ACTION",
    "details_state",
    "record_hand_move",
    "record_unit_change",
    "unit_state",
]
