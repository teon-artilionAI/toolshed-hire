"""How busy the season of trading history is, model by model and day by day.

Nothing here touches a database. These are the figures the planner draws from,
kept apart so the shape of the season can be read and tuned without reading
the planner.

The season runs from 1 June to 30 September 2026. Every date is fixed, so a run
next year writes the same history as a run today. The branches close on Sundays
and on the three public holidays that fall in the season, and nothing starts,
falls due or comes back on a day the branch is closed.

Demand is set per unit of a model. A few models are in steady demand and keep
about half their units out, a few hardly move, and the rest sit between ten and
thirty percent. The month moves it as well. Cape Town is wet from June to
August, so pumps, heaters and dryers are busier then and the garden tools are
quieter, and September brings the spring work back.

The chances below are plain floats because they are odds and never money. Every
amount the history charges is worked out by the domain from Decimal rates.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Final

# The seed every choice of the season is drawn from. I picked it from a run of
# neighbouring seeds as one whose draw lands near the stated chances, so the
# season shows about one damaged hire in forty and one late hire in twelve.
HISTORY_RANDOM_SEED: Final[int] = 20260611
SEASON_FIRST_DAY: Final[date] = date(2026, 6, 1)
SEASON_LAST_DAY: Final[date] = date(2026, 9, 30)
SUNDAY: Final[int] = 6
# Youth Day, the Monday after National Women's Day and Heritage Day.
PUBLIC_HOLIDAYS: Final[frozenset[date]] = frozenset(
    {date(2026, 6, 16), date(2026, 8, 10), date(2026, 9, 24)}
)

# How many hires of each length in days come out of every hundred. Two in
# three are shorter than a week, and a week and a fortnight are the lengths a
# contractor books most after that.
HIRE_LENGTH_WEIGHTS: Final[Mapping[int, int]] = MappingProxyType(
    {1: 16, 2: 15, 3: 12, 4: 9, 5: 8, 6: 5, 7: 14, 8: 2, 9: 2, 10: 5, 11: 1, 12: 1, 13: 1, 14: 9}
)
MEAN_HIRE_DAYS: Final[float] = sum(
    days * weight for days, weight in HIRE_LENGTH_WEIGHTS.items()
) / sum(HIRE_LENGTH_WEIGHTS.values())
# Most hires take one unit, some take two or three of the same model.
QUANTITY_WEIGHTS: Final[Mapping[int, int]] = MappingProxyType({1: 84, 2: 12, 3: 4})

LATE_RETURN_CHANCE: Final[float] = 1 / 12
DAYS_LATE_CHOICES: Final[tuple[int, ...]] = (1, 2, 3)
DAMAGE_CHANCE: Final[float] = 1 / 40
CHARGEABLE_DAMAGE_CHANCE: Final[float] = 0.5
# A hire that takes a second model of the same category with it, a mixer and a
# poker for one pour for example.
SECOND_LINE_CHANCE: Final[float] = 0.07
# A walk in who books and collects in the same visit.
SAME_DAY_CHANCE: Final[float] = 0.45
LONGEST_LEAD_DAYS: Final[int] = 10
# A customer usually hires from the branch they registered at.
OWN_BRANCH_CHANCE: Final[float] = 0.85
# A customer with a login books online this often, and at the counter otherwise.
ONLINE_BOOKING_CHANCE: Final[float] = 0.6

# The share of the season a unit of each kind of model is wanted for. The
# planner turns it into requests a day, and requests that find no free unit
# are lost, so what a model achieves is a little under what it is asked for.
STEADY_DEMAND: Final[float] = 0.62
SLOW_DEMAND: Final[float] = 0.05
NORMAL_DEMAND_FLOOR: Final[float] = 0.10
NORMAL_DEMAND_STEPS: Final[int] = 12
NORMAL_DEMAND_STEP: Final[float] = 0.01

# The workhorses of a Cape Town hire shop, in steady demand all season.
STEADY_MODELS: Final[frozenset[str]] = frozenset(
    {
        "DR-BOSCH-GBH226",
        "PC-WACKER-CP100",
        "MX-BAUMAX-140L",
        "GN-HONDA-65KVA",
        "AG-BOSCH-GWS22230",
        "CL-KARCHER-HD515C",
        "SC-INSTANT-TOWER6M",
        "PU-HONDA-WB20XT",
        "CS-STIHL-TS420",
    }
)
# Heavy or specialised plant that is rarely asked for.
SLOW_MODELS: Final[frozenset[str]] = frozenset(
    {
        "PC-BOMAG-BW65H",
        "GN-ATLASCOPCO-QAS20",
        "ST-ATLASCOPCO-XAS88",
        "WD-LINCOLN-RANGER305D",
        "GN-ATLASCOPCO-HILIGHTV5",
        "DR-HUSQVARNA-DM230",
        "EC-TRACTEL-TU16",
    }
)

JUNE: Final[int] = 6
JULY: Final[int] = 7
AUGUST: Final[int] = 8
SEPTEMBER: Final[int] = 9
NO_SEASONAL_CHANGE: Final[float] = 1.0
# How each month moves the demand of a category, against an ordinary month.
SEASONAL_FACTORS: Final[Mapping[str, Mapping[int, float]]] = MappingProxyType(
    {
        "PUMPS": MappingProxyType({JUNE: 1.4, JULY: 1.5, AUGUST: 1.3, SEPTEMBER: 0.8}),
        "SITE-EQUIP": MappingProxyType({JUNE: 1.2, JULY: 1.3, AUGUST: 1.1, SEPTEMBER: 0.8}),
        "GARDEN": MappingProxyType({JUNE: 0.6, JULY: 0.6, AUGUST: 0.9, SEPTEMBER: 1.5}),
        "CLEANING": MappingProxyType({JUNE: 0.8, JULY: 0.8, AUGUST: 1.0, SEPTEMBER: 1.3}),
        "ACCESS": MappingProxyType({JUNE: 0.9, JULY: 0.9, AUGUST: 1.0, SEPTEMBER: 1.2}),
    }
)
# The rest of the range picks up a little in September as the building work of
# spring starts.
SPRING_FACTOR: Final[float] = 1.1
# Monday to Sunday. Mondays and Fridays are the busiest counter days, and the
# branches are shut on a Sunday.
WEEKDAY_FACTORS: Final[tuple[float, ...]] = (1.2, 1.0, 1.0, 0.95, 1.15, 0.85, 0.0)
# The days of the season the branches are open, against every day of it. The
# requests of a closed day are spread over the open ones.
OPEN_DAY_SHARE: Final[float] = 0.85


def is_open(day: date) -> bool:
    """Return True when the branches trade on a day, which is every day but Sundays and holidays."""
    return day.weekday() != SUNDAY and day not in PUBLIC_HOLIDAYS


def demand_of(sku: str) -> float:
    """Return the share of the season a unit of this model is wanted for.

    A model in neither the steady nor the slow list gets a figure from ten to
    thirty percent fixed by a checksum of its SKU, so it is scattered and is the
    same on every run.
    """
    if sku in STEADY_MODELS:
        return STEADY_DEMAND
    if sku in SLOW_MODELS:
        return SLOW_DEMAND
    step = zlib.crc32(sku.encode("ascii")) % NORMAL_DEMAND_STEPS
    return NORMAL_DEMAND_FLOOR + step * NORMAL_DEMAND_STEP


def seasonal_factor(category_code: str, day: date) -> float:
    """Return how the month of a day moves the demand of a category."""
    by_month = SEASONAL_FACTORS.get(category_code)
    if by_month is not None:
        return by_month.get(day.month, NO_SEASONAL_CHANGE)
    return SPRING_FACTOR if day.month == SEPTEMBER else NO_SEASONAL_CHANGE


def requests_per_unit(sku: str, category_code: str, day: date) -> float:
    """Return how many hires of one unit of a model are asked for on a day, on average.

    A unit wanted for a share of the season, hired for the mean length, is
    asked for that share divided by the mean length on each day, and the open
    days carry the requests of the closed ones.
    """
    if not is_open(day):
        return 0.0
    base = demand_of(sku) / MEAN_HIRE_DAYS / OPEN_DAY_SHARE
    return base * seasonal_factor(category_code, day) * WEEKDAY_FACTORS[day.weekday()]
