"""The history of one unit, built from the four places its life is recorded (FR-23, SC-21).

A unit's life is written down in four places. Its allocations say which
bookings held it and when they let it go, its rental items say when it went
out and how it came back, its damage reports say when it was found damaged and
how that ended, and its audit events say when it was registered, edited and
moved through its lifecycle. Each fact becomes one entry for each instant it
records, so an allocation that was let go is two entries, the hold and the
release.

The entries are put in one list, the newest first, and the list is cut at
fifty. The query reads at most fifty facts of each kind, ordered by the latest
instant each carries, so the fifty newest entries are always among what it
read. A sentence says what happened in the words the counter uses, with the
reference it belongs to beside it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from types import MappingProxyType
from typing import Final

from app.application.catalogue.asset_changes import (
    ASSET_STATUS_CHANGED_ACTION,
    UNIT_REGISTERED_ACTION,
    UNIT_UPDATED_ACTION,
)
from app.application.catalogue.asset_read_models import (
    AllocationFact,
    AssetHistoryEntry,
    AssetHistoryFacts,
    AssetHistoryKind,
    AuditFact,
    DamageFact,
    HireFact,
)
from app.domain.asset_register import (
    CONDITION_GRADE,
    HOUR_METER_READING,
    NOTES,
    SERIAL_NUMBER,
)
from app.domain.damage import REPORT_STANDING_IN_WORDS
from app.domain.enums import DamageSeverity, ReleaseReason

# The most entries the history of a unit shows.
HISTORY_LIMIT: Final[int] = 50
ONE_FIELD: Final[int] = 1
NOTHING_NAMED_MESSAGE: Final[str] = "Changed its details."

# Why a booking let the unit go, as the end of a sentence.
RELEASED_IN_WORDS: Final[Mapping[ReleaseReason | None, str]] = MappingProxyType(
    {
        ReleaseReason.RETURNED: " when the hire ended",
        ReleaseReason.CANCELLED: " when it was cancelled",
        ReleaseReason.NO_SHOW: " when nobody collected it",
        ReleaseReason.EXPIRED: " when the hold ran out",
        ReleaseReason.REALLOCATED: " by an administrator",
        None: "",
    }
)
SEVERITY_IN_WORDS: Final[Mapping[DamageSeverity, str]] = MappingProxyType(
    {
        DamageSeverity.MINOR: "minor damage",
        DamageSeverity.MAJOR: "major damage",
        DamageSeverity.WRITE_OFF: "damage beyond repair",
    }
)
FIELD_IN_WORDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        SERIAL_NUMBER: "the serial number",
        CONDITION_GRADE: "the grade",
        HOUR_METER_READING: "the meter reading",
        NOTES: "the notes",
    }
)
# Which of two entries of the same instant is listed first, newest first. Two
# entries of one kind at one instant keep the order the query read them in,
# which for the audit events is the order they were written, the newest first.
KIND_ORDER: Final[Mapping[AssetHistoryKind, int]] = MappingProxyType(
    {
        AssetHistoryKind.ALLOCATION: 0,
        AssetHistoryKind.RENTAL: 1,
        AssetHistoryKind.DAMAGE_REPORT: 2,
        AssetHistoryKind.AUDIT_EVENT: 3,
    }
)


def history_of(
    facts: AssetHistoryFacts, limit: int = HISTORY_LIMIT
) -> tuple[AssetHistoryEntry, ...]:
    """Return the entries of a unit's history, the newest first, at most `limit` of them."""
    entries = [
        *(entry for fact in facts.allocations for entry in _allocation_entries(fact)),
        *(entry for fact in facts.hires for entry in _hire_entries(fact)),
        *(entry for fact in facts.damage_reports for entry in _damage_entries(fact)),
        *(_audit_entry(fact) for fact in facts.audit_events),
    ]
    entries.sort(key=lambda entry: (entry.at, KIND_ORDER[entry.kind]), reverse=True)
    return tuple(entries[:limit])


