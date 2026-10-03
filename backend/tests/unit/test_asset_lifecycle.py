"""The asset states, which are the life of a tagged unit in the fleet.

The design document lists the moves a unit may make between its seven
statuses. The table in `app.domain.asset_lifecycle` is that list, and these
pin it entry by entry, so a move added or lost there fails here. Every pair of
statuses is then asked, so a permitted move is made and every other one is
refused in a sentence that names the unit.
"""

from __future__ import annotations

from itertools import product
from typing import Final
from uuid import uuid4

import pytest

from app.domain.asset_lifecycle import (
    PERMITTED_ASSET_MOVES,
    UNIT_MOVE_IN_WORDS,
    UNIT_STANDING_IN_WORDS,
    asset_may_move,
    moved,
)
from app.domain.catalogue import Asset
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import StateTransitionError

A: Final = AssetStatus
# The permitted moves as the design document lists them, and nothing else.
DOCUMENTED_MOVES: Final[dict[AssetStatus, set[AssetStatus]]] = {
    A.INTAKE: {A.AVAILABLE, A.QUARANTINED},
    A.AVAILABLE: {A.ON_HIRE, A.QUARANTINED, A.UNDER_REPAIR, A.RETIRED},
    A.ON_HIRE: {A.AVAILABLE, A.QUARANTINED, A.LOST},
    A.QUARANTINED: {A.AVAILABLE, A.UNDER_REPAIR, A.RETIRED},
    A.UNDER_REPAIR: {A.AVAILABLE, A.RETIRED},
    A.LOST: {A.QUARANTINED, A.RETIRED},
    A.RETIRED: set(),
}
PAIRS: Final[list[tuple[AssetStatus, AssetStatus]]] = list(product(AssetStatus, AssetStatus))
TAG: Final[str] = "TSH-DR-0042"


def a_unit(status: AssetStatus) -> Asset:
    """Return one tagged unit in a status."""
    return Asset(
        id=uuid4(),
        asset_tag=TAG,
        product_model_id=uuid4(),
        branch_id=uuid4(),
        status=status,
        condition_grade=ConditionGrade.A,
    )


def test_the_table_is_the_documented_list_of_moves() -> None:
    assert {status: set(targets) for status, targets in PERMITTED_ASSET_MOVES.items()} == (
        DOCUMENTED_MOVES
    )


def test_every_status_has_its_words_in_both_directions() -> None:
    assert set(UNIT_STANDING_IN_WORDS) == set(AssetStatus) == set(UNIT_MOVE_IN_WORDS)


@pytest.mark.parametrize(("current", "target"), PAIRS, ids=[f"{a}->{b}" for a, b in PAIRS])
def test_a_move_is_made_exactly_when_the_table_permits_it(
    current: AssetStatus, target: AssetStatus
) -> None:
    unit = a_unit(current)
    if target in DOCUMENTED_MOVES[current]:
        assert asset_may_move(current, target)
        after = moved(unit, target)
        assert (after.status, after.id, after.asset_tag) == (target, unit.id, unit.asset_tag)
        assert unit.status is current, "The unit passed in was changed."
    else:
        assert not asset_may_move(current, target)
        with pytest.raises(StateTransitionError) as refusal:
            moved(unit, target)
        assert (refusal.value.from_status, refusal.value.to_status) == (
            current.value,
            target.value,
        )


def test_a_refusal_names_the_unit_and_where_it_is() -> None:
    with pytest.raises(StateTransitionError) as refusal:
        moved(a_unit(AssetStatus.UNDER_REPAIR), AssetStatus.ON_HIRE)
    assert refusal.value.message == "Unit TSH-DR-0042 is under repair, so it cannot be handed over."


def test_a_retired_unit_moves_nowhere() -> None:
    retired = a_unit(AssetStatus.RETIRED)
    for target in AssetStatus:
        with pytest.raises(StateTransitionError):
            moved(retired, target)
