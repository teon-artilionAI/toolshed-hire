"""Registering a unit and editing its paperwork, run against ports and nothing else (FR-23).

A unit is registered at INTAKE with `asset.registered`, and its paperwork is
edited with `asset.updated` recording only what changed. A model nobody can
find, a branch that is not trading and a tag another unit carries are refused
naming the field, whether the check finds the tag or the unique constraint
does. A refused write, and a write whose audit event fails, commits nothing.
The moves by hand are in tests/unit/test_move_unit_use_case.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.catalogue.admin_commands import Change
from app.application.catalogue.asset_changes import UNIT_REGISTERED_ACTION, UNIT_UPDATED_ACTION
from app.application.catalogue.asset_commands import (
    EditUnitCommand,
    RegisterUnitCommand,
    UnitChanges,
)
from app.application.catalogue.asset_read_models import AdminAssetDetail
from app.application.catalogue.register_asset import EditUnitUseCase, RegisterUnitUseCase
from app.domain.asset_register import NewUnitTerms
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import NotFound, ValidationFailure
from tests.support.catalogue_terms import ADMINISTRATOR
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.memory_register import (
    COMMIT,
    MemoryAssetRegister,
    MemoryRegisterUnitOfWork,
    RegisterStore,
    StoreFault,
)
from tests.support.register_terms import (
    HELD_TAG,
    TODAY,
    paperwork,
    refused_name,
    stocked,
)
from tests.support.register_terms import NEW_TAG as TAG


def register(store: RegisterStore, **changes: object) -> AdminAssetDetail:
    """Register the new hammer at CBD, with any field of the command changed."""
    model_id = next(iter(store.models))
    command = RegisterUnitCommand(
        actor=ADMINISTRATOR,
        model_id=model_id,
        branch_code="CBD",
        terms=NewUnitTerms(
            asset_tag=TAG,
            acquired_on=date(2026, 2, 1),
            acquisition_cost=Decimal("3900.00"),
            details=paperwork(),
        ),
    )
    use_case = RegisterUnitUseCase(
        MemoryRegisterUnitOfWork(store), FixedClock(), MemoryAssetRegister(store)
    )
    return use_case.execute(replace(command, **changes))


def edit(store: RegisterStore, changes: UnitChanges, tag: str = HELD_TAG) -> AdminAssetDetail:
    """Edit the paperwork of a unit."""
    use_case = EditUnitUseCase(
        MemoryRegisterUnitOfWork(store), FixedClock(), MemoryAssetRegister(store)
    )
    return use_case.execute(EditUnitCommand(actor=ADMINISTRATOR, asset_tag=tag, changes=changes))


class TestRegistering:
    """A unit is registered at INTAKE, with an event that records every field."""

    def test_a_new_unit_starts_at_intake_and_is_recorded_whole(self) -> None:
        store, _ = stocked()
        answer = register(store)
        assert (answer.entry.asset_tag, answer.entry.status, answer.entry.branch_code) == (
            TAG,
            AssetStatus.INTAKE,
            "CBD",
        )
        assert answer.entry.allowed_transitions == (AssetStatus.AVAILABLE, AssetStatus.QUARANTINED)
        (event,) = store.events
        assert (event.action, event.entity_type, event.entity_id) == (
            UNIT_REGISTERED_ACTION,
            "asset",
            answer.entry.id,
        )
        assert (event.before_state, event.actor_user_id) == (None, ADMINISTRATOR.user_id)
        assert event.after_state == {
            "asset_tag": TAG,
            "model_id": str(answer.entry.model_id),
            "branch_code": "CBD",
            "status": "INTAKE",
            "acquired_on": "2026-02-01",
            "acquisition_cost": "3900.00",
            "serial_number": "SN-882731",
            "condition_grade": "A",
            "hour_meter_reading": 120,
            "notes": None,
        }
        assert store.committed.changed_at[answer.entry.id] == DEFAULT_INSTANT
        assert store.history_asked == [50]

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"model_id": uuid4()}, "modelId"),
            ({"branch_code": "XYZ"}, "branchCode"),
        ],
    )
    def test_a_model_or_a_branch_nobody_can_find_is_refused_naming_it(
        self, changes: dict[str, object], field: str
    ) -> None:
        store, _ = stocked()
        with pytest.raises(ValidationFailure) as refusal:
            register(store, **changes)
        assert (refused_name(refusal), store.journal) == (field, [])

    def test_a_branch_that_stopped_trading_is_refused_naming_it(self) -> None:
        store, _ = stocked()
        store.closed_branch_codes.add("CBD")
        with pytest.raises(ValidationFailure) as refusal:
            register(store)
        assert refused_name(refusal) == "branchCode"

    def test_a_field_that_breaks_a_rule_is_refused_naming_it_on_the_wire(self) -> None:
        store, _ = stocked()
        terms = NewUnitTerms(
            asset_tag=TAG,
            acquired_on=date(2026, 3, 3),
            acquisition_cost=Decimal("1.00"),
            details=paperwork(),
        )
        with pytest.raises(ValidationFailure) as refusal:
            register(store, terms=terms)
        assert (refused_name(refusal), store.events) == ("acquiredOn", [])

    def test_a_tag_another_unit_carries_is_refused_naming_it(self) -> None:
        store, _ = stocked()
        terms = NewUnitTerms(
            asset_tag=HELD_TAG,
            acquired_on=TODAY,
            acquisition_cost=Decimal("1.00"),
            details=paperwork(),
        )
        with pytest.raises(ValidationFailure, match="already carries") as refusal:
            register(store, terms=terms)
        assert refused_name(refusal) == "assetTag"

    def test_a_tag_lost_to_the_unique_constraint_is_refused_the_same_way(self) -> None:
        store, _ = stocked()
        store.race_on_tag = True
        with pytest.raises(ValidationFailure) as refusal:
            register(store)
        assert (refused_name(refusal), store.journal) == ("assetTag", [])

    def test_a_registration_whose_event_fails_keeps_nothing(self) -> None:
        store, held = stocked()
        store.fail_audit = True
        with pytest.raises(StoreFault):
            register(store)
        assert (list(store.committed.units.values()), store.journal) == ([held], [])

    def test_a_unit_that_cannot_be_read_back_is_a_fault_and_not_an_answer(self) -> None:
        store, _ = stocked()
        store.forget_answers = True
        with pytest.raises(LookupError, match=TAG):
            register(store)
        assert store.journal == [COMMIT]


class TestEditing:
    """An edit changes the paperwork it names and records only what changed."""

    def test_named_fields_change_and_the_event_records_them_before_and_after(self) -> None:
        store, held = stocked()
        answer = edit(
            store,
            UnitChanges(
                serial_number=Change(None),
                condition_grade=Change(ConditionGrade.B),
                notes=Change("  Chuck replaced.  "),
            ),
        )
        assert (answer.entry.serial_number, answer.entry.condition_grade, answer.entry.notes) == (
            None,
            ConditionGrade.B,
            "Chuck replaced.",
        )
        assert answer.entry.hour_meter_reading == 120
        (event,) = store.events
        assert (event.action, event.entity_id) == (UNIT_UPDATED_ACTION, held.unit.id)
        assert event.before_state == {
            "serial_number": "SN-882731",
            "condition_grade": "A",
            "notes": None,
        }
        assert event.after_state == {
            "serial_number": None,
            "condition_grade": "B",
            "notes": "Chuck replaced.",
        }
        stored = store.unit_tagged(HELD_TAG)
        assert stored is not None
        assert (stored.unit.status, stored.unit.asset_tag) == (AssetStatus.AVAILABLE, HELD_TAG)

    def test_an_edit_that_changes_nothing_writes_nothing(self) -> None:
        store, _ = stocked()
        answer = edit(store, UnitChanges(hour_meter_reading=Change(120)))
        assert (answer.entry.hour_meter_reading, store.events, store.journal) == (120, [], [])

    def test_paperwork_that_breaks_a_rule_is_refused_naming_it(self) -> None:
        store, _ = stocked()
        with pytest.raises(ValidationFailure) as refusal:
            edit(store, UnitChanges(hour_meter_reading=Change(-1)))
        assert (refused_name(refusal), store.journal) == ("hourMeterReading", [])

    def test_a_tag_nobody_carries_is_not_found(self) -> None:
        store, _ = stocked()
        with pytest.raises(NotFound):
            edit(store, UnitChanges(notes=Change("x")), tag="TSH-ZZ-0000")