def _allocation_entries(fact: AllocationFact) -> Iterator[AssetHistoryEntry]:
    """Yield the hold of an allocation and, once it was let go, its release."""
    reference = fact.reservation_reference
    yield AssetHistoryEntry(
        at=fact.allocated_at,
        kind=AssetHistoryKind.ALLOCATION,
        summary=(
            f"Held for booking {reference} from {fact.start_date.isoformat()} to "
            f"{fact.end_date.isoformat()}."
        ),
        reference=reference,
    )
    if fact.released_at is not None:
        yield AssetHistoryEntry(
            at=fact.released_at,
            kind=AssetHistoryKind.ALLOCATION,
            summary=f"Released from booking {reference}{RELEASED_IN_WORDS[fact.release_reason]}.",
            reference=reference,
        )


def _hire_entries(fact: HireFact) -> Iterator[AssetHistoryEntry]:
    """Yield the handover of a hire and, once it ended, the return or the loss."""
    reference = fact.rental_reference
    yield AssetHistoryEntry(
        at=fact.checked_out_at,
        kind=AssetHistoryKind.RENTAL,
        summary=(
            f"Handed over on hire {reference} in grade {fact.condition_out.value}, due back "
            f"{fact.due_back_on.isoformat()}."
        ),
        reference=reference,
    )
    if fact.returned_at is None:
        return
    summary = (
        f"Recorded as lost on hire {reference}."
        if fact.condition_in is None
        else f"Came back from hire {reference} in grade {fact.condition_in.value}."
    )
    yield AssetHistoryEntry(
        at=fact.returned_at, kind=AssetHistoryKind.RENTAL, summary=summary, reference=reference
    )


def _damage_entries(fact: DamageFact) -> Iterator[AssetHistoryEntry]:
    """Yield the filing of a damage report and, once it was closed, how it ended."""
    reference = fact.reference
    yield AssetHistoryEntry(
        at=fact.reported_at,
        kind=AssetHistoryKind.DAMAGE_REPORT,
        summary=f"Damage report {reference} filed for {SEVERITY_IN_WORDS[fact.severity]}.",
        reference=reference,
    )
    if fact.resolved_at is not None:
        yield AssetHistoryEntry(
            at=fact.resolved_at,
            kind=AssetHistoryKind.DAMAGE_REPORT,
            summary=f"Damage report {reference} {REPORT_STANDING_IN_WORDS[fact.status]}.",
            reference=reference,
        )


def _audit_entry(fact: AuditFact) -> AssetHistoryEntry:
    """Return the entry of one audit event, in the words its action is told in."""
    told = AUDIT_SUMMARIES.get(fact.action, _action_name)
    return AssetHistoryEntry(
        at=fact.occurred_at,
        kind=AssetHistoryKind.AUDIT_EVENT,
        summary=told(fact),
        reference=fact.reference,
    )


def _registered(fact: AuditFact) -> str:
    """Return what the registration of a unit says."""
    return f"Registered in the fleet at {fact.after_status}."


def _updated(fact: AuditFact) -> str:
    """Return what an edit of a unit's paperwork says, naming the fields it changed."""
    names = [FIELD_IN_WORDS.get(field, field) for field in fact.changed_fields]
    if not names:
        return NOTHING_NAMED_MESSAGE
    listed = names[0] if len(names) == ONE_FIELD else f"{', '.join(names[:-1])} and {names[-1]}"
    return f"Changed {listed}."


def _status_changed(fact: AuditFact) -> str:
    """Return what a change of status says, with the reason when one was given."""
    moved = f"Moved from {fact.before_status} to {fact.after_status}."
    return moved if fact.reason is None else f"{moved} {fact.reason}"


def _action_name(fact: AuditFact) -> str:
    """Return the name of an action the history has no sentence for."""
    return f"Recorded as {fact.action}."


AUDIT_SUMMARIES: Final[Mapping[str, Callable[[AuditFact], str]]] = MappingProxyType(
    {
        UNIT_REGISTERED_ACTION: _registered,
        UNIT_UPDATED_ACTION: _updated,
        ASSET_STATUS_CHANGED_ACTION: _status_changed,
    }
)
