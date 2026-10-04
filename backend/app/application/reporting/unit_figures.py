"""The figures of each unit, put together from the evidence the query object read.

The query object reads three parts and works nothing out. This module turns
the dated facts about each unit into business days, hands them to the domain
for the two day counts, shares every hire charge raised on a whole hire
between its units through the hire charge share policy, and adds each unit's
share to the money charged on it directly. Every rule it applies lives in the
domain, in `app.domain.unit_days`, `app.domain.policies.hire_charge_share` and
`app.domain.contribution`.

An instant becomes the business day it falls on in Cape Town, so a hire that
went out at half past midnight belongs to the new day.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.application.clock import business_day
from app.application.reporting.evidence import (
    DatedRow,
    EvidenceKind,
    FleetEvidence,
    SharedHireRow,
    UnitRow,
)
from app.domain.contribution import Contribution
from app.domain.money import Money
from app.domain.policies.hire_charge_share import UnitOnLine, shares_of_hire_charge
from app.domain.report_days import DaySpan, span_or_none
from app.domain.unit_days import (
    Spell,
    StatusChange,
    StatusRecord,
    UnitDays,
    UnitService,
    UnitUse,
    unit_days,
)


@dataclass(frozen=True, slots=True)
class UnitFigures:
    """One unit with its two day counts and its parts of gross contribution.

    Attributes:
        unit: What the unit is and where it is.
        days: Its days on hire and its serviceable days.
        contribution: Its hire revenue, late fees, recovery and repair costs.

    """

    unit: UnitRow
    days: UnitDays
    contribution: Contribution


def figures_of(evidence: FleetEvidence, period: DaySpan, today: date) -> tuple[UnitFigures, ...]:
    """Return the figures of every unit in scope, in the order the units were read.

    Args:
        evidence: What the query object read for the period.
        period: The period, half open.
        today: The current business day, which a unit still out is on hire on.

    """
    dated: dict[UUID, list[DatedRow]] = {}
    for fact in evidence.dated:
        dated.setdefault(fact.asset_id, []).append(fact)
    shares = hire_shares(evidence.shared_hire)
    return tuple(
        UnitFigures(
            unit=unit,
            days=unit_days(
                _service_of(unit, dated.get(unit.asset_id, [])),
                _use_of(dated.get(unit.asset_id, [])),
                period,
                today,
            ),
            contribution=_contribution_of(unit, shares.get(unit.asset_id, Money.zero())),
        )
        for unit in evidence.units
    )


def hire_shares(rows: Sequence[SharedHireRow]) -> dict[UUID, Money]:
    """Return what each unit is given of the hire charges raised on whole hires, added up.

    The rows of one charge arrive together and in the order its shares are
    taken, and the policy gives the last of them the rounding cent.
    """
    by_charge: dict[UUID, list[SharedHireRow]] = {}
    for row in rows:
        by_charge.setdefault(row.charge_id, []).append(row)
    given: dict[UUID, Money] = {}
    for units in by_charge.values():
        shares = shares_of_hire_charge(
            Money.create(units[0].amount_ex_vat),
            [UnitOnLine(Money.create(unit.line_amount), unit.units_on_line) for unit in units],
        )
        for unit, share in zip(units, shares, strict=True):
            given[unit.asset_id] = given.get(unit.asset_id, Money.zero()).add(share)
    return given


def _service_of(unit: UnitRow, facts: Iterable[DatedRow]) -> UnitService:
    """Return what is known about whether the unit could be hired."""
    chosen = list(facts)
    return UnitService(
        acquired_on=unit.acquired_on,
        retired_on=unit.retired_on,
        statuses=StatusRecord(
            held_on_entry=unit.held_on_entry,
            changes=tuple(_changes(chosen)),
            held_on_exit=unit.held_on_exit,
            held_now=unit.status,
        ),
        damage=_spells(chosen, EvidenceKind.DAMAGE),
        losses=_spells(chosen, EvidenceKind.LOSS),
    )


def _use_of(facts: Iterable[DatedRow]) -> UnitUse:
    """Return what is known about when the unit was out or booked."""
    chosen = list(facts)
    bookings = (
        span_or_none(fact.begins_on, fact.ends_on)
        for fact in chosen
        if fact.kind is EvidenceKind.BOOKING
        and fact.begins_on is not None
        and fact.ends_on is not None
    )
    return UnitUse(
        hires=_spells(chosen, EvidenceKind.HIRE),
        bookings=tuple(span for span in bookings if span is not None),
    )


def _changes(facts: Iterable[DatedRow]) -> Iterable[StatusChange]:
    """Yield each recorded change of status, on the business day it was recorded."""
    for fact in facts:
        if (
            fact.kind is EvidenceKind.STATUS
            and fact.began_at is not None
            and fact.moved_from is not None
            and fact.moved_to is not None
        ):
            yield StatusChange(
                on=business_day(fact.began_at), moved_from=fact.moved_from, moved_to=fact.moved_to
            )


def _spells(facts: Iterable[DatedRow], kind: EvidenceKind) -> tuple[Spell, ...]:
    """Return each fact of one kind as the business days it ran over."""
    return tuple(
        Spell(
            begins=business_day(fact.began_at),
            ends=business_day(fact.ended_at) if fact.ended_at is not None else None,
        )
        for fact in facts
        if fact.kind is kind and fact.began_at is not None
    )


def _contribution_of(unit: UnitRow, shared_hire: Money) -> Contribution:
    """Return the unit's parts of gross contribution, its share of whole hires included."""
    return Contribution(
        hire_revenue=Money.create(unit.hire_revenue).add(shared_hire),
        late_fees=Money.create(unit.late_fees),
        damage_recovery=Money.create(unit.damage_recovery),
        repair_costs=Money.create(unit.repair_costs),
    )
