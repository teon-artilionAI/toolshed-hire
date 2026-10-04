"""Reading the asset register and putting a unit's history together, with no database (SC-21).

The list is narrowed by a branch named by its code, and a code no branch has
is refused naming `branchCode`. One unit is read with its history, and a tag
nobody carries is a 404. The history is built from four kinds of fact, each
of which says what happened in a sentence, the newest first, and is cut at
fifty. A search the boundary would refuse is refused again here.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.catalogue.asset_history import HISTORY_LIMIT, history_of
from app.application.catalogue.asset_read_models import (
    AdminAssetSearch,
    AllocationFact,
    AssetHistoryFacts,
    AssetHistoryKind,
    AuditFact,
    DamageFact,
    HireFact,
)
from app.application.catalogue.asset_reads import ListUnitsQuery, ReadAssetRegister
from app.application.refusal import refused_parameter_of
from app.domain.asset_register import NewUnitTerms, UnitDetails, registered
from app.domain.enums import (
    AssetStatus,
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    ReleaseReason,
)
from app.domain.errors import NotFound, ValidationFailure
from tests.support.catalogue_terms import ADMINISTRATOR
from tests.support.memory_register import (
    NO_HISTORY,
    MemoryAssetRegister,
    RegisterStore,
    a_branch,
    a_model,
)

START: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
HOUR: Final[timedelta] = timedelta(hours=1)
K: Final = AssetHistoryKind
REPORT: Final[str] = "TSH-D-26-00031"
RENTAL: Final[str] = "TSH-H-26-000099"


def at(hours: int) -> datetime:
    """Return an instant some hours after the start."""
    return START + hours * HOUR


def stocked() -> tuple[RegisterStore, ReadAssetRegister]:
    """Return a store with two units at two branches, and the read over it."""
    store = RegisterStore()
    model = a_model()
    store.models[model.id] = model
    for code, tag in (("CBD", "TSH-DR-0042"), ("BLV", "TSH-DR-0043")):
        branch = a_branch(code=code, name=f"Branch {code}")
        store.branches[code] = branch
        store.keep(
            registered(
                NewUnitTerms(
                    asset_tag=tag,
                    acquired_on=date(2025, 6, 1),
                    acquisition_cost=Decimal("3900.00"),
                    details=UnitDetails(
                        serial_number=None,
                        condition_grade=ConditionGrade.A,
                        hour_meter_reading=None,
                        notes=None,
                    ),
                ),
                unit_id=uuid4(),
                product_model_id=model.id,
                branch_id=branch.id,
            )
        )
    return store, ReadAssetRegister(MemoryAssetRegister(store))


class TestTheList:
    """The list is narrowed by a branch named by its code."""

    def test_the_list_is_narrowed_to_the_branch_named(self) -> None:
        _, reads = stocked()
        page = reads.page(ADMINISTRATOR, ListUnitsQuery(branch_code="BLV"))
        assert ([entry.asset_tag for entry in page.items], page.total) == (["TSH-DR-0043"], 1)
        every = reads.page(ADMINISTRATOR, ListUnitsQuery(text="dr", status=AssetStatus.INTAKE))
        assert every.total == 2

    def test_a_branch_code_no_branch_has_is_refused_naming_it(self) -> None:
        _, reads = stocked()
        with pytest.raises(ValidationFailure) as refusal:
            reads.page(ADMINISTRATOR, ListUnitsQuery(branch_code="XYZ"))
        assert refused_parameter_of(refusal.value) == "branchCode"

    @pytest.mark.parametrize(
        "changes",
        [{"text": "d"}, {"text": "d" * 81}, {"page": 0}, {"page_size": 0}, {"page_size": 101}],
    )
    def test_a_search_the_boundary_would_refuse_is_refused_again(
        self, changes: dict[str, object]
    ) -> None:
        search = AdminAssetSearch(
            text=None, branch_id=None, status=None, model_id=None, page=1, page_size=20
        )
        with pytest.raises(ValueError, match="Attempted to"):
            replace(search, **changes)


class TestOneUnit:
    """One unit is read with its history, and a tag nobody carries is not found."""

    def test_a_unit_is_read_with_its_history_the_newest_first(self) -> None:
        store, reads = stocked()
        unit = store.unit_tagged("TSH-DR-0042")
        assert unit is not None
        store.history[unit.unit.id] = AssetHistoryFacts(
            allocations=(),
            hires=(),
            damage_reports=(),
            audit_events=(
                AuditFact(at(0), "asset.registered", None, "INTAKE", None, None, ("asset_tag",)),
                AuditFact(at(1), "asset.status_changed", "INTAKE", "AVAILABLE", None, None, ()),
            ),
        )
        detail = reads.unit(ADMINISTRATOR, "TSH-DR-0042")
        assert detail.entry.asset_tag == "TSH-DR-0042"
        assert [entry.summary for entry in detail.history] == [
            "Moved from INTAKE to AVAILABLE.",
            "Registered in the fleet at INTAKE.",
        ]
        assert store.history_asked == [HISTORY_LIMIT]

    def test_a_tag_nobody_carries_is_not_found(self) -> None:
        _, reads = stocked()
        with pytest.raises(NotFound, match="tag"):
            reads.unit(ADMINISTRATOR, "TSH-ZZ-0000")


class TestTheHistory:
    """Every fact says what happened, and the list is the newest first and cut at fifty."""

    def test_each_kind_of_fact_becomes_its_entries_newest_first(self) -> None:
        facts = AssetHistoryFacts(
            allocations=(
                AllocationFact(
                    at(1), at(9), ReleaseReason.RETURNED, "TSH-R-26-000124",
                    date(2026, 3, 3), date(2026, 3, 5),
                ),
                AllocationFact(
                    at(10), None, None, "TSH-R-26-000125", date(2026, 3, 9), date(2026, 3, 10)
                ),
            ),
            hires=(
                HireFact(
                    at(2), at(8), "TSH-H-26-000099", ConditionGrade.A, ConditionGrade.C,
                    date(2026, 3, 5),
                ),
            ),
            damage_reports=(
                DamageFact(
                    at(11), at(12), "TSH-D-26-00031", DamageSeverity.MAJOR, DamageStatus.RESOLVED
                ),
            ),
            audit_events=(
                AuditFact(
                    at(13), "asset.status_changed", "AVAILABLE", "QUARANTINED",
                    "Cracked casing.", "TSH-D-26-00031", (),
                ),
            ),
        )  # fmt: skip
        history = history_of(facts)
        assert [(entry.kind, entry.reference) for entry in history] == [
            (K.AUDIT_EVENT, REPORT),
            (K.DAMAGE_REPORT, REPORT),
            (K.DAMAGE_REPORT, REPORT),
            (K.ALLOCATION, "TSH-R-26-000125"),
            (K.ALLOCATION, "TSH-R-26-000124"),
            (K.RENTAL, RENTAL),
            (K.RENTAL, RENTAL),
            (K.ALLOCATION, "TSH-R-26-000124"),
        ]
        assert [entry.summary for entry in history] == [
            "Moved from AVAILABLE to QUARANTINED. Cracked casing.",
            f"Damage report {REPORT} resolved.",
            f"Damage report {REPORT} filed for major damage.",
            "Held for booking TSH-R-26-000125 from 2026-03-09 to 2026-03-10.",
            "Released from booking TSH-R-26-000124 when the hire ended.",
            f"Came back from hire {RENTAL} in grade C.",
            f"Handed over on hire {RENTAL} in grade A, due back 2026-03-05.",
            "Held for booking TSH-R-26-000124 from 2026-03-03 to 2026-03-05.",
        ]
        assert history[0].at == at(13)

    @pytest.mark.parametrize(
        ("reason", "ending"),
        [
            (ReleaseReason.CANCELLED, " when it was cancelled."),
            (ReleaseReason.NO_SHOW, " when nobody collected it."),
            (ReleaseReason.EXPIRED, " when the hold ran out."),
            (ReleaseReason.REALLOCATED, " by an administrator."),
            (None, "."),
        ],
    )
    def test_a_release_says_why_the_booking_let_the_unit_go(
        self, reason: ReleaseReason | None, ending: str
    ) -> None:
        fact = AllocationFact(
            at(0), at(1), reason, "TSH-R-26-000124", date(2026, 3, 3), date(2026, 3, 5)
        )
        released = history_of(replace(NO_HISTORY, allocations=(fact,)))[0]
        assert released.summary == f"Released from booking TSH-R-26-000124{ending}"

    def test_a_unit_still_out_or_lost_and_a_report_written_off_say_so(self) -> None:
        out = HireFact(at(0), None, "TSH-H-26-000100", ConditionGrade.B, None, date(2026, 3, 5))
        lost = HireFact(at(1), at(2), "TSH-H-26-000101", ConditionGrade.B, None, date(2026, 3, 5))
        open_report = DamageFact(
            at(3), None, "TSH-D-26-00032", DamageSeverity.MINOR, DamageStatus.OPEN
        )
        written_off = DamageFact(
            at(4), at(5), "TSH-D-26-00033", DamageSeverity.WRITE_OFF, DamageStatus.WRITTEN_OFF
        )
        history = history_of(
            replace(NO_HISTORY, hires=(out, lost), damage_reports=(open_report, written_off))
        )
        assert [entry.summary for entry in history] == [
            "Damage report TSH-D-26-00033 written off.",
            "Damage report TSH-D-26-00033 filed for damage beyond repair.",
            "Damage report TSH-D-26-00032 filed for minor damage.",
            "Recorded as lost on hire TSH-H-26-000101.",
            "Handed over on hire TSH-H-26-000101 in grade B, due back 2026-03-05.",
            "Handed over on hire TSH-H-26-000100 in grade B, due back 2026-03-05.",
        ]

    @pytest.mark.parametrize(
        ("fields", "summary"),
        [
            (("notes",), "Changed the notes."),
            (("serial_number", "notes"), "Changed the serial number and the notes."),
            (
                ("serial_number", "condition_grade", "hour_meter_reading"),
                "Changed the serial number, the grade and the meter reading.",
            ),
            (("colour",), "Changed colour."),
            ((), "Changed its details."),
        ],
    )
    def test_an_edit_names_the_fields_it_changed(
        self, fields: tuple[str, ...], summary: str
    ) -> None:
        event = AuditFact(at(0), "asset.updated", None, None, None, None, fields)
        assert history_of(replace(NO_HISTORY, audit_events=(event,)))[0].summary == summary

    def test_an_action_the_history_has_no_sentence_for_is_named(self) -> None:
        event = AuditFact(at(0), "asset.inspected", None, None, None, None, ())
        entry = history_of(replace(NO_HISTORY, audit_events=(event,)))[0]
        assert (entry.summary, entry.kind) == ("Recorded as asset.inspected.", K.AUDIT_EVENT)

    def test_the_history_is_cut_at_its_limit_keeping_the_newest(self) -> None:
        events = tuple(
            AuditFact(at(hour), "asset.updated", None, None, None, None, ("notes",))
            for hour in range(HISTORY_LIMIT + 5)
        )
        history = history_of(replace(NO_HISTORY, audit_events=events))
        assert len(history) == HISTORY_LIMIT
        assert (history[0].at, history[-1].at) == (at(HISTORY_LIMIT + 4), at(5))

    def test_entries_of_one_instant_keep_the_order_they_were_written_in(self) -> None:
        newer = AuditFact(at(0), "asset.status_changed", "INTAKE", "AVAILABLE", None, None, ())
        older = AuditFact(at(0), "asset.registered", None, "INTAKE", None, None, ())
        history = history_of(replace(NO_HISTORY, audit_events=(newer, older)))
        assert [entry.summary for entry in history] == [
            "Moved from INTAKE to AVAILABLE.",
            "Registered in the fleet at INTAKE.",
        ]
