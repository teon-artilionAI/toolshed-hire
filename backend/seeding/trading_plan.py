"""Plan the season of trading history, hire by hire, without touching a database.

The planner walks the season a day at a time. On each day, for each model at
each branch, it draws how many hires are asked for from the demand figures in
`trading_demand`, and for each one the length, the quantity, whether it comes
back late and whether a unit comes back damaged. A request is met only by
units of that model at that branch which are free for every day they will be
away, counted to the day they actually come back and, for a damaged unit, to
the day its repair is done. A request no unit can meet is lost, as it would be
at a real counter.

Each unit keeps a diary of the days it is away. It starts with whatever the
database already holds for it in the season, so the history never puts a unit
out on a day it really was out. The free unit that has stood idle longest goes
out first, which is how a counter rotates stock.

One generator, seeded with a fixed number, makes every choice, and the season,
the units and the customers are always taken in the same order, so the same
fleet always gives the same plan.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from random import Random
from uuid import UUID

from app.domain.period import BookingPeriod
from app.domain.report_days import DaySpan
from seeding.trading_damage import DamagePlan, plan_damage
from seeding.trading_demand import (
    DAMAGE_CHANCE,
    DAYS_LATE_CHOICES,
    HIRE_LENGTH_WEIGHTS,
    HISTORY_RANDOM_SEED,
    LATE_RETURN_CHANCE,
    ONLINE_BOOKING_CHANCE,
    OWN_BRANCH_CHANCE,
    QUANTITY_WEIGHTS,
    SEASON_FIRST_DAY,
    SEASON_LAST_DAY,
    SECOND_LINE_CHANCE,
    is_open,
    requests_per_unit,
)
from seeding.trading_records import (
    CustomerChoice,
    FleetUnit,
    PlannedDamage,
    PlannedHire,
    PlannedLine,
    numbered,
)
from seeding.trading_times import (
    ONE_DAY,
    booking_times,
    can_go_out_on,
    ready_at,
    report_time,
    return_time,
    workshop_time,
)


@dataclass(frozen=True, slots=True)
class DamageDraw:
    """The damage a request drew, and the day the workshop is done with the unit."""

    plan: DamagePlan
    resolved_on: date


@dataclass(slots=True)
class UnitDiary:
    """The days one unit is away, and when it last came back.

    Attributes:
        unit: The unit.
        away: Every run of days it is out or in the workshop, half open.
        last_back: The day it last came back, which decides who goes out next.
        back_at: The moment it last came back or left the workshop, or None
            before its first hire of the season.

    """

    unit: FleetUnit
    away: list[DaySpan] = field(default_factory=list)
    last_back: date = SEASON_FIRST_DAY
    back_at: datetime | None = None

    def is_free(self, begins: date, ends: date) -> bool:
        """Return True when the unit is in the fleet, ready that day and away on none of them."""
        if self.unit.acquired_on > begins or not can_go_out_on(begins, self.back_at):
            return False
        return all(not (span.begins < ends and begins < span.ends) for span in self.away)

    def book(self, begins: date, ends: date, back_at: datetime) -> None:
        """Mark the unit away from one day up to the day it is back, and when it is back."""
        self.away.append(DaySpan(begins, ends))
        self.last_back = ends
        self.back_at = back_at


def plan_season(
    units: Sequence[FleetUnit],
    already_away: Mapping[UUID, Sequence[DaySpan]],
    customers: Sequence[CustomerChoice],
) -> tuple[PlannedHire, ...]:
    """Return every hire of the season, numbered, in the order the bookings were made.

    Args:
        units: The units that may go out. Their order does not matter.
        already_away: Days the database already has each unit away in the season.
        customers: Who may hire. Their order does not matter.

    Raises:
        ValueError: If there is nobody to hire to.

    """
    if not customers:
        raise ValueError("Attempted to plan a season of hires with no customer to hire to.")
    return numbered(_SeasonPlanner(units, already_away, customers).plan())


class _SeasonPlanner:
    """Walks the season and turns the requests of each day into hires."""

    def __init__(
        self,
        units: Sequence[FleetUnit],
        already_away: Mapping[UUID, Sequence[DaySpan]],
        customers: Sequence[CustomerChoice],
    ) -> None:
        """Index the units by branch and model and seed the one generator."""
        self._rng = Random(HISTORY_RANDOM_SEED)
        self._diaries: dict[tuple[str, str], list[UnitDiary]] = {}
        for unit in sorted(units, key=lambda unit: unit.asset_tag):
            diary = UnitDiary(unit, list(already_away.get(unit.asset_id, ())))
            self._diaries.setdefault((unit.branch_code, unit.sku), []).append(diary)
        self._customers = sorted(customers, key=lambda customer: customer.key)
        self._hires: list[PlannedHire] = []

    def plan(self) -> list[PlannedHire]:
        """Return the hires of every day of the season, not yet numbered."""
        day = SEASON_FIRST_DAY
        while day <= SEASON_LAST_DAY:
            for branch_code, sku in sorted(self._diaries):
                diaries = self._diaries[(branch_code, sku)]
                rate = requests_per_unit(sku, diaries[0].unit.category_code, day)
                for _request in range(_poisson(self._rng, rate * len(diaries))):
                    self._meet_request(day, branch_code, diaries)
            day += ONE_DAY
        return self._hires

    def _meet_request(self, day: date, branch_code: str, diaries: list[UnitDiary]) -> None:
        """Turn one request into a hire if free units can meet it, and book them."""
        period = self._period_from(day)
        if period is None:
            return
        returned_on = self._return_day(period.end)
        sample = diaries[0].unit
        damage = self._damage(sample, returned_on)
        wanted = min(_weighted(self._rng, QUANTITY_WEIGHTS), len(diaries))
        chosen = _free(diaries, period.start, returned_on)[:wanted]
        if not chosen:
            return
        chosen.extend(self._second_line(branch_code, sample, period.start, returned_on))
        damaged = _damaged_unit(chosen, period.start, damage)
        hire = self._planned(branch_code, period, returned_on, chosen, damaged, damage)
        for diary in chosen:
            if hire.damage is not None and damage is not None and diary is damaged:
                diary.book(period.start, damage.resolved_on, hire.damage.resolved_at)
            else:
                diary.book(period.start, returned_on, hire.returned_at)
        self._hires.append(hire)

    def _planned(
        self,
        branch_code: str,
        period: BookingPeriod,
        returned_on: date,
        chosen: Sequence[UnitDiary],
        damaged: UnitDiary | None,
        damage: DamageDraw | None,
    ) -> PlannedHire:
        """Return the hire with its customer and its times, the units' readiness respected."""
        customer = self._customer(branch_code)
        online = customer.has_login and self._rng.random() < ONLINE_BOOKING_CHANCE
        ready = ready_at(period.start, (diary.back_at for diary in chosen))
        times = booking_times(self._rng, period.start, online=online, ready=ready)
        returned_at = return_time(self._rng, returned_on)
        planned_damage = None
        if damaged is not None and damage is not None:
            planned_damage = PlannedDamage(
                asset_id=damaged.unit.asset_id,
                plan=damage.plan,
                reported_at=report_time(self._rng, returned_at),
                resolved_at=workshop_time(self._rng, damage.resolved_on),
            )
        return PlannedHire(
            branch_code=branch_code,
            customer_key=customer.key,
            booked_online=online,
            lines=_lines_of(chosen),
            period=period,
            times=times,
            returned_on=returned_on,
            returned_at=returned_at,
            damage=planned_damage,
        )

    def _period_from(self, day: date) -> BookingPeriod | None:
        """Draw the hire period starting on a day, due back on a day the branch is open."""
        end = day + timedelta(days=_weighted(self._rng, HIRE_LENGTH_WEIGHTS))
        while not is_open(end):
            end += ONE_DAY
        end = min(end, SEASON_LAST_DAY)
        return BookingPeriod(day, end) if end > day else None

    def _return_day(self, due: date) -> date:
        """Draw the day the units came back, which is the due day or one to three days later."""
        if self._rng.random() >= LATE_RETURN_CHANCE:
            return due
        late = [due + ONE_DAY * days for days in DAYS_LATE_CHOICES]
        open_days = [day for day in late if is_open(day) and day <= SEASON_LAST_DAY]
        return self._rng.choice(open_days) if open_days else due

    def _damage(self, sample: FleetUnit, returned_on: date) -> DamageDraw | None:
        """Draw whether a unit comes back damaged, with the day its repair is done."""
        if self._rng.random() >= DAMAGE_CHANCE:
            return None
        plan = plan_damage(self._rng, sample.category_code, sample.replacement_value)
        resolved_on = returned_on + ONE_DAY * plan.repair_days
        while not is_open(resolved_on):
            resolved_on += ONE_DAY
        resolved_on = min(resolved_on, SEASON_LAST_DAY)
        return DamageDraw(plan, resolved_on) if resolved_on > returned_on else None

    def _second_line(
        self, branch_code: str, sample: FleetUnit, begins: date, ends: date
    ) -> list[UnitDiary]:
        """Draw whether the hire takes a unit of another model of the same category too."""
        if self._rng.random() >= SECOND_LINE_CHANCE:
            return []
        others = [
            sku
            for (branch, sku), diaries in sorted(self._diaries.items())
            if branch == branch_code
            and sku != sample.sku
            and diaries[0].unit.category_code == sample.category_code
        ]
        if not others:
            return []
        return _free(self._diaries[(branch_code, self._rng.choice(others))], begins, ends)[:1]

    def _customer(self, branch_code: str) -> CustomerChoice:
        """Draw who hired, usually somebody registered at the branch."""
        pool = self._customers
        if self._rng.random() < OWN_BRANCH_CHANCE:
            pool = [customer for customer in pool if customer.branch_code == branch_code] or pool
        return self._rng.choices(pool, weights=[customer.weight for customer in pool])[0]


