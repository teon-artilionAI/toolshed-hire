"""The moves an administrator makes by hand through a unit's lifecycle (FR-23, US-31, US-32, BR-37).

The asset state model in `app.domain.asset_lifecycle` is the one table of
permitted moves, and every move made here goes through its `moved`. What this
module adds is which of those moves are made by hand, and the guards the
administrator's route holds on top of the table.

1. ON_HIRE and LOST are never set by hand. Checkout puts a unit on hire and
   the loss route records it lost, each in the transaction that opens or
   closes the hire, so a unit cannot be marked on hire with no rental behind
   it. Asking for either is a refusal of the field, whatever the unit's status.
2. A unit on hire leaves that status through its return or its loss and never
   by hand. The table lets a unit go from ON_HIRE back to the shelf, but that
   move belongs to the return, which closes the rental item and lets the
   allocation go with it. A unit on hire therefore has no move by hand at all.
3. A move to QUARANTINED, UNDER_REPAIR or RETIRED takes a reason, because
   taking a unit out of service is a decision somebody has to be able to
   explain later. A reason is held to the rule of an administrator's override,
   five to two hundred characters once trimmed.
4. A unit is not retired while a booking still holds it (BR-37). The refusal
   names the booking, which has to be dealt with first.
5. A unit with a damage report still open goes back on the shelf when that
   report is resolved, and not by hand. Resolving the report is what records
   the repair cost and closes the report's span in the utilisation report, so
   putting the unit back by hand would leave the report open and the unit
   counted as out of service while it is on the shelf.

`transitions_by_hand` reads the same table, so the moves the register offers
are exactly the moves the route accepts and the screen never holds a copy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Final

from app.domain.asset_lifecycle import PERMITTED_ASSET_MOVES, UNIT_MOVE_IN_WORDS, moved
from app.domain.catalogue import Asset
from app.domain.catalogue_forms import field_refusal
from app.domain.enums import AssetStatus
from app.domain.errors import StateTransitionError
from app.domain.override_reason import (
    REASON_FIELD,
    REASON_MAX_LENGTH,
    REASON_MIN_LENGTH,
    written_reason,
)

TARGET_FIELD: Final[str] = "to"
ALLOCATION_RULE: Final[str] = "BR-37"
LIFECYCLE_RULE: Final[str] = "FR-23"
# The statuses only checkout and the loss route set.
SET_BY_THEIR_OWN_ROUTES: Final[frozenset[AssetStatus]] = frozenset(
    {AssetStatus.ON_HIRE, AssetStatus.LOST}
)
# The status a unit only leaves through its return or its loss.
LEFT_BY_ITS_OWN_ROUTES: Final[frozenset[AssetStatus]] = frozenset({AssetStatus.ON_HIRE})
# The moves that take a unit out of service, which have to be explained.
NEEDS_A_REASON: Final[frozenset[AssetStatus]] = frozenset(
    {AssetStatus.QUARANTINED, AssetStatus.UNDER_REPAIR, AssetStatus.RETIRED}
)

NOT_BY_HAND_MESSAGE: Final[str] = (
    "A unit goes on hire at checkout and is recorded as lost from its rental. Choose another "
    "status."
)
REASON_REQUIRED_MESSAGE: Final[str] = (
    "Say why the unit is being {move}, in "
    f"{REASON_MIN_LENGTH} to {REASON_MAX_LENGTH} characters."
)


@dataclass(frozen=True, slots=True)
class HandMove:
    """What a move by hand did, for the caller to store and to record.

    Attributes:
        unit_before: The unit as it stood.
        unit: The unit in its new status, with its retirement stamped when retired.
        reason: The reason given, trimmed, or None when none was needed or given.

    """

    unit_before: Asset
    unit: Asset
    reason: str | None


def transitions_by_hand(status: AssetStatus) -> tuple[AssetStatus, ...]:
    """Return the statuses an administrator may move a unit to by hand, in lifecycle order.

    They are the moves the asset state model permits from the status, less the
    two statuses only their own routes set, and none at all for a unit on hire.
    """
    if status in LEFT_BY_ITS_OWN_ROUTES:
        return ()
    return tuple(
        target
        for target in AssetStatus
        if target in PERMITTED_ASSET_MOVES[status] and target not in SET_BY_THEIR_OWN_ROUTES
    )


def checked_reason(target: AssetStatus, reason: str | None) -> str | None:
    """Return the reason for a move trimmed, or refuse one that is missing or out of bounds.

    A move that takes a unit out of service needs one. Any other may carry one,
    which is held to the same bounds.

    Raises:
        ValidationFailure: Naming `reason`.

    """
    given = (reason or "").strip()
    if not given:
        if target in NEEDS_A_REASON:
            raise field_refusal(
                REASON_FIELD, REASON_REQUIRED_MESSAGE.format(move=UNIT_MOVE_IN_WORDS[target])
            )
        return None
    return written_reason(given)


def moved_by_hand(
    unit: Asset,
    target: AssetStatus,
    *,
    reason: str | None,
    today: date,
    holding_reservation: str | None,
    open_damage_report: str | None,
) -> HandMove:
    """Return the unit moved by an administrator, or refuse and change nothing.

    The fields are decided first and the standing of the unit after, so a
    request that is wrong in itself is told so whatever the unit is doing.

    Args:
        unit: The unit, locked by the caller.
        target: The status it is to move to.
        reason: Why, as the administrator wrote it, or None.
        today: The current business day, which a retirement is stamped with.
        holding_reservation: The reference of a booking that still holds the
            unit, or None. Only a retirement asks.
        open_damage_report: The reference of a damage report of the unit that
            is still open, or None. Only a move back to the shelf asks.

    Raises:
        ValidationFailure: Naming `to` for ON_HIRE or LOST, or `reason` when
            one is needed and missing or is out of bounds.
        StateTransitionError: If the unit is on hire, the asset state model
            does not permit the move, a booking holds a unit being retired
            (BR-37), or an open report holds a unit being put back.

    """
    if target in SET_BY_THEIR_OWN_ROUTES:
        raise field_refusal(TARGET_FIELD, NOT_BY_HAND_MESSAGE, rule=LIFECYCLE_RULE)
    written = checked_reason(target, reason)
    if unit.status in LEFT_BY_ITS_OWN_ROUTES:
        raise StateTransitionError(
            f"Unit {unit.asset_tag} is out on hire, so it comes off hire through its return or "
            "its loss.",
            from_status=unit.status.value,
            to_status=target.value,
            rule=LIFECYCLE_RULE,
        )
    after = moved(unit, target)
    if target is AssetStatus.RETIRED:
        _ensure_not_held(unit, holding_reservation)
        after = replace(after, retired_on=today)
    if target is AssetStatus.AVAILABLE:
        _ensure_no_open_report(unit, open_damage_report)
    return HandMove(unit_before=unit, unit=after, reason=written)


def _ensure_not_held(unit: Asset, holding_reservation: str | None) -> None:
    """Refuse to retire a unit a booking still holds (BR-37).

    Raises:
        StateTransitionError: Naming the booking.

    """
    if holding_reservation is None:
        return
    raise StateTransitionError(
        f"Unit {unit.asset_tag} is held for booking {holding_reservation}, so it cannot be "
        "retired. Release it from that booking first.",
        from_status=unit.status.value,
        to_status=AssetStatus.RETIRED.value,
        rule=ALLOCATION_RULE,
    )


def _ensure_no_open_report(unit: Asset, open_damage_report: str | None) -> None:
    """Refuse to put a unit back on the shelf by hand while one of its damage reports is open.

    Raises:
        StateTransitionError: Naming the report.

    """
    if open_damage_report is None:
        return
    raise StateTransitionError(
        f"Unit {unit.asset_tag} has damage report {open_damage_report} open, so it goes back "
        "on the shelf when that report is resolved.",
        from_status=unit.status.value,
        to_status=AssetStatus.AVAILABLE.value,
        rule=LIFECYCLE_RULE,
    )
