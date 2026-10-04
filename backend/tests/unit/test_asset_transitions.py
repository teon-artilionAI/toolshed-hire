"""The moves an administrator makes by hand through a unit's lifecycle, with no database (US-31).

The moves offered by hand are the moves of the asset state model less ON_HIRE
and LOST, which only checkout and the loss route set, and none at all for a
unit on hire, which leaves that status through its return or its loss. Every
move offered is made, and every pairing the model does not permit is refused
naming the status the unit is in. Taking a unit out of service needs a
reason. A unit a booking holds is not retired and the refusal names the
booking (BR-37), a unit with a damage report open goes back on the shelf with
the report, and a retirement stamps the day.
"""

from __future__ import annotations

from datetime import date
from itertools import product
from typing import Final
from uuid import uuid4

import pytest

from app.domain.asset_lifecycle import PERMITTED_ASSET_MOVES
from app.domain.asset_transitions import (
    NEEDS_A_REASON,
    TARGET_FIELD,
    HandMove,
    checked_reason,
    moved_by_hand,
    transitions_by_hand,
)
from app.domain.catalogue import Asset
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.override_reason import REASON_FIELD

A: Final = AssetStatus
TODAY: Final[date] = date(2026, 3, 2)
TAG: Final[str] = "TSH-DR-0042"
REASON: Final[str] = "Failed its inspection on arrival."
BOOKING: Final[str] = "TSH-R-26-000124"
REPORT: Final[str] = "TSH-D-26-00031"
# What an administrator may do by hand from each status.
BY_HAND: Final[dict[AssetStatus, tuple[AssetStatus, ...]]] = {
    A.INTAKE: (A.AVAILABLE, A.QUARANTINED),
    A.AVAILABLE: (A.QUARANTINED, A.UNDER_REPAIR, A.RETIRED),
    A.ON_HIRE: (),
    A.QUARANTINED: (A.AVAILABLE, A.UNDER_REPAIR, A.RETIRED),
    A.UNDER_REPAIR: (A.AVAILABLE, A.RETIRED),
    A.LOST: (A.QUARANTINED, A.RETIRED),
    A.RETIRED: (),
}
OFFERED: Final[list[tuple[AssetStatus, AssetStatus]]] = [
    (status, target) for status, targets in BY_HAND.items() for target in targets
]
NOT_PERMITTED: Final[list[tuple[AssetStatus, AssetStatus]]] = [
    (status, target)
    for status, target in product(AssetStatus, AssetStatus)
    if status is not A.ON_HIRE
    and target not in (A.ON_HIRE, A.LOST)
    and target not in PERMITTED_ASSET_MOVES[status]
]


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


def move(
    status: AssetStatus,
    target: AssetStatus,
    *,
    reason: str | None = REASON,
    holding: str | None = None,
    report: str | None = None,
) -> HandMove:
    """Move a unit in a status by hand."""
    return moved_by_hand(
        a_unit(status),
        target,
        reason=reason,
        today=TODAY,
        holding_reservation=holding,
        open_damage_report=report,
    )


@pytest.mark.parametrize("status", list(AssetStatus))
def test_the_moves_offered_by_hand_are_the_table_less_the_two_set_elsewhere(
    status: AssetStatus,
) -> None:
    assert transitions_by_hand(status) == BY_HAND[status]


@pytest.mark.parametrize(("status", "target"), OFFERED)
def test_every_move_offered_is_made_and_the_unit_handed_in_is_not_changed(
    status: AssetStatus, target: AssetStatus
) -> None:
    unit = a_unit(status)
    made = moved_by_hand(
        unit, target, reason=REASON, today=TODAY, holding_reservation=None, open_damage_report=None
    )
    assert (made.unit.status, made.unit_before, made.reason) == (target, unit, REASON)
    assert unit.status is status
    assert made.unit.retired_on == (TODAY if target is A.RETIRED else None)


@pytest.mark.parametrize(("status", "target"), NOT_PERMITTED)
def test_a_move_the_table_does_not_hold_is_refused_naming_the_status_held(
    status: AssetStatus, target: AssetStatus
) -> None:
    with pytest.raises(StateTransitionError) as refusal:
        move(status, target)
    assert (refusal.value.from_status, refusal.value.to_status) == (status.value, target.value)
    assert TAG in refusal.value.message


@pytest.mark.parametrize(
    ("status", "target"), list(product(AssetStatus, (A.ON_HIRE, A.LOST)))
)
def test_on_hire_and_lost_are_never_set_by_hand_and_the_refusal_names_to(
    status: AssetStatus, target: AssetStatus
) -> None:
    with pytest.raises(ValidationFailure) as refusal:
        move(status, target)
    assert refusal.value.detail[REFUSED_FIELD] == TARGET_FIELD


@pytest.mark.parametrize("target", [A.AVAILABLE, A.QUARANTINED])
def test_a_unit_on_hire_comes_off_hire_through_its_return_and_not_by_hand(
    target: AssetStatus,
) -> None:
    with pytest.raises(StateTransitionError, match="return or its loss") as refusal:
        move(A.ON_HIRE, target)
    assert refusal.value.from_status == A.ON_HIRE.value


@pytest.mark.parametrize("target", sorted(NEEDS_A_REASON))
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_taking_a_unit_out_of_service_needs_a_reason(
    target: AssetStatus, reason: str | None
) -> None:
    with pytest.raises(ValidationFailure, match="5 to 200 characters") as refusal:
        move(A.AVAILABLE, target, reason=reason)
    assert refusal.value.detail[REFUSED_FIELD] == REASON_FIELD


def test_a_reason_given_is_trimmed_and_held_to_its_bounds() -> None:
    assert checked_reason(A.QUARANTINED, f"  {REASON}  ") == REASON
    assert checked_reason(A.AVAILABLE, None) is None
    with pytest.raises(ValidationFailure) as refusal:
        checked_reason(A.AVAILABLE, "ok")
    assert refusal.value.detail[REFUSED_FIELD] == REASON_FIELD


def test_putting_a_unit_back_on_the_shelf_needs_no_reason() -> None:
    made = moved_by_hand(
        a_unit(A.QUARANTINED),
        A.AVAILABLE,
        reason=None,
        today=TODAY,
        holding_reservation=None,
        open_damage_report=None,
    )
    assert (made.unit.status, made.reason) == (A.AVAILABLE, None)


@pytest.mark.parametrize("status", [A.AVAILABLE, A.QUARANTINED, A.UNDER_REPAIR])
def test_a_unit_a_booking_holds_is_not_retired_and_the_booking_is_named(
    status: AssetStatus,
) -> None:
    with pytest.raises(StateTransitionError) as refusal:
        move(status, A.RETIRED, holding=BOOKING)
    assert BOOKING in refusal.value.message
    assert (refusal.value.to_status, refusal.value.rule) == (A.RETIRED.value, "BR-37")


@pytest.mark.parametrize("status", [A.QUARANTINED, A.UNDER_REPAIR, A.INTAKE])
def test_a_unit_with_a_report_open_goes_back_on_the_shelf_with_its_report(
    status: AssetStatus,
) -> None:
    with pytest.raises(StateTransitionError) as refusal:
        move(status, A.AVAILABLE, report=REPORT)
    assert REPORT in refusal.value.message


def test_a_booking_or_a_report_only_stops_the_move_it_is_about() -> None:
    quarantined = move(A.AVAILABLE, A.QUARANTINED, holding=BOOKING, report=REPORT)
    retired = move(A.QUARANTINED, A.RETIRED, report=REPORT)
    assert (quarantined.unit.status, retired.unit.retired_on) == (A.QUARANTINED, TODAY)
