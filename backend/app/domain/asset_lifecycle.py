"""The asset states, which are the rules of a unit's life in the fleet.

A tagged unit moves between seven statuses along the transitions the design
document lists in its asset state model, and along no others. The table below
is that list, written once. A move it does not hold is refused with
`StateTransitionError`, which the API answers with 409, so a unit cannot be
handed over from quarantine or put back on the shelf from retirement by a path
nobody thought to check.

There is deliberately no RESERVED status. A unit that is booked for next week
is AVAILABLE today. What it is booked for lives in its allocations, and a
status that said so as well would be a second source of truth that could
disagree with the exclusion constraint.

Nothing here knows how an asset is stored. A move returns a new `Asset` and the
repository writes it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Final

from app.domain.catalogue import Asset
from app.domain.enums import AssetStatus
from app.domain.errors import StateTransitionError

# Every permitted move, from each status to the statuses it may lead to.
PERMITTED_ASSET_MOVES: Final[Mapping[AssetStatus, frozenset[AssetStatus]]] = MappingProxyType(
    {
        AssetStatus.INTAKE: frozenset({AssetStatus.AVAILABLE, AssetStatus.QUARANTINED}),
        AssetStatus.AVAILABLE: frozenset(
            {
                AssetStatus.ON_HIRE,
                AssetStatus.QUARANTINED,
                AssetStatus.UNDER_REPAIR,
                AssetStatus.RETIRED,
            }
        ),
        AssetStatus.ON_HIRE: frozenset(
            {AssetStatus.AVAILABLE, AssetStatus.QUARANTINED, AssetStatus.LOST}
        ),
        AssetStatus.QUARANTINED: frozenset(
            {AssetStatus.AVAILABLE, AssetStatus.UNDER_REPAIR, AssetStatus.RETIRED}
        ),
        AssetStatus.UNDER_REPAIR: frozenset({AssetStatus.AVAILABLE, AssetStatus.RETIRED}),
        AssetStatus.LOST: frozenset({AssetStatus.QUARANTINED, AssetStatus.RETIRED}),
        AssetStatus.RETIRED: frozenset(),
    }
)

# Where a unit stands, as a member of staff reads it in a refusal.
UNIT_STANDING_IN_WORDS: Final[Mapping[AssetStatus, str]] = MappingProxyType(
    {
        AssetStatus.INTAKE: "still being taken into the fleet",
        AssetStatus.AVAILABLE: "on the shelf",
        AssetStatus.ON_HIRE: "out on hire",
        AssetStatus.QUARANTINED: "in quarantine",
        AssetStatus.UNDER_REPAIR: "under repair",
        AssetStatus.LOST: "recorded as lost",
        AssetStatus.RETIRED: "retired",
    }
)
# What a move to each status would have done, as a member of staff reads it.
UNIT_MOVE_IN_WORDS: Final[Mapping[AssetStatus, str]] = MappingProxyType(
    {
        AssetStatus.INTAKE: "taken into the fleet again",
        AssetStatus.AVAILABLE: "put back on the shelf",
        AssetStatus.ON_HIRE: "handed over",
        AssetStatus.QUARANTINED: "put in quarantine",
        AssetStatus.UNDER_REPAIR: "sent for repair",
        AssetStatus.LOST: "recorded as lost",
        AssetStatus.RETIRED: "retired",
    }
)


def asset_may_move(current: AssetStatus, target: AssetStatus) -> bool:
    """Return True when the asset state model permits a move from one status to another."""
    return target in PERMITTED_ASSET_MOVES[current]


def moved(asset: Asset, target: AssetStatus) -> Asset:
    """Return the unit in its new status, or refuse a move the state model does not permit.

    Args:
        asset: The unit as it stands.
        target: The status it is to move to.

    Returns:
        A copy of the unit in the target status. The unit passed in is not changed.

    Raises:
        StateTransitionError: If the move is not one the asset state model
            lists. The sentence names the unit by its tag and says where it is.

    """
    if not asset_may_move(asset.status, target):
        raise StateTransitionError(
            f"Unit {asset.asset_tag} is {UNIT_STANDING_IN_WORDS[asset.status]}, so it cannot be "
            f"{UNIT_MOVE_IN_WORDS[target]}.",
            from_status=asset.status.value,
            to_status=target.value,
        )
    return replace(asset, status=target)