def _free(diaries: Sequence[UnitDiary], begins: date, ends: date) -> list[UnitDiary]:
    """Return the units free for the days asked for, the longest idle first."""
    free = [diary for diary in diaries if diary.is_free(begins, ends)]
    return sorted(free, key=lambda diary: (diary.last_back, diary.unit.asset_tag))


def _damaged_unit(
    chosen: Sequence[UnitDiary], begins: date, damage: DamageDraw | None
) -> UnitDiary | None:
    """Return the unit that came back damaged, one free until its repair is done, or None."""
    if damage is None:
        return None
    return next((diary for diary in chosen if diary.is_free(begins, damage.resolved_on)), None)


def _lines_of(chosen: Sequence[UnitDiary]) -> tuple[PlannedLine, ...]:
    """Group the units that went out by model, in the order they were chosen."""
    by_sku: dict[str, list[UUID]] = {}
    for diary in chosen:
        by_sku.setdefault(diary.unit.sku, []).append(diary.unit.asset_id)
    return tuple(PlannedLine(sku, tuple(asset_ids)) for sku, asset_ids in by_sku.items())


def _weighted(rng: Random, weights: Mapping[int, int]) -> int:
    """Draw one of the keys of a table of weights, in proportion to its weight."""
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _poisson(rng: Random, mean: float) -> int:
    """Draw how many requests arrive when this many are expected, by Knuth's method."""
    if mean <= 0:
        return 0
    threshold = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > threshold:
        count += 1
        product *= rng.random()
    return count
