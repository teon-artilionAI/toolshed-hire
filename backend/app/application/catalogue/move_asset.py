"""The use case by which an administrator moves a unit through its lifecycle by hand (US-31, US-32).

A unit leaves INTAKE for the shelf or for quarantine, is taken out of service,
is put back once it is fit, comes back from LOST into quarantine when it is
found, and is retired at the end of its life. Every move goes through the
asset state model and the guards of `app.domain.asset_transitions`, so a move
the model does not hold is refused naming the status the unit is in, ON_HIRE
and LOST are never set here, and a unit a booking still holds is not retired
(BR-37).

In one unit of work the unit is locked by its tag, the booking that holds it
is looked for when it is to be retired and an open damage report when it is
to go back on the shelf, and the move is written through the asset
repository, which is where every other change of a unit's status is written.
A retirement stamps the business day, and the row is kept for ever, so the
unit stays in the register, in its history and in the report's figures, and
never comes back in the availability search, which offers AVAILABLE units
only (BR-38).

The move writes `asset.status_changed` in the shape checkout, a return, a
loss and a damage report write it, with the reason beside it (BR-49). The
utilisation report rebuilds a unit's days out of service from those events,
so a move made here counts there from the day it was made.
"""

from __future__ import annotations

import logging

from app.application.catalogue.asset_changes import record_hand_move
from app.application.catalogue.asset_commands import MoveUnitCommand
from app.application.catalogue.asset_read_models import AdminAssetDetail
from app.application.catalogue.register_asset import UnitUseCase, locked_unit
from app.application.identity.account_rules import refused_field
from app.domain.asset_transitions import moved_by_hand
from app.domain.enums import AssetStatus
from app.domain.errors import ValidationFailure

logger = logging.getLogger(__name__)


class MoveUnitUseCase(UnitUseCase[MoveUnitCommand]):
    """Move a unit to another status by hand, with its audit event."""

    def execute(self, command: MoveUnitCommand) -> AdminAssetDetail:
        """Move the unit, or refuse and change nothing.

        Raises:
            NotFound: If no unit carries the tag.
            ValidationFailure: Naming `to` for ON_HIRE or LOST, or `reason`
                when a move out of service has none or it is out of bounds.
            StateTransitionError: If the move is not one the unit may make
                from its status, or a booking or an open report holds it.

        """
        target = command.target
        logger.info(
            "asset.move_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "asset_tag": command.asset_tag,
                "to_status": target.value,
                "has_reason": bool(command.reason),
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            unit = locked_unit(uow, command.asset_tag).unit
            register = uow.asset_register
            holding = (
                register.holding_reservation(unit.id) if target is AssetStatus.RETIRED else None
            )
            open_report = (
                register.open_damage_report(unit.id) if target is AssetStatus.AVAILABLE else None
            )
            try:
                move = moved_by_hand(
                    unit,
                    target,
                    reason=command.reason,
                    today=today,
                    holding_reservation=holding,
                    open_damage_report=open_report,
                )
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            uow.assets.save_units([move.unit])
            record_hand_move(uow, actor=command.actor, move=move, now=now)
            uow.commit()
        logger.info(
            "asset.moved",
            extra={
                "asset_tag": unit.asset_tag,
                "from_status": move.unit_before.status.value,
                "to_status": move.unit.status.value,
                "retired_on": move.unit.retired_on.isoformat() if move.unit.retired_on else None,
            },
        )
        return self._answer(unit.asset_tag)
