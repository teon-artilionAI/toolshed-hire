"""What a damage report does to the unit it names (BR-35, BR-37, BR-38).

Filing a report takes the unit out of availability. A unit already out of
service, in quarantine or under repair, stays where it is. Any other is moved
to QUARANTINED through the asset state model, so a retired unit is refused
there with 409. A unit out on hire is refused before that. The asset state
model lets a unit go from ON_HIRE to QUARANTINED, but that move belongs to the
return, so the damage of a unit on hire is reported once it is back.

Sending a report for repair takes the unit to UNDER_REPAIR with it, unless it
is there already. Resolving a report puts the unit back on the shelf once no
other report against it is open. A unit that is not out of service any more,
because another report retired it, stays where it is.

Writing a report off retires the unit and stamps the day (BR-38). It is
refused while the unit holds an active allocation (BR-37), because a booking
would be left holding a unit that no longer exists, and the booking has to be
dealt with first. The row of a retired unit is kept forever, so its hires and
its reports stay readable.

Each function returns the unit as it should now stand and changes nothing it
is handed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Final

from app.domain.asset_lifecycle import moved
from app.domain.catalogue import Asset
from app.domain.enums import AssetStatus
from app.domain.errors import StateTransitionError

ON_HIRE_RULE: Final[str] = "BR-35"
ALLOCATION_RULE: Final[str] = "BR-37"
NO_OTHER_REPORTS: Final[int] = 0
# The statuses of a unit that is already out of availability for its damage.
OUT_OF_SERVICE: Final[frozenset[AssetStatus]] = frozenset(
    {AssetStatus.QUARANTINED, AssetStatus.UNDER_REPAIR}
)


def quarantined_for_report(unit: Asset) -> Asset:
    """Return the unit as a new damage report leaves it, out of availability.

    Raises:
        StateTransitionError: If the unit is out on hire, or its status may
            not move to QUARANTINED, which a retired unit's may not.

    """
    if unit.status in OUT_OF_SERVICE:
        return unit
    if unit.status is AssetStatus.ON_HIRE:
        raise StateTransitionError(
            f"Unit {unit.asset_tag} is out on hire, so its damage cannot be reported yet. "
            "Report it once the unit is back.",
            from_status=unit.status.value,
            to_status=AssetStatus.QUARANTINED.value,
            rule=ON_HIRE_RULE,
        )
    return moved(unit, AssetStatus.QUARANTINED)


def sent_for_repair(unit: Asset) -> Asset:
    """Return the unit as sending its report for repair leaves it, under repair.

    Raises:
        StateTransitionError: If its status may not move to UNDER_REPAIR.

    """
    if unit.status is AssetStatus.UNDER_REPAIR:
        return unit
    return moved(unit, AssetStatus.UNDER_REPAIR)


def back_in_service(unit: Asset, *, other_open_reports: int) -> Asset:
    """Return the unit as resolving one of its reports leaves it.

    Args:
        unit: The unit, locked by the caller.
        other_open_reports: How many reports against it are still open, the
            one being resolved left out.

    Returns:
        The unit back on the shelf when it was out of service for its damage
        and nothing else holds it there, and the unit unchanged otherwise.

    """
    if unit.status not in OUT_OF_SERVICE or other_open_reports > NO_OTHER_REPORTS:
        return unit
    return moved(unit, AssetStatus.AVAILABLE)


def retired(unit: Asset, *, today: date, holds_active_allocation: bool) -> Asset:
    """Return the unit retired on a day, as writing its report off leaves it (BR-38).

    Args:
        unit: The unit, locked by the caller.
        today: The current business day, which becomes its retirement date.
        holds_active_allocation: Whether a booking still holds the unit.

    Raises:
        StateTransitionError: If a booking still holds the unit (BR-37).

    """
    if holds_active_allocation:
        raise StateTransitionError(
            f"Unit {unit.asset_tag} is still held for a booking, so it cannot be written off. "
            "Move or cancel that booking first.",
            from_status=unit.status.value,
            to_status=AssetStatus.RETIRED.value,
            rule=ALLOCATION_RULE,
        )
    if unit.status is AssetStatus.RETIRED:
        return unit
    return replace(moved(unit, AssetStatus.RETIRED), retired_on=today)
