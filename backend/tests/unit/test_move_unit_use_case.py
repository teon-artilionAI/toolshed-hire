"""Moving a unit by hand, run against ports and nothing else (US-31, US-32, BR-37).

A unit is moved through its lifecycle with `asset.status_changed`, in the
shape every other change of a unit's status is recorded in, with the reason
beside it. A retirement stamps the day. A unit a booking holds is not retired
and a unit with a report open is not put back by hand. A field refused is
named on the wire, a move the lifecycle does not hold names the status, and
a refused move, or one whose audit event fails, commits nothing.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.application.catalogue.asset_commands import MoveUnitCommand
from app.application.catalogue.asset_read_models import AdminAssetDetail
from app.application.catalogue.move_asset import MoveUnitUseCase
from app.application.hire.rental_audit import ASSET_STATUS_CHANGED_ACTION
from app.domain.enums import AssetStatus
from app.domain.errors import NotFound, StateTransitionError, ValidationFailure
from tests.support.catalogue_terms import ADMINISTRATOR
from tests.support.clock import FixedClock
from tests.support.memory_register import (
    MemoryAssetRegister,
    MemoryRegisterUnitOfWork,
    RegisterStore,
    StoreFault,
)
from tests.support.register_terms import HELD_TAG, REASON, TODAY, refused_name, stocked


def move(
    store: RegisterStore, target: AssetStatus, reason: str | None = REASON, tag: str = HELD_TAG
) -> AdminAssetDetail:
    """Move a unit by hand."""
    use_case = MoveUnitUseCase(
        MemoryRegisterUnitOfWork(store), FixedClock(), MemoryAssetRegister(store)
    )
    return use_case.execute(
        MoveUnitCommand(actor=ADMINISTRATOR, asset_tag=tag, target=target, reason=reason)
    )


class TestMoving:
    """A move by hand goes through the lifecycle and records the shape every move records."""

    def test_a_move_out_of_service_records_the_status_before_and_after_and_the_reason(
        self,
    ) -> None:
        store, held = stocked()
        answer = move(store, AssetStatus.QUARANTINED)
        assert (answer.entry.status, answer.entry.allowed_transitions) == (
            AssetStatus.QUARANTINED,
            (AssetStatus.AVAILABLE, AssetStatus.UNDER_REPAIR, AssetStatus.RETIRED),
        )
        (event,) = store.events
        assert (event.action, event.entity_type, event.entity_id) == (
            ASSET_STATUS_CHANGED_ACTION,
            "asset",
            held.unit.id,
        )
        assert event.before_state == {"status": "AVAILABLE"}
        assert event.after_state == {
            "status": "QUARANTINED",
            "asset_tag": HELD_TAG,
            "retired_on": None,
            "reason": REASON,
        }

    def test_a_retirement_stamps_the_day_and_keeps_the_unit(self) -> None:
        store, _ = stocked()
        answer = move(store, AssetStatus.RETIRED)
        assert (answer.entry.status, answer.entry.retired_on) == (AssetStatus.RETIRED, TODAY)
        assert answer.entry.allowed_transitions == ()
        assert store.events[0].after_state is not None
        assert store.events[0].after_state["retired_on"] == "2026-03-02"

    def test_a_unit_a_booking_holds_is_not_retired_and_nothing_is_written(self) -> None:
        store, held = stocked()
        store.held_by[held.unit.id] = "TSH-R-26-000124"
        with pytest.raises(StateTransitionError, match="TSH-R-26-000124"):
            move(store, AssetStatus.RETIRED)
        assert (store.journal, store.unit_tagged(HELD_TAG)) == ([], held)

    def test_a_unit_with_a_report_open_is_not_put_back_by_hand(self) -> None:
        store, held = stocked()
        store.keep(replace(held, unit=replace(held.unit, status=AssetStatus.QUARANTINED)))
        store.open_reports[held.unit.id] = "TSH-D-26-00031"
        with pytest.raises(StateTransitionError, match="TSH-D-26-00031"):
            move(store, AssetStatus.AVAILABLE, reason=None)
        assert store.journal == []

    def test_a_unit_back_on_the_shelf_needs_no_reason(self) -> None:
        store, held = stocked()
        store.keep(replace(held, unit=replace(held.unit, status=AssetStatus.UNDER_REPAIR)))
        answer = move(store, AssetStatus.AVAILABLE, reason=None)
        assert answer.entry.status is AssetStatus.AVAILABLE
        assert store.events[0].after_state is not None
        assert store.events[0].after_state["reason"] is None

    @pytest.mark.parametrize(
        ("target", "reason", "field"),
        [(AssetStatus.ON_HIRE, REASON, "to"), (AssetStatus.UNDER_REPAIR, None, "reason")],
    )
    def test_a_refused_field_is_named_and_nothing_is_written(
        self, target: AssetStatus, reason: str | None, field: str
    ) -> None:
        store, _ = stocked()
        with pytest.raises(ValidationFailure) as refusal:
            move(store, target, reason=reason)
        assert (refused_name(refusal), store.journal) == (field, [])

    def test_a_move_the_lifecycle_does_not_hold_is_refused_naming_the_status(self) -> None:
        store, _ = stocked()
        with pytest.raises(StateTransitionError) as refusal:
            move(store, AssetStatus.INTAKE)
        assert refusal.value.from_status == "AVAILABLE"
        assert store.journal == []

    def test_a_move_whose_event_fails_keeps_the_unit_where_it_was(self) -> None:
        store, held = stocked()
        store.fail_audit = True
        with pytest.raises(StoreFault):
            move(store, AssetStatus.QUARANTINED)
        assert store.unit_tagged(HELD_TAG) == held

    def test_a_tag_nobody_carries_is_not_found(self) -> None:
        store, _ = stocked()
        with pytest.raises(NotFound):
            move(store, AssetStatus.QUARANTINED, tag="TSH-ZZ-0000")
